// ==================================================================
// infra/modules/ai-foundry/connection-storage-account.bicep
// ==================================================================
metadata name = 'ai-foundry-connection-storage'
metadata description = 'Create a Storage Account connection in Azure AI Foundry account.'

@description('Required. The name of the Azure AI Foundry account.')
param aiFoundryName string

@description('Required. The name of the Storage Account to connect.')
param connectedResourceName string

@description('Optional. The name to assign to the Storage connection.')
param storageConnectionName string = '${connectedResourceName}-storage-connection'

// Reference existing AI Foundry account
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiFoundryName
  scope: resourceGroup()
}

// Reference existing Storage Account
resource existingStorage 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: connectedResourceName
}

// Create the Storage Account connection
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-06-01' = {
  name: storageConnectionName
  parent: aiFoundry
  properties: {
    category: 'AzureStorageAccount'
    target: existingStorage.properties.primaryEndpoints.blob
    authType: 'AAD' // Use Azure AD authentication (recommended)
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: existingStorage.id
    }
  }
}

@description('The name of the Storage connection.')
output connectionName string = storageConnectionName
