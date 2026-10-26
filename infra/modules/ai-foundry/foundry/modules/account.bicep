// =============================================================================
// AI Foundry account module — STRUCTURAL fix for issues #26 + #29
// =============================================================================
// This module is part of the customized derivation of
// avm/ptn/ai-ml/ai-foundry@0.6.0 maintained at `modules/ai-foundry/foundry/`.
//
// The previous v1.1.3 fix (deploymentScripts wait) was structurally
// incompatible with the Azure Policy
//   `Storage accounts should prevent shared key access`
//   (8c6a50c6-9ffd-4ae7-986f-5fa6111f9a54)
// because deploymentScripts require a backing storage account with shared-key
// access. See issue #29.
//
// CURRENT FIX (#29)
// -----------------
// Cognitive Services child resources (`accounts/projects`,
// `accounts/deployments`, `accounts/capabilityHosts`) are processed by the
// cog-svc resource provider and serialize server-side against the parent
// account `provisioningState`. By the time any such child resource completes,
// the parent account is in `Succeeded`. Therefore the private endpoint can be
// gated on a child resource — specifically `foundryProject` (which creates
// `Microsoft.CognitiveServices/accounts/projects/{name}`) declared in the
// parent `foundry/main.bicep`. This is fully declarative, policy-neutral, and
// requires no out-of-band runtime dependency.
//
// CONSEQUENCES FOR THIS MODULE
// ----------------------------
// - `privateEndpoints: []` is still passed to `avm/res/cognitive-services/account`
//   so the AVM resource module does NOT create the PE inline.
// - The PE itself is created in `foundry/main.bicep` AFTER `foundryProject`.
// - All wait machinery (deploymentScript, UAI, Reader role) is removed.
//
// History on this repo:
//   - PR  #19  — original property-matching pre-create workaround
//   - Issue #25 — first regression (networkInjections)
//   - Issue #26 — second regression (networkAcls.bypass) → split structure
//   - Issue #27 — upstream tracking (Azure/bicep-registry-modules#5957)
//   - Issue #29 — deploymentScript incompatible with deny-shared-key policy
//                  → switched to declarative `dependsOn` on foundryProject
// =============================================================================

@description('Required. The name of the AI Foundry resource.')
param name string

@description('Required. The location for the AI Foundry resource.')
param location string

@description('Optional. SKU of the AI Foundry / Cognitive Services account. Use \'Get-AzCognitiveServicesAccountSku\' to determine a valid combinations of \'kind\' and \'SKU\' for your Azure region.')
@allowed([
  'C2'
  'C3'
  'C4'
  'F0'
  'F1'
  'S'
  'S0'
  'S1'
  'S10'
  'S2'
  'S3'
  'S4'
  'S5'
  'S6'
  'S7'
  'S8'
  'S9'
  'DC0'
])
param sku string = 'S0'

@description('Required. Whether to allow project management in AI Foundry. This is required to enable the AI Foundry UI and project management features.')
param allowProjectManagement bool

@description('Optional. Resource Id of an existing subnet to use for private connectivity. This is required along with \'privateDnsZoneResourceIds\' to establish private endpoints.')
param privateEndpointSubnetResourceId string?

@description('Optional. Resource Id of an existing subnet to use for agent connectivity. This is required when using agents with private endpoints.')
param agentSubnetResourceId string?

@description('Required. Allow only Azure AD authentication. Should be enabled for security reasons.')
param disableLocalAuth bool

import { roleAssignmentType } from 'br/public:avm/utl/types/avm-common-types:0.6.1'
@description('Optional. Specifies the role assignments for the AI Foundry resource.')
param roleAssignments roleAssignmentType[]?

import { lockType } from 'br/public:avm/utl/types/avm-common-types:0.6.1'
@description('Optional. The lock settings of AI Foundry resources.')
param lock lockType?

import { deploymentType } from 'br/public:avm/res/cognitive-services/account:0.13.2'
@description('Optional. Specifies the OpenAI deployments to create.')
param aiModelDeployments deploymentType[] = []

@description('Optional. List of private DNS zone resource IDs to use for the AI Foundry resource. This is required when using private endpoints.')
param privateDnsZoneResourceIds string[]?

@description('Optional. Enable/Disable usage telemetry for module.')
param enableTelemetry bool = true

@description('Optional. Specifies the resource tags for all the resources.')
param tags resourceInput<'Microsoft.Resources/resourceGroups@2025-04-01'>.tags = {}

var privateDnsZoneResourceIdValues = [
  for id in privateDnsZoneResourceIds ?? []: {
    privateDnsZoneResourceId: id
  }
]
// Policy-managed DNS intentionally omits zone IDs, but still requires private
// access and agent subnet injection.
var privateNetworkingEnabled = !empty(privateEndpointSubnetResourceId)

// -----------------------------------------------------------------------------
// Cognitive Services account (no inline PE — see header for #29 fix)
// -----------------------------------------------------------------------------
module foundryAccount 'br/public:avm/res/cognitive-services/account:0.13.2' = {
  name: take('avm.res.cognitive-services.account.${name}', 64)
  params: {
    name: name
    location: location
    tags: tags
    sku: sku
    kind: 'AIServices'
    lock: lock
    allowProjectManagement: allowProjectManagement
    managedIdentities: {
      systemAssigned: true
    }
    deployments: aiModelDeployments
    customSubDomainName: name
    disableLocalAuth: disableLocalAuth
    publicNetworkAccess: privateNetworkingEnabled ? 'Disabled' : 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
    networkInjections: privateNetworkingEnabled && !empty(agentSubnetResourceId)
      ? {
          scenario: 'agent'
          subnetResourceId: agentSubnetResourceId!
          useMicrosoftManagedNetwork: false
        }
      : null
    // Issue #26+#29: PE is created OUTSIDE this AVM module, gated on the
    // foundryProject child resource declared in `foundry/main.bicep`, which
    // server-side blocks until parent `provisioningState == Succeeded`.
    privateEndpoints: []
    enableTelemetry: enableTelemetry
    roleAssignments: roleAssignments
  }
}

@description('Name of the AI Foundry resource.')
output name string = foundryAccount.outputs.name

@description('Resource ID of the AI Foundry resource.')
output resourceId string = foundryAccount.outputs.resourceId

@description('Subscription ID of the AI Foundry resource.')
output subscriptionId string = subscription().subscriptionId

@description('Resource Group Name of the AI Foundry resource.')
output resourceGroupName string = resourceGroup().name

@description('Location of the AI Foundry resource.')
output location string = location

@description('System assigned managed identity principal ID of the AI Foundry resource.')
output systemAssignedMIPrincipalId string = foundryAccount!.outputs.systemAssignedMIPrincipalId!

@description('Whether private networking is enabled (PE must be created externally and gated on a cog-svc child resource).')
output privateNetworkingEnabled bool = privateNetworkingEnabled

@description('Private DNS zone configs for the externally-created PE.')
output privateDnsZoneConfigs array = privateDnsZoneResourceIdValues
