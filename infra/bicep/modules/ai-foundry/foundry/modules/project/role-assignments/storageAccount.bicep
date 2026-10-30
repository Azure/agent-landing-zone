@description('Required. The name of the storage account.')
param storageAccountName string

@description('Required. The principal ID of the project identity.')
param projectIdentityPrincipalId string

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' existing = {
  name: storageAccountName
  scope: resourceGroup()
}

resource blobStorageContributorRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // Storage Blob Data Contributor
  scope: resourceGroup()
}

// NOTE: using resource module over AVM due to resource possibly existing out of the current scope
resource storageAccountBlobContributorRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(storageAccount.id, blobStorageContributorRole.id, storageAccountName, projectIdentityPrincipalId)
  properties: {
    principalId: projectIdentityPrincipalId
    roleDefinitionId: blobStorageContributorRole.id
    principalType: 'ServicePrincipal'
  }
}
