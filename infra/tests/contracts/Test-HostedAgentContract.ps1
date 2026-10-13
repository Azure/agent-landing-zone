<#
.SYNOPSIS
    Validates the accelerator-neutral hosted-agent infrastructure contract.

.DESCRIPTION
    Compiles main.bicep and compares its symbolic ARM resource graph with the
    merge-base fixture. Pre-existing deployment semantics remain stable except
    for named post-baseline mutations covered by their own focused contracts.
    The two hosted-agent RBAC payloads must be gated by prepareHostedAgent or
    deployHostedAgent.
#>

[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'main.bicep'),
    [string]$FixtureFile = (Join-Path $PSScriptRoot 'fixtures\hosted-agent-resource-graph.json')
)

$ErrorActionPreference = 'Stop'
$failures = [System.Collections.Generic.List[string]]::new()
$compiledFile = Join-Path ([System.IO.Path]::GetTempPath()) "hosted-agent-contract-$([guid]::NewGuid()).json"

function Add-Failure {
    param([Parameter(Mandatory)] [string]$Message)
    $failures.Add($Message) | Out-Null
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Add-Pass {
    param([Parameter(Mandatory)] [string]$Message)
    Write-Host "  [PASS] $Message" -ForegroundColor Green
}

function ConvertTo-ContractCanonicalValue {
    param(
        [AllowNull()] $Value,
        [switch]$IgnoreGeneratedMetadata
    )

    if ($null -eq $Value) { return $null }
    if ($Value -is [string]) {
        return $Value.Replace("`r`n", "`n").Replace("`r", "`n")
    }
    if ($Value -is [System.Collections.IDictionary]) {
        $result = [ordered]@{}
        foreach ($key in $Value.Keys) {
            if ($IgnoreGeneratedMetadata -and $key -eq '_generator') { continue }
            $result[$key] = ConvertTo-ContractCanonicalValue -Value $Value[$key] -IgnoreGeneratedMetadata:$IgnoreGeneratedMetadata
        }
        return $result
    }
    if ($Value -is [pscustomobject]) {
        $result = [ordered]@{}
        foreach ($property in $Value.PSObject.Properties) {
            if ($IgnoreGeneratedMetadata -and $property.Name -eq '_generator') { continue }
            $result[$property.Name] = ConvertTo-ContractCanonicalValue -Value $property.Value -IgnoreGeneratedMetadata:$IgnoreGeneratedMetadata
        }
        return $result
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        $result = [System.Collections.Generic.List[object]]::new()
        foreach ($item in $Value) {
            $result.Add((ConvertTo-ContractCanonicalValue -Value $item -IgnoreGeneratedMetadata:$IgnoreGeneratedMetadata))
        }
        return ,$result.ToArray()
    }
    return $Value
}

function Get-ObjectHash {
    param(
        [Parameter(Mandatory)] $Value,
        [switch]$NormalizeGeneratedContent
    )

    if ($NormalizeGeneratedContent) {
        # Deeply nested AVM templates contain compiler hashes derived from source
        # line endings. Remove those non-deploying fields and normalize newlines
        # so Windows and Linux compare the same semantic resource definition.
        $Value = ConvertTo-ContractCanonicalValue -Value $Value -IgnoreGeneratedMetadata
    }
    $json = $Value | ConvertTo-Json -Depth 100 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

try {
    if (-not (Test-Path -LiteralPath $FixtureFile)) {
        throw "Fixture not found: $FixtureFile"
    }
    $fixture = Get-Content -LiteralPath $FixtureFile -Raw | ConvertFrom-Json -Depth 20

    if (Get-Command az -ErrorAction SilentlyContinue) {
        $compilerVersionOutput = (& az bicep version 2>&1) -join "`n"
        if ($compilerVersionOutput -notmatch 'Bicep CLI version (?<version>\d+\.\d+\.\d+)') {
            throw "Unable to determine the Azure CLI Bicep version from: $compilerVersionOutput"
        }
        if ($Matches.version -ne $fixture.bicepVersion) {
            throw "Fixture requires Bicep $($fixture.bicepVersion), but Azure CLI uses $($Matches.version). Run 'az bicep install --version v$($fixture.bicepVersion)'."
        }
        $env:PYTHONIOENCODING = 'utf-8'
        & az bicep build --file $MainFile --outfile $compiledFile
    }
    elseif (Get-Command bicep -ErrorAction SilentlyContinue) {
        $compilerVersionOutput = (& bicep --version 2>&1) -join "`n"
        if ($compilerVersionOutput -notmatch 'Bicep CLI version (?<version>\d+\.\d+\.\d+)') {
            throw "Unable to determine the standalone Bicep version from: $compilerVersionOutput"
        }
        if ($Matches.version -ne $fixture.bicepVersion) {
            throw "Fixture requires Bicep $($fixture.bicepVersion), but the standalone CLI uses $($Matches.version)."
        }
        & bicep build $MainFile --outfile $compiledFile
    }
    else {
        throw 'Neither bicep nor az is available on PATH.'
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Bicep compilation failed with exit code $LASTEXITCODE."
    }
    $template = Get-Content -LiteralPath $compiledFile -Raw | ConvertFrom-Json -Depth 100

    Write-Host "Hosted-agent resource contract (baseline $($fixture.mergeBase))" -ForegroundColor Cyan

    foreach ($parameterName in 'prepareHostedAgent', 'deployHostedAgent') {
        if ($template.parameters.$parameterName.defaultValue -ne $false) {
            Add-Failure "$parameterName must default to false."
        }
        else {
            Add-Pass "$parameterName defaults to false."
        }
    }
    if ($template.parameters.grantHostedAgentProjectManager.type -ne 'bool' -or
        $template.parameters.grantHostedAgentProjectManager.defaultValue -ne $true) {
        Add-Failure 'Operator Project Manager gate must be a compatible boolean defaulting to true.'
    } else {
        Add-Pass 'Operator Project Manager gate preserves legacy foundation defaults.'
    }

    $prerequisiteExpression = [string]$template.variables._hostedAgentPrerequisitesEnabled
    $missingPrerequisiteTokens = @(
        "parameters('prepareHostedAgent')",
        "parameters('deployHostedAgent')"
    ) | Where-Object { -not $prerequisiteExpression.Contains($_) }
    if ($missingPrerequisiteTokens.Count -gt 0 -or -not $prerequisiteExpression.Contains('or(')) {
        Add-Failure "Hosted-agent prerequisites must be enabled by prepareHostedAgent OR deployHostedAgent. Expression: $prerequisiteExpression"
    }
    else {
        Add-Pass 'deployHostedAgent is a superset of prepareHostedAgent prerequisites.'
    }

    $allowedPostBaselineMutations = @($fixture.allowedPostBaselineMutations)
    $expectedNames = @(
        @($fixture.resourceHashes.PSObject.Properties.Name) +
        @($fixture.allowedHostedMutations) +
        $allowedPostBaselineMutations |
            Select-Object -Unique
    )
    $actualNames = @($template.resources.PSObject.Properties.Name)
    $missingNames = @($expectedNames | Where-Object { $_ -notin $actualNames })
    $addedNames = @($actualNames | Where-Object { $_ -notin $expectedNames })
    if ($missingNames.Count -gt 0 -or $addedNames.Count -gt 0) {
        Add-Failure "Symbolic resource graph changed. Missing: [$($missingNames -join ', ')]; added: [$($addedNames -join ', ')]."
    }
    else {
        Add-Pass "Symbolic resource graph matches the $($expectedNames.Count)-resource merge-base fixture."
    }

    $normalizedResourceHashes = @{}
    if ($fixture.PSObject.Properties.Name -contains 'normalizedResourceHashes') {
        foreach ($entry in $fixture.normalizedResourceHashes.PSObject.Properties) {
            $normalizedResourceHashes[$entry.Name] = $entry.Value
        }
    }

    foreach ($entry in $fixture.resourceHashes.PSObject.Properties) {
        if ($entry.Name -notin $actualNames) { continue }
        if ($entry.Name -in $allowedPostBaselineMutations) { continue }
        $useNormalizedHash = $normalizedResourceHashes.ContainsKey($entry.Name)
        $expectedHash = $useNormalizedHash ? $normalizedResourceHashes[$entry.Name] : $entry.Value
        $actualHash = Get-ObjectHash -Value $template.resources.($entry.Name) -NormalizeGeneratedContent:$useNormalizedHash
        if ($actualHash -ne $expectedHash) {
            Add-Failure "Pre-existing resource '$($entry.Name)' changed (expected $expectedHash, got $actualHash)."
        }
    }
    if (-not ($failures | Where-Object { $_ -like "Pre-existing resource '*" })) {
        $stableResourceCount = @($fixture.resourceHashes.PSObject.Properties).Count - @(
            $fixture.resourceHashes.PSObject.Properties.Name |
                Where-Object { $_ -in $allowedPostBaselineMutations }
        ).Count
        Add-Pass "All $stableResourceCount non-hosted resource definitions match the merge-base contract."
    }

    $executorJson = $template.resources.assignExecutorRoles | ConvertTo-Json -Depth 100 -Compress
    $crossServiceJson = $template.resources.assignCrossServiceRoles | ConvertTo-Json -Depth 100 -Compress
    foreach ($check in @(
            @{
                Name = 'Executor receives Foundry Project Manager only when its independent grant gate and Hosted preparation are selected.'
                Json = $executorJson
                Required = @("variables('_hostedAgentPrerequisitesEnabled')", "parameters('grantHostedAgentProjectManager')", 'AzureAIProjectManager')
            },
            @{
                Name = 'Foundry project identity receives a registry-mode-compatible pull role when preparation or deployment is selected.'
                Json = $crossServiceJson
                Required = @("variables('_hostedAgentPrerequisitesEnabled')", "variables('_hostedAgentContainerRegistryPullRoleId')")
            }
        )) {
        $missing = @($check.Required | Where-Object { -not $check.Json.Contains($_) })
        if ($missing.Count -gt 0) {
            Add-Failure "$($check.Name) Missing compiled tokens: $($missing -join ', ')."
        }
        else {
            Add-Pass $check.Name
        }
    }
    if ($crossServiceJson.Contains("parameters('grantHostedAgentProjectManager')")) {
        Add-Failure 'Operator grant gate must never suppress project managed identity registry pull.'
    } else {
        Add-Pass 'Project managed identity registry pull is independent of operator grants.'
    }

    $source = Get-Content -LiteralPath $MainFile -Raw
    $registryRoleTokens = @(
        "hostedAgentContainerRegistryRoleAssignmentMode == 'rbac'",
        'const.roles.AcrPull.guid',
        "var _containerRegistryRepositoryReaderRoleId = 'b93aa761-3e63-49ed-ac28-beffa264f7ac'"
    )
    $missingRegistryRoleTokens = @($registryRoleTokens | Where-Object { -not $source.Contains($_) })
    if ($missingRegistryRoleTokens.Count -gt 0) {
        Add-Failure "The hosted-agent registry pull role does not select the least-privilege role for RBAC and ABAC registries. Missing: $($missingRegistryRoleTokens -join ', ')."
    }
    else {
        Add-Pass 'The hosted-agent registry pull role matches RBAC and ABAC registry modes.'
    }

    foreach ($forbidden in @('deployAdminPanel', 'adminPanelApp', '_deployClassicApps', '_deployAdminPanelApp')) {
        if ($source.Contains($forbidden)) {
            Add-Failure "Forbidden product-topology token '$forbidden' remains in main.bicep."
        }
    }
    if (-not ($failures | Where-Object { $_ -like "Forbidden product-topology token*" })) {
        Add-Pass 'No administrative-panel or workload-removal topology tokens remain.'
    }

    foreach ($outputName in @(
            'AZURE_AI_PROJECT_RESOURCE_ID',
            'AZURE_AI_PROJECT_ENDPOINT',
            'AZURE_CONTAINER_REGISTRY_RESOURCE_ID',
            'AZURE_CONTAINER_REGISTRY_ENDPOINT',
            'HOSTED_AGENT_PREPARED',
            'HOSTED_AGENT_DEPLOYMENT'
        )) {
        if ($outputName -notin $template.outputs.PSObject.Properties.Name) {
            Add-Failure "Required hosted-agent handoff output '$outputName' is missing."
        }
    }
    if (-not ($failures | Where-Object { $_ -like "Required hosted-agent handoff output*" })) {
        Add-Pass 'Stable Foundry, registry, image/runtime, network, and private-build outputs are present.'
    }

    foreach ($outputName in @(
            'AZURE_AI_PROJECT_RESOURCE_ID',
            'AZURE_AI_PROJECT_ENDPOINT',
            'AZURE_CONTAINER_REGISTRY_RESOURCE_ID',
            'AZURE_CONTAINER_REGISTRY_ENDPOINT'
        )) {
        $outputJson = $template.outputs.$outputName | ConvertTo-Json -Depth 20 -Compress
        if (-not $outputJson.Contains("variables('_hostedAgentPrerequisitesEnabled')")) {
            Add-Failure "$outputName must be available in prepare and deploy modes."
        }
    }
    if (-not ($failures | Where-Object { $_ -like '*must be available in prepare and deploy modes*' })) {
        Add-Pass 'Foundry and registry handoff outputs are available in both preparation and deployment modes.'
    }

    $preparedOutputJson = $template.outputs.HOSTED_AGENT_PREPARED | ConvertTo-Json -Depth 20 -Compress
    if (-not $preparedOutputJson.Contains("variables('_hostedAgentPrerequisitesEnabled')")) {
        Add-Failure 'HOSTED_AGENT_PREPARED must expose effective prerequisite enablement.'
    }
    else {
        Add-Pass 'HOSTED_AGENT_PREPARED distinguishes prepared infrastructure from deployment intent.'
    }

    $deploymentOutput = $template.outputs.HOSTED_AGENT_DEPLOYMENT.value
    $deploymentOnlyJson = @(
        $deploymentOutput.enabled,
        $deploymentOutput.agent
    ) | ConvertTo-Json -Depth 30 -Compress
    if (-not $deploymentOnlyJson.Contains("parameters('deployHostedAgent')") -or
        $deploymentOnlyJson.Contains("parameters('prepareHostedAgent')") -or
        $deploymentOnlyJson.Contains("variables('_hostedAgentPrerequisitesEnabled')")) {
        Add-Failure 'HOSTED_AGENT_DEPLOYMENT.enabled and agent must remain gated only by deployHostedAgent.'
    }
    else {
        Add-Pass 'Preparation does not enable or populate the hosted-agent deployment payload.'
    }

    $prerequisiteOutputJson = @(
        $deploymentOutput.foundry,
        $deploymentOutput.containerRegistry,
        $deploymentOutput.privateBuild
    ) | ConvertTo-Json -Depth 30 -Compress
    if (-not $prerequisiteOutputJson.Contains("variables('_hostedAgentPrerequisitesEnabled')")) {
        Add-Failure 'HOSTED_AGENT_DEPLOYMENT prerequisite handoff must be available in prepare and deploy modes.'
    }
    else {
        Add-Pass 'The consolidated handoff exposes Foundry, registry, and private-build prerequisites in prepare mode.'
    }

    $resourceJson = $template.resources | ConvertTo-Json -Depth 100 -Compress
    $hostedResourceTokens = @('azure.ai.agent', 'Microsoft.CognitiveServices/accounts/projects/agents')
    $unexpectedHostedResourceTokens = @($hostedResourceTokens | Where-Object { $resourceJson.Contains($_) })
    if ($unexpectedHostedResourceTokens.Count -gt 0) {
        Add-Failure "Preparation must not create a hosted-agent resource. Found: $($unexpectedHostedResourceTokens -join ', ')."
    }
    else {
        Add-Pass 'No hosted-agent resource exists in the compiled preparation template.'
    }

    $agentPoolExpression = [string]$template.variables._deployAcrTaskAgentPool
    $requiredAgentPoolTokens = @(
        "parameters('deployContainerRegistry')",
        "variables('_networkIsolation')",
        "parameters('deployAcrTaskAgentPool')"
    )
    $missingAgentPoolTokens = @($requiredAgentPoolTokens | Where-Object { -not $agentPoolExpression.Contains($_) })
    if ($missingAgentPoolTokens.Count -gt 0 -or
        $agentPoolExpression.Contains("parameters('prepareHostedAgent')") -or
        $agentPoolExpression.Contains("parameters('deployHostedAgent')")) {
        Add-Failure "Private ACR agent-pool topology changed unexpectedly. Expression: $agentPoolExpression"
    }
    else {
        Add-Pass 'Private ACR agent-pool topology remains independently gated by registry, isolation, and pool selection.'
    }

    $registryJson = $template.resources.containerRegistry | ConvertTo-Json -Depth 100 -Compress
    if (-not $registryJson.Contains("variables('_publicNetworkAccess')") -or -not $registryJson.Contains('publicNetworkAccess')) {
        Add-Failure 'Container Registry no longer preserves network-isolation-driven public access controls.'
    }
    else {
        Add-Pass 'Private-registry public access controls remain in the unchanged registry resource.'
    }
}
finally {
    Remove-Item -LiteralPath $compiledFile -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    Write-Host "`n$($failures.Count) hosted-agent contract check(s) failed." -ForegroundColor Red
    exit 1
}

Write-Host "`nHosted-agent contract checks passed." -ForegroundColor Green
exit 0
