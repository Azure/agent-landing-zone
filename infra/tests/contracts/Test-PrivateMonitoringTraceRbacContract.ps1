<#
.SYNOPSIS
    Offline compiled contract for #882 Task 5 private monitoring DNS and opt-in trace-evaluation RBAC.
.DESCRIPTION
    Verifies AMPLS privateDnsZoneGroup zone membership (including hyphenated
    privatelink.agentsvc.azure-automation.net and intentional omission of
    privatelink.applicationinsights.io from the AMPLS private endpoint zone
    group), default-off trace-evaluation flags, prerequisite validation guards,
    exact role GUIDs, cross-subscription BYO observability scopes, ServicePrincipal
    project identity binding, and exact AppGenAIContent + Protected ABAC v2.0
    condition. Never deploys live Azure resources.
#>
[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'bicep/main.bicep')
)

$ErrorActionPreference = 'Stop'
$MainFile = (Resolve-Path -LiteralPath $MainFile).Path
. (Join-Path $PSScriptRoot 'ScopedResourceGroupNormalization.ps1')
$compiledFile = Join-Path ([IO.Path]::GetTempPath()) "private-monitoring-trace-rbac-$([guid]::NewGuid().ToString('N')).json"
$script:checks = 0

function Assert-Equal($Name, $Actual, $Expected) {
    $a = ConvertTo-Json -InputObject $Actual -Compress -Depth 100
    $e = ConvertTo-Json -InputObject $Expected -Compress -Depth 100
    if ($a -cne $e) { throw "$Name -- expected $e; got $a" }
    $script:checks++
}

function Assert-True($Name, [bool]$Condition) {
    Assert-Equal $Name $Condition $true
}

function Assert-Rejected($Name, [scriptblock]$Action) {
    $rejected = $false
    try { $null = & $Action }
    catch {
        if (-not $_.Exception.Message.StartsWith('SCOPED:')) { throw }
        $rejected = $true
    }
    Assert-Equal $Name $rejected $true
}

function Resolve-TraceEvaluationContract {
    param(
        [bool]$GrantTraceEval = $false,
        [bool]$GrantProtectedTrace = $false,
        [bool]$DeployAiFoundry = $true,
        [bool]$DeployAfProject = $true,
        [bool]$DeployLogAnalytics = $true,
        [bool]$DeployAppInsights = $true,
        [string]$ExistingLawId = '',
        [string]$ExistingAppInsightsId = '',
        [string]$WorkloadSubscriptionId = '00000000-0000-0000-0000-000000000001',
        [string]$ApplicationResourceGroup = 'rg-app',
        [string]$ManagedLawName = 'log-agentlz',
        [string]$ManagedAppInsightsName = 'appi-agentlz',
        [string]$ProjectPrincipalId = '00000000-0000-0000-0000-000000000055'
    )

    $hasExistingLaw = -not [string]::IsNullOrEmpty($ExistingLawId.Trim())
    $hasExistingAi = -not [string]::IsNullOrEmpty($ExistingAppInsightsId.Trim())
    $createLaw = $DeployLogAnalytics -and (-not $hasExistingLaw)
    $createAi = $DeployAppInsights -and (-not $hasExistingAi) -and ($createLaw -or $hasExistingLaw)
    $hasEffectiveLaw = $hasExistingLaw -or $createLaw
    $hasEffectiveAi = $hasExistingAi -or $createAi

    $validationActive = $GrantTraceEval -or $GrantProtectedTrace
    if ($validationActive) {
        if ($GrantProtectedTrace -and (-not $GrantTraceEval)) {
            return @{ Valid = $false; Error = 'grantProjectProtectedTraceContentReader requires grantProjectTraceEvaluationReader=true.'; Grants = @() }
        }
        if (-not ($DeployAiFoundry -and $DeployAfProject)) {
            return @{ Valid = $false; Error = 'Scheduled Foundry trace evaluation permissions require deployAiFoundry=true and deployAfProject=true.'; Grants = @() }
        }
        if (-not ($hasEffectiveAi -and $hasEffectiveLaw)) {
            return @{ Valid = $false; Error = 'Scheduled Foundry trace evaluation permissions require effective Application Insights and Log Analytics resources.'; Grants = @() }
        }
        if ($hasExistingAi -and $ExistingAppInsightsId.Trim() -notmatch '^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.Insights/components/[^/]+$') {
            return @{ Valid = $false; Error = 'Existing Application Insights and Log Analytics resource IDs must be full ARM resource IDs.'; Grants = @() }
        }
        if ($hasExistingLaw -and $ExistingLawId.Trim() -notmatch '^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.OperationalInsights/workspaces/[^/]+$') {
            return @{ Valid = $false; Error = 'Existing Application Insights and Log Analytics resource IDs must be full ARM resource IDs.'; Grants = @() }
        }
    }

    $grantsActive = $GrantTraceEval -and $DeployAiFoundry -and $DeployAfProject -and $hasEffectiveAi -and $hasEffectiveLaw
    if (-not $grantsActive) {
        return @{ Valid = $true; Error = ''; Grants = @() }
    }

    $effectiveAiId = if ($hasExistingAi) { $ExistingAppInsightsId } else { "/subscriptions/$WorkloadSubscriptionId/resourceGroups/$ApplicationResourceGroup/providers/Microsoft.Insights/components/$ManagedAppInsightsName" }
    $effectiveLawId = if ($hasExistingLaw) { $ExistingLawId } else { "/subscriptions/$WorkloadSubscriptionId/resourceGroups/$ApplicationResourceGroup/providers/Microsoft.OperationalInsights/workspaces/$ManagedLawName" }

    $aiSub = $effectiveAiId.Split('/')[2]
    $lawSub = $effectiveLawId.Split('/')[2]
    $abac = "(`n  (`n    !(ActionMatches{'Microsoft.OperationalInsights/workspaces/tables/data/read'})`n  )`n  OR`n  (`n    @Resource[Microsoft.OperationalInsights/workspaces/tables:name] StringEquals 'AppGenAIContent'`n    AND`n    @Resource[Microsoft.OperationalInsights/workspaces/tables:protectionLevel] StringEquals 'Protected'`n  )`n)"

    $grants = [System.Collections.Generic.List[hashtable]]::new()
    $grants.Add(@{
            Scope            = $effectiveAiId
            PrincipalId      = $ProjectPrincipalId
            PrincipalType    = 'ServicePrincipal'
            RoleDefinitionId = "/subscriptions/$aiSub/providers/Microsoft.Authorization/roleDefinitions/acdd72a7-3385-48ef-bd42-f606fba81ae7"
            ConditionVersion = $null
            Condition        = $null
        })
    $grants.Add(@{
            Scope            = $effectiveLawId
            PrincipalId      = $ProjectPrincipalId
            PrincipalType    = 'ServicePrincipal'
            RoleDefinitionId = "/subscriptions/$lawSub/providers/Microsoft.Authorization/roleDefinitions/3b03c2da-16b3-4a49-8834-0f8130efdd3b"
            ConditionVersion = $null
            Condition        = $null
        })
    if ($GrantProtectedTrace) {
        $grants.Add(@{
                Scope            = $effectiveAiId
                PrincipalId      = $ProjectPrincipalId
                PrincipalType    = 'ServicePrincipal'
                RoleDefinitionId = "/subscriptions/$aiSub/providers/Microsoft.Authorization/roleDefinitions/dbc9c667-e97f-4491-aee6-90b9cf960190"
                ConditionVersion = '2.0'
                Condition        = $abac
            })
        $grants.Add(@{
                Scope            = $effectiveLawId
                PrincipalId      = $ProjectPrincipalId
                PrincipalType    = 'ServicePrincipal'
                RoleDefinitionId = "/subscriptions/$lawSub/providers/Microsoft.Authorization/roleDefinitions/dbc9c667-e97f-4491-aee6-90b9cf960190"
                ConditionVersion = '2.0'
                Condition        = $abac
            })
    }
    return @{ Valid = $true; Error = ''; Grants = $grants.ToArray() }
}

try {
    & az bicep build --file $MainFile --outfile $compiledFile --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "Bicep compilation failed: $LASTEXITCODE" }

    $rawJson = Get-Content -LiteralPath $compiledFile -Raw
    $t = $rawJson | ConvertFrom-Json -AsHashtable -Depth 100

    # 1. Output budget and shared roles.json preservation.
    Assert-Equal 'Native Bicep output budget remains 64' $t.outputs.Count 64
    Assert-Equal 'Shared roles.json excludes LogAnalyticsDataReader to preserve _1._3' $t.variables['_1._3'].ContainsKey('LogAnalyticsDataReader') $false
    Assert-Equal 'Shared roles.json excludes PrivilegedMonitoringDataReader to preserve _1._3' $t.variables['_1._3'].ContainsKey('PrivilegedMonitoringDataReader') $false

    # 2. AMPLS Private DNS zone hyphenation & privateDnsZoneGroup contract.
    Assert-Equal 'Compiled template contains zero legacy dot-typo privatelink.agentsvc.azure.automation.net' $rawJson.Contains('privatelink.agentsvc.azure.automation.net') $false
    Assert-True 'Compiled _dnsZonesList provisions hyphenated privatelink.agentsvc.azure-automation.net' $t.variables._dnsZonesList.Contains('privatelink.agentsvc.azure-automation.net')
    Assert-True 'Compiled _dnsZonesList provisions privatelink.applicationinsights.io when _deployAmpls is true' $t.variables._dnsZonesList.Contains('privatelink.applicationinsights.io')
    Assert-True 'Compiled _dnsZoneAzureAutomationId uses hyphenated privatelink.agentsvc.azure-automation.net' $t.variables._dnsZoneAzureAutomationId.Contains('privatelink.agentsvc.azure-automation.net')

    $amplsPe = $t.resources.privateEndpointPrivateLinkScope
    Assert-Equal 'AMPLS private endpoint gated on _deployAmpls' $amplsPe.condition "[variables('_deployAmpls')]"
    $amplsZoneGroupExpr = [string]$amplsPe.properties.parameters.privateDnsZoneGroup
    foreach ($expectedZoneVar in @('_dnsZoneAzureMonitorId', '_dnsZoneOmsOpsInsightsId', '_dnsZoneOdsOpsInsightsId', '_dnsZoneAzureAutomationId')) {
        Assert-True "AMPLS privateDnsZoneGroup attaches $expectedZoneVar" $amplsZoneGroupExpr.Contains("variables('$expectedZoneVar')")
    }
    Assert-Equal 'AMPLS privateDnsZoneGroup intentionally omits privatelink.applicationinsights.io' $amplsZoneGroupExpr.Contains('applicationinsights') $false
    Assert-Equal 'AMPLS privateDnsZoneGroup intentionally omits existingPrivateDnsZoneAppInsightsResourceId' $amplsZoneGroupExpr.Contains('AppInsights') $false
    Assert-True 'AMPLS privateDnsZoneGroup honors policyManagedPrivateDns' $amplsZoneGroupExpr.Contains("parameters('policyManagedPrivateDns')")

    # 3. Parameter declarations, defaults, and parameter seeds.
    Assert-Equal 'grantProjectTraceEvaluationReader defaults to false' $t.parameters.grantProjectTraceEvaluationReader.defaultValue $false
    Assert-Equal 'grantProjectProtectedTraceContentReader defaults to false' $t.parameters.grantProjectProtectedTraceContentReader.defaultValue $false

    $repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MainFile))
    foreach ($seedPath in @((Join-Path $repoRoot 'main.parameters.json'), (Join-Path (Split-Path -Parent $MainFile) 'main.parameters.json'))) {
        $seedParams = (Get-Content -LiteralPath $seedPath -Raw | ConvertFrom-Json -AsHashtable).parameters
        Assert-Equal "Seed $seedPath maps grantProjectTraceEvaluationReader" $seedParams.grantProjectTraceEvaluationReader.value '${GRANT_PROJECT_TRACE_EVALUATION_READER=false}'
        Assert-Equal "Seed $seedPath maps grantProjectProtectedTraceContentReader" $seedParams.grantProjectProtectedTraceContentReader.value '${GRANT_PROJECT_PROTECTED_TRACE_CONTENT_READER=false}'
    }

    # 4. Exact role GUIDs, validation guards, cross-subscription BYO scopes, and ABAC v2.0 predicate.
    Assert-Equal 'LogAnalyticsDataReader GUID' $t.variables._logAnalyticsDataReaderRoleId '3b03c2da-16b3-4a49-8834-0f8130efdd3b'
    Assert-Equal 'PrivilegedMonitoringDataReader GUID' $t.variables._privilegedMonitoringDataReaderRoleId 'dbc9c667-e97f-4491-aee6-90b9cf960190'
    Assert-Equal 'Reader GUID in shared catalog' $t.variables['_1._3'].Reader.guid 'acdd72a7-3385-48ef-bd42-f606fba81ae7'

    $valMod = $t.resources.traceEvaluationValidation
    Assert-Equal 'traceEvaluationValidation gate' $valMod.condition "[or(parameters('grantProjectTraceEvaluationReader'), parameters('grantProjectProtectedTraceContentReader'))]"
    Assert-Equal 'traceEvaluationValidation has zero resource dependsOn so invalid inputs fail fast' $valMod.ContainsKey('dependsOn') $false

    $rolesMod = $t.resources.assignProjectTraceEvaluationRoles
    Assert-Equal 'assignProjectTraceEvaluationRoles gate' $rolesMod.condition "[and(and(and(and(parameters('grantProjectTraceEvaluationReader'), parameters('deployAiFoundry')), parameters('deployAfProject')), variables('_hasEffectiveAI')), variables('_hasEffectiveLaw'))]"
    Assert-Equal 'assignProjectTraceEvaluationRoles binds Foundry project managed identity' $rolesMod.properties.parameters.principalId.value "[reference('aiFoundry').outputs.aiProjectPrincipalId.value]"
    Assert-True 'assignProjectTraceEvaluationRoles waits on traceEvaluationValidation' ($rolesMod.dependsOn -contains 'traceEvaluationValidation')

    $expectedAbac = "(`n  (`n    !(ActionMatches{'Microsoft.OperationalInsights/workspaces/tables/data/read'})`n  )`n  OR`n  (`n    @Resource[Microsoft.OperationalInsights/workspaces/tables:name] StringEquals 'AppGenAIContent'`n    AND`n    @Resource[Microsoft.OperationalInsights/workspaces/tables:protectionLevel] StringEquals 'Protected'`n  )`n)"
    $normalizedCompiledAbac = ([string]$rolesMod.properties.template.variables.protectedTraceCondition).Replace("`r`n", "`n")
    Assert-Equal 'Exact Protected AppGenAIContent ABAC v2.0 condition' $normalizedCompiledAbac $expectedAbac

    $appiChild = $rolesMod.properties.template.resources[0]
    $lawChild = $rolesMod.properties.template.resources[1]
    Assert-Equal 'App Insights child deployment targets parsed BYO/managed subscriptionId' $appiChild.subscriptionId "[variables('appInsightsSubscriptionId')]"
    Assert-Equal 'App Insights child deployment targets parsed BYO/managed resourceGroup' $appiChild.resourceGroup "[variables('appInsightsResourceGroupName')]"
    Assert-Equal 'Log Analytics child deployment targets parsed BYO/managed subscriptionId' $lawChild.subscriptionId "[variables('workspaceSubscriptionId')]"
    Assert-Equal 'Log Analytics child deployment targets parsed BYO/managed resourceGroup' $lawChild.resourceGroup "[variables('workspaceResourceGroupName')]"
    Assert-Equal 'App Insights Privileged assignment uses conditionVersion 2.0' $appiChild.properties.template.resources[1].properties.conditionVersion '2.0'
    Assert-Equal 'Log Analytics Privileged assignment uses conditionVersion 2.0' $lawChild.properties.template.resources[1].properties.conditionVersion '2.0'

    # 5. Bounded scenario verification across default, standard, protected, cross-sub BYO, and invalid combinations.
    $defaultOff = Resolve-TraceEvaluationContract
    Assert-Equal 'Default flags produce zero extra role assignments' @($defaultOff.Valid, $defaultOff.Grants.Count) @($true, 0)

    $standardTrace = Resolve-TraceEvaluationContract -GrantTraceEval $true
    Assert-Equal 'Standard trace evaluation creates exactly 2 role assignments' @($standardTrace.Valid, $standardTrace.Grants.Count) @($true, 2)
    Assert-Equal 'Standard trace evaluation grants have no ABAC condition' @($standardTrace.Grants[0].Condition, $standardTrace.Grants[1].Condition) @($null, $null)

    $crossSubProtected = Resolve-TraceEvaluationContract `
        -GrantTraceEval $true `
        -GrantProtectedTrace $true `
        -ExistingAppInsightsId '/subscriptions/00000000-0000-0000-0000-000000000099/resourceGroups/rg-central-obs/providers/Microsoft.Insights/components/appi-central' `
        -ExistingLawId '/subscriptions/00000000-0000-0000-0000-000000000098/resourceGroups/rg-central-law/providers/Microsoft.OperationalInsights/workspaces/law-central'
    Assert-Equal 'Protected trace evaluation creates 4 role assignments across cross-subscription BYO targets' @($crossSubProtected.Valid, $crossSubProtected.Grants.Count) @($true, 4)
    Assert-Equal 'Cross-sub App Insights Reader roleDefinitionId uses foreign subscription' $crossSubProtected.Grants[0].RoleDefinitionId '/subscriptions/00000000-0000-0000-0000-000000000099/providers/Microsoft.Authorization/roleDefinitions/acdd72a7-3385-48ef-bd42-f606fba81ae7'
    Assert-Equal 'Cross-sub Log Analytics Data Reader roleDefinitionId uses foreign subscription' $crossSubProtected.Grants[1].RoleDefinitionId '/subscriptions/00000000-0000-0000-0000-000000000098/providers/Microsoft.Authorization/roleDefinitions/3b03c2da-16b3-4a49-8834-0f8130efdd3b'
    Assert-Equal 'Cross-sub App Insights Privileged roleDefinitionId and ABAC' @($crossSubProtected.Grants[2].RoleDefinitionId, $crossSubProtected.Grants[2].ConditionVersion, $crossSubProtected.Grants[2].Condition) @('/subscriptions/00000000-0000-0000-0000-000000000099/providers/Microsoft.Authorization/roleDefinitions/dbc9c667-e97f-4491-aee6-90b9cf960190', '2.0', $expectedAbac)
    Assert-Equal 'Cross-sub Log Analytics Privileged roleDefinitionId and ABAC' @($crossSubProtected.Grants[3].RoleDefinitionId, $crossSubProtected.Grants[3].ConditionVersion, $crossSubProtected.Grants[3].Condition) @('/subscriptions/00000000-0000-0000-0000-000000000098/providers/Microsoft.Authorization/roleDefinitions/dbc9c667-e97f-4491-aee6-90b9cf960190', '2.0', $expectedAbac)

    Assert-Equal 'Reject protected flag without base trace reader' (Resolve-TraceEvaluationContract -GrantProtectedTrace $true).Valid $false
    Assert-Equal 'Reject trace reader without Foundry account' (Resolve-TraceEvaluationContract -GrantTraceEval $true -DeployAiFoundry $false).Valid $false
    Assert-Equal 'Reject trace reader without Foundry project' (Resolve-TraceEvaluationContract -GrantTraceEval $true -DeployAfProject $false).Valid $false
    Assert-Equal 'Reject trace reader without App Insights' (Resolve-TraceEvaluationContract -GrantTraceEval $true -DeployAppInsights $false).Valid $false
    Assert-Equal 'Reject trace reader without Log Analytics' (Resolve-TraceEvaluationContract -GrantTraceEval $true -DeployLogAnalytics $false).Valid $false
    Assert-Equal 'Reject malformed BYO observability ID' (Resolve-TraceEvaluationContract -GrantTraceEval $true -ExistingLawId 'not-an-arm-id').Valid $false

    # 6. Verify inverse normalization and negative mutations.
    $restored = ConvertTo-PrePrivateMonitoringTraceRbacGraph $t
    Assert-Equal 'Inverse removes grantProjectTraceEvaluationReader' $restored.parameters.ContainsKey('grantProjectTraceEvaluationReader') $false
    Assert-Equal 'Inverse removes grantProjectProtectedTraceContentReader' $restored.parameters.ContainsKey('grantProjectProtectedTraceContentReader') $false
    Assert-Equal 'Inverse removes traceEvaluationValidation' $restored.resources.ContainsKey('traceEvaluationValidation') $false
    Assert-Equal 'Inverse removes assignProjectTraceEvaluationRoles' $restored.resources.ContainsKey('assignProjectTraceEvaluationRoles') $false
    Assert-True 'Inverse restores legacy dot-spelled DNS zone only for historical fixture comparison' ([string]$restored.variables._dnsZoneAzureAutomationId).Contains('privatelink.agentsvc.azure.automation.net')

    $negativeCases = @(
        @{ Name = 'grantProjectTraceEvaluationReader default flipped'; Mutate = { param($m) $m.parameters.grantProjectTraceEvaluationReader.defaultValue = $true } },
        @{ Name = 'grantProjectProtectedTraceContentReader default flipped'; Mutate = { param($m) $m.parameters.grantProjectProtectedTraceContentReader.defaultValue = $true } },
        @{ Name = '_dnsZonesList reverted to dot spelling'; Mutate = { param($m) $m.variables._dnsZonesList = ([string]$m.variables._dnsZonesList).Replace('privatelink.agentsvc.azure-automation.net', 'privatelink.agentsvc.azure.automation.net') } },
        @{ Name = 'assignProjectTraceEvaluationRoles principal changed'; Mutate = { param($m) $m.resources.assignProjectTraceEvaluationRoles.properties.parameters.principalId.value = "[parameters('principalId')]" } },
        @{ Name = 'ABAC condition weakened'; Mutate = { param($m) $m.resources.assignProjectTraceEvaluationRoles.properties.template.variables.protectedTraceCondition = 'true' } }
    )
    foreach ($case in $negativeCases) {
        $mutated = $rawJson | ConvertFrom-Json -AsHashtable -Depth 100
        & $case.Mutate $mutated
        Assert-Rejected "Reject $($case.Name)" { ConvertTo-PrePrivateMonitoringTraceRbacGraph $mutated }
    }

    Write-Host "Private monitoring DNS and trace-evaluation RBAC contract passed: $script:checks assertions." -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $compiledFile -Force -ErrorAction SilentlyContinue
}
