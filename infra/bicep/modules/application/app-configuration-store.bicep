targetScope = 'resourceGroup'

param name string
param location string
param tags object
param networkIsolation bool
param publicNetworkAccess string
param principalId string
param principalType string
param dataOwnerRoleGuid string

resource store 'Microsoft.AppConfiguration/configurationStores@2024-05-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    dataPlaneProxy: {
      authenticationMode: 'Pass-through'
      privateLinkDelegation: networkIsolation ? 'Enabled' : 'Disabled'
    }
    publicNetworkAccess: publicNetworkAccess
    disableLocalAuth: false
  }
}

resource dataOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(store.id, principalId, dataOwnerRoleGuid)
  scope: store
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', dataOwnerRoleGuid)
  }
}

output name string = store.name
output resourceId string = store.id
output properties object = store.properties
