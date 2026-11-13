@description('Application Insights component name in the target resource group.')
param appInsightsName string

@description('Full ARM resource ID of the Application Insights component.')
param appInsightsResourceId string

@description('Target subscription ID of the Application Insights component.')
param targetSubscriptionId string

@description('Principal ID of the AI Foundry project managed identity.')
param principalId string

@description('Built-in Reader role GUID.')
param readerRoleGuid string

@description('Built-in Privileged Monitoring Data Reader role GUID.')
param privilegedMonitoringDataReaderRoleGuid string

@description('Grant conditional Privileged Monitoring Data Reader for Protected AppGenAIContent.')
param grantProtectedTraceContentReader bool

@description('ABAC v2.0 condition restricting workspace table reads to Protected AppGenAIContent.')
param protectedTraceCondition string

var readerRoleDefinitionId = subscriptionResourceId(targetSubscriptionId, 'Microsoft.Authorization/roleDefinitions', readerRoleGuid)
var privilegedRoleDefinitionId = subscriptionResourceId(targetSubscriptionId, 'Microsoft.Authorization/roleDefinitions', privilegedMonitoringDataReaderRoleGuid)

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

resource readerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: appInsights
  name: guid(principalId, readerRoleDefinitionId, appInsightsResourceId)
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: readerRoleDefinitionId
  }
}

resource privilegedAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (grantProtectedTraceContentReader) {
  scope: appInsights
  name: guid(principalId, privilegedRoleDefinitionId, appInsightsResourceId)
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: privilegedRoleDefinitionId
    conditionVersion: '2.0'
    condition: protectedTraceCondition
  }
}
