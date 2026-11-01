@maxLength(24)
@description('Required. The name of the Key Vault.')
param name string

@description('Required. The location for the Key Vault.')
param location string

@description('Optional. The full resource ID of an existing Key Vault to use instead of creating a new one.')
param existingResourceId string?

@description('Optional. Resource Id of an existing subnet to use for private connectivity. This is required along with \'privateDnsZoneResourceId\' to establish private endpoints.')
param privateEndpointSubnetResourceId string?

@description('Actual RG ARM ID for customer-owned private endpoints.')
param privateEndpointResourceGroupResourceId string = resourceGroup().id
@description('Private endpoint region.')
param privateEndpointLocation string = location

@description('Optional. The resource ID of the private DNS zone for the Key Vault to establish private endpoints.')
param privateDnsZoneResourceId string?

import { roleAssignmentType } from 'br/public:avm/utl/types/avm-common-types:0.6.1'
@description('Optional. Specifies the role assignments for the Key Vault.')
param roleAssignments roleAssignmentType[]?

@description('Optional. Enable/Disable usage telemetry for module.')
param enableTelemetry bool = true

@description('Optional. Specifies the resource tags for all the resources.')
param tags resourceInput<'Microsoft.Resources/resourceGroups@2025-04-01'>.tags = {}

import { getResourceParts, getResourceName, getSubscriptionId, getResourceGroupName } from 'parseResourceIdFunctions.bicep'

var existingResourceParts = getResourceParts(existingResourceId)
var existingName = getResourceName(existingResourceId, existingResourceParts)
var existingSubscriptionId = getSubscriptionId(existingResourceParts)
var existingResourceGroupName = getResourceGroupName(existingResourceParts)

resource existingKeyVault 'Microsoft.KeyVault/vaults@2024-11-01' existing = if (!empty(existingResourceId)) {
  name: existingName
  scope: resourceGroup(existingSubscriptionId, existingResourceGroupName)
}

var privateNetworkingEnabled = !empty(privateEndpointSubnetResourceId)

module keyVault 'br/public:avm/res/key-vault/vault:0.13.3' = if (empty(existingResourceId)) {
  name: take('avm.res.key-vault.vault.${name}', 64)
  params: {
    name: name
    location: location
    tags: tags
    enableTelemetry: enableTelemetry
    publicNetworkAccess: privateNetworkingEnabled ? 'Disabled' : 'Enabled'
    networkAcls: {
      defaultAction: privateNetworkingEnabled ? 'Deny' : 'Allow'
    }
    enableVaultForDeployment: true
    enableVaultForDiskEncryption: true
    enableVaultForTemplateDeployment: true
    enablePurgeProtection: false
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    privateEndpoints: privateNetworkingEnabled
      ? [
          union({
            service: 'vault'
            subnetResourceId: privateEndpointSubnetResourceId!
            resourceGroupResourceId: privateEndpointResourceGroupResourceId
            location: privateEndpointLocation
          }, !empty(privateDnsZoneResourceId) ? {
            privateDnsZoneGroup: {
              privateDnsZoneGroupConfigs: [
                {
                  privateDnsZoneResourceId: privateDnsZoneResourceId!
                }
              ]
            }
          } : {})
        ]
      : []
    roleAssignments: roleAssignments
  }
}

@description('Name of the Key Vault.')
output name string = empty(existingResourceId) ? keyVault!.outputs.name : existingKeyVault.name

@description('Resource ID of the Key Vault.')
output resourceId string = empty(existingResourceId) ? keyVault!.outputs.resourceId : existingKeyVault.id

@description('Subscription ID of the Key Vault.')
output subscriptionId string = empty(existingResourceId) ? subscription().subscriptionId : existingSubscriptionId

@description('Resource Group Name of the Key Vault.')
output resourceGroupName string = empty(existingResourceId) ? resourceGroup().name : existingResourceGroupName
