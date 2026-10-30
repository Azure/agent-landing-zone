@description('The name of the Azure Cognitive Services account to be used for the Bing Search tool.')
param account_name string  

@description('The name of the Azure Cognitive Services Project.')
param project_name string  

@description('The name to assign to the Bing Search resource instance.')
param bingSearchName string 

@description('The name to assign to the Bing Search resource instance.')
param bingConnectionName string  = '${bingSearchName}-connection'

#disable-next-line BCP081
resource account_name_resource 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: account_name
  scope: resourceGroup()
}

#disable-next-line BCP081
resource bingAccount 'Microsoft.Bing/accounts@2025-05-01-preview' = {
  name: bingSearchName
  location: 'global'
  kind: 'Bing.Grounding'
  sku: {
    name: 'G1'
  }
}

#disable-next-line BCP081
resource bing_search_account_connection 'Microsoft.CognitiveServices/accounts/connections@2025-06-01' = {
  name: bingConnectionName
  parent: account_name_resource
  properties: {
    category: 'GroundingWithBingSearch'
    target: bingAccount.properties.endpoint
    authType: 'ApiKey'
    credentials: {
      key: bingAccount.listKeys().key1
    }
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      Location: bingAccount.location
      ResourceId: bingAccount.id
    }
  }
}

output bingConnectionId string = '/subscriptions/${subscription().subscriptionId}/resourceGroups/${resourceGroup().name}/providers/Microsoft.CognitiveServices/accounts/${account_name}/projects/${project_name}/connections/${bingConnectionName}'
