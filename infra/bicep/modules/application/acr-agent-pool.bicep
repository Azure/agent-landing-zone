targetScope = 'resourceGroup'

param registryName string
param name string
param location string
param tags object
param count int
param tier string
param subnetResourceId string

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: registryName
}

resource pool 'Microsoft.ContainerRegistry/registries/agentPools@2019-06-01-preview' = {
  parent: registry
  name: name
  location: location
  tags: tags
  properties: {
    count: count
    tier: tier
    os: 'Linux'
    virtualNetworkSubnetResourceId: subnetResourceId
  }
}
