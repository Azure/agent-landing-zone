targetScope = 'resourceGroup'

import * as const from '../../constants/constants.bicep'

@description('Master switch for deploying the spoke-local Azure Firewall.')
param deployAzureFirewall bool

@description('Enable DNS proxy on the existing firewall policy without changing client DNS. Defaults to false.')
param enableFirewallDnsProxy bool = false

@description('Whether the deployment runs in network-isolated mode.')
param networkIsolation bool

@description('Enable the ACS Media (WebRTC/TURN) network rule collection.')
param enableAcsMediaEgress bool

@description('Whether Azure AI Speech is deployed (adds Speech FQDNs to jumpbox bootstrap rule).')
param deploySpeechService bool

@description('Whether the ACR Tasks agent pool is effectively deployed (computed in main.bicep).')
param deployAcrTaskAgentPool bool

@description('Extend the firewall policy with jumpbox bootstrap egress FQDNs.')
param extendFirewallForJumpboxBootstrap bool

@description('Extend the firewall policy with ACR Tasks build egress FQDNs.')
param extendFirewallForAcrTaskBuilds bool

@description('Additional FQDNs to allow for ACR Tasks builds.')
param additionalAcrTaskBuildFqdns array

@description('Deterministic resource token used to compose resource names.')
param resourceToken string

@description('Azure region for the firewall resources.')
param location string

@description('Resource tags.')
param tags object

@description('Resource ID of the virtual network hosting the AzureFirewallSubnet.')
param virtualNetworkResourceId string

@description('Name of the AzureFirewallSubnet.')
param azureFirewallSubnetName string

@description('Address prefix of the jumpbox subnet (rule source scoping).')
param jumpboxSubnetPrefix string

@description('Address prefix of the DevOps build-agents subnet (rule source scoping).')
param devopsBuildAgentsSubnetPrefix string

@description('Address prefix of the ACA environment subnet (rule source scoping).')
param acaEnvironmentSubnetPrefix string

@description('Address prefix of the agent subnet (rule source scoping).')
param agentSubnetPrefix string

@description('Whether an effective Log Analytics workspace is available for diagnostics.')
param hasEffectiveLaw bool

@description('Resource ID of the Log Analytics workspace for firewall diagnostics.')
param lawResourceId string

// Firewall FQDN allowlist for essential outbound connectivity
// Essential (shared across subnets, source = '*'): auth, container registry mirror, GitHub
var _firewallEssentialAuthFqdns = [
  #disable-next-line no-hardcoded-env-urls
  'login.microsoftonline.com'
  'login.windows.net'
  #disable-next-line no-hardcoded-env-urls
  'management.azure.com'
  'graph.microsoft.com'
  '*.applicationinsights.azure.com'
]
var _firewallEssentialContainerFqdns = ['mcr.microsoft.com', '*.data.mcr.microsoft.com']
// Platform-internal FQDNs required by the Container Apps Environment itself when egress
// is forced through Azure Firewall (fixes #39, #40). The per-pod IMDS sidecar that backs
// IDENTITY_ENDPOINT / IDENTITY_HEADER has two independent legs that both need to traverse
// the firewall: (a) a Microsoft-managed Service Bus / Event Hub namespace whose FQDN
// matches `gsm*eh.servicebus.windows.net` (the broker leg, fixes #39); (b) the ACA token
// endpoint at `control-{region}.identity.azure.net` (the token-endpoint leg, fixes #40).
// Without BOTH allow rules, every DefaultAzureCredential / ManagedIdentityCredential call
// from a Container App fails at runtime with HTTP 500 "An unexpected error occured while
// fetching the AAD Token", with no log entry on the workload side indicating the firewall
// is the cause. Also includes ACA control-plane and Azure Monitor / Log Analytics /
// Application Insights ingestion endpoints used by the platform's diagnostics pipeline,
// plus the Microsoft Foundry Agent Service's own `agent365.svc.cloud.microsoft`
// observability endpoint required by hosted agents on the Foundry Agents subnet.
// Azure Firewall application-rule wildcards only match a single label, so explicit
// wildcarded FQDNs are required (a generic `*.windows.net` does NOT match
// `gsm123eh.servicebus.windows.net`, and `*.azure.com` does NOT match
// `control-swedencentral.identity.azure.net`).
var _firewallEssentialPlatformFqdns = [
  '*.servicebus.windows.net'
  '*.identity.azure.net'
  '*.azurecontainerapps.io'
  '*.azurecontainerapps.dev'
  '*.in.applicationinsights.azure.com'
  '*.livediagnostics.monitor.azure.com'
  '*.ingest.monitor.azure.com'
  '*.monitor.azure.com'
  '*.monitor.core.windows.net'
  '*.opinsights.azure.com'
  '*.loganalytics.io'
  // Certificate revocation / trust list (Schannel + .NET) — fixes #42.
  // Without these, Windows TLS clients (Bastion/jumpbox curl.exe, Invoke-WebRequest,
  // .NET HttpClient with CheckCertificateRevocationList=true) fail with
  // CRYPT_E_REVOCATION_OFFLINE when validating Azure-managed certs served by
  // Container Apps / App Service / etc. These are public Microsoft + DigiCert
  // revocation endpoints implicit in any Azure-issued cert chain — allowing them
  // in an outbound rule does not weaken the Zero Trust posture.
  'oneocsp.microsoft.com'
  'ocsp.digicert.com'
  'crl.microsoft.com'
  'crl2.microsoft.com'
  'crl3.microsoft.com'
  'crl.digicert.com'
  'crl3.digicert.com'
  'crl4.digicert.com'
  'ctldl.windowsupdate.com'
  // Microsoft Foundry Agent Service observability/telemetry endpoint used by
  // hosted agents running on the AI Foundry Agents subnet (`agentSubnetPrefix`).
  // Live Azure validation of a network-isolated deployment proved this exact
  // FQDN is required: without it, hosted-agent requests fail after the
  // runtime has already started (the capability host provisions successfully
  // and only the post-startup observability call is blocked by the
  // firewall's default-deny). Sourced from '*' alongside the other
  // always-on platform diagnostics endpoints above because the Foundry
  // Agents subnet is already covered by this rule's source scope and no
  // separate agent-only rule is needed.
  'agent365.svc.cloud.microsoft'
]
var _firewallEssentialGitHubFqdns = [
  'github.com'
  '*.github.com'
  'raw.githubusercontent.com'
  'codeload.github.com'
  'objects.githubusercontent.com'
  '*.githubusercontent.com'
]

// Jumpbox-only FQDNs — scoped to jumpboxSubnetPrefix so ACA/agent subnets do not
// inherit developer-tooling egress. Split into purpose-labeled sets so consumers can
// audit which tool requires which endpoint.
// Docker / Docker Hub FQDNs intentionally removed — image builds run in the ACR
// Tasks agent pool (see deployAcrTaskAgentPool) and the Windows Server jumpbox
// cannot build Linux images with BuildKit anyway.
var _firewallVmBootstrapFqdns = [
  'community.chocolatey.org'
  'packages.chocolatey.org'
  '*.chocolatey.org'
  'api.nuget.org'
  'www.nuget.org'
  'dist.nuget.org'
  '*.nuget.org'
  'download.visualstudio.microsoft.com'
  '*.visualstudio.microsoft.com'
  'download.microsoft.com'
  '*.download.microsoft.com'
  'aka.ms'
  'go.microsoft.com'
  // azd auto-downloads the Bicep CLI binary from `downloads.bicep.azure.com`
  // on first run (`azd env refresh` / `azd provision`); without this FQDN the
  // jumpbox fails at "Downloading Bicep" before any deployment work begins
  // (#36).
  'downloads.bicep.azure.com'
  // GitHub release fallback used by azd, the .NET installer, and many
  // bootstrap scripts. `objects.githubusercontent.com` and
  // `codeload.github.com` are the actual content hosts behind release asset
  // and source-archive URLs respectively (#36).
  'github.com'
  '*.githubusercontent.com'
  'objects.githubusercontent.com'
  'codeload.github.com'
  #disable-next-line no-hardcoded-env-urls
  '*.core.windows.net'
  '*.azureedge.net'
]
#disable-next-line no-hardcoded-env-urls
var _firewallDevRuntimeFqdns = [
  'www.python.org'
  '*.python.org'
  'pypi.org'
  '*.pypi.org'
  'files.pythonhosted.org'
  '*.pythonhosted.org'
  // get-pip.py is served from bootstrap.pypa.io. Required by the Python
  // embeddable-distribution install path on the jumpbox (see issue #48 and
  // install.ps1) which downloads `get-pip.py` to bootstrap pip into
  // `C:\Python311` after extracting the embeddable zip.
  'bootstrap.pypa.io'
  '*.pypa.io'
  'registry.npmjs.org'
  '*.npmjs.org'
]
// Jumpbox ACME workflow egress (issue #53): scoped only to the jumpbox subnet
// and only when `extendFirewallForJumpboxBootstrap=true`.
// - api.github.com: reserved for ACME-client release discovery / plugin checks.
// - acme-v02.api.letsencrypt.org: Let's Encrypt ACME v2 directory endpoint
//   used during certificate issuance/renewal.
var _firewallJumpboxAcmeFqdns = [
  'api.github.com'
  'acme-v02.api.letsencrypt.org'
]
#disable-next-line no-hardcoded-env-urls
var _firewallEditorFqdns = [
  'update.code.visualstudio.com'
  '*.vo.msecnd.net'
  '*.vscode-cdn.net'
]

// Azure AI Speech FQDNs (#35) — only added to the bootstrap allow rule when
// `deploySpeechService` is true. Covers control plane, TTS, and STT regional
// endpoints used by the Speech SDK.
#disable-next-line no-hardcoded-env-urls
var _firewallSpeechFqdns = deploySpeechService ? [
  '*.cognitiveservices.azure.com'
  '*.tts.speech.microsoft.com'
  '*.stt.speech.microsoft.com'
] : []

// ACR Tasks agent-pool FQDNs — scoped to devopsBuildAgentsSubnetPrefix. Only
// populated when the agent pool is actually deployed.
//
// Note: ACR Tasks agents need egress to ACR data plane (`*.azurecr.io`,
// `*.data.azurecr.io`) AND to the Azure Storage queue/blob/table endpoints
// the ACR Tasks control plane uses to dispatch jobs to the agent VM.
// Without the *.core.windows.net FQDNs, builds queued via
// `az acr build --agent-pool` hang indefinitely in `Queued` state because
// the agent VM cannot reach the storage queue. See issue #18.
var _firewallAcrTaskFqdns = deployAcrTaskAgentPool ? [
  '*.azurecr.io'
  '*.data.azurecr.io'
  '*.blob.${environment().suffixes.storage}'
  '*.queue.${environment().suffixes.storage}'
  '*.table.${environment().suffixes.storage}'
] : []

// OS package repositories used by Debian/Ubuntu-based builder images during
// `apt-get` steps in ACR Tasks runs. Scoped to devopsBuildAgentsSubnetPrefix
// via `AllowAcrTaskOsPackages`. Includes packages.microsoft.com because
// Microsoft-supported Linux packages such as msodbcsql18 are common build-time
// dependencies for solution accelerators. Language registries (npm/PyPI/python.org)
// are reused from `_firewallDevRuntimeFqdns` via `AllowAcrTaskDevRuntimes`.
// See issues #20 and #68.
#disable-next-line no-hardcoded-env-urls
var _firewallAcrTaskOsPackageFqdns = [
  'deb.debian.org'
  'security.debian.org'
  'archive.ubuntu.com'
  'security.ubuntu.com'
  'dl.yarnpkg.com'
  'packages.microsoft.com'
]

// Pinned orchestrator frontend npm feeds (v5.2.1 lockfile) and their download
// redirect CDN. Keep separate from shared developer runtimes so only the
// build subnet inherits these destinations, via HTTPS-only AllowAcrTaskDevRuntimes.
var _firewallAcrTaskPackageFeedFqdns = [
  'ms-feed-2.pkgs.visualstudio.com'
  'ms-feed-12.pkgs.visualstudio.com'
  'ms-feed-17.pkgs.visualstudio.com'
  'ms-feed-25.pkgs.visualstudio.com'
  '*.vsblob.vsassets.io'
]

// Azure Firewall rejects ApplicationRules whose targetFqdns is an empty
// array with `BadRequest: "The request is invalid."` at the ARM
// request-validation layer (no rule-collection-group operation is even
// created). Build the full set of rules here, then filter out any whose
// targetFqdns ended up empty due to disabled feature flags (for example
// deployJumpbox=false or deployAcrTaskAgentPool=false). This keeps every rule
// definition co-located while ensuring the ARM payload only ever contains rules
// with at least one FQDN target.
var _firewallDefaultApplicationRules = filter([
  {
    ruleType: 'ApplicationRule'
    name: 'AllowMicrosoftContainerRegistry'
    protocols: [
      { protocolType: 'Https', port: 443 }
    ]
    targetFqdns: _firewallEssentialContainerFqdns
    sourceAddresses: ['*']
  }
  {
    ruleType: 'ApplicationRule'
    name: 'AllowEntraIdAuth'
    protocols: [
      { protocolType: 'Https', port: 443 }
    ]
    targetFqdns: _firewallEssentialAuthFqdns
    sourceAddresses: ['*']
  }
  {
    ruleType: 'ApplicationRule'
    name: 'AllowGitHub'
    protocols: [
      { protocolType: 'Https', port: 443 }
    ]
    targetFqdns: _firewallEssentialGitHubFqdns
    sourceAddresses: ['*']
  }
  {
    ruleType: 'ApplicationRule'
    name: 'AllowContainerAppsPlatform'
    protocols: [
      { protocolType: 'Https', port: 443 }
    ]
    targetFqdns: _firewallEssentialPlatformFqdns
    sourceAddresses: ['*']
  }
  {
    ruleType: 'ApplicationRule'
    name: 'AllowJumpboxBootstrap'
    protocols: [
      { protocolType: 'Https', port: 443 }
      { protocolType: 'Http', port: 80 }
    ]
    targetFqdns: extendFirewallForJumpboxBootstrap ? concat(_firewallVmBootstrapFqdns, _firewallSpeechFqdns) : []
    sourceAddresses: [jumpboxSubnetPrefix]
  }
  {
    ruleType: 'ApplicationRule'
    name: 'AllowJumpboxDevRuntimes'
    protocols: [
      { protocolType: 'Https', port: 443 }
    ]
    targetFqdns: extendFirewallForJumpboxBootstrap ? _firewallDevRuntimeFqdns : []
    sourceAddresses: [jumpboxSubnetPrefix]
  }
  {
    ruleType: 'ApplicationRule'
    name: 'AllowJumpboxEditors'
    protocols: [
      { protocolType: 'Https', port: 443 }
    ]
    targetFqdns: extendFirewallForJumpboxBootstrap ? _firewallEditorFqdns : []
    sourceAddresses: [jumpboxSubnetPrefix]
  }
  {
    ruleType: 'ApplicationRule'
    name: 'AllowJumpboxAcme'
    protocols: [
      { protocolType: 'Https', port: 443 }
    ]
    targetFqdns: extendFirewallForJumpboxBootstrap ? _firewallJumpboxAcmeFqdns : []
    sourceAddresses: [jumpboxSubnetPrefix]
  }
  {
    ruleType: 'ApplicationRule'
    name: 'AllowAcrTasks'
    protocols: [
      { protocolType: 'Https', port: 443 }
    ]
    targetFqdns: _firewallAcrTaskFqdns
    sourceAddresses: [devopsBuildAgentsSubnetPrefix]
  }
  {
    ruleType: 'ApplicationRule'
    name: 'AllowAcrTaskDevRuntimes'
    protocols: [
      { protocolType: 'Https', port: 443 }
    ]
    targetFqdns: (deployAcrTaskAgentPool && extendFirewallForAcrTaskBuilds) ? union(_firewallDevRuntimeFqdns, _firewallAcrTaskPackageFeedFqdns, additionalAcrTaskBuildFqdns) : []
    sourceAddresses: [devopsBuildAgentsSubnetPrefix]
  }
  {
    ruleType: 'ApplicationRule'
    name: 'AllowAcrTaskOsPackages'
    protocols: [
      { protocolType: 'Https', port: 443 }
      { protocolType: 'Http', port: 80 }
    ]
    targetFqdns: (deployAcrTaskAgentPool && extendFirewallForAcrTaskBuilds) ? _firewallAcrTaskOsPackageFqdns : []
    sourceAddresses: [devopsBuildAgentsSubnetPrefix]
  }
], rule => !empty(rule.targetFqdns))

var _firewallDefaultRuleCollections = [
  {
    ruleCollectionType: 'FirewallPolicyFilterRuleCollection'
    name: 'AllowEssentialOutbound'
    priority: 100
    action: {
      type: 'Allow'
    }
    rules: _firewallDefaultApplicationRules
  }
]

var _firewallAcsMediaRules = [
  {
    ruleType: 'NetworkRule'
    name: 'AllowAcsMediaUdp'
    ipProtocols: ['UDP']
    sourceAddresses: [
      jumpboxSubnetPrefix
      acaEnvironmentSubnetPrefix
      agentSubnetPrefix
    ]
    destinationAddresses: ['AzureCloud']
    destinationPorts: ['3478-3481']
  }
  {
    ruleType: 'NetworkRule'
    name: 'AllowAcsMediaTcp'
    ipProtocols: ['TCP']
    sourceAddresses: [
      jumpboxSubnetPrefix
      acaEnvironmentSubnetPrefix
      agentSubnetPrefix
    ]
    destinationAddresses: ['AzureCloud']
    destinationPorts: ['443', '3478-3481']
  }
]

var _firewallAcsMediaRuleCollections = [
  {
    ruleCollectionType: 'FirewallPolicyFilterRuleCollection'
    name: 'AllowAcsMedia'
    priority: 100
    action: {
      type: 'Allow'
    }
    rules: _firewallAcsMediaRules
  }
]

// ACR Task agent pool platform-bootstrap network rules (fixes Azure/GPT-RAG#597
// Defect C). These are required for the agent pool itself to provision and
// scale inside the VNet — independent of what a queued build later needs
// (see the AllowAcrTasks / AllowAcrTaskDevRuntimes / AllowAcrTaskOsPackages
// ApplicationRules above, which only cover build-time egress). Per Microsoft
// Learn "Run an Azure Container Registry task on a dedicated agent pool >
// Create pool in a virtual network > Add firewall rules", the pool's own
// platform bootstrap requires outbound TCP 443 (plus 12000 for Azure Monitor
// diagnostics) to five service tags: AzureKeyVault, Storage, EventHub,
// AzureActiveDirectory, AzureMonitor.
// https://learn.microsoft.com/azure/container-registry/tasks-agent-pools#add-firewall-rules
//
// These are IP/service-tag-based control-plane calls, not FQDN-addressable
// HTTP(S) application traffic, so Azure Firewall ApplicationRules (which only
// inspect HTTP(S) FQDNs) cannot express them — they require NetworkRules
// with `destinationAddresses` set to service tags. Without this collection,
// the agent pool's platform bootstrap traffic is silently dropped by the
// firewall's default-deny and the VNet-injected pool never reaches
// Succeeded, while the same pool without VNet injection (no route through
// this firewall) provisions immediately.
var _firewallAcrTaskAgentPoolNetworkRules = [
  {
    ruleType: 'NetworkRule'
    name: 'AllowAcrTaskAgentPoolKeyVault'
    ipProtocols: ['TCP']
    sourceAddresses: [devopsBuildAgentsSubnetPrefix]
    destinationAddresses: ['AzureKeyVault']
    destinationPorts: ['443']
  }
  {
    ruleType: 'NetworkRule'
    name: 'AllowAcrTaskAgentPoolStorage'
    ipProtocols: ['TCP']
    sourceAddresses: [devopsBuildAgentsSubnetPrefix]
    destinationAddresses: ['Storage']
    destinationPorts: ['443']
  }
  {
    ruleType: 'NetworkRule'
    name: 'AllowAcrTaskAgentPoolEventHub'
    ipProtocols: ['TCP']
    sourceAddresses: [devopsBuildAgentsSubnetPrefix]
    destinationAddresses: ['EventHub']
    destinationPorts: ['443']
  }
  {
    ruleType: 'NetworkRule'
    name: 'AllowAcrTaskAgentPoolAzureAD'
    ipProtocols: ['TCP']
    sourceAddresses: [devopsBuildAgentsSubnetPrefix]
    destinationAddresses: ['AzureActiveDirectory']
    destinationPorts: ['443']
  }
  {
    ruleType: 'NetworkRule'
    name: 'AllowAcrTaskAgentPoolMonitor'
    ipProtocols: ['TCP']
    sourceAddresses: [devopsBuildAgentsSubnetPrefix]
    destinationAddresses: ['AzureMonitor']
    destinationPorts: ['443', '12000']
  }
]

var _firewallAcrTaskAgentPoolRuleCollections = [
  {
    ruleCollectionType: 'FirewallPolicyFilterRuleCollection'
    name: 'AllowAcrTaskAgentPoolPlatform'
    priority: 100
    action: {
      type: 'Allow'
    }
    rules: _firewallAcrTaskAgentPoolNetworkRules
  }
]

// Azure Firewall for egress traffic control
///////////////////////////////////////////////////////////////////////////

resource firewallPublicIp 'Microsoft.Network/publicIPAddresses@2024-07-01' = if (deployAzureFirewall && networkIsolation) {
  name: '${const.abbrs.networking.publicIPAddress}${const.abbrs.networking.firewall}${resourceToken}'
  location: location
  sku: {
    name: 'Standard'
    tier: 'Regional'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
  }
  tags: tags
}

resource firewallPolicy 'Microsoft.Network/firewallPolicies@2024-07-01' = if (deployAzureFirewall && networkIsolation) {
  name: '${const.abbrs.networking.firewallPolicy}${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: {
      tier: 'Standard'
    }
    threatIntelMode: 'Alert'
    dnsSettings: {
      enableProxy: enableFirewallDnsProxy
    }
  }
}

resource firewallPolicyDefaultRuleCollectionGroup 'Microsoft.Network/firewallPolicies/ruleCollectionGroups@2024-07-01' = if (deployAzureFirewall && networkIsolation) {
  parent: firewallPolicy
  name: 'DefaultRuleCollectionGroup'
  properties: {
    priority: 200
    ruleCollections: _firewallDefaultRuleCollections
  }
}

// ACS Media (WebRTC / TURN) — opt-in network rule collection.
// Required for Speech real-time avatar, ACS Calling, Teams Media. The signaling
// path is HTTPS (already covered by application rules); the *media* path uses
// UDP 3478-3481 / TCP 443+3478-3481 to the ACS / Speech avatar TURN fleet,
// which is otherwise dropped by the firewall under network isolation.
// Note: the destination is the `AzureCloud` service tag, not a hypothetical
// `AzureCommunicationServices` tag — the latter does not exist in the Azure
// service-tag namespace, and the actual TURN backends (e.g.
// `relay.communication.microsoft.com`,
// `a-tr-skysc-*.<region>.cloudapp.azure.com`) resolve into IP ranges covered
// by `AzureCloud` / `AzureCloud.<region>`. See issue #50.
// Separate rule collection group so it can be toggled independently of the
// default group, and so the default group's priority doesn't have to shift.
resource firewallPolicyAcsMediaRuleCollectionGroup 'Microsoft.Network/firewallPolicies/ruleCollectionGroups@2024-07-01' = if (deployAzureFirewall && networkIsolation && enableAcsMediaEgress) {
  parent: firewallPolicy
  name: 'AcsMediaRuleCollectionGroup'
  properties: {
    priority: 300
    ruleCollections: _firewallAcsMediaRuleCollections
  }
  dependsOn: [
    firewallPolicyDefaultRuleCollectionGroup
  ]
}

// ACR Task agent pool platform-bootstrap network rules — separate rule
// collection group (mirrors the AcsMedia pattern) so it toggles independently
// via `deployAcrTaskAgentPool` without shifting the default group's priority.
// Chained after both prior groups: concurrent PUTs against sibling
// ruleCollectionGroups under the same firewallPolicy can 409
// (AnotherOperationInProgress), so every group in this module is serialized.
// The AcsMedia dependency is unconditional here by design — Azure Resource
// Manager automatically drops an explicit dependsOn entry at deployment time
// when the referenced resource's own `if` condition evaluates to false (see
// https://learn.microsoft.com/azure/azure-resource-manager/bicep/conditional-resource-deployment#new-or-existing-resource),
// so no ternary/null-guard is needed even when `enableAcsMediaEgress` is false.
//
// Explicit `azureFirewall` dependency: on a fresh/cold deployment, without
// this, ARM has no ordering constraint between the ruleCollectionGroup chain
// and the azureFirewall resource itself (both only depend on firewallPolicy),
// so the chain can race the firewall's own ~10-25 minute provisioning. Live
// validation of this fix (disposable eastus2 deployment, Azure/GPT-RAG#597)
// observed exactly this: this group's PUT was rejected with
// `FirewallPolicyUpdateFailed` / "1 faulted referenced firewalls" because the
// azureFirewall resource hadn't finished associating yet, even though the
// chained DefaultRuleCollectionGroup PUT ahead of it happened to complete in
// time. Depending directly on azureFirewall guarantees this group's rules are
// only applied once the firewall itself is fully provisioned, so the pool's
// platform-bootstrap traffic is reliably unblocked on the very first
// deployment attempt.
resource firewallPolicyAcrTaskAgentPoolRuleCollectionGroup 'Microsoft.Network/firewallPolicies/ruleCollectionGroups@2024-07-01' = if (deployAzureFirewall && networkIsolation && deployAcrTaskAgentPool) {
  parent: firewallPolicy
  name: 'AcrTaskAgentPoolRuleCollectionGroup'
  properties: {
    priority: 250
    ruleCollections: _firewallAcrTaskAgentPoolRuleCollections
  }
  dependsOn: [
    firewallPolicyDefaultRuleCollectionGroup
    firewallPolicyAcsMediaRuleCollectionGroup
    azureFirewall
  ]
}

#disable-next-line BCP318
var _firewallSubnetId = networkIsolation ? '${virtualNetworkResourceId}/subnets/${azureFirewallSubnetName}' : ''

resource azureFirewall 'Microsoft.Network/azureFirewalls@2024-07-01' = if (deployAzureFirewall && networkIsolation) {
  name: '${const.abbrs.networking.firewall}${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'AZFW_VNet'
      tier: 'Standard'
    }
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          publicIPAddress: {
            id: firewallPublicIp.id
          }
          subnet: {
            id: _firewallSubnetId
          }
        }
      }
    ]
    firewallPolicy: {
      id: firewallPolicy.id
    }
  }
}

// Azure Firewall diagnostics to Log Analytics
resource firewallDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (deployAzureFirewall && networkIsolation && hasEffectiveLaw) {
  name: 'fw-diagnostics'
  scope: azureFirewall
  properties: {
    workspaceId: lawResourceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

#disable-next-line BCP318
output privateIp string = (deployAzureFirewall && networkIsolation) ? azureFirewall!.properties.ipConfigurations[0].properties.privateIPAddress : ''
