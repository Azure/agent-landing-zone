@description('Log Analytics workspace name in the target resource group.')
param workspaceName string

@description('Full ARM resource ID of the Log Analytics workspace.')
param workspaceResourceId string

@description('Target subscription ID of the Log Analytics workspace.')
param targetSubscriptionId string

@description('Principal ID of the AI Foundry project managed identity.')
param principalId string

@description('Built-in Log Analytics Data Reader role GUID.')
param logAnalyticsDataReaderRoleGuid string

@description('Built-in Privileged Monitoring Data Reader role GUID.')
param privilegedMonitoringDataReaderRoleGuid string

@description('Grant conditional Privileged Monitoring Data Reader for Protected AppGenAIContent.')
param grantProtectedTraceContentReader bool

@description('ABAC v2.0 condition restricting workspace table reads to Protected AppGenAIContent.')
param protectedTraceCondition string

var dataReaderRoleDefinitionId = subscriptionResourceId(targetSubscriptionId, 'Microsoft.Authorization/roleDefinitions', logAnalyticsDataReaderRoleGuid)
var privilegedRoleDefinitionId = subscriptionResourceId(targetSubscriptionId, 'Microsoft.Authorization/roleDefinitions', privilegedMonitoringDataReaderRoleGuid)

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: workspaceName
}

resource dataReaderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: workspace
  name: guid(principalId, dataReaderRoleDefinitionId, workspaceResourceId)
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: dataReaderRoleDefinitionId
  }
}

resource privilegedAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (grantProtectedTraceContentReader) {
  scope: workspace
  name: guid(principalId, privilegedRoleDefinitionId, workspaceResourceId)
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: privilegedRoleDefinitionId
    conditionVersion: '2.0'
    condition: protectedTraceCondition
  }
}
