@maxLength(44)
@description('Required. The name of the Cosmos DB.')
param name string

@description('Required. The location for the Cosmos DB.')
param location string

@description('Optional. The full resource ID of an existing Cosmos DB to use instead of creating a new one.')
param existingResourceId string?

@description('Optional. Resource Id of an existing subnet to use for private connectivity. This is required along with \'privateDnsZoneResourceId\' to establish private endpoints.')
param privateEndpointSubnetResourceId string?

@description('Actual RG ARM ID for customer-owned private endpoints.')
param privateEndpointResourceGroupResourceId string = resourceGroup().id
@description('Private endpoint region.')
param privateEndpointLocation string = location

@description('Optional. The resource ID of the private DNS zone for the Cosmos DB to establish private endpoints.')
param privateDnsZoneResourceId string?

import { roleAssignmentType } from 'br/public:avm/utl/types/avm-common-types:0.6.1'
@description('Optional. Specifies the role assignments for the Cosmos DB.')
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

resource existingCosmosDb 'Microsoft.DocumentDB/databaseAccounts@2025-04-15' existing = if (!empty(existingResourceId)) {
  name: existingName
  scope: resourceGroup(existingSubscriptionId, existingResourceGroupName)
}

var privateNetworkingEnabled = !empty(privateEndpointSubnetResourceId)

module cosmosDb 'br/public:avm/res/document-db/database-account:0.18.0' = if (empty(existingResourceId)) {
  name: take('avm.res.document-db.database-account.${name}', 64)
  params: {
    name: name
    enableTelemetry: enableTelemetry
    enableAutomaticFailover: true
    disableKeyBasedMetadataWriteAccess: true
    disableLocalAuthentication: true
    location: location
    minimumTlsVersion: 'Tls12'
    defaultConsistencyLevel: 'Session'
    networkRestrictions: {
      networkAclBypass: 'AzureServices'
      publicNetworkAccess: privateNetworkingEnabled ? 'Disabled' : 'Enabled'
    }
    privateEndpoints: privateNetworkingEnabled
      ? [
          union({
            service: 'Sql'
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
    tags: tags
  }
}

@description('Name of the Cosmos DB.')
output name string = empty(existingResourceId) ? cosmosDb!.outputs.name : existingCosmosDb.name

@description('Resource ID of the Cosmos DB.')
output resourceId string = empty(existingResourceId) ? cosmosDb!.outputs.resourceId : existingCosmosDb.id

@description('Subscription ID of the Cosmos DB.')
output subscriptionId string = empty(existingResourceId) ? subscription().subscriptionId : existingSubscriptionId

@description('Resource Group Name of the Cosmos DB.')
output resourceGroupName string = empty(existingResourceId) ? resourceGroup().name : existingResourceGroupName
