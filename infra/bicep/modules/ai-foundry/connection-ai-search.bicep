// ==================================================================
// infra/modules/ai-foundry/connection-ai-search.bicep
// ==================================================================
metadata name = 'ai-foundry-connection-ai-search'
metadata description = 'Create an Azure AI Search connection in Azure AI Foundry account.'

@description('Required. The name of the Azure AI Foundry account.')
param aiFoundryName string

@description('Required. The name of the Azure AI Foundry project.')
param aiProjectName string

@description('Required. The name of the Azure AI Search service to connect.')
param connectedResourceName string

@description('Optional. The name to assign to the AI Search connection.')
param aiSearchConnectionName string = '${connectedResourceName}-connection'

// Reference existing AI Foundry account
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiFoundryName
  scope: resourceGroup()
}

// Reference existing AI Search service
resource existingSearchService 'Microsoft.Search/searchServices@2025-02-01-preview' existing = {
  name: connectedResourceName
}

// Create the AI Search connection
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-06-01' = {
  name: aiSearchConnectionName
  parent: aiFoundry
  properties: {
    category: 'CognitiveSearch'
    target: existingSearchService.properties.endpoint
    authType: 'AAD' // Use Azure AD authentication (recommended)
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: existingSearchService.id
      location: existingSearchService.location
    }
  }
}

@description('Connection ID path under the AI services project.')
output searchConnectionId string = '/subscriptions/${subscription().subscriptionId}/resourceGroups/${resourceGroup().name}/providers/Microsoft.CognitiveServices/accounts/${aiFoundryName}/projects/${aiProjectName}/connections/${aiSearchConnectionName}'

@description('The name of the AI Search connection.')
output connectionName string = aiSearchConnectionName
