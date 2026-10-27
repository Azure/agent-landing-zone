<#
.SYNOPSIS
    Validates safe component deployment flag dependencies.

.DESCRIPTION
    Compiles main.bicep and proves that invalid component combinations reach the
    validation module while dependent Container Apps, subnet, private DNS, Key
    Vault, and App Configuration artifacts use defensive gates.
#>

[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'main.bicep')
)

$ErrorActionPreference = 'Stop'
$failures = [System.Collections.Generic.List[string]]::new()
$compiledFile = Join-Path ([System.IO.Path]::GetTempPath()) "component-flags-contract-$([guid]::NewGuid()).json"

function Test-Contains {
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [string]$Actual,
        [Parameter(Mandatory)] [string[]]$Required
    )

    $missing = @($Required | Where-Object { -not $Actual.Contains($_) })
    if ($missing.Count -gt 0) {
        $failures.Add("$Name is missing: $($missing -join ', ')") | Out-Null
        Write-Host "  [FAIL] $Name is missing: $($missing -join ', ')" -ForegroundColor Red
    }
    else {
        Write-Host "  [PASS] $Name" -ForegroundColor Green
    }
}

function Test-ExactExpression([string]$Name, [string]$Actual, [string]$Expected) {
    if ($Actual -cne $Expected) {
        $failures.Add("$Name -- unsupported compiled expression.") | Out-Null
        Write-Host "  [FAIL] $Name -- expected $Expected; got $Actual" -ForegroundColor Red
    }
    else { Write-Host "  [PASS] $Name" -ForegroundColor Green }
}

try {
    if (Get-Command az -ErrorAction SilentlyContinue) {
        $env:PYTHONIOENCODING = 'utf-8'
        & az bicep build --file $MainFile --outfile $compiledFile
    }
    elseif (Get-Command bicep -ErrorAction SilentlyContinue) {
        & bicep build $MainFile --outfile $compiledFile
    }
    else {
        throw 'Neither bicep nor az is available on PATH.'
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Bicep compilation failed with exit code $LASTEXITCODE."
    }

    $template = Get-Content -LiteralPath $compiledFile -Raw | ConvertFrom-Json -Depth 100
    Write-Host 'Component deployment flag contract' -ForegroundColor Cyan

    $validation = $template.resources.componentFlagValidation
    if ($null -eq $validation) {
        $failures.Add("Symbolic module 'componentFlagValidation' is missing.") | Out-Null
        Write-Host "  [FAIL] Symbolic module 'componentFlagValidation' is missing." -ForegroundColor Red
    }
    else {
        Test-Contains -Name 'Container Apps/environment validation expression' `
            -Actual ([string]$validation.properties.parameters.containerAppsRequireEnvironment.value) `
            -Required @("parameters('deployContainerApps')", "parameters('deployContainerEnv')")
        Test-Contains -Name 'Container App API-key prerequisite validation expression' `
            -Actual ([string]$validation.properties.parameters.containerAppApiKeysHavePrerequisites.value) `
            -Required @(
                "parameters('useCAppAPIKey')",
                "parameters('deployContainerApps')",
                "parameters('deployKeyVault')",
                "parameters('deployAppConfig')",
                "parameters('appRuntimeConfigurationMode')"
            )
        Test-ExactExpression -Name 'BYO subnet/NSG protection evaluates actual selected writes' `
            -Actual ([string]$validation.properties.parameters.existingSubnetNsgAssociationsAreProtected.value) `
            -Expected "[not(and(and(and(parameters('networkIsolation'), parameters('useExistingVNet')), not(empty(variables('selectedSubnetDefinitions')))), not(parameters('deployNsgs'))))]"
        Test-Contains -Name 'Validation module fail messages' `
            -Actual ([string]$validation.properties.template.outputs.validated.value) `
            -Required @(
                'Container Apps require the Container Apps Environment.',
                'Container App API keys require Container Apps, Key Vault, App Configuration, and appConfig runtime mode.',
                'A network-isolated deployment cannot update subnets in an existing VNet while deployNsgs is false.'
            )
    }

    Test-Contains -Name 'Defensive Container Apps resource gate' `
        -Actual ([string]$template.resources.containerApps.condition) `
        -Required @("variables('_deployContainerApps')")
    Test-Contains -Name 'Effective Container Apps gate includes environment and API-key prerequisites' `
        -Actual ([string]$template.variables._deployContainerApps) `
        -Required @(
            "parameters('deployContainerApps')",
            "parameters('deployContainerEnv')",
            "variables('_containerAppApiKeyPrerequisitesMet')"
        )
    Test-Contains -Name 'Defensive Container Apps settings gate' `
        -Actual ([string]$template.resources.containerAppsSettings.condition) `
        -Required @("variables('_deployContainerApps')")
    Test-Contains -Name 'Defensive API-key publication gate' `
        -Actual ([string]$template.resources.appConfigKeyVaultPopulate.condition) `
        -Required @(
            "variables('_deployContainerApps')",
            "parameters('deployKeyVault')",
            "parameters('deployAppConfig')",
            "variables('_runtimeConfigIsAppConfig')"
        )
    Test-ExactExpression -Name 'Selected subnet set includes global and isolation precedence' `
        -Actual ([string]$template.variables.selectedSubnetDefinitions) `
        -Expected "[filter(variables('subnetDefinitions'), lambda('subnet', and(and(variables('_networkIsolation'), parameters('deploySubnets')), lambdaVariables('subnet').create)))]"
    Test-ExactExpression -Name 'Defensive existing-subnet update gate' `
        -Actual ([string]$template.resources.virtualNetworkSubnets.condition) `
        -Expected "[and(and(and(and(variables('_networkIsolation'), parameters('useExistingVNet')), parameters('deploySubnets')), parameters('deployNsgs')), not(empty(variables('selectedSubnetDefinitions'))))]"
    Test-Contains -Name 'Container Apps private DNS follows environment deployment' `
        -Actual ([string]$template.variables._dnsZonesList) `
        -Required @("and(parameters('deployContainerEnv'), not(variables('_byoZoneContainerApps')))")
    Test-Contains -Name 'Container App Key Vault secrets require the complete prerequisite set' `
        -Actual ([string]$template.variables._containerAppsKeyVaultKeys) `
        -Required @(
            "variables('_deployContainerApps')",
            "parameters('deployKeyVault')",
            "parameters('deployAppConfig')",
            "variables('_runtimeConfigIsAppConfig')"
        )

    Test-Contains -Name 'AI Foundry local-auth selection reaches the account module' `
        -Actual ($template.resources.aiFoundry | ConvertTo-Json -Compress -Depth 100) `
        -Required @("parameters('aiFoundryDisableLocalAuth')")

    $parametersFile = Join-Path (Split-Path -Parent $MainFile) 'main.parameters.json'
    $parameterValues = (Get-Content -LiteralPath $parametersFile -Raw | ConvertFrom-Json -Depth 100).parameters
    $expectedEnvironmentMappings = [ordered]@{
        deployCosmosDb            = '${DEPLOY_COSMOS_DB=true}'
        deployContainerApps       = '${DEPLOY_CONTAINER_APPS=true}'
        deployContainerRegistry   = '${DEPLOY_CONTAINER_REGISTRY=true}'
        deployContainerEnv        = '${DEPLOY_CONTAINER_ENV=true}'
        deployNsgs                = '${DEPLOY_NSGS=true}'
        aiFoundryDisableLocalAuth = '${AI_FOUNDRY_DISABLE_LOCAL_AUTH=true}'
    }
    foreach ($entry in $expectedEnvironmentMappings.GetEnumerator()) {
        $binding = $parameterValues.($entry.Key)
        $actual = if ($null -ne $binding) { $binding.value } else { $template.parameters.($entry.Key).defaultValue }
        # The incorporated parameter files retain literal true strings, and
        # omitted inputs use native Bicep defaults. An upstream azd alias is
        # also supported, but false/renamed aliases must never pass this gate.
        $compatible = ($actual -is [bool] -and $actual) -or
            ($actual -is [string] -and ($actual -ceq 'true' -or $actual -ceq $entry.Value))
        if (-not $compatible) {
            $failures.Add("$($entry.Key) must retain its true default or exact '$($entry.Value)' mapping; got '$actual'.") | Out-Null
            Write-Host "  [FAIL] $($entry.Key) environment mapping" -ForegroundColor Red
        }
        else {
            Write-Host "  [PASS] $($entry.Key) environment mapping" -ForegroundColor Green
        }
    }
}
finally {
    Remove-Item -LiteralPath $compiledFile -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    Write-Host "`n$($failures.Count) component deployment flag contract check(s) failed." -ForegroundColor Red
    exit 1
}

Write-Host "`nComponent deployment flag contract checks passed." -ForegroundColor Green
exit 0
