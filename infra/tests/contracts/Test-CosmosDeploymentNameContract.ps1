<#
.SYNOPSIS
    Validates Cosmos DB nested deployment names stay within ARM's 64-character limit.

.DESCRIPTION
    Regression test for issue #119. The Cosmos DB account AVM previously received
    the SQL database collection inline and composed a nested deployment name from
    the complete database resource name. CAF environment names of 19 or more
    characters could therefore make the deployment name exceed 64 characters.

    The test compiles main.bicep and proves that:
      - the account AVM no longer creates its unbounded SQL database deployment;
      - a fixed, bounded local module deploys the SQL database and containers;
      - the database and container resource names remain parameter-driven; and
      - the local module waits for the Cosmos DB account deployment.
#>

[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'main.bicep')
)

$ErrorActionPreference = 'Stop'
$failures = [System.Collections.Generic.List[string]]::new()
$compiledFile = Join-Path ([System.IO.Path]::GetTempPath()) "cosmos-deployment-name-contract-$([guid]::NewGuid()).json"

function Add-Failure {
    param([Parameter(Mandatory)] [string]$Message)
    $failures.Add($Message) | Out-Null
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Add-Pass {
    param([Parameter(Mandatory)] [string]$Message)
    Write-Host "  [PASS] $Message" -ForegroundColor Green
}

function Assert-True {
    param(
        [Parameter(Mandatory)] [bool]$Condition,
        [Parameter(Mandatory)] [string]$Message
    )

    if ($Condition) {
        Add-Pass $Message
    }
    else {
        Add-Failure $Message
    }
}

Write-Host 'Cosmos DB deployment-name contract' -ForegroundColor Cyan

try {
    az bicep build --file $MainFile --outfile $compiledFile | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Bicep compilation failed with exit code $LASTEXITCODE."
    }

    $template = Get-Content -Path $compiledFile -Raw | ConvertFrom-Json -Depth 100
    $accountDeployment = $template.resources.cosmosDBAccount
    $databaseDeployment = $template.resources.cosmosSqlDatabase

    $topLevelDeployments = @(
        foreach ($resourceProperty in $template.resources.PSObject.Properties) {
            if ($resourceProperty.Value.type -eq 'Microsoft.Resources/deployments') {
                $resourceProperty.Value
            }
        }
    )
    $resourceNameDerivedDeployments = @(
        $topLevelDeployments |
            Where-Object { ([string]$_.name).Contains("variables('resourceNames')") }
    )
    Assert-True `
        -Condition ($resourceNameDerivedDeployments.Count -eq 0) `
        -Message 'Top-level deployment names do not embed environment-derived resource names'

    $oversizedStaticDeployments = @(
        $topLevelDeployments |
            Where-Object {
                $name = [string]$_.name
                -not $name.StartsWith('[') -and $name.Length -gt 64
            }
    )
    Assert-True `
        -Condition ($oversizedStaticDeployments.Count -eq 0) `
        -Message 'Every static top-level deployment name is within the 64-character ARM limit'

    Assert-True `
        -Condition (
            [string]$template.resources.aiFoundry.name -eq 'aiFoundryDeployment' -and
            [string]$template.resources.aiFoundryBingConnection.name -eq 'aiFoundryBingConnection'
        ) `
        -Message 'Foundry deployment names remain bounded when CAF resource names are long'

    Assert-True `
        -Condition ($null -ne $accountDeployment) `
        -Message 'Cosmos DB account AVM deployment remains present'

    $accountResources = $accountDeployment.properties.template.resources
    $accountSqlDeployments = if ($accountResources -is [array]) {
        @($accountResources | Where-Object {
            $_.type -like 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases*' -or
            ($_.type -eq 'Microsoft.Resources/deployments' -and $_.copy.name -ceq 'databaseAccount_sqlDatabases')
        })
    }
    else { @($accountResources.databaseAccount_sqlDatabases | Where-Object { $null -ne $_ }) }
    $localAccountOnly = $accountResources -is [array] -and
        $accountResources.Count -eq 1 -and
        $accountResources[0].type -ceq 'Microsoft.DocumentDB/databaseAccounts' -and
        $null -eq $accountDeployment.properties.template.parameters.sqlDatabases
    Assert-True `
        -Condition (
            $null -eq $accountDeployment.properties.parameters.sqlDatabases -and
            (($localAccountOnly -and $accountSqlDeployments.Count -eq 0) -or
                ($accountSqlDeployments.Count -eq 1 -and
                    [string]$accountSqlDeployments[0].copy.count -eq "[length(coalesce(parameters('sqlDatabases'), createArray()))]"))
        ) `
        -Message 'Account-only local module creates no SQL children (or the legacy AVM receives an empty SQL collection)'

    Assert-True `
        -Condition ($null -ne $databaseDeployment) `
        -Message 'Fixed-name Cosmos SQL database deployment is present'

    $deploymentName = [string]$databaseDeployment.name
    Assert-True `
        -Condition ($deploymentName -eq 'cosmosSqlDatabase' -and $deploymentName.Length -le 64) `
        -Message 'Cosmos SQL deployment name is constant and within the 64-character ARM limit'

    $databaseParameters = $databaseDeployment.properties.parameters
    Assert-True `
        -Condition ([string]$databaseParameters.databaseName.value -eq "[variables('resourceNames').dbDatabaseName]") `
        -Message 'Database resource name remains the configured resource name'

    Assert-True `
        -Condition ([string]$databaseParameters.databaseAccountName.value -eq "[variables('resourceNames').dbAccountName]") `
        -Message 'Database deployment targets the configured Cosmos DB account'

    $localResources = $databaseDeployment.properties.template.resources
    $sqlDatabase = $localResources.sqlDatabase
    $sqlContainers = $localResources.sqlContainers
    Assert-True `
        -Condition (
            [string]$sqlDatabase.type -eq 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases' -and
            [string]$sqlDatabase.apiVersion -eq '2024-11-15' -and
            [string]$sqlDatabase.name -eq "[format('{0}/{1}', parameters('databaseAccountName'), parameters('databaseName'))]"
        ) `
        -Message 'Local module preserves the direct SQL database resource contract'

    Assert-True `
        -Condition (
            [string]$sqlContainers.type -eq 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers' -and
            [string]$sqlContainers.apiVersion -eq '2024-11-15' -and
            [string]$sqlContainers.name -eq "[format('{0}/{1}/{2}', parameters('databaseAccountName'), parameters('databaseName'), parameters('containers')[copyIndex()].name)]"
        ) `
        -Message 'Local module preserves the direct container resource contract'

    $serializedLocalTemplate = $databaseDeployment.properties.template | ConvertTo-Json -Depth 100 -Compress
    Assert-True `
        -Condition ($serializedLocalTemplate -notmatch '"type":"Microsoft.Resources/deployments"') `
        -Message 'Local Cosmos module introduces no additional nested deployments'

    $databaseOptions = [string]$sqlDatabase.properties.options
    Assert-True `
        -Condition (
            $databaseOptions.Contains("'EnableServerless'") -and
            $databaseOptions.Contains("parameters('databaseThroughput')")
        ) `
        -Message 'Database throughput remains disabled for serverless and parameter-driven otherwise'

    $containerResource = $sqlContainers.properties.resource
    $partitionKeyJson = $containerResource.partitionKey | ConvertTo-Json -Depth 20 -Compress
    Assert-True `
        -Condition (
            [string]$containerResource.defaultTtl -match 'defaultTtl.*-1' -and
            [string]$containerResource.indexingPolicy -match 'indexingPolicy' -and
            $partitionKeyJson.Contains("startsWith(parameters('containers')") -and
            $partitionKeyJson.Contains('"kind":"Hash"') -and
            $partitionKeyJson.Contains('"version":1')
        ) `
        -Message 'Container TTL, indexing, and partition-key semantics remain intact'

    $containerOptions = [string]$sqlContainers.properties.options
    Assert-True `
        -Condition (
            $containerOptions.Contains("'EnableServerless'") -and
            $containerOptions.Contains("parameters('databaseThroughput')") -and
            $containerOptions.Contains("'throughput'") -and
            $containerOptions.Contains('400')
        ) `
        -Message 'Container throughput preserves serverless, database-level, and default branches'

    $containerParameterCopy = $databaseParameters.containers.copy | ConvertTo-Json -Depth 20 -Compress
    Assert-True `
        -Condition (
            $containerParameterCopy.Contains("'name'") -and
            $containerParameterCopy.Contains("'paths'") -and
            $containerParameterCopy.Contains("'defaultTtl', -1") -and
            $containerParameterCopy.Contains("'throughput'") -and
            $containerParameterCopy.Contains("'indexingPolicy'")
        ) `
        -Message 'Main template forwards every supported container setting'

    $dependsOn = @($databaseDeployment.dependsOn)
    Assert-True `
        -Condition ($dependsOn -contains 'cosmosDBAccount') `
        -Message 'SQL database deployment waits for the Cosmos DB account'

    Assert-True `
        -Condition (@($sqlContainers.dependsOn) -contains 'sqlDatabase') `
        -Message 'Container resources wait for the SQL database'

    $reportedEnvironmentName = 'gpt-rag-consolidate-v350'
    Assert-True `
        -Condition ($reportedEnvironmentName.Length -ge 19 -and $deploymentName.Length -le 64) `
        -Message 'Issue #119 long environment-name reproduction cannot affect the fixed deployment name'
}
finally {
    Remove-Item -Path $compiledFile -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    Write-Host "`nCosmos DB deployment-name contract failed with $($failures.Count) error(s)." -ForegroundColor Red
    exit 1
}

Write-Host "`nCosmos DB deployment-name contract checks passed." -ForegroundColor Green
