// ============================================================================
// AI Landing Zone Bicep Deployment Template
// This infrastructure-as-code template follows best practices for modular,
// reusable, and configuration-aware deployments. Key principles:
//
// - **AZD Integration**: This template is optimized for use with the Azure Developer CLI (`azd`).
//   Use `azd provision` to deploy infrastructure and `azd deploy` to deploy your application.
//   It supports automated, repeatable, and configuration-aware workflows. The `main.json` file
//   can include placeholders (e.g., `${AZURE_LOCATION}`, `${AZURE_PRINCIPAL_ID}`) that are automatically
//   injected by `azd` during execution, enabling seamless parameter resolution.
//
// - **Parameterization**: All configuration values are defined in `main.json`.
//   You can create multiple parameter files to support different deployment configurations,
//   such as variations in scale, resource combinations, or cost constraints.
//
// - **Feature Flags**: Resource provisioning is modular and controlled via feature flags
//   (e.g., `deployAppConfig`). This enables selective deployment of components based on project needs.
//
// - **Azure Verified Modules (AVM)**: Official AVM modules are used as the foundation
//   for resource deployment, ensuring consistency, maintainability, and alignment with Microsoft standards.
//   Reference: https://azure.github.io/Azure-Verified-Modules/indexes/bicep/bicep-resource-modules/
//   When AVM does not cover a specific resource, custom Bicep module is used as fallback.
//
// - **Output Exposure**: Key outputs such as connection strings, endpoints, and resource IDs
//   are exposed as Bicep outputs and can be consumed by downstream processes or deployment scripts.
//
// - **Post-Provisioning Automation**: Supports optional post-provisioning scripts to perform data plane
//   operations or additional configurations. These scripts can run independently or as `azd` hooks,
//   enabling fine-grained control and custom automation after infrastructure deployment.
//
// ============================================================================

targetScope = 'resourceGroup'

//////////////////////////////////////////////////////////////////////////
// PARAMETERS
//////////////////////////////////////////////////////////////////////////

// Important notes about parameters:
// 1) Before running azd provision, set parameter values using main.parameters.json or 
// the command line: azd env set ENV_VARIABLE_NAME value, for parameters configured to allow substitution.
//
// 2) You can identify these substitutable parameters in main.parameters.json by this format:
// "parameterName": { "value": "${ENV_VARIABLE_NAME}" }.
// This allows the convenience of setting values via the command line (e.g., azd env set ENV_VARIABLE_NAME true).
//
// 3) Substitutable parameters: if an environment variable isn’t set before running `azd provision`, its value will be empty.
// To prevent this, each parameter that uses the substitution mechanism has a corresponding Bicep variable (`_parameterName`) with a default value.
// When adding new substitutable parameters in this Bicep file or in `main.parameters.bicep`, follow the same pattern.

// ---------------------------------------------------------------------
// Imports
// ----------------------------------------------------------------------
import * as const from 'constants/constants.bicep'
import * as storageTypes from 'constants/storage-types.bicep'

// ----------------------------------------------------------------------
// General Parameters
// ----------------------------------------------------------------------

@description('Name of the Azure Developer CLI environment')
param environmentName string

@description('Application destination in the workload subscription. Empty uses the Foundry/root resource group. Intended for new environments only.')
param applicationResourceGroupName string = ''

@description('Locally owned networking destination in the workload subscription. Empty uses the Foundry/root resource group. Explicit BYO resource IDs retain precedence.')
param networkResourceGroupName string = ''

@description('The Azure region where your resources will be created.')
param location string = resourceGroup().location

@description('The Azure region where Cosmos DB will be created. Defaults to the resource group location.')
param cosmosLocation string = resourceGroup().location

@description('The Azure region where Azure AI Search services will be created. Defaults to the main deployment location. Override this when the primary region is out of capacity for AI Search.')
param searchServiceLocation string = ''

@description('The Azure region where the Azure AI Speech service will be created. Defaults to the main deployment location.')
param speechServiceLocation string = ''

@description('Principal ID for role assignments. This is typically the Object ID of the user or service principal running the deployment.')
param principalId string

@description('Principal type for role assignments. This can be "User", "ServicePrincipal", or "Group".')
param principalType string = 'User'

@description('Tags to apply to all resources in the deployment')
param deploymentTags object = {}

@description('Label used for App Configuration key-value pairs.')
param appConfigLabel string = 'ai-lz'

@description('Optional. Accelerator-specific App Configuration key-values appended verbatim to the App Configuration store. This lets a consuming accelerator publish its own settings without the landing zone needing to know about them. Values are stored as plaintext in App Configuration, so never pass secrets here (use Key Vault references instead). Each entry must have a unique name+label. On a name+label collision with a workload configuration key the landing zone already emits, the passthrough entry wins. Do not redefine reserved infrastructure keys emitted by other modules (the Cosmos identifiers COSMOS_DB_ACCOUNT_RESOURCE_ID and COSMOS_DB_ENDPOINT, and the per-app <APP>_APIKEY Key Vault references); reusing those names would create a duplicate key-value and fail the deployment. Note: this is only applied on non network-isolated deployments, where the landing zone writes App Configuration at deploy time. Network-isolated deployments configure App Configuration from the accelerator post-provision step, so pass these values through that path instead.')
param additionalAppConfigurationSettings additionalAppConfigurationSettingType[] = []

@description('Enable network isolation for the deployment. This will restrict public access to resources and require private endpoints where applicable.')
param networkIsolation bool = false

@description('Gap 8 — Deployment topology preset. Required to surface deployment intent explicitly. Allowed values: `standalone` (default — self-contained spoke, own firewall/bastion/NAT GW; suitable for sandbox or single-team subscriptions) or `ailz-integrated` (spoke designed to plug into an Azure Landing Zone-managed hub; consumer is expected to provide `hubIntegrationHubVnetResourceId`, `hubIntegrationEgressNextHopIp` and/or `hubIntegrationExistingRouteTableResourceId`, BYO Private DNS overrides, and optionally `existingLogAnalyticsWorkspaceResourceId` for centralized observability). The value is captured as a `deploymentMode` tag on the resource group so platform teams can audit deployment posture. The preset does NOT automatically override explicit operator flags; it primarily documents intent and powers the pre-flight script (`scripts/Invoke-PreflightChecks.ps1`, Gap 9).')
@allowed([
  'standalone'
  'ailz-integrated'
])
param deploymentMode string = 'standalone'

@description('Optional. When non-empty, opens each services public surface restricted to these CIDRs via native `ipRules` / `networkAcls.ipRules`. Empty (default) means no public allow-list. Applied to Storage, Key Vault, Cosmos DB, AI Search, Container Registry, and the AI Foundry / Cognitive Services accounts. App Configuration and Application Insights do not expose native ipRules and ignore this parameter (documented in docs/v2-migration.md). When `networkIsolation=true` AND `allowedIpRanges` is non-empty, services are switched to `publicNetworkAccess=Enabled` so the IP rules can take effect (defense-in-depth alongside private endpoints).')
param allowedIpRanges string[] = []

@description('''When set to true, Private DNS Zones and DNS zone groups will NOT be created by this module.
Use this option in environments where Azure Policy automatically manages Private DNS Zone linking for private endpoints
(e.g., CAF Enterprise-Scale Platform Landing Zone). Creating DNS zones in those environments causes conflicts with
policy-driven DNS management and results in deployment failures.
When false (default), the module creates and manages all Private DNS Zones and links them to the VNet.
Requires networkIsolation to be true to have any effect.''')
param policyManagedPrivateDns bool = false

// ----------------------------------------------------------------------
// Gap 2 — BYO Private DNS Zones (granular per-namespace overrides)
// ----------------------------------------------------------------------
// For each Private DNS zone the landing zone normally creates, an
// `existingPrivateDnsZone<Namespace>ResourceId` param accepts a full
// resource ID. When provided:
//   * The zone is NOT created by this deployment.
//   * The zone is NOT linked from the spoke VNet (assumed pre-linked via
//     the hub or another mechanism; cross-RG linking is an operator task
//     in v2.0.0 — see docs/v2-migration.md).
//   * The provided resource ID is used directly in every Private
//     Endpoint DNS Zone Group that consumes the zone, so PE→FQDN
//     resolution still works against the shared zone.
// `policyManagedPrivateDns=true` continues to win — when it is set,
// neither creation nor linking happens for any zone regardless of these
// BYO params (the pre-flight script flags this as a misconfiguration).

@description('Gap 2 — Resource ID of an existing `privatelink.cognitiveservices.azure.com` Private DNS Zone to reuse (Azure AI Foundry / Cognitive Services PE DNS). When set, the local zone is not created. Pre-link the zone to the spoke VNet (or rely on hub→spoke peering + hub-side link) — automatic spoke linking is not performed.')
param existingPrivateDnsZoneCogSvcsResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.openai.azure.com` Private DNS Zone to reuse (Azure OpenAI PE DNS).')
param existingPrivateDnsZoneOpenAiResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.services.ai.azure.com` Private DNS Zone to reuse (AI Services / Foundry PE DNS).')
param existingPrivateDnsZoneAiServicesResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.search.windows.net` Private DNS Zone to reuse (Azure AI Search PE DNS).')
param existingPrivateDnsZoneSearchResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.documents.azure.com` Private DNS Zone to reuse (Azure Cosmos DB PE DNS).')
param existingPrivateDnsZoneCosmosResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.blob.<storage suffix>` Private DNS Zone to reuse (Azure Storage Blob PE DNS).')
param existingPrivateDnsZoneBlobResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.vaultcore.azure.net` Private DNS Zone to reuse (Azure Key Vault PE DNS).')
param existingPrivateDnsZoneKeyVaultResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.azconfig.io` Private DNS Zone to reuse (Azure App Configuration PE DNS).')
param existingPrivateDnsZoneAppConfigResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.<region>.azurecontainerapps.io` Private DNS Zone to reuse (Azure Container Apps PE DNS). Region-specific zone — must match the deployment region.')
param existingPrivateDnsZoneContainerAppsResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.azurecr.io` Private DNS Zone to reuse (Azure Container Registry PE DNS).')
param existingPrivateDnsZoneAcrResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.monitor.azure.com` Private DNS Zone to reuse (Azure Monitor Private Link Scope PE DNS).')
param existingPrivateDnsZoneAzureMonitorResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.oms.opinsights.azure.com` Private DNS Zone to reuse (OMS Log Analytics PE DNS).')
param existingPrivateDnsZoneOmsOpsInsightsResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.ods.opinsights.azure.com` Private DNS Zone to reuse (ODS Log Analytics ingestion PE DNS).')
param existingPrivateDnsZoneOdsOpsInsightsResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.agentsvc.azure.automation.net` Private DNS Zone to reuse (Azure Monitor agent service PE DNS).')
param existingPrivateDnsZoneAzureAutomationResourceId string?

@description('Gap 2 — Resource ID of an existing `privatelink.applicationinsights.io` Private DNS Zone to reuse. Only consumed when `enablePrivateLogAnalytics=true` and AMPLS is created locally; otherwise this BYO ID is ignored.')
param existingPrivateDnsZoneAppInsightsResourceId string?

@description('The Azure region where private endpoints will be created. Defaults to the main deployment location. Use this when your VNet is in a different region than the resources.')
param privateEndpointLocation string = ''

@description('Private endpoint RG override in the workload subscription. When empty, use the existing VNet subscription/RG if sideBySideDeploy is disabled, otherwise the resolved network RG.')
param privateEndpointResourceGroupName string = ''

@description('Use an existing Virtual Network. When false, a new VNet will be created.')
param useExistingVNet bool = false

@description('The full ARM resource ID of an existing Virtual Network. Format: /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/virtualNetworks/{vnetName}. Leave empty to create a new VNet.')
param existingVnetResourceId string = ''

param agentSubnetName string = 'agent-subnet'
param peSubnetName string = 'pe-subnet'

@description('Dedicated application private endpoint subnet. Creation ownership is independent of its consumers; there is no shared Foundry subnet fallback.')
param applicationPeSubnetName string = 'application-pe-subnet'

@description('IPv4 CIDR for the application PE subnet. Must be non-overlapping inside the workload VNet. No delegation is applied.')
param applicationPeSubnetPrefix string = '192.168.3.128/26'
param gatewaySubnetName string = 'GatewaySubnet'
param azureBastionSubnetName string = 'AzureBastionSubnet'
param azureFirewallSubnetName string = 'AzureFirewallSubnet'
param azureAppGatewaySubnetName string = 'AppGatewaySubnet'
param jumpboxSubnetName string = 'jumpbox-subnet'
param acaEnvironmentSubnetName string = 'aca-environment-subnet'
param devopsBuildAgentsSubnetName string = 'devops-build-agents-subnet'
param powerPlatformSubnetName string = 'powerplatform-subnet'
param aiGatewaySubnetName string = 'ai-gateway-subnet'

@description('Power Platform capacity default, configurable for environment demand. Delegation does not associate an environment.')
param powerPlatformSubnetPrefix string = '192.168.4.0/24'

@description('APIM Standard v2/Premium v2 outbound integration subnet, /27 or larger. Does not deploy APIM or private endpoints.')
param aiGatewaySubnetPrefix string = '192.168.5.0/24'

// Creation ownership only: effective creation also requires networkIsolation and deploySubnets.
@description('Create/manage the Agent Service subnet; does not control Foundry association.')
param deployAgentSubnet bool = true
@description('Create/manage the Foundry and grounding private endpoint subnet.')
param deployPeSubnet bool = true
@description('Create/manage the dedicated application private endpoint subnet.')
param deployApplicationPeSubnet bool = true
@description('Create/manage AzureBastionSubnet without deploying Bastion.')
param deployAzureBastionSubnet bool = true
@description('Create/manage AzureFirewallSubnet without deploying a firewall.')
param deployAzureFirewallSubnet bool = true
@description('Create/manage GatewaySubnet without deploying a VPN/ExpressRoute gateway.')
param deployGatewaySubnet bool = true
@description('Create/manage the Application Gateway subnet without deploying a gateway.')
param deployAppGatewaySubnet bool = true
@description('Create/manage the jumpbox subnet without deploying a VM.')
param deployJumpboxSubnet bool = true
@description('Create/manage the Container Apps environment subnet.')
param deployAcaEnvironmentSubnet bool = true
@description('Create/manage the build-agent subnet without deploying build agents.')
param deployDevopsBuildAgentsSubnet bool = true
@description('Create/manage the Power Platform delegated subnet only.')
param deployPowerPlatformSubnet bool = true
@description('Create/manage the AI Gateway delegated integration subnet only; requires deployNsgs.')
param deployAiGatewaySubnet bool = true

@description('Address prefixes for the virtual network.')
param vnetAddressPrefixes array = [
  '192.168.0.0/21' // 192.168.0.0 – 192.168.7.255 (2048 IPs total)
]

@description('Gap 3 — Optional suffix appended to every Private DNS zone VNet link name created by this deployment. Set to a unique value (e.g., the spoke name or environment short-code) when multiple spokes link to the same shared Private DNS zone — without a unique suffix the link name collides and the second deployment fails. Leave empty for single-spoke or non-shared-zone deployments. Final link name: `<vnetName>-<zone-shortcode>-link<suffix>[<-byon if useExistingVNet>]`. Forbidden characters per Microsoft.Network/privateDnsZones/virtualNetworkLinks: must be 1–80 chars, alphanumeric / hyphens / underscores only.')
param dnsZoneLinkSuffix string = ''

//
// Subnet allocations (non-overlapping, optimized for production workloads)
// PE subnet increased to /26 to support multiple Private Endpoints without race conditions
//

@description('AI Foundry Agents subnet — Recommended /24 (256 IPs)')
param agentSubnetPrefix string = '192.168.0.0/24' // 192.168.0.0–192.168.0.255

@description('Azure Container Apps Environment subnet — /24 (256 IPs)') // Recommended minimum is /23
param acaEnvironmentSubnetPrefix string = '192.168.1.0/24' // 192.168.1.0–192.168.1.255

@description('Private Endpoints subnet — /26 (64 IPs) — Increased to prevent race conditions during parallel PE creation')
param peSubnetPrefix string = '192.168.2.0/26' // 192.168.2.0–192.168.2.63

@description('Azure Bastion subnet — Required /26 (64 IPs, CIDR-aligned)')
param azureBastionSubnetPrefix string = '192.168.2.64/26' // 192.168.2.64–192.168.2.127

@description('Azure Firewall subnet — /26 (64 IPs, CIDR-aligned)')
param azureFirewallSubnetPrefix string = '192.168.2.128/26' // 192.168.2.128–192.168.2.191

@description('Gateway subnet — Required /26 (64 IPs, CIDR-aligned)')
param gatewaySubnetPrefix string = '192.168.2.192/26' // 192.168.2.192–192.168.2.255

@description('Application Gateway subnet — /27 (32 IPs)')
param azureAppGatewaySubnetPrefix string = '192.168.3.0/27' // 192.168.3.0–192.168.3.31

@description('Jumpbox subnet — /27 (32 IPs)')
param jumpboxSubnetPrefix string = '192.168.3.64/27' // 192.168.3.64–192.168.3.95

@description('DevOps Build Agents subnet — /27 (32 IPs)')
param devopsBuildAgentsSubnetPrefix string = '192.168.3.96/27' // 192.168.3.96–192.168.3.127

// ----------------------------------------------------------------------
// Feature-flagging Params (as booleans with a default of true)
// ----------------------------------------------------------------------

// @description('If false, skips creating platform infrastructure such as Firewall, Jumpbox, Bastion, etc.')
// param greenFieldDeployment bool = true

@description('Whether to deploy Bing-powered grounding capabilities alongside your AI services.')
param deployGroundingWithBing bool = true

@description('Deploy Azure AI Foundry for building and managing AI models.')
param deployAiFoundry bool = true

@description('Associate Azure AI Foundry Agent Service with agentSubnetName. Subnet creation is independently controlled by deployAgentSubnet.')
param deployAiFoundrySubnet bool = true

@description('Deploy Azure App Configuration for centralized feature-flag and configuration management.')
param deployAppConfig bool = true

@description('How the landing zone should provide runtime configuration to the external Container Apps. ``appConfig`` (default) preserves the existing behavior: an Azure App Configuration store is populated with deployment outputs and each Container App receives an ``APP_CONFIG_ENDPOINT`` env var plus the ``App Configuration Data Reader`` RBAC. ``containerEnv`` skips the App Configuration population and instead injects a small set of bootstrap env vars (tenant, subscription, resource group, location, resource token, network/identity flags, plus the names of the deployed resources) directly on every Container App so consumers can resolve endpoints via SDK without going through App Configuration. ``none`` deploys the Container App shells with only the identity bootstrap env vars (``AZURE_TENANT_ID`` and ``AZURE_CLIENT_ID`` when applicable); callers are expected to supply runtime configuration through their own mechanism. Secrets are always sourced from secure parameters or Key Vault references regardless of mode. Set ``deployAppConfig=false`` to skip the store entirely when the mode is ``containerEnv`` or ``none``.')
@allowed([
  'appConfig'
  'containerEnv'
  'none'
])
param appRuntimeConfigurationMode string = 'appConfig'

@description('Deploy an Azure Key Vault to securely store secrets, keys, and certificates.')
param deployKeyVault bool = true

@description('Deploy an Azure Key Vault to securely store VM secrets, keys, and certificates.')
param deployVmKeyVault bool = false

@description('Deploy an Azure Log Analytics workspace for centralized log collection and query.')
param deployLogAnalytics bool = true

@description('Resource ID of an existing Log Analytics workspace to reuse instead of creating one (Gap 5). When non-empty, no LAW is created in this deployment and all diagnostic settings, AMPLS linkage, and App Configuration entries point at this central workspace. Cross-RG and cross-subscription IDs are supported.')
param existingLogAnalyticsWorkspaceResourceId string?

@description('When network isolation is enabled, also deploy an Azure Monitor Private Link Scope (AMPLS) with private endpoints and the related monitor/opinsights/automation private DNS zones to keep Log Analytics + Application Insights traffic on the private network. Disable to opt-out and avoid sharing those Azure Monitor private DNS zones with other workloads (preventing cross-workload DNS conflicts). Has no effect when networkIsolation is false or when an `existingLogAnalyticsWorkspaceResourceId` is provided (the central workspace is assumed to be private-linked centrally).')
param enablePrivateLogAnalytics bool = true

@description('Deploy Azure Application Insights for application performance monitoring and diagnostics.')
param deployAppInsights bool = true

@description('Resource ID of an existing Application Insights component to reuse instead of creating one (Gap 5). Pair with `existingApplicationInsightsConnectionString` so downstream consumers (Container Apps Environment, App Configuration) receive a working connection string without requiring same-RG access to the existing component. Cross-RG/cross-subscription IDs are supported.')
param existingApplicationInsightsResourceId string?

@description('Connection string for the existing Application Insights component referenced by `existingApplicationInsightsResourceId`. Required when reusing AppInsights so the Container Apps Environment and the `APPLICATIONINSIGHTS_CONNECTION_STRING` App Configuration entry are correctly populated. Operators retrieve this from `az monitor app-insights component show -g <rg> -a <name> --query connectionString -o tsv`.')
@secure()
param existingApplicationInsightsConnectionString string?

@description('When `existingApplicationInsightsResourceId` is provided WITHOUT a matching `existingLogAnalyticsWorkspaceResourceId`, the deployment normally fails the pre-flight check (Gap 5 §4.13) because telemetry would split between the central AppInsights workspace and this deployment\'s own LAW. Set to `true` only if the split is intentional and accepted.')
param allowMixedObservabilityWorkspaces bool = false

@description('Gap 6 — IP address of an external network virtual appliance (typically the hub Azure Firewall private IP) that should receive the spoke 0.0.0.0/0 default route when no spoke-local firewall is deployed. Effective only when `deployAzureFirewall=false`, `networkIsolation=true`, and no `hubIntegrationExistingRouteTableResourceId` is provided. Use this in AI-LZ-integrated topologies where the hub provides centralized egress filtering.')
param hubIntegrationEgressNextHopIp string?

@description('Gap 6 — Resource ID of an existing Route Table to attach the spoke workload subnets to. When set, the deployment skips creation of its local route table and reuses this RT (assumed pre-configured with the correct default route). Required for Landing Zone-managed topologies where the platform team owns the spoke RT. Mutually exclusive with `hubIntegrationEgressNextHopIp` (which builds a local RT). When set, both `deployAzureFirewall` and any local default-route creation are suppressed.')
param hubIntegrationExistingRouteTableResourceId string?

@description('Gap 7 — Resource ID of the hub Virtual Network the spoke should peer with. When set and `hubIntegrationCreateHubPeering=true`, the deployment creates a spoke→hub VNet peering. The reverse (hub→spoke) peering is the operator\'s responsibility — typically handled by a platform team script (`tests/scripts/Add-HubSpokePeering.ps1` for our test harness). Hub VNet may live in a different subscription/RG; the peering resource itself lives in the spoke VNet so the spoke deployment has the rights to create it.')
param hubIntegrationHubVnetResourceId string?

@description('Gap 7 — When true and `hubIntegrationHubVnetResourceId` is set, the deployment creates the spoke→hub peering inline. Set to `false` to defer peering creation entirely to the platform team (both directions handled externally). Only effective when the spoke VNet is created by this deployment (`useExistingVNet=false`); with BYO VNet, peering management is the operator\'s responsibility.')
param hubIntegrationCreateHubPeering bool = true

@description('Gap 7 — `allowGatewayTransit` flag on the spoke→hub peering. Set to `true` when the spoke owns a VPN/ExpressRoute gateway that the hub should be allowed to use as transit. Defaults to `false` (hub-owned gateway is the standard topology).')
param hubIntegrationPeeringAllowGatewayTransit bool = false

@description('Gap 7 — `useRemoteGateways` flag on the spoke→hub peering. Set to `true` to route on-premises traffic from the spoke through the hub-owned VPN/ExpressRoute gateway. Requires the reverse hub→spoke peering to have `allowGatewayTransit=true` and a gateway provisioned in the hub. Defaults to `false` for the standalone topology.')
param hubIntegrationPeeringUseRemoteGateways bool = false

@description('Deploy an Azure Cognitive Search service for indexing and querying content. When disabled, search-related connections are skipped and search app configuration values resolve to empty values.')
param deploySearchService bool = true

@description('Deploy an Azure AI Speech (SpeechServices) cognitive account with the same private-endpoint / DNS / RBAC posture as the rest of the AI services in this landing zone. Off by default so the change is non-breaking for existing consumers. When enabled under network isolation, the account is created with publicNetworkAccess=Disabled and a private endpoint into the existing privatelink.cognitiveservices.azure.com zone.')
param deploySpeechService bool = false

@description('SKU for the Azure AI Speech service. Only F0 (free) and S0 (standard) are supported via SDK.')
@allowed([
  'F0'
  'S0'
])
param speechServiceSku string = 'S0'

@description('Deploy an Azure Storage Account to hold blobs, queues, tables, and files.')
param deployStorageAccount bool = true

@description('Network ACL bypass for the solution Storage account only. AzureServices preserves existing behavior; None removes trusted-service bypass without changing public network access or IP rules.')
param storageAccountNetworkAclsBypass storageTypes.storageAccountNetworkAclsBypassType = 'AzureServices'

@description('Complete desired resource-instance network access rules for the solution Storage account. Empty means no resource-instance exceptions. Supply only approved resource IDs and tenant IDs; no live rules are imported and no Defender scanner, plan, or role is created.')
param storageAccountResourceAccessRules storageTypes.storageAccountResourceAccessRuleType[] = []

@description('Allow Shared Key authorization for the solution Storage account. Defaults to true for compatibility. Set false only after migrating affected key-based clients and SAS tokens; this does not remove the pinned AVM management-plane key-listing outputs.')
param storageAccountAllowSharedKeyAccess bool = true

@description('Deploy an Azure Cosmos DB account for globally distributed NoSQL data storage.')
param deployCosmosDb bool = true

@description('Deploy Azure Container Apps for running your microservices in a serverless Kubernetes environment.')
param deployContainerApps bool = true

@description('Deploy an Azure Container Registry to store and manage Docker container images.')
param deployContainerRegistry bool = true

@description('Deploy the Container Apps environment (log ingestion, VNet integration, etc.).')
param deployContainerEnv bool = true

// ---------------------------------------------------------------------------
// Hub-component deployment flags (Gap 4, issue #58)
// ---------------------------------------------------------------------------
// `deployVM` (v1.x) consolidated three independent deployments — jumpbox,
// Bastion, and NAT Gateway — under one switch. v2.0.0 splits them so each
// component can be controlled, reused (BYO) or skipped independently.
//
// Defaults are nullable. When null, the effective value is derived to match
// v1.x behavior (everything deploys when `networkIsolation=true`). Set any
// flag explicitly to override.
//
//   deployJumpbox      | jumpbox VM + CSE + RBAC + (optionally) VM Key Vault
//   deployBastion      | spoke-side Azure Bastion + Bastion NSG + Bastion PIP
//   deployNatGateway   | spoke NAT Gateway + NAT PIP for outbound egress
//
// Each component also accepts a matching `existing<Component>ResourceId` BYO
// parameter. When the BYO ID is non-empty, the corresponding `deploy*` flag
// defaults to `false` and the existing resource ID is consumed by downstream
// wiring (RBAC, diagnostics, runbook docs).
//
@description('Deploy the jumpbox Virtual Machine (and its CSE + RBAC + optional VM Key Vault). When null, defaults to `networkIsolation` to match v1.x behavior. Set to `false` for AI LZ-integrated topologies where the operator connects via central tooling.')
param deployJumpbox bool?

@description('Deploy a spoke-side Azure Bastion + Bastion NSG + Bastion PIP. When null, defaults to `networkIsolation && deployJumpbox` (preserves v1.x behavior). Set to `false` when reusing a central hub Bastion via VNet peering (Gap 7).')
param deployBastion bool?

@description('Deploy a NAT Gateway + NAT PIP for outbound spoke egress. When null, defaults to `networkIsolation && deployJumpbox` (preserves v1.x behavior). Set to `false` when egress is centralized via Azure Firewall in the hub (Gap 6).')
param deployNatGateway bool?

@description('Resource ID of an existing Bastion to reuse (BYO). Informational — used by docs/runbooks. When non-empty, `deployBastion` defaults to `false`.')
param existingBastionResourceId string?

@description('Resource ID of an existing NAT Gateway to associate with the spoke subnets (BYO). When non-empty, `deployNatGateway` defaults to `false`.')
param existingNatGatewayResourceId string?

@description('Resource ID of an existing jumpbox VM (BYO). Informational — used by docs/runbooks for post-provision flows. When non-empty, `deployJumpbox` defaults to `false`.')
param existingJumpboxResourceId string?

@description('DEPRECATED (v2.0.0). Legacy v1.x consolidated switch for jumpbox + Bastion + NAT Gateway. Provided as a transitional fallback so v1.x parameter files continue to deploy unmodified — explicit `deployJumpbox` / `deployBastion` / `deployNatGateway` values ALWAYS take precedence over this flag. Will be REMOVED in v3.0.0; migrate to the three component-specific flags.')
param deployVM bool?

@description('Deploy the virtual network subnets.')
param deploySubnets bool = true

@description('Will deploy network security groups.')
param deployNsgs bool = true

@description('Deploy Azure Firewall with UDR for egress traffic control. Defaults to true when networkIsolation is enabled.')
param deployAzureFirewall bool = true

@description('Enable DNS proxy on the spoke-local Azure Firewall policy. Defaults to false. Only effective when deployAzureFirewall and networkIsolation are true; does not change VNet or VPN client DNS settings or create a DNS resolver.')
param enableFirewallDnsProxy bool = false

@description('Deploy an ACR Task agent pool so image builds can run inside the VNet when the registry has public access disabled. Requires a Premium container registry (auto-selected when networkIsolation is true) and is gated on both deployContainerRegistry and networkIsolation.')
param deployAcrTaskAgentPool bool = true

@description('Prepare accelerator-neutral Microsoft Foundry hosted-agent prerequisites without requesting downstream agent deployment. Provisions the required project and registry RBAC and exposes project, registry, network, and private-build handoff values. deployHostedAgent implies this behavior. Defaults to false.')
param prepareHostedAgent bool = false

@description('Grant the deployment executor Foundry Project Manager when Hosted prerequisites are selected. Defaults to true for compatible foundation callers. Set false when the executor already has required project authorization; this never disables the project managed identity registry pull grant.')
param grantHostedAgentProjectManager bool = true

@description('Request the downstream Microsoft Foundry hosted-agent deployment handoff. Implies prepareHostedAgent behavior and requires hostedAgent.version to be an immutable OCI digest. The landing zone does not create the data-plane agent version and never changes Container Apps or data resources. Defaults to false.')
param deployHostedAgent bool = false

@description('Typed hosted-agent deployment handoff consumed by a downstream `azure.ai.agent` service. `image` is the repository path within the selected registry, `version` must be an immutable OCI digest (`sha256:` plus 64 lowercase hex characters), optional `startupCommand` maps to the official azure.yaml field, and `runtime` maps to `container.resources`. Values are validated only when deployHostedAgent is true.')
param hostedAgent hostedAgentConfigurationType = {
  name: ''
  image: ''
  version: ''
  startupCommand: ''
  runtime: {
    cpu: '1'
    memory: '1Gi'
  }
  protocols: [
    {
      protocol: 'responses'
      version: '2.0.0'
    }
  ]
}

@description('Optional resource ID of an existing Azure Container Registry used for hosted-agent images when deployContainerRegistry is false. The deploying principal must be able to create role assignments at this scope.')
param hostedAgentContainerRegistryResourceId string = ''

@description('Optional login endpoint of an existing Azure Container Registry used for hosted-agent images when deployContainerRegistry is false, for example `contoso.azurecr.io`. Private endpoint, DNS, and VNet-internal build connectivity for an existing registry remain consumer responsibilities.')
param hostedAgentContainerRegistryEndpoint string = ''

@description('Role assignment permissions mode of the existing hosted-agent registry when deployContainerRegistry is false. Use `rbac` for RBAC Registry Permissions or `rbac-abac` for RBAC Registry + ABAC Repository Permissions. The landing-zone registry always uses `rbac`.')
@allowed([ 'rbac', 'rbac-abac' ])
param hostedAgentContainerRegistryRoleAssignmentMode string = 'rbac'

@description('Name for the ACR Task agent pool. Max 20 characters.')
@maxLength(20)
param acrTaskAgentPoolName string = 'build-pool'

@description('SKU tier for the ACR Task agent pool: S1 (2 vCPU), S2 (4 vCPU), S3 (8 vCPU).')
@allowed([ 'S1', 'S2', 'S3' ])
param acrTaskAgentPoolTier string = 'S1'

@description('Initial instance count for the ACR Task agent pool. Set to 0 after provisioning to pause billing (az acr agentpool update -r <acr> -n <pool> --count 0).')
@minValue(0)
param acrTaskAgentPoolCount int = 1

@description('When true, extends the Azure Firewall Policy with the FQDN allow-list required by the default install.ps1 jumpbox bootstrap (Chocolatey, Python, Node, VS Code, GitHub clones, Azure CLI control plane). Disable if you manage egress centrally.')
param extendFirewallForJumpboxBootstrap bool = true

@description('When true, extends the Azure Firewall Policy with the FQDN allow-list required for ACR Tasks builds running inside the build-agents subnet to fetch language packages (npm, PyPI) and OS packages (Debian/Ubuntu apt repos, yarn). Only effective when networkIsolation, deployAzureFirewall and deployAcrTaskAgentPool are all enabled. Disable if you manage egress centrally or pre-bake all dependencies into the builder base image.')
param extendFirewallForAcrTaskBuilds bool = true

@description('Additional FQDNs to allow from the ACR Tasks build-agent subnet when extendFirewallForAcrTaskBuilds is true. Use this for application-specific build dependencies that are not part of the landing-zone default allow-list.')
param additionalAcrTaskBuildFqdns array = []

@description('List of trusted source IP CIDRs allowed to connect to the Bastion public IP on port 443. When empty, all internet inbound to port 443 is denied by default.')
param bastionAllowedSourceIPs array = []

@description('Bastion SKU. `Standard` supports native client (`az network bastion rdp/ssh`) and tunneling; `Premium` adds shareable link, session recording, and private-only mode. `Basic` does not support tunneling.')
@allowed(['Basic', 'Standard', 'Premium'])
param bastionSkuName string = 'Standard'

@description('Enable Bastion native client tunneling. Required for `az network bastion rdp/ssh`, RDP audio/clipboard/device redirection, and SSH agent forwarding. Off by default for parity with portal-only access. Requires `bastionSkuName` to be `Standard` or `Premium`.')
param bastionEnableTunneling bool = false

@description('When true, extends the Azure Firewall Policy with a Network Rule Collection allowing UDP/TCP egress from spoke subnets (jumpbox, ACA environment, agent) to the `AzureCloud` Service Tag. Required for any spoke workload that uses Azure Speech real-time avatar, Azure Communication Services Calling, or Microsoft Teams Media (WebRTC peer connections, STUN/TURN UDP 3478-3481 and TCP 443/3478-3481). Off by default to preserve least-privilege egress. Only effective when `networkIsolation` and `deployAzureFirewall` are both true.')
param enableAcsMediaEgress bool = false

// ----------------------------------------------------------------------
// Public Ingress (#49) — optional Application Gateway WAF v2 in front of the
// internal Container Apps environment. Default-disabled. WARNING: enabling
// this deploys WAF_v2 + a Standard Public IP, which incur hourly charges
// even when idle. To remove the stack, run `azd down` or delete the
// resources manually — `azd`/ARM incremental deployments will NOT delete
// these resources when `publicIngress.enabled` flips back to false after a
// previous deploy. See README "Optional Public Ingress" for the runbook.
// ----------------------------------------------------------------------

@export()
@description('Aggregate parameter for the optional public ingress (Application Gateway WAF v2). See README "Optional Public Ingress".')
type publicIngressType = {
  @description('Master toggle. When false (default) no public-ingress resources are deployed.')
  enabled: bool

  @description('Optional. Index of the entry in `containerAppsList` that the gateway routes to. Defaults to 0.')
  backendAppIndex: int?

  @description('Optional. Frontend host name presented to clients (e.g., app.contoso.com). Required to activate the HTTPS listener.')
  frontendHostName: string?

  @description('Optional. Versionless Key Vault secret ID for the TLS certificate. Required to activate the HTTPS listener.')
  sslCertSecretId: string?

  @description('Optional. CIDRs allowed to reach the gateway on TCP/443. Empty list keeps the gateway fully inert (skeleton mode).')
  allowedSourceAddressPrefixes: string[]?

  @description('Optional. WAF mode. Defaults to `Prevention`.')
  wafMode: ('Prevention' | 'Detection')?

  @description('Optional. WAF custom rules merged with the OWASP CRS 3.2 managed ruleset.')
  wafCustomRules: object[]?

  @description('Optional. AGW autoscale capacity (e.g., `{ minCapacity: 0, maxCapacity: 2 }`).')
  capacity: object?

  @description('Optional. AGW sslPolicy block. When omitted, the gateway uses the Azure default policy.')
  sslPolicy: object?
}

@export()
@sealed()
@description('Invocation protocol implemented by a hosted agent. Values match the Microsoft Foundry `azure.ai.agent` service contract.')
type hostedAgentProtocolType = {
  @description('Protocol implemented by the agent container.')
  protocol: 'responses' | 'invocations' | 'invocations_ws' | 'a2a'

  @description('Optional protocol version exposed by the agent.')
  version: string?
}

@export()
@sealed()
@description('Container CPU and memory settings passed to `azure.ai.agent` as `container.resources`.')
type hostedAgentRuntimeType = {
  @description('CPU allocation from `0.25` through `4.0`, for example `0.5` or `1`.')
  cpu: string

  @description('Memory allocation from `0.5Gi` through `8Gi`.')
  memory: string
}

@export()
@sealed()
@description('Accelerator-neutral handoff for a downstream Microsoft Foundry hosted-agent deployment.')
type hostedAgentConfigurationType = {
  @description('Stable hosted-agent name. Reusing this name creates a new immutable version.')
  name: string

  @description('Container image repository path inside the selected registry, without a tag or digest.')
  image: string

  @description('Immutable OCI image digest in `sha256:<64 lowercase hex characters>` form.')
  version: string

  @description('Optional command that starts the agent server. Maps to `startupCommand` in the official `azure.ai.agent` service contract.')
  startupCommand: string

  @description('Hosted-agent container resource settings.')
  runtime: hostedAgentRuntimeType

  @description('Invocation protocols implemented by the hosted agent.')
  protocols: hostedAgentProtocolType[]
}

@export()
@description('Shape for an accelerator-supplied App Configuration key-value that the landing zone passes through verbatim. Values are stored as plaintext, never pass secrets here (use Key Vault references instead).')
type additionalAppConfigurationSettingType = {
  @description('Required. App Configuration key name.')
  name: string

  @description('Required. Plaintext value. Do not put secrets here.')
  value: string

  @description('Optional. App Configuration label. Defaults to the landing zone appConfigLabel.')
  label: string?

  @description('Optional. Content type. Defaults to text/plain. Use application/json for JSON values.')
  contentType: string?
}

@description('Optional. Public Application Gateway WAF v2 ingress in front of the internal Container Apps environment. Disabled by default. WARNING: enabling this deploys WAF_v2 and a Standard Public IP, which incur hourly charges even when idle. See README "Optional Public Ingress" for the post-deploy runbook.')
param publicIngress publicIngressType = { enabled: false }

@description('Will deploy network resources side by side with the Azure resources.')
param sideBySideDeploy bool = true

@description('Deploy Virtual Machine software.')
param deploySoftware bool = true

@description('Deploy AI Foundry Project.')
param deployAfProject bool = true

@description('Deploy AI Foundry Service.')
param deployAAfAgentSvc bool = true

@description('Whether to disable local (API-key) authentication on the AI Foundry account, enforcing Microsoft Entra ID-only authentication. Local authentication is disabled by default for security.')
param aiFoundryDisableLocalAuth bool = true


@description('Deprecated. Kept for one release for compatibility with existing deployments. Use retrievalBackend and the Foundry IQ parameters instead.')
param enableAgenticRetrieval bool = false

@description('Retrieval backend stamped into application runtime configuration. New deployments default to foundry_iq. Existing deployments can keep ai_search until they explicitly migrate.')
@allowed([
  'ai_search'
  'foundry_iq'
])
param retrievalBackend string = 'foundry_iq'

@description('Deprecated: prefer publishing this via additionalAppConfigurationSettings so the landing zone stays workload-agnostic. Retained for backward compatibility. Foundry IQ knowledge pattern. azureBlob uses native Foundry IQ Blob or ADLS Gen2 ingestion and is the default. searchIndex registers the existing Agent Landing Zone Azure AI Search index as an opt-in legacy Pattern B knowledge source. managed is accepted as a compatibility alias for azureBlob.')
@allowed([
  'azureBlob'
  'managed'
  'searchIndex'
])
param foundryIqPattern string = 'azureBlob'

@description('Azure AI Search / Foundry IQ data-plane API version for knowledge base retrieval and knowledge source operations. Use 2026-05-01-preview when native permissions or Pattern B filterAddOn are required.')
param foundryIqApiVersion string = '2026-05-01-preview'

@description('Azure AI Search knowledgeRetrieval billing plan for agentic retrieval. free uses the included allowance; standard enables pay-as-you-go billing after the free allowance.')
@allowed([
  'free'
  'standard'
])
param foundryIqKnowledgeRetrievalBillingPlan string = 'free'

@description('Foundry IQ knowledge base name to stamp into runtime configuration.')
param knowledgeBaseName string = '${environmentName}-knowledge-base'

@description('Dedicated Azure AI Foundry connection name used by the knowledge base. Do not reuse SEARCH_CONNECTION_ID.')
param knowledgeBaseConnectionName string = '${environmentName}-knowledge-base-connection'

@description('Deprecated: prefer publishing this via additionalAppConfigurationSettings so the landing zone stays workload-agnostic. Retained for backward compatibility. Foundry IQ knowledge source name. For azureBlob this is the native Blob or ADLS Gen2 source. For searchIndex this is the registered Agent Landing Zone Azure AI Search index source.')
param foundryIqKnowledgeSourceName string = '${environmentName}-blob-ks'

@description('Foundry IQ knowledge source kind stamped into runtime configuration. Leave empty to derive it from foundryIqPattern. Set to azureBlob for native Blob/ADLS sources or searchIndex for Pattern B.')
@allowed([
  ''
  'azureBlob'
  'searchIndex'
])
param foundryIqKnowledgeSourceKind string = ''

@description('Storage container used by the native Foundry IQ azureBlob knowledge source.')
param foundryIqStorageContainerName string = 'documents'

@description('Optional folder path within the native Foundry IQ Blob or ADLS Gen2 knowledge source container. Empty ingests from the container root.')
param foundryIqStorageFolderPath string = ''

@description('Set true when the native Foundry IQ azureBlob knowledge source points to an ADLS Gen2 account/container with hierarchical namespace enabled.')
param foundryIqIsAdlsGen2 bool = false

@description('Native Foundry IQ content extraction mode for the azureBlob knowledge source. standard uses the Content Understanding skill for layout and OCR, which is required for scanned and image-only PDFs. minimal skips Content Understanding and ingests only text already present in the source.')
@allowed([
  'minimal'
  'standard'
])
param foundryIqContentExtractionMode string = 'standard'

@description('Optional Foundry AI Services endpoint for native Foundry IQ standard extraction. Leave empty to use https://<ai-foundry-account>.services.ai.azure.com/.')
param foundryIqAiServicesEndpoint string = ''

@description('Native Foundry IQ permission metadata to ingest. Blob sources with foundryIqIsAdlsGen2=false support rbacScope and sensitivityLabels. ADLS Gen2 sources can override this to include userIds and groupIds when ACL metadata is required.')
param foundryIqIngestionPermissionOptions array = [
  'rbacScope'
]

@description('JSON array override for native Foundry IQ permission metadata, intended for azd environment substitution from FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS. Leave empty to use foundryIqIngestionPermissionOptions.')
param foundryIqIngestionPermissionOptionsJson string = ''

@description('Deprecated: prefer publishing this via additionalAppConfigurationSettings so the landing zone stays workload-agnostic. Retained for backward compatibility. Existing Agent Landing Zone Azure AI Search index name to register as a Pattern B Foundry IQ searchIndex knowledge source.')
param foundryIqSearchIndexName string = 'agent-lz-index'

@description('Semantic configuration name on the Agent Landing Zone Azure AI Search index. Required by Azure AI Search agentic retrieval.')
param foundryIqSemanticConfigurationName string = 'default'

@description('Retrievable source data fields exposed from the Pattern B searchIndex knowledge source for citations.')
param foundryIqSourceDataFields array = [
  'id'
  'title'
  'filepath'
  'url'
  'content'
]

@description('Optional search fields for the Pattern B searchIndex knowledge source. Leave empty to let Azure AI Search search all eligible fields.')
param foundryIqSearchFields array = [
  'content'
]

@description('Deprecated: prefer publishing this via additionalAppConfigurationSettings so the landing zone stays workload-agnostic. Retained for backward compatibility. Optional persisted baseFilter for the Pattern B searchIndex knowledge source. Keep security trimming in query-time filterAddOn unless a static tenant/corpus filter is required.')
param foundryIqBaseFilter string = ''

@description('Deprecated: prefer publishing this via additionalAppConfigurationSettings so the landing zone stays workload-agnostic. Retained for backward compatibility. Enable query-time Pattern B filterAddOn in the Agent Landing Zone orchestrator. Requires foundryIqApiVersion 2026-05-01-preview.')
param foundryIqFilterAddOnEnabled bool = true

@description('Collection field used by the Agent Landing Zone for Pattern B security trimming filterAddOn.')
param foundryIqSecurityFieldName string = 'metadata_security_id'

@description('Optional maximum documents to return from Foundry IQ retrieval. Empty keeps the orchestrator default.')
param foundryIqMaxOutputDocuments string = ''

// ----------------------------------------------------------------------
// Reuse Existing Services Parameters
// Note: Reuse is optional. Leave empty to create new resources
// ----------------------------------------------------------------------

// AI Foundry Dependencies

@description('The AI Search Service full ARM resource ID. Optional; if not provided, a new resource will be created.')
param aiSearchResourceId string = ''

@description('The AI Storage Account full ARM resource ID. Optional; if not provided, a new resource will be created.')
param aiFoundryStorageAccountResourceId string = ''

@description('The SKU name for the AI Foundry Storage Account. Only used when a new account is created (aiFoundryStorageAccountResourceId is empty). The AVM ai-foundry module does not expose this, so we pre-create the storage account with the requested SKU. Defaults to Standard_LRS for broad regional availability (some regions, e.g. Poland Central, do not support the AVM default Standard_GRS).')
@allowed([
  'Standard_LRS'
  'Standard_GRS'
  'Standard_RAGRS'
  'Standard_ZRS'
  'Standard_GZRS'
  'Standard_RAGZRS'
  'Premium_LRS'
  'Premium_ZRS'
])
param aiFoundryStorageSku string = 'Standard_LRS'

@description('The Cosmos DB account full ARM resource ID. Optional; if not provided, a new resource will be created.')
param aiFoundryCosmosDBAccountResourceId string = ''

// GenAI App Services

@description('The Key Vault full ARM resource ID. Optional; if not provided, a new vault will be created.')
param keyVaultResourceId string = ''

// ----------------------------------------------------------------------
// Feature-flagging Params (as booleans with a default of false)
// ----------------------------------------------------------------------
param useUAI bool = false // Use User Assigned Identity (UAI)
param useCAppAPIKey bool = false // Use API Keys to connect to container apps
param useZoneRedundancy bool = false // Use Zone Redundancy

// ----------------------------------------------------------------------
// Resource Naming params
// ----------------------------------------------------------------------

@description('Unique token used to build deterministic resource names, derived from subscription ID, environment name, and location.')
param resourceToken string = toLower(uniqueString(subscription().id, environmentName, location))

@description('Controls generated resource names. Use `caf` (default) for Cloud Adoption Framework-style generated names. Use `legacy` to preserve the older resource-token-based generated names. Explicit name parameters still override generated names in either mode.')
@allowed([
  'legacy'
  'caf'
])
param resourceNamingMode string = 'caf'

@description('CAF naming token for the workload or application. Leave empty (default) to use a short deterministic hash, stable per subscription, environment, and location, so deployments get unique names without manual input. Override with a meaningful name such as `chatapp` when desired. Used only when `resourceNamingMode` is `caf` and an explicit resource name parameter is not supplied.')
param cafWorkloadName string = ''

@description('CAF naming token for the environment, such as dev, test, or prod. Leave empty (default) to use the azd environment name. Used only when `resourceNamingMode` is `caf` and an explicit resource name parameter is not supplied.')
param cafEnvironmentName string = ''

@description('CAF naming token for the Azure region. Leave empty (default) to use the deployment location supplied by azd (`AZURE_LOCATION`), mapped to a short region code. Used only when `resourceNamingMode` is `caf` and an explicit resource name parameter is not supplied.')
param cafRegionName string = ''

@description('CAF naming instance token, such as 001. Increment only when deploying a second parallel copy of the same workload in the same environment and region. Used only when `resourceNamingMode` is `caf` and an explicit resource name parameter is not supplied.')
param cafInstance string = '001'

@description('Name of the Azure AI Foundry account to create or reference.')
param aiFoundryAccountName string = '${const.abbrs.ai.aiFoundry}${resourceToken}'

@description('Name of the AI Foundry project resource.')
param aiFoundryProjectName string = '${const.abbrs.ai.aiFoundryProject}${resourceToken}'

@description('Optional display name for the AI Foundry project. When omitted, the default display name is used.')
param aiFoundryProjectDisplayName string?

@description('Optional description for the AI Foundry project. When omitted, the default description is used.')
param aiFoundryProjectDescription string?

@description('Name of the Storage Account used by AI Foundry for blobs, queues, tables, and files.')
param aiFoundryStorageAccountName string = replace('${const.abbrs.storage.storageAccount}${const.abbrs.ai.aiFoundry}${resourceToken}', '-', '')

@description('Name of the Cognitive Search service provisioned for AI Foundry.')
param aiFoundrySearchServiceName string = '${const.abbrs.ai.aiSearch}${const.abbrs.ai.aiFoundry}${resourceToken}'

@description('Name of the Azure Cosmos DB account used by AI Foundry.')
param aiFoundryCosmosDbName string = '${const.abbrs.databases.cosmosDBDatabase}${const.abbrs.ai.aiFoundry}${resourceToken}'

@description('Name of the Bing Search resource for grounding capabilities.')
param bingSearchName string = '${const.abbrs.ai.bing}${resourceToken}'

@description('Name of the Azure App Configuration store for centralized settings.')
param appConfigName string = '${const.abbrs.configuration.appConfiguration}${resourceToken}'

@description('Name of the Application Insights instance for monitoring.')
param appInsightsName string = '${const.abbrs.managementGovernance.applicationInsights}${resourceToken}'

@description('Name of the Azure Container Apps environment (log ingestion, VNet integration, etc.).')
param containerEnvName string = '${const.abbrs.containers.containerAppsEnvironment}${resourceToken}'

@description('Name of the Azure Container Registry for storing Docker images.')
param containerRegistryName string = '${const.abbrs.containers.containerRegistry}${resourceToken}'

@description('Name of the Cosmos DB account (alias for database operations).')
param dbAccountName string = '${const.abbrs.databases.cosmosDBDatabase}${resourceToken}'

@description('Name of the Cosmos DB database to host application data.')
param dbDatabaseName string = '${const.abbrs.databases.cosmosDBDatabase}db${resourceToken}'

@description('Name of the Azure Key Vault for secrets, keys, and certificates.')
param keyVaultName string = '${const.abbrs.security.keyVault}${resourceToken}'

@description('Name of the Log Analytics workspace for collecting and querying logs.')
param logAnalyticsWorkspaceName string = '${const.abbrs.managementGovernance.logAnalyticsWorkspace}${resourceToken}'

@description('Name of the Cognitive Search service.')
param searchServiceName string = '${const.abbrs.ai.aiSearch}${resourceToken}'

@description('Optional override for the Azure AI Speech account name. When empty, a name is generated from the resource token. Also used as the customSubDomainName, so it must be globally unique within `cognitiveservices.azure.com`.')
param speechServiceName string = '${const.abbrs.ai.speechService}${resourceToken}'

@description('Name of the Azure Storage Account for general-purpose blob and file storage.')
param storageAccountName string = '${const.abbrs.storage.storageAccount}${resourceToken}'

@description('Name of the Virtual Network to isolate resources and enable private endpoints.')
param vnetName string = '${const.abbrs.networking.virtualNetwork}${resourceToken}'

// Trims a candidate name to a maximum length and drops a trailing hyphen so the
// result is never an invalid Azure resource name (e.g. `kv-...-` after truncation).
func cafTrim(candidate string, maxLength int) string =>
  endsWith(take(candidate, maxLength), '-') ? take(candidate, maxLength - 1) : take(candidate, maxLength)

// CAF region tokens are abbreviated to short codes so generated names stay within
// Azure resource name limits (storage 24, Key Vault 24, Container Apps env 32, etc.).
// Unknown regions fall back to a 5-character slug of the raw region string.
var _cafRegionAbbrs = {
  eastus: 'eus'
  eastus2: 'eus2'
  centralus: 'cus'
  northcentralus: 'ncus'
  southcentralus: 'scus'
  westcentralus: 'wcus'
  westus: 'wus'
  westus2: 'wus2'
  westus3: 'wus3'
  canadacentral: 'cnc'
  canadaeast: 'cne'
  brazilsouth: 'brs'
  brazilsoutheast: 'brse'
  mexicocentral: 'mxc'
  northeurope: 'neu'
  westeurope: 'weu'
  uksouth: 'uks'
  ukwest: 'ukw'
  francecentral: 'frc'
  francesouth: 'frs'
  germanywestcentral: 'gwc'
  switzerlandnorth: 'chn'
  switzerlandwest: 'chw'
  norwayeast: 'noe'
  swedencentral: 'sdc'
  polandcentral: 'plc'
  italynorth: 'itn'
  spaincentral: 'spc'
  uaenorth: 'uan'
  qatarcentral: 'qac'
  israelcentral: 'ilc'
  southafricanorth: 'san'
  australiaeast: 'aue'
  australiasoutheast: 'ause'
  southeastasia: 'sea'
  eastasia: 'ea'
  centralindia: 'inc'
  southindia: 'ins'
  westindia: 'inw'
  japaneast: 'jpe'
  japanwest: 'jpw'
  koreacentral: 'krc'
  koreasouth: 'krs'
}
var _cafRegionInput = empty(cafRegionName) ? location : cafRegionName
var _cafRegionRaw = toLower(replace(_cafRegionInput, ' ', ''))
var _cafRegion = contains(_cafRegionAbbrs, _cafRegionRaw) ? _cafRegionAbbrs[_cafRegionRaw] : take(_cafRegionRaw, 5)
var _cafWorkload = toLower(empty(cafWorkloadName) ? substring(uniqueString(subscription().id, environmentName, location), 0, 6) : cafWorkloadName)
var _cafEnv = toLower(empty(cafEnvironmentName) ? environmentName : cafEnvironmentName)
var _cafInstance = toLower(empty(cafInstance) ? '001' : cafInstance)
var _cafNameStem = '${_cafWorkload}-${_cafEnv}-${_cafRegion}-${_cafInstance}'
var _cafCompactStem = replace(_cafNameStem, '-', '')

var _legacyResourceNames = {
  aiFoundryAccountName: '${const.abbrs.ai.aiFoundry}${resourceToken}'
  aiFoundryProjectName: '${const.abbrs.ai.aiFoundryProject}${resourceToken}'
  aiFoundryStorageAccountName: replace('${const.abbrs.storage.storageAccount}${const.abbrs.ai.aiFoundry}${resourceToken}', '-', '')
  aiFoundrySearchServiceName: '${const.abbrs.ai.aiSearch}${const.abbrs.ai.aiFoundry}${resourceToken}'
  aiFoundryCosmosDbName: '${const.abbrs.databases.cosmosDBDatabase}${const.abbrs.ai.aiFoundry}${resourceToken}'
  bingSearchName: '${const.abbrs.ai.bing}${resourceToken}'
  appConfigName: '${const.abbrs.configuration.appConfiguration}${resourceToken}'
  appInsightsName: '${const.abbrs.managementGovernance.applicationInsights}${resourceToken}'
  containerEnvName: '${const.abbrs.containers.containerAppsEnvironment}${resourceToken}'
  containerRegistryName: '${const.abbrs.containers.containerRegistry}${resourceToken}'
  dbAccountName: '${const.abbrs.databases.cosmosDBDatabase}${resourceToken}'
  dbDatabaseName: '${const.abbrs.databases.cosmosDBDatabase}db${resourceToken}'
  keyVaultName: '${const.abbrs.security.keyVault}${resourceToken}'
  logAnalyticsWorkspaceName: '${const.abbrs.managementGovernance.logAnalyticsWorkspace}${resourceToken}'
  searchServiceName: '${const.abbrs.ai.aiSearch}${resourceToken}'
  speechServiceName: '${const.abbrs.ai.speechService}${resourceToken}'
  storageAccountName: '${const.abbrs.storage.storageAccount}${resourceToken}'
  vnetName: '${const.abbrs.networking.virtualNetwork}${resourceToken}'
}

var _cafResourceNames = {
  aiFoundryAccountName: cafTrim('aif-${_cafNameStem}', 64)
  aiFoundryProjectName: cafTrim('aifp-${_cafNameStem}', 64)
  aiFoundryStorageAccountName: cafTrim('staif${_cafCompactStem}', 24)
  aiFoundrySearchServiceName: cafTrim('srch-aif-${_cafNameStem}', 60)
  aiFoundryCosmosDbName: cafTrim('cosmos-aif-${_cafNameStem}', 44)
  bingSearchName: cafTrim('bing-${_cafNameStem}', 64)
  appConfigName: cafTrim('appcs-${_cafNameStem}', 50)
  appInsightsName: cafTrim('appi-${_cafNameStem}', 64)
  containerEnvName: cafTrim('cae-${_cafNameStem}', 32)
  containerRegistryName: cafTrim('cr${_cafCompactStem}', 50)
  dbAccountName: cafTrim('cosmos-${_cafNameStem}', 44)
  dbDatabaseName: cafTrim('cosmosdb-${_cafNameStem}', 63)
  keyVaultName: cafTrim('kv-${_cafNameStem}', 24)
  logAnalyticsWorkspaceName: cafTrim('log-${_cafNameStem}', 63)
  searchServiceName: cafTrim('srch-${_cafNameStem}', 60)
  speechServiceName: cafTrim('spch-${_cafNameStem}', 64)
  storageAccountName: cafTrim('st${_cafCompactStem}', 24)
  vnetName: cafTrim('vnet-${_cafNameStem}', 64)
}

var resourceNames = {
  aiFoundryAccountName: !empty(aiFoundryAccountName) && !(resourceNamingMode == 'caf' && aiFoundryAccountName == _legacyResourceNames.aiFoundryAccountName) ? aiFoundryAccountName : (resourceNamingMode == 'caf' ? _cafResourceNames.aiFoundryAccountName : _legacyResourceNames.aiFoundryAccountName)
  aiFoundryProjectName: !empty(aiFoundryProjectName) && !(resourceNamingMode == 'caf' && aiFoundryProjectName == _legacyResourceNames.aiFoundryProjectName) ? aiFoundryProjectName : (resourceNamingMode == 'caf' ? _cafResourceNames.aiFoundryProjectName : _legacyResourceNames.aiFoundryProjectName)
  aiFoundryStorageAccountName: !empty(aiFoundryStorageAccountName) && !(resourceNamingMode == 'caf' && aiFoundryStorageAccountName == _legacyResourceNames.aiFoundryStorageAccountName) ? aiFoundryStorageAccountName : (resourceNamingMode == 'caf' ? _cafResourceNames.aiFoundryStorageAccountName : _legacyResourceNames.aiFoundryStorageAccountName)
  aiFoundrySearchServiceName: !empty(aiFoundrySearchServiceName) && !(resourceNamingMode == 'caf' && aiFoundrySearchServiceName == _legacyResourceNames.aiFoundrySearchServiceName) ? aiFoundrySearchServiceName : (resourceNamingMode == 'caf' ? _cafResourceNames.aiFoundrySearchServiceName : _legacyResourceNames.aiFoundrySearchServiceName)
  aiFoundryCosmosDbName: !empty(aiFoundryCosmosDbName) && !(resourceNamingMode == 'caf' && aiFoundryCosmosDbName == _legacyResourceNames.aiFoundryCosmosDbName) ? aiFoundryCosmosDbName : (resourceNamingMode == 'caf' ? _cafResourceNames.aiFoundryCosmosDbName : _legacyResourceNames.aiFoundryCosmosDbName)
  bingSearchName: !empty(bingSearchName) && !(resourceNamingMode == 'caf' && bingSearchName == _legacyResourceNames.bingSearchName) ? bingSearchName : (resourceNamingMode == 'caf' ? _cafResourceNames.bingSearchName : _legacyResourceNames.bingSearchName)
  appConfigName: !empty(appConfigName) && !(resourceNamingMode == 'caf' && appConfigName == _legacyResourceNames.appConfigName) ? appConfigName : (resourceNamingMode == 'caf' ? _cafResourceNames.appConfigName : _legacyResourceNames.appConfigName)
  appInsightsName: !empty(appInsightsName) && !(resourceNamingMode == 'caf' && appInsightsName == _legacyResourceNames.appInsightsName) ? appInsightsName : (resourceNamingMode == 'caf' ? _cafResourceNames.appInsightsName : _legacyResourceNames.appInsightsName)
  containerEnvName: !empty(containerEnvName) && !(resourceNamingMode == 'caf' && containerEnvName == _legacyResourceNames.containerEnvName) ? containerEnvName : (resourceNamingMode == 'caf' ? _cafResourceNames.containerEnvName : _legacyResourceNames.containerEnvName)
  containerRegistryName: !empty(containerRegistryName) && !(resourceNamingMode == 'caf' && containerRegistryName == _legacyResourceNames.containerRegistryName) ? containerRegistryName : (resourceNamingMode == 'caf' ? _cafResourceNames.containerRegistryName : _legacyResourceNames.containerRegistryName)
  dbAccountName: !empty(dbAccountName) && !(resourceNamingMode == 'caf' && dbAccountName == _legacyResourceNames.dbAccountName) ? dbAccountName : (resourceNamingMode == 'caf' ? _cafResourceNames.dbAccountName : _legacyResourceNames.dbAccountName)
  dbDatabaseName: !empty(dbDatabaseName) && !(resourceNamingMode == 'caf' && dbDatabaseName == _legacyResourceNames.dbDatabaseName) ? dbDatabaseName : (resourceNamingMode == 'caf' ? _cafResourceNames.dbDatabaseName : _legacyResourceNames.dbDatabaseName)
  keyVaultName: !empty(keyVaultName) && !(resourceNamingMode == 'caf' && keyVaultName == _legacyResourceNames.keyVaultName) ? keyVaultName : (resourceNamingMode == 'caf' ? _cafResourceNames.keyVaultName : _legacyResourceNames.keyVaultName)
  logAnalyticsWorkspaceName: !empty(logAnalyticsWorkspaceName) && !(resourceNamingMode == 'caf' && logAnalyticsWorkspaceName == _legacyResourceNames.logAnalyticsWorkspaceName) ? logAnalyticsWorkspaceName : (resourceNamingMode == 'caf' ? _cafResourceNames.logAnalyticsWorkspaceName : _legacyResourceNames.logAnalyticsWorkspaceName)
  searchServiceName: !empty(searchServiceName) && !(resourceNamingMode == 'caf' && searchServiceName == _legacyResourceNames.searchServiceName) ? searchServiceName : (resourceNamingMode == 'caf' ? _cafResourceNames.searchServiceName : _legacyResourceNames.searchServiceName)
  speechServiceName: !empty(speechServiceName) && !(resourceNamingMode == 'caf' && speechServiceName == _legacyResourceNames.speechServiceName) ? speechServiceName : (resourceNamingMode == 'caf' ? _cafResourceNames.speechServiceName : _legacyResourceNames.speechServiceName)
  storageAccountName: !empty(storageAccountName) && !(resourceNamingMode == 'caf' && storageAccountName == _legacyResourceNames.storageAccountName) ? storageAccountName : (resourceNamingMode == 'caf' ? _cafResourceNames.storageAccountName : _legacyResourceNames.storageAccountName)
  vnetName: !empty(vnetName) && !(resourceNamingMode == 'caf' && vnetName == _legacyResourceNames.vnetName) ? vnetName : (resourceNamingMode == 'caf' ? _cafResourceNames.vnetName : _legacyResourceNames.vnetName)
}

// ----------------------------------------------------------------------
// Azure AI Foundry Service params
// ----------------------------------------------------------------------

@description('List of model deployments to create in the AI Foundry account')
param modelDeploymentList array

// ----------------------------------------------------------------------
// Container Apps params
// ----------------------------------------------------------------------

@description('List of container apps to create. Dapr is opt-in per app through `dapr.enabled=true`; apps without a `dapr` object deploy with Dapr disabled. Optional `image` keeps an already deployed image on reprovision; when empty the placeholder image is used.')
param containerAppsList array

@description('Workload profiles.')
param workloadProfiles array = []

param acrDnsSuffix string = (environment().name == 'AzureUSGovernment' ? 'azurecr.us' : environment().name == 'AzureChinaCloud'   ? 'azurecr.cn' : 'azurecr.io')

var effectiveFoundryIqKnowledgeSourceKind = retrievalBackend == 'foundry_iq'
  ? (!empty(foundryIqKnowledgeSourceKind) ? foundryIqKnowledgeSourceKind : (foundryIqPattern == 'searchIndex' ? 'searchIndex' : 'azureBlob'))
  : ''
var effectiveFoundryIqIngestionPermissionOptions = !empty(foundryIqIngestionPermissionOptionsJson) ? json(foundryIqIngestionPermissionOptionsJson) : foundryIqIngestionPermissionOptions

// ----------------------------------------------------------------------
// Cosmos DB Database params
// ----------------------------------------------------------------------

@description('Optional throughput (RU/s) for the Cosmos DB database. Omit or set to null for serverless accounts.')
param dbDatabaseThroughput int?

@description('List of Cosmos DB containers to create. Each entry supports optional throughput and indexingPolicy via safe access.')
param databaseContainersList array

@description('Enable Synapse Link / Analytical Storage on the workload Cosmos DB account. Default is false because (a) Azure rejects this on account creation in several region/subscription combinations with the literal error "Enabling analytical storage on account creation is not supported in this subscription/region. Please disable analytical storage on the account creation request and try again." (notably observed in swedencentral, see issue #93), and (b) the default landing-zone topology does not deploy any Analytical Store consumer (Synapse Link, Fabric Mirroring). The value only takes effect at account creation; Azure does not permit toggling it on an existing Cosmos DB account, so a failed provision requires deleting the account before retrying. Set to true only when a downstream pipeline actively consumes the analytical store and the target region/subscription is known to allow it. The preflight check Test-CosmosAnalyticalStorageRegionSupport will WARN if this is true in a known-restrictive region.')
param enableCosmosAnalyticalStorage bool = false

// ----------------------------------------------------------------------
// VM params
// ----------------------------------------------------------------------

@description('The name of the Test VM. If left empty, a random name will be generated.')
param vmName string = ''

@description('Test vm user name. Needed only when choosing network isolation and create bastion option. If not you can leave it blank.')
param vmUserName string = ''

@secure()
@description('Admin password for the test VM user')
param vmAdminPassword string

@description('Size of the test VM')
param vmSize string = 'Standard_D2s_v5'

@description('Image SKU (e.g., 2022-datacenter-azure-edition, win11-25h2-ent).')
param vmImageSku string = '2022-datacenter-azure-edition'

@description('Image publisher (Windows Server: MicrosoftWindowsServer, Windows 11: MicrosoftWindowsDesktop).')
param vmImagePublisher string = 'MicrosoftWindowsServer'

@description('Image offer (Windows Server: WindowsServer, Windows 11: windows-11).')
param vmImageOffer string = 'WindowsServer'

@description('Image version (use latest unless you need a pinned build).')
param vmImageVersion string = 'latest'


// ----------------------------------------------------------------------
// Storage Account params
// ----------------------------------------------------------------------

@description('List of containers to create in the Storage Account')
param storageAccountContainersList array

// ----------------------------------------------------------------------
// CMK params
// ----------------------------------------------------------------------
// Note : Customer Managed Keys (CMK) not implemented in this module yet
// @description('Use Customer Managed Keys for Storage Account and Key Vault')
// param useCMK      bool   = false

// ----------------------------------------------------------------------
// Component deployment invariants. A parameter-only nested deployment keeps
// these checks compatible with the repository's pinned Bicep version.
// ----------------------------------------------------------------------
module componentFlagValidation 'modules/validation/component-flags.bicep' = {
  name: 'componentFlagValidation'
  params: {
    containerAppsRequireEnvironment: !deployContainerApps || deployContainerEnv
    containerAppApiKeysHavePrerequisites: !useCAppAPIKey || (deployContainerApps && deployKeyVault && deployAppConfig && appRuntimeConfigurationMode == 'appConfig')
    existingSubnetNsgAssociationsAreProtected: !(networkIsolation && useExistingVNet && !empty(selectedSubnetDefinitions) && !deployNsgs)
  }
}

//////////////////////////////////////////////////////////////////////////
// VARIABLES
//////////////////////////////////////////////////////////////////////////

// ----------------------------------------------------------------------
// General Variables
// ----------------------------------------------------------------------

// The repository-root manifest.json is the single release manifest: `components`
// feed the jumpbox clone list and `infra.source.tag` pins install.ps1 (ADR-0015).
var _manifest = loadJsonContent('../manifest.json')
var _infraSourceTag = _manifest.infra.source.tag
var _azdTags = { 'azd-env-name': environmentName }
var _modeTags = { deploymentMode: deploymentMode, 'ai-lz-version': 'v2.0.0' }
var _tags = union(_azdTags, _modeTags, deploymentTags)

var _foundryResourceGroupName = resourceGroup().name
var _applicationResourceGroupName = empty(applicationResourceGroupName) ? resourceGroup().name : applicationResourceGroupName
var _networkResourceGroupName = empty(networkResourceGroupName) ? resourceGroup().name : networkResourceGroupName

// Derive the list of additional Git repositories to clone onto the jumpbox
// directly from `manifest.json#components`. Consumers that use this landing
// zone as a Bicep module / git submodule overlay their own `manifest.json`
// (the documented submodule pattern) and so control the components there as
// the single source of truth, without needing per-deployment Bicep params.
// The derived CSV strings are forwarded to install.ps1 via the CSE
// commandToExecute as `-ExtraRepoUrls/-ExtraRepoTags/-ExtraRepoNames`. See
// issue #22.
var _manifestComponents = _manifest.?components ?? []
var _extraRepoUrls  = [for c in _manifestComponents: c.repo]
var _extraRepoTags  = [for c in _manifestComponents: c.?tag ?? 'main']
var _extraRepoNames = [for c in _manifestComponents: c.?name ?? replace(last(split(c.repo, '/')), '.git', '')]

var _networkIsolation = empty(string(networkIsolation)) ? false : bool(networkIsolation)
var _hostedAgentPrerequisitesEnabled = prepareHostedAgent || deployHostedAgent

#disable-next-line BCP318
var _hostedAgentContainerRegistryResourceId = deployContainerRegistry ? containerRegistry.outputs.resourceId : hostedAgentContainerRegistryResourceId
var _hostedAgentContainerRegistryEndpoint = deployContainerRegistry ? '${resourceNames.containerRegistryName}.${acrDnsSuffix}' : hostedAgentContainerRegistryEndpoint
var _hostedAgentImageReference = deployHostedAgent ? '${_hostedAgentContainerRegistryEndpoint}/${hostedAgent.image}@${hostedAgent.version}' : ''
var _containerRegistryRepositoryReaderRoleId = 'b93aa761-3e63-49ed-ac28-beffa264f7ac'
var _hostedAgentContainerRegistryPullRoleId = deployContainerRegistry || hostedAgentContainerRegistryRoleAssignmentMode == 'rbac'
  ? const.roles.AcrPull.guid
  : _containerRegistryRepositoryReaderRoleId

// -----------------------------------------------------------------------------
// Public network access derivation (Gap 1, issue #58)
// -----------------------------------------------------------------------------
// `publicNetworkAccess` for every workload service is now derived from two
// flat inputs rather than coupled directly to `_networkIsolation`:
//
//   _applyIpRules:        true when the operator provided one or more CIDRs.
//   _publicNetworkAccess: 'Enabled' when the topology is public OR an
//                         IP allow-list is in effect; otherwise 'Disabled'.
//
// Two parameters cover all four scenarios documented in issue #58:
//
//   networkIsolation=true,  allowedIpRanges=[]      -> Private only
//   networkIsolation=true,  allowedIpRanges=[CIDR]  -> Private + public allow-list
//   networkIsolation=false, allowedIpRanges=[]      -> Public
//   networkIsolation=false, allowedIpRanges=[CIDR]  -> Public restricted to listed IPs
//
// Per-service rule arrays are pre-shaped because each Azure RP exposes a
// slightly different schema (Storage/ACR use `{value, action}`, KV/Search/
// Cognitive use `{value}`, Cosmos accepts a flat string[]).
var _applyIpRules        = !empty(allowedIpRanges)
var _publicNetworkAccess = (!_networkIsolation || _applyIpRules) ? 'Enabled' : 'Disabled'
var _storageIpRules      = [for ip in allowedIpRanges: { value: ip, action: 'Allow' }]
var _acrIpRules          = [for ip in allowedIpRanges: { value: ip, action: 'Allow' }]
var _keyVaultIpRules     = [for ip in allowedIpRanges: { value: ip }]
var _searchIpRules       = [for ip in allowedIpRanges: { value: ip }]
var _cognitiveIpRules    = [for ip in allowedIpRanges: { value: ip }]
var _cosmosIpRules       = allowedIpRanges
// ---------------------------------------------------------------------------
// Hub-component effective deployment derivations (Gap 4, issue #58)
// ---------------------------------------------------------------------------
// Nullable inputs coalesce to v1.x defaults so existing parameter files
// (without the new flags) behave identically. BYO resource IDs flip the
// default to `false` automatically — explicit `true/false` always wins.
var _hasExistingJumpbox     = !empty(existingJumpboxResourceId ?? '')
var _hasExistingBastion     = !empty(existingBastionResourceId ?? '')
var _hasExistingNatGateway  = !empty(existingNatGatewayResourceId ?? '')

// Legacy fallback (v1.x compatibility): when `deployVM` is non-null, it acts
// as a global default for all three new flags so existing parameter files
// (e.g. the Agent Landing Zone manifest-driven overlay) keep working unmodified. Explicit
// new flags ALWAYS win — `deployVM` is purely a fallback layer. Slated for
// removal in v3.0.0; emits a deployment-time warning when consumed.
var _legacyDeployVMSet      = !(deployVM == null)
#disable-next-line BCP318
var _legacyDeployVMValue    = _legacyDeployVMSet ? deployVM! : false
var _deployJumpbox          = deployJumpbox    ?? (_legacyDeployVMSet ? (_legacyDeployVMValue && _networkIsolation && !_hasExistingJumpbox)    : (_networkIsolation && !_hasExistingJumpbox))
var _deployBastion          = deployBastion    ?? (_legacyDeployVMSet ? (_legacyDeployVMValue && _networkIsolation && _deployJumpbox && !_hasExistingBastion)    : (_networkIsolation && _deployJumpbox && !_hasExistingBastion))
var _deployNatGateway       = deployNatGateway ?? (_legacyDeployVMSet ? (_legacyDeployVMValue && _networkIsolation && _deployJumpbox && !_hasExistingNatGateway) : (_networkIsolation && _deployJumpbox && !_hasExistingNatGateway))

// Effective NAT Gateway ID — when we deploy our own NAT GW, use that. When
// the operator BYO'd one, use theirs. Otherwise empty (subnet leaves
// natGateway unset). Wired into `subnets[jumpbox].natGatewayResourceId`
// so both code paths (greenfield + useExistingVNet) attach the subnet
// to the NAT GW.
#disable-next-line BCP318
var _effectiveNatGatewayId  = _deployNatGateway ? natGateway.outputs.resourceId : (_hasExistingNatGateway ? existingNatGatewayResourceId! : '')

// ---------------------------------------------------------------------------
// Observability reuse derivations (Gap 5, issue #58)
// ---------------------------------------------------------------------------
// When the operator supplies an existing LAW or AppInsights resource ID, we
// SKIP creating those resources locally and route every consumer — diagnostic
// settings, AMPLS, Container Apps Environment telemetry, App Configuration
// publishing — to the existing IDs instead.
//
//   _hasExistingLaw / _hasExistingAI  : BYO ID provided?
//   _createLogAnalytics / _createAppInsights : do we deploy our own?
//   _lawResourceId / _appInsightsResourceId  : effective IDs to wire downstream
//   _appInsightsConnectionString             : effective connection string for
//                                              Container Apps + App Config
//
// Cross-RG-safe: we never call `.id` / `.properties` against `existing`
// resources here — those are passed through unchanged as raw strings.
var _hasExistingLaw           = !empty(existingLogAnalyticsWorkspaceResourceId ?? '')
var _hasExistingAI            = !empty(existingApplicationInsightsResourceId ?? '')
var _createLogAnalytics       = deployLogAnalytics && !_hasExistingLaw
var _createAppInsights        = deployAppInsights && !_hasExistingAI && (_createLogAnalytics || _hasExistingLaw)
#disable-next-line BCP318
var _lawResourceId            = _hasExistingLaw ? existingLogAnalyticsWorkspaceResourceId! : (_createLogAnalytics ? logAnalytics.outputs.resourceId : '')
#disable-next-line BCP318
var _appInsightsResourceId    = _hasExistingAI ? existingApplicationInsightsResourceId! : (_createAppInsights ? appInsights.outputs.resourceId : '')
#disable-next-line BCP318
var _appInsightsConnectionString = _hasExistingAI ? (existingApplicationInsightsConnectionString ?? '') : (_createAppInsights ? appInsights.outputs.properties.ConnectionString : '')
// Instrumentation key is the first KV pair in a v2 connection string
// ("InstrumentationKey=<guid>;..."). We split safely so an empty string
// returns an empty key rather than failing the template.
var _appInsightsInstrumentationKey = !empty(_appInsightsConnectionString)
  ? split(split(_appInsightsConnectionString, ';')[0], '=')[1]
  : ''
var _hasEffectiveLaw          = _hasExistingLaw || _createLogAnalytics
var _hasEffectiveAI           = _hasExistingAI || _createAppInsights

// ----------------------------------------------------------------------
// Gap 6 — External egress / route table reuse
// ----------------------------------------------------------------------
// Three valid configurations are now supported for the spoke 0.0.0.0/0 default route:
//   1. Standalone (deployAzureFirewall=true)                : local FW, local RT, route → local FW IP.
//   2. AI-LZ-integrated, hub-FW shared                       : deployAzureFirewall=false +
//                                                             hubIntegrationEgressNextHopIp set → local RT,
//                                                             route → hub FW IP.
//   3. AI-LZ-integrated, platform-team-owned RT              : hubIntegrationExistingRouteTableResourceId set →
//                                                             no local RT, no local default route. The
//                                                             platform team's RT is attached to spoke subnets
//                                                             and is assumed to already define egress routing.
// Any other combination is invalid and surfaced by the pre-flight script (Gap 9).
var _hasExistingRouteTable = !empty(hubIntegrationExistingRouteTableResourceId ?? '')
var _hasExternalEgress     = !empty(hubIntegrationEgressNextHopIp ?? '')
var _createRouteTable      = _networkIsolation && !_hasExistingRouteTable
#disable-next-line BCP318
var _effectiveRouteTableId = _hasExistingRouteTable
  ? hubIntegrationExistingRouteTableResourceId!
  : (_createRouteTable ? routeTable!.outputs.resourceId : '')
var _createDefaultRoute    = _createRouteTable && (deployAzureFirewall || _hasExternalEgress)
var _defaultRouteNextHopIp = deployAzureFirewall
  ? firewall.outputs.privateIp
  : (_hasExternalEgress ? hubIntegrationEgressNextHopIp! : '')

// ----------------------------------------------------------------------
// Gap 7 — Hub VNet peering (spoke side)
// ----------------------------------------------------------------------
// Spoke→hub peering is created inline when the spoke owns its VNet
// (useExistingVNet=false) and the operator opts in. The hub VNet may
// reside in a different subscription/RG; we parse its segments so the
// peering resource (which lives under the spoke VNet) can reference
// the remote VNet correctly. The reverse hub→spoke peering is the
// operator's responsibility — see tests/scripts/Add-HubSpokePeering.ps1.
var _hasHubVnet      = !empty(hubIntegrationHubVnetResourceId ?? '')
var _createSpokeToHubPeering = _hasHubVnet && hubIntegrationCreateHubPeering && _networkIsolation && !useExistingVNet
var _hubVnetSegs   = _hasHubVnet ? split(hubIntegrationHubVnetResourceId!, '/') : ['']
var _hubVnetName   = length(_hubVnetSegs) >= 9 ? _hubVnetSegs[8] : ''

// AMPLS (Azure Monitor Private Link Scope) and the related monitor/opinsights/automation
// private DNS zones + private endpoint are only deployed when network isolation is on AND
// the operator explicitly opts in via enablePrivateLogAnalytics AND we're creating our
// own LAW locally (a BYO/central LAW is assumed to be private-linked centrally already,
// so deploying a duplicate AMPLS would conflict on the shared monitor private DNS zones).
var _deployAmpls = _networkIsolation && _createAppInsights && _createLogAnalytics && enablePrivateLogAnalytics
var _deployPrivateDnsZones = _networkIsolation && !policyManagedPrivateDns
var _searchServiceLocation = empty(searchServiceLocation) ? location : searchServiceLocation
var _speechServiceLocation = empty(speechServiceLocation) ? location : speechServiceLocation
var _deployAiFoundryAgentService = deployAiFoundry && deployAAfAgentSvc
var _useExistingAiFoundrySearch = !empty(aiSearchResourceId)
var _useExistingAiFoundryStorage = !empty(aiFoundryStorageAccountResourceId)
var _useExistingAiFoundryCosmos = !empty(aiFoundryCosmosDBAccountResourceId)
var _deployAiFoundrySearch = _deployAiFoundryAgentService && !_useExistingAiFoundrySearch
var _deployAiFoundryStorage = _deployAiFoundryAgentService && !_useExistingAiFoundryStorage


// ----------------------------------------------------------------------
// Container vars
// ----------------------------------------------------------------------

// Placeholder image deployed initially; replaced by the operator's real image
// via `azd deploy`. Pinned to `aspnetapp-9.0` because:
//   - it listens on port 8080 by default (matches our `target_port` default,
//     so the placeholder serves a working page out of the box and lets the
//     operator validate ingress before deploying their app);
//   - it is published on MCR (no auth required from ACA pull egress);
//   - the explicit tag prevents drift when Microsoft retags `:aspnetapp`.
var _containerDummyImageName = 'mcr.microsoft.com/dotnet/samples:aspnetapp-9.0'

// ----------------------------------------------------------------------
// Networking vars
// ----------------------------------------------------------------------

// Parse existing VNet Resource ID if provided
var varVnetIdSegments = empty(existingVnetResourceId) ? [''] : split(existingVnetResourceId, '/')
var varExistingVnetSubscriptionId = length(varVnetIdSegments) >= 3 ? varVnetIdSegments[2] : subscription().subscriptionId
var varExistingVnetResourceGroupName = length(varVnetIdSegments) >= 5 ? varVnetIdSegments[4] : resourceGroup().name
var varExistingVnetName = length(varVnetIdSegments) >= 9 ? varVnetIdSegments[8] : ''

var virtualNetworkResourceId = _networkIsolation ? (useExistingVNet ? existingVnetResourceId : virtualNetwork!.outputs.resourceId) : ''

#disable-next-line BCP318
var _peSubnetId = _networkIsolation ? '${virtualNetworkResourceId}/subnets/${peSubnetName}' : ''
#disable-next-line BCP318
var _caEnvSubnetId = _networkIsolation ? '${virtualNetworkResourceId}/subnets/${acaEnvironmentSubnetName}' : ''
#disable-next-line BCP318
var _jumpbxSubnetId = _networkIsolation ? '${virtualNetworkResourceId}/subnets/${jumpboxSubnetName}' : ''
#disable-next-line BCP318
var _agentSubnetId = _networkIsolation ? '${virtualNetworkResourceId}/subnets/${agentSubnetName}' : ''

var _peLocation = !empty(privateEndpointLocation) ? privateEndpointLocation : location
var _defaultPeResourceGroupName = useExistingVNet && !sideBySideDeploy ? varExistingVnetResourceGroupName : _networkResourceGroupName
var _peResourceGroupName = !empty(privateEndpointResourceGroupName) ? privateEndpointResourceGroupName : _defaultPeResourceGroupName
// The explicit RG override historically names a group in the workload subscription.
// Only the implicit BYO fallback follows the VNet's subscription.
var _peSubscriptionId = !empty(privateEndpointResourceGroupName)
  ? subscription().subscriptionId
  : (useExistingVNet && !sideBySideDeploy ? varExistingVnetSubscriptionId : subscription().subscriptionId)
var _peResourceGroupResourceId = '/subscriptions/${_peSubscriptionId}/resourceGroups/${_peResourceGroupName}'
var _applicationPeSubnetId = _networkIsolation ? '${virtualNetworkResourceId}/subnets/${applicationPeSubnetName}' : ''

// ----------------------------------------------------------------------
// VM vars
// ----------------------------------------------------------------------

var _vmBaseName = !empty(vmName) ? vmName : 'testvm${resourceToken}'
var _vmName = substring(_vmBaseName, 0, 15)
var _vmUserName = !empty(vmUserName) ? vmUserName : 'testvmuser'

// ----------------------------------------------------------------------
// Container App vars
// ----------------------------------------------------------------------

var _containerAppsKeyVaultKeysTemp =  [
  for app in containerAppsList: {
    name: '${app.canonical_name}_APIKEY'
    value: resourceToken
    contentType: 'string'
  }
]
var _containerAppsKeyVaultKeys = _useCAppAPIKey && _deployContainerApps && deployKeyVault && deployAppConfig && _runtimeConfigIsAppConfig ? _containerAppsKeyVaultKeysTemp : []

// ----------------------------------------------------------------------
// // Feature-flagging vars 
// ----------------------------------------------------------------------
var _useUAI         = empty(string(useUAI)) ? false : bool(useUAI)
var _useCAppAPIKey  = empty(string(useCAppAPIKey))? false : bool(useCAppAPIKey)
var _containerAppApiKeyPrerequisitesMet = !_useCAppAPIKey || (deployKeyVault && deployAppConfig && _runtimeConfigIsAppConfig)
var _deployContainerApps = deployContainerApps && deployContainerEnv && _containerAppApiKeyPrerequisitesMet

// ----------------------------------------------------------------------
// App runtime configuration mode (Issue #89)
// ----------------------------------------------------------------------
// ``appConfig``     -> existing behavior: App Configuration store is populated
//                       with deployment outputs and Container Apps receive
//                       APP_CONFIG_ENDPOINT + the AppConfigurationDataReader RBAC.
// ``containerEnv``  -> App Configuration population is skipped; Container Apps
//                       receive a curated bootstrap env (tenant, subscription,
//                       RG, location, resource token, network/identity flags
//                       and the names of the deployed resources) so consumers
//                       can resolve everything else through the Azure SDK
//                       without going through App Configuration.
// ``none``          -> Container Apps are deployed with only the identity
//                       bootstrap (AZURE_TENANT_ID, AZURE_CLIENT_ID when UAI);
//                       callers supply runtime configuration through their own
//                       mechanism. Secrets remain on secure params / Key Vault.
var _runtimeConfigIsAppConfig    = appRuntimeConfigurationMode == 'appConfig'
var _runtimeConfigIsContainerEnv = appRuntimeConfigurationMode == 'containerEnv'

//////////////////////////////////////////////////////////////////////////
// RESOURCES
//////////////////////////////////////////////////////////////////////////

// Security
///////////////////////////////////////////////////////////////////////////

// Network Watcher
// Note: Automatically provisioned when network isolation is enabled (VNet deployment)

// Azure Defender for Cloud
// Note: By default, free tier (foundational recommendations) is enabled at the subscription level.
//       To enable its advanced threat protection features, Defender plans must be explicitly configured
//       using the Microsoft.Security/pricings resource (e.g., for Storage, Key Vault, App Services).

// Purview Compliance Manager
// Note: Not applicable, it's part of Microsoft 365 Compliance Center, not Azure Resource Manager.

// Networking
///////////////////////////////////////////////////////////////////////////

// Bastion NSG — restricts inbound 443 to trusted IPs only
module bastionNsg 'modules/networking/bastion-nsg.bicep' = if (_deployBastion && deployNsgs) {
  scope: resourceGroup(_networkResourceGroupName)
  name: 'bastionNsgDeployment'
  params: {
    name: 'nsg-${resourceNames.vnetName}-${azureBastionSubnetName}'
    location: location
    bastionAllowedSourceIPs: bastionAllowedSourceIPs
  }
}

// Public Ingress NSG (#49) — declared in main.bicep because the Application
// Gateway subnet's `networkSecurityGroupResourceId` must be set in the same
// subnet declaration that creates the subnet. Splitting NSG creation out of
// the public-ingress module avoids a circular dependency between the subnet
// and the gateway.
module appGwNsg 'modules/networking/appgw-nsg.bicep' = if (_publicIngressEnabled) {
  scope: resourceGroup(_networkResourceGroupName)
  name: 'appGwNsgDeployment'
  params: {
    name: 'nsg-${resourceNames.vnetName}-${azureAppGatewaySubnetName}'
    location: location
    allowedSourceAddressPrefixes: _publicIngressAllowedSources
  }
}

module aiGatewayNsg 'modules/networking/ai-gateway-nsg.bicep' = if (_networkIsolation && deploySubnets && deployAiGatewaySubnet && deployNsgs) {
  scope: resourceGroup(useExistingVNet ? varExistingVnetSubscriptionId : subscription().subscriptionId, useExistingVNet ? varExistingVnetResourceGroupName : _networkResourceGroupName)
  name: 'aiGatewayNsgDeployment'
  params: {
    name: 'nsg-${useExistingVNet ? varExistingVnetName : resourceNames.vnetName}-${aiGatewaySubnetName}'
    location: location
  }
}

var _deployAcrTaskAgentPool = deployContainerRegistry && _networkIsolation && deployAcrTaskAgentPool

// Public Ingress (#49) — only effective in network-isolated mode with Container
// Apps deployed. The gateway fronts an internal ACA environment, so it is a
// no-op outside that topology.
var _publicIngressEnabled = publicIngress.enabled && _networkIsolation && deployContainerEnv && deployContainerApps && length(containerAppsList) > 0
var _publicIngressBackendIndex = publicIngress.?backendAppIndex ?? 0
var _publicIngressAllowedSources = publicIngress.?allowedSourceAddressPrefixes ?? []

// Route Table for egress traffic control through Azure Firewall (or external NVA, Gap 6).
// Created only when network isolation is on AND no existing RT is provided via
// `hubIntegrationExistingRouteTableResourceId`.
module routeTable 'modules/networking/route-table.bicep' = if (_createRouteTable) {
  scope: resourceGroup(_networkResourceGroupName)
  name: 'routeTableDeployment'
  params: {
    name: '${const.abbrs.networking.routeTable}${resourceToken}'
    location: location
    tags: _tags
  }
}

// One explicit ownership/consumer model for both VNet paths. Creation flags do
// not disable consumers. Reused BYO subnet properties are verified by preflight.
var subnetDefinitions = [
      {
        purpose: 'agent'
        create: deployAgentSubnet
        required: deployAiFoundry && deployAiFoundrySubnet
        name: agentSubnetName
        addressPrefix: agentSubnetPrefix 
        // Issue #110: the serviceName must be the canonical 'Microsoft.App/environments'
        // (capital 'A'). The AVM virtual-network module emits the same string for both
        // the delegation `name` and `properties.serviceName`, and AmlRp's capability
        // host validator does a case-sensitive lookup on `serviceName` when creating
        // `<account>@aml_aiagentservice`. With lowercase 'app', capability host create
        // fails ~47min into provision with "Invalid vnet resource ID provided, or the
        // virtual network could not be found." even though the VNet/subnet are healthy.
        delegation: 'Microsoft.App/environments'
        serviceEndpoints: [
          'Microsoft.CognitiveServices'
        ]
      }
      {
        purpose: 'pe'
        create: deployPeSubnet
        // Cosmos retains service-endpoint ACL references to this subnet.
        required: deployAiFoundry || deployStorageAccount || deploySearchService || deploySpeechService || _deployAiFoundryStorage || _deployAiFoundrySearch || deployCosmosDb
        name: peSubnetName
        addressPrefix: peSubnetPrefix 
        serviceEndpoints: [
          'Microsoft.AzureCosmosDB'
        ]        
        delegation: ''
      }
      {
        purpose: 'gateway'
        create: deployGatewaySubnet
        required: false
        name: gatewaySubnetName
        addressPrefix: gatewaySubnetPrefix 
        delegation: ''
        serviceEndpoints : []
      }
      {
        purpose: 'bastion'
        create: deployAzureBastionSubnet
        required: _deployBastion
        name: azureBastionSubnetName
        addressPrefix: azureBastionSubnetPrefix
        delegation: ''
        serviceEndpoints : []
      }
      {
        purpose: 'firewall'
        create: deployAzureFirewallSubnet
        required: deployAzureFirewall
        name: azureFirewallSubnetName
        addressPrefix: azureFirewallSubnetPrefix 
        delegation: ''
        serviceEndpoints : []
      }
      {
        purpose: 'appGateway'
        create: deployAppGatewaySubnet
        required: _publicIngressEnabled
        name: azureAppGatewaySubnetName
        addressPrefix: azureAppGatewaySubnetPrefix  
        delegation: ''
        serviceEndpoints : []
      }
      {
        purpose: 'jumpbox'
        create: deployJumpboxSubnet
        required: _deployJumpbox
        name: jumpboxSubnetName
        addressPrefix: jumpboxSubnetPrefix 
        delegation: ''
        serviceEndpoints : []
      }
      {
        purpose: 'acaEnvironment'
        create: deployAcaEnvironmentSubnet
        // Cosmos retains this subnet ACL even when Container Apps is disabled.
        required: deployContainerEnv || deployCosmosDb
        name: acaEnvironmentSubnetName
        addressPrefix: acaEnvironmentSubnetPrefix  
        // Match the agent-subnet delegation casing (see comment above). Canonical
        // 'Microsoft.App/environments' avoids any case-sensitive lookup downstream.
        delegation: 'Microsoft.App/environments'
        serviceEndpoints: [
          'Microsoft.AzureCosmosDB'
        ]
      }
      {
        purpose: 'devopsBuildAgents'
        create: deployDevopsBuildAgentsSubnet
        required: _deployAcrTaskAgentPool
        name: devopsBuildAgentsSubnetName
        addressPrefix: devopsBuildAgentsSubnetPrefix 
        delegation: ''
        serviceEndpoints : []
      }
      {
        purpose: 'applicationPe'
        create: deployApplicationPeSubnet
        required: deployCosmosDb || deployKeyVault || deployAppConfig || deployContainerEnv || deployContainerRegistry || _deployAmpls
        name: applicationPeSubnetName
        addressPrefix: applicationPeSubnetPrefix
        serviceEndpoints: ['Microsoft.AzureCosmosDB']
        delegation: ''
      }
      {
        purpose: 'powerPlatform'
        create: deployPowerPlatformSubnet
        required: false
        name: powerPlatformSubnetName
        addressPrefix: powerPlatformSubnetPrefix
        delegation: 'Microsoft.PowerPlatform/enterprisePolicies'
        serviceEndpoints: []
      }
      {
        purpose: 'aiGateway'
        create: deployAiGatewaySubnet
        required: false
        name: aiGatewaySubnetName
        addressPrefix: aiGatewaySubnetPrefix
        delegation: 'Microsoft.Web/serverFarms'
        serviceEndpoints: []
      }
]

var selectedSubnetDefinitions = filter(subnetDefinitions, subnet => _networkIsolation && deploySubnets && subnet.create)
// Only resource properties cross the AVM/child-deployment boundary.
var subnets = map(selectedSubnetDefinitions, subnet => {
  name: subnet.name
  addressPrefix: subnet.addressPrefix
  delegation: subnet.delegation
  serviceEndpoints: subnet.serviceEndpoints
  #disable-next-line BCP318
  networkSecurityGroupResourceId: subnet.purpose == 'bastion' && _deployBastion && deployNsgs ? bastionNsg!.outputs.id : (subnet.purpose == 'appGateway' && _publicIngressEnabled ? appGwNsg!.outputs.id : (subnet.purpose == 'aiGateway' && deployNsgs ? aiGatewayNsg!.outputs.id : ''))
  // GatewaySubnet and both new delegated reservations have no forced-tunnel UDR.
  routeTableResourceId: contains(['agent', 'pe', 'jumpbox', 'acaEnvironment', 'devopsBuildAgents', 'applicationPe'], subnet.purpose) ? _effectiveRouteTableId : ''
  natGatewayResourceId: subnet.purpose == 'jumpbox' ? _effectiveNatGatewayId : ''
})

module networkLayoutValidation 'modules/validation/subnet-layout.bicep' = if (_networkIsolation) {
  name: 'subnetLayoutValidation'
  params: {
    subnetDefinitions: map(subnetDefinitions, subnet => {
      purpose: subnet.purpose
      name: subnet.name
      addressPrefix: subnet.addressPrefix
      create: deploySubnets && subnet.create
      required: subnet.required
    })
    vnetAddressPrefixes: vnetAddressPrefixes
    useExistingVNet: useExistingVNet
    deployNsgs: deployNsgs
  }
}

module virtualNetworkSubnets 'modules/networking/subnets.bicep' = if (_networkIsolation && useExistingVNet && deploySubnets && deployNsgs && !empty(selectedSubnetDefinitions)) {
  name: 'virtualNetworkSubnetsDeployment'
  params: {
    vnetName: useExistingVNet ? varExistingVnetName : resourceNames.vnetName
    location: location
    resourceGroupName: useExistingVNet ? varExistingVnetResourceGroupName : _networkResourceGroupName
    subscriptionId: useExistingVNet ? varExistingVnetSubscriptionId : subscription().subscriptionId
    tags: _tags
    addressPrefixes: vnetAddressPrefixes
    subnets: subnets
    deploySubnets : deploySubnets
    deployNsgs: deployNsgs
    useExistingVNet: useExistingVNet
    virtualNetworkResourceId: virtualNetworkResourceId
  }
  dependsOn: [networkLayoutValidation, componentFlagValidation]
}

// VNet
// Note on IP address sizing: https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/virtual-networks#known-limitations
module virtualNetwork 'br/public:avm/res/network/virtual-network:0.7.0' = if (_networkIsolation && !useExistingVNet) {
  scope: resourceGroup(_networkResourceGroupName)
  name: 'virtualNetworkDeployment'
  params: {
    addressPrefixes: vnetAddressPrefixes
    name: resourceNames.vnetName
    location: location

    tags: _tags
    subnets: subnets
  }
  dependsOn: [networkLayoutValidation]
}

// Gap 7 — Spoke→hub VNet peering.
// Lives under the locally-created spoke VNet; the existing resource
// reference below ensures Bicep can attach the peering as a child without
// the AVM module having to expose a peerings property.
module spokeToHubPeering 'modules/networking/spoke-peering.bicep' = if (_createSpokeToHubPeering) {
  scope: resourceGroup(_networkResourceGroupName)
  name: 'spokeToHubPeeringDeployment'
  params: {
    vnetName: resourceNames.vnetName
    name: 'to-hub-${_hubVnetName}'
    allowGatewayTransit: hubIntegrationPeeringAllowGatewayTransit
    useRemoteGateways: hubIntegrationPeeringUseRemoteGateways
    hubVnetResourceId: hubIntegrationHubVnetResourceId!
  }
  dependsOn: [
    virtualNetwork
  ]
}

// Bastion Host
// Bastion Host — replaced the AVM `bastion-host` module with a raw resource so
// `enableTunneling` can be set (the AVM module up to 0.8.2 does not expose it).
// Native-client tunneling is required for `az network bastion rdp/ssh`, RDP
// audio/clipboard/device redirection, and SSH agent forwarding from inside the
// spoke. Behavior-equivalent to the previous module call: same subnet
// (AzureBastionSubnet), Standard static PIP, optional zone redundancy, tags.
module testVmBastionHost 'modules/networking/bastion.bicep' = if (_deployBastion) {
  scope: resourceGroup(_networkResourceGroupName)
  name: 'bastionDeployment'
  params: {
    name: '${const.abbrs.security.bastion}testvm-${resourceToken}'
    publicIpName: '${const.abbrs.networking.publicIPAddress}bastion-${resourceToken}'
    location: location
    tags: _tags
    skuName: bastionSkuName
    useZoneRedundancy: useZoneRedundancy
    enableTunneling: bastionEnableTunneling
    subnetResourceId: '${virtualNetworkResourceId}/subnets/${azureBastionSubnetName}'
  }
  dependsOn: [
    #disable-next-line BCP321
    !useExistingVNet ? virtualNetwork : null
    #disable-next-line BCP321
    useExistingVNet ? virtualNetworkSubnets : null
  ]
}

// Azure Firewall for egress traffic control
///////////////////////////////////////////////////////////////////////////

module firewall 'modules/networking/azure-firewall.bicep' = {
  scope: resourceGroup(_networkResourceGroupName)
  name: 'firewall'
  params: {
    deployAzureFirewall: deployAzureFirewall
    enableFirewallDnsProxy: enableFirewallDnsProxy
    networkIsolation: _networkIsolation
    enableAcsMediaEgress: enableAcsMediaEgress
    deploySpeechService: deploySpeechService
    deployAcrTaskAgentPool: _deployAcrTaskAgentPool
    extendFirewallForJumpboxBootstrap: extendFirewallForJumpboxBootstrap
    extendFirewallForAcrTaskBuilds: extendFirewallForAcrTaskBuilds
    additionalAcrTaskBuildFqdns: additionalAcrTaskBuildFqdns
    resourceToken: resourceToken
    location: location
    tags: _tags
    virtualNetworkResourceId: virtualNetworkResourceId
    azureFirewallSubnetName: azureFirewallSubnetName
    jumpboxSubnetPrefix: jumpboxSubnetPrefix
    devopsBuildAgentsSubnetPrefix: devopsBuildAgentsSubnetPrefix
    acaEnvironmentSubnetPrefix: acaEnvironmentSubnetPrefix
    agentSubnetPrefix: agentSubnetPrefix
    hasEffectiveLaw: _hasEffectiveLaw
    lawResourceId: _lawResourceId
  }
  dependsOn: [
    #disable-next-line BCP321
    !useExistingVNet ? virtualNetwork : null
    #disable-next-line BCP321
    useExistingVNet ? virtualNetworkSubnets : null
  ]
}

// Default route through Azure Firewall (local) or external NVA/hub firewall (Gap 6).
// Skipped entirely when the operator brings their own Route Table via
// `hubIntegrationExistingRouteTableResourceId` (we don't write into a foreign RT).
module defaultRoute 'modules/networking/default-route.bicep' = if (_createDefaultRoute) {
  scope: resourceGroup(_networkResourceGroupName)
  name: 'defaultRouteDeployment'
  params: {
    routeTableName: '${const.abbrs.networking.routeTable}${resourceToken}'
    nextHopIpAddress: _defaultRouteNextHopIp
  }
  #disable-next-line no-unnecessary-dependson
  dependsOn: [routeTable]
}

//Test VM User Managed Identity
module testVmUAI 'modules/security/managed-identity.bicep' = if (_useUAI) {
  scope: resourceGroup(_networkResourceGroupName)
  name: 'testVmIdentityDeployment'
  params: {
    name: '${const.abbrs.security.managedIdentity}${_vmName}'
    location: location
  }
}

// Test VM
module testVm 'br/public:avm/res/compute/virtual-machine:0.15.0' = if (_deployJumpbox) {
  scope: resourceGroup(_networkResourceGroupName)
  name: 'testVmDeployment'
  params: {
    name: _vmName
    location: location
    adminUsername: _vmUserName
    adminPassword: vmAdminPassword
    managedIdentities: {
      systemAssigned: _useUAI ? false : true
      #disable-next-line BCP318
      userAssignedResourceIds: _useUAI ? [testVmUAI.outputs.resourceId] : []
    }
    imageReference: {
      publisher: vmImagePublisher
      offer:     vmImageOffer
      sku:       vmImageSku
      version:   vmImageVersion
    }
    encryptionAtHost: false 
    vmSize: vmSize
    osDisk: {
      caching: 'ReadWrite'
      diskSizeGB: 250
      managedDisk: {
        storageAccountType: 'Standard_LRS'
      }
      
    }
    osType: 'Windows'
    zone: 0
    nicConfigurations: [
      {
        nicSuffix: '-nic-01'
        ipConfigurations: [
          {
            name: 'ipconfig01'
            #disable-next-line BCP318
            subnetResourceId: _jumpbxSubnetId
          }
        ]
      }
    ]
  }
  dependsOn: [
    testVmBastionHost
    #disable-next-line BCP321
    !useExistingVNet ? virtualNetwork : null
    #disable-next-line BCP321
    useExistingVNet ? virtualNetworkSubnets : null
  ]
}

module natGateway 'modules/networking/nat-gateway.bicep' = if (_deployNatGateway) {
  scope: resourceGroup(_networkResourceGroupName)
  name: 'natGatewayDeployment'
  params: {
    name: '${const.abbrs.networking.natGateway}${resourceToken}'
    publicIpName: '${const.abbrs.networking.publicIPAddress}${const.abbrs.networking.natGateway}${resourceToken}'
    location: location
    tags: _tags
  }
}

// ---------------------------------------------------------------------------
// TestVM role assignments (consolidated into a single array-driven module call
// to keep the compiled ARM template under the 4 MB deployment limit).
// ---------------------------------------------------------------------------
var _testVmPrincipalId = _deployJumpbox
  #disable-next-line BCP318
  ? (_useUAI ? testVmUAI.outputs.principalId : testVm.outputs.systemAssignedMIPrincipalId!)
  : ''

var _testVmDestinationReaderRoles = map(union(
  toLower(_applicationResourceGroupName) == toLower(resourceGroup().name) ? [] : [toLower(_applicationResourceGroupName)],
  toLower(_networkResourceGroupName) == toLower(resourceGroup().name) ? [] : [toLower(_networkResourceGroupName)]
), destination => {
  roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.Reader.guid)
  principalId: _testVmPrincipalId
  resourceId: '/subscriptions/${subscription().subscriptionId}/resourceGroups/${destination}'
  principalType: 'ServicePrincipal'
})

var _testVmRoles = _deployJumpbox ? concat(
  [
    // Reader on the resource group itself so the jumpbox SAMI can enumerate
    // ARM resources from inside the VNet (`az resource list`,
    // `az cosmosdb list`, `az containerapp list`, …). Required by consumer
    // postProvision / data-seed scripts that resolve resource names by
    // discovery when env vars / App Config values are missing or the script
    // is being run interactively for troubleshooting. Without this, every
    // ARM list call returns `[]` even though the SAMI already has the
    // data-plane roles needed for the actual operations. Scoped to the
    // resource group (empty `resourceId` => deployment scope, which is RG).
    {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.Reader.guid)
      principalId: _testVmPrincipalId
      resourceId: ''
      principalType: 'ServicePrincipal'
    }
  ],
  _testVmDestinationReaderRoles,
  (deployAppConfig && deployContainerRegistry) ? [
    {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.ContainerAppsContributor.guid)
      principalId: _testVmPrincipalId
      resourceId: ''
      principalType: 'ServicePrincipal'
    }
    {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.ManagedIdentityOperator.guid)
      principalId: _testVmPrincipalId
      resourceId: ''
      principalType: 'ServicePrincipal'
    }
    {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.ContainerRegistryRepositoryWriter.guid)
      principalId: _testVmPrincipalId
      #disable-next-line BCP318
      resourceId: containerRegistry.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
    {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.ContainerRegistryContributorDataAccessConfigurationAdministrator.guid)
      principalId: _testVmPrincipalId
      #disable-next-line BCP318
      resourceId: containerRegistry.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
    {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.ContainerRegistryTasksContributor.guid)
      principalId: _testVmPrincipalId
      #disable-next-line BCP318
      resourceId: containerRegistry.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
  ] : [],
  deployAppConfig ? [
    {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.AppConfigurationDataOwner.guid)
      principalId: _testVmPrincipalId
      #disable-next-line BCP318
      resourceId: appConfig.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
  ] : [],
  deployContainerRegistry ? [
    {
      principalId: _testVmPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.AcrPush.guid)
      #disable-next-line BCP318
      resourceId: containerRegistry.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
  ] : [],
  deployKeyVault ? [
    {
      principalId: _testVmPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.KeyVaultContributor.guid)
      #disable-next-line BCP318
      resourceId: keyVault.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
    {
      principalId: _testVmPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.KeyVaultSecretsOfficer.guid)
      #disable-next-line BCP318
      resourceId: keyVault.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
    {
      principalId: _testVmPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.KeyVaultCertificatesOfficer.guid)
      #disable-next-line BCP318
      resourceId: keyVault.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
  ] : [],
  deploySearchService ? [
    {
      principalId: _testVmPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.SearchServiceContributor.guid)
      #disable-next-line BCP318
      resourceId: searchService.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
    {
      principalId: _testVmPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.SearchIndexDataContributor.guid)
      #disable-next-line BCP318
      resourceId: searchService.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
  ] : [],
  deployAiFoundry ? [
    {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.CognitiveServicesContributor.guid)
      principalId: _testVmPrincipalId
      resourceId: aiFoundryAccountResourceId
      principalType: 'ServicePrincipal'
    }
    {
      principalId: _testVmPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.CognitiveServicesOpenAIUser.guid)
      resourceId: aiFoundryAccountResourceId
      principalType: 'ServicePrincipal'
    }
  ] : [],
  deploySpeechService ? [
    {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.CognitiveServicesContributor.guid)
      principalId: _testVmPrincipalId
      #disable-next-line BCP318
      resourceId: speechService.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
    {
      principalId: _testVmPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.CognitiveServicesUser.guid)
      #disable-next-line BCP318
      resourceId: speechService.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
  ] : [],
  deployStorageAccount ? [
    {
      principalId: _testVmPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.StorageBlobDataContributor.guid)
      #disable-next-line BCP318
      resourceId: storageAccount.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
  ] : []
) : []

module assignTestVmRoles 'modules/security/resource-role-assignment.bicep' = if (_deployJumpbox) {
  name: 'assignTestVmRoles'
  params: {
    name: 'assignTestVmRoles'
    roleAssignments: _testVmRoles
  }
}

// Cosmos DB Account - Cosmos DB Built-in Data Contributor -> TestVm
module assignCosmosDBCosmosDbBuiltInDataContributorTestVm 'modules/security/cosmos-data-plane-role-assignment.bicep' = if (_deployJumpbox && deployCosmosDb) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'assignCosmosDBCosmosDbBuiltInDataContributorTestVm'
  params: {
    #disable-next-line BCP318
    cosmosDbAccountName: cosmosDBAccount.outputs.name
    principalId: _testVmPrincipalId
    roleDefinitionGuid: const.roles.CosmosDBBuiltInDataContributor.guid
    scopePath: '/subscriptions/${subscription().subscriptionId}/resourceGroups/${_applicationResourceGroupName}/providers/Microsoft.DocumentDB/databaseAccounts/${resourceNames.dbAccountName}'
  }
}

var _fileUris = [
  'https://raw.githubusercontent.com/Azure/bicep-ptn-aiml-landing-zone/refs/tags/${_infraSourceTag}/install.ps1'
]

// Windows CustomScriptExtension has a FIXED 90-minute platform provisioning
// timeout (`VMExtensionProvisioningTimeout`) that cannot be extended from the
// extension definition — there is no supported `timeout` setting here. Under
// Zero Trust all jumpbox egress traverses the Azure Firewall, so package feeds
// and external downloads can be slow or transiently blocked. `install.ps1` is
// therefore self-limiting: it caps every network operation and tracks an
// overall wall-clock budget (~75 min) so it always reports a terminal status
// before the 90-minute cap, skipping OPTIONAL steps (Python, win-acme,
// component/extra repos) under low budget while keeping CORE steps fatal. See
// issue #82. NOTE: this script is fetched from the tag pinned in
// `manifest.json#infra.source.tag` (and passed as `-release`), so a fix to
// install.ps1 only takes effect once a new tag containing it is published AND
// `infra.source.tag` is bumped to that tag.
module cse 'modules/networking/jumpbox-extension.bicep' = if (_deployJumpbox && deploySoftware) {
  scope: resourceGroup(_networkResourceGroupName)
  name: 'jumpboxExtensionDeployment'
  params: {
    vmName: _vmName
    location: location
    forceUpdateTag: deployment().name
    fileUris: _fileUris
    commandToExecute: 'powershell.exe -ExecutionPolicy Unrestricted -File install.ps1 -release ${_infraSourceTag} -UseUAI ${_useUAI} -ResourceToken ${resourceToken} -AzureTenantId ${subscription().tenantId} -AzureLocation ${location} -AzureSubscriptionId ${subscription().subscriptionId} -AzureResourceGroupName ${resourceGroup().name} -AzdEnvName ${environmentName} -ExtraRepoUrls "${join(_extraRepoUrls, ',')}" -ExtraRepoTags "${join(_extraRepoTags, ',')}" -ExtraRepoNames "${join(_extraRepoNames, ',')}"'
  }
  dependsOn: [
    testVm
    appConfigPopulate
    assignTestVmRoles
    assignCosmosDBCosmosDbBuiltInDataContributorTestVm
    firewall
  ]
}

// Private DNS Zones (consolidated into a single for-loop module to keep compiled ARM template under 4 MB).
///////////////////////////////////////////////////////////////////////////

var _dnsZonesTargetRg = useExistingVNet && !sideBySideDeploy ? varExistingVnetResourceGroupName : _networkResourceGroupName
var _dnsZonesLinkSuffix = '${useExistingVNet ? '-byon' : ''}${empty(dnsZoneLinkSuffix) ? '' : '-${dnsZoneLinkSuffix}'}'

// Gap 2 — Per-zone BYO flags (true ⇒ skip local creation for that zone).
var _byoZoneCogSvcs        = !empty(existingPrivateDnsZoneCogSvcsResourceId ?? '')
var _byoZoneOpenAi         = !empty(existingPrivateDnsZoneOpenAiResourceId ?? '')
var _byoZoneAiServices     = !empty(existingPrivateDnsZoneAiServicesResourceId ?? '')
var _byoZoneSearch         = !empty(existingPrivateDnsZoneSearchResourceId ?? '')
var _byoZoneCosmos         = !empty(existingPrivateDnsZoneCosmosResourceId ?? '')
var _byoZoneBlob           = !empty(existingPrivateDnsZoneBlobResourceId ?? '')
var _byoZoneKeyVault       = !empty(existingPrivateDnsZoneKeyVaultResourceId ?? '')
var _byoZoneAppConfig      = !empty(existingPrivateDnsZoneAppConfigResourceId ?? '')
var _byoZoneContainerApps  = !empty(existingPrivateDnsZoneContainerAppsResourceId ?? '')
var _byoZoneAcr            = !empty(existingPrivateDnsZoneAcrResourceId ?? '')
var _byoZoneAppInsights    = !empty(existingPrivateDnsZoneAppInsightsResourceId ?? '')
var _byoZoneAzureMonitor   = !empty(existingPrivateDnsZoneAzureMonitorResourceId ?? '')
var _byoZoneOmsOpInsights  = !empty(existingPrivateDnsZoneOmsOpsInsightsResourceId ?? '')
var _byoZoneOdsOpInsights  = !empty(existingPrivateDnsZoneOdsOpsInsightsResourceId ?? '')
var _byoZoneAzureAutomation= !empty(existingPrivateDnsZoneAzureAutomationResourceId ?? '')

var _dnsZonesList = _deployPrivateDnsZones ? concat(
  _byoZoneCogSvcs       ? [] : [ { dnsName: 'privatelink.cognitiveservices.azure.com', virtualNetworkLinkName: '${resourceNames.vnetName}-cogsvcs-link${_dnsZonesLinkSuffix}' } ],
  _byoZoneOpenAi        ? [] : [ { dnsName: 'privatelink.openai.azure.com',            virtualNetworkLinkName: '${resourceNames.vnetName}-openai-link${_dnsZonesLinkSuffix}' } ],
  _byoZoneAiServices    ? [] : [ { dnsName: 'privatelink.services.ai.azure.com',       virtualNetworkLinkName: '${resourceNames.vnetName}-aiservices-link${_dnsZonesLinkSuffix}' } ],
  _byoZoneSearch        ? [] : [ { dnsName: 'privatelink.search.windows.net',          virtualNetworkLinkName: '${resourceNames.vnetName}-search-std-link${_dnsZonesLinkSuffix}' } ],
  _byoZoneCosmos        ? [] : [ { dnsName: 'privatelink.documents.azure.com',         virtualNetworkLinkName: '${resourceNames.vnetName}-cosmos-std-link${_dnsZonesLinkSuffix}' } ],
  _byoZoneBlob          ? [] : [ { dnsName: 'privatelink.blob.${environment().suffixes.storage}', virtualNetworkLinkName: '${resourceNames.vnetName}-blob-std-link${_dnsZonesLinkSuffix}' } ],
  _byoZoneKeyVault      ? [] : [ { dnsName: 'privatelink.vaultcore.azure.net',         virtualNetworkLinkName: '${resourceNames.vnetName}-kv-link${_dnsZonesLinkSuffix}' } ],
  _byoZoneAppConfig     ? [] : [ { dnsName: 'privatelink.azconfig.io',                 virtualNetworkLinkName: '${resourceNames.vnetName}-appcfg-link${_dnsZonesLinkSuffix}' } ],
  (deployContainerEnv && !_byoZoneContainerApps) ? [
    { dnsName: 'privatelink.${location}.azurecontainerapps.io', virtualNetworkLinkName: '${resourceNames.vnetName}-containerapps-link${_dnsZonesLinkSuffix}' }
  ] : [],
  (deployContainerRegistry && !_byoZoneAcr) ? [
    { dnsName: 'privatelink.${acrDnsSuffix}',                         virtualNetworkLinkName: '${resourceNames.vnetName}-containerregistry-link${_dnsZonesLinkSuffix}' }
  ] : [],
  _deployAmpls ? concat(
    _byoZoneAppInsights     ? [] : [ { dnsName: 'privatelink.applicationinsights.io',      virtualNetworkLinkName: '${resourceNames.vnetName}-appi-link${_dnsZonesLinkSuffix}' } ],
    _byoZoneAzureMonitor    ? [] : [ { dnsName: 'privatelink.monitor.azure.com',           virtualNetworkLinkName: '${resourceNames.vnetName}-azure-monitor-link${_dnsZonesLinkSuffix}' } ],
    _byoZoneOmsOpInsights   ? [] : [ { dnsName: 'privatelink.oms.opinsights.azure.com',    virtualNetworkLinkName: '${resourceNames.vnetName}-oms-opinsights-link${_dnsZonesLinkSuffix}' } ],
    _byoZoneOdsOpInsights   ? [] : [ { dnsName: 'privatelink.ods.opinsights.azure.com',    virtualNetworkLinkName: '${resourceNames.vnetName}-ods-opinsights-link${_dnsZonesLinkSuffix}' } ],
    _byoZoneAzureAutomation ? [] : [ { dnsName: 'privatelink.agentsvc.azure.automation.net', virtualNetworkLinkName: '${resourceNames.vnetName}-azure-automation-link${_dnsZonesLinkSuffix}' } ]
  ) : []
) : []

module privateDnsZones 'modules/networking/private-dns-zones.bicep' = if (_deployPrivateDnsZones && !empty(_dnsZonesList)) {
  name: 'dep-private-dns-zones'
  params: {
    zones: _dnsZonesList
    tags: _tags
    resourceGroupName: _dnsZonesTargetRg
    subscriptionId: _dnsZonesSubscriptionId
    virtualNetworkResourceId: virtualNetworkResourceId
  }
  dependsOn: [
    virtualNetwork!
    virtualNetworkSubnets!
  ]
}

// Private Endpoints (consolidated into a single for-loop module with @batchSize(1) to keep compiled ARM template under 4 MB while preserving serialized PE creation).
///////////////////////////////////////////////////////////////////////////

var _peDnsZoneGroups = {
  blob: policyManagedPrivateDns ? null : {
    name: 'blobDnsZoneGroup'
    privateDnsZoneGroupConfigs: [
      { name: 'blobARecord', privateDnsZoneResourceId: _dnsZoneBlobId }
    ]
  }
  cosmos: policyManagedPrivateDns ? null : {
    name: 'cosmosDnsZoneGroup'
    privateDnsZoneGroupConfigs: [
      { name: 'cosmosARecord', privateDnsZoneResourceId: _dnsZoneCosmosId }
    ]
  }
  search: policyManagedPrivateDns ? null : {
    name: 'searchDnsZoneGroup'
    privateDnsZoneGroupConfigs: [
      { name: 'searchARecord', privateDnsZoneResourceId: _dnsZoneSearchId }
    ]
  }
  keyVault: policyManagedPrivateDns ? null : {
    name: 'kvDnsZoneGroup'
    privateDnsZoneGroupConfigs: [
      { name: 'kvARecord', privateDnsZoneResourceId: _dnsZoneKeyVaultId }
    ]
  }
  appConfig: policyManagedPrivateDns ? null : {
    name: 'appConfigDnsZoneGroup'
    privateDnsZoneGroupConfigs: [
      { name: 'appConfigARecord', privateDnsZoneResourceId: _dnsZoneAppConfigId }
    ]
  }
  containerApps: policyManagedPrivateDns ? null : {
    name: 'ccaDnsZoneGroup'
    privateDnsZoneGroupConfigs: [
      { name: 'ccaARecord', privateDnsZoneResourceId: _dnsZoneContainerAppsId }
    ]
  }
  acr: policyManagedPrivateDns ? null : {
    name: 'acrDnsZoneGroup'
    privateDnsZoneGroupConfigs: [
      { name: 'acr', privateDnsZoneResourceId: _dnsZoneAcrId }
    ]
  }
  cognitiveServices: policyManagedPrivateDns ? null : {
    name: 'cogSvcsDnsZoneGroup'
    privateDnsZoneGroupConfigs: [
      { name: 'cogSvcsARecord', privateDnsZoneResourceId: _dnsZoneCogSvcsId }
    ]
  }
}

var _peList = concat(
  (_networkIsolation && deployStorageAccount) ? [
    {
      name: '${const.abbrs.networking.privateEndpoint}${resourceNames.storageAccountName}'
      privateLinkServiceConnections: [
        {
          name: 'blobConnection${useExistingVNet?'-byon':''}'
          #disable-next-line BCP318
          properties: { privateLinkServiceId: storageAccount.outputs.resourceId, groupIds: ['blob'] }
        }
      ]
      privateDnsZoneGroup: _peDnsZoneGroups.?blob
    }
  ] : [],
  (_networkIsolation && deployCosmosDb) ? [
    {
      name: '${const.abbrs.networking.privateEndpoint}${resourceNames.dbAccountName}'
      subnetResourceId: _applicationPeSubnetId
      privateLinkServiceConnections: [
        {
          name: 'cosmosConnection${useExistingVNet?'-byon':''}'
          #disable-next-line BCP318
          properties: { privateLinkServiceId: cosmosDBAccount.outputs.resourceId, groupIds: ['Sql'] }
        }
      ]
      privateDnsZoneGroup: _peDnsZoneGroups.?cosmos
    }
  ] : [],
  (_networkIsolation && deploySearchService) ? [
    {
      name: '${const.abbrs.networking.privateEndpoint}${resourceNames.searchServiceName}'
      privateLinkServiceConnections: [
        {
          name: 'searchConnection${useExistingVNet?'-byon':''}'
          #disable-next-line BCP318
          properties: { privateLinkServiceId: searchService.outputs.resourceId, groupIds: ['searchService'] }
        }
      ]
      privateDnsZoneGroup: _peDnsZoneGroups.?search
    }
  ] : [],
  (_networkIsolation && _deployAiFoundrySearch) ? [
    {
      name: '${const.abbrs.networking.privateEndpoint}${resourceNames.aiFoundrySearchServiceName}'
      privateLinkServiceConnections: [
        {
          name: 'searchAIFConnection${useExistingVNet?'-byon':''}'
          #disable-next-line BCP318
          properties: { privateLinkServiceId: searchServiceAIFoundry.outputs.resourceId, groupIds: ['searchService'] }
        }
      ]
      privateDnsZoneGroup: _peDnsZoneGroups.?search
    }
  ] : [],
  (_networkIsolation && deployKeyVault) ? [
    {
      name: '${const.abbrs.networking.privateEndpoint}${resourceNames.keyVaultName}'
      subnetResourceId: _applicationPeSubnetId
      privateLinkServiceConnections: [
        {
          name: 'kvConnection${useExistingVNet?'-byon':''}'
          #disable-next-line BCP318
          properties: { privateLinkServiceId: keyVault.outputs.resourceId, groupIds: ['vault'] }
        }
      ]
      privateDnsZoneGroup: _peDnsZoneGroups.?keyVault
    }
  ] : [],
  (_networkIsolation && deployAppConfig) ? [
    {
      name: '${const.abbrs.networking.privateEndpoint}${resourceNames.appConfigName}'
      subnetResourceId: _applicationPeSubnetId
      privateLinkServiceConnections: [
        {
          name: 'appConfigConnection${useExistingVNet?'-byon':''}'
          #disable-next-line BCP318
          properties: { privateLinkServiceId: appConfig.outputs.resourceId, groupIds: ['configurationStores'] }
        }
      ]
      privateDnsZoneGroup: _peDnsZoneGroups.?appConfig
    }
  ] : [],
  (_networkIsolation && deployContainerEnv) ? [
    {
      name: '${const.abbrs.networking.privateEndpoint}${resourceNames.containerEnvName}'
      subnetResourceId: _applicationPeSubnetId
      privateLinkServiceConnections: [
        {
          name: 'ccaConnection'
          #disable-next-line BCP318
          properties: { privateLinkServiceId: containerEnv.outputs.resourceId, groupIds: ['managedEnvironments'] }
        }
      ]
      privateDnsZoneGroup: _peDnsZoneGroups.?containerApps
    }
  ] : [],
  (_networkIsolation && deployContainerRegistry) ? [
    {
      name: '${const.abbrs.networking.privateEndpoint}${resourceNames.containerRegistryName}'
      subnetResourceId: _applicationPeSubnetId
      privateLinkServiceConnections: [
        {
          name: '${resourceNames.containerRegistryName}-registry-connection'
          #disable-next-line BCP318
          properties: { privateLinkServiceId: containerRegistry.outputs.resourceId, groupIds: ['registry'] }
        }
      ]
      privateDnsZoneGroup: _peDnsZoneGroups.?acr
    }
  ] : [],
  (_networkIsolation && deploySpeechService) ? [
    {
      name: '${const.abbrs.networking.privateEndpoint}${resourceNames.speechServiceName}'
      privateLinkServiceConnections: [
        {
          name: 'speechConnection${useExistingVNet?'-byon':''}'
          #disable-next-line BCP318
          properties: { privateLinkServiceId: speechService.outputs.resourceId, groupIds: ['account'] }
        }
      ]
      privateDnsZoneGroup: _peDnsZoneGroups.?cognitiveServices
    }
  ] : []
)

module privateEndpoints 'modules/networking/private-endpoints.bicep' = if (_networkIsolation) {
  name: 'dep-private-endpoints'
  params: {
    endpoints: _peList
    location: _peLocation
    resourceGroupName: _peResourceGroupName
    subscriptionId: _peSubscriptionId
    tags: _tags
    subnetResourceId: _peSubnetId
  }
  dependsOn: [
    privateDnsZones
    storageAccount!
    cosmosDBAccount!
    searchService!
    #disable-next-line BCP321
    _deployAiFoundrySearch ? searchServiceAIFoundry : null
    keyVault!
    appConfig!
    containerEnv!
    containerRegistry!
    speechService!
  ]
}


// Azure Application Gateway
//////////////////////////////////////////////////////////////////////////
// Coming Soon

// Azure Firewall
//////////////////////////////////////////////////////////////////////////
// Coming Soon

// AI Foundry Standard Setup
//////////////////////////////////////////////////////////////////////////


var _dnsZonesSubscriptionId = useExistingVNet && !sideBySideDeploy ? varExistingVnetSubscriptionId : subscription().subscriptionId
var _dnsZonesResourceGroupName = useExistingVNet && !sideBySideDeploy ? varExistingVnetResourceGroupName : _networkResourceGroupName
var _dnsZoneCogSvcsId         = !empty(existingPrivateDnsZoneCogSvcsResourceId ?? '')         ? existingPrivateDnsZoneCogSvcsResourceId!         : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.cognitiveservices.azure.com')
var _dnsZoneOpenAiId          = !empty(existingPrivateDnsZoneOpenAiResourceId ?? '')          ? existingPrivateDnsZoneOpenAiResourceId!          : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.openai.azure.com')
var _dnsZoneAiServicesId      = !empty(existingPrivateDnsZoneAiServicesResourceId ?? '')      ? existingPrivateDnsZoneAiServicesResourceId!      : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.services.ai.azure.com')
var _dnsZoneSearchId          = !empty(existingPrivateDnsZoneSearchResourceId ?? '')          ? existingPrivateDnsZoneSearchResourceId!          : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.search.windows.net')
var _dnsZoneCosmosId          = !empty(existingPrivateDnsZoneCosmosResourceId ?? '')          ? existingPrivateDnsZoneCosmosResourceId!          : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.documents.azure.com')
var _dnsZoneBlobId            = !empty(existingPrivateDnsZoneBlobResourceId ?? '')            ? existingPrivateDnsZoneBlobResourceId!            : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.blob.${environment().suffixes.storage}')
var _dnsZoneKeyVaultId        = !empty(existingPrivateDnsZoneKeyVaultResourceId ?? '')        ? existingPrivateDnsZoneKeyVaultResourceId!        : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.vaultcore.azure.net')
var _dnsZoneAppConfigId       = !empty(existingPrivateDnsZoneAppConfigResourceId ?? '')       ? existingPrivateDnsZoneAppConfigResourceId!       : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.azconfig.io')
var _dnsZoneContainerAppsId   = !empty(existingPrivateDnsZoneContainerAppsResourceId ?? '')   ? existingPrivateDnsZoneContainerAppsResourceId!   : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.${location}.azurecontainerapps.io')
var _dnsZoneAcrId             = !empty(existingPrivateDnsZoneAcrResourceId ?? '')             ? existingPrivateDnsZoneAcrResourceId!             : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.${acrDnsSuffix}')
var _dnsZoneAzureMonitorId    = !empty(existingPrivateDnsZoneAzureMonitorResourceId ?? '')    ? existingPrivateDnsZoneAzureMonitorResourceId!    : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.monitor.azure.com')
var _dnsZoneOmsOpsInsightsId  = !empty(existingPrivateDnsZoneOmsOpsInsightsResourceId ?? '')  ? existingPrivateDnsZoneOmsOpsInsightsResourceId!  : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.oms.opinsights.azure.com')
var _dnsZoneOdsOpsInsightsId  = !empty(existingPrivateDnsZoneOdsOpsInsightsResourceId ?? '')  ? existingPrivateDnsZoneOdsOpsInsightsResourceId!  : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.ods.opinsights.azure.com')
var _dnsZoneAzureAutomationId = !empty(existingPrivateDnsZoneAzureAutomationResourceId ?? '') ? existingPrivateDnsZoneAzureAutomationResourceId! : resourceId(_dnsZonesSubscriptionId, _dnsZonesResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.agentsvc.azure.automation.net')

//AI Foundry Account User Managed Identity
module aiFoundryUAI 'modules/security/managed-identity.bicep' = if (_useUAI) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'foundryIdentityDeployment'
  params: {
    name: '${const.abbrs.security.managedIdentity}${resourceNames.aiFoundryAccountName}'
    location: location
  }
}

// 16.0 AI Foundry account creation is delegated entirely to the customized
// derivation of avm/ptn/ai-ml/ai-foundry@0.6.0 maintained at
// `modules/ai-foundry/foundry/`. The customized `account.bicep` therein
// splits account creation from private-endpoint creation and adds an
// explicit deploymentScript wait on `provisioningState == Succeeded`, which
// closes the race the previous pre-create workaround tried (and failed) to
// mask via property-matching. See issues #25, #26, #27 for the full history.

// Pre-create AI Foundry Storage Account with a region-safe SKU.
// The AVM ai-foundry module (<= 0.6.0) creates its Storage Account with the
// provider default `Standard_GRS`, which is not offered in every region
// (e.g. Poland Central -> RedundancyConfigurationNotAvailableInRegion).
// Creating it ourselves and passing the resource ID as `existingResourceId`
// lets us honor an explicit SKU (default `Standard_LRS`).
module aiFoundryStorageAccount 'modules/ai-foundry/storage-account.bicep' = if (_deployAiFoundryStorage) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'aiFoundryStorage-${resourceToken}-deployment'
  params: {
    name: resourceNames.aiFoundryStorageAccountName
    location: location
    tags: _tags
    skuName: aiFoundryStorageSku
    disablePublicNetworkAccess: _networkIsolation
    allowedIpRanges: allowedIpRanges
    privateEndpointSubnetResourceId: _networkIsolation ? _peSubnetId : ''
    privateEndpointResourceGroupResourceId: _peResourceGroupResourceId
    privateEndpointLocation: _peLocation
    blobPrivateDnsZoneResourceId: (_networkIsolation && !policyManagedPrivateDns) ? _dnsZoneBlobId : ''
  }
  dependsOn: [
    #disable-next-line BCP321
    (_networkIsolation && !useExistingVNet) ? virtualNetwork : null
    #disable-next-line BCP321
    (_networkIsolation && useExistingVNet && deploySubnets && deployNsgs) ? virtualNetworkSubnets : null
    #disable-next-line BCP321
    (_networkIsolation && !policyManagedPrivateDns) ? privateDnsZones : null
    // `privateEndpoints` module creates ~10 PEs against `pe-subnet` (already serialized
    // internally via @batchSize(1)). This module also creates an inline blob PE on the
    // same subnet via the AVM storage-account module's `privateEndpoints` parameter.
    // Without this dependsOn, the inline PE NIC and the aggregator's PE NICs race the
    // subnet update and ARM intermittently fails one of them with
    // `ReferencedResourceNotProvisioned`.
    #disable-next-line BCP321
    _networkIsolation ? privateEndpoints : null
  ]
}


// 16.1 AI Foundry Configuration
module aiFoundry 'modules/ai-foundry/main.bicep' = if (deployAiFoundry) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'aiFoundryDeployment'
  params: {
    // Required
    baseName: substring(resourceToken, 0, 10)
    baseUniqueName: substring(uniqueString(subscription().id, resourceGroup().name, substring(resourceToken, 0, 10)), 0, 5)

    includeAssociatedResources: _deployAiFoundryAgentService
    location: location
    tags: deploymentTags

    // Gate this on `_networkIsolation` to mirror the sibling `aiFoundryStorageAccount`
    // module at L2220. When network isolation is off, the spoke VNet is not deployed,
    // `virtualNetworkResourceId` resolves to '', and `varPeSubnetId` collapses to the
    // bogus literal '/subnets/pe-subnet'. Passing that down to the four AI Foundry-
    // bundled sub-modules (Cosmos, Key Vault, AI Search, Storage) makes each one's
    // `privateNetworkingEnabled = !empty(privateEndpointSubnetResourceId)` evaluate
    // true (the string is non-empty but invalid), and ARM template validation fails
    // with `databaseAccount_privateEndpoints[0]` / `keyVault_privateEndpoints[0]` ...
    // `'reference' is not valid: all function arguments should be string literals.`.
    // See issue #63 for the full diagnosis.
    privateEndpointSubnetResourceId: _networkIsolation ? _peSubnetId : ''
    privateEndpointResourceGroupResourceId: _peResourceGroupResourceId
    privateEndpointLocation: _peLocation

    aiFoundryConfiguration: {
      accountName: resourceNames.aiFoundryAccountName
      allowProjectManagement: deployAfProject
      createCapabilityHosts: _deployAiFoundryAgentService
      disableLocalAuth: aiFoundryDisableLocalAuth
      location: location

      networking: varAfNetworkingOverride

      project: deployAfProject
        ? {
            name: resourceNames.aiFoundryProjectName
            displayName: empty(aiFoundryProjectDisplayName) ? resourceNames.aiFoundryProjectName : aiFoundryProjectDisplayName!
            description: empty(aiFoundryProjectDescription) ? 'This is the default project for AI Foundry.' : aiFoundryProjectDescription!
          }
        : null
    }

    aiModelDeployments: !empty(modelDeploymentList)
      ? modelDeploymentList
      : [
          {
            model: {
              format: 'OpenAI'
              name: 'gpt-5-nano'
              version: '2025-08-07'
            }
            name: 'gpt-5-nano'
            sku: {
              name: 'GlobalStandard'
              capacity: 40
            }
          }
          {
            model: {
              format: 'OpenAI'
              name: 'text-embedding-3-large'
              version: '1'
            }
            name: 'text-embedding-3-large'
            sku: {
              name: 'Standard'
              capacity: 10
            }
          }
        ]

    aiSearchConfiguration: varAfAiSearchCfgComplete
    cosmosDbConfiguration: varAfCosmosCfgComplete
    keyVaultConfiguration: varAfKVCfgComplete
    storageAccountConfiguration: varAfStorageCfgComplete

    enableTelemetry: true
  }
  dependsOn: [
    #disable-next-line BCP321
    _deployAiFoundrySearch ? searchServiceAIFoundry : null
    #disable-next-line BCP321
    (_networkIsolation && !useExistingVNet) ? virtualNetwork : null
    #disable-next-line BCP321
    (_networkIsolation && useExistingVNet && deploySubnets && deployNsgs) ? virtualNetworkSubnets : null
    #disable-next-line BCP321
    _networkIsolation ? privateDnsZones : null
    #disable-next-line BCP321
    _deployAiFoundryStorage ? aiFoundryStorageAccount : null
    // Serialize AI Foundry's internal PE creation against the shared `pe-subnet`
    // (fixes #41). The AVM ai-foundry module creates its own cog-svc PEs on the
    // same subnet used by the `privateEndpoints` aggregator and by the inline blob
    // PE in `aiFoundryStorageAccount`. Without this dependsOn, the AVM-internal PE
    // NICs race the subnet update and ARM intermittently fails one of them with
    // `ReferencedResourceNotProvisioned`.
    #disable-next-line BCP321
    _networkIsolation ? privateEndpoints : null
  ]
}


var varAfNetworkingOverride = _networkIsolation
  ? (policyManagedPrivateDns
    ? {
        agentServiceSubnetResourceId: deployAiFoundrySubnet ? _agentSubnetId : null
      }
    : {
        cognitiveServicesPrivateDnsZoneResourceId: _dnsZoneCogSvcsId
        openAiPrivateDnsZoneResourceId: _dnsZoneOpenAiId
        aiServicesPrivateDnsZoneResourceId: _dnsZoneAiServicesId
        agentServiceSubnetResourceId: deployAiFoundrySubnet ? _agentSubnetId : null
      })
  : null

var varAfAiSearchCfgComplete = _deployAiFoundryAgentService ? {
  #disable-next-line BCP318
  existingResourceId: _useExistingAiFoundrySearch ? aiSearchResourceId : searchServiceAIFoundry.outputs.resourceId
  name: resourceNames.aiFoundrySearchServiceName
  privateDnsZoneResourceId: (_networkIsolation && !policyManagedPrivateDns) ? _dnsZoneSearchId : null
  roleAssignments: []
} : {}

var varAfCosmosCfgComplete = _deployAiFoundryAgentService ? {
  existingResourceId: _useExistingAiFoundryCosmos ? aiFoundryCosmosDBAccountResourceId : null
  name: resourceNames.aiFoundryCosmosDbName
  privateDnsZoneResourceId: (_networkIsolation && !policyManagedPrivateDns) ? _dnsZoneCosmosId : null
  roleAssignments: []
} : {}

var varAfKVCfgComplete = _deployAiFoundryAgentService ? {
  existingResourceId: keyVaultResourceId != '' ? keyVaultResourceId : null
  name: '${const.abbrs.security.keyVault}ai-${resourceToken}'
  privateDnsZoneResourceId: (_networkIsolation && !policyManagedPrivateDns) ? _dnsZoneKeyVaultId : null
  roleAssignments: []
} : {}

// NOTE: The AVM ai-foundry `storageAccountConfigurationType` does not expose
// a `skuName` field. We instead pre-create the Storage Account in
// `aiFoundryStorageAccount` above with the requested SKU and pass its
// resource ID here as `existingResourceId`, which causes the AVM to skip
// internal storage creation (and its default `Standard_GRS`).
var varAfStorageCfgComplete = _deployAiFoundryAgentService ? {
  #disable-next-line BCP318
  existingResourceId: _useExistingAiFoundryStorage ? aiFoundryStorageAccountResourceId : aiFoundryStorageAccount.outputs.resourceId
  name: resourceNames.aiFoundryStorageAccountName
  blobPrivateDnsZoneResourceId: (_networkIsolation && !policyManagedPrivateDns) ? _dnsZoneBlobId : null
  roleAssignments: []
} : {}

var aiFoundryAccountResourceId = aiFoundry!.outputs.accountResourceId

var aiFoundryProjectResourceId = aiFoundry!.outputs.projectResourceId

var aiFoundryAccountEndpoint = 'https://${aiFoundry!.outputs.aiServicesName}.cognitiveservices.azure.com/'

var aiFoundryProjectEndpoint = 'https://${aiFoundry!.outputs.aiServicesName}.services.ai.azure.com/api/projects/${aiFoundry!.outputs.aiProjectName}'

// Bing Search Connection (optional)
module bingSearchConnection 'modules/bing-search/main.bicep' = if (deployAiFoundry && deployGroundingWithBing) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'bingSearchConnection-${resourceToken}'
  params: {
    accountName: aiFoundry!.outputs.aiServicesName
    projectName: aiFoundry!.outputs.aiProjectName
    bingSearchName: resourceNames.bingSearchName
  }
  dependsOn: [
    aiFoundry!
  ]
}

// AI Foundry Connections
//////////////////////////////////////////////////////////////////////////

// Bing Search Connection
module aiFoundryBingConnection 'modules/ai-foundry/connection-bing-search-tool.bicep' = if (deployAiFoundry && deployGroundingWithBing) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'aiFoundryBingConnection'
  params: {
    account_name: aiFoundry!.outputs.aiServicesName
    project_name: aiFoundry!.outputs.aiProjectName
    bingSearchName: resourceNames.bingSearchName
  }
  dependsOn: [
    aiFoundry!
  ]
}

// AI Search Connection
module aiFoundryConnectionSearch 'modules/ai-foundry/connection-ai-search.bicep' = if (deployAiFoundry && deploySearchService) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'connection-ai-search-${resourceToken}'
  params: {
    aiFoundryName: aiFoundry!.outputs.aiServicesName
    aiProjectName: aiFoundry!.outputs.aiProjectName
    connectedResourceName: searchService!.outputs.name
  }
  dependsOn: [
    aiFoundry!
    searchService!
  ]
}

// Dedicated AI Search connection for Foundry IQ knowledge bases. This is kept
// separate from SEARCH_CONNECTION_ID so application search and knowledge-base
// lifecycle can evolve independently.
module aiFoundryKnowledgeBaseSearchConnection 'modules/ai-foundry/connection-ai-search.bicep' = if (deployAiFoundry && deploySearchService && retrievalBackend == 'foundry_iq') {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'connection-foundry-iq-search-${resourceToken}'
  params: {
    aiFoundryName: aiFoundry!.outputs.aiServicesName
    aiProjectName: aiFoundry!.outputs.aiProjectName
    connectedResourceName: searchService!.outputs.name
    aiSearchConnectionName: knowledgeBaseConnectionName
  }
  dependsOn: [
    aiFoundry!
    searchService!
  ]
}

// Application Insights Connection
module aiFoundryConnectionInsights 'modules/ai-foundry/connection-application-insights.bicep' = if (deployAiFoundry && _hasEffectiveAI) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'connection-appinsights-${resourceToken}'
  params: {
    aiFoundryName: aiFoundry!.outputs.aiServicesName
    connectedResourceId: _appInsightsResourceId
  }
  dependsOn: [
    aiFoundry!
    #disable-next-line BCP321
    _createAppInsights ? appInsights : null
  ]
}

// Storage Account Connection
module aiFoundryConnectionStorage 'modules/ai-foundry/connection-storage-account.bicep' = if (deployAiFoundry && deployStorageAccount) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'connection-storage-account-${resourceToken}'
  params: {
    aiFoundryName: aiFoundry!.outputs.aiServicesName
    connectedResourceName: storageAccount!.outputs.name
  }
  dependsOn: [
    aiFoundry!
    storageAccount!
  ]
}

// Application Insights
//////////////////////////////////////////////////////////////////////////
var appInsightsInvalidLocations = ['westcentralus']

module appInsights 'modules/application/app-insights.bicep' = if (_createAppInsights) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'applicationInsights'
  params: {
    name: resourceNames.appInsightsName
    location: contains(appInsightsInvalidLocations, location) ? 'eastus' : location
    tags: _tags
    workspaceResourceId: _lawResourceId
  }
}

//private link scope
module privateLinkScope 'modules/application/monitor-private-link-scope.bicep' = if (_deployAmpls) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'applicationMonitorPrivateLinkScope'
  params: {
    name: '${const.abbrs.networking.privateLinkScope}${resourceToken}'
    workspaceName: resourceNames.logAnalyticsWorkspaceName
    workspaceResourceId: _lawResourceId
    appInsightsName: resourceNames.appInsightsName
    appInsightsResourceId: _appInsightsResourceId
  }
  dependsOn: [
    appInsights!
  ]
}

module privateEndpointPrivateLinkScope 'modules/networking/private-endpoint.bicep' = if (_deployAmpls) {
  name: 'privatelink-scope-private-endpoint'
  params: {
    name: '${const.abbrs.networking.privateEndpoint}${const.abbrs.networking.privateLinkScope}${resourceToken}'
    location: _peLocation
    resourceGroupName: _peResourceGroupName
    subscriptionId: _peSubscriptionId
    tags: _tags
    subnetResourceId: _applicationPeSubnetId
    privateLinkServiceConnections: [
      {
        name: 'privateLinkScopeConnection'
        properties: {
          privateLinkServiceId: privateLinkScope.outputs.resourceId
          groupIds: ['azuremonitor']
        }
      }
    ]
    privateDnsZoneGroup: policyManagedPrivateDns ? null : {
      name: 'privateLinkDnsZoneGroup'
      privateDnsZoneGroupConfigs: [
        { name: 'azuremonitorARecord', privateDnsZoneResourceId: _dnsZoneAzureMonitorId }
        { name: 'omsinsightsARecord',  privateDnsZoneResourceId: _dnsZoneOmsOpsInsightsId }
        { name: 'odsinsightsARecord',  privateDnsZoneResourceId: _dnsZoneOdsOpsInsightsId }
        { name: 'automationARecord',   privateDnsZoneResourceId: _dnsZoneAzureAutomationId }
      ]
    }
  }
  dependsOn: [
    privateLinkScope!
    privateDnsZones
    privateEndpoints // Serialize PE operations to avoid conflicts
    aiFoundry // Also serialize against Foundry's nested endpoints on the legacy shared subnet.
    aiFoundryStorageAccount
  ]
}

// Container Resources
//////////////////////////////////////////////////////////////////////////

//Container Apps Env User Managed Identity
module containerEnvUAI 'modules/security/managed-identity.bicep' = if (_useUAI && deployContainerEnv) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'containerEnvironmentIdentity'
  params: {
    name: '${const.abbrs.security.managedIdentity}${resourceNames.containerEnvName}'
    location: location
  }
}

// Container Apps Environment
module containerEnv 'modules/application/container-environment.bicep' = if (deployContainerEnv) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'containerEnvironment'
  params: {
    name: resourceNames.containerEnvName
    location: location
    tags: _tags
    identity: {
      type: _useUAI ? 'UserAssigned' : 'SystemAssigned'
      userAssignedIdentities: _useUAI ? { '${containerEnvUAI.outputs.resourceId}': {} } : null
    }
    properties: {
      appLogsConfiguration: {
        destination: null
      }
      appInsightsConfiguration: _hasEffectiveAI ? {
        connectionString: _appInsightsConnectionString
      } : null
      zoneRedundant: useZoneRedundancy
      workloadProfiles: workloadProfiles
      vnetConfiguration: networkIsolation ? {
        infrastructureSubnetId: _caEnvSubnetId
        internal: true
      } : null
    }
  }
  dependsOn: [
    #disable-next-line BCP321
    !useExistingVNet ? virtualNetwork : null
    #disable-next-line BCP321
    useExistingVNet ? virtualNetworkSubnets : null
  ]
}

//Container Registry User Managed Identity
module containerRegistryUAI 'modules/security/managed-identity.bicep' = if (_useUAI && deployContainerRegistry) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'containerRegistryIdentity'
  params: {
    name: '${const.abbrs.security.managedIdentity}${resourceNames.containerRegistryName}'
    location: location
  }
}

// Container Registry
module containerRegistry 'modules/application/container-registry.bicep' = if (deployContainerRegistry) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'containerRegistry'
  params: {
    name: resourceNames.containerRegistryName
    location: location
    tags: _tags
    skuName: _networkIsolation ? 'Premium' : 'Basic'
    identity: {
      type: _useUAI ? 'UserAssigned' : 'SystemAssigned'
      userAssignedIdentities: _useUAI ? { '${containerRegistryUAI.outputs.resourceId}': {} } : null
    }
    properties: {
      publicNetworkAccess: _publicNetworkAccess
      zoneRedundancy: useZoneRedundancy ? 'Enabled' : 'Disabled'
      dataEndpointEnabled: _networkIsolation
      networkRuleSet: _applyIpRules ? {
        defaultAction: 'Deny'
        ipRules: _acrIpRules
      } : null
      policies: {
        exportPolicy: {
          status: 'enabled'
        }
      }
    }
  }
}

// ACR Task agent pool — enables `az acr build --agent-pool <name>` to run image
// builds inside the VNet when publicNetworkAccess on the registry is Disabled.
// Gated on networkIsolation (Premium SKU) and deployAcrTaskAgentPool.
module acrTaskAgentPool 'modules/application/acr-agent-pool.bicep' = if (_deployAcrTaskAgentPool) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'containerRegistryAgentPool'
  params: {
    registryName: resourceNames.containerRegistryName
    name: acrTaskAgentPoolName
    location: location
    tags: _tags
    count: acrTaskAgentPoolCount
    tier: acrTaskAgentPoolTier
    #disable-next-line BCP318
    subnetResourceId: _networkIsolation ? '${virtualNetworkResourceId}/subnets/${devopsBuildAgentsSubnetName}' : ''
  }
  dependsOn: [
    containerRegistry
    // The constructed BYO subnet ID does not imply subnet creation order.
    virtualNetworkSubnets
  ]
}

//Container Apps User Managed Identity
module containerAppsUAI 'modules/security/managed-identity.bicep' = [
  for app in containerAppsList: if (_useUAI && _deployContainerApps) {
    scope: resourceGroup(_applicationResourceGroupName)
    name: 'containerAppIdentity-${app.service_name}'
    params: {
      name: '${const.abbrs.security.managedIdentity}${const.abbrs.containers.containerApp}${resourceToken}-${app.service_name}'
      location: location
    }
  }
]

// Container Apps
//
// Runtime configuration env vars (Issue #89). When
// ``appRuntimeConfigurationMode == 'containerEnv'`` every Container App
// receives this curated bootstrap env block in addition to the identity
// bootstrap (AZURE_TENANT_ID, AZURE_CLIENT_ID when UAI). The block intentionally
// contains only values that are knowable from input parameters and resource
// names (no module .outputs references) so it stays free of cross-module
// circular dependencies and re-deploys idempotently. Endpoints that the
// consumer needs at runtime can be resolved from these names through the
// Azure SDK. Secrets remain on secure params / Key Vault references and are
// NOT emitted here.
var _containerRuntimeEnv = [
  { name: 'SUBSCRIPTION_ID',           value: subscription().subscriptionId }
  { name: 'AZURE_RESOURCE_GROUP',      value: resourceGroup().name }
  { name: 'AZURE_APP_RESOURCE_GROUP', value: _applicationResourceGroupName }
  { name: 'AZURE_NETWORK_RESOURCE_GROUP', value: _networkResourceGroupName }
  { name: 'LOCATION',                  value: location }
  { name: 'ENVIRONMENT_NAME',          value: environmentName }
  { name: 'RESOURCE_TOKEN',            value: resourceToken }
  { name: 'RELEASE',                   value: _manifest.tag }
  { name: 'NETWORK_ISOLATION',         value: toLower(string(_networkIsolation)) }
  { name: 'USE_UAI',                   value: toLower(string(_useUAI)) }
  { name: 'ENABLE_AGENTIC_RETRIEVAL',  value: toLower(string(enableAgenticRetrieval)) }
  { name: 'RETRIEVAL_BACKEND',         value: retrievalBackend }
  { name: 'KNOWLEDGE_BASE_NAME',       value: retrievalBackend == 'foundry_iq' ? knowledgeBaseName : '' }
  { name: 'KNOWLEDGE_BASE_ENDPOINT',   value: retrievalBackend == 'foundry_iq' ? 'https://${resourceNames.searchServiceName}.search.windows.net' : '' }
  { name: 'KNOWLEDGE_BASE_CONNECTION_ID', value: retrievalBackend == 'foundry_iq' ? '/subscriptions/${subscription().subscriptionId}/resourceGroups/${_foundryResourceGroupName}/providers/Microsoft.CognitiveServices/accounts/${resourceNames.aiFoundryAccountName}/projects/${resourceNames.aiFoundryProjectName}/connections/${knowledgeBaseConnectionName}' : '' }
  { name: 'FOUNDRY_IQ_API_VERSION',    value: retrievalBackend == 'foundry_iq' ? foundryIqApiVersion : '' }
  { name: 'FOUNDRY_IQ_KNOWLEDGE_RETRIEVAL_BILLING_PLAN', value: retrievalBackend == 'foundry_iq' ? foundryIqKnowledgeRetrievalBillingPlan : '' }
  { name: 'FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME', value: retrievalBackend == 'foundry_iq' ? foundryIqKnowledgeSourceName : '' }
  { name: 'FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND', value: effectiveFoundryIqKnowledgeSourceKind }
  { name: 'FOUNDRY_IQ_FILTER_ADD_ON_ENABLED', value: retrievalBackend == 'foundry_iq' && foundryIqPattern == 'searchIndex' ? toLower(string(foundryIqFilterAddOnEnabled)) : 'false' }
  { name: 'FOUNDRY_IQ_SECURITY_FIELD_NAME', value: retrievalBackend == 'foundry_iq' && foundryIqPattern == 'searchIndex' ? foundryIqSecurityFieldName : '' }
  { name: 'FOUNDRY_IQ_MAX_OUTPUT_DOCUMENTS', value: retrievalBackend == 'foundry_iq' ? foundryIqMaxOutputDocuments : '' }
  { name: 'LOG_LEVEL',                 value: 'INFO' }
  { name: 'ENABLE_CONSOLE_LOGGING',    value: 'true' }
  { name: 'AI_FOUNDRY_ACCOUNT_NAME',   value: resourceNames.aiFoundryAccountName }
  { name: 'AI_FOUNDRY_PROJECT_NAME',   value: resourceNames.aiFoundryProjectName }
  { name: 'AI_FOUNDRY_ACCOUNT_ENDPOINT', value: 'https://${resourceNames.aiFoundryAccountName}.cognitiveservices.azure.com/' }
  { name: 'AI_FOUNDRY_OPENAI_ENDPOINT',  value: 'https://${resourceNames.aiFoundryAccountName}.openai.azure.com/' }
  { name: 'APP_INSIGHTS_NAME',         value: resourceNames.appInsightsName }
  { name: 'CONTAINER_ENV_NAME',        value: resourceNames.containerEnvName }
  { name: 'CONTAINER_REGISTRY_NAME',   value: resourceNames.containerRegistryName }
  { name: 'CONTAINER_REGISTRY_LOGIN_SERVER', value: '${resourceNames.containerRegistryName}.azurecr.io' }
  { name: 'DATABASE_ACCOUNT_NAME',     value: resourceNames.dbAccountName }
  { name: 'DATABASE_NAME',             value: resourceNames.dbDatabaseName }
  { name: 'SEARCH_SERVICE_NAME',       value: resourceNames.searchServiceName }
  { name: 'STORAGE_ACCOUNT_NAME',      value: resourceNames.storageAccountName }
  { name: 'KEY_VAULT_NAME',            value: resourceNames.keyVaultName }
  { name: 'APP_CONFIG_NAME',           value: resourceNames.appConfigName }
  { name: 'APP_RUNTIME_CONFIGURATION_MODE', value: appRuntimeConfigurationMode }
]

// Symmetric accelerator passthrough for the containerEnv runtime mode (Issue #89).
// When the consumer opts out of App Configuration, the same accelerator-supplied
// settings must reach the Container Apps as env vars. Container env vars have no
// label or contentType, so only name/value are projected. Additional settings win
// on a name collision (the base bootstrap entry is dropped) to keep the same
// precedence as the App Configuration passthrough. With the default empty array
// this is a no-op and the emitted env block is byte-identical.
var _additionalContainerEnv = [
  for s in additionalAppConfigurationSettings: {
    name: s.name
    value: s.value
  }
]
var _additionalContainerEnvNames = map(_additionalContainerEnv, e => e.name)
var _containerRuntimeEnvWithAdditional = concat(
  filter(_containerRuntimeEnv, e => !contains(_additionalContainerEnvNames, e.name)),
  _additionalContainerEnv
)

var _containerAppNames = [
  for app in containerAppsList: empty(app.name) ? '${const.abbrs.containers.containerApp}${resourceToken}-${app.service_name}' : app.name
]

var _containerAppDaprConfigs = [
  for app in containerAppsList: app.?dapr.?enabled == true ? {
    enabled: true
    appId: app.?dapr.?appId ?? app.service_name
    appPort: int(app.?dapr.?appPort ?? app.?target_port ?? 8080)
    appProtocol: app.?dapr.?appProtocol ?? 'http'
    enableApiLogging: app.?dapr.?enableApiLogging ?? false
  } : null
]

var _containerAppBaseEnvironmentVariables = [
  for app in containerAppsList: concat(
    // APP_CONFIG_ENDPOINT is only meaningful when the App Configuration
    // store is the source of runtime configuration (Issue #89).
    _runtimeConfigIsAppConfig ? [
      {
        name: 'APP_CONFIG_ENDPOINT'
        value: 'https://${resourceNames.appConfigName}.azconfig.io'
      }
    ] : [],
    [
      {
        name: 'AZURE_TENANT_ID'
        value: subscription().tenantId
      }
    ]
  )
]

@batchSize(4)
module containerApps 'br/public:avm/res/app/container-app:0.18.1' = [
  for (app, index) in containerAppsList: if (_deployContainerApps) {
    scope: resourceGroup(_applicationResourceGroupName)
    name: _containerAppNames[index]
    params: {
      name: _containerAppNames[index]
      location: location
      #disable-next-line BCP318
      environmentResourceId: containerEnv.outputs.resourceId
      workloadProfileName: app.profile_name

      ingressExternal: app.external
      ingressTargetPort: int(app.?target_port ?? 8080)
      ingressTransport: 'auto'
      ingressAllowInsecure: false

      dapr: _containerAppDaprConfigs[index]

      managedIdentities: {
        systemAssigned: (_useUAI) ? false : true
        #disable-next-line BCP318
        userAssignedResourceIds: (_useUAI) ? [containerAppsUAI[index].outputs.resourceId] : []
      }

      // A preserved ACR image needs its registry pull identity, otherwise the PUT drops it.
      registries: endsWith(split(app.?image ?? '', '/')[0], '.azurecr.io') ? [
        {
          server: split(app.image, '/')[0]
          #disable-next-line BCP318
          identity: _useUAI ? containerAppsUAI[index].outputs.resourceId : 'system'
        }
      ] : []

      scaleSettings: {
        minReplicas: app.min_replicas
        maxReplicas: app.max_replicas
      }

      containers: [
        {
          name: app.service_name
          // Reprovisioning keeps the deployed image when the caller passes it as `app.image`.
          image: !empty(app.?image ?? '') ? app.image : _containerDummyImageName
          resources: {
            cpu: app.?cpu ?? '0.5'
            memory: app.?memory ?? '1.0Gi'
          }
          env: concat(
            _containerAppBaseEnvironmentVariables[index],
            // Only inject AZURE_CLIENT_ID when a UAI is actually configured (#38).
            // Emitting an empty AZURE_CLIENT_ID alongside AZURE_TENANT_ID breaks
            // DefaultAzureCredential on the SystemAssigned path. With the var omitted,
            // ManagedIdentityCredential uses the platform-injected SystemAssigned MI.
            _useUAI ? [
              {
                name: 'AZURE_CLIENT_ID'
                #disable-next-line BCP318
                value: containerAppsUAI[index].outputs.clientId
              }
            ] : [],
            // Bootstrap runtime config when the consumer opts out of App Config
            // (Issue #89, `appRuntimeConfigurationMode == 'containerEnv'`).
            _runtimeConfigIsContainerEnv ? _containerRuntimeEnvWithAdditional : []
          )
        }
      ]

      tags: union(_tags, {
        'azd-service-name': app.service_name
      })
    }
    dependsOn: [
      containerEnv!                   
      privateDnsZones
      privateEndpoints
      // Issue #78 — under network isolation the aca-environment-subnet UDR
      // routes 0.0.0.0/0 to Azure Firewall. The ACA control plane validates
      // the placeholder image (`_containerDummyImageName`, MCR) at create
      // time. Without this dependency the container apps race the firewall
      // rule collection group and the MCR pull is denied (EOF), which
      // aborts the whole provision before the firewall rules ever land.
      // The reference is to a conditional resource; in Basic mode
      // (`deployAzureFirewall=false` or `networkIsolation=false`) the
      // dependency is simply absent.
      firewall
    ]
  }
]

// Cosmos DB Account and Database
//////////////////////////////////////////////////////////////////////////

//Cosmos User Managed Identity
module cosmosUAI 'modules/security/managed-identity.bicep' = if (_useUAI) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'cosmosIdentity'
  params: {
    name: '${const.abbrs.security.managedIdentity}${resourceNames.dbAccountName}'
    location: location
  }
}

// Declared locally so every deployment sends the full account property set.
// See modules/cosmos-db/database-account.bicep for details.
module cosmosDBAccount 'modules/cosmos-db/database-account.bicep' = if (deployCosmosDb) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'CosmosDBAccount'
  params: {
    name: resourceNames.dbAccountName
    location: cosmosLocation
    systemAssignedIdentity: !_useUAI
    #disable-next-line BCP318
    userAssignedResourceIds: _useUAI ? [cosmosUAI.outputs.resourceId] : []
    isZoneRedundant: useZoneRedundancy
    defaultConsistencyLevel: 'Session'
    capabilities: ['EnableServerless']
    enableAnalyticalStorage: enableCosmosAnalyticalStorage
    enableFreeTier: false
    publicNetworkAccess: _publicNetworkAccess
    ipRules: _cosmosIpRules
    virtualNetworkSubnetIds: _networkIsolation ? union([_peSubnetId, _caEnvSubnetId], [_applicationPeSubnetId]) : []
    tags: _tags
  }
  dependsOn: [
    #disable-next-line BCP321
    (_networkIsolation) ? virtualNetwork : null
  ]
}

// The Cosmos DB AVM composes its SQL database deployment name from the full
// database resource name. CAF environment names can therefore push that nested
// deployment beyond ARM's 64-character limit. The account is declared locally and
// deploy its database and containers through a fixed-name local module so
// resource names remain unchanged and deployment-name length is constant.
module cosmosSqlDatabase 'modules/cosmos-db/sql-database.bicep' = if (deployCosmosDb) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'cosmosSqlDatabase'
  params: {
    databaseAccountName: resourceNames.dbAccountName
    databaseName: resourceNames.dbDatabaseName
    databaseThroughput: dbDatabaseThroughput
    containers: [
      for container in databaseContainersList: {
        name: container.name
        paths: [container.partitionKey]
        defaultTtl: -1
        throughput: container.?throughput
        indexingPolicy: container.?indexingPolicy
      }
    ]
  }
  dependsOn: [
    cosmosDBAccount
  ]
}

// Key Vault
//////////////////////////////////////////////////////////////////////////

module keyVault 'modules/application/key-vault.bicep' = if (deployKeyVault) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'applicationKeyVault'
  params: {
    name: resourceNames.keyVaultName
    location: location
    tags: _tags
    publicNetworkAccess: _publicNetworkAccess
    networkAcls: _applyIpRules ? {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
      ipRules: _keyVaultIpRules
    } : null
    secrets: { values: _containerAppsKeyVaultKeys }
  }
}

// Log Analytics Workspace
//////////////////////////////////////////////////////////////////////////

module logAnalytics 'modules/application/log-analytics.bicep' = if (_createLogAnalytics) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'applicationLogAnalytics'
  params: {
    name: resourceNames.logAnalyticsWorkspaceName
    location: location
    tags: _tags
  }
}

// AI Search
//////////////////////////////////////////////////////////////////////////

//Search Service User Managed Identity
module searchServiceUAI 'modules/security/managed-identity.bicep' = if (_useUAI && deploySearchService) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'searchServiceIdentityDeployment'
  params: {
    name: '${const.abbrs.security.managedIdentity}${resourceNames.searchServiceName}'
    location: _searchServiceLocation
  }
}

module searchService 'br/public:avm/res/search/search-service:0.11.1' = if (deploySearchService) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'searchService'
  params: {
    name: resourceNames.searchServiceName
    location: _searchServiceLocation
    publicNetworkAccess: _publicNetworkAccess
    networkRuleSet: _applyIpRules ? {
      bypass: 'AzureServices'
      ipRules: _searchIpRules
    } : null
    tags: _tags

    // SKU & capacity
    // Using 'standard' rather than 'basic' because several regions (eastus2, westus3, etc.)
    // are returning InsufficientResourcesAvailable for the basic SKU capacity pool. Standard
    // has broader capacity availability at ~same cost tier when kept at 1 replica / 1 partition.
    sku: 'standard'
    replicaCount: 1
    partitionCount: 1
    semanticSearch: 'standard'

    // Identity & Auth
    managedIdentities: {
      systemAssigned: _useUAI ? false : true
      #disable-next-line BCP318
      userAssignedResourceIds: _useUAI ? [searchServiceUAI.outputs.resourceId] : []
    }

    disableLocalAuth: false
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
    sharedPrivateLinkResources: _networkIsolation
      ? concat(
        deployStorageAccount
          ? [
          {
            groupId: 'blob'
            #disable-next-line BCP318
            privateLinkResourceId: storageAccount.outputs.resourceId
            requestMessage: 'Allow AI Search private indexing access to Agent Landing Zone documents storage.'
          }
        ]
          : [],
        deployAiFoundry && retrievalBackend == 'foundry_iq'
          ? []
          : [])
      : []
  }
  dependsOn: [
    containerEnv!
    storageAccount!
  ]
}

// Search shared private-link names are limited to 60 characters. The plain,
// human-readable name (`spl-<searchServiceName>-<groupId>-1`) is kept as-is
// whenever it already fits, preserving names for existing deployments and
// ordinary CAF/azd-generated Search service names. Only when the plain name
// would exceed the limit — long explicit or CAF-generated Search service
// names — do we fall back to a bounded token that truncates the Search name
// and appends a deterministic hash, keeping the semantic group suffix intact
// and retaining collision resistance. This keeps the worst case (a
// maximum-length 60-character Search service name) at exactly 60 characters
// for every group, so it never depends on operators choosing short (<=7
// character) environment names.
var searchFoundrySharedPrivateLinkNameToken = '${take(resourceNames.searchServiceName, 21)}-${take(uniqueString(resourceNames.searchServiceName), 6)}'
var searchFoundrySharedPrivateLinkMaxNameLength = 60

var searchFoundrySharedPrivateLinkResources = (_networkIsolation && deploySearchService && deployAiFoundry && retrievalBackend == 'foundry_iq')
  ? [
      {
        name: length('spl-${resourceNames.searchServiceName}-openai_account-1') <= searchFoundrySharedPrivateLinkMaxNameLength
          ? 'spl-${resourceNames.searchServiceName}-openai_account-1'
          : 'spl-${searchFoundrySharedPrivateLinkNameToken}-openai_account-1'
        groupId: 'openai_account'
        requestMessage: 'Allow AI Search private access to Azure OpenAI embeddings for Foundry IQ.'
      }
      {
        name: length('spl-${resourceNames.searchServiceName}-foundry_account-1') <= searchFoundrySharedPrivateLinkMaxNameLength
          ? 'spl-${resourceNames.searchServiceName}-foundry_account-1'
          : 'spl-${searchFoundrySharedPrivateLinkNameToken}-foundry_account-1'
        groupId: 'foundry_account'
        requestMessage: 'Allow AI Search private access to Microsoft Foundry for Foundry IQ.'
      }
      {
        name: length('spl-${resourceNames.searchServiceName}-cognitiveservices_account-1') <= searchFoundrySharedPrivateLinkMaxNameLength
          ? 'spl-${resourceNames.searchServiceName}-cognitiveservices_account-1'
          : 'spl-${searchFoundrySharedPrivateLinkNameToken}-cognitiveservices_account-1'
        groupId: 'cognitiveservices_account'
        requestMessage: 'Allow AI Search private access to Cognitive Services for Foundry IQ standard extraction.'
      }
    ]
  : []

// Post-provision readiness uses exact template-owned identities, including the
// bounded Foundry names. Blob is entry zero in the AVM shared-link array.
var searchFoundrySharedPrivateLinkReadinessManifest = [for spl in searchFoundrySharedPrivateLinkResources: {
  name: spl.name
  groupId: spl.groupId
  privateLinkResourceId: resourceId(subscription().subscriptionId, _foundryResourceGroupName, 'Microsoft.CognitiveServices/accounts', resourceNames.aiFoundryAccountName)
}]

var searchSharedPrivateLinkReadinessManifest = (_networkIsolation && deploySearchService)
  ? concat(
      deployStorageAccount
        ? [{
            name: 'spl-${resourceNames.searchServiceName}-blob-0'
            groupId: 'blob'
            privateLinkResourceId: resourceId(subscription().subscriptionId, _foundryResourceGroupName, 'Microsoft.Storage/storageAccounts', resourceNames.storageAccountName)
          }]
        : [],
      searchFoundrySharedPrivateLinkReadinessManifest
    )
  : []

module searchFoundrySharedPrivateLinks 'modules/ai-foundry/search-shared-private-links.bicep' = if (!empty(searchFoundrySharedPrivateLinkResources)) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'searchFoundrySharedPrivateLinksDeployment'
  params: {
    searchServiceName: resourceNames.searchServiceName
    foundryAccountResourceId: aiFoundryAccountResourceId
    links: searchFoundrySharedPrivateLinkResources
  }
  dependsOn: [
    searchService
  ]
}

// Dedicated AI Search service for AI Foundry (separate from the application search).
// Skipped when the consumer brings their own AI Foundry search via `aiSearchResourceId`.
module searchServiceAIFoundry 'br/public:avm/res/search/search-service:0.11.1' = if (_deployAiFoundrySearch) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'searchServiceAIFoundry'
  params: {
    name: resourceNames.aiFoundrySearchServiceName
    location: _searchServiceLocation
    publicNetworkAccess: _publicNetworkAccess
    networkRuleSet: _applyIpRules ? {
      bypass: 'AzureServices'
      ipRules: _searchIpRules
    } : null
    tags: _tags

    // SKU & capacity (aligned with application search defaults; override for heavier workloads)
    // Using 'standard' SKU for reliable regional capacity availability.
    sku: 'standard'
    replicaCount: 1
    partitionCount: 1
    semanticSearch: 'standard'

    // Identity & Auth: system-assigned MI (AI Foundry project identity gets data-plane roles via AVM)
    managedIdentities: {
      systemAssigned: true
    }

    disableLocalAuth: false
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
  }
  dependsOn: [
    containerEnv!
    // Serialize creation of the two search services to avoid a rare race
    // condition in the Microsoft.Search resource provider where two parallel
    // PUTs against similarly-named services in the same region/subscription
    // can leave the second name "stuck" in the backend namespace cache,
    // producing subsequent "already exists" / "ServiceNameUnavailable" errors
    // even though the service is not visible in ARM and the name appears
    // available to checkNameAvailability.
    searchService!
  ]
}

// Azure AI Speech (SpeechServices)
//////////////////////////////////////////////////////////////////////////
// First-class, optional Speech account. Same network-isolated posture as the
// rest of the AI services in this landing zone — customSubDomainName,
// publicNetworkAccess=Disabled under NI, private endpoint into the existing
// `privatelink.cognitiveservices.azure.com` zone (groupId `account`), and
// system-assigned MI for diagnostic settings / future RBAC scenarios.
//
// PE is created externally via `_peList` (parallel to the search/cosmos
// pattern) so it routes through the same `privateEndpoints` aggregator
// module and reuses the existing private DNS zone — no duplicate zone.
module speechService 'br/public:avm/res/cognitive-services/account:0.13.2' = if (deploySpeechService) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'speechService'
  params: {
    name: resourceNames.speechServiceName
    location: _speechServiceLocation
    tags: _tags
    kind: 'SpeechServices'
    sku: speechServiceSku

    // customSubDomainName is required for AAD auth and private endpoints.
    // Pinning it to the account name keeps the FQDN deterministic.
    customSubDomainName: resourceNames.speechServiceName

    publicNetworkAccess: _publicNetworkAccess
    networkAcls: _applyIpRules ? {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      ipRules: _cognitiveIpRules
    } : {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }

    // Identity for diagnostic settings + future data-plane RBAC scenarios.
    managedIdentities: {
      systemAssigned: true
    }

    // PE is created out-of-module via `_peList` (#35).
    privateEndpoints: []

    diagnosticSettings: _hasEffectiveLaw ? [
      {
        workspaceResourceId: _lawResourceId
      }
    ] : []
  }
}

// Storage Accounts
//////////////////////////////////////////////////////////////////////////

// Storage Account
module storageAccount 'br/public:avm/res/storage/storage-account:0.26.2' = if (deployStorageAccount) {
  scope: resourceGroup(_foundryResourceGroupName)
  name: 'storageAccountSolution'
  params: {
    name: resourceNames.storageAccountName
    location: location
    publicNetworkAccess: _publicNetworkAccess
    skuName: 'Standard_LRS'
    kind: 'StorageV2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: storageAccountAllowSharedKeyAccess
    supportsHttpsTrafficOnly: true
    requireInfrastructureEncryption: true
    networkAcls: {
      bypass: storageAccountNetworkAclsBypass
      resourceAccessRules: storageAccountResourceAccessRules
      virtualNetworkRules: []
      ipRules: _storageIpRules
      defaultAction: _applyIpRules ? 'Deny' : 'Allow'
    }
    tags: _tags
    blobServices: {
      automaticSnapshotPolicyEnabled: true
      containerDeleteRetentionPolicyDays: 10
      containerDeleteRetentionPolicyEnabled: true
      containers: [
        for container in storageAccountContainersList: {
          name: container.name
          publicAccess: 'None'
        }
      ]
      deleteRetentionPolicyDays: 7
      deleteRetentionPolicyEnabled: true
      lastAccessTimeTrackingPolicyEnabled: true
    }
  }
}

var _documentsContainers = filter(storageAccountContainersList, container => container.?canonical_name == 'DOCUMENTS_STORAGE_CONTAINER')
var _documentsContainerResourceId = deployStorageAccount && length(_documentsContainers) == 1
  ? '${storageAccount!.outputs.resourceId}/blobServices/default/containers/${_documentsContainers[0].name}'
  : ''

//////////////////////////////////////////////////////////////////////////
// ROLE ASSIGNMENTS
//////////////////////////////////////////////////////////////////////////

// Role assignments are centralized in this section to make it easier to view all permissions granted in this template.
// Custom modules are used for role assignments since no published AVM module available for this at the time we created this template.

// ---------------------------------------------------------------------------
// Executor role assignments (consolidated into a single array-driven module
// call to reduce compiled ARM template size).
// ---------------------------------------------------------------------------
var _executorRoles = concat(
  deployContainerRegistry ? [
    {
      principalId: principalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.AcrPush.guid)
      #disable-next-line BCP318
      resourceId: containerRegistry.outputs.resourceId
      principalType: principalType
    }
    {
      principalId: principalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.AcrPull.guid)
      #disable-next-line BCP318
      resourceId: containerRegistry.outputs.resourceId
      principalType: principalType
    }
  ] : [],
  deployKeyVault ? [
    {
      principalId: principalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.KeyVaultContributor.guid)
      #disable-next-line BCP318
      resourceId: keyVault.outputs.resourceId
      principalType: principalType
    }
    {
      principalId: principalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.KeyVaultSecretsOfficer.guid)
      #disable-next-line BCP318
      resourceId: keyVault.outputs.resourceId
      principalType: principalType
    }
  ] : [],
  deploySearchService ? [
    {
      principalId: principalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.SearchServiceContributor.guid)
      #disable-next-line BCP318
      resourceId: searchService.outputs.resourceId
      principalType: principalType
    }
    {
      principalId: principalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.SearchIndexDataContributor.guid)
      #disable-next-line BCP318
      resourceId: searchService.outputs.resourceId
      principalType: principalType
    }
    {
      principalId: principalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.SearchIndexDataReader.guid)
      #disable-next-line BCP318
      resourceId: searchService.outputs.resourceId
      principalType: principalType
    }
  ] : [],
  deployStorageAccount ? [
    {
      principalId: principalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.StorageBlobDataContributor.guid)
      #disable-next-line BCP318
      resourceId: storageAccount.outputs.resourceId
      principalType: principalType
    }
  ] : [],
  deployAiFoundry ? concat(
    [
      {
        principalId: principalId
        roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.CognitiveServicesOpenAIUser.guid)
        resourceId: aiFoundryAccountResourceId
        principalType: principalType
      }
      {
        principalId: principalId
        roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.CognitiveServicesUser.guid)
        resourceId: aiFoundryAccountResourceId
        principalType: principalType
      }
    ],
    (_hostedAgentPrerequisitesEnabled && grantHostedAgentProjectManager) ? [
      {
        principalId: principalId
        roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.AzureAIProjectManager.guid)
        resourceId: aiFoundryProjectResourceId
        principalType: principalType
      }
    ] : []
  ) : [],
  deploySpeechService ? [
    {
      principalId: principalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.CognitiveServicesContributor.guid)
      #disable-next-line BCP318
      resourceId: speechService.outputs.resourceId
      principalType: principalType
    }
    {
      principalId: principalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.CognitiveServicesUser.guid)
      #disable-next-line BCP318
      resourceId: speechService.outputs.resourceId
      principalType: principalType
    }
  ] : []
)

module assignExecutorRoles 'modules/security/resource-role-assignment.bicep' = if (deployContainerRegistry || deployKeyVault || deploySearchService || deployStorageAccount || deployAiFoundry || deploySpeechService) {
  name: 'assignExecutorRoles'
  params: {
    name: 'assignExecutorRoles'
    roleAssignments: _executorRoles
  }
}

// Cosmos DB Account - Cosmos DB Built-in Data Contributor -> Executor (data plane, separate module)
module assignCosmosDBCosmosDbBuiltInDataContributorExecutor 'modules/security/cosmos-data-plane-role-assignment.bicep' = if (deployCosmosDb) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'assignCosmosDBCosmosDbBuiltInDataContributorExecutor'
  params: {
    #disable-next-line BCP318
    cosmosDbAccountName: cosmosDBAccount.outputs.name
    principalId: principalId
    roleDefinitionGuid: const.roles.CosmosDBBuiltInDataContributor.guid
    scopePath: '/subscriptions/${subscription().subscriptionId}/resourceGroups/${_applicationResourceGroupName}/providers/Microsoft.DocumentDB/databaseAccounts/${resourceNames.dbAccountName}'
  }
}

// Container App control-plane role assignments (consolidated).
// Each app gets a single array-driven module invocation that builds the full
// set of control-plane roles it qualifies for, replacing the previous
// per-role per-app loops. Role assignment names are deterministic
// (guid(principalId, roleDefinitionId, resourceId)), so consolidating the
// deployment invocations does not change the deployed role assignment set.
// Cosmos DB data-plane assignments stay in their dedicated module below.
module assignContainerAppRoles 'modules/security/resource-role-assignment.bicep' = [
  for (app, i) in containerAppsList: if (_deployContainerApps && ((deployKeyVault && contains(app.roles, const.roles.KeyVaultSecretsUser.key)) || (deployAppConfig && _runtimeConfigIsAppConfig && contains(app.roles, const.roles.AppConfigurationDataReader.key)) || (deployAiFoundry && contains(app.roles, const.roles.CognitiveServicesUser.key)) || (deployAiFoundry && contains(app.roles, const.roles.CognitiveServicesOpenAIUser.key)) || (deploySpeechService && contains(app.roles, const.roles.CognitiveServicesUser.key)) || (deployContainerRegistry && contains(app.roles, const.roles.AcrPull.key)) || (deploySearchService && contains(app.roles, const.roles.SearchIndexDataReader.key)) || (deploySearchService && contains(app.roles, const.roles.SearchIndexDataContributor.key)) || (deployStorageAccount && contains(app.roles, const.roles.StorageBlobDataContributor.key)) || (deployStorageAccount && contains(app.roles, const.roles.StorageBlobDataReader.key)) || (deployStorageAccount && contains(app.roles, const.roles.StorageBlobDelegator.key)))) {
    name: 'assignContainerAppRoles-${app.service_name}'
    params: {
      name: 'assignContainerAppRoles-${app.service_name}'
      roleAssignments: concat(
        (deployKeyVault && contains(app.roles, const.roles.KeyVaultSecretsUser.key)) ? [
          {
            roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.KeyVaultSecretsUser.guid)
            #disable-next-line BCP318
            principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
            #disable-next-line BCP318
            resourceId: keyVault.outputs.resourceId
            principalType: 'ServicePrincipal'
          }
        ] : [],
        (deployAppConfig && _runtimeConfigIsAppConfig && contains(app.roles, const.roles.AppConfigurationDataReader.key)) ? [
          {
            roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.AppConfigurationDataReader.guid)
            #disable-next-line BCP318
            principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
            #disable-next-line BCP318
            resourceId: appConfig.outputs.resourceId
            principalType: 'ServicePrincipal'
          }
        ] : [],
        (deployAiFoundry && contains(app.roles, const.roles.CognitiveServicesUser.key)) ? [
          {
            roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.CognitiveServicesUser.guid)
            #disable-next-line BCP318
            principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
            resourceId: aiFoundryAccountResourceId
            principalType: 'ServicePrincipal'
          }
        ] : [],
        (deployAiFoundry && contains(app.roles, const.roles.CognitiveServicesOpenAIUser.key)) ? [
          {
            roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.CognitiveServicesOpenAIUser.guid)
            #disable-next-line BCP318
            principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
            resourceId: aiFoundryAccountResourceId
            principalType: 'ServicePrincipal'
          }
        ] : [],
        (deploySpeechService && contains(app.roles, const.roles.CognitiveServicesUser.key)) ? [
          {
            roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.CognitiveServicesUser.guid)
            #disable-next-line BCP318
            principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
            #disable-next-line BCP318
            resourceId: speechService.outputs.resourceId
            principalType: 'ServicePrincipal'
          }
        ] : [],
        (deployContainerRegistry && contains(app.roles, const.roles.AcrPull.key)) ? [
          {
            roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.AcrPull.guid)
            #disable-next-line BCP318
            principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
            #disable-next-line BCP318
            resourceId: containerRegistry.outputs.resourceId
            principalType: 'ServicePrincipal'
          }
        ] : [],
        (deploySearchService && contains(app.roles, const.roles.SearchIndexDataReader.key)) ? [
          {
            roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.SearchIndexDataReader.guid)
            #disable-next-line BCP318
            principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
            #disable-next-line BCP318
            resourceId: searchService.outputs.resourceId
            principalType: 'ServicePrincipal'
          }
        ] : [],
        (deploySearchService && contains(app.roles, const.roles.SearchIndexDataContributor.key)) ? [
          {
            roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.SearchIndexDataContributor.guid)
            #disable-next-line BCP318
            principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
            #disable-next-line BCP318
            resourceId: searchService.outputs.resourceId
            principalType: 'ServicePrincipal'
          }
        ] : [],
        (deployStorageAccount && contains(app.roles, const.roles.StorageBlobDataContributor.key)) ? [
          {
            roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.StorageBlobDataContributor.guid)
            #disable-next-line BCP318
            principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
            #disable-next-line BCP318
            resourceId: storageAccount.outputs.resourceId
            principalType: 'ServicePrincipal'
          }
        ] : [],
        (deployStorageAccount && contains(app.roles, const.roles.StorageBlobDataReader.key)) ? [
          {
            roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.StorageBlobDataReader.guid)
            #disable-next-line BCP318
            principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
            #disable-next-line BCP318
            resourceId: storageAccount.outputs.resourceId
            principalType: 'ServicePrincipal'
          }
        ] : [],
        (deployStorageAccount && contains(app.roles, const.roles.StorageBlobDelegator.key)) ? [
          {
            roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.StorageBlobDelegator.guid)
            #disable-next-line BCP318
            principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
            #disable-next-line BCP318
            resourceId: storageAccount.outputs.resourceId
            principalType: 'ServicePrincipal'
          }
        ] : []
      )
    }
  }
]

// Cross-service control-plane role assignments (consolidated; see #87).
// Each entry is conditionally included exactly as before; the underlying
// guid(principalId, roleDefinitionId, resourceId) keeps deployed role
// assignment GUIDs identical regardless of the deployment/module name.
var _crossServiceRoleAssignments = concat(
  // AI Foundry Account - Cognitive Services User -> Search Service (for agentic retrieval vectorizers)
  (deployAiFoundry && deploySearchService) ? [
    {
      #disable-next-line BCP318
      principalId: (_useUAI) ? searchServiceUAI.outputs.principalId : searchService.outputs.systemAssignedMIPrincipalId!
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.CognitiveServicesUser.guid)
      resourceId: aiFoundryAccountResourceId
      principalType: 'ServicePrincipal'
    }
  ] : [],
  // Storage Account - Storage Blob Data Reader -> Search Service
  (deployStorageAccount && deploySearchService) ? [
    {
      #disable-next-line BCP318
      principalId: (_useUAI) ? searchServiceUAI.outputs.principalId : searchService.outputs.systemAssignedMIPrincipalId!
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.StorageBlobDataReader.guid)
      #disable-next-line BCP318
      resourceId: storageAccount.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
  ] : [],
  // Search Service - Search Index Data Reader -> AiFoundryProject
  (deployAiFoundry && deploySearchService) ? [
    {
      principalId: aiFoundry!.outputs.aiProjectPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.SearchIndexDataReader.guid)
      #disable-next-line BCP318
      resourceId: searchService.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
  ] : [],
  // Storage Account - Storage Blob Data Reader -> AiFoundry Project
  (deployAiFoundry && deployStorageAccount) ? [
    {
      principalId: aiFoundry!.outputs.aiProjectPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', const.roles.StorageBlobDataReader.guid)
      #disable-next-line BCP318
      resourceId: storageAccount.outputs.resourceId
      principalType: 'ServicePrincipal'
    }
  ] : [],
  // Registry-mode-compatible pull role -> AI Foundry project identity.
  // The dedicated hosted-agent identity and its runtime roles are created by
  // `azd deploy`; the landing zone must not invent or replace that identity.
  (_hostedAgentPrerequisitesEnabled && deployAiFoundry) ? [
    {
      principalId: aiFoundry!.outputs.aiProjectPrincipalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', _hostedAgentContainerRegistryPullRoleId)
      resourceId: _hostedAgentContainerRegistryResourceId
      principalType: 'ServicePrincipal'
    }
  ] : []
)

module assignCrossServiceRoles 'modules/security/resource-role-assignment.bicep' = if ((deployAiFoundry && deploySearchService) || (deployStorageAccount && deploySearchService) || (deployAiFoundry && deployStorageAccount) || (_hostedAgentPrerequisitesEnabled && deployAiFoundry)) {
  name: 'assignCrossServiceRoles'
  params: {
    name: 'assignCrossServiceRoles'
    roleAssignments: _crossServiceRoleAssignments
  }
}

// Cosmos DB Account - Cosmos DB Built-in Data Contributor -> ContainerApp
module assignCosmosDBCosmosDbBuiltInDataContributorContainerApps 'modules/security/cosmos-data-plane-role-assignment.bicep' = [
  for (app, i) in containerAppsList: if (_deployContainerApps && deployCosmosDb && contains(
    app.roles,
    const.roles.CosmosDBBuiltInDataContributor.key
  )) {
    scope: resourceGroup(_applicationResourceGroupName)
    name: 'assignCosmosDBCosmosDbBuiltInDataContributor-${app.service_name}'
    params: {
      #disable-next-line BCP318
      cosmosDbAccountName: cosmosDBAccount.outputs.name
      #disable-next-line BCP318
      principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
      roleDefinitionGuid: const.roles.CosmosDBBuiltInDataContributor.guid
      scopePath: '/subscriptions/${subscription().subscriptionId}/resourceGroups/${_applicationResourceGroupName}/providers/Microsoft.DocumentDB/databaseAccounts/${resourceNames.dbAccountName}'
    }
  }
]

// NOTE: Search Service Contributor for the AI Foundry Project identity on the
// Search service is already created by the AVM AI Foundry module (avm/ptn/ai-ml/ai-foundry)
// when aiSearchConfiguration is provided. Creating it again here causes a
// RoleAssignmentExists conflict because both produce the same deterministic GUID.
// Intentionally omitted.

//////////////////////////////////////////////////////////////////////////
// App Configuration Settings Service
//////////////////////////////////////////////////////////////////////////

// App Configuration Store
//////////////////////////////////////////////////////////////////////////

module appConfig 'modules/application/app-configuration-store.bicep' = if (deployAppConfig) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'applicationConfiguration'
  params: {
    name: resourceNames.appConfigName
    location: location
    tags: _tags
    networkIsolation: _networkIsolation
    publicNetworkAccess: _publicNetworkAccess
    principalId: principalId
    principalType: principalType
    dataOwnerRoleGuid: const.roles.AppConfigurationDataOwner.guid
  }
}

// prepare the container apps settings for the app configuration store
module containerAppsSettings 'modules/container-apps/container-apps-list.bicep' = if (_deployContainerApps) {
  name: 'containerAppsSettings'
  params: {
    appConfigLabel: appConfigLabel
    containerAppsList: [
      for i in range(0, length(containerAppsList)): {
        #disable-next-line BCP318
        name: containerApps[i].outputs.name
        serviceName: containerAppsList[i].service_name
        canonical_name: containerAppsList[i].canonical_name
        #disable-next-line BCP318
        principalId: (_useUAI) ? containerAppsUAI[i].outputs.principalId : containerApps[i].outputs.systemAssignedMIPrincipalId!
        #disable-next-line BCP318
        fqdn: containerApps[i].outputs.fqdn
      }
    ]
  }
}

// Optional Public Ingress (#49) — Application Gateway WAF v2 in front of the
// internal Container Apps environment. See `modules/networking/public-ingress.bicep`
// and the README "Optional Public Ingress" section for the runbook.
module publicIngressM 'modules/networking/public-ingress.bicep' = if (_publicIngressEnabled) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'publicIngressDeployment'
  params: {
    namePrefix: 'agw-${resourceToken}'
    location: location
    tags: _tags
    #disable-next-line BCP318
    appGatewaySubnetResourceId: '${virtualNetworkResourceId}/subnets/${azureAppGatewaySubnetName}'
    logAnalyticsWorkspaceResourceId: _lawResourceId
    #disable-next-line BCP318
    backendAppFqdn: containerApps[_publicIngressBackendIndex].outputs.fqdn
    useZoneRedundancy: useZoneRedundancy
    wafMode: publicIngress.?wafMode ?? 'Prevention'
    wafCustomRules: publicIngress.?wafCustomRules ?? []
    capacity: publicIngress.?capacity ?? { minCapacity: 0, maxCapacity: 2 }
    sslPolicy: publicIngress.?sslPolicy ?? {}
    sslCertSecretId: publicIngress.?sslCertSecretId ?? ''
    frontendHostName: publicIngress.?frontendHostName ?? ''
    keyVaultResourceId: deployKeyVault ? keyVault.outputs.resourceId : ''
    keyVaultName: deployKeyVault ? resourceNames.keyVaultName : ''
  }
}

// prepare the model deployment names for the app configuration store
var _modelDeploymentNamesSettings = [
  for modelDeployment in modelDeploymentList: {
    name: modelDeployment.canonical_name
    value: modelDeployment.name
    label: appConfigLabel
    contentType: 'text/plain'
  }
]

// prepare the database container names for the app configuration store
var _databaseContainerNamesSettings = [
  for databaseContainer in databaseContainersList: {
    name: databaseContainer.canonical_name
    value: databaseContainer.name
    label: appConfigLabel
    contentType: 'text/plain'
  }
]

// prepare the storage container names for the app configuration store
var _storageContainerNamesSettings = [
  for storageContainer in storageAccountContainersList: {
    name: storageContainer.canonical_name
    value: storageContainer.name
    label: appConfigLabel
    contentType: 'text/plain'
  }
]

var _modelDeploymentSettings = [
  for modelDeployment in modelDeploymentList: { 
    canonical_name: modelDeployment.canonical_name 
    capacity: modelDeployment.sku.capacity          
    model: modelDeployment.model.name                  
    modelFormat: modelDeployment.model.format          
    name: modelDeployment.name
    version: modelDeployment.model.version         
    apiVersion: modelDeployment.?apiVersion ?? '2025-01-01-preview' 
    endpoint: 'https://${resourceNames.aiFoundryAccountName}.openai.azure.com/'
  }
]

// Populate App Configuration store with Container App API keys (only when useAPIKeys is true).
module appConfigKeyVaultPopulate 'modules/app-configuration/app-configuration.bicep' = if (_deployContainerApps && deployAppConfig && _runtimeConfigIsAppConfig && deployKeyVault && _useCAppAPIKey) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'appConfigKeyVaultPopulate'
  params: {
    #disable-next-line BCP318
    storeName: appConfig.outputs.name
    keyValues:  [ 
      for app in containerAppsList: {
            name: '${app.canonical_name}_APIKEY'
            #disable-next-line BCP318
            value: '{"uri":"${keyVault.outputs.properties.vaultUri}secrets/${replace(app.canonical_name, '_', '-')}-APIKEY"}'
            label: appConfigLabel
            contentType: 'application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8'
      }
    ]
  }
}

module cosmosConfigKeyVaultPopulate 'modules/app-configuration/app-configuration.bicep' = if (deployCosmosDb && deployAppConfig && _runtimeConfigIsAppConfig && !_networkIsolation) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'cosmosConfigKeyVaultPopulate'
  params: {
    #disable-next-line BCP318
    storeName: appConfig.outputs.name
    keyValues: concat(
      [
        #disable-next-line BCP318
      { name: 'COSMOS_DB_ACCOUNT_RESOURCE_ID', value: cosmosDBAccount.outputs.resourceId, label: appConfigLabel, contentType: 'text/plain' }
      #disable-next-line BCP318
      { name: 'COSMOS_DB_ENDPOINT',              value: cosmosDBAccount.outputs.endpoint,            label: appConfigLabel, contentType: 'text/plain' }
      ]
    )
  }
}

// Normalize accelerator-supplied App Configuration passthrough entries so every item carries a label and contentType. The app-configuration module reads both unconditionally, so a missing label defaults to appConfigLabel and a missing contentType defaults to text/plain.
var _normalizedAdditionalAppConfigSettings = [
  for s in additionalAppConfigurationSettings: {
    name: s.name
    value: s.value
    label: s.?label ?? appConfigLabel
    contentType: s.?contentType ?? 'text/plain'
  }
]

// Collision keys for the passthrough, derived exactly how the app-configuration module names each key-value resource (name$label, or name when the label is empty). Used to drop any landing-zone key the passthrough overrides, so the passthrough always wins without emitting a duplicate resource name.
var _additionalAppConfigKeys = map(_normalizedAdditionalAppConfigSettings, s => empty(s.label) ? s.name : '${s.name}$${s.label}')

module appConfigPopulate 'modules/app-configuration/app-configuration.bicep' = if (deployAppConfig && _runtimeConfigIsAppConfig && !_networkIsolation) {
  scope: resourceGroup(_applicationResourceGroupName)
  name: 'appConfigPopulate'
  params: {
    #disable-next-line BCP318
    storeName: appConfig.outputs.name
    keyValues: concat(
      filter(
      concat(
      #disable-next-line BCP318
      _deployContainerApps ? containerAppsSettings.outputs.containerAppsEndpoints : [],
      #disable-next-line BCP318
      _deployContainerApps ? containerAppsSettings.outputs.containerAppsName : [],
      _modelDeploymentNamesSettings,
      _databaseContainerNamesSettings,
      _storageContainerNamesSettings,
      [
        // ── General / Deployment ─────────────────────────────────────────────
      { name: 'AZURE_TENANT_ID',     value: tenant().tenantId,                      label: appConfigLabel, contentType: 'text/plain' }
      { name: 'SUBSCRIPTION_ID',     value: subscription().subscriptionId,          label: appConfigLabel, contentType: 'text/plain' }
      { name: 'AZURE_RESOURCE_GROUP', value: resourceGroup().name,                  label: appConfigLabel, contentType: 'text/plain' }
      { name: 'AZURE_APP_RESOURCE_GROUP', value: _applicationResourceGroupName, label: 'agent-lz', contentType: 'text/plain' }
      { name: 'AZURE_NETWORK_RESOURCE_GROUP', value: _networkResourceGroupName, label: 'agent-lz', contentType: 'text/plain' }
      { name: 'LOCATION',            value: location,                               label: appConfigLabel, contentType: 'text/plain' }
      { name: 'ENVIRONMENT_NAME',    value: environmentName,                        label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DEPLOYMENT_NAME',     value: deployment().name,                      label: appConfigLabel, contentType: 'text/plain' }
      { name: 'RESOURCE_TOKEN',      value: resourceToken,                          label: appConfigLabel, contentType: 'text/plain' }
      { name: 'NETWORK_ISOLATION',   value: toLower(string(_networkIsolation)),      label: appConfigLabel, contentType: 'text/plain' }
      { name: 'SEARCH_RAG_INDEX_NAME', value: 'ragindex-${resourceToken}',           label: appConfigLabel, contentType: 'text/plain' }
      { name: 'ENABLE_AGENTIC_RETRIEVAL', value: toLower(string(enableAgenticRetrieval)), label: appConfigLabel, contentType: 'text/plain' }
      { name: 'RETRIEVAL_BACKEND', value: retrievalBackend, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_PATTERN', value: foundryIqPattern, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_API_VERSION', value: retrievalBackend == 'foundry_iq' ? foundryIqApiVersion : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_KNOWLEDGE_RETRIEVAL_BILLING_PLAN', value: retrievalBackend == 'foundry_iq' ? foundryIqKnowledgeRetrievalBillingPlan : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME', value: retrievalBackend == 'foundry_iq' ? foundryIqKnowledgeSourceName : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND', value: effectiveFoundryIqKnowledgeSourceKind, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_STORAGE_CONTAINER_NAME', value: retrievalBackend == 'foundry_iq' && foundryIqPattern != 'searchIndex' ? foundryIqStorageContainerName : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_STORAGE_FOLDER_PATH', value: retrievalBackend == 'foundry_iq' && foundryIqPattern != 'searchIndex' ? foundryIqStorageFolderPath : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_IS_ADLS_GEN2', value: retrievalBackend == 'foundry_iq' && foundryIqPattern != 'searchIndex' ? toLower(string(foundryIqIsAdlsGen2)) : 'false', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_CONTENT_EXTRACTION_MODE', value: retrievalBackend == 'foundry_iq' && foundryIqPattern != 'searchIndex' ? foundryIqContentExtractionMode : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_AI_SERVICES_ENDPOINT', value: retrievalBackend == 'foundry_iq' && foundryIqPattern != 'searchIndex' ? (!empty(foundryIqAiServicesEndpoint) ? foundryIqAiServicesEndpoint : 'https://${resourceNames.aiFoundryAccountName}.services.ai.azure.com/') : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS', value: retrievalBackend == 'foundry_iq' && foundryIqPattern != 'searchIndex' ? string(effectiveFoundryIqIngestionPermissionOptions) : '[]', label: appConfigLabel, contentType: 'application/json' }
      { name: 'FOUNDRY_IQ_SEARCH_INDEX_NAME', value: retrievalBackend == 'foundry_iq' && foundryIqPattern == 'searchIndex' ? foundryIqSearchIndexName : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_SEMANTIC_CONFIGURATION_NAME', value: retrievalBackend == 'foundry_iq' && foundryIqPattern == 'searchIndex' ? foundryIqSemanticConfigurationName : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_SOURCE_DATA_FIELDS', value: string(foundryIqSourceDataFields), label: appConfigLabel, contentType: 'application/json' }
      { name: 'FOUNDRY_IQ_SEARCH_FIELDS', value: string(foundryIqSearchFields), label: appConfigLabel, contentType: 'application/json' }
      { name: 'FOUNDRY_IQ_BASE_FILTER', value: retrievalBackend == 'foundry_iq' && foundryIqPattern == 'searchIndex' ? foundryIqBaseFilter : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_FILTER_ADD_ON_ENABLED', value: retrievalBackend == 'foundry_iq' && foundryIqPattern == 'searchIndex' ? toLower(string(foundryIqFilterAddOnEnabled)) : 'false', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_SECURITY_FIELD_NAME', value: retrievalBackend == 'foundry_iq' && foundryIqPattern == 'searchIndex' ? foundryIqSecurityFieldName : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'FOUNDRY_IQ_MAX_OUTPUT_DOCUMENTS', value: retrievalBackend == 'foundry_iq' ? foundryIqMaxOutputDocuments : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'USE_UAI',             value: string(_useUAI),                        label: appConfigLabel, contentType: 'text/plain' }
      { name: 'LOG_LEVEL',           value: 'INFO',                                 label: appConfigLabel, contentType: 'text/plain' }
      { name: 'ENABLE_CONSOLE_LOGGING', value: 'true',                              label: appConfigLabel, contentType: 'text/plain' }
      { name: 'RELEASE',     value: _manifest.tag,                      label: appConfigLabel, contentType: 'text/plain' }
      { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: _appInsightsConnectionString,   label: appConfigLabel, contentType: 'text/plain' }
      { name: 'APPLICATIONINSIGHTS__INSTRUMENTATIONKEY', value: _appInsightsInstrumentationKey, label: appConfigLabel, contentType: 'text/plain' }

      //── Resource IDs ─────────────────────────────────────────────────────
      #disable-next-line BCP318
      { name: 'KEY_VAULT_RESOURCE_ID', value: deployKeyVault ? keyVault.outputs.resourceId : '', label: appConfigLabel, contentType: 'text/plain' }
      #disable-next-line BCP318
      { name: 'STORAGE_ACCOUNT_RESOURCE_ID', value: deployStorageAccount ? storageAccount.outputs.resourceId : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID', value: _documentsContainerResourceId, label: 'agent-lz', contentType: 'text/plain' }
      { name: 'APP_INSIGHTS_RESOURCE_ID', value: _appInsightsResourceId, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'LOG_ANALYTICS_RESOURCE_ID', value: _lawResourceId, label: appConfigLabel, contentType: 'text/plain' }
      #disable-next-line BCP318
      { name: 'CONTAINER_ENV_RESOURCE_ID', value: deployContainerEnv ? containerEnv.outputs.resourceId : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'AI_FOUNDRY_ACCOUNT_RESOURCE_ID', value: (deployAiFoundry) ? aiFoundryAccountResourceId : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'AI_FOUNDRY_PROJECT_RESOURCE_ID', value: (deployAiFoundry) ? aiFoundryProjectResourceId : '', label: appConfigLabel, contentType: 'text/plain' }
      // { name: 'AI_FOUNDRY_PROJECT_WORKSPACE_ID', value: (deployAiFoundry) ? aiFoundryFormatProjectWorkspaceId!.outputs.projectWorkspaceIdGuid : '', label: appConfigLabel, contentType: 'text/plain' }
      #disable-next-line BCP318
      { name: 'SEARCH_SERVICE_UAI_RESOURCE_ID', value: (deploySearchService && _useUAI) ? searchServiceUAI.outputs.resourceId : '', label: appConfigLabel, contentType: 'text/plain' }
      #disable-next-line BCP318
      { name: 'SEARCH_SERVICE_RESOURCE_ID', value: deploySearchService ? searchService.outputs.resourceId : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'SEARCH_SHARED_PRIVATE_LINKS', value: string(searchSharedPrivateLinkReadinessManifest), label: appConfigLabel, contentType: 'application/json' }
      #disable-next-line BCP318
      { name: 'KNOWLEDGE_BASE_CONNECTION_ID', value: retrievalBackend == 'foundry_iq' && deploySearchService && deployAiFoundry ? aiFoundryKnowledgeBaseSearchConnection.outputs.searchConnectionId : '', label: appConfigLabel, contentType: 'text/plain' }
      #disable-next-line BCP318
      { name: 'AZURE_SPEECH_RESOURCE_ID', value: deploySpeechService ? speechService.outputs.resourceId : '', label: appConfigLabel, contentType: 'text/plain' }
      
      // ── Resource Names ───────────────────────────────────────────────────
      { name: 'AI_FOUNDRY_ACCOUNT_NAME', value: resourceNames.aiFoundryAccountName, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'AI_FOUNDRY_PROJECT_NAME', value: resourceNames.aiFoundryProjectName, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'AI_FOUNDRY_STORAGE_ACCOUNT_NAME', value: resourceNames.aiFoundryStorageAccountName, label: appConfigLabel, contentType: 'text/plain'}
      { name: 'APP_CONFIG_NAME', value: resourceNames.appConfigName, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'APP_INSIGHTS_NAME', value: resourceNames.appInsightsName, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'CONTAINER_ENV_NAME', value: resourceNames.containerEnvName, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'CONTAINER_REGISTRY_NAME', value: resourceNames.containerRegistryName, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'CONTAINER_REGISTRY_LOGIN_SERVER', value: '${resourceNames.containerRegistryName}.azurecr.io', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DATABASE_ACCOUNT_NAME', value: resourceNames.dbAccountName, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DATABASE_NAME', value: resourceNames.dbDatabaseName, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'SEARCH_SERVICE_NAME', value: resourceNames.searchServiceName, label: appConfigLabel, contentType: 'text/plain' }
      { name: 'AZURE_SPEECH_RESOURCE_NAME', value: deploySpeechService ? resourceNames.speechServiceName : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'AZURE_SPEECH_REGION', value: deploySpeechService ? _speechServiceLocation : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'STORAGE_ACCOUNT_NAME', value: resourceNames.storageAccountName, label: appConfigLabel, contentType: 'text/plain' }

      // ── Feature flagging ─────────────────────────────────────────────────
      { name: 'DEPLOY_APP_CONFIG', value: string(deployAppConfig), label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DEPLOY_KEY_VAULT', value: string(deployKeyVault), label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DEPLOY_LOG_ANALYTICS', value: string(deployLogAnalytics), label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DEPLOY_APP_INSIGHTS', value: string(deployAppInsights), label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DEPLOY_SEARCH_SERVICE', value: string(deploySearchService), label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DEPLOY_SPEECH_SERVICE', value: string(deploySpeechService), label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DEPLOY_STORAGE_ACCOUNT', value: string(deployStorageAccount), label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DEPLOY_COSMOS_DB', value: string(deployCosmosDb), label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DEPLOY_CONTAINER_APPS', value: string(deployContainerApps), label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DEPLOY_CONTAINER_REGISTRY', value: string(deployContainerRegistry), label: appConfigLabel, contentType: 'text/plain' }
      { name: 'DEPLOY_CONTAINER_ENV', value: string(deployContainerEnv), label: appConfigLabel, contentType: 'text/plain' }

      // ── Endpoints / URIs ──────────────────────────────────────────────────
      #disable-next-line BCP318
      { name: 'KEY_VAULT_URI',                   value: deployKeyVault ? keyVault.outputs.properties.vaultUri : '',                        label: appConfigLabel, contentType: 'text/plain' }
      #disable-next-line BCP318
      { name: 'STORAGE_BLOB_ENDPOINT',           value: deployStorageAccount ? storageAccount.outputs.primaryBlobEndpoint : '',  label: appConfigLabel, contentType: 'text/plain' }
      { name: 'AI_FOUNDRY_ACCOUNT_ENDPOINT',     value: (deployAiFoundry) ? aiFoundryAccountEndpoint : '', label: appConfigLabel, contentType: 'text/plain' }      
      { name: 'AI_FOUNDRY_PROJECT_ENDPOINT',     value: (deployAiFoundry) ? aiFoundryProjectEndpoint : '', label: appConfigLabel, contentType: 'text/plain' }
      #disable-next-line BCP318
      { name: 'SEARCH_SERVICE_QUERY_ENDPOINT',   value: deploySearchService ? searchService.outputs.endpoint : '',              label: appConfigLabel, contentType: 'text/plain' }
      #disable-next-line BCP318
      { name: 'KNOWLEDGE_BASE_ENDPOINT', value: retrievalBackend == 'foundry_iq' && deploySearchService ? searchService.outputs.endpoint : '', label: appConfigLabel, contentType: 'text/plain' }
      #disable-next-line BCP318
      { name: 'AZURE_SPEECH_ENDPOINT', value: deploySpeechService ? speechService.outputs.endpoint : '', label: appConfigLabel, contentType: 'text/plain' }

      // ── Connections ───────────────────────────────────────────────────────
      #disable-next-line BCP318
      { name: 'SEARCH_CONNECTION_ID', value: deploySearchService && deployAiFoundry ? aiFoundryConnectionSearch.outputs.searchConnectionId : '', label: appConfigLabel, contentType: 'text/plain' }
      { name: 'KNOWLEDGE_BASE_NAME', value: retrievalBackend == 'foundry_iq' ? knowledgeBaseName : '', label: appConfigLabel, contentType: 'text/plain' }
      #disable-next-line BCP318
      { name: 'BING_CONNECTION_ID', value: deployGroundingWithBing && deployAiFoundry ? bingSearchConnection!.outputs.bingConnectionId : '', label: appConfigLabel, contentType: 'text/plain' }

      //── Managed Identity Principals ───────────────────────────────────────
      #disable-next-line BCP318
      { name: 'CONTAINER_ENV_PRINCIPAL_ID', value: deployContainerEnv ? ((_useUAI) ? containerEnvUAI.outputs.principalId : (containerEnv.outputs.identity.?principalId ?? '')) : '', label: appConfigLabel, contentType: 'text/plain' }
      #disable-next-line BCP318
      { name: 'SEARCH_SERVICE_PRINCIPAL_ID', value: deploySearchService ? ((_useUAI) ? searchServiceUAI.outputs.principalId : searchService.outputs.systemAssignedMIPrincipalId!) : '', label: appConfigLabel, contentType: 'text/plain' }

      // ── Container Apps List & Model Deployments ────────────────────────────
      #disable-next-line BCP318
      { name: 'CONTAINER_APPS', value: _deployContainerApps ? string(containerAppsSettings.outputs.containerAppsList) : '[]', label: appConfigLabel, contentType: 'application/json' }
      { name: 'MODEL_DEPLOYMENTS', value: string(_modelDeploymentSettings), label: appConfigLabel, contentType: 'application/json' }

    ]
      ),
      kv => !contains(_additionalAppConfigKeys, empty(kv.label) ? kv.name : '${kv.name}$${kv.label}')
      ),
      _normalizedAdditionalAppConfigSettings
    )
  }
}

//////////////////////////////////////////////////////////////////////////
// OUTPUTS
//////////////////////////////////////////////////////////////////////////

// ──────────────────────────────────────────────────────────────────────
// General / Deployment
// ──────────────────────────────────────────────────────────────────────
output TENANT_ID string = tenant().tenantId
output SUBSCRIPTION_ID string = subscription().subscriptionId
output AZURE_RESOURCE_GROUP string = resourceGroup().name

@description('Effective application resource group; defaults to the Foundry/root group.')
output AZURE_APP_RESOURCE_GROUP string = _applicationResourceGroupName

@description('Effective locally owned networking resource group; explicit BYO resources retain their actual IDs.')
output AZURE_NETWORK_RESOURCE_GROUP string = _networkResourceGroupName

output LOCATION string = location
output ENVIRONMENT_NAME string = environmentName
output DEPLOYMENT_NAME string = deployment().name
output RESOURCE_TOKEN string = resourceToken
output NETWORK_ISOLATION bool = _networkIsolation
output USE_UAI bool = _useUAI
output USE_CAPP_API_KEY bool = _useCAppAPIKey
output RELEASE string = _manifest.tag
output APP_RUNTIME_CONFIGURATION_MODE string = appRuntimeConfigurationMode

// ──────────────────────────────────────────────────────────────────────
// Feature flagging
// ──────────────────────────────────────────────────────────────────────
output DEPLOY_APP_CONFIG bool = deployAppConfig
output DEPLOY_SOFTWARE bool = deploySoftware
output DEPLOY_KEY_VAULT bool = deployKeyVault
output DEPLOY_LOG_ANALYTICS bool = deployLogAnalytics
output DEPLOY_APP_INSIGHTS bool = deployAppInsights
output DEPLOY_SEARCH_SERVICE bool = deploySearchService
output DEPLOY_SPEECH_SERVICE bool = deploySpeechService
output DEPLOY_STORAGE_ACCOUNT bool = deployStorageAccount
output DEPLOY_COSMOS_DB bool = deployCosmosDb
output DEPLOY_CONTAINER_APPS bool = deployContainerApps
output DEPLOY_CONTAINER_REGISTRY bool = deployContainerRegistry
output DEPLOY_CONTAINER_ENV bool = deployContainerEnv
output DEPLOY_VM_KEY_VAULT bool = deployVmKeyVault

@description('Name of the ACR Task agent pool when deployed. Empty when not deployed.')
output ACR_TASK_AGENT_POOL string = _deployAcrTaskAgentPool ? acrTaskAgentPoolName : ''

// ──────────────────────────────────────────────────────────────────────
// Endpoints / URIs
// ──────────────────────────────────────────────────────────────────────
#disable-next-line BCP318
output APP_CONFIG_ENDPOINT string = deployAppConfig ? appConfig.outputs.properties.endpoint : ''
@description('Application Key Vault URI for downstream bootstrap. Empty when Key Vault is not deployed.')
output KEY_VAULT_URI string = deployKeyVault ? keyVault!.outputs.properties.vaultUri : ''
output RETRIEVAL_BACKEND string = retrievalBackend
output FOUNDRY_IQ_PATTERN string = foundryIqPattern
output KNOWLEDGE_BASE_NAME string = retrievalBackend == 'foundry_iq' ? knowledgeBaseName : ''
#disable-next-line BCP318
output KNOWLEDGE_BASE_ENDPOINT string = retrievalBackend == 'foundry_iq' && deploySearchService ? searchService.outputs.endpoint : ''
#disable-next-line BCP318
output KNOWLEDGE_BASE_CONNECTION_ID string = retrievalBackend == 'foundry_iq' && deploySearchService && deployAiFoundry ? aiFoundryKnowledgeBaseSearchConnection.outputs.searchConnectionId : ''
output FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME string = retrievalBackend == 'foundry_iq' ? foundryIqKnowledgeSourceName : ''
output FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND string = effectiveFoundryIqKnowledgeSourceKind

// Azure AI Speech (#35)
#disable-next-line BCP318
output AZURE_SPEECH_RESOURCE_ID string = deploySpeechService ? speechService.outputs.resourceId : ''
#disable-next-line BCP318
output AZURE_SPEECH_ENDPOINT string = deploySpeechService ? speechService.outputs.endpoint : ''
output AZURE_SPEECH_REGION string = deploySpeechService ? _speechServiceLocation : ''
output AZURE_SPEECH_RESOURCE_NAME string = deploySpeechService ? resourceNames.speechServiceName : ''

// ──────────────────────────────────────────────────────────────────────
// Public Ingress (#49) — surface the gateway for downstream automation
// (DNS A record, NSG audit, health checks). Empty when not deployed.
// ──────────────────────────────────────────────────────────────────────
output PUBLIC_INGRESS_ENABLED bool = _publicIngressEnabled
#disable-next-line BCP318
output PUBLIC_INGRESS_PUBLIC_IP string = _publicIngressEnabled ? publicIngressM!.outputs.publicIp : ''
#disable-next-line BCP318
output PUBLIC_INGRESS_PUBLIC_IP_RESOURCE_ID string = _publicIngressEnabled ? publicIngressM!.outputs.publicIpResourceId : ''
#disable-next-line BCP318
output PUBLIC_INGRESS_GATEWAY_RESOURCE_ID string = _publicIngressEnabled ? publicIngressM!.outputs.gatewayResourceId : ''
#disable-next-line BCP318
output PUBLIC_INGRESS_NSG_RESOURCE_ID string = _publicIngressEnabled ? appGwNsg!.outputs.id : ''
#disable-next-line BCP318
output PUBLIC_INGRESS_WAF_POLICY_RESOURCE_ID string = _publicIngressEnabled ? publicIngressM!.outputs.wafPolicyResourceId : ''
#disable-next-line BCP318
output PUBLIC_INGRESS_IDENTITY_PRINCIPAL_ID string = _publicIngressEnabled ? publicIngressM!.outputs.identityPrincipalId : ''
#disable-next-line BCP318
output PUBLIC_INGRESS_LIVE bool = _publicIngressEnabled ? publicIngressM!.outputs.liveMode : false

// Landing-zone outputs that the public-ingress module (or external consumers)
// depend on. Surfacing these unconditionally aligns with #49.
output APP_GATEWAY_SUBNET_RESOURCE_ID string = _networkIsolation ? '${virtualNetworkResourceId}/subnets/${azureAppGatewaySubnetName}' : ''
output VNET_RESOURCE_ID string = virtualNetworkResourceId
#disable-next-line BCP318
output KEY_VAULT_RESOURCE_ID string = deployKeyVault ? keyVault.outputs.resourceId : ''
output KEY_VAULT_NAME string = deployKeyVault ? resourceNames.keyVaultName : ''
#disable-next-line BCP318
output LOG_ANALYTICS_RESOURCE_ID string = _lawResourceId
output APP_INSIGHTS_RESOURCE_ID string = _appInsightsResourceId
output OBSERVABILITY_MIXED_WORKSPACES_ALLOWED bool = allowMixedObservabilityWorkspaces
#disable-next-line BCP318
output CONTAINER_APP_INTERNAL_FQDN string = (_deployContainerApps && length(containerAppsList) > 0) ? containerApps[_publicIngressBackendIndex].outputs.fqdn : ''

// Microsoft Foundry hosted-agent deployment handoff. The actual agent version,
// dedicated agent identity, and invocation endpoint are data-plane resources
// created by the downstream `azure.ai.agent` service during `azd deploy`.
output DEPLOY_HOSTED_AGENT bool = deployHostedAgent
@description('True when hosted-agent prerequisites were selected through prepareHostedAgent or deployHostedAgent. This does not indicate that a hosted agent version exists.')
output HOSTED_AGENT_PREPARED bool = _hostedAgentPrerequisitesEnabled
@description('Provisioned Foundry project ID for application deployment, including custom applications in classic topology.')
output AZURE_AI_PROJECT_RESOURCE_ID string = (deployAiFoundry || _hostedAgentPrerequisitesEnabled) ? aiFoundryProjectResourceId : ''
@description('Provisioned Foundry project endpoint, independent of bundled hosted-agent selection.')
output AZURE_AI_PROJECT_ENDPOINT string = (deployAiFoundry || _hostedAgentPrerequisitesEnabled) ? aiFoundryProjectEndpoint : ''
@description('Provisioned registry ID, or the declared external hosted-agent registry when hosted prerequisites are selected.')
output AZURE_CONTAINER_REGISTRY_RESOURCE_ID string = (deployContainerRegistry || _hostedAgentPrerequisitesEnabled) ? _hostedAgentContainerRegistryResourceId : ''
@description('Provisioned registry login server for application builds and immutable image deployment.')
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = (deployContainerRegistry || _hostedAgentPrerequisitesEnabled) ? _hostedAgentContainerRegistryEndpoint : ''
#disable-next-line BCP318
output HOSTED_AGENT_DEPLOYMENT object = {
  workloadEgress: {
    networkIsolation: _networkIsolation
    managedFirewallPolicyId: firewall.outputs.policyResourceId
    subnets: {
      containerapp: _caEnvSubnetId
      'azure.ai.agent': _agentSubnetId
    }
  }
  enabled: deployHostedAgent
  agent: deployHostedAgent ? {
    name: hostedAgent.name
    image: _hostedAgentImageReference
    imageVersion: hostedAgent.version
    startupCommand: hostedAgent.startupCommand
    runtime: hostedAgent.runtime
    protocols: hostedAgent.protocols
  } : null
  foundry: _hostedAgentPrerequisitesEnabled ? {
    projectResourceId: aiFoundryProjectResourceId
    projectEndpoint: aiFoundryProjectEndpoint
    projectPrincipalId: aiFoundry!.outputs.aiProjectPrincipalId
    agentSubnetResourceId: _agentSubnetId
  } : null
  containerRegistry: _hostedAgentPrerequisitesEnabled ? {
    resourceId: _hostedAgentContainerRegistryResourceId
    endpoint: _hostedAgentContainerRegistryEndpoint
  } : null
  privateBuild: {
    required: _hostedAgentPrerequisitesEnabled && _networkIsolation
    subnetResourceId: (_hostedAgentPrerequisitesEnabled && _networkIsolation) ? '${virtualNetworkResourceId}/subnets/${devopsBuildAgentsSubnetName}' : ''
    jumpboxResourceId: (_hostedAgentPrerequisitesEnabled && _networkIsolation) ? (_deployJumpbox ? testVm!.outputs.resourceId : (existingJumpboxResourceId ?? '')) : ''
    acrTaskAgentPoolName: (_hostedAgentPrerequisitesEnabled && _deployAcrTaskAgentPool) ? acrTaskAgentPoolName : ''
  }
}
