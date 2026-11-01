targetScope = 'resourceGroup'

param name string
param location string
param tags object
param skuName string
param identity object
param properties object

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  identity: identity
  properties: properties
}

output resourceId string = registry.id
