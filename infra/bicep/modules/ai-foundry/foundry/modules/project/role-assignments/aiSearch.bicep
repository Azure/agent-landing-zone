@description('Required. The name of the AI Search resource.')
param aiSearchName string

@description('Required. The principal ID of the project identity.')
param projectIdentityPrincipalId string

resource aiSearch 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: aiSearchName
  scope: resourceGroup()
}

resource indexDataContributorRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: '8ebe5a00-799e-43f5-93ac-243d3dce84a7' // Search Index Data Contributor
  scope: resourceGroup()
}

resource searchIndexDataContributorRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: aiSearch
  name: guid(projectIdentityPrincipalId, indexDataContributorRole.id, aiSearch.id)
  properties: {
    principalId: projectIdentityPrincipalId
    roleDefinitionId: indexDataContributorRole.id
    principalType: 'ServicePrincipal'
  }
}

resource searchServiceContributorRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: '7ca78c08-252a-4471-8644-bb5ff32d4ba0' // Search Service Contributor
  scope: resourceGroup()
}

resource searchServiceContributorRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: aiSearch
  name: guid(projectIdentityPrincipalId, searchServiceContributorRole.id, aiSearch.id)
  properties: {
    principalId: projectIdentityPrincipalId
    roleDefinitionId: searchServiceContributorRole.id
    principalType: 'ServicePrincipal'
  }
}
