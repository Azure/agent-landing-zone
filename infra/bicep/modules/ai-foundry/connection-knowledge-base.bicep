metadata name = 'ai-foundry-connection-knowledge-base'
metadata description = 'Project MCP connection to a Search knowledge base using project managed identity.'

param aiFoundryName string
param aiProjectName string
param knowledgeBaseConnectionName string
param searchEndpoint string
param knowledgeBaseName string
param knowledgeApiVersion string

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiFoundryName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: account
  name: aiProjectName
}

// Match azd's raw ARM connection API, which supports the newer Foundry auth types.
resource connection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: knowledgeBaseConnectionName
  properties: {
    category: 'RemoteTool'
    authType: 'ProjectManagedIdentity'
    target: '${searchEndpoint}/knowledgebases/${knowledgeBaseName}/mcp?api-version=${knowledgeApiVersion}'
    audience: 'https://search.azure.com/'
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
    }
  }
}

output connectionId string = connection.id
