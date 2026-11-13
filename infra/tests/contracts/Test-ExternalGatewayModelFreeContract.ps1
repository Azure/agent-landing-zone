<#
.SYNOPSIS
    Offline compiled contract for #882 Task 3 external AI Gateway model-free mode.
.DESCRIPTION
    Verifies that deployModelDeployments defaults to true (preserving 100% of
    existing modelDeploymentList and empty-array native fallback behavior) and
    that deployModelDeployments = false produces zero local AI Foundry model
    deployments, empty DEPLOYMENT_METADATA.modelDeployments, empty MODEL_DEPLOYMENTS
    JSON, and zero canonical model deployment keys in App Configuration even when
    main.parameters.json retains its default two-item modelDeploymentList.
#>
[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'bicep/main.bicep')
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ScopedResourceGroupNormalization.ps1')
$compiledFile = Join-Path ([IO.Path]::GetTempPath()) "external-gateway-model-free-$([guid]::NewGuid().ToString('N')).json"
$script:checks = 0

function Assert-Equal($Name, $Actual, $Expected) {
    $a = ConvertTo-Json -InputObject (ConvertTo-ScopedComparable $Actual) -Compress -Depth 100
    $e = ConvertTo-Json -InputObject (ConvertTo-ScopedComparable $Expected) -Compress -Depth 100
    if ($a -cne $e) { throw "$Name -- expected $e, got $a" }
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

# Bounded projection of the exact compiled model deployment expressions verified below.
function Resolve-ModelDeploymentContract {
    param(
        [bool]$DeployAiFoundry = $true,
        [bool]$DeployModelDeployments = $true,
        [array]$ModelDeploymentList = @(),
        [string]$AccountName = 'aif-contract',
        [string]$AccountResourceId = '/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-contract/providers/Microsoft.CognitiveServices/accounts/aif-contract',
        [string]$AppConfigLabel = 'agent-lz'
    )

    $nativeFallback = @(
        [ordered]@{
            model = [ordered]@{ format = 'OpenAI'; name = 'gpt-5-nano'; version = '2025-08-07' }
            name  = 'gpt-5-nano'
            sku   = [ordered]@{ name = 'GlobalStandard'; capacity = 40 }
        },
        [ordered]@{
            model = [ordered]@{ format = 'OpenAI'; name = 'text-embedding-3-large'; version = '1' }
            name  = 'text-embedding-3-large'
            sku   = [ordered]@{ name = 'GlobalStandard'; capacity = 10 }
        }
    )

    $effectiveModels = @(
        if ($DeployModelDeployments) {
            if ($ModelDeploymentList.Count -gt 0) { $ModelDeploymentList } else { $nativeFallback }
        }
    )

    $settingsSource = @(if ($DeployModelDeployments) { $ModelDeploymentList })
    $canonicalNameSettings = @(
        foreach ($m in $settingsSource) {
            [ordered]@{
                name        = $m.canonical_name
                value       = $m.name
                label       = $AppConfigLabel
                contentType = 'text/plain'
            }
        }
    )
    $modelSettings = @(
        foreach ($m in $settingsSource) {
            $apiVersion = if ($null -ne $m.apiVersion -and '' -ne $m.apiVersion) { $m.apiVersion } else { '2025-01-01-preview' }
            [ordered]@{
                canonical_name = $m.canonical_name
                capacity       = $m.sku.capacity
                model          = $m.model.name
                modelFormat    = $m.model.format
                name           = $m.name
                version        = $m.model.version
                apiVersion     = $apiVersion
                endpoint       = "https://$AccountName.openai.azure.com/"
            }
        }
    )
    $metadataBindings = @(
        $activeBindings = @(if ($DeployAiFoundry) { $effectiveModels })
        for ($idx = 0; $idx -lt $activeBindings.Count; $idx++) {
            $m = $activeBindings[$idx]
            $canonical = if ($ModelDeploymentList.Count -eq 0) {
                if ($idx -eq 0) { 'GPT_MODEL' } else { 'EMBEDDING_MODEL' }
            }
            else { $m.canonical_name }
            $apiVersion = if ($null -ne $m.apiVersion -and '' -ne $m.apiVersion) { $m.apiVersion } else { '2025-01-01-preview' }
            [ordered]@{
                canonicalName = $canonical
                resourceId    = "$AccountResourceId/deployments/$($m.name)"
                name          = $m.name
                model         = [ordered]@{
                    format  = $m.model.format
                    name    = $m.model.name
                    version = $m.model.version
                }
                apiVersion    = $apiVersion
                endpoint      = "https://$AccountName.openai.azure.com/"
            }
        }
    )

    $modelDeploymentsJson = if ($modelSettings.Count -eq 0) { '[]' } else { ConvertTo-Json -InputObject $modelSettings -AsArray -Compress -Depth 20 }

    return [ordered]@{
        aiModelDeployments           = $effectiveModels
        modelDeploymentNamesSettings = $canonicalNameSettings
        modelDeploymentsJson         = $modelDeploymentsJson
        metadataModelDeployments     = $metadataBindings
    }
}

try {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Azure CLI Bicep is required.' }
    $env:PYTHONIOENCODING = 'utf-8'

    & az bicep build --file $MainFile --outfile $compiledFile --only-show-errors
    Assert-Equal 'Foundation Bicep compiles cleanly' $LASTEXITCODE 0
    $rawJson = Get-Content -LiteralPath $compiledFile -Raw
    $t = $rawJson | ConvertFrom-Json -AsHashtable -Depth 100

    # 1. Verify exact parameter contract, output budget, and parameter seeds.
    Assert-Equal 'Native Bicep output budget preserved at 64' $t.outputs.Count 64
    Assert-Equal 'deployModelDeployments parameter shape' $t.parameters.deployModelDeployments @{
        type         = 'bool'
        defaultValue = $true
        metadata     = @{
            description = 'Deploy local AI Foundry model deployments. Set to false when all inference routes through an external AI Gateway.'
        }
    }

    $repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Resolve-Path -LiteralPath $MainFile).Path))
    $rootParams = (Get-Content -LiteralPath (Join-Path $repoRoot 'main.parameters.json') -Raw | ConvertFrom-Json -AsHashtable -Depth 100).parameters
    $bicepSeedParams = (Get-Content -LiteralPath (Join-Path (Split-Path -Parent (Resolve-Path -LiteralPath $MainFile).Path) 'main.parameters.json') -Raw | ConvertFrom-Json -AsHashtable -Depth 100).parameters
    Assert-Equal 'Root main.parameters.json exposes DEPLOY_MODEL_DEPLOYMENTS=true' $rootParams.deployModelDeployments @{ value = '${DEPLOY_MODEL_DEPLOYMENTS=true}' }
    Assert-Equal 'Bicep seed main.parameters.json matches root deployModelDeployments' $bicepSeedParams.deployModelDeployments $rootParams.deployModelDeployments

    # 2. Verify compiled ARM expressions match the exact projection rule.
    $projection = Get-ModelDeploymentsOptionalProjection
    Assert-Equal 'aiFoundry module consumes _deploymentMetadataModels' $t.resources.aiFoundry.properties.parameters.aiModelDeployments @{ value = "[variables('_deploymentMetadataModels')]" }
    Assert-Equal '_deploymentMetadataModels gated by deployModelDeployments' $t.variables._deploymentMetadataModels $projection.changes.variables.changes._deploymentMetadataModels.after
    $namesLoop = @($t.variables.copy | Where-Object { $_.name -ceq '_modelDeploymentNamesSettings' })
    $settingsLoop = @($t.variables.copy | Where-Object { $_.name -ceq '_modelDeploymentSettings' })
    Assert-Equal 'Single _modelDeploymentNamesSettings loop' $namesLoop.Count 1
    Assert-Equal 'Single _modelDeploymentSettings loop' $settingsLoop.Count 1
    Assert-Equal '_modelDeploymentNamesSettings gated by deployModelDeployments' $namesLoop[0] $projection.changes.variables.changes.copy.changes['15'].after
    Assert-Equal '_modelDeploymentSettings gated by deployModelDeployments' $settingsLoop[0] $projection.changes.variables.changes.copy.changes['18'].after

    # Foundry account, project, Search connection, and knowledge base connection remain gated by deployAiFoundry, not deployModelDeployments.
    Assert-Equal 'aiFoundry module condition ignores deployModelDeployments' $t.resources.aiFoundry.condition "[parameters('deployAiFoundry')]"
    Assert-Equal 'Search connection condition ignores deployModelDeployments' $t.resources.aiFoundryConnectionSearch.condition "[and(parameters('deployAiFoundry'), parameters('deploySearchService'))]"
    Assert-Equal 'Knowledge base connection condition ignores deployModelDeployments' $t.resources.aiFoundryKnowledgeBaseSearchConnection.condition "[and(and(and(parameters('deployAiFoundry'), parameters('deployAfProject')), parameters('deploySearchService')), equals(parameters('retrievalBackend'), 'foundry_iq'))]"

    # 3. Verify bounded scenarios: external gateway mode (deployModelDeployments=false) vs default/fallback modes.
    $defaultSeedModels = $rootParams.modelDeploymentList.value
    Assert-Equal 'Seed retains two default declared models' $defaultSeedModels.Count 2

    $gatewayWithSeedModels = Resolve-ModelDeploymentContract -DeployModelDeployments $false -ModelDeploymentList $defaultSeedModels
    Assert-Equal 'External gateway mode ignores seed modelDeploymentList for Foundry' $gatewayWithSeedModels.aiModelDeployments.Count 0
    Assert-Equal 'External gateway mode publishes zero model canonical keys' $gatewayWithSeedModels.modelDeploymentNamesSettings.Count 0
    Assert-Equal 'External gateway mode publishes empty MODEL_DEPLOYMENTS JSON' $gatewayWithSeedModels.modelDeploymentsJson '[]'
    Assert-Equal 'External gateway mode emits empty DEPLOYMENT_METADATA.modelDeployments' $gatewayWithSeedModels.metadataModelDeployments.Count 0

    $gatewayWithEmptyModels = Resolve-ModelDeploymentContract -DeployModelDeployments $false -ModelDeploymentList @()
    Assert-Equal 'External gateway mode with empty list skips native fallbacks' $gatewayWithEmptyModels.aiModelDeployments.Count 0
    Assert-Equal 'External gateway mode with empty list emits empty metadata' $gatewayWithEmptyModels.metadataModelDeployments.Count 0

    $nativeFallbackMode = Resolve-ModelDeploymentContract -DeployModelDeployments $true -ModelDeploymentList @()
    Assert-Equal 'Default deployModelDeployments=true with [] preserves 2 native fallback models' $nativeFallbackMode.aiModelDeployments.Count 2
    Assert-Equal 'Native fallback canonical names preserved' @($nativeFallbackMode.metadataModelDeployments | ForEach-Object { $_.canonicalName }) @('GPT_MODEL', 'EMBEDDING_MODEL')

    $explicitSeedMode = Resolve-ModelDeploymentContract -DeployModelDeployments $true -ModelDeploymentList $defaultSeedModels
    Assert-Equal 'Default deployModelDeployments=true with seed models deploys 2 models' $explicitSeedMode.aiModelDeployments.Count 2
    Assert-Equal 'Default seed publishes CHAT_DEPLOYMENT_NAME and EMBEDDING_DEPLOYMENT_NAME' @($explicitSeedMode.modelDeploymentNamesSettings | ForEach-Object { $_.name }) @('CHAT_DEPLOYMENT_NAME', 'EMBEDDING_DEPLOYMENT_NAME')

    # 4. Verify inverse normalization restores historical graph and rejects mutations.
    $restored = ConvertTo-PreModelDeploymentsOptionalGraph $t
    Assert-Equal 'Inverse removes deployModelDeployments parameter' $restored.parameters.ContainsKey('deployModelDeployments') $false
    Assert-Equal 'Inverse restores historical _deploymentMetadataModels' $restored.variables._deploymentMetadataModels $projection.changes.variables.changes._deploymentMetadataModels.before

    $mutationCases = @(
        @{
            Name   = 'deployModelDeployments default flipped to false'
            Mutate = { param($m) $m.parameters.deployModelDeployments.defaultValue = $false }
        },
        @{
            Name   = '_deploymentMetadataModels gate bypassed'
            Mutate = { param($m) $m.variables._deploymentMetadataModels = $projection.changes.variables.changes._deploymentMetadataModels.before }
        },
        @{
            Name   = '_modelDeploymentNamesSettings gate bypassed'
            Mutate = { param($m) $m.variables.copy[15] = $projection.changes.variables.changes.copy.changes['15'].before }
        },
        @{
            Name   = '_modelDeploymentSettings gate bypassed'
            Mutate = { param($m) $m.variables.copy[18] = $projection.changes.variables.changes.copy.changes['18'].before }
        }
    )
    foreach ($case in $mutationCases) {
        $mutated = $rawJson | ConvertFrom-Json -AsHashtable -Depth 100
        & $case.Mutate $mutated
        Assert-Rejected "Reject $($case.Name)" { ConvertTo-PreModelDeploymentsOptionalGraph $mutated }
    }

    Write-Host "External AI Gateway model-free contract passed: $script:checks assertions."
}
finally {
    Remove-Item -LiteralPath $compiledFile -Force -ErrorAction SilentlyContinue
}
