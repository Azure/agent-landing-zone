targetScope = 'resourceGroup'

param name string
param location string
param tags object
param publicNetworkAccess string
param networkAcls object?

@secure()
param secrets object

resource vault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    publicNetworkAccess: publicNetworkAccess
    networkAcls: networkAcls
  }
}

resource secret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = [for config in secrets.values: {
  parent: vault
  name: replace(config.name, '_', '-')
  properties: {
    contentType: config.contentType
    value: config.value
  }
  tags: {}
}]

output resourceId string = vault.id
output properties object = vault.properties
