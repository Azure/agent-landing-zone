<# Read-only mocked operator authorization with no implicit role grants. #>
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\..\..\scripts\infra\ModelQuota.ps1')
$source = Get-Content (Join-Path $PSScriptRoot '../../../scripts/infra/Invoke-PreflightChecks.ps1') -Raw
$ast = [System.Management.Automation.Language.Parser]::ParseInput($source, [ref]$null, [ref]$null)
foreach ($function in $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    Invoke-Expression $function.Extent.Text
}
$script:SkipAzureLookups = $false
$script:RoleCalls = 0
function Get-AzdEnvValues {
    return @{
        AZURE_SUBSCRIPTION_ID = 'sub-test'
        AZURE_RESOURCE_GROUP = 'rg-test'
        AZURE_FOUNDRY_RESOURCE_GROUP = $script:FoundryGroup
        AZURE_AI_PROJECT_RESOURCE_ID = $script:ProjectId
    }
}
function Invoke-AzCli {
    param([string[]]$Arguments)
    $script:RoleCalls++
    if ($Arguments[0] -ne 'role' -or $Arguments[2] -ne 'list') { throw 'Only read-only role inventory is allowed.' }
    if ($Arguments[1] -eq 'assignment') { return $script:Assignments }
    if ($Arguments[4] -ne '00000000-0000-0000-0000-000000000001') { throw 'Role definitions must be requested by UUID, not full ARM ID.' }
    return @(@{ permissions = $script:Permissions })
}
function Assert-Finding([string]$Code) {
    if (-not @($script:Findings | Where-Object Code -eq $Code).Count) {
        throw "Expected actionable finding $Code"
    }
}
$operator = 'operator-test'
$script:ProjectId = '/subscriptions/sub-test/resourceGroups/rg-test/providers/Microsoft.CognitiveServices/accounts/account/projects/project'
$script:FoundryGroup = ''
$parameters = @{
    prepareHostedAgent = $true; deployHostedAgent = $false
    grantHostedAgentProjectManager = $false; deployAiFoundry = $true
    deployContainerRegistry = $true; networkIsolation = $false
    principalId = $operator
}
foreach ($case in 'existing', 'missing', 'management-only', 'excluded', 'conditional', 'wrong-principal', 'wrong-scope') {
    $script:Findings = [System.Collections.Generic.List[pscustomobject]]::new()
    $script:Assignments = @(@{ principalId = $operator; roleDefinitionId = '/subscriptions/sub-test/providers/Microsoft.Authorization/roleDefinitions/00000000-0000-0000-0000-000000000001'; condition = $null })
    $script:Permissions = @(@{ actions = @('*'); notActions = @(); dataActions = @('Microsoft.CognitiveServices/*'); notDataActions = @() })
    $inputParameters = $parameters.Clone()
    switch ($case) {
        'missing' { $script:Assignments = @() }
        'management-only' { $script:Permissions[0].dataActions = @() }
        'excluded' { $script:Permissions[0].notDataActions = @('Microsoft.CognitiveServices/accounts/AIServices/agents/write') }
        'conditional' { $script:Assignments[0].condition = 'not independently verified' }
        'wrong-principal' { $script:Assignments[0].principalId = 'different' }
        'wrong-scope' { $inputParameters.principalId = '' }
    }
    Test-HostedAgentConfiguration -P $inputParameters
    $expected = if ($case -eq 'existing') { 'HOSTED_OPERATOR_ACCESS_VERIFIED' } elseif ($case -eq 'wrong-scope') { 'HOSTED_OPERATOR_SCOPE_REQUIRED' } else { 'HOSTED_OPERATOR_ACCESS_REQUIRED' }
    Assert-Finding $expected
    Write-Host "PASS existing operator authorization: $case"
}
$script:RoleCalls = 0
$parameters.grantHostedAgentProjectManager = $true
$script:Findings = [System.Collections.Generic.List[pscustomobject]]::new()
Test-HostedAgentConfiguration -P $parameters
if ($script:RoleCalls) { throw 'Legacy/default callers must not gain new read-only preflight dependencies.' }
Write-Host 'PASS compatible default skips existing-authorization gate.'
$script:ProjectId = ''
$parameters.grantHostedAgentProjectManager = $false
$script:Assignments = @(@{ principalId = $operator; roleDefinitionId = '/subscriptions/sub-test/providers/Microsoft.Authorization/roleDefinitions/00000000-0000-0000-0000-000000000001'; condition = $null })
$script:Permissions = @(@{ actions = @('*'); notActions = @(); dataActions = @(); notDataActions = @() })
$script:Findings = [System.Collections.Generic.List[pscustomobject]]::new()
Test-HostedAgentConfiguration -P $parameters
Assert-Finding 'HOSTED_OPERATOR_ACCESS_VERIFIED'
Write-Host 'PASS first foundation preserves declared account executor data access without Project Manager.'
$script:Permissions[0].actions = @()
$script:Findings = [System.Collections.Generic.List[pscustomobject]]::new()
Test-HostedAgentConfiguration -P $parameters
Assert-Finding 'HOSTED_OPERATOR_ACCESS_REQUIRED'
Write-Host 'PASS new foundation without existing management authorization fails explicitly.'

$script:Permissions = @(@{ actions = @('*'); notActions = @(); dataActions = @('Microsoft.CognitiveServices/*'); notDataActions = @() })
$oldAmbientFoundry = $env:AZURE_FOUNDRY_RESOURCE_GROUP
try {
    $env:AZURE_FOUNDRY_RESOURCE_GROUP = 'stale-ambient-group'
    foreach ($case in @(
        @{ Name = 'split Foundry'; Group = 'rg-foundry'; ProjectGroup = 'rg-foundry'; Expected = 'HOSTED_OPERATOR_ACCESS_VERIFIED' },
        @{ Name = 'wrong application group'; Group = 'rg-foundry'; ProjectGroup = 'rg-test'; Expected = 'HOSTED_OPERATOR_SCOPE_REQUIRED' },
        @{ Name = 'whitespace fallback'; Group = '  '; ProjectGroup = 'rg-test'; Expected = 'HOSTED_OPERATOR_ACCESS_VERIFIED' }
    )) {
        $script:FoundryGroup = $case.Group
        $script:ProjectId = "/subscriptions/sub-test/resourceGroups/$($case.ProjectGroup)/providers/Microsoft.CognitiveServices/accounts/account/projects/project"
        $script:Findings = [System.Collections.Generic.List[pscustomobject]]::new()
        $script:RoleCalls = 0
        Test-HostedAgentConfiguration -P $parameters
        Assert-Finding $case.Expected
        if ($case.Expected -eq 'HOSTED_OPERATOR_SCOPE_REQUIRED' -and $script:RoleCalls) {
            throw 'Wrong-group project must fail before Azure role inventory.'
        }
        Write-Host "PASS selected-environment operator scope: $($case.Name)"
    }
}
finally { $env:AZURE_FOUNDRY_RESOURCE_GROUP = $oldAmbientFoundry }
