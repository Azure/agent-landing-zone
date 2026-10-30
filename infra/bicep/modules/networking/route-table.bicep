targetScope = 'resourceGroup'

@description('Route table name, derived by the root naming contract.')
param name string
@description('Workload region.')
param location string
@description('Deployment tags.')
param tags object

resource routeTable 'Microsoft.Network/routeTables@2024-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    disableBgpRoutePropagation: true
  }
}

@description('Actual ARM ID of the route table.')
output resourceId string = routeTable.id
