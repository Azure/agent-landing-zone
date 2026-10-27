# postProvision.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "🔧 Running post-provision steps..."
Write-Host ""

#-------------------------------------------------------------------------------
# Mirror azd environment variables into process environment
# This avoids persisting secrets in the User environment (registry)
#-------------------------------------------------------------------------------
$azdValues = & azd env get-values --output json
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($azdValues -join "`n"))) {
    Write-Error "Could not load the selected azd environment; refusing to configure resources."
    exit 1
}
try {
    $azdEnvironment = ($azdValues -join "`n") | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-Error "Invalid azd environment JSON; refusing to configure resources."
    exit 1
}
if ($azdEnvironment -isnot [pscustomobject] -or @($azdEnvironment.PSObject.Properties).Count -eq 0) {
    Write-Error "The selected azd environment must be a nonempty object."
    exit 1
}
foreach ($prop in $azdEnvironment.PSObject.Properties) {
    if ($prop.Name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$' -or $prop.Value -isnot [string] -or $prop.Value.Contains([char]0)) {
        Write-Error "Invalid azd environment key or value; refusing to configure resources."
        exit 1
    }
}
foreach ($prop in $azdEnvironment.PSObject.Properties) {
    Set-Item -Path "Env:$($prop.Name)" -Value $prop.Value
}

#-------------------------------------------------------------------------------
# Private deployment-host prerequisite (before data-plane configuration)
#-------------------------------------------------------------------------------
function Test-Truthy {
    param([AllowNull()][string]$Value)
    return -not [string]::IsNullOrWhiteSpace($Value) -and $Value -match '^(1|true|t|yes|y)$'
}

$env:AGENTLZ_REPO_ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
& python -c "import os, runpy, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); sys.argv = ['config.deployment.resource_groups', '--azure-dir', os.path.join(os.environ['AGENTLZ_REPO_ROOT'], '.azure'), '--bind-only']; runpy.run_module('config.deployment.resource_groups', run_name='__main__')" | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error "Resource-group destination binding failed; configuration has not started."; exit $LASTEXITCODE }
& python -c "import os, runpy, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); sys.argv = ['config.deployment.private_network', '--stage', 'post-provision']; runpy.run_module('config.deployment.private_network', run_name='__main__')"
$networkExitCode = $LASTEXITCODE
if ($networkExitCode -eq 20) {
    Write-Warning "Post-provision configuration explicitly deferred; application setup is incomplete."
    exit 0
}
if ($networkExitCode -ne 0) {
    Write-Error "Private post-provision prerequisites failed. Connect through VPN/VNet and rerun postProvision; configuration has not started." -ErrorAction Continue
    exit $networkExitCode
}

#-------------------------------------------------------------------------------
# Container APP API Keys Warning
#-------------------------------------------------------------------------------
Write-Host ""
if ($env:USE_CAPP_API_KEY -and $env:USE_CAPP_API_KEY.ToLower() -eq 'true') {
    Write-Host "🔑 Using API Key for Container Apps access."
    Write-Host "⚠️ IMPORTANT: Each App API Key was initialized with resourceToken."
    Write-Host "    Please update to a custom API key ASAP."
}

#-------------------------------------------------------------------------------
# Check required environment variable
#-------------------------------------------------------------------------------
Write-Host "📋 Checking required environment variables..."
$requiredVars = @('APP_CONFIG_ENDPOINT')
$missing = @()
foreach ($v in $requiredVars) {
    $val = [Environment]::GetEnvironmentVariable($v)
    if (-not $val) { $missing += $v; Write-Host "  $v=<missing>" -ForegroundColor Yellow } else { Write-Host "  $v=$val" }
}
if ($missing.Count -gt 0) {
    Write-Error "Missing required variables: $($missing -join ', ')."
    exit 1
}

function Get-RequiredEnvValue {
    param([Parameter(Mandatory = $true)][string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        Write-Error "Missing required environment variable '$Name'."
        exit 1
    }
    return $value
}

function Get-OptionalEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Default = ''
    )
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

function Invoke-NativeCommand {
    param([Parameter(Mandatory = $true)][scriptblock]$Command)

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Command
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Invoke-AzTsv {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Description,
        [switch]$Required
    )
    if ($env:AZURE_SUBSCRIPTION_ID -and '--subscription' -notin $Arguments -and '--ids' -notin $Arguments) {
        $Arguments += @('--subscription', $env:AZURE_SUBSCRIPTION_ID)
    }
    $output = Invoke-NativeCommand { & az @Arguments -o tsv 2>$null }
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($output)) {
        if ($Required) {
            Write-Error "Failed to resolve $Description."
            exit 1
        }
        return ''
    }
    return ($output | Select-Object -First 1).Trim()
}

function Get-UserAssignedIdentityResourceId {
    param(
        [AllowEmptyString()][string]$ResourceId,
        [Parameter(Mandatory = $true)][string]$Description
    )
    if ([string]::IsNullOrWhiteSpace($ResourceId)) {
        return ''
    }

    $identityJson = Invoke-NativeCommand {
        & az resource show --ids $ResourceId --query identity.userAssignedIdentities -o json 2>$null
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to resolve the user-assigned identity for $Description."
        exit 1
    }
    if ([string]::IsNullOrWhiteSpace($identityJson) -or $identityJson.Trim() -eq 'null') {
        return ''
    }

    try {
        $identityMap = $identityJson | ConvertFrom-Json
        $identities = @($identityMap.PSObject.Properties)
    }
    catch {
        Write-Error "The user-assigned identity response for $Description was malformed."
        exit 1
    }
    if ($identities.Count -gt 1) {
        Write-Error "Multiple user-assigned identities are attached to $Description; refusing an ambiguous selection."
        exit 1
    }
    if ($identities.Count -eq 1) {
        return $identities[0].Name
    }
    return ''
}

function Get-AppConfigResourceName {
    param([Parameter(Mandatory = $true)][string]$Endpoint)
    return (($Endpoint -replace '^https?://', '') -replace '\.azconfig\.io/?$', '')
}

function ConvertTo-FlatJsonString {
    param([Parameter(Mandatory = $true)]$Value)
    return ($Value | ConvertTo-Json -Depth 50 -Compress)
}

#-------------------------------------------------------------------------------
# Make config.* importable early (moved ahead of Set-AgentLzAppConfiguration so
# the Foundry IQ MCP pre-flight validation below can run before any App
# Configuration write/import). No Python package installation is required for
# that pre-flight check: foundry_iq_mcp_setup.py has no external dependencies.
#-------------------------------------------------------------------------------
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$repoRoot;$($env:PYTHONPATH)" } else { $repoRoot }
$env:AGENTLZ_REPO_ROOT = $repoRoot
Set-Location $repoRoot

function Invoke-PythonModule {
    param(
        [Parameter(Mandatory = $true)][string]$ModuleName,
        [string[]]$Arguments = @()
    )
    Invoke-NativeCommand {
        & python -c "import os, runpy, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); sys.argv = ['$ModuleName'] + sys.argv[1:]; runpy.run_module('$ModuleName', run_name='__main__')" @Arguments
    }
}

#-------------------------------------------------------------------------------
# Foundry IQ MCP Server source pre-flight validation
# Validates FOUNDRY_IQ_MCP_SOURCES_JSON (JSON shape, security constraints:
# only non-secret queryHeaders references, no auth/authentication or literal
# credential material at any nesting depth, trusted-host allowlisting,
# output-parsing shape, token caps) before ANY of it is imported into Azure
# App Configuration below. The validator returns canonical JSON so the raw
# operator value is never persisted.
#-------------------------------------------------------------------------------
$mcpEnabled = Test-Truthy (Get-OptionalEnvValue 'FOUNDRY_IQ_MCP_ENABLED' 'false')
if ($mcpEnabled) {
    Write-Host "🔐 Validating Foundry IQ MCP Server source configuration..."
    $mcpSourcesJson = Invoke-PythonModule -ModuleName 'config.search.foundry_iq_mcp_setup' -Arguments @('--canonical')
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Foundry IQ MCP Server source validation failed; aborting before any App Configuration write."
        exit 1
    }
    $mcpSourcesJson = ([string]$mcpSourcesJson).Trim()
    $mcpReasoningEffort = Get-OptionalEnvValue 'FOUNDRY_IQ_MCP_REASONING_EFFORT' 'low'
    $mcpTrustedHosts = Get-OptionalEnvValue 'FOUNDRY_IQ_MCP_TRUSTED_HOSTS' ''
    $mcpLogToolArguments = Get-OptionalEnvValue 'FOUNDRY_IQ_MCP_LOG_TOOL_ARGUMENTS' 'false'
} else {
    # Disabled provisioning must not parse, preserve, or persist stale source
    # content. Write canonical safe defaults instead.
    Write-Host "⏭️ Foundry IQ MCP Server disabled; skipping source validation."
    $mcpSourcesJson = '[]'
    $mcpReasoningEffort = 'low'
    $mcpTrustedHosts = ''
    $mcpLogToolArguments = 'false'
}

function Set-AgentLzAppConfiguration {
    param(
        [Parameter(Mandatory = $true)][string]$Endpoint,
        [Parameter(Mandatory = $true)][string]$Label
    )

    Write-Host "⚙️ Populating Agent Landing Zone App Configuration settings (label=$Label)..."
    Invoke-NativeCommand { az config set extension.use_dynamic_install=yes_without_prompt 2>$null | Out-Null }

    $resourceGroup = Get-RequiredEnvValue 'AZURE_RESOURCE_GROUP'
    $foundryResourceGroup = Get-OptionalEnvValue 'AZURE_FOUNDRY_RESOURCE_GROUP' $resourceGroup
    $networkResourceGroup = Get-OptionalEnvValue 'AZURE_NETWORK_RESOURCE_GROUP' $resourceGroup
    $subscriptionId = Get-OptionalEnvValue 'AZURE_SUBSCRIPTION_ID'
    if (-not $subscriptionId) {
        $subscriptionId = Invoke-AzTsv -Arguments @('account', 'show', '--query', 'id') -Description 'current subscription id' -Required
    }

    $tenantId = Get-OptionalEnvValue 'AZURE_TENANT_ID'
    if (-not $tenantId) {
        $tenantId = Invoke-AzTsv -Arguments @('account', 'show', '--query', 'tenantId') -Description 'current tenant id' -Required
    }

    $resourceToken = Get-OptionalEnvValue 'RESOURCE_TOKEN'
    if (-not $resourceToken -and $Endpoint -match 'appcs-?([a-z0-9]{8,})\.azconfig\.io') {
        $resourceToken = $matches[1]
    }
    if (-not $resourceToken) {
        Write-Error "RESOURCE_TOKEN could not be resolved; cannot populate Agent Landing Zone App Configuration deterministically."
        exit 1
    }

    $location = Get-OptionalEnvValue 'AZURE_LOCATION' (Get-OptionalEnvValue 'LOCATION')
    $environmentName = Get-OptionalEnvValue 'AZURE_ENV_NAME' (Get-OptionalEnvValue 'ENVIRONMENT_NAME')
    $deploymentName = Get-OptionalEnvValue 'DEPLOYMENT_NAME'
    $release = Get-OptionalEnvValue 'RELEASE'
    # ADR-0001 rev. 5: read back the deployment topology that scripts/preProvision
    # already resolved and materialized into the azd environment (mirrored into
    # process env above), rather than re-deriving the fresh/existing/sticky
    # decision here. config.deployment.topology --describe performs no Azure CLI
    # lookups; it is a pure read-back of DEPLOYMENT_TOPOLOGY / the legacy flag
    # pair, so postProvision always agrees with preProvision's decision.
    $topologyJson = Invoke-PythonModule -ModuleName 'config.deployment.topology' -Arguments @('--describe')
    if ($LASTEXITCODE -ne 0 -or -not $topologyJson) {
        Write-Error "Failed to resolve the Agent Landing Zone deployment topology. Ensure scripts/preProvision ran successfully before postProvision."
        exit 1
    }
    $topologyInfo = ([string]$topologyJson).Trim() | ConvertFrom-Json
    # The requested topology remains hosted throughout migration, while the
    # shared resolver reports a classic effective runtime until both the
    # immutable image and hosted endpoint exist.
    $runtimeTopology = [string]$topologyInfo.runtime_topology
    $hostedMode = $runtimeTopology -ne 'classic'
    $administrativePanel = $runtimeTopology -eq 'hosted-panel'
    $deployIngestion = [bool]$topologyInfo.deploy_ingestion_container_app
    $cosmosEnabled = (-not $hostedMode) -or $administrativePanel

    $appConfigName = Get-AppConfigResourceName -Endpoint $Endpoint
    $nameSuffix = $resourceToken

    # --- CAF-aware resource discovery (v3.1.0) ---
    # AI Landing Zone v2.2.0 defaults to caf naming; resource names no longer follow the
    # legacy "<prefix>-$nameSuffix" pattern. Discover exact identities in their
    # configured destinations; missing or ambiguous resources are not guessed.
    function _resolveResource {
        param(
            [string]$Type,
            [string]$Fallback,
            [scriptblock]$Filter = $null,
            [string]$PreferredName = '',
            [string]$Group = $resourceGroup,
            [string]$ResourceId = '',
            [switch]$Optional
        )
            if ($ResourceId) {
                $resourcePattern = '^/subscriptions/[^/\s]+/resourceGroups/[^/\s]+/providers/' + [regex]::Escape($Type) + '/([^/\s]+)$'
                if ($ResourceId -notmatch $resourcePattern) { throw "Declared '$Type' ARM ID is malformed." }
                $declaredName = $matches[1]
                if ($PreferredName -and $declaredName -ne $PreferredName) { throw "Declared '$Type' ARM ID and name conflict." }
                $metadata = az resource show --ids $ResourceId -o json 2>$null
                if ($LASTEXITCODE -ne 0 -or -not $metadata) { throw "Failed to read declared '$Type' ARM ID." }
                $resolved = $metadata | ConvertFrom-Json
                if (-not $resolved.id -or -not $resolved.id.Equals($ResourceId, [StringComparison]::OrdinalIgnoreCase) -or $resolved.type -ne $Type) {
                    throw "Declared '$Type' ARM metadata identity/type mismatch."
                }
                return $declaredName
            }
            $json = az resource list --subscription $subscriptionId -g $Group --resource-type $Type -o json 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $json) { throw "Failed to discover '$Type' in its configured destination." }
            $items = $json | ConvertFrom-Json -NoEnumerate
            if ($null -eq $items -or $items -isnot [array]) { throw "Invalid resource discovery response for '$Type'." }
            foreach ($item in $items) {
                $expectedId = "/subscriptions/$subscriptionId/resourceGroups/$Group/providers/$Type/$($item.name)"
                if (-not $item.id -or -not $item.id.Equals($expectedId, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Resource discovery returned a foreign or malformed '$Type' identity."
                }
            }
            if ($Filter -and -not $PreferredName) { $items = @($items | Where-Object $Filter) }
            if (-not [string]::IsNullOrWhiteSpace($PreferredName)) {
                $preferredMatches = @(
                    $items | Where-Object {
                        $_.name.Equals(
                            $PreferredName,
                            [StringComparison]::OrdinalIgnoreCase
                        )
                    }
                )
                if ($preferredMatches.Count -eq 1) {
                    return $preferredMatches[0].name
                }
                throw "Configured resource '$PreferredName' did not uniquely match type '$Type' in its destination."
            }
            if ($items.Count -eq 1) { return $items[0].name }
            if ($items.Count -eq 0 -and $Optional) { return '' }
            throw "Expected exactly one '$Type' resource in its destination; set the corresponding resource name explicitly."
    }

    # Storage: main workload vs AI Foundry storage (prefix "staif")
    $storageName = _resolveResource `
        -Group $foundryResourceGroup `
        -Type 'Microsoft.Storage/storageAccounts' `
        -Fallback "st$nameSuffix" `
        -Filter { -not $_.name.StartsWith('staif') } `
        -PreferredName (Get-OptionalEnvValue 'AZURE_STORAGE_ACCOUNT_NAME')
    $foundryStorageName = _resolveResource `
        -Group $foundryResourceGroup -Optional `
        -Type 'Microsoft.Storage/storageAccounts' `
        -Fallback "staif$nameSuffix" `
        -Filter { $_.name.StartsWith('staif') } `
        -PreferredName (Get-OptionalEnvValue 'AZURE_AI_FOUNDRY_STORAGE_ACCOUNT_NAME')

    # Key Vault: main workload vs AI Foundry KV (prefix "kv-ai")
    $keyVaultName = _resolveResource `
        -Type 'Microsoft.KeyVault/vaults' `
        -Fallback "kv-$nameSuffix" `
        -Filter { -not $_.name.StartsWith('kv-ai') } `
        -PreferredName (Get-OptionalEnvValue 'KEY_VAULT_NAME')

    # Cosmos: main vs AI Foundry-project cosmos (prefix "cosmos-aif")
    $cosmosName = if ($cosmosEnabled) {
        _resolveResource `
            -Type 'Microsoft.DocumentDB/databaseAccounts' `
            -Fallback "cosmos-$nameSuffix" `
            -Filter { -not $_.name.StartsWith('cosmos-aif') }
    } else { '' }

    # Search: main vs AI Foundry-project search (prefix "srch-aif")
    $searchName = _resolveResource `
        -Group $foundryResourceGroup `
        -Type 'Microsoft.Search/searchServices' `
        -Fallback "srch-$nameSuffix" `
        -Filter { -not $_.name.StartsWith('srch-aif') } `
        -PreferredName (Get-OptionalEnvValue 'AZURE_AI_SEARCH_NAME')

    # AI Foundry Cognitive account (kind = AIServices) - LZ v2.2.0 deploys a single one
    $foundryProjectResourceId = Get-OptionalEnvValue 'AZURE_AI_PROJECT_RESOURCE_ID'
    $preferredFoundryName = Get-OptionalEnvValue 'AZURE_AI_FOUNDRY_NAME'
    if (
        -not $preferredFoundryName -and
        $foundryProjectResourceId -match '/accounts/([^/]+)/projects/'
    ) {
        $preferredFoundryName = $matches[1]
    }
    $foundryName = _resolveResource `
        -Group $foundryResourceGroup `
        -Type 'Microsoft.CognitiveServices/accounts' `
        -Fallback "aif-$nameSuffix" `
        -PreferredName $preferredFoundryName

    # Resolve the project through generic ARM discovery because the specialized
    # project-list command is absent from some supported Azure CLI versions.
    $requestedFoundryProjectName = Get-OptionalEnvValue 'AI_FOUNDRY_PROJECT_NAME'
    $foundryAccountResourceId = "/subscriptions/$subscriptionId/resourceGroups/$foundryResourceGroup/providers/Microsoft.CognitiveServices/accounts/$foundryName"
    $projectJson = Invoke-NativeCommand {
        & az resource list `
            --subscription $subscriptionId `
            --resource-group $foundryResourceGroup `
            --resource-type 'Microsoft.CognitiveServices/accounts/projects' `
            -o json 2>$null
    }
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($projectJson)) {
        Write-Error "Failed to discover the AI Foundry project under '$foundryName'."
        exit 1
    }

    $foundryProjects = @(
        $projectJson |
            ConvertFrom-Json |
            Where-Object {
                $_.id.StartsWith(
                    "$foundryAccountResourceId/projects/",
                    [StringComparison]::OrdinalIgnoreCase
                )
            }
    )
    if (-not [string]::IsNullOrWhiteSpace($requestedFoundryProjectName)) {
        $foundryProjects = @(
            $foundryProjects |
                Where-Object {
                    (Split-Path $_.id -Leaf) -eq $requestedFoundryProjectName
                }
        )
    }
    if ($foundryProjects.Count -ne 1) {
        $selectionHint = if ([string]::IsNullOrWhiteSpace($requestedFoundryProjectName)) {
            'Set AI_FOUNDRY_PROJECT_NAME when the account contains more than one project.'
        } else {
            "No unique project matched AI_FOUNDRY_PROJECT_NAME='$requestedFoundryProjectName'."
        }
        Write-Error "Expected exactly one AI Foundry project under '$foundryName', found $($foundryProjects.Count). $selectionHint"
        exit 1
    }
    $foundryProjectName = Split-Path $foundryProjects[0].id -Leaf
    if ($foundryProjectResourceId -and -not $foundryProjectResourceId.Equals($foundryProjects[0].id, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Configured Foundry project ID conflicts with its discovered destination/account.'
    }

    # Container Registry / Container Apps Env / Log Analytics / App Insights
    $registryResourceGroup = Invoke-NativeCommand {
        & python -c "import os, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); from config.deployment.context import registry_resource_group; print(registry_resource_group(os.environ))"
    }
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($registryResourceGroup)) {
        throw 'Declared registry context is invalid; no App Configuration values were imported.'
    }
    $acrName = _resolveResource `
        -Group "$registryResourceGroup".Trim() `
        -Type 'Microsoft.ContainerRegistry/registries' `
        -Fallback "cr$nameSuffix" `
        -PreferredName (
            (Get-OptionalEnvValue 'AZURE_CONTAINER_REGISTRY_ENDPOINT') -replace '\..*$', ''
        )
    $containerEnvName = _resolveResource `
        -Type 'Microsoft.App/managedEnvironments' `
        -Fallback "cae-$nameSuffix"
    $logAnalyticsName = _resolveResource `
        -ResourceId (Get-OptionalEnvValue 'LOG_ANALYTICS_RESOURCE_ID') `
        -Type 'Microsoft.OperationalInsights/workspaces' `
        -Fallback "log-$nameSuffix"
    $appInsightsName = _resolveResource `
        -ResourceId (Get-OptionalEnvValue 'APP_INSIGHTS_RESOURCE_ID') `
        -Type 'Microsoft.Insights/components' `
        -Fallback "appi-$nameSuffix"

    # Container apps use the RESOURCE_TOKEN suffix from Agent Landing Zone's own bicep - this is
    # stable across naming modes.
    $frontendAppName = "ca-$nameSuffix-frontend"
    $orchestratorAppName = "ca-$nameSuffix-orchestrator"
    $dataIngestAppName = if ($deployIngestion) { "ca-$nameSuffix-dataingest" } else { '' }

    # Cosmos database name - introspect the account to get the actual DB name
    $databaseName = if ($cosmosEnabled) { Get-OptionalEnvValue 'DATABASE_NAME' } else { '' }
    if ($cosmosEnabled) {
        $dbJson = az cosmosdb sql database list --subscription $subscriptionId -g $resourceGroup -a $cosmosName -o json 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $dbJson) { throw 'Failed to discover application Cosmos databases.' }
        $dbs = $dbJson | ConvertFrom-Json -NoEnumerate
        if ($dbs -isnot [array]) { throw 'Invalid Cosmos database discovery response.' }
        if ($databaseName) { $dbs = @($dbs | Where-Object { $_.name -eq $databaseName }) }
        if ($dbs.Count -ne 1) { throw 'Expected one application Cosmos database; set DATABASE_NAME to choose one.' }
        $databaseName = $dbs[0].name
    }

    Write-Host "🔎 Resolved resource names:"
    Write-Host "   Foundry:          $foundryName / $foundryProjectName"
    Write-Host "   Storage:          $storageName (main), $foundryStorageName (foundry)"
    Write-Host "   Cosmos / DB:      $cosmosName / $databaseName"
    Write-Host "   Search:           $searchName"
    Write-Host "   Key Vault:        $keyVaultName"
    Write-Host "   ACR / CAE:        $acrName / $containerEnvName"
    Write-Host "   Observability:    $logAnalyticsName / $appInsightsName"
    Write-Host "   Container apps:   $frontendAppName, $orchestratorAppName, $dataIngestAppName"

    $resourceGroupId = "/subscriptions/$subscriptionId/resourceGroups/$resourceGroup"
    $foundryResourceGroupId = "/subscriptions/$subscriptionId/resourceGroups/$foundryResourceGroup"
    $keyVaultResourceId = "$resourceGroupId/providers/Microsoft.KeyVault/vaults/$keyVaultName"
    $storageResourceId = "$foundryResourceGroupId/providers/Microsoft.Storage/storageAccounts/$storageName"
    $cosmosResourceId = if ($cosmosEnabled) { "$resourceGroupId/providers/Microsoft.DocumentDB/databaseAccounts/$cosmosName" } else { '' }
    $searchResourceId = "$foundryResourceGroupId/providers/Microsoft.Search/searchServices/$searchName"
    $foundryResourceId = "$foundryResourceGroupId/providers/Microsoft.CognitiveServices/accounts/$foundryName"
    $foundryProjectResourceId = "$foundryResourceId/projects/$foundryProjectName"
    $containerEnvResourceId = "$resourceGroupId/providers/Microsoft.App/managedEnvironments/$containerEnvName"
    $appInsightsResourceId = Get-OptionalEnvValue 'APP_INSIGHTS_RESOURCE_ID' "$resourceGroupId/providers/Microsoft.Insights/components/$appInsightsName"
    $logAnalyticsResourceId = Get-OptionalEnvValue 'LOG_ANALYTICS_RESOURCE_ID' "$resourceGroupId/providers/Microsoft.OperationalInsights/workspaces/$logAnalyticsName"

    $frontendFqdn = Invoke-AzTsv -Arguments @('containerapp', 'show', '-g', $resourceGroup, '-n', $frontendAppName, '--query', 'properties.configuration.ingress.fqdn') -Description "$frontendAppName FQDN" -Required
    $orchestratorFqdn = if ($hostedMode) { '' } else { Invoke-AzTsv -Arguments @('containerapp', 'show', '-g', $resourceGroup, '-n', $orchestratorAppName, '--query', 'properties.configuration.ingress.fqdn') -Description "$orchestratorAppName FQDN" -Required }
    $dataIngestFqdn = if ($deployIngestion) { Invoke-AzTsv -Arguments @('containerapp', 'show', '-g', $resourceGroup, '-n', $dataIngestAppName, '--query', 'properties.configuration.ingress.fqdn') -Description "$dataIngestAppName FQDN" -Required } else { '' }

    $frontendPrincipalId = Invoke-AzTsv -Arguments @('containerapp', 'show', '-g', $resourceGroup, '-n', $frontendAppName, '--query', 'identity.principalId') -Description "$frontendAppName principal id"
    $orchestratorPrincipalId = if ($hostedMode) { '' } else { Invoke-AzTsv -Arguments @('containerapp', 'show', '-g', $resourceGroup, '-n', $orchestratorAppName, '--query', 'identity.principalId') -Description "$orchestratorAppName principal id" }
    $dataIngestPrincipalId = if ($deployIngestion) { Invoke-AzTsv -Arguments @('containerapp', 'show', '-g', $resourceGroup, '-n', $dataIngestAppName, '--query', 'identity.principalId') -Description "$dataIngestAppName principal id" } else { '' }
    $containerEnvPrincipalId = Invoke-AzTsv -Arguments @('resource', 'show', '--ids', $containerEnvResourceId, '--query', 'identity.principalId') -Description 'Container Apps Environment principal id'
    $searchPrincipalId = Invoke-AzTsv -Arguments @('resource', 'show', '--ids', $searchResourceId, '--query', 'identity.principalId') -Description 'Search service principal id'

    $appInsightsConnectionString = Invoke-AzTsv -Arguments @('resource', 'show', '--ids', $appInsightsResourceId, '--query', 'properties.ConnectionString') -Description 'Application Insights connection string'
    $appInsightsInstrumentationKey = Invoke-AzTsv -Arguments @('resource', 'show', '--ids', $appInsightsResourceId, '--query', 'properties.InstrumentationKey') -Description 'Application Insights instrumentation key'

    $containerApps = @(
        [ordered]@{ name = $frontendAppName; serviceName = 'frontend'; canonical_name = 'FRONTEND_APP'; principalId = $frontendPrincipalId; fqdn = $frontendFqdn }
    )
    if ($deployIngestion) {
        $containerApps += [ordered]@{ name = $dataIngestAppName; serviceName = 'dataingest'; canonical_name = 'DATA_INGEST_APP'; principalId = $dataIngestPrincipalId; fqdn = $dataIngestFqdn }
    }
    if (-not $hostedMode) {
        $containerApps = @(
            [ordered]@{ name = $orchestratorAppName; serviceName = 'orchestrator'; canonical_name = 'ORCHESTRATOR_APP'; principalId = $orchestratorPrincipalId; fqdn = $orchestratorFqdn }
        ) + $containerApps
    }

    $modelDeployments = @(
        [ordered]@{ canonical_name = 'CHAT_DEPLOYMENT_NAME'; capacity = 100; model = [ordered]@{ format = 'OpenAI'; name = 'gpt-5-nano'; version = '2025-08-07' }; name = 'chat'; version = '2025-08-07'; apiVersion = '2025-12-01-preview'; endpoint = "https://$foundryName.openai.azure.com/" },
        [ordered]@{ canonical_name = 'EMBEDDING_DEPLOYMENT_NAME'; capacity = 100; model = [ordered]@{ format = 'OpenAI'; name = 'text-embedding-3-large'; version = '1' }; name = 'text-embedding'; version = '1'; apiVersion = '2025-01-01-preview'; endpoint = "https://$foundryName.openai.azure.com/" }
    )

    $retrievalBackend = Get-OptionalEnvValue 'RETRIEVAL_BACKEND' 'foundry_iq'
    $foundryIqPattern = Get-OptionalEnvValue 'FOUNDRY_IQ_PATTERN' 'azureBlob'
    $ragIndexName = Get-OptionalEnvValue 'SEARCH_RAG_INDEX_NAME' "ragindex-$resourceToken"
    $knowledgeBaseName = Get-OptionalEnvValue 'KNOWLEDGE_BASE_NAME' "$ragIndexName-rag-kb"
    $knowledgeBaseConnectionName = Get-OptionalEnvValue 'KNOWLEDGE_BASE_CONNECTION_NAME' "$environmentName-knowledge-base-connection"
    $knowledgeBaseEndpoint = if ($retrievalBackend -eq 'foundry_iq') {
        Get-OptionalEnvValue 'KNOWLEDGE_BASE_ENDPOINT' "https://$searchName.search.windows.net"
    }
    else {
        ''
    }
    $knowledgeBaseConnectionId = if ($retrievalBackend -eq 'foundry_iq') {
        Get-OptionalEnvValue 'KNOWLEDGE_BASE_CONNECTION_ID' "$foundryProjectResourceId/connections/$knowledgeBaseConnectionName"
    }
    else {
        ''
    }
    $foundryIqDefaultKnowledgeSourceName = if ($foundryIqPattern -eq 'searchIndex') {
        "$ragIndexName-rag-ks"
    }
    else {
        "$ragIndexName-blob-ks"
    }
    $foundryIqKnowledgeSourceName = if ($retrievalBackend -eq 'foundry_iq') {
        Get-OptionalEnvValue 'FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME' $foundryIqDefaultKnowledgeSourceName
    }
    else {
        ''
    }
    $foundryIqKnowledgeSourceKind = if ($retrievalBackend -eq 'foundry_iq') {
        Get-OptionalEnvValue 'FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND' $foundryIqPattern
    }
    else {
        ''
    }
    $effectiveKnowledgeBaseName = if ($retrievalBackend -eq 'foundry_iq') { $knowledgeBaseName } else { '' }

    $foundryIqConversationKnowledgeSourceName = if ($retrievalBackend -eq 'foundry_iq') {
        Get-OptionalEnvValue 'FOUNDRY_IQ_CONVERSATION_KNOWLEDGE_SOURCE_NAME' "$ragIndexName-conv-ks"
    }
    else {
        ''
    }
    $searchServiceUaiResourceId = Get-OptionalEnvValue 'SEARCH_SERVICE_UAI_RESOURCE_ID'
    if (-not $searchServiceUaiResourceId) {
        $searchServiceUaiResourceId = Get-UserAssignedIdentityResourceId `
            -ResourceId $searchResourceId `
            -Description 'Azure AI Search'
    }

    $settings = [ordered]@{
        AZURE_TENANT_ID = $tenantId
        SUBSCRIPTION_ID = $subscriptionId
        AZURE_RESOURCE_GROUP = $resourceGroup
        AZURE_FOUNDRY_RESOURCE_GROUP = $foundryResourceGroup
        AZURE_NETWORK_RESOURCE_GROUP = $networkResourceGroup
        LOCATION = $location
        ENVIRONMENT_NAME = $environmentName
        DEPLOYMENT_NAME = $deploymentName
        RESOURCE_TOKEN = $resourceToken
        SEARCH_RAG_INDEX_NAME = $ragIndexName
        ENABLE_AGENTIC_RETRIEVAL = (Get-OptionalEnvValue 'ENABLE_AGENTIC_RETRIEVAL' 'false')
        RETRIEVAL_BACKEND = $retrievalBackend
        FOUNDRY_IQ_PATTERN = $foundryIqPattern
        FOUNDRY_IQ_API_VERSION = (Get-OptionalEnvValue 'FOUNDRY_IQ_API_VERSION' '2026-05-01-preview')
        FOUNDRY_IQ_KNOWLEDGE_RETRIEVAL_BILLING_PLAN = (Get-OptionalEnvValue 'FOUNDRY_IQ_KNOWLEDGE_RETRIEVAL_BILLING_PLAN' 'free')
        FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME = $foundryIqKnowledgeSourceName
        FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND = $foundryIqKnowledgeSourceKind
        FOUNDRY_IQ_STORAGE_CONTAINER_NAME = (Get-OptionalEnvValue 'FOUNDRY_IQ_STORAGE_CONTAINER_NAME' 'documents')
        FOUNDRY_IQ_STORAGE_FOLDER_PATH = (Get-OptionalEnvValue 'FOUNDRY_IQ_STORAGE_FOLDER_PATH')
        FOUNDRY_IQ_IS_ADLS_GEN2 = (Get-OptionalEnvValue 'FOUNDRY_IQ_IS_ADLS_GEN2' 'false')
        FOUNDRY_IQ_CONTENT_EXTRACTION_MODE = (Get-OptionalEnvValue 'FOUNDRY_IQ_CONTENT_EXTRACTION_MODE' 'standard')
        FOUNDRY_IQ_AI_SERVICES_ENDPOINT = (Get-OptionalEnvValue 'FOUNDRY_IQ_AI_SERVICES_ENDPOINT' "https://$foundryName.services.ai.azure.com/")
        FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS = (Get-OptionalEnvValue 'FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS' '["rbacScope"]')
        FOUNDRY_IQ_SEARCH_INDEX_NAME = (Get-OptionalEnvValue 'FOUNDRY_IQ_SEARCH_INDEX_NAME' $ragIndexName)
        FOUNDRY_IQ_SEMANTIC_CONFIGURATION_NAME = (Get-OptionalEnvValue 'FOUNDRY_IQ_SEMANTIC_CONFIGURATION_NAME' 'semantic-config')
        FOUNDRY_IQ_FILTER_ADD_ON_ENABLED = (Get-OptionalEnvValue 'FOUNDRY_IQ_FILTER_ADD_ON_ENABLED' 'false')
        FOUNDRY_IQ_SECURITY_FIELD_NAME = (Get-OptionalEnvValue 'FOUNDRY_IQ_SECURITY_FIELD_NAME' 'metadata_security_id')
        FOUNDRY_IQ_MAX_OUTPUT_DOCUMENTS = (Get-OptionalEnvValue 'FOUNDRY_IQ_MAX_OUTPUT_DOCUMENTS')
        FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED = (Get-OptionalEnvValue 'FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED' 'false')
        FOUNDRY_IQ_CONVERSATION_KNOWLEDGE_SOURCE_NAME = $foundryIqConversationKnowledgeSourceName
        # Work IQ and Fabric IQ knowledge-source passthrough keys. Defaults
        # match config/search/search.settings.j2 (opt-in via `*_ENABLED=true`
        # plus the required identifiers). Seeding them here so a fresh
        # provision registers the keys with default values under the
        # agent-lz label, and operators can flip the flags from the App
        # Configuration blade without having to know the exact key names.
        WORK_IQ_ENABLED = (Get-OptionalEnvValue 'WORK_IQ_ENABLED' 'false')
        WORK_IQ_KNOWLEDGE_SOURCE_NAME = (Get-OptionalEnvValue 'WORK_IQ_KNOWLEDGE_SOURCE_NAME' '')
        FABRIC_IQ_ENABLED = (Get-OptionalEnvValue 'FABRIC_IQ_ENABLED' 'false')
        FABRIC_IQ_KNOWLEDGE_SOURCE_NAME = (Get-OptionalEnvValue 'FABRIC_IQ_KNOWLEDGE_SOURCE_NAME' '')
        FABRIC_IQ_WORKSPACE_ID = (Get-OptionalEnvValue 'FABRIC_IQ_WORKSPACE_ID' '')
        FABRIC_IQ_ONTOLOGY_ID = (Get-OptionalEnvValue 'FABRIC_IQ_ONTOLOGY_ID' '')
        FABRIC_DATA_AGENT_ENABLED = (Get-OptionalEnvValue 'FABRIC_DATA_AGENT_ENABLED' 'false')
        FABRIC_DATA_AGENT_KNOWLEDGE_SOURCE_NAME = (Get-OptionalEnvValue 'FABRIC_DATA_AGENT_KNOWLEDGE_SOURCE_NAME' '')
        FABRIC_DATA_AGENT_WORKSPACE_ID = (Get-OptionalEnvValue 'FABRIC_DATA_AGENT_WORKSPACE_ID' '')
        FABRIC_DATA_AGENT_DATA_AGENT_ID = (Get-OptionalEnvValue 'FABRIC_DATA_AGENT_DATA_AGENT_ID' '')
        SHAREPOINT_REMOTE_ENABLED = (Get-OptionalEnvValue 'SHAREPOINT_REMOTE_ENABLED' 'false')
        SHAREPOINT_REMOTE_KNOWLEDGE_SOURCE_NAME = (Get-OptionalEnvValue 'SHAREPOINT_REMOTE_KNOWLEDGE_SOURCE_NAME' '')
        SHAREPOINT_REMOTE_FILTER_EXPRESSION_ADD_ON = (Get-OptionalEnvValue 'SHAREPOINT_REMOTE_FILTER_EXPRESSION_ADD_ON' '')
        ONELAKE_KS_ENABLED = (Get-OptionalEnvValue 'ONELAKE_KS_ENABLED' 'false')
        ONELAKE_KNOWLEDGE_SOURCE_NAME = (Get-OptionalEnvValue 'ONELAKE_KNOWLEDGE_SOURCE_NAME' '')
        ONELAKE_WORKSPACE_ID = (Get-OptionalEnvValue 'ONELAKE_WORKSPACE_ID' '')
        ONELAKE_LAKEHOUSE_ID = (Get-OptionalEnvValue 'ONELAKE_LAKEHOUSE_ID' '')
        SHAREPOINT_INDEXED_ENABLED = (Get-OptionalEnvValue 'SHAREPOINT_INDEXED_ENABLED' 'false')
        SHAREPOINT_INDEXED_KNOWLEDGE_SOURCE_NAME = (Get-OptionalEnvValue 'SHAREPOINT_INDEXED_KNOWLEDGE_SOURCE_NAME' '')
        SHAREPOINT_INDEXED_INDEX_NAME = (Get-OptionalEnvValue 'SHAREPOINT_INDEXED_INDEX_NAME' '')
        SHAREPOINT_INDEXED_SITE_URL = (Get-OptionalEnvValue 'SHAREPOINT_INDEXED_SITE_URL' '')
        SHAREPOINT_INDEXED_TENANT_ID = (Get-OptionalEnvValue 'SHAREPOINT_INDEXED_TENANT_ID' '')
        # Web grounding (Grounding with Bing) knowledge-source passthrough
        # keys. Opt-in via WEB_GROUNDING_ENABLED=true plus a knowledge
        # source name. Public data, no ACL, no OBO. Allowed/blocked
        # domain lists are optional and comma-separated.
        WEB_GROUNDING_ENABLED = (Get-OptionalEnvValue 'WEB_GROUNDING_ENABLED' 'false')
        WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME = (Get-OptionalEnvValue 'WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME' '')
        WEB_GROUNDING_ALLOWED_DOMAINS = (Get-OptionalEnvValue 'WEB_GROUNDING_ALLOWED_DOMAINS' '')
        WEB_GROUNDING_BLOCKED_DOMAINS = (Get-OptionalEnvValue 'WEB_GROUNDING_BLOCKED_DOMAINS' '')
        # Generic MCP Server knowledge source passthrough keys (preview).
        # Opt-in via FOUNDRY_IQ_MCP_ENABLED=true plus at least one source in
        # FOUNDRY_IQ_MCP_SOURCES_JSON (a JSON array; see
        # docs/howto_grounding_mcp_server.md for the schema). Disabled by
        # default. No secrets belong in FOUNDRY_IQ_MCP_SOURCES_JSON or in
        # App Configuration. queryHeaders may contain only managed identity
        # or OBO scopes, Key Vault secret names, or explicit none metadata;
        # the compatible orchestrator resolves values at request time.
        # FOUNDRY_IQ_MCP_TRUSTED_HOSTS is a
        # comma-separated allowlist of exact hostnames the provisioning
        # script requires an MCP serverURL to match before it will
        # register the source.
        FOUNDRY_IQ_MCP_ENABLED = if ($mcpEnabled) { 'true' } else { 'false' }
        FOUNDRY_IQ_MCP_SOURCES_JSON = $mcpSourcesJson
        FOUNDRY_IQ_MCP_REASONING_EFFORT = $mcpReasoningEffort
        FOUNDRY_IQ_MCP_TRUSTED_HOSTS = $mcpTrustedHosts
        FOUNDRY_IQ_MCP_LOG_TOOL_ARGUMENTS = $mcpLogToolArguments
        NETWORK_ISOLATION = (Get-OptionalEnvValue 'NETWORK_ISOLATION' 'false')
        USE_UAI = (Get-OptionalEnvValue 'USE_UAI' 'false')
        USE_CAPP_API_KEY = (Get-OptionalEnvValue 'USE_CAPP_API_KEY' 'false')
        LOG_LEVEL = 'INFO'
        ENABLE_CONSOLE_LOGGING = 'true'
        RELEASE = $release
        APPLICATIONINSIGHTS_CONNECTION_STRING = $appInsightsConnectionString
        APPLICATIONINSIGHTS__INSTRUMENTATIONKEY = $appInsightsInstrumentationKey

        KEY_VAULT_RESOURCE_ID = $keyVaultResourceId
        STORAGE_ACCOUNT_RESOURCE_ID = $storageResourceId
        APP_INSIGHTS_RESOURCE_ID = $appInsightsResourceId
        LOG_ANALYTICS_RESOURCE_ID = $logAnalyticsResourceId
        CONTAINER_ENV_RESOURCE_ID = $containerEnvResourceId
        AI_FOUNDRY_ACCOUNT_RESOURCE_ID = $foundryResourceId
        AI_FOUNDRY_PROJECT_RESOURCE_ID = $foundryProjectResourceId
        SEARCH_SERVICE_UAI_RESOURCE_ID = $searchServiceUaiResourceId
        KNOWLEDGE_BASE_CONNECTION_ID = $knowledgeBaseConnectionId
        SEARCH_SERVICE_RESOURCE_ID = $searchResourceId
        AZURE_SPEECH_RESOURCE_ID = (Get-OptionalEnvValue 'AZURE_SPEECH_RESOURCE_ID')
        COSMOS_DB_ACCOUNT_RESOURCE_ID = $cosmosResourceId

        AI_FOUNDRY_ACCOUNT_NAME = $foundryName
        AI_FOUNDRY_PROJECT_NAME = $foundryProjectName
        AI_FOUNDRY_STORAGE_ACCOUNT_NAME = $foundryStorageName
        APP_CONFIG_NAME = $appConfigName
        APP_INSIGHTS_NAME = $appInsightsName
        CONTAINER_ENV_NAME = $containerEnvName
        CONTAINER_REGISTRY_NAME = $acrName
        CONTAINER_REGISTRY_LOGIN_SERVER = "$acrName.azurecr.io"
        DATABASE_ACCOUNT_NAME = $cosmosName
        DATABASE_NAME = $databaseName
        SEARCH_SERVICE_NAME = $searchName
        AZURE_SPEECH_RESOURCE_NAME = (Get-OptionalEnvValue 'AZURE_SPEECH_RESOURCE_NAME')
        AZURE_SPEECH_REGION = (Get-OptionalEnvValue 'AZURE_SPEECH_REGION')
        STORAGE_ACCOUNT_NAME = $storageName

        DEPLOY_APP_CONFIG = (Get-OptionalEnvValue 'DEPLOY_APP_CONFIG' 'true')
        DEPLOY_KEY_VAULT = (Get-OptionalEnvValue 'DEPLOY_KEY_VAULT' 'true')
        DEPLOY_LOG_ANALYTICS = (Get-OptionalEnvValue 'DEPLOY_LOG_ANALYTICS' 'true')
        DEPLOY_APP_INSIGHTS = (Get-OptionalEnvValue 'DEPLOY_APP_INSIGHTS' 'true')
        DEPLOY_SEARCH_SERVICE = (Get-OptionalEnvValue 'DEPLOY_SEARCH_SERVICE' 'true')
        DEPLOY_SPEECH_SERVICE = (Get-OptionalEnvValue 'DEPLOY_SPEECH_SERVICE' 'false')
        DEPLOY_STORAGE_ACCOUNT = (Get-OptionalEnvValue 'DEPLOY_STORAGE_ACCOUNT' 'true')
        DEPLOY_COSMOS_DB = "$cosmosEnabled".ToLowerInvariant()
        DEPLOY_CONTAINER_APPS = (Get-OptionalEnvValue 'DEPLOY_CONTAINER_APPS' 'true')
        DEPLOY_CONTAINER_REGISTRY = (Get-OptionalEnvValue 'DEPLOY_CONTAINER_REGISTRY' 'true')
        DEPLOY_CONTAINER_ENV = (Get-OptionalEnvValue 'DEPLOY_CONTAINER_ENV' 'true')

        KEY_VAULT_URI = "https://$keyVaultName.vault.azure.net/"
        STORAGE_BLOB_ENDPOINT = "https://$storageName.blob.core.windows.net/"
        AI_FOUNDRY_ACCOUNT_ENDPOINT = "https://$foundryName.cognitiveservices.azure.com/"
        AI_FOUNDRY_PROJECT_ENDPOINT = "https://$foundryName.services.ai.azure.com/api/projects/$foundryProjectName"
        SEARCH_SERVICE_QUERY_ENDPOINT = "https://$searchName.search.windows.net"
        KNOWLEDGE_BASE_ENDPOINT = $knowledgeBaseEndpoint
        AZURE_SPEECH_ENDPOINT = (Get-OptionalEnvValue 'AZURE_SPEECH_ENDPOINT')
        COSMOS_DB_ENDPOINT = if ($cosmosEnabled) { "https://$cosmosName.documents.azure.com:443/" } else { '' }

        SEARCH_CONNECTION_ID = ''
        KNOWLEDGE_BASE_NAME = $effectiveKnowledgeBaseName
        BING_CONNECTION_ID = ''
        CONTAINER_ENV_PRINCIPAL_ID = $containerEnvPrincipalId
        SEARCH_SERVICE_PRINCIPAL_ID = $searchPrincipalId

        ORCHESTRATOR_APP_ENDPOINT = if ($orchestratorFqdn) { "https://$orchestratorFqdn" } else { '' }
        FRONTEND_APP_ENDPOINT = "https://$frontendFqdn"
        DATA_INGEST_APP_ENDPOINT = if ($dataIngestFqdn) { "https://$dataIngestFqdn" } else { '' }
        ORCHESTRATOR_APP_NAME = if ($hostedMode) { '' } else { $orchestratorAppName }
        FRONTEND_APP_NAME = $frontendAppName
        DATA_INGEST_APP_NAME = $dataIngestAppName

        CHAT_DEPLOYMENT_NAME = 'chat'
        EMBEDDING_DEPLOYMENT_NAME = 'text-embedding'
        CONVERSATIONS_DATABASE_CONTAINER = if ($cosmosEnabled) { 'conversations' } else { '' }
        DATASOURCES_DATABASE_CONTAINER = if ($cosmosEnabled) { 'datasources' } else { '' }
        PROMPTS_CONTAINER = if ($cosmosEnabled) { 'prompts' } else { '' }
        MCP_CONTAINER = if ($cosmosEnabled) { 'mcp' } else { '' }
        DOCUMENTS_IMAGES_STORAGE_CONTAINER = 'documents-images'
        DOCUMENTS_STORAGE_CONTAINER = 'documents'
        CONVERSATION_CACHE_STORAGE_CONTAINER = 'conversation-cache'
        CONVERSATION_DOCUMENTS_STORAGE_CONTAINER = 'conversation-documents'
        NL2SQL_STORAGE_CONTAINER = 'nl2sql'
        CONTAINER_APPS = (ConvertTo-FlatJsonString $containerApps)
        MODEL_DEPLOYMENTS = (ConvertTo-FlatJsonString $modelDeployments)
    }

    $flatSettings = [ordered]@{}
    foreach ($key in $settings.Keys) {
        $value = $settings[$key]
        $flatSettings[$key] = if ($null -eq $value) { '' } else { "$value" }
    }
    foreach ($key in $flatSettings.Keys) {
        Set-Item -Path "Env:$key" -Value $flatSettings[$key]
    }

    $tempFile = Join-Path $repoRoot ".azure\agentlz-appconfig-$([Guid]::NewGuid().ToString('N')).json"
    try {
        $flatSettings | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $tempFile -Encoding UTF8
        $importOutput = Invoke-NativeCommand {
            az appconfig kv import `
                --endpoint $Endpoint `
                --source file `
                --format json `
                --path $tempFile `
                --label $Label `
                --content-type 'text/plain' `
                --auth-mode login `
                --yes 2>&1
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to import Agent Landing Zone App Configuration settings: $importOutput"
            exit 1
        }
    } finally {
        Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
    }

    Write-Host "✅ Agent Landing Zone App Configuration populated ($($flatSettings.Count) keys)."
}

Set-AgentLzAppConfiguration -Endpoint (Get-RequiredEnvValue 'APP_CONFIG_ENDPOINT') -Label 'agent-lz'
Invoke-PythonModule -ModuleName 'config.deployment.appconfig'
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to publish Agent Landing Zone deployment-mode App Configuration settings."
    exit $LASTEXITCODE
}

#-------------------------------------------------------------------------------
# Setup Python environment
#-------------------------------------------------------------------------------
Write-Host "🐍 Checking Python venv support..."
Invoke-NativeCommand { & python -c "import venv" 2>$null }
$venvSupported = ($LASTEXITCODE -eq 0)
if ($venvSupported) {
    Write-Host "📦 Creating temporary venv..."
    Invoke-NativeCommand { python -m venv --without-pip config/.venv_temp }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # Activate the venv
    & config/.venv_temp/Scripts/Activate.ps1

    Write-Host "⬇️ Manually bootstrapping pip..."
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -UseBasicParsing |
        Select-Object -ExpandProperty Content |
        & python
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "⚠️ Python venv is unavailable; using the current Python interpreter and site-packages."
    Write-Host "   This matches the AI Landing Zone jumpbox Python contract used by other solution accelerators."
    Invoke-NativeCommand { & python -m pip --version }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Python pip is required for post-provisioning but is not available on the selected interpreter."
        exit 1
    }
}

Write-Host "⬇️ Installing requirements..."
Invoke-NativeCommand { & python -m pip install --upgrade pip }
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Invoke-NativeCommand { & python -m pip install -r config/requirements.txt }
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

#-------------------------------------------------------------------------------
# Application definition: placeholder plan for containerapp components only
# (from config.appdefinition effective_components), capability-profile roles,
# then platform outputs. No application image is built during provision.
#-------------------------------------------------------------------------------
Write-Host "📦 Checking placeholder Container Apps for the application definition..."
Invoke-PythonModule -ModuleName 'config.deployment.existing_images'
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to plan placeholder Container Apps for the application definition."
    exit $LASTEXITCODE
}
Write-Host "🔐 Assigning capability-profile roles to component identities..."
Invoke-PythonModule -ModuleName 'config.appdefinition' -Arguments @('--assign-roles')
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to assign capability-profile roles to component identities."
    exit $LASTEXITCODE
}
Write-Host "📤 Publishing platform outputs (AGENTLZ_PLATFORM_OUTPUTS)..."
Invoke-PythonModule -ModuleName 'config.deployment.outputs'
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to publish platform outputs to App Configuration."
    exit $LASTEXITCODE
}

#-------------------------------------------------------------------------------
# 1) Governance and audit configuration
#-------------------------------------------------------------------------------
if (-not $missing.Contains('APP_CONFIG_ENDPOINT')) {
    Write-Host "`n🔐 Governance and audit configuration..."
    Write-Host "🚀 Running config.governance.setup..."
    Invoke-PythonModule -ModuleName 'config.governance.setup'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "✅ Governance and audit configuration finished."
} else {
    Write-Host "⏭️  Skipping governance setup (missing APP_CONFIG_ENDPOINT)."
}

#-------------------------------------------------------------------------------
# 2) Hosted conversation continuity
#-------------------------------------------------------------------------------
if (-not $missing.Contains('APP_CONFIG_ENDPOINT')) {
    Write-Host "`n🔐 Publishing fail-closed delegated continuity defaults..."
    Write-Host "🚀 Running config.continuity.setup..."
    Invoke-PythonModule -ModuleName 'config.continuity.setup'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "✅ Fail-closed delegated continuity defaults published."
} else {
    Write-Host "⏭️  Skipping hosted continuity setup (missing APP_CONFIG_ENDPOINT)."
}

#-------------------------------------------------------------------------------
# 3) AI Foundry Setup
#-------------------------------------------------------------------------------
if (-not $missing.Contains('APP_CONFIG_ENDPOINT')) {
    Write-Host "`n📑 AI Foundry Setup..."
    Write-Host "🚀 Running config.aifoundry.setup..."
    Invoke-PythonModule -ModuleName 'config.aifoundry.setup'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "✅ AI Foundry setup script finished."
} else {
    Write-Host "⏭️  Skipping AI Foundry setup (missing APP_CONFIG_ENDPOINT)."
}

#-------------------------------------------------------------------------------
# 4) Container Apps Setup
#-------------------------------------------------------------------------------
if (-not $missing.Contains('APP_CONFIG_ENDPOINT')) {
    Write-Host "`n🔍 ContainerApp setup..."
    Write-Host "🚀 Running config.containerapps.setup..."
    Invoke-PythonModule -ModuleName 'config.containerapps.setup'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "✅ Container Apps setup script finished."
} else {
    Write-Host "⏭️  Skipping Container Apps setup (missing APP_CONFIG_ENDPOINT)."
}

#-------------------------------------------------------------------------------
# 5) AI Search Setup
#-------------------------------------------------------------------------------
if (-not $missing.Contains('APP_CONFIG_ENDPOINT')) {
    Write-Host "🔍 AI Search setup..."
    Write-Host "🚀 Running config.search.setup..."
    Invoke-PythonModule -ModuleName 'config.search.setup'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "✅ Search setup script finished."
} else {
    Write-Host "⏭️  Skipping Search setup (missing APP_CONFIG_ENDPOINT)."
}

#-------------------------------------------------------------------------------
# 6) Administrative panel Cosmos RBAC (issue #611, ADR-0004)
#-------------------------------------------------------------------------------
if (-not $missing.Contains('APP_CONFIG_ENDPOINT')) {
    Write-Host "`n🔐 Administrative panel Cosmos RBAC..."
    Write-Host "🚀 Running config.panel.setup..."
    Invoke-PythonModule -ModuleName 'config.panel.setup'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "✅ Administrative panel Cosmos RBAC finished (no-op unless DEPLOY_ADMINISTRATIVE_PANEL=true)."
} else {
    Write-Host "⏭️  Skipping administrative panel Cosmos RBAC (missing APP_CONFIG_ENDPOINT)."
}

#-------------------------------------------------------------------------------
# Cleaning up
#-------------------------------------------------------------------------------
# Write-Host "`n🧹 Cleaning Python environment up..."
# if (Get-Command deactivate -ErrorAction SilentlyContinue) { deactivate }
# # Try to stop any python processes that reference the temporary venv to avoid file locks
# $venvPattern = "config\\.venv_temp"
# try {
#     $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match $venvPattern) }
# } catch {
#     # Fallback if Get-CimInstance isn't available for some reason
#     $procs = @()
# }

# if ($procs -and $procs.Count -gt 0) {
#     Write-Host "Stopping processes referencing venv:"
#     foreach ($p in $procs) {
#         Write-Host "  Stopping pid $($p.ProcessId) - $($p.Name)"
#         try { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
#     }
#     Start-Sleep -Seconds 1
# }

# # Retry removal with exponential backoff to handle transient locks
# $maxRetries = 5
# for ($i = 1; $i -le $maxRetries; $i++) {
#     try {
#         Remove-Item -Recurse -Force config/.venv_temp -ErrorAction Stop
#         Write-Host "Removed venv directory."
#         break
#     } catch {
#         if ($i -eq $maxRetries) {
#             Write-Host "⚠️ Failed to remove venv after $maxRetries attempts: $($_.Exception.Message)"
#         } else {
#             Write-Host ("Retry {0}/{1}: waiting and retrying..." -f $i, $maxRetries)
#             Start-Sleep -Seconds (2 * $i)
#         }
#     }
# }

Write-Host "`n✅ postProvisioning completed."
