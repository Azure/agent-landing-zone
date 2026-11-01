targetScope = 'resourceGroup'

param dnsName string
param location string = 'global'
param resourceGroupName string
param tags object
param virtualNetworkResourceId string
param virtualNetworkLinkName string
param registrationEnabled bool = false

module privateDnsZone 'br/public:avm/res/network/private-dns-zone:0.8.0' = {
  scope: resourceGroup(resourceGroupName)
  params: {
    name: dnsName
    location: location
    tags: tags
    virtualNetworkLinks: [
      {
        name: virtualNetworkLinkName
        registrationEnabled: registrationEnabled
        #disable-next-line BCP318
        virtualNetworkResourceId: virtualNetworkResourceId
      }
    ]
  }
}

output resourceId string = privateDnsZone.outputs.resourceId
