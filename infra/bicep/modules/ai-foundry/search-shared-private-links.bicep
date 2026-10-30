targetScope = 'resourceGroup'

@description('Name of the solution Search service.')
param searchServiceName string
@description('Actual ARM ID of the Foundry account.')
param foundryAccountResourceId string
@description('Template-owned Search outbound shared private links.')
param links {
  name: string
  groupId: string
  requestMessage: string
}[]

resource search 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: searchServiceName
}

@batchSize(1)
resource sharedPrivateLinks 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2025-05-01' = [for link in links: {
  parent: search
  name: link.name
  properties: {
    groupId: link.groupId
    privateLinkResourceId: foundryAccountResourceId
    requestMessage: link.requestMessage
  }
}]
