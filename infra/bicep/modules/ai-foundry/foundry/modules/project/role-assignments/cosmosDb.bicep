@description('Required. The name of the Cosmos DB account.')
param cosmosDbName string

@description('Required. The principal ID of the project identity.')
param projectIdentityPrincipalId string

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts@2025-04-15' existing = {
  name: cosmosDbName
  scope: resourceGroup()
}

resource cosmosDBOperatorRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: '230815da-be43-4aae-9cb4-875f7bd000aa' // Cosmos DB Operator
  scope: resourceGroup()
}

// NOTE: using resource module over AVM due to resource possibly existing out of the current scope
resource cosmosDBOperatorRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: cosmosDb
  name: guid(projectIdentityPrincipalId, cosmosDBOperatorRole.id, cosmosDb.id)
  properties: {
    principalId: projectIdentityPrincipalId
    roleDefinitionId: cosmosDBOperatorRole.id
    principalType: 'ServicePrincipal'
  }
}
