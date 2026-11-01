@maxLength(60)
@description('Required. The name of the AI Search resource.')
param name string

@description('Required. The location for the AI Search resource.')
param location string

@description('Optional. The full resource ID of an existing AI Search resource to use instead of creating a new one.')
param existingResourceId string?

@description('Optional. Resource Id of an existing subnet to use for private connectivity. This is required along with \'privateDnsZoneResourceId\' to establish private endpoints.')
param privateEndpointSubnetResourceId string?

@description('Actual RG ARM ID for customer-owned private endpoints.')
param privateEndpointResourceGroupResourceId string = resourceGroup().id
@description('Private endpoint region.')
param privateEndpointLocation string = location

@description('Optional. The resource ID of the private DNS zone for the AI Search resource to establish private endpoints.')
param privateDnsZoneResourceId string?

import { roleAssignmentType } from 'br/public:avm/utl/types/avm-common-types:0.6.1'
@description('Optional. Specifies the role assignments for the AI Search resource.')
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

resource existingSearchService 'Microsoft.Search/searchServices@2025-05-01' existing = if (!empty(existingResourceId)) {
  name: existingName
  scope: resourceGroup(existingSubscriptionId, existingResourceGroupName)
}

var privateNetworkingEnabled = !empty(privateEndpointSubnetResourceId)

module aiSearch 'br/public:avm/res/search/search-service:0.11.1' = if (empty(existingResourceId)) {
  name: take('avm.res.search.search-service.${name}', 64)
  params: {
    name: name
    location: location
    enableTelemetry: enableTelemetry
    cmkEnforcement: 'Unspecified'
    managedIdentities: {
      systemAssigned: true
    }
    publicNetworkAccess: privateNetworkingEnabled ? 'Disabled' : 'Enabled'
    disableLocalAuth: privateNetworkingEnabled
    authOptions: privateNetworkingEnabled
      ? null
      : {
          aadOrApiKey: {
            aadAuthFailureMode: 'http401WithBearerChallenge'
          }
        }
    sku: 'standard'
    partitionCount: 1
    replicaCount: 1
    roleAssignments: roleAssignments
    privateEndpoints: privateNetworkingEnabled
      ? [
          union({
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
    tags: tags
  }
}

@description('Name of the AI Search resource.')
output name string = empty(existingResourceId) ? aiSearch!.outputs.name : existingSearchService.name

@description('Resource ID of the AI Search resource.')
output resourceId string = empty(existingResourceId) ? aiSearch!.outputs.resourceId : existingSearchService.id

@description('Subscription ID of the AI Search resource.')
output subscriptionId string = empty(existingResourceId) ? subscription().subscriptionId : existingSubscriptionId

@description('Resource Group Name of the AI Search resource.')
output resourceGroupName string = empty(existingResourceId) ? resourceGroup().name : existingResourceGroupName

@description('System assigned managed identity principal ID of the AI Search resource.')
output systemAssignedMIPrincipalId string? = empty(existingResourceId)
  ? aiSearch!.outputs.systemAssignedMIPrincipalId!
  : ''
