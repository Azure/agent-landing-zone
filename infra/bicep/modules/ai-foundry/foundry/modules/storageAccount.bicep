@maxLength(24)
@description('Required. The name of the storage account.')
param name string

@description('Required. The location for the storage account.')
param location string

@description('Optional. The full resource ID of an existing storage account to use instead of creating a new one.')
param existingResourceId string?

@description('Optional. Resource Id of an existing subnet to use for private connectivity. This is required along with \'blobPrivateDnsZoneResourceId\' to establish private endpoints.')
param privateEndpointSubnetResourceId string?

@description('Actual RG ARM ID for customer-owned private endpoints.')
param privateEndpointResourceGroupResourceId string = resourceGroup().id
@description('Private endpoint region.')
param privateEndpointLocation string = location

@description('Optional. The resource ID of the private DNS zone for the storage account blob service to establish private endpoints.')
param blobPrivateDnsZoneResourceId string?

import { roleAssignmentType } from 'br/public:avm/utl/types/avm-common-types:0.6.1'
@description('Optional. Specifies the role assignments for the storage account.')
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

resource existingStorageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' existing = if (!empty(existingResourceId)) {
  name: existingName
  scope: resourceGroup(existingSubscriptionId, existingResourceGroupName)
}

var privateNetworkingEnabled = !empty(privateEndpointSubnetResourceId)

module storageAccount 'br/public:avm/res/storage/storage-account:0.28.0' = if (empty(existingResourceId)) {
  name: take('avm.res.storage.storage-account.${name}', 64)
  params: {
    name: name
    location: location
    tags: tags
    enableTelemetry: enableTelemetry
    publicNetworkAccess: privateNetworkingEnabled ? 'Disabled' : 'Enabled'
    accessTier: 'Hot'
    allowBlobPublicAccess: !privateNetworkingEnabled
    allowSharedKeyAccess: false
    allowCrossTenantReplication: false
    blobServices: {
      deleteRetentionPolicyEnabled: true
      deleteRetentionPolicyDays: 7
      containerDeleteRetentionPolicyEnabled: true
      containerDeleteRetentionPolicyDays: 7
    }
    minimumTlsVersion: 'TLS1_2'
    networkAcls: {
      defaultAction: privateNetworkingEnabled ? 'Deny' : 'Allow'
      bypass: 'AzureServices'
    }
    supportsHttpsTrafficOnly: true
    privateEndpoints: privateNetworkingEnabled
      ? [
          union({
            service: 'blob'
            subnetResourceId: privateEndpointSubnetResourceId!
            resourceGroupResourceId: privateEndpointResourceGroupResourceId
            location: privateEndpointLocation
          }, !empty(blobPrivateDnsZoneResourceId) ? {
            privateDnsZoneGroup: {
              privateDnsZoneGroupConfigs: [
                {
                  privateDnsZoneResourceId: blobPrivateDnsZoneResourceId!
                }
              ]
            }
          } : {})
        ]
      : []
    roleAssignments: roleAssignments
  }
}

@description('Name of the Storage Account.')
output name string = empty(existingResourceId) ? storageAccount!.outputs.name : existingStorageAccount.name

@description('Resource ID of the Storage Account.')
output resourceId string = empty(existingResourceId) ? storageAccount!.outputs.resourceId : existingStorageAccount.id

@description('Subscription ID of the Storage Account.')
output subscriptionId string = empty(existingResourceId) ? subscription().subscriptionId : existingSubscriptionId

@description('Resource Group Name of the Storage Account.')
output resourceGroupName string = empty(existingResourceId) ? resourceGroup().name : existingResourceGroupName
