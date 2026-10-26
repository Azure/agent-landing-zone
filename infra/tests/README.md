# AI Landing Zone — Test harness

> Scope: deterministic offline contract checks plus the issue #58 (v2.0.0)
> live integration harness.

This directory contains offline checks used by CI and a purpose-built
hub-and-spoke fixture for validating v2.0.0 deliverables end-to-end against a
real Azure subscription. The live fixture is **not** required to use the landing
zone; it exists to reproduce the two synthetic scenarios in issue #58.

## Conventions

| Concept | Convention |
|---|---|
| Test subscription | `9788a92c-2f71-4629-8173-7ad449cb50e1` |
| Hub resource group | `rg-ailz-hub` (singleton; reused across tests) |
| Spoke resource group | `rg-ailz-spoke-MMDDYYHHMM` (timestamp; one per `azd provision` run) |
| Hub location | `eastus2` |
| Hub address space | `10.100.0.0/16` (non-overlapping with default spoke `192.168.0.0/21`) |
| Cleanup | Manual — operator inspects and deletes RGs explicitly. Hub is intentionally long-lived to avoid 30-minute re-provision delays |

## Directory layout

```
tests/
├── README.md                 (this file)
├── contracts/
│   ├── Test-HostedAgentContract.ps1
│   ├── Test-AcrTaskAgentPoolFirewallContract.ps1
│   ├── Test-AcrTaskAgentPoolSubnetContract.ps1
│   ├── Test-ResourceGroupScopesContract.ps1
│   ├── Test-SolutionStorageAccessContract.ps1
│   ├── Test-FoundrySharedPrivateLinkNameContract.ps1
│   ├── Test-MaintenanceConfigurationWrapperContract.ps1
│   ├── Test-ComponentDeploymentFlagsContract.ps1
│   ├── Test-CosmosDeploymentNameContract.ps1
│   └── fixtures/
│       ├── hosted-agent-resource-graph.json
│       └── maintenance-configuration/
│           └── main.bicep
├── hub/
│   ├── main.bicep            (test hub: VNet, Firewall, Bastion, LAW)
│   ├── main.parameters.json
│   └── .outputs.json         (gitignored — captured outputs from last deploy)
└── scripts/
    ├── Deploy-Hub.ps1        (idempotent hub deployer + output capture)
    ├── Measure-MainJsonSize.Tests.ps1
    └── Invoke-PreflightChecks.Tests.ps1
```

## Offline contract checks

Run from the umbrella repository root (PowerShell 7, Azure CLI Bicep
**0.42.1**, `powershell-yaml` **0.4.12** or later). The compiler version is
the historical fixtures' version, not an infrastructure or runtime component pin:

```pwsh
az config set bicep.use_binary_from_path=false
az bicep install --version v0.42.1
Install-Module powershell-yaml -RequiredVersion 0.4.12 -Scope CurrentUser -Repository PSGallery -Force -ErrorAction Stop
pwsh -NoProfile -File infra/tests/Invoke-OfflineContracts.ps1

# Separate parity/schema/provenance suite; requires Node.js and pinned packages.
npm --prefix infra ci --no-audit --no-fund
npm --prefix infra run test:parity
```

The offline runner executes every `contracts/Test-*Contract.ps1` and
`scripts/*.Tests.ps1`, reports each exit code and elapsed time, and fails if any
gate fails. Compiler scratch files and native runtime extraction stay in a
unique directory under `infra/tests/`, removed in `finally`. It does not execute
the live hub/spoke scripts or make Azure writes. The parity suite remains
separate: a historical source/approval/provenance failure must be reported, not
resolved by changing source pins or waiving a gate. The copied
`infra/.github/workflows/` are not active umbrella workflows; active CI must
invoke these commands explicitly.

The scoped-resource-group integration run passed all **16** offline entrypoints
in **703.4 seconds** on Windows with Azure CLI Bicep 0.42.1, including 139 scope
assertions, 14 normalization mutation rejections, the original hosted/Storage
fingerprints, and split/wrong-group operator authorization. No Azure deployment,
what-if, live RBAC or DNS validation was performed.

The smallest umbrella CI addition is the single offline-runner command above,
replacing the standalone resource-group-contract invocation so it is not run
twice. Keep the existing build/lint steps and install the fixture compiler with
`az bicep install --version v0.42.1`. Active CI also installs the PowerShell
module above. The measured offline run fits the current 30-minute build job;
parity is a separate command with the provenance limitations below.

### Historical parity provenance

The full 17-entrypoint parity verification in this umbrella checkout has
12 passing entrypoints and five pre-existing provenance failures, separate from
the compiled foundation contracts:

| Entrypoint | Existing failure |
| --- | --- |
| `Test-InventoryCoverage.Tests.ps1` | Historical commit `64195c01b70974fa7256c2f54a0035fb06804139` does not contain root `main.bicep` in the umbrella repository. |
| `Invoke-ParityWorkflow.Tests.ps1` | Historical commit `54d18f53273082dd12f0cab0689ec7968e845950` does not contain root `parity/inventory.json`. |
| `Test-ParityPerformance.Tests.ps1` | Aggregate validation and Markdown export stop at that missing committed inventory. |
| `Test-NewTerraformHandoff.Tests.ps1` | Its historical `5dd04b6e…` inventory digest differs from the current committed inventory's `37ee758c…` digest. |
| `Test-ParityPublication.Tests.ps1` | The historical approved handoff has a stale/mismatched inventory digest. |

The parity data, scripts, tests, source pins and approval records are unchanged
by the resource-group work. These tests must not be made green by inventing
source history, replacing approved digests or changing the release's component
or foundation pins. No upstream release or infrastructure-submodule change is
required: `infra/` is repository-owned source.

The hosted-agent contract test compiles with the Bicep version recorded in its
fixture and proves that the default-disabled feature preserves every symbolic
resource from the merge base except named post-baseline mutations covered by
focused contracts. It checks that hosted-agent additions remain limited to the
two centralized RBAC deployment payloads and are gated by
`prepareHostedAgent || deployHostedAgent`, least privilege, and accompanied by
the stable Foundry/registry handoff. It also proves both flags default to
`false`, prepare mode never enables the agent payload or creates a hosted-agent
resource, deployment remains digest-gated, and private ACR agent-pool topology
stays independently controlled. The ACR Task agent pool firewall contract test
(Azure/GPT-RAG#597) asserts that the VNet-injected ACR Tasks dedicated agent
pool's required outbound platform-bootstrap Network Rules (AzureKeyVault,
Storage, EventHub, AzureActiveDirectory, AzureMonitor) are present, correctly
gated, ordered, and scoped to the devops build agents subnet — independent of
the opaque hash check above. The Foundry shared private-link naming contract
proves valid legacy child IDs remain unchanged, both long suffix variants stay
within 60 characters, output is deterministic, and distinct tested long inputs
do not collide. The Maintenance Configuration wrapper contract compiles default
and InGuestPatch calls and proves every typed property is forwarded to AVM
0.3.1, with schedules and reboot settings retaining their required nesting and
omitted values retaining AVM defaults. The deterministic preflight tests cover
disabled, prepare-only, valid immutable deployment, mutable/missing image
digest, private build, missing-prerequisite, strict Boolean, Container Apps
dependency, API-key prerequisite, and BYO subnet/NSG configurations without
accessing Azure. The component deployment flag contract proves the matching
Bicep validation expressions and defensive resource, DNS, secret, and
configuration gates.

The resource-group scope contract compiles the actual orchestrator with Azure
CLI Bicep, checks application/Foundry/network ownership, actual IDs and RBAC
scopes, and projects one/two/three-RG mappings only after checking their exact
compiled bindings. It checks independent legacy/separate PE subnet selection,
BYO and explicit PE/DNS precedence (including subscriptions), nested Foundry
endpoint destinations and serialization, prerequisite project grants, private
access with policy-managed DNS, collision-safe deployment names, the ARM
64-output limit, and minified template size. CIDR/name validation gates new
subnet writes; address-space checks are not applied to untouched platform-owned
BYO subnets. It makes no Azure requests and creates its compiler artifact beside
the test, deleting it in `finally`.

The scoped refactor intentionally changes the historical symbolic resource
graph: direct network resources now live in focused deployments, Foundry
modules acquire destination scopes, and RBAC fans out to actual target RGs.
The hosted-agent and solution-Storage fingerprint baselines are **not**
regenerated or waived. `ScopedResourceGroupNormalization.ps1` checks exact
compiled before/after deltas before projecting the reviewed changes back to
their historical graph representation. The two explicit allowlists keep the
ADR-0023 scoped refactor separate from the earlier incorporation/customization
of repository-owned `infra/` and upstream post-baseline fixes. They preserve
all original hashes, including nested module properties and definitions.
Dictionary membership, wrapper contents, scopes, bindings, security settings,
and new outputs must match the reviewed values; unrelated fields survive
projection and remain subject to the original fingerprints. Only generated
compiler hashes and line endings are non-deploying comparison differences.
`Test-ScopedGraphNormalizationContract.ps1` proves that projection leaves the
actual deployment graph untouched and rejects wrong scopes, grounding Storage
ownership changes, default/subnet/output/security drift, extra wrapper
resources, unrelated resource changes, and manifest spoofing. Behavioral checks
still inspect the actual compiled template, not the historical projection.
The ACR subnet and Search shared-link semantic tests follow the new compiled
composition while retaining ordering, naming, and NSG checks.

The Cosmos DB deployment-name contract proves that no top-level deployment
embeds an environment-derived resource name and that SQL databases and
containers use direct resources behind a fixed nested deployment name. Long CAF
environment names therefore cannot exceed ARM's 64-character deployment-name
limit while configured Azure resource names remain unchanged. The incorporated
account-only local module must contain exactly one account resource and no SQL
parameter or SQL children; legacy AVM fixture shapes must retain an empty SQL
collection.
The compiled-template size tests prove that the script's default 3.5 MB warning,
4.7 MB failure, and 5.0 MB hard ceiling remain aligned with the workflow's bare
command and exercise each exit path without compiling or accessing Azure.

The ACR subnet contract (#159) checks the compiled pool dependency on BYO subnet
creation, the existing registry/new-VNet dependencies, conditional resource and
output gates, count-zero behavior, the existing NSG guard, cross-scope subnet
targets, and serialized subnet operations (A1-A9). A live cold-start test must
still start with an absent build subnet and show subnet completion before pool
provisioning; a successful retry is not cold-start evidence.

The same compiled subnet contract covers #168: reserved `AzureBastionSubnet`
does not receive a generic NSG when Bastion is disabled, while explicit NSGs,
enabled Bastion's dedicated binding, ordinary/custom subnets and disabled-NSG
paths retain their precedence. The Storage graph guard permits only that
precise additional exclusion, retaining the historical fingerprints and
rejecting unrelated exclusion or explicit-NSG selector changes.

The solution Storage access contract (#160) checks typed input/default and
native JSON parameter values (or omitted inputs using the exact native Bicep
defaults), exact root-to-AVM-to-resource forwarding, all
supported bypass values, true/false, zero/one/multiple resource-instance rules,
invalid typed inputs, and standard/isolated/IP-exception/disabled-account cases
(S1-S9). It checks nested compiled expressions rather than treating source-token
presence as proof, and protects unrelated Storage configuration and auxiliary
accounts. Default equivalence means unchanged effective values, not identical
template bytes. No Defender resource, plan, role or exception is inferred.

The [proposed release guard](../docs/adr/0006-release-metadata-and-comparison-baselines.md)
checks exact equal manifest tags and the latest unique versioned changelog
heading, separately from historical parity tag/SHA pins. Its offline tests
include metadata mutations and both workflows' path coverage.
The Storage graph guard verifies that `_manifest` retains its Bicep 0.42.1
binding to `$fxv#0`. Before compatibility projection, the loaded object must
match the actual umbrella manifest, its `infra.source.tag` must match the
incorporated foundation manifest, and source/component pins and manifest shape
must match the reviewed incorporation allowlist. The projected foundation
manifest is then checked against its own manifest/changelog; only its `tag` and
`ailz_tag` are normalized to `v2.6.1` before the original variable fingerprint.
Release numbers can change; arbitrary repositories, pins, extra fields,
variables, resources and outputs cannot. No fingerprints are regenerated.
`-MainFile` fixtures must include the corresponding umbrella manifest and
foundation manifest/changelog. These checks do not authorize a release.

Both scripts accept `-MainFile` for isolated regression fixtures and remove their
temporary compiler artifacts. Their offline checks do not prove live subnet
preservation, ACL persistence, consumer authentication or Defender scanning.
The [private-deployment validation guide](../specs/002-private-deployment-reliability/quickstart.md)
separates those approved operational scenarios and their evidence.

## End-to-end test flow

### 1. Deploy the hub (one time per subscription)

```pwsh
pwsh tests/scripts/Deploy-Hub.ps1
```

This:
- Switches `az` to the test subscription if needed.
- Creates `rg-ailz-hub` if missing.
- Deploys `tests/hub/main.bicep` — VNet + Firewall (Standard) + Bastion (Standard) + LAW.
- Writes outputs to `tests/hub/.outputs.json`.

Takes ~25-30 minutes (Azure Firewall + Bastion provisioning).

To preview without applying:

```pwsh
pwsh tests/scripts/Deploy-Hub.ps1 -WhatIf
```

### 2. Deploy the spoke (per test)

The spoke is the landing zone itself (`main.bicep` at repo root). You drive
it via `azd`, passing parameters captured from the hub:

```pwsh
# Pick a fresh spoke RG name following the convention
$timestamp = Get-Date -Format 'MMddyyHHmm'
$spokeRG = "rg-ailz-spoke-$timestamp"

# Load hub outputs
$hub = Get-Content tests/hub/.outputs.json | ConvertFrom-Json

# Create azd env and inject hub references
azd env new "ailz-v2-$timestamp"
azd env set AZURE_SUBSCRIPTION_ID 9788a92c-2f71-4629-8173-7ad449cb50e1
azd env set AZURE_LOCATION eastus2
azd env set AZURE_RESOURCE_GROUP $spokeRG
azd env set NETWORK_ISOLATION true
azd env set HUB_VNET_RESOURCE_ID $hub.hubVnetResourceId
azd env set CREATE_HUB_PEERING true
azd env set EGRESS_NEXT_HOP_IP $hub.firewallPrivateIp                  # Gap 6 (optional)
azd env set LOG_ANALYTICS_WORKSPACE_RESOURCE_ID $hub.logAnalyticsWorkspaceResourceId  # Gap 5 (optional)
azd env set DEPLOY_BASTION false                                       # Use hub Bastion instead

# Provision
azd provision
```

> **Note:** the specific `azd env` keys above (HUB_VNET_RESOURCE_ID,
> CREATE_HUB_PEERING, etc.) are introduced by v2.0.0 Gaps 6/7/4. Until the
> corresponding gap commit lands, those env vars will be silently ignored by the
> spoke deployment.

### 3. Connect to the spoke jumpbox via the hub Bastion

After provision completes, locate the jumpbox VM in the spoke RG and connect
through Azure Portal:

1. Azure Portal → Resource Groups → `rg-ailz-hub` → Bastion host
2. Connect to the spoke jumpbox VM by resource ID (paste `/subscriptions/9788a92c-.../resourceGroups/<spokeRG>/providers/Microsoft.Compute/virtualMachines/<vmName>`).
3. Authenticate with the credentials set via `azd env set AZURE_JUMPBOX_PASSWORD` (the standard landing-zone parameter).

Once logged in, post-provision scripts and validation run **from inside the
jumpbox**.

### 4. Verify the Container App from the jumpbox

Inside the jumpbox session:

```pwsh
# Get the Container App FQDN (output by the spoke deployment)
$caFqdn = azd env get-value APP_CONTAINER_APP_ORCHESTRATOR_FQDN

# Hit it from the jumpbox (which sits inside the spoke VNet and can reach
# the Container App private FQDN through the VNet-linked Private DNS zone)
Invoke-WebRequest "https://$caFqdn" -UseBasicParsing | Select-Object StatusCode, Content
```

Expected: HTTP 200 + the dotnet/samples:aspnetapp-9.0 default landing page
(which is the v2.0.0 dummy image listening on port 8080).

## What the test fixture intentionally does NOT do

- The hub firewall has an **empty policy**. Spoke egress is not forced through
  it by default. To exercise Gap 6 end-to-end with active filtering, populate
  `firewallPolicy.properties.ruleCollectionGroups` (out of scope for the
  v2.0.0 acceptance test). See plan.md §4.6 Option B.
- The hub has **no Private DNS zones**. The spoke creates its own (default) or
  reuses external zones declared via `existingPrivateDnsZones` (Gap 2). No
  central DNS resolver is configured.
- Bidirectional VNet peering: the **spoke→hub** peering is created by the
  spoke deployment itself (Gap 7). The **hub→spoke** reverse peering must be
  added separately — the hub deploy script does not know spoke VNet IDs
  in advance. Use:

  ```pwsh
  az network vnet peering create `
    --name to-spoke-<timestamp> `
    --resource-group rg-ailz-hub `
    --vnet-name $hub.hubVnetName `
    --remote-vnet $spokeVnetId `
    --allow-vnet-access true
  ```

  This is captured in `tests/scripts/Add-HubToSpokePeering.ps1` (Phase 7 add).
