@description('Full ARM resource ID of the effective Application Insights component.')
param appInsightsResourceId string

@description('Full ARM resource ID of the effective Log Analytics workspace.')
param workspaceResourceId string

@description('Principal ID of the AI Foundry project managed identity.')
param principalId string

@description('Built-in Reader role GUID.')
param readerRoleGuid string

@description('Built-in Log Analytics Data Reader role GUID.')
param logAnalyticsDataReaderRoleGuid string

@description('Built-in Privileged Monitoring Data Reader role GUID.')
param privilegedMonitoringDataReaderRoleGuid string

@description('Grant conditional Privileged Monitoring Data Reader for Protected AppGenAIContent.')
param grantProtectedTraceContentReader bool = false

var protectedTraceCondition = '(\n  (\n    !(ActionMatches{\'Microsoft.OperationalInsights/workspaces/tables/data/read\'})\n  )\n  OR\n  (\n    @Resource[Microsoft.OperationalInsights/workspaces/tables:name] StringEquals \'AppGenAIContent\'\n    AND\n    @Resource[Microsoft.OperationalInsights/workspaces/tables:protectionLevel] StringEquals \'Protected\'\n  )\n)'

var appInsightsSubscriptionId = split(appInsightsResourceId, '/')[2]
var appInsightsResourceGroupName = split(appInsightsResourceId, '/')[4]
var appInsightsName = last(split(appInsightsResourceId, '/'))

var workspaceSubscriptionId = split(workspaceResourceId, '/')[2]
var workspaceResourceGroupName = split(workspaceResourceId, '/')[4]
var workspaceName = last(split(workspaceResourceId, '/'))

module appInsightsTraceRoles './app-insights-trace-role-assignments.bicep' = {
  scope: resourceGroup(appInsightsSubscriptionId, appInsightsResourceGroupName)
  name: 'role-trace-appi-${uniqueString(appInsightsResourceId, principalId)}'
  params: {
    appInsightsName: appInsightsName
    appInsightsResourceId: appInsightsResourceId
    targetSubscriptionId: appInsightsSubscriptionId
    principalId: principalId
    readerRoleGuid: readerRoleGuid
    privilegedMonitoringDataReaderRoleGuid: privilegedMonitoringDataReaderRoleGuid
    grantProtectedTraceContentReader: grantProtectedTraceContentReader
    protectedTraceCondition: protectedTraceCondition
  }
}

module logAnalyticsTraceRoles './log-analytics-trace-role-assignments.bicep' = {
  scope: resourceGroup(workspaceSubscriptionId, workspaceResourceGroupName)
  name: 'role-trace-law-${uniqueString(workspaceResourceId, principalId)}'
  params: {
    workspaceName: workspaceName
    workspaceResourceId: workspaceResourceId
    targetSubscriptionId: workspaceSubscriptionId
    principalId: principalId
    logAnalyticsDataReaderRoleGuid: logAnalyticsDataReaderRoleGuid
    privilegedMonitoringDataReaderRoleGuid: privilegedMonitoringDataReaderRoleGuid
    grantProtectedTraceContentReader: grantProtectedTraceContentReader
    protectedTraceCondition: protectedTraceCondition
  }
}
