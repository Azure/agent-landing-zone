@description('Name of the Cosmos DB account')
param cosmosDbAccountName string

@description('Object ID of the principal to assign')
param principalId         string

@description('Role definition GUID or name')
param roleDefinitionGuid      string

@description('Fully qualified resource path of the target container or database')
param scopePath string

var roleDefinitionId = resourceId(
  'Microsoft.DocumentDB/databaseAccounts/sqlRoleDefinitions',
  cosmosDbAccountName,
  roleDefinitionGuid
)

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2021-04-15' existing = {
  name: cosmosDbAccountName
}

resource containerRoleAssignmentUserContainer 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2022-05-15' = {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, principalId, roleDefinitionId, scopePath)
  properties: {
    principalId: principalId
    roleDefinitionId: roleDefinitionId
    scope: scopePath
  }
}
