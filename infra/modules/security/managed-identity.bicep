targetScope = 'resourceGroup'

@description('Name of the resource-owned user-assigned managed identity.')
param name string

@description('Region of the owning resource.')
param location string

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: name
  location: location
}

@description('Actual ARM ID of the identity.')
output resourceId string = identity.id

@description('Principal ID of the identity.')
output principalId string = identity.properties.principalId

@description('Client ID of the identity.')
output clientId string = identity.properties.clientId
