targetScope = 'resourceGroup'

param name string
param workspaceName string
param workspaceResourceId string
param appInsightsName string
param appInsightsResourceId string

resource privateLinkScope 'microsoft.insights/privatelinkscopes@2021-07-01-preview' = {
  name: name
  location: 'global'
  properties: {
    accessModeSettings: {
      queryAccessMode: 'Open'
      ingestionAccessMode: 'Open'
    }
  }
}

resource workspace 'microsoft.insights/privatelinkscopes/scopedresources@2021-07-01-preview' = {
  parent: privateLinkScope
  name: workspaceName
  properties: {
    linkedResourceId: workspaceResourceId
  }
}

resource appInsights 'microsoft.insights/privatelinkscopes/scopedresources@2021-07-01-preview' = {
  parent: privateLinkScope
  name: appInsightsName
  properties: {
    linkedResourceId: appInsightsResourceId
  }
}

output resourceId string = privateLinkScope.id
