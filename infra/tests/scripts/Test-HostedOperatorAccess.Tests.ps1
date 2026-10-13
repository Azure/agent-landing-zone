<# Read-only mocked operator authorization with no implicit role grants. #>
$ErrorActionPreference = 'Stop'
$source = Get-Content (Join-Path $PSScriptRoot '../../scripts/Invoke-PreflightChecks.ps1') -Raw
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
        AZURE_AI_PROJECT_RESOURCE_ID = $script:ProjectId
    }
}
function Invoke-AzCli {
    param([string[]]$Arguments)
    $script:RoleCalls++
    if ($Arguments[0] -ne 'role' -or $Arguments[2] -ne 'list') { throw 'Only read-only role inventory is allowed.' }
    if ($Arguments[1] -eq 'assignment') { return $script:Assignments }
    return @(@{ permissions = $script:Permissions })
}
function Assert-Finding([string]$Code) {
    if (-not @($script:Findings | Where-Object Code -eq $Code).Count) {
        throw "Expected actionable finding $Code"
    }
}
$operator = 'operator-test'
$script:ProjectId = '/subscriptions/sub-test/resourceGroups/rg-test/providers/Microsoft.CognitiveServices/accounts/account/projects/project'
$parameters = @{
    prepareHostedAgent = $true; deployHostedAgent = $false
    grantHostedAgentProjectManager = $false; deployAiFoundry = $true
    deployContainerRegistry = $true; networkIsolation = $false
    principalId = $operator
}
foreach ($case in 'existing', 'missing', 'management-only', 'excluded', 'conditional', 'wrong-principal', 'wrong-scope') {
    $script:Findings = [System.Collections.Generic.List[pscustomobject]]::new()
    $script:Assignments = @(@{ principalId = $operator; roleDefinitionId = 'role-test'; condition = $null })
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
$script:Assignments = @(@{ principalId = $operator; roleDefinitionId = 'owner-test'; condition = $null })
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
