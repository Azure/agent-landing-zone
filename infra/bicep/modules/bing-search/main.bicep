metadata name = 'bing-search'
metadata description = 'Create-or-reuse a Bing Grounding account and its Cognitive Services connection to be used by Azure AI Foundry.'

@description('Conditional. The name of the Azure Cognitive Services account to be used for the Bing Search tool. Required if `enableBingSearchConnection` is true.')
param accountName string

@description('Conditional. The name of the Azure Cognitive Services Project. Required if `enableBingSearchConnection` is true.')
param projectName string

@description('Conditional. The name to assign to the Bing Search resource instance (used when creating a new account). Required if `enableBingSearchConnection` is true.')
param bingSearchName string

@description('Conditional. The name to assign to the Bing Search connection in the project. Required if `enableBingSearchConnection` is true.')
param bingConnectionName string = '${bingSearchName}-connection'

@description('Optional. Existing Bing Grounding account resource ID to reuse instead of creating a new one.')
param existingResourceId string = ''

// Resolve create vs reuse
var varIsReuse = !empty(existingResourceId)
var varIdSegs = split(existingResourceId, '/')
var varExSub = length(varIdSegs) >= 3 ? varIdSegs[2] : ''
var varExRg = length(varIdSegs) >= 5 ? varIdSegs[4] : ''
var varExName = length(varIdSegs) >= 1 ? last(varIdSegs) : ''

// Cognitive Services account (same resource group as current deployment)
#disable-next-line BCP081
resource account_name_resource 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
  scope: resourceGroup()
}

// Reuse path: declare existing Bing account
#disable-next-line BCP081
resource existingBing 'Microsoft.Bing/accounts@2025-05-01-preview' existing = if (varIsReuse) {
  name: varExName
  scope: resourceGroup(varExSub, varExRg)
}

// Create path: create Bing account (global location)
#disable-next-line BCP081
resource bingAccount 'Microsoft.Bing/accounts@2025-05-01-preview' = if (!varIsReuse) {
  name: bingSearchName
  location: 'global'
  kind: 'Bing.Grounding'
  sku: {
    name: 'G1'
  }
}

// Effective props for both paths
var varBingId = varIsReuse ? existingResourceId : bingAccount.id
var varBingEndpoint = varIsReuse ? existingBing!.properties.endpoint : bingAccount!.properties.endpoint
var varBingKey = varIsReuse ? existingBing!.listKeys().key1 : bingAccount!.listKeys().key1
var varBingLocation = varIsReuse ? existingBing!.location : 'global'

// Create the Cognitive Services connection under the AI Services account
#disable-next-line BCP081
resource bing_search_account_connection 'Microsoft.CognitiveServices/accounts/connections@2025-06-01' = {
  name: bingConnectionName
  parent: account_name_resource
  properties: {
    category: 'GroundingWithBingSearch'
    target: varBingEndpoint
    authType: 'ApiKey'
    credentials: {
      key: varBingKey
    }
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      Location: varBingLocation
      ResourceId: varBingId
    }
  }
}

// Outputs
@description('Resource ID of the Bing Grounding account (created or reused).')
output resourceId string = varBingId

@description('Connection ID path under the AI services project.')
output bingConnectionId string = '/subscriptions/${subscription().subscriptionId}/resourceGroups/${resourceGroup().name}/providers/Microsoft.CognitiveServices/accounts/${accountName}/projects/${projectName}/connections/${bingConnectionName}'

@description('Name of the resource group where the Bing Grounding account is deployed (same as the deployment resource group when creating a new account, or the existing account resource group when reusing).')
output resourceGroupName string = resourceGroup().name
