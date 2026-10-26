targetScope = 'resourceGroup'

@description('Private endpoints to deploy. Consolidated into a single for-loop to keep the compiled ARM template small. @batchSize(1) serializes PE operations to avoid parallel conflicts.')
type endpointInfo = {
  name: string
  privateLinkServiceConnections: array
  privateDnsZoneGroup: object?
  customNetworkInterfaceName: string?
  subnetResourceId: string?
}

param endpoints endpointInfo[] = []
param location string
param resourceGroupName string
@description('Actual subscription of the private endpoints, including the supported BYO VNet fallback.')
param subscriptionId string = subscription().subscriptionId
param tags object
param subnetResourceId string
param prefix string = 'nic-'

@batchSize(1)
module privateEndpoints 'br/public:avm/res/network/private-endpoint:0.11.0' = [for (ep, i) in endpoints: {
  scope: resourceGroup(subscriptionId, resourceGroupName)
  name: 'dep-pe-${uniqueString(ep.name)}'
  params: {
    name: ep.name
    location: location
    tags: tags
    subnetResourceId: ep.?subnetResourceId ?? subnetResourceId
    privateLinkServiceConnections: ep.privateLinkServiceConnections
    privateDnsZoneGroup: ep.?privateDnsZoneGroup
    customNetworkInterfaceName: ep.?customNetworkInterfaceName ?? '${prefix}${ep.name}'
  }
}]
