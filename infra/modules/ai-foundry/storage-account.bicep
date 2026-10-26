// ============================================================================
// AI Foundry Storage Account Helper Module
// ----------------------------------------------------------------------------
// Creates a Standard_LRS (or caller-chosen SKU) Storage Account that can be
// fed back into the AVM `avm/ptn/ai-ml/ai-foundry` module via its
// `storageAccountConfiguration.existingResourceId` input.
//
// Why this exists:
//   The AVM ai-foundry pattern (<= v0.6.0) does NOT expose a `skuName` on its
//   `storageAccountConfiguration` and internally creates the Storage Account
//   with the provider default (`Standard_GRS`). That fails in regions where
//   GRS is not offered (e.g. Poland Central) with
//   `RedundancyConfigurationNotAvailableInRegion`.
//
//   By pre-creating the account here with `Standard_LRS` and handing its
//   resource ID to the AVM as an existing resource, we honor the requested
//   SKU and unblock deployments in GRS-restricted regions.
// ============================================================================

targetScope = 'resourceGroup'

@description('Required. Name of the Storage Account. Must be globally unique, 3-24 lowercase alphanumeric characters.')
@minLength(3)
@maxLength(24)
param name string

@description('Optional. Location for the Storage Account.')
param location string = resourceGroup().location

@description('Optional. Tags to apply to the Storage Account.')
param tags object = {}

@description('Optional. Storage Account SKU. Defaults to Standard_LRS for broad regional availability.')
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
param skuName string = 'Standard_LRS'

@description('Optional. Disable public network access on the Storage Account. When `allowedIpRanges` is non-empty, the public surface is kept Enabled to allow IP-rule restriction (issue #58 Gap 1).')
param disablePublicNetworkAccess bool = false

@description('Optional. CIDR allow-list for service-level IP rules. Empty (default) means no allow-list. When non-empty, `networkAcls.defaultAction` is set to `Deny` and these CIDRs are added as `ipRules` with action `Allow`.')
param allowedIpRanges string[] = []

@description('Optional. Subnet resource ID for the blob private endpoint. When empty, no private endpoint is created.')
param privateEndpointSubnetResourceId string = ''

@description('Actual RG ARM ID for the blob private endpoint.')
param privateEndpointResourceGroupResourceId string = resourceGroup().id

@description('Region for the private endpoint.')
param privateEndpointLocation string = location

@description('Optional. Private DNS zone resource ID for the blob private endpoint (privatelink.blob.<suffix>).')
param blobPrivateDnsZoneResourceId string = ''

@description('Optional. Enable telemetry via the Customer Usage Attribution ID.')
param enableTelemetry bool = true

var _applyIpRules    = !empty(allowedIpRanges)
var _ipRules         = [for ip in allowedIpRanges: { value: ip, action: 'Allow' }]
// publicNetworkAccess matrix:
//   disablePublic=true,  allowedIpRanges=[]   -> Disabled (private only)
//   disablePublic=true,  allowedIpRanges=CIDR -> Enabled  (private + IP allow-list)
//   disablePublic=false, allowedIpRanges=*    -> Enabled  (public)
var _publicAccess    = (disablePublicNetworkAccess && !_applyIpRules) ? 'Disabled' : 'Enabled'
var _defaultAction   = (disablePublicNetworkAccess || _applyIpRules) ? 'Deny' : 'Allow'

// ---------------------------------------------------------------------
// Storage Account
// ---------------------------------------------------------------------
module storageAccount 'br/public:avm/res/storage/storage-account:0.26.2' = {
  name: 'aiFoundryStorage-${name}'
  params: {
    name: name
    location: location
    tags: tags
    skuName: skuName
    kind: 'StorageV2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: _publicAccess
    networkAcls: {
      bypass: 'AzureServices'
      virtualNetworkRules: []
      ipRules: _ipRules
      defaultAction: _defaultAction
    }
    privateEndpoints: !empty(privateEndpointSubnetResourceId)
      ? [
          union({
            name: 'pe-${name}-blob'
            service: 'blob'
            subnetResourceId: privateEndpointSubnetResourceId
            resourceGroupResourceId: privateEndpointResourceGroupResourceId
            location: privateEndpointLocation
          }, !empty(blobPrivateDnsZoneResourceId) ? {
            privateDnsZoneGroup: {
              privateDnsZoneGroupConfigs: [
                {
                  privateDnsZoneResourceId: blobPrivateDnsZoneResourceId
                }
              ]
            }
          } : {})
        ]
      : []
    enableTelemetry: enableTelemetry
  }
}

// ---------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------
@description('The full ARM resource ID of the Storage Account.')
output resourceId string = storageAccount.outputs.resourceId

@description('The name of the Storage Account.')
output name string = storageAccount.outputs.name
