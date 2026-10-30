targetScope = 'resourceGroup'

param name string
param location string
param tags object
param identity object
param properties object

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: name
  location: location
  tags: tags
  identity: identity
  properties: properties
}

output resourceId string = environment.id
output identity object = environment.identity
