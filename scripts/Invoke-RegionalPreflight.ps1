<#
.SYNOPSIS
    Agent Landing Zone regional readiness preflight for azd provision.

.DESCRIPTION
    Performs read-only Azure checks before long-running provisioning starts.
    The script intentionally reports only deterministic blockers as FAIL.
    Capacity signals that Azure cannot guarantee before deployment are WARN.

.PARAMETER ProjectRoot
    Agent Landing Zone repository root. Defaults to the parent folder of this script.

.PARAMETER ParameterFile
    Effective main.parameters.json file to evaluate. Defaults to the root
    main.parameters.json.

.PARAMETER SubscriptionId
    Subscription to check. Defaults to AZURE_SUBSCRIPTION_ID from azd env, then
    the current az account.

.PARAMETER SkipAzureCliChecks
    Skip checks that call Azure CLI. Useful for parser/offline validation.
#>

[CmdletBinding()]
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$ParameterFile,
    [string]$SubscriptionId,
    [switch]$SkipAzureCliChecks
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path (Join-Path (Join-Path (Split-Path -Parent $PSScriptRoot) 'infra') 'scripts') 'ModelQuota.ps1')

$script:FailureCount = 0
$script:WarningCount = 0
$script:ProviderCache = @{}

function Write-PreflightCheck {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('PASS', 'WARN', 'FAIL')][string]$Status,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Message
    )

    if ($Status -eq 'FAIL') { $script:FailureCount++ }
    if ($Status -eq 'WARN') { $script:WarningCount++ }
    Write-Host "$Status $Name - $Message"
}

function Test-Truthy {
    param([AllowNull()]$Value)

    if ($null -eq $Value) { return $false }
    if ($Value -is [bool]) { return $Value }
    $text = "$Value".Trim()
    return $text -match '^(1|true|t|yes|y)$'
}

function Import-AzdEnvironment {
    if (-not (Get-Command azd -ErrorAction SilentlyContinue)) {
        Write-PreflightCheck -Status WARN -Name 'azd-env' -Message 'azd CLI not found; using current process environment only.'
        return
    }

    $lines = @(& azd env get-values 2>$null)
    if ($LASTEXITCODE -ne 0 -or $lines.Count -eq 0) {
        Write-PreflightCheck -Status WARN -Name 'azd-env' -Message 'azd env get-values returned no values; using current process environment only.'
        return
    }

    foreach ($line in $lines) {
        if ($line -match '^([^=]+)=(.*)$') {
            $name = $matches[1]
            $value = $matches[2] -replace '^"|"$'
            Set-Item -Path "Env:$name" -Value $value
        }
    }
    Write-PreflightCheck -Status PASS -Name 'azd-env' -Message 'loaded current azd environment values.'
}

function Resolve-TemplateValue {
    param([AllowNull()]$Value)

    if ($null -eq $Value) { return $null }
    if ($Value -isnot [string]) { return $Value }

    $text = $Value.Trim()
    if ($text -match '^\$\{([^}=]+)(=(.*))?\}$') {
        $name = $matches[1]
        $default = ''
        if ($matches.Count -ge 4) { $default = $matches[3] }
        $envValue = [Environment]::GetEnvironmentVariable($name)
        if ([string]::IsNullOrWhiteSpace($envValue)) { return $default }
        return $envValue
    }

    return $Value
}

function Get-ParameterValue {
    param(
        [Parameter(Mandatory = $true)]$Parameters,
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()]$DefaultValue = $null
    )

    $property = $Parameters.PSObject.Properties[$Name]
    if ($null -eq $property) { return $DefaultValue }

    $entry = $property.Value
    if ($null -eq $entry) { return $DefaultValue }

    $valueProperty = $entry.PSObject.Properties['value']
    if ($null -eq $valueProperty) { return $DefaultValue }

    $resolved = Resolve-TemplateValue $valueProperty.Value
    if ($null -eq $resolved) { return $DefaultValue }
    if ($resolved -is [string] -and [string]::IsNullOrWhiteSpace($resolved)) { return $DefaultValue }
    if ($resolved -is [string] -and $resolved.Trim() -eq 'null') { return $DefaultValue }
    return $resolved
}

function Get-DeploymentFlag {
    param(
        [Parameter(Mandatory = $true)]$Parameters,
        [Parameter(Mandatory = $true)][string]$Name,
        [bool]$DefaultValue
    )

    $value = Get-ParameterValue -Parameters $Parameters -Name $Name -DefaultValue $DefaultValue
    return Test-Truthy $value
}

function Get-NormalizedLocation {
    param([AllowNull()][string]$Location)

    if ([string]::IsNullOrWhiteSpace($Location)) { return '' }
    return ($Location -replace '\s+', '').ToLowerInvariant()
}

function Invoke-AzJson {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )

    if ($SkipAzureCliChecks) { return $null }

    $output = @(& az @Arguments --only-show-errors -o json 2>&1)
    $exitCode = $LASTEXITCODE
    $text = ($output -join [Environment]::NewLine).Trim()
    if ($exitCode -ne 0) {
        if ($AllowFailure) { return @{ failed = $true; error = $text } }
        throw "az $($Arguments -join ' ') failed: $text"
    }
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    return $text | ConvertFrom-Json
}

function Get-Provider {
    param([Parameter(Mandatory = $true)][string]$Namespace)

    if ($script:ProviderCache.ContainsKey($Namespace)) { return $script:ProviderCache[$Namespace] }

    $args = @('provider', 'show', '--namespace', $Namespace, '--expand', 'resourceTypes/locations')
    if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) { $args += @('--subscription', $SubscriptionId) }
    $provider = Invoke-AzJson -Arguments $args
    $script:ProviderCache[$Namespace] = $provider
    return $provider
}

function Test-ProviderRegistration {
    param([Parameter(Mandatory = $true)][string]$Namespace)

    if ($SkipAzureCliChecks) {
        Write-PreflightCheck -Status WARN -Name "provider:$Namespace" -Message 'skipped because SkipAzureCliChecks is set.'
        return
    }

    try {
        $provider = Get-Provider -Namespace $Namespace
        if ($provider.registrationState -eq 'Registered') {
            Write-PreflightCheck -Status PASS -Name "provider:$Namespace" -Message 'registered.'
        } else {
            Write-PreflightCheck -Status FAIL -Name "provider:$Namespace" -Message "registration state is '$($provider.registrationState)'."
        }
    } catch {
        Write-PreflightCheck -Status FAIL -Name "provider:$Namespace" -Message "could not read provider registration: $($_.Exception.Message)"
    }
}

function Test-ProviderLocation {
    param(
        [Parameter(Mandatory = $true)][string]$Namespace,
        [Parameter(Mandatory = $true)][string]$ResourceType,
        [Parameter(Mandatory = $true)][string]$Location,
        [Parameter(Mandatory = $true)][string]$DisplayName
    )

    if ($SkipAzureCliChecks) {
        Write-PreflightCheck -Status WARN -Name $DisplayName -Message 'provider/location support skipped because SkipAzureCliChecks is set.'
        return
    }

    if ([string]::IsNullOrWhiteSpace($Location)) {
        Write-PreflightCheck -Status FAIL -Name $DisplayName -Message 'location is empty.'
        return
    }

    try {
        $provider = Get-Provider -Namespace $Namespace
        $resource = @($provider.resourceTypes | Where-Object { $_.resourceType -eq $ResourceType } | Select-Object -First 1)
        if ($resource.Count -eq 0) {
            Write-PreflightCheck -Status WARN -Name $DisplayName -Message "resource type '$Namespace/$ResourceType' was not returned by Azure provider metadata."
            return
        }

        $target = Get-NormalizedLocation $Location
        $supported = @($resource[0].locations | ForEach-Object { Get-NormalizedLocation $_ }) -contains $target
        if ($supported) {
            Write-PreflightCheck -Status PASS -Name $DisplayName -Message "provider supports $Location."
        } else {
            Write-PreflightCheck -Status FAIL -Name $DisplayName -Message "provider does not list $Location for $Namespace/$ResourceType."
        }
    } catch {
        Write-PreflightCheck -Status FAIL -Name $DisplayName -Message "could not verify provider location: $($_.Exception.Message)"
    }
}

function Get-QuotaData {
    param(
        [Parameter(Mandatory = $true)][string]$ProviderNamespace,
        [Parameter(Mandatory = $true)][string]$Location
    )

    $scope = "/subscriptions/$SubscriptionId/providers/$ProviderNamespace/locations/$Location"
    $usage = Invoke-AzJson -Arguments @('quota', 'usage', 'list', '--scope', $scope, '--subscription', $SubscriptionId) -AllowFailure
    if ($usage -is [hashtable] -and $usage.failed) {
        return @{ supported = $false; error = $usage.error }
    }

    $limits = Invoke-AzJson -Arguments @('quota', 'list', '--scope', $scope, '--subscription', $SubscriptionId) -AllowFailure
    if ($limits -is [hashtable] -and $limits.failed) {
        return @{ supported = $false; error = $limits.error }
    }

    return @{ supported = $true; usage = @($usage); limits = @($limits) }
}

function Get-QuotaItemName {
    param([Parameter(Mandatory = $true)]$Item)

    if ($Item.PSObject.Properties['name'] -and $Item.name -is [string]) { return $Item.name }
    $nameProperty = $Item.PSObject.Properties['properties']
    if ($nameProperty -and $Item.properties.PSObject.Properties['name']) {
        return $Item.properties.name.value
    }
    return ''
}

function Get-QuotaUsageValue {
    param([Parameter(Mandatory = $true)]$Item)

    if ($Item.PSObject.Properties['properties'] -and $Item.properties.PSObject.Properties['usages']) {
        return [double]$Item.properties.usages.value
    }
    return $null
}

function Get-QuotaLimitValue {
    param([Parameter(Mandatory = $true)]$Item)

    if ($Item.PSObject.Properties['properties'] -and $Item.properties.PSObject.Properties['limit']) {
        return [double]$Item.properties.limit.value
    }
    return $null
}

function Find-QuotaItem {
    param(
        [Parameter(Mandatory = $true)]$Items,
        [Parameter(Mandatory = $true)][string[]]$Names
    )

    foreach ($name in $Names) {
        $match = @($Items | Where-Object { (Get-QuotaItemName $_) -eq $name } | Select-Object -First 1)
        if ($match.Count -gt 0) { return $match[0] }
    }
    return $null
}

function Test-QuotaRemaining {
    param(
        [Parameter(Mandatory = $true)][string]$CheckName,
        [Parameter(Mandatory = $true)]$QuotaData,
        [Parameter(Mandatory = $true)][string[]]$Names,
        [double]$Required = 1
    )

    if (-not $QuotaData.supported) {
        Write-PreflightCheck -Status WARN -Name $CheckName -Message "quota API did not return data: $($QuotaData.error)"
        return
    }

    $usageItem = Find-QuotaItem -Items $QuotaData.usage -Names $Names
    $limitItem = Find-QuotaItem -Items $QuotaData.limits -Names $Names
    if ($null -eq $usageItem -or $null -eq $limitItem) {
        Write-PreflightCheck -Status WARN -Name $CheckName -Message "quota item not found ($($Names -join ', '))."
        return
    }

    $usage = Get-QuotaUsageValue $usageItem
    $limit = Get-QuotaLimitValue $limitItem
    if ($null -eq $usage -or $null -eq $limit) {
        Write-PreflightCheck -Status WARN -Name $CheckName -Message 'quota API returned usage or limit without numeric values.'
        return
    }

    $remaining = $limit - $usage
    if ($remaining -ge $Required) {
        Write-PreflightCheck -Status PASS -Name $CheckName -Message "$remaining of $limit remaining; needs at least $Required."
    } else {
        Write-PreflightCheck -Status FAIL -Name $CheckName -Message "$remaining of $limit remaining; needs at least $Required."
    }
}

function Test-ComputeQuota {
    param(
        [Parameter(Mandatory = $true)][string]$Location,
        [Parameter(Mandatory = $true)][string]$VmSize
    )

    if ($SkipAzureCliChecks) {
        Write-PreflightCheck -Status WARN -Name 'quota:compute' -Message 'skipped because SkipAzureCliChecks is set.'
        return
    }

    $quota = Get-QuotaData -ProviderNamespace 'Microsoft.Compute' -Location $Location
    Test-QuotaRemaining -CheckName 'quota:compute:regional-vcpus' -QuotaData $quota -Names @('cores', 'standardCores') -Required 1

    $skuArgs = @('vm', 'list-skus', '--location', $Location, '--size', $VmSize, '--all')
    if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) { $skuArgs += @('--subscription', $SubscriptionId) }
    $skuResult = Invoke-AzJson -Arguments $skuArgs -AllowFailure
    if ($skuResult -is [hashtable] -and $skuResult.failed) {
        Write-PreflightCheck -Status WARN -Name 'quota:compute:vm-sku' -Message "could not read VM SKU metadata: $($skuResult.error)"
        return
    }

    $sku = @($skuResult | Where-Object { $_.name -eq $VmSize } | Select-Object -First 1)
    if ($sku.Count -eq 0) {
        Write-PreflightCheck -Status FAIL -Name 'quota:compute:vm-sku' -Message "$VmSize is not available in $Location."
        return
    }
    if (@($sku[0].restrictions).Count -gt 0) {
        Write-PreflightCheck -Status FAIL -Name 'quota:compute:vm-sku' -Message "$VmSize has restrictions in $Location."
        return
    }

    $vcpuCapability = @($sku[0].capabilities | Where-Object { $_.name -eq 'vCPUs' } | Select-Object -First 1)
    $requiredVcpus = 1
    if ($vcpuCapability.Count -gt 0) { $requiredVcpus = [double]$vcpuCapability[0].value }

    Write-PreflightCheck -Status PASS -Name 'quota:compute:vm-sku' -Message "$VmSize is available in $Location."
    if ($sku[0].PSObject.Properties['family'] -and -not [string]::IsNullOrWhiteSpace($sku[0].family)) {
        Test-QuotaRemaining -CheckName "quota:compute:$($sku[0].family)" -QuotaData $quota -Names @($sku[0].family) -Required $requiredVcpus
    }
}

function Test-NetworkQuota {
    param([Parameter(Mandatory = $true)][string]$Location)

    if ($SkipAzureCliChecks) {
        Write-PreflightCheck -Status WARN -Name 'quota:network' -Message 'skipped because SkipAzureCliChecks is set.'
        return
    }

    $quota = Get-QuotaData -ProviderNamespace 'Microsoft.Network' -Location $Location
    Test-QuotaRemaining -CheckName 'quota:network:vnets' -QuotaData $quota -Names @('VirtualNetworks') -Required 1
    Test-QuotaRemaining -CheckName 'quota:network:public-ips' -QuotaData $quota -Names @('PublicIPAddresses', 'StandardSkuPublicIpAddresses') -Required 1
    Test-QuotaRemaining -CheckName 'quota:network:nics' -QuotaData $quota -Names @('NetworkInterfaces') -Required 1
}

function Test-ContainerAppsQuota {
    param([Parameter(Mandatory = $true)][string]$Location)

    if ($SkipAzureCliChecks) {
        Write-PreflightCheck -Status WARN -Name 'quota:container-apps' -Message 'skipped because SkipAzureCliChecks is set.'
        return
    }

    $quota = Get-QuotaData -ProviderNamespace 'Microsoft.App' -Location $Location
    Test-QuotaRemaining -CheckName 'quota:container-apps:managed-environments' -QuotaData $quota -Names @('ManagedEnvironmentCount') -Required 1
}

function Test-ContentUnderstandingRegion {
    param([Parameter(Mandatory = $true)][string]$Location)

    $supportedRegions = @(
        'australiaeast',
        'eastus',
        'eastus2',
        'japaneast',
        'northeurope',
        'southcentralus',
        'southeastasia',
        'swedencentral',
        'uksouth',
        'westeurope',
        'westus',
        'westus3'
    )

    $normalized = Get-NormalizedLocation $Location
    if ($supportedRegions -contains $normalized) {
        Write-PreflightCheck -Status PASS -Name 'foundry-iq:content-understanding-region' -Message "Content Understanding supports Foundry resource location $Location."
    } else {
        Write-PreflightCheck -Status FAIL -Name 'foundry-iq:content-understanding-region' -Message "Content Understanding does not support Foundry resource location $Location. Use one of: $($supportedRegions -join ', ')."
    }
}

function Test-ModelReadiness {
    param(
        [Parameter(Mandatory = $true)][string]$Location,
        [Parameter(Mandatory = $true)]$Models
    )

    if ($SkipAzureCliChecks) {
        Write-PreflightCheck -Status WARN -Name 'models' -Message 'model availability and quota skipped because SkipAzureCliChecks is set.'
        return
    }

    $modelList = Invoke-AzJson -Arguments @('cognitiveservices', 'model', 'list', '--location', $Location, '--subscription', $SubscriptionId) -AllowFailure
    if ($modelList -is [hashtable] -and $modelList.failed) {
        Write-PreflightCheck -Status WARN -Name 'models' -Message "could not read model availability: $($modelList.error)"
        return
    }

    $usageList = Invoke-AzJson -Arguments @('cognitiveservices', 'usage', 'list', '--location', $Location, '--subscription', $SubscriptionId) -AllowFailure
    if ($usageList -is [hashtable] -and $usageList.failed) {
        Write-PreflightCheck -Status WARN -Name 'models:quota' -Message "could not read model quota: $($usageList.error)"
        $usageList = @()
    }

    $existing = @(Get-ExistingModelDeployments -Location $Location -SubscriptionId $SubscriptionId -ReadAzureJson {
        param([string[]]$Arguments)
        Invoke-AzJson -Arguments $Arguments -AllowFailure
    } -OnWarning {
        param([string]$Message)
        Write-PreflightCheck -Status WARN -Name 'models:existing-target' -Message $Message
    })
    foreach ($deployment in @($Models)) {
        $model = $deployment.model
        $modelName = $model.name
        $modelVersion = $model.version
        $skuName = $deployment.sku.name
        $checkName = "model:$modelName"
        $available = @($modelList | Where-Object {
            $_.model.name -eq $modelName -and
            ([string]::IsNullOrWhiteSpace($modelVersion) -or $_.model.version -eq $modelVersion) -and
            (@($_.model.skus | Where-Object { $_.name -eq $skuName }).Count -gt 0)
        })

        if ($available.Count -gt 0) {
            Write-PreflightCheck -Status PASS -Name $checkName -Message "$skuName deployment is listed in $Location."
        } else {
            Write-PreflightCheck -Status FAIL -Name $checkName -Message "$modelName $modelVersion with sku $skuName is not listed in $Location."
        }

    }

    try {
        $requests = @(Get-ModelQuotaRequirements -Models $Models -ExistingDeployments $existing)
    } catch {
        Write-PreflightCheck -Status FAIL -Name 'models:quota' -Message $_.Exception.Message
        return
    }
    foreach ($request in $requests) {
        $usageName = $request.QuotaName
        $quota = @($usageList | Where-Object { $_.name.value -eq $usageName } | Select-Object -First 1)
        if ($quota.Count -eq 0) {
            Write-PreflightCheck -Status WARN -Name "models:quota:$usageName" -Message "quota item $usageName was not returned."
            continue
        }

        $remaining = [double]$quota[0].limit - [double]$quota[0].currentValue
        $requested = $request.DesiredCapacity
        $credit = $request.ExistingCredit
        $additional = $request.AdditionalCapacity
        $message = "$remaining quota units remaining; desired $requested, verified existing credit $credit, additional allocation $additional."
        if ($additional -eq 0 -or $remaining -ge $additional) {
            Write-PreflightCheck -Status PASS -Name "models:quota:$usageName" -Message $message
        } else {
            Write-PreflightCheck -Status FAIL -Name "models:quota:$usageName" -Message $message
        }
    }
}

if ([string]::IsNullOrWhiteSpace($ParameterFile)) {
    $ParameterFile = Join-Path $ProjectRoot 'main.parameters.json'
}

Write-Host 'Agent Landing Zone regional preflight'
Import-AzdEnvironment

if (-not (Test-Path $ParameterFile)) {
    Write-PreflightCheck -Status FAIL -Name 'parameters' -Message "parameter file not found: $ParameterFile"
    Write-Host "Result: FAIL ($script:FailureCount fail, $script:WarningCount warn)"
    exit 1
}

$parametersDocument = Get-Content -Path $ParameterFile -Raw | ConvertFrom-Json
$parameters = $parametersDocument.parameters
Write-PreflightCheck -Status PASS -Name 'parameters' -Message "loaded $ParameterFile."

$primaryLocation = Get-ParameterValue -Parameters $parameters -Name 'location'
$aiFoundryLocation = Get-ParameterValue -Parameters $parameters -Name 'aiFoundryLocation' -DefaultValue $primaryLocation
$cosmosLocation = Get-ParameterValue -Parameters $parameters -Name 'cosmosLocation' -DefaultValue $primaryLocation
$searchLocation = Get-ParameterValue -Parameters $parameters -Name 'searchServiceLocation' -DefaultValue $primaryLocation
$speechLocation = Get-ParameterValue -Parameters $parameters -Name 'speechServiceLocation' -DefaultValue $primaryLocation
$privateEndpointLocation = Get-ParameterValue -Parameters $parameters -Name 'privateEndpointLocation' -DefaultValue $primaryLocation

if ([string]::IsNullOrWhiteSpace($primaryLocation)) {
    Write-PreflightCheck -Status FAIL -Name 'regions' -Message 'AZURE_LOCATION is required.'
} else {
    Write-PreflightCheck -Status PASS -Name 'regions' -Message "primary=$primaryLocation; aiFoundry=$aiFoundryLocation; search=$searchLocation; cosmos=$cosmosLocation; speech=$speechLocation; privateEndpoints=$privateEndpointLocation."
}

if ([string]::IsNullOrWhiteSpace($SubscriptionId)) {
    $SubscriptionId = [Environment]::GetEnvironmentVariable('AZURE_SUBSCRIPTION_ID')
}

if ($SkipAzureCliChecks) {
    Write-PreflightCheck -Status WARN -Name 'azure-cli' -Message 'Azure CLI checks skipped by parameter.'
} elseif (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Write-PreflightCheck -Status FAIL -Name 'azure-cli' -Message 'az CLI not found.'
} else {
    try {
        $accountArgs = @('account', 'show')
        if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) { $accountArgs += @('--subscription', $SubscriptionId) }
        $account = Invoke-AzJson -Arguments $accountArgs
        if ([string]::IsNullOrWhiteSpace($SubscriptionId)) { $SubscriptionId = $account.id }
        Write-PreflightCheck -Status PASS -Name 'azure-cli' -Message "authenticated to subscription $SubscriptionId."
    } catch {
        Write-PreflightCheck -Status FAIL -Name 'azure-cli' -Message "could not read Azure account: $($_.Exception.Message)"
    }
}

$deployAiFoundry = Get-DeploymentFlag -Parameters $parameters -Name 'deployAiFoundry' -DefaultValue $true
$deploySearch = Get-DeploymentFlag -Parameters $parameters -Name 'deploySearchService' -DefaultValue $true
$deploySpeech = Get-DeploymentFlag -Parameters $parameters -Name 'deploySpeechService' -DefaultValue $false
$deployCosmos = Get-DeploymentFlag -Parameters $parameters -Name 'deployCosmosDb' -DefaultValue $true
$deployContainerApps = Get-DeploymentFlag -Parameters $parameters -Name 'deployContainerApps' -DefaultValue $true
$deployContainerRegistry = Get-DeploymentFlag -Parameters $parameters -Name 'deployContainerRegistry' -DefaultValue $true
$deployKeyVault = Get-DeploymentFlag -Parameters $parameters -Name 'deployKeyVault' -DefaultValue $true
$deployStorage = Get-DeploymentFlag -Parameters $parameters -Name 'deployStorageAccount' -DefaultValue $true
$deployAppConfig = Get-DeploymentFlag -Parameters $parameters -Name 'deployAppConfig' -DefaultValue $true
$deployLogAnalytics = Get-DeploymentFlag -Parameters $parameters -Name 'deployLogAnalytics' -DefaultValue $true
$deployAppInsights = Get-DeploymentFlag -Parameters $parameters -Name 'deployAppInsights' -DefaultValue $true
$deployVm = Get-DeploymentFlag -Parameters $parameters -Name 'deployVM' -DefaultValue $true
$networkIsolation = Get-DeploymentFlag -Parameters $parameters -Name 'networkIsolation' -DefaultValue $false
# Mirror the landing zone gating: jumpbox, Bastion and NAT are only deployed with network isolation unless explicitly set.
$explicitJumpbox = Get-ParameterValue -Parameters $parameters -Name 'deployJumpbox' -DefaultValue $null
$deployJumpbox = if ($null -ne $explicitJumpbox) { Test-Truthy $explicitJumpbox } else { $deployVm -and $networkIsolation }
$explicitBastion = Get-ParameterValue -Parameters $parameters -Name 'deployBastion' -DefaultValue $null
$deployBastion = if ($null -ne $explicitBastion) { Test-Truthy $explicitBastion } else { $networkIsolation -and $deployJumpbox }
$explicitNatGateway = Get-ParameterValue -Parameters $parameters -Name 'deployNatGateway' -DefaultValue $null
$deployNatGateway = if ($null -ne $explicitNatGateway) { Test-Truthy $explicitNatGateway } else { $networkIsolation -and $deployJumpbox }
$retrievalBackend = Get-ParameterValue -Parameters $parameters -Name 'retrievalBackend' -DefaultValue 'foundry_iq'
$foundryIqPattern = Get-ParameterValue -Parameters $parameters -Name 'foundryIqPattern' -DefaultValue 'azureBlob'
$foundryIqContentExtractionMode = Get-ParameterValue -Parameters $parameters -Name 'foundryIqContentExtractionMode' -DefaultValue 'standard'

$providerNamespaces = [System.Collections.Generic.HashSet[string]]::new()
if ($deployAiFoundry -or $deploySpeech) { [void]$providerNamespaces.Add('Microsoft.CognitiveServices') }
if ($deploySearch) { [void]$providerNamespaces.Add('Microsoft.Search') }
if ($deployCosmos) { [void]$providerNamespaces.Add('Microsoft.DocumentDB') }
if ($deployContainerApps) { [void]$providerNamespaces.Add('Microsoft.App') }
if ($deployContainerRegistry) { [void]$providerNamespaces.Add('Microsoft.ContainerRegistry') }
if ($deployKeyVault) { [void]$providerNamespaces.Add('Microsoft.KeyVault') }
if ($deployStorage) { [void]$providerNamespaces.Add('Microsoft.Storage') }
if ($deployAppConfig) { [void]$providerNamespaces.Add('Microsoft.AppConfiguration') }
if ($deployLogAnalytics) { [void]$providerNamespaces.Add('Microsoft.OperationalInsights') }
if ($deployAppInsights) { [void]$providerNamespaces.Add('Microsoft.Insights') }
if ($networkIsolation -or $deployJumpbox -or $deployBastion -or $deployNatGateway) { [void]$providerNamespaces.Add('Microsoft.Network') }
if ($deployJumpbox) { [void]$providerNamespaces.Add('Microsoft.Compute') }

foreach ($namespace in $providerNamespaces) {
    Test-ProviderRegistration -Namespace $namespace
}

if (-not [string]::IsNullOrWhiteSpace($primaryLocation)) {
    if ($deployAiFoundry) { Test-ProviderLocation -Namespace 'Microsoft.CognitiveServices' -ResourceType 'accounts' -Location $aiFoundryLocation -DisplayName 'location:ai-foundry' }
    if ($deploySpeech) { Test-ProviderLocation -Namespace 'Microsoft.CognitiveServices' -ResourceType 'accounts' -Location $speechLocation -DisplayName 'location:speech' }
    if ($deploySearch) { Test-ProviderLocation -Namespace 'Microsoft.Search' -ResourceType 'searchServices' -Location $searchLocation -DisplayName 'location:ai-search' }
    if ($deployCosmos) { Test-ProviderLocation -Namespace 'Microsoft.DocumentDB' -ResourceType 'databaseAccounts' -Location $cosmosLocation -DisplayName 'location:cosmos' }
    if ($deployContainerApps) {
        Test-ProviderLocation -Namespace 'Microsoft.App' -ResourceType 'managedEnvironments' -Location $primaryLocation -DisplayName 'location:container-app-env'
        Test-ProviderLocation -Namespace 'Microsoft.App' -ResourceType 'containerApps' -Location $primaryLocation -DisplayName 'location:container-apps'
    }
    if ($deployContainerRegistry) { Test-ProviderLocation -Namespace 'Microsoft.ContainerRegistry' -ResourceType 'registries' -Location $primaryLocation -DisplayName 'location:container-registry' }
    if ($deployKeyVault) { Test-ProviderLocation -Namespace 'Microsoft.KeyVault' -ResourceType 'vaults' -Location $primaryLocation -DisplayName 'location:key-vault' }
    if ($deployStorage) { Test-ProviderLocation -Namespace 'Microsoft.Storage' -ResourceType 'storageAccounts' -Location $primaryLocation -DisplayName 'location:storage' }
    if ($deployAppConfig) { Test-ProviderLocation -Namespace 'Microsoft.AppConfiguration' -ResourceType 'configurationStores' -Location $primaryLocation -DisplayName 'location:app-configuration' }
    if ($deployLogAnalytics) { Test-ProviderLocation -Namespace 'Microsoft.OperationalInsights' -ResourceType 'workspaces' -Location $primaryLocation -DisplayName 'location:log-analytics' }
    if ($deployAppInsights) { Test-ProviderLocation -Namespace 'Microsoft.Insights' -ResourceType 'components' -Location $primaryLocation -DisplayName 'location:application-insights' }
    if ($networkIsolation -or $deployJumpbox -or $deployBastion -or $deployNatGateway) {
        Test-ProviderLocation -Namespace 'Microsoft.Network' -ResourceType 'virtualNetworks' -Location $primaryLocation -DisplayName 'location:vnet'
        Test-ProviderLocation -Namespace 'Microsoft.Network' -ResourceType 'privateEndpoints' -Location $privateEndpointLocation -DisplayName 'location:private-endpoints'
    }
}

if (-not $SkipAzureCliChecks -and -not [string]::IsNullOrWhiteSpace($SubscriptionId) -and -not [string]::IsNullOrWhiteSpace($primaryLocation)) {
    if ($deployJumpbox) {
        $vmSize = Get-ParameterValue -Parameters $parameters -Name 'vmSize' -DefaultValue 'Standard_D2s_v3'
        Test-ComputeQuota -Location $primaryLocation -VmSize $vmSize
    }
    if ($networkIsolation -or $deployJumpbox -or $deployBastion -or $deployNatGateway) {
        Test-NetworkQuota -Location $primaryLocation
    }
    if ($deployContainerApps) {
        Test-ContainerAppsQuota -Location $primaryLocation
    }
}

if ($deploySearch) {
    Write-PreflightCheck -Status WARN -Name 'capacity:ai-search' -Message 'regional live capacity cannot be guaranteed before deployment; Azure may still return InsufficientResourcesAvailable.'
}
if ($deployCosmos) {
    Write-PreflightCheck -Status WARN -Name 'capacity:cosmos' -Message 'regional live capacity cannot be guaranteed before deployment; Azure may still return ServiceUnavailable or capacity errors.'
}

if ($deployAiFoundry) {
    if ($retrievalBackend -eq 'foundry_iq' -and $foundryIqPattern -ne 'searchIndex' -and $foundryIqContentExtractionMode -eq 'standard') {
        Test-ContentUnderstandingRegion -Location $aiFoundryLocation
    }

    $models = Get-ParameterValue -Parameters $parameters -Name 'modelDeploymentList' -DefaultValue @()
    if (@($models).Count -gt 0) {
        Test-ModelReadiness -Location $aiFoundryLocation -Models $models
    } else {
        Write-PreflightCheck -Status WARN -Name 'models' -Message 'modelDeploymentList is empty; no model readiness checks were run.'
    }
}

if ($script:FailureCount -gt 0) {
    Write-Host "Result: FAIL ($script:FailureCount fail, $script:WarningCount warn)"
    exit 1
}

if ($script:WarningCount -gt 0) {
    Write-Host "Result: WARN (0 fail, $script:WarningCount warn)"
    exit 0
}

Write-Host 'Result: PASS (0 fail, 0 warn)'
exit 0
