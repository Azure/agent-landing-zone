targetScope = 'resourceGroup'

param name string
param location string
param resourceGroupName string
@description('Actual subscription of the private endpoint.')
param subscriptionId string = subscription().subscriptionId
param tags object
param subnetResourceId string
param privateLinkServiceConnections array = []
param privateDnsZoneGroup object?
param prefix string = 'nic-'

module privateEndpoint 'br/public:avm/res/network/private-endpoint:0.11.0' = if (privateDnsZoneGroup != null) {
  scope: resourceGroup(subscriptionId, resourceGroupName)
  params: {
    name: name
    location: location
    tags: tags
    subnetResourceId: subnetResourceId
    privateLinkServiceConnections: privateLinkServiceConnections
    privateDnsZoneGroup: privateDnsZoneGroup!
    customNetworkInterfaceName: '${prefix}${name}'
  }
}

module privateEndpointWithoutDns 'br/public:avm/res/network/private-endpoint:0.11.0' = if (privateDnsZoneGroup == null) {
  scope: resourceGroup(subscriptionId, resourceGroupName)
  params: {
    name: name
    location: location
    tags: tags
    subnetResourceId: subnetResourceId
    privateLinkServiceConnections: privateLinkServiceConnections
    customNetworkInterfaceName: '${prefix}${name}'
  }
}

#disable-next-line BCP318
output resourceId string = privateDnsZoneGroup == null ? privateEndpointWithoutDns!.outputs.resourceId : privateEndpoint!.outputs.resourceId
