@description('Parameter-only prerequisite validation for opt-in Foundry trace evaluation RBAC.')
param grantProjectTraceEvaluationReader bool
param grantProjectProtectedTraceContentReader bool
param deployAiFoundry bool
param deployAfProject bool
param hasEffectiveAppInsights bool
param hasEffectiveLogAnalytics bool
param existingApplicationInsightsResourceId string
param existingLogAnalyticsWorkspaceResourceId string

var baseReaderSatisfied = !grantProjectProtectedTraceContentReader || grantProjectTraceEvaluationReader
var foundryProjectSatisfied = deployAiFoundry && deployAfProject
var observabilitySatisfied = hasEffectiveAppInsights && hasEffectiveLogAnalytics
var existingAppInsightsSegments = split(trim(existingApplicationInsightsResourceId), '/')
var existingLawSegments = split(trim(existingLogAnalyticsWorkspaceResourceId), '/')
var existingAppInsightsValid = empty(trim(existingApplicationInsightsResourceId)) || (length(existingAppInsightsSegments) == 9 && empty(existingAppInsightsSegments[0]) && toLower(existingAppInsightsSegments[1]) == 'subscriptions' && !empty(existingAppInsightsSegments[2]) && toLower(existingAppInsightsSegments[3]) == 'resourcegroups' && !empty(existingAppInsightsSegments[4]) && toLower(existingAppInsightsSegments[5]) == 'providers' && toLower(existingAppInsightsSegments[6]) == 'microsoft.insights' && toLower(existingAppInsightsSegments[7]) == 'components' && !empty(existingAppInsightsSegments[8]))
var existingLawValid = empty(trim(existingLogAnalyticsWorkspaceResourceId)) || (length(existingLawSegments) == 9 && empty(existingLawSegments[0]) && toLower(existingLawSegments[1]) == 'subscriptions' && !empty(existingLawSegments[2]) && toLower(existingLawSegments[3]) == 'resourcegroups' && !empty(existingLawSegments[4]) && toLower(existingLawSegments[5]) == 'providers' && toLower(existingLawSegments[6]) == 'microsoft.operationalinsights' && toLower(existingLawSegments[7]) == 'workspaces' && !empty(existingLawSegments[8]))

output validated bool = !baseReaderSatisfied
  ? fail('grantProjectProtectedTraceContentReader requires grantProjectTraceEvaluationReader=true.')
  : !foundryProjectSatisfied
    ? fail('Scheduled Foundry trace evaluation permissions require deployAiFoundry=true and deployAfProject=true.')
    : !observabilitySatisfied
      ? fail('Scheduled Foundry trace evaluation permissions require effective Application Insights and Log Analytics resources.')
      : !(existingAppInsightsValid && existingLawValid)
        ? fail('Existing Application Insights and Log Analytics resource IDs must be full ARM resource IDs.')
        : true
