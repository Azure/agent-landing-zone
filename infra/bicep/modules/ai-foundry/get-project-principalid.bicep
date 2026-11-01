// ============================================================================
// Helper module to retrieve AI Project Principal ID
// This module uses an 'existing' resource reference to access the managed
// identity principalId of an AI Foundry project.
// ============================================================================

targetScope = 'resourceGroup'

@description('The name of the AI Services account.')
param accountName string

@description('The name of the AI Foundry project.')
param projectName string

// Reference the existing AI Project
resource aiProject 'Microsoft.CognitiveServices/accounts/projects@2025-09-01' existing = {
  name: '${accountName}/${projectName}'
}

@description('The principal ID of the AI Foundry project managed identity.')
output principalId string = aiProject.identity.principalId
