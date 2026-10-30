targetScope = 'resourceGroup'

@description('Name of the locally owned route table.')
param routeTableName string
@description('Address of the local firewall or configured external next hop.')
param nextHopIpAddress string

resource routeTable 'Microsoft.Network/routeTables@2024-07-01' existing = {
  name: routeTableName
}

resource defaultRoute 'Microsoft.Network/routeTables/routes@2024-07-01' = {
  parent: routeTable
  name: 'default-to-firewall'
  properties: {
    addressPrefix: '0.0.0.0/0'
    nextHopType: 'VirtualAppliance'
    nextHopIpAddress: nextHopIpAddress
  }
}
