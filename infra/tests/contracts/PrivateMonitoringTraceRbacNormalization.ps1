# Issue #882 Task 5: exact bounded inverse of the AMPLS Azure Automation DNS
# zone hyphenation fix (`privatelink.agentsvc.azure-automation.net`) and opt-in
# scheduled Foundry trace-evaluation RBAC (`grantProjectTraceEvaluationReader`,
# `grantProjectProtectedTraceContentReader`), compiled with Bicep 0.42.1.
# Historical fixtures and downstream normalization digests remain untouched.
function Get-PrivateMonitoringTraceRbacProjection {
    $dnsZonesListAfter = "[if(variables('_deployPrivateDnsZones'), concat(if(and(parameters('deployPostgreSql'), not(variables('_byoZonePostgreSql'))), createArray(createObject('dnsName', 'privatelink.postgres.database.azure.com', 'virtualNetworkLinkName', format('{0}-postgresql-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix')))), createArray()), if(and(parameters('deployDurableTaskScheduler'), empty(parameters('existingPrivateDnsZoneDurableTaskResourceId'))), createArray(createObject('dnsName', 'privatelink.durabletask.io', 'virtualNetworkLinkName', format('{0}-durabletask-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix')))), createArray()), if(variables('_byoZoneCogSvcs'), createArray(), createArray(createObject('dnsName', 'privatelink.cognitiveservices.azure.com', 'virtualNetworkLinkName', format('{0}-cogsvcs-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix'))))), if(variables('_byoZoneOpenAi'), createArray(), createArray(createObject('dnsName', 'privatelink.openai.azure.com', 'virtualNetworkLinkName', format('{0}-openai-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix'))))), if(variables('_byoZoneAiServices'), createArray(), createArray(createObject('dnsName', 'privatelink.services.ai.azure.com', 'virtualNetworkLinkName', format('{0}-aiservices-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix'))))), if(variables('_byoZoneSearch'), createArray(), createArray(createObject('dnsName', 'privatelink.search.windows.net', 'virtualNetworkLinkName', format('{0}-search-std-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix'))))), if(variables('_byoZoneCosmos'), createArray(), createArray(createObject('dnsName', 'privatelink.documents.azure.com', 'virtualNetworkLinkName', format('{0}-cosmos-std-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix'))))), if(variables('_byoZoneBlob'), createArray(), createArray(createObject('dnsName', format('privatelink.blob.{0}', environment().suffixes.storage), 'virtualNetworkLinkName', format('{0}-blob-std-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix'))))), if(variables('_byoZoneKeyVault'), createArray(), createArray(createObject('dnsName', 'privatelink.vaultcore.azure.net', 'virtualNetworkLinkName', format('{0}-kv-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix'))))), if(variables('_byoZoneAppConfig'), createArray(), createArray(createObject('dnsName', 'privatelink.azconfig.io', 'virtualNetworkLinkName', format('{0}-appcfg-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix'))))), if(and(parameters('deployContainerEnv'), not(variables('_byoZoneContainerApps'))), createArray(createObject('dnsName', format('privatelink.{0}.azurecontainerapps.io', parameters('location')), 'virtualNetworkLinkName', format('{0}-containerapps-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix')))), createArray()), if(and(parameters('deployContainerRegistry'), not(variables('_byoZoneAcr'))), createArray(createObject('dnsName', format('privatelink.{0}', parameters('acrDnsSuffix')), 'virtualNetworkLinkName', format('{0}-containerregistry-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix')))), createArray()), if(variables('_deployAmpls'), concat(if(variables('_byoZoneAppInsights'), createArray(), createArray(createObject('dnsName', 'privatelink.applicationinsights.io', 'virtualNetworkLinkName', format('{0}-appi-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix'))))), if(variables('_byoZoneAzureMonitor'), createArray(), createArray(createObject('dnsName', 'privatelink.monitor.azure.com', 'virtualNetworkLinkName', format('{0}-azure-monitor-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix'))))), if(variables('_byoZoneOmsOpInsights'), createArray(), createArray(createObject('dnsName', 'privatelink.oms.opinsights.azure.com', 'virtualNetworkLinkName', format('{0}-oms-opinsights-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix'))))), if(variables('_byoZoneOdsOpInsights'), createArray(), createArray(createObject('dnsName', 'privatelink.ods.opinsights.azure.com', 'virtualNetworkLinkName', format('{0}-ods-opinsights-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix'))))), if(variables('_byoZoneAzureAutomation'), createArray(), createArray(createObject('dnsName', 'privatelink.agentsvc.azure-automation.net', 'virtualNetworkLinkName', format('{0}-azure-automation-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix')))))), createArray())), createArray())]"
    $dnsZonesListBefore = $dnsZonesListAfter.Replace('privatelink.agentsvc.azure-automation.net', 'privatelink.agentsvc.azure.automation.net')

    $dnsZoneAzureAutomationIdAfter = "[if(not(empty(coalesce(parameters('existingPrivateDnsZoneAzureAutomationResourceId'), ''))), parameters('existingPrivateDnsZoneAzureAutomationResourceId'), resourceId(variables('_dnsZonesSubscriptionId'), variables('_dnsZonesResourceGroupName'), 'Microsoft.Network/privateDnsZones', 'privatelink.agentsvc.azure-automation.net'))]"
    $dnsZoneAzureAutomationIdBefore = $dnsZoneAzureAutomationIdAfter.Replace('privatelink.agentsvc.azure-automation.net', 'privatelink.agentsvc.azure.automation.net')

    $protectedCondition = "(`n  (`n    !(ActionMatches{'Microsoft.OperationalInsights/workspaces/tables/data/read'})`n  )`n  OR`n  (`n    @Resource[Microsoft.OperationalInsights/workspaces/tables:name] StringEquals 'AppGenAIContent'`n    AND`n    @Resource[Microsoft.OperationalInsights/workspaces/tables:protectionLevel] StringEquals 'Protected'`n  )`n)"

    $traceValidationResource = [ordered]@{
        condition  = "[or(parameters('grantProjectTraceEvaluationReader'), parameters('grantProjectProtectedTraceContentReader'))]"
        type       = 'Microsoft.Resources/deployments'
        apiVersion = '2025-04-01'
        name       = 'traceEvaluationValidation'
        properties = [ordered]@{
            expressionEvaluationOptions = [ordered]@{ scope = 'inner' }
            mode                        = 'Incremental'
            parameters                  = [ordered]@{
                grantProjectTraceEvaluationReader          = [ordered]@{ value = "[parameters('grantProjectTraceEvaluationReader')]" }
                grantProjectProtectedTraceContentReader    = [ordered]@{ value = "[parameters('grantProjectProtectedTraceContentReader')]" }
                deployAiFoundry                            = [ordered]@{ value = "[parameters('deployAiFoundry')]" }
                deployAfProject                            = [ordered]@{ value = "[parameters('deployAfProject')]" }
                hasEffectiveAppInsights                    = [ordered]@{ value = "[variables('_hasEffectiveAI')]" }
                hasEffectiveLogAnalytics                   = [ordered]@{ value = "[variables('_hasEffectiveLaw')]" }
                existingApplicationInsightsResourceId      = [ordered]@{ value = "[coalesce(parameters('existingApplicationInsightsResourceId'), '')]" }
                existingLogAnalyticsWorkspaceResourceId    = [ordered]@{ value = "[coalesce(parameters('existingLogAnalyticsWorkspaceResourceId'), '')]" }
            }
            template                    = [ordered]@{
                '$schema'      = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#'
                contentVersion = '1.0.0.0'
                metadata       = [ordered]@{ _generator = [ordered]@{ name = 'bicep' } }
                parameters     = [ordered]@{
                    grantProjectTraceEvaluationReader       = [ordered]@{
                        type     = 'bool'
                        metadata = [ordered]@{ description = 'Parameter-only prerequisite validation for opt-in Foundry trace evaluation RBAC.' }
                    }
                    grantProjectProtectedTraceContentReader = [ordered]@{ type = 'bool' }
                    deployAiFoundry                         = [ordered]@{ type = 'bool' }
                    deployAfProject                         = [ordered]@{ type = 'bool' }
                    hasEffectiveAppInsights                 = [ordered]@{ type = 'bool' }
                    hasEffectiveLogAnalytics                = [ordered]@{ type = 'bool' }
                    existingApplicationInsightsResourceId   = [ordered]@{ type = 'string' }
                    existingLogAnalyticsWorkspaceResourceId = [ordered]@{ type = 'string' }
                }
                variables      = [ordered]@{
                    baseReaderSatisfied         = "[or(not(parameters('grantProjectProtectedTraceContentReader')), parameters('grantProjectTraceEvaluationReader'))]"
                    foundryProjectSatisfied     = "[and(parameters('deployAiFoundry'), parameters('deployAfProject'))]"
                    observabilitySatisfied      = "[and(parameters('hasEffectiveAppInsights'), parameters('hasEffectiveLogAnalytics'))]"
                    existingAppInsightsSegments = "[split(trim(parameters('existingApplicationInsightsResourceId')), '/')]"
                    existingLawSegments         = "[split(trim(parameters('existingLogAnalyticsWorkspaceResourceId')), '/')]"
                    existingAppInsightsValid    = "[or(empty(trim(parameters('existingApplicationInsightsResourceId'))), and(and(and(and(and(and(and(and(and(equals(length(variables('existingAppInsightsSegments')), 9), empty(variables('existingAppInsightsSegments')[0])), equals(toLower(variables('existingAppInsightsSegments')[1]), 'subscriptions')), not(empty(variables('existingAppInsightsSegments')[2]))), equals(toLower(variables('existingAppInsightsSegments')[3]), 'resourcegroups')), not(empty(variables('existingAppInsightsSegments')[4]))), equals(toLower(variables('existingAppInsightsSegments')[5]), 'providers')), equals(toLower(variables('existingAppInsightsSegments')[6]), 'microsoft.insights')), equals(toLower(variables('existingAppInsightsSegments')[7]), 'components')), not(empty(variables('existingAppInsightsSegments')[8]))))]"
                    existingLawValid            = "[or(empty(trim(parameters('existingLogAnalyticsWorkspaceResourceId'))), and(and(and(and(and(and(and(and(and(equals(length(variables('existingLawSegments')), 9), empty(variables('existingLawSegments')[0])), equals(toLower(variables('existingLawSegments')[1]), 'subscriptions')), not(empty(variables('existingLawSegments')[2]))), equals(toLower(variables('existingLawSegments')[3]), 'resourcegroups')), not(empty(variables('existingLawSegments')[4]))), equals(toLower(variables('existingLawSegments')[5]), 'providers')), equals(toLower(variables('existingLawSegments')[6]), 'microsoft.operationalinsights')), equals(toLower(variables('existingLawSegments')[7]), 'workspaces')), not(empty(variables('existingLawSegments')[8]))))]"
                }
                resources      = @()
                outputs        = [ordered]@{
                    validated = [ordered]@{
                        type  = 'bool'
                        value = "[if(not(variables('baseReaderSatisfied')), fail('grantProjectProtectedTraceContentReader requires grantProjectTraceEvaluationReader=true.'), if(not(variables('foundryProjectSatisfied')), fail('Scheduled Foundry trace evaluation permissions require deployAiFoundry=true and deployAfProject=true.'), if(not(variables('observabilitySatisfied')), fail('Scheduled Foundry trace evaluation permissions require effective Application Insights and Log Analytics resources.'), if(not(and(variables('existingAppInsightsValid'), variables('existingLawValid'))), fail('Existing Application Insights and Log Analytics resource IDs must be full ARM resource IDs.'), true()))))]"
                    }
                }
            }
        }
    }

    $traceRolesResource = [ordered]@{
        condition  = "[and(and(and(and(parameters('grantProjectTraceEvaluationReader'), parameters('deployAiFoundry')), parameters('deployAfProject')), variables('_hasEffectiveAI')), variables('_hasEffectiveLaw'))]"
        type       = 'Microsoft.Resources/deployments'
        apiVersion = '2025-04-01'
        name       = 'assignProjectTraceEvaluationRoles'
        properties = [ordered]@{
            expressionEvaluationOptions = [ordered]@{ scope = 'inner' }
            mode                        = 'Incremental'
            parameters                  = [ordered]@{
                appInsightsResourceId                  = "[if(variables('_hasExistingAI'), createObject('value', parameters('existingApplicationInsightsResourceId')), if(variables('_createAppInsights'), createObject('value', reference('appInsights').outputs.resourceId.value), createObject('value', '')))]"
                workspaceResourceId                    = "[if(variables('_hasExistingLaw'), createObject('value', parameters('existingLogAnalyticsWorkspaceResourceId')), if(variables('_createLogAnalytics'), createObject('value', reference('logAnalytics').outputs.resourceId.value), createObject('value', '')))]"
                principalId                            = [ordered]@{ value = "[reference('aiFoundry').outputs.aiProjectPrincipalId.value]" }
                readerRoleGuid                         = [ordered]@{ value = "[variables('_1.roles').Reader.guid]" }
                logAnalyticsDataReaderRoleGuid         = [ordered]@{ value = "[variables('_logAnalyticsDataReaderRoleId')]" }
                privilegedMonitoringDataReaderRoleGuid = [ordered]@{ value = "[variables('_privilegedMonitoringDataReaderRoleId')]" }
                grantProtectedTraceContentReader       = [ordered]@{ value = "[parameters('grantProjectProtectedTraceContentReader')]" }
            }
            template                    = [ordered]@{
                '$schema'      = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#'
                contentVersion = '1.0.0.0'
                metadata       = [ordered]@{ _generator = [ordered]@{ name = 'bicep' } }
                parameters     = [ordered]@{
                    appInsightsResourceId                  = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Full ARM resource ID of the effective Application Insights component.' } }
                    workspaceResourceId                    = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Full ARM resource ID of the effective Log Analytics workspace.' } }
                    principalId                            = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Principal ID of the AI Foundry project managed identity.' } }
                    readerRoleGuid                         = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Built-in Reader role GUID.' } }
                    logAnalyticsDataReaderRoleGuid         = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Built-in Log Analytics Data Reader role GUID.' } }
                    privilegedMonitoringDataReaderRoleGuid = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Built-in Privileged Monitoring Data Reader role GUID.' } }
                    grantProtectedTraceContentReader       = [ordered]@{ type = 'bool'; defaultValue = $false; metadata = [ordered]@{ description = 'Grant conditional Privileged Monitoring Data Reader for Protected AppGenAIContent.' } }
                }
                variables      = [ordered]@{
                    protectedTraceCondition       = $protectedCondition
                    appInsightsSubscriptionId     = "[split(parameters('appInsightsResourceId'), '/')[2]]"
                    appInsightsResourceGroupName  = "[split(parameters('appInsightsResourceId'), '/')[4]]"
                    appInsightsName               = "[last(split(parameters('appInsightsResourceId'), '/'))]"
                    workspaceSubscriptionId       = "[split(parameters('workspaceResourceId'), '/')[2]]"
                    workspaceResourceGroupName    = "[split(parameters('workspaceResourceId'), '/')[4]]"
                    workspaceName                 = "[last(split(parameters('workspaceResourceId'), '/'))]"
                }
                resources      = @(
                    [ordered]@{
                        type           = 'Microsoft.Resources/deployments'
                        apiVersion     = '2025-04-01'
                        name           = "[format('role-trace-appi-{0}', uniqueString(parameters('appInsightsResourceId'), parameters('principalId')))]"
                        subscriptionId = "[variables('appInsightsSubscriptionId')]"
                        resourceGroup  = "[variables('appInsightsResourceGroupName')]"
                        properties     = [ordered]@{
                            expressionEvaluationOptions = [ordered]@{ scope = 'inner' }
                            mode                        = 'Incremental'
                            parameters                  = [ordered]@{
                                appInsightsName                        = [ordered]@{ value = "[variables('appInsightsName')]" }
                                appInsightsResourceId                  = [ordered]@{ value = "[parameters('appInsightsResourceId')]" }
                                targetSubscriptionId                   = [ordered]@{ value = "[variables('appInsightsSubscriptionId')]" }
                                principalId                            = [ordered]@{ value = "[parameters('principalId')]" }
                                readerRoleGuid                         = [ordered]@{ value = "[parameters('readerRoleGuid')]" }
                                privilegedMonitoringDataReaderRoleGuid = [ordered]@{ value = "[parameters('privilegedMonitoringDataReaderRoleGuid')]" }
                                grantProtectedTraceContentReader       = [ordered]@{ value = "[parameters('grantProtectedTraceContentReader')]" }
                                protectedTraceCondition                = [ordered]@{ value = "[variables('protectedTraceCondition')]" }
                            }
                            template                    = [ordered]@{
                                '$schema'      = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#'
                                contentVersion = '1.0.0.0'
                                metadata       = [ordered]@{ _generator = [ordered]@{ name = 'bicep' } }
                                parameters     = [ordered]@{
                                    appInsightsName                        = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Application Insights component name in the target resource group.' } }
                                    appInsightsResourceId                  = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Full ARM resource ID of the Application Insights component.' } }
                                    targetSubscriptionId                   = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Target subscription ID of the Application Insights component.' } }
                                    principalId                            = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Principal ID of the AI Foundry project managed identity.' } }
                                    readerRoleGuid                         = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Built-in Reader role GUID.' } }
                                    privilegedMonitoringDataReaderRoleGuid = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Built-in Privileged Monitoring Data Reader role GUID.' } }
                                    grantProtectedTraceContentReader       = [ordered]@{ type = 'bool'; metadata = [ordered]@{ description = 'Grant conditional Privileged Monitoring Data Reader for Protected AppGenAIContent.' } }
                                    protectedTraceCondition                = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'ABAC v2.0 condition restricting workspace table reads to Protected AppGenAIContent.' } }
                                }
                                variables      = [ordered]@{
                                    readerRoleDefinitionId     = "[subscriptionResourceId(parameters('targetSubscriptionId'), 'Microsoft.Authorization/roleDefinitions', parameters('readerRoleGuid'))]"
                                    privilegedRoleDefinitionId = "[subscriptionResourceId(parameters('targetSubscriptionId'), 'Microsoft.Authorization/roleDefinitions', parameters('privilegedMonitoringDataReaderRoleGuid'))]"
                                }
                                resources      = @(
                                    [ordered]@{
                                        type       = 'Microsoft.Authorization/roleAssignments'
                                        apiVersion = '2022-04-01'
                                        scope      = "[resourceId('Microsoft.Insights/components', parameters('appInsightsName'))]"
                                        name       = "[guid(parameters('principalId'), variables('readerRoleDefinitionId'), parameters('appInsightsResourceId'))]"
                                        properties = [ordered]@{
                                            principalId      = "[parameters('principalId')]"
                                            principalType    = 'ServicePrincipal'
                                            roleDefinitionId = "[variables('readerRoleDefinitionId')]"
                                        }
                                    },
                                    [ordered]@{
                                        condition  = "[parameters('grantProtectedTraceContentReader')]"
                                        type       = 'Microsoft.Authorization/roleAssignments'
                                        apiVersion = '2022-04-01'
                                        scope      = "[resourceId('Microsoft.Insights/components', parameters('appInsightsName'))]"
                                        name       = "[guid(parameters('principalId'), variables('privilegedRoleDefinitionId'), parameters('appInsightsResourceId'))]"
                                        properties = [ordered]@{
                                            principalId      = "[parameters('principalId')]"
                                            principalType    = 'ServicePrincipal'
                                            roleDefinitionId = "[variables('privilegedRoleDefinitionId')]"
                                            conditionVersion = '2.0'
                                            condition        = "[parameters('protectedTraceCondition')]"
                                        }
                                    }
                                )
                            }
                        }
                    },
                    [ordered]@{
                        type           = 'Microsoft.Resources/deployments'
                        apiVersion     = '2025-04-01'
                        name           = "[format('role-trace-law-{0}', uniqueString(parameters('workspaceResourceId'), parameters('principalId')))]"
                        subscriptionId = "[variables('workspaceSubscriptionId')]"
                        resourceGroup  = "[variables('workspaceResourceGroupName')]"
                        properties     = [ordered]@{
                            expressionEvaluationOptions = [ordered]@{ scope = 'inner' }
                            mode                        = 'Incremental'
                            parameters                  = [ordered]@{
                                workspaceName                          = [ordered]@{ value = "[variables('workspaceName')]" }
                                workspaceResourceId                    = [ordered]@{ value = "[parameters('workspaceResourceId')]" }
                                targetSubscriptionId                   = [ordered]@{ value = "[variables('workspaceSubscriptionId')]" }
                                principalId                            = [ordered]@{ value = "[parameters('principalId')]" }
                                logAnalyticsDataReaderRoleGuid         = [ordered]@{ value = "[parameters('logAnalyticsDataReaderRoleGuid')]" }
                                privilegedMonitoringDataReaderRoleGuid = [ordered]@{ value = "[parameters('privilegedMonitoringDataReaderRoleGuid')]" }
                                grantProtectedTraceContentReader       = [ordered]@{ value = "[parameters('grantProtectedTraceContentReader')]" }
                                protectedTraceCondition                = [ordered]@{ value = "[variables('protectedTraceCondition')]" }
                            }
                            template                    = [ordered]@{
                                '$schema'      = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#'
                                contentVersion = '1.0.0.0'
                                metadata       = [ordered]@{ _generator = [ordered]@{ name = 'bicep' } }
                                parameters     = [ordered]@{
                                    workspaceName                          = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Log Analytics workspace name in the target resource group.' } }
                                    workspaceResourceId                    = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Full ARM resource ID of the Log Analytics workspace.' } }
                                    targetSubscriptionId                   = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Target subscription ID of the Log Analytics workspace.' } }
                                    principalId                            = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Principal ID of the AI Foundry project managed identity.' } }
                                    logAnalyticsDataReaderRoleGuid         = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Built-in Log Analytics Data Reader role GUID.' } }
                                    privilegedMonitoringDataReaderRoleGuid = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'Built-in Privileged Monitoring Data Reader role GUID.' } }
                                    grantProtectedTraceContentReader       = [ordered]@{ type = 'bool'; metadata = [ordered]@{ description = 'Grant conditional Privileged Monitoring Data Reader for Protected AppGenAIContent.' } }
                                    protectedTraceCondition                = [ordered]@{ type = 'string'; metadata = [ordered]@{ description = 'ABAC v2.0 condition restricting workspace table reads to Protected AppGenAIContent.' } }
                                }
                                variables      = [ordered]@{
                                    dataReaderRoleDefinitionId = "[subscriptionResourceId(parameters('targetSubscriptionId'), 'Microsoft.Authorization/roleDefinitions', parameters('logAnalyticsDataReaderRoleGuid'))]"
                                    privilegedRoleDefinitionId = "[subscriptionResourceId(parameters('targetSubscriptionId'), 'Microsoft.Authorization/roleDefinitions', parameters('privilegedMonitoringDataReaderRoleGuid'))]"
                                }
                                resources      = @(
                                    [ordered]@{
                                        type       = 'Microsoft.Authorization/roleAssignments'
                                        apiVersion = '2022-04-01'
                                        scope      = "[resourceId('Microsoft.OperationalInsights/workspaces', parameters('workspaceName'))]"
                                        name       = "[guid(parameters('principalId'), variables('dataReaderRoleDefinitionId'), parameters('workspaceResourceId'))]"
                                        properties = [ordered]@{
                                            principalId      = "[parameters('principalId')]"
                                            principalType    = 'ServicePrincipal'
                                            roleDefinitionId = "[variables('dataReaderRoleDefinitionId')]"
                                        }
                                    },
                                    [ordered]@{
                                        condition  = "[parameters('grantProtectedTraceContentReader')]"
                                        type       = 'Microsoft.Authorization/roleAssignments'
                                        apiVersion = '2022-04-01'
                                        scope      = "[resourceId('Microsoft.OperationalInsights/workspaces', parameters('workspaceName'))]"
                                        name       = "[guid(parameters('principalId'), variables('privilegedRoleDefinitionId'), parameters('workspaceResourceId'))]"
                                        properties = [ordered]@{
                                            principalId      = "[parameters('principalId')]"
                                            principalType    = 'ServicePrincipal'
                                            roleDefinitionId = "[variables('privilegedRoleDefinitionId')]"
                                            conditionVersion = '2.0'
                                            condition        = "[parameters('protectedTraceCondition')]"
                                        }
                                    }
                                )
                            }
                        }
                    }
                )
            }
        }
        dependsOn  = @('aiFoundry', 'appInsights', 'logAnalytics', 'traceEvaluationValidation')
    }

    return @{
        kind    = 'object'
        changes = @{
            parameters = @{
                kind    = 'object'
                changes = @{
                    existingPrivateDnsZoneAzureAutomationResourceId = @{
                        kind    = 'object'
                        changes = @{
                            metadata = @{
                                kind    = 'object'
                                changes = @{
                                    description = @{
                                        kind   = 'changed'
                                        after  = 'Gap 2 — Resource ID of an existing `privatelink.agentsvc.azure-automation.net` Private DNS Zone to reuse (Azure Monitor agent service PE DNS).'
                                        before = 'Gap 2 — Resource ID of an existing `privatelink.agentsvc.azure.automation.net` Private DNS Zone to reuse (Azure Monitor agent service PE DNS).'
                                    }
                                }
                            }
                        }
                    }
                    grantProjectTraceEvaluationReader               = @{
                        kind  = 'added'
                        after = @{
                            type         = 'bool'
                            defaultValue = $false
                            metadata     = @{
                                description = 'Opt-in: grant the AI Foundry project managed identity Reader on the effective Application Insights resource and Log Analytics Data Reader on the effective Log Analytics workspace for scheduled Foundry trace evaluations. Defaults to false.'
                            }
                        }
                    }
                    grantProjectProtectedTraceContentReader         = @{
                        kind  = 'added'
                        after = @{
                            type         = 'bool'
                            defaultValue = $false
                            metadata     = @{
                                description = 'Strictly opt-in: grant the AI Foundry project managed identity Privileged Monitoring Data Reader with an ABAC v2.0 condition restricted to the Protected AppGenAIContent table on the effective Application Insights and Log Analytics resources. Requires grantProjectTraceEvaluationReader=true. Defaults to false.'
                            }
                        }
                    }
                }
            }
            variables  = @{
                kind    = 'object'
                changes = @{
                    _logAnalyticsDataReaderRoleId         = @{
                        kind  = 'added'
                        after = '3b03c2da-16b3-4a49-8834-0f8130efdd3b'
                    }
                    _privilegedMonitoringDataReaderRoleId = @{
                        kind  = 'added'
                        after = 'dbc9c667-e97f-4491-aee6-90b9cf960190'
                    }
                    _dnsZonesList                         = @{
                        kind   = 'changed'
                        after  = $dnsZonesListAfter
                        before = $dnsZonesListBefore
                    }
                    _dnsZoneAzureAutomationId             = @{
                        kind   = 'changed'
                        after  = $dnsZoneAzureAutomationIdAfter
                        before = $dnsZoneAzureAutomationIdBefore
                    }
                }
            }
            resources  = @{
                kind    = 'object'
                changes = @{
                    traceEvaluationValidation           = @{
                        kind  = 'added'
                        after = $traceValidationResource
                    }
                    assignProjectTraceEvaluationRoles   = @{
                        kind  = 'added'
                        after = $traceRolesResource
                    }
                }
            }
        }
    }
}

function ConvertTo-PrePrivateMonitoringTraceRbacGraph {
    param([Parameter(Mandatory)] $Template)
    $copy = ConvertTo-Json -InputObject $Template -Depth 100 -Compress |
        ConvertFrom-Json -AsHashtable -Depth 100
    return Invoke-ScopedProjection $copy (Get-PrivateMonitoringTraceRbacProjection)
}

function ConvertTo-PrivateMonitoringTraceRbacPrePostgreSqlGraph {
    param([Parameter(Mandatory)] $PrePostgreSqlTemplate)
    $copy = ConvertTo-Json -InputObject $PrePostgreSqlTemplate -Depth 100 -Compress |
        ConvertFrom-Json -AsHashtable -Depth 100
    $rule = Get-PrivateMonitoringTraceRbacProjection
    $paramChanges = $rule.changes.parameters.changes
    $varChanges = $rule.changes.variables.changes
    $resChanges = $rule.changes.resources.changes

    $copy.parameters.existingPrivateDnsZoneAzureAutomationResourceId.metadata.description = $paramChanges.existingPrivateDnsZoneAzureAutomationResourceId.changes.metadata.changes.description.after
    $copy.parameters.grantProjectTraceEvaluationReader = $paramChanges.grantProjectTraceEvaluationReader.after
    $copy.parameters.grantProjectProtectedTraceContentReader = $paramChanges.grantProjectProtectedTraceContentReader.after

    $copy.variables._logAnalyticsDataReaderRoleId = $varChanges._logAnalyticsDataReaderRoleId.after
    $copy.variables._privilegedMonitoringDataReaderRoleId = $varChanges._privilegedMonitoringDataReaderRoleId.after
    if ([regex]::Matches([string]$copy.variables._dnsZonesList, [regex]::Escape('privatelink.agentsvc.azure.automation.net')).Count -ne 1) {
        throw 'SCOPED: expected single pre-PostgreSQL AzureAutomation DNS zone entry.'
    }
    $copy.variables._dnsZonesList = ([string]$copy.variables._dnsZonesList).Replace('privatelink.agentsvc.azure.automation.net', 'privatelink.agentsvc.azure-automation.net')
    $copy.variables._dnsZoneAzureAutomationId = $varChanges._dnsZoneAzureAutomationId.after

    $copy.resources.traceEvaluationValidation = $resChanges.traceEvaluationValidation.after
    $copy.resources.assignProjectTraceEvaluationRoles = $resChanges.assignProjectTraceEvaluationRoles.after
    return $copy
}
