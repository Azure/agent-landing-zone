@description('Required. The name of the Cosmos DB account.')
param cosmosDbName string

@description('Required. The principal ID of the project identity.')
param projectIdentityPrincipalId string

@description('Required. The project workspace ID.')
param projectWorkspaceId string

// Name of the database that the Foundry capability host owns. Isolated as a
// variable so the Foundry contract is named once and reused.
var foundryCapabilityHostDbName = 'enterprise_memory'

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts@2025-04-15' existing = {
  name: cosmosDbName
  scope: resourceGroup()
}

var cosmosDefaultSqlRoleDefinitionId = resourceId(
  'Microsoft.DocumentDB/databaseAccounts/sqlRoleDefinitions',
  cosmosDbName,
  '00000000-0000-0000-0000-000000000002'
)

var foundryCapabilityHostDbScope = '${cosmosDb.id}/dbs/${foundryCapabilityHostDbName}'

// The Foundry Agent Service v2 capability host owns every collection under the
// `enterprise_memory` database and creates additional containers lazily at
// runtime (for example `<workspaceId>-aoaiv2-vector-store-store`). A
// per-collection role assignment cannot cover containers that do not exist
// yet, which causes `AIProjectClient.agents.create_version` / `run_stream` to
// fail with Cosmos 403 in regions such as `swedencentral`. We assign Built-in
// Data Contributor at database scope so the project identity is authorized
// over the whole capability-host DB. See issue #94.
// projectWorkspaceId is included in the role assignment name so that
// redeploys remain deterministic and so the calling module's contract stays
// stable (the parameter was previously used to interpolate per-collection
// scopes).
resource cosmosDataRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2025-04-15' = {
  parent: cosmosDb
  name: guid(
    cosmosDefaultSqlRoleDefinitionId,
    projectIdentityPrincipalId,
    foundryCapabilityHostDbScope,
    projectWorkspaceId
  )
  properties: {
    principalId: projectIdentityPrincipalId
    roleDefinitionId: cosmosDefaultSqlRoleDefinitionId
    scope: foundryCapabilityHostDbScope
  }
}
