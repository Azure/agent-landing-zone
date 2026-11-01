targetScope = 'resourceGroup'

param name string
param taskHubName string = 'agent-lz'
param location string
param tags object = {}
param networkIsolation bool = false
@allowed(['Consumption', 'Dedicated'])
param sku string = 'Consumption'
@minValue(1)
param capacity int = 1

// Official control-plane API; no workflow/agent publication in foundation.
resource scheduler 'Microsoft.DurableTask/schedulers@2026-02-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: { name: sku, capacity: capacity }
    ipAllowlist: []
    publicNetworkAccess: networkIsolation ? 'Disabled' : 'Enabled'
  }
}

resource hub 'Microsoft.DurableTask/schedulers/taskHubs@2026-02-01' = {
  parent: scheduler
  name: taskHubName
  properties: {}
}

output backend object = {
  resourceId: scheduler.id
  endpoint: scheduler.properties.endpoint
  taskHubName: hub.name
  taskHubResourceId: hub.id
}
