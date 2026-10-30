// ==================================================================
// infra/modules/ai-foundry/connection-application-insights.bicep
// ==================================================================
metadata name = 'ai-foundry-connection-app-insights'
metadata description = 'Create an Application Insights connection in Azure AI Foundry account. Supports both local (same-RG name) and BYO cross-RG references via `connectedResourceId`.'

@description('Required. The name of the Azure AI Foundry account.')
param aiFoundryName string

@description('Required. Resource ID of the Application Insights component to connect. Supports cross-subscription / cross-resource-group BYO via the explicit ID.')
param connectedResourceId string

@description('Optional. The name to assign to the App Insights connection.')
param appInsightsConnectionName string = '${aiFoundryName}-appinsights-connection'

// Reference existing AI Foundry account
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiFoundryName
  scope: resourceGroup()
}

// Parse the BYO/local Application Insights resource ID so we can reach it
// at its actual scope (works for same-RG and for cross-sub/cross-RG IDs).
var _idSegments  = split(connectedResourceId, '/')
var _aiSubId     = _idSegments[2]
var _aiRgName    = _idSegments[4]
var _aiName      = _idSegments[8]

// Reference existing Application Insights — scope is derived from the
// resource ID so this works for both local and cross-RG/sub IDs.
resource existingAppInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: _aiName
  scope: resourceGroup(_aiSubId, _aiRgName)
}

// Create the App Insights connection
resource connection 'Microsoft.CognitiveServices/accounts/connections@2025-06-01' = {
  name: appInsightsConnectionName
  parent: aiFoundry
  properties: {
    category: 'AppInsights'
    target: existingAppInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: existingAppInsights.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: existingAppInsights.id
    }
  }
}

@description('The name of the App Insights connection.')
output connectionName string = appInsightsConnectionName
