@description('Required. The name of the storage account.')
param storageAccountName string

@description('Required. The principal ID of the project identity.')
param projectIdentityPrincipalId string

@description('Required. The project workspace ID.')
param projectWorkspaceId string

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' existing = {
  name: storageAccountName
  scope: resourceGroup()
}

resource storageBlobDataOwnerRoleDefinition 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b' // Storage Blob Data Owner
  scope: resourceGroup()
}

resource storageAccountCustomContainerDataOwnerRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(storageAccount.id, storageBlobDataOwnerRoleDefinition.id, storageAccountName, projectIdentityPrincipalId)
  properties: {
    principalId: projectIdentityPrincipalId
    roleDefinitionId: storageBlobDataOwnerRoleDefinition.id
    principalType: 'ServicePrincipal'
    conditionVersion: '2.0'
    // NOTE: doing a string replace here because multi-line strings do not support string interpolation
    condition: replace(
      '''
      (
        (
          !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/read'})
          AND  !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/filter/action'})
          AND  !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/write'})
        )
        OR
        (@Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringStartsWithIgnoreCase '#projectWorkspaceId#'
        AND @Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringLikeIgnoreCase '*-azureml-agent')
      )
      ''',
      '#projectWorkspaceId#',
      projectWorkspaceId
    )
  }
}
