<#
.SYNOPSIS
    Smoke tests for scripts/Invoke-PreflightChecks.ps1.

.DESCRIPTION
    Synthetic-input tests that exercise the deterministic checks (Test-Topology,
    Test-HostedAgentConfiguration, Test-AllowedIpRanges, Test-LocalCidrSanity)
    without touching Azure.

    Usage:
        pwsh ./tests/scripts/Invoke-PreflightChecks.Tests.ps1

    Exits non-zero on any test failure.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

# Dot-source the script in test mode by creating a temporary stub that re-exports
# its functions. The real script ends with an `exit` so we cannot dot-source it
# directly. Instead, we use AST parsing to extract the function definitions and
# re-execute them in this scope.

$scriptPath = Join-Path -Path (Split-Path -Parent $PSScriptRoot) -ChildPath '..\scripts\Invoke-PreflightChecks.ps1'
$scriptPath = (Resolve-Path -Path $scriptPath).Path
. (Join-Path (Split-Path -Parent $scriptPath) 'ModelQuota.ps1')
$raw = Get-Content -Path $scriptPath -Raw
$ast = [System.Management.Automation.Language.Parser]::ParseInput($raw, [ref]$null, [ref]$null)

$funcs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
foreach ($f in $funcs) {
    Invoke-Expression $f.Extent.Text
}

$script:TestFailures = 0
$script:TestsRun = 0

function Assert-True {
    param([Parameter(Mandatory)] [string]$Name, [Parameter(Mandatory)] [bool]$Condition, [string]$Reason = '')
    $script:TestsRun++
    if ($Condition) {
        Write-Host ("  [PASS] {0}" -f $Name) -ForegroundColor Green
    }
    else {
        $suffix = if ($Reason) { " - $Reason" } else { '' }
        Write-Host ("  [FAIL] {0}{1}" -f $Name, $suffix) -ForegroundColor Red
        $script:TestFailures++
    }
}

function Reset-Findings {
    $script:Findings = [System.Collections.Generic.List[pscustomobject]]::new()
}

function Test-FindingPresent {
    param([string]$Code)
    return @($script:Findings | Where-Object Code -eq $Code).Count -gt 0
}

function Test-FindingAbsent {
    param([string]$Code)
    return @($script:Findings | Where-Object Code -eq $Code).Count -eq 0
}

# --------------------------------------------------------------------------
Write-Host 'CIDR helpers' -ForegroundColor Cyan

$r = Get-CidrRange -Cidr '192.168.0.0/24'
Assert-True 'Get-CidrRange 192.168.0.0/24 start' ($r.Start -eq (ConvertTo-IpUint32 '192.168.0.0'))
Assert-True 'Get-CidrRange 192.168.0.0/24 end' ($r.End -eq (ConvertTo-IpUint32 '192.168.0.255'))
Assert-True 'Get-CidrRange /0 covers everything' ((Get-CidrRange '0.0.0.0/0').End -eq [uint32]4294967295)

Assert-True 'Overlap detect adjacent /24s' (-not (Test-CidrOverlap '10.0.0.0/24' '10.0.1.0/24'))
Assert-True 'Overlap detect nested' (Test-CidrOverlap '10.0.0.0/16' '10.0.5.0/24')
Assert-True 'Contains: /16 contains /24 inside' (Test-CidrContains '10.0.0.0/16' '10.0.5.0/24')
Assert-True 'Contains: /16 does not contain /24 outside' (-not (Test-CidrContains '10.0.0.0/16' '10.1.0.0/24'))

# --------------------------------------------------------------------------
Write-Host 'Parameter expansion preserves structured values' -ForegroundColor Cyan

$envValues = @{ ENVIRONMENT_NAME = 'ailz-test' }
$expandedString = Expand-ParamValue -Raw 'rg-${ENVIRONMENT_NAME=default}' -EnvValues $envValues
Assert-True 'String parameters still expand env tokens' ($expandedString -eq 'rg-ailz-test')

$objectValue = [pscustomobject]@{ name = 'text-embedding-3-large'; capacity = 100 }
$expandedObject = Expand-ParamValue -Raw $objectValue -EnvValues $envValues
Assert-True 'Object parameter values are preserved' ([object]::ReferenceEquals($objectValue, $expandedObject))

$arrayValue = @(
    [pscustomobject]@{ model = [pscustomobject]@{ format = 'OpenAI'; name = 'text-embedding-3-large' }; sku = [pscustomobject]@{ name = 'Standard'; capacity = 100 } }
)
$expandedArray = Expand-ParamValue -Raw $arrayValue -EnvValues $envValues
Assert-True 'Array parameter values are preserved' (-not ($expandedArray -is [string]) -and @($expandedArray).Count -eq 1 -and $expandedArray[0].model.name -eq 'text-embedding-3-large')

$paramsFile = Join-Path -Path ([System.IO.Path]::GetTempPath()) -ChildPath ("ailz-preflight-params-{0}.json" -f ([guid]::NewGuid()))
try {
    @'
{
  "parameters": {
    "resourceGroupName": {
      "value": "rg-${ENVIRONMENT_NAME=default}"
    },
    "modelDeploymentList": {
      "value": [
        {
          "model": {
            "format": "OpenAI",
            "name": "text-embedding-3-large"
          },
          "sku": {
            "name": "Standard",
            "capacity": 100
          }
        }
      ]
    }
  }
}
'@ | Set-Content -Path $paramsFile -Encoding utf8
    function Get-AzdEnvValues { return @{ ENVIRONMENT_NAME = 'ailz-test' } }
    Reset-Findings
    $effectiveParams = Get-EffectiveParameters -Path $paramsFile
    Assert-True 'Get-EffectiveParameters expands string values' ($effectiveParams['resourceGroupName'] -eq 'rg-ailz-test')
    Assert-True 'Get-EffectiveParameters preserves modelDeploymentList as array' (-not ($effectiveParams['modelDeploymentList'] -is [string]) -and @($effectiveParams['modelDeploymentList']).Count -eq 1 -and $effectiveParams['modelDeploymentList'][0].sku.capacity -eq 100)
}
finally {
    Remove-Item -Path $paramsFile -ErrorAction SilentlyContinue
}

# --------------------------------------------------------------------------
Write-Host 'VM SKU lookup is restricted to virtual machines' -ForegroundColor Cyan
$originalAzCliRaw = ${function:Invoke-AzCliRaw}
try {
    function Invoke-AzCliRaw {
        param([string[]]$Arguments)
        $script:VmSkuArguments = $Arguments
        return @([pscustomobject]@{
            name = 'Standard_D2s_v3'
            resourceType = 'virtualMachines'
            capabilities = @([pscustomobject]@{ name = 'vCPUs'; value = '2' })
            restrictions = @()
            family = 'standardDSv3Family'
        })
    }
    $sku = Get-VmSkuInfo -Location 'westus3' -VmSize 'Standard_D2s_v3'
    $typeIndex = [Array]::IndexOf($script:VmSkuArguments, '--resource-type')
    Assert-True 'SKU request filters virtualMachines server-side' (
        $typeIndex -ge 0 -and $script:VmSkuArguments[$typeIndex + 1] -eq 'virtualMachines'
    )
    Assert-True 'Filtered SKU keeps vCPU and availability facts' (
        $sku.Name -eq 'Standard_D2s_v3' -and $sku.VCpus -eq 2
    )
} finally {
    ${function:Invoke-AzCliRaw} = $originalAzCliRaw
}

# --------------------------------------------------------------------------
Write-Host 'Boolean parameter values accept only true and false' -ForegroundColor Cyan
foreach ($validValue in @($true, $false, 'true', ' FALSE ')) {
    Reset-Findings
    Test-BooleanParameterValues -P @{ deployContainerApps = $validValue }
    Assert-True "Boolean value '$validValue' is accepted" (Test-FindingAbsent 'BOOL_VALUE_INVALID')
}
foreach ($invalidValue in @('yes', 'no', '1', '0', 'banana', '')) {
    Reset-Findings
    Test-BooleanParameterValues -P @{ deployContainerApps = $invalidValue }
    Assert-True "Boolean value '$invalidValue' is rejected" (Test-FindingPresent 'BOOL_VALUE_INVALID')
}

# --------------------------------------------------------------------------
Write-Host 'Boolean parameter validation preserves explicit empty azd values' -ForegroundColor Cyan
function Get-AzdEnvValues {
    return @{
        DEPLOY_COSMOS_DB              = ''
        DEPLOY_CONTAINER_APPS         = ''
        DEPLOY_CONTAINER_REGISTRY     = ''
        DEPLOY_CONTAINER_ENV          = ''
        DEPLOY_NSGS                   = ''
        AI_FOUNDRY_DISABLE_LOCAL_AUTH = ''
    }
}
$mainParametersPath = Join-Path -Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) -ChildPath 'main.parameters.json'
Reset-Findings
$effectiveEmptyBooleanParams = Get-EffectiveParameters -Path $mainParametersPath
Test-BooleanParameterValues -P $effectiveEmptyBooleanParams
$invalidEmptyBooleanFindings = @($script:Findings | Where-Object Code -eq 'BOOL_VALUE_INVALID')
Assert-True 'All six explicit empty azd Boolean values remain empty after expansion' (
    $effectiveEmptyBooleanParams['deployCosmosDb'] -eq '' -and
    $effectiveEmptyBooleanParams['deployContainerApps'] -eq '' -and
    $effectiveEmptyBooleanParams['deployContainerRegistry'] -eq '' -and
    $effectiveEmptyBooleanParams['deployContainerEnv'] -eq '' -and
    $effectiveEmptyBooleanParams['deployNsgs'] -eq '' -and
    $effectiveEmptyBooleanParams['aiFoundryDisableLocalAuth'] -eq ''
)
Assert-True 'All six explicit empty azd Boolean values are rejected' ($invalidEmptyBooleanFindings.Count -eq 6)

# --------------------------------------------------------------------------
Write-Host 'Topology: Container Apps require an environment' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    deployContainerApps = $true
    deployContainerEnv  = $false
}
Assert-True 'FAIL ACA_APPS_REQUIRE_ENV raised' (Test-FindingPresent 'ACA_APPS_REQUIRE_ENV')

# --------------------------------------------------------------------------
Write-Host 'Topology: Container Apps environment-only deployment is valid' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    deployContainerApps = $false
    deployContainerEnv  = $true
}
Assert-True 'INFO ACA_ENVIRONMENT_ONLY raised' (Test-FindingPresent 'ACA_ENVIRONMENT_ONLY')
Assert-True 'Environment-only deployment has no failures' (@($script:Findings | Where-Object Severity -eq 'FAIL').Count -eq 0)

# --------------------------------------------------------------------------
Write-Host 'Topology: Container App API keys require apps, Key Vault, App Configuration, and appConfig mode' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    deployContainerApps         = $true
    deployContainerEnv          = $true
    deployKeyVault              = $false
    deployAppConfig             = $true
    appRuntimeConfigurationMode = 'appConfig'
    useCAppAPIKey               = $true
}
Assert-True 'FAIL CAPP_API_KEY_PREREQUISITES raised' (Test-FindingPresent 'CAPP_API_KEY_PREREQUISITES')

# --------------------------------------------------------------------------
Write-Host 'Topology: BYO subnet NSG associations are protected' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    networkIsolation = $true
    useExistingVNet  = $true
    deploySubnets    = $true
    deployNsgs       = $false
}
Assert-True 'FAIL BYO_SUBNET_NSG_DETACH raised' (Test-FindingPresent 'BYO_SUBNET_NSG_DETACH')

Reset-Findings
Test-Topology -P @{
    networkIsolation = $true
    useExistingVNet  = $true
    deploySubnets    = $false
    deployNsgs       = $false
}
Assert-True 'BYO VNet with externally managed subnets does not raise detach failure' (Test-FindingAbsent 'BYO_SUBNET_NSG_DETACH')
Assert-True 'WARN NSGS_DISABLED raised' (Test-FindingPresent 'NSGS_DISABLED')

# --------------------------------------------------------------------------
Write-Host 'Topology: enabling AI Foundry local auth warns' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{ aiFoundryDisableLocalAuth = $false }
Assert-True 'WARN AI_FOUNDRY_LOCAL_AUTH_ENABLED raised' (Test-FindingPresent 'AI_FOUNDRY_LOCAL_AUTH_ENABLED')

# --------------------------------------------------------------------------
Write-Host 'Topology: policy + BYO DNS conflict' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    policyManagedPrivateDns                  = $true
    existingPrivateDnsZoneOpenAiResourceId   = '/subscriptions/x/resourceGroups/y/providers/Microsoft.Network/privateDnsZones/privatelink.openai.azure.com'
    deploymentMode                           = 'standalone'
}
Assert-True 'FAIL DNS_POLICY_VS_BYO raised' (Test-FindingPresent 'DNS_POLICY_VS_BYO')

# --------------------------------------------------------------------------
Write-Host 'Topology: hub egress + existing RT mutex' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    hubIntegrationEgressNextHopIp              = '10.100.0.4'
    hubIntegrationExistingRouteTableResourceId = '/subscriptions/x/resourceGroups/y/providers/Microsoft.Network/routeTables/rt-1'
    deploymentMode                             = 'ailz-integrated'
}
Assert-True 'FAIL EGRESS_MUTEX raised' (Test-FindingPresent 'EGRESS_MUTEX')

# --------------------------------------------------------------------------
Write-Host 'Topology: deployAzureFirewall + hub egress IP warns' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    deployAzureFirewall              = $true
    hubIntegrationEgressNextHopIp    = '10.100.0.4'
}
Assert-True 'WARN FW_AND_EXTERNAL_EGRESS raised' (Test-FindingPresent 'FW_AND_EXTERNAL_EGRESS')

# --------------------------------------------------------------------------
Write-Host 'Topology: ailz-integrated without hub params warns' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    deploymentMode = 'ailz-integrated'
}
Assert-True 'WARN AILZ_NO_HUB_PARAMS raised' (Test-FindingPresent 'AILZ_NO_HUB_PARAMS')

# --------------------------------------------------------------------------
Write-Host 'Topology: existing AppI without connection string fails' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    existingApplicationInsightsResourceId      = '/subscriptions/x/resourceGroups/y/providers/Microsoft.Insights/components/appi-1'
    existingLogAnalyticsWorkspaceResourceId    = '/subscriptions/x/resourceGroups/y/providers/Microsoft.OperationalInsights/workspaces/law-1'
    existingApplicationInsightsConnectionString = ''
}
Assert-True 'FAIL APPI_NO_CONNSTR raised' (Test-FindingPresent 'APPI_NO_CONNSTR')

# --------------------------------------------------------------------------
Write-Host 'Topology: existing AppI without existing LAW (mixed not allowed) fails' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    existingApplicationInsightsResourceId       = '/subscriptions/x/resourceGroups/y/providers/Microsoft.Insights/components/appi-1'
    existingApplicationInsightsConnectionString = 'InstrumentationKey=xxx;IngestionEndpoint=https://eastus.in.applicationinsights.azure.com'
    allowMixedObservabilityWorkspaces           = $false
}
Assert-True 'FAIL APPI_NO_LAW raised' (Test-FindingPresent 'APPI_NO_LAW')

# --------------------------------------------------------------------------
Write-Host 'Topology: existing AppI without LAW + mixed allowed is OK' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    existingApplicationInsightsResourceId       = '/subscriptions/x/resourceGroups/y/providers/Microsoft.Insights/components/appi-1'
    existingApplicationInsightsConnectionString = 'InstrumentationKey=xxx;IngestionEndpoint=https://eastus.in.applicationinsights.azure.com'
    allowMixedObservabilityWorkspaces           = $true
}
Assert-True 'No APPI_NO_LAW when mixed allowed' (Test-FindingAbsent 'APPI_NO_LAW')

# --------------------------------------------------------------------------
Write-Host 'Topology: networkIsolation without ingress warns' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    networkIsolation  = $true
    deployJumpbox     = $false
    deployVM          = $false
    allowedIpRanges   = @()
}
Assert-True 'WARN ISO_NO_INGRESS raised' (Test-FindingPresent 'ISO_NO_INGRESS')

# --------------------------------------------------------------------------
Write-Host 'Hosted agent: disabled contract is inert' -ForegroundColor Cyan
Reset-Findings
Test-HostedAgentConfiguration -P @{
    prepareHostedAgent = $false
    deployHostedAgent = $false
}
Assert-True 'Disabled hosted-agent contract emits no findings' (@($script:Findings).Count -eq 0)

# --------------------------------------------------------------------------
Write-Host 'Hosted agent: prepare-only contract does not require an image digest' -ForegroundColor Cyan
Reset-Findings
Test-HostedAgentConfiguration -P @{
    prepareHostedAgent    = $true
    deployHostedAgent     = $false
    deployAiFoundry       = $true
    deployContainerRegistry = $true
    networkIsolation      = $false
}
Assert-True 'Prepare-only hosted-agent contract has no failures without hostedAgent.version' (@($script:Findings | Where-Object Severity -eq 'FAIL').Count -eq 0)
Assert-True 'Prepare-only hosted-agent contract skips immutable image validation' (Test-FindingAbsent 'HOSTED_AGENT_IMAGE_NOT_IMMUTABLE')

# --------------------------------------------------------------------------
Write-Host 'Hosted agent: deploy is a superset and accepts an immutable digest' -ForegroundColor Cyan
Reset-Findings
Test-HostedAgentConfiguration -P @{
    prepareHostedAgent      = $false
    deployHostedAgent       = $true
    deployAiFoundry         = $true
    deployContainerRegistry = $true
    networkIsolation        = $false
    hostedAgent             = [pscustomobject]@{
        name           = 'sample-agent'
        image          = 'agents/sample'
        version        = "sha256:$('a' * 64)"
        startupCommand = ''
        runtime        = [pscustomobject]@{ cpu = '1'; memory = '1Gi' }
        protocols      = @([pscustomobject]@{ protocol = 'responses'; version = '2.0.0' })
    }
}
Assert-True 'Valid hosted-agent contract has no failures' (@($script:Findings | Where-Object Severity -eq 'FAIL').Count -eq 0)
Assert-True 'Immutable hosted-agent image digest is accepted' (Test-FindingAbsent 'HOSTED_AGENT_IMAGE_NOT_IMMUTABLE')

# --------------------------------------------------------------------------
Write-Host 'Hosted agent: private preparation reports the VNet build requirement' -ForegroundColor Cyan
Reset-Findings
Test-HostedAgentConfiguration -P @{
    prepareHostedAgent      = $true
    deployHostedAgent       = $false
    deployAiFoundry         = $true
    deployContainerRegistry = $true
    networkIsolation        = $true
}
Assert-True 'Prepare-only private registry requires an in-VNet build path' (Test-FindingPresent 'HOSTED_AGENT_PRIVATE_BUILD_REQUIRED')
Assert-True 'Prepare-only private registry has no failures' (@($script:Findings | Where-Object Severity -eq 'FAIL').Count -eq 0)

# --------------------------------------------------------------------------
Write-Host 'Hosted agent: registry role assignment mode is validated' -ForegroundColor Cyan
Reset-Findings
Test-HostedAgentConfiguration -P @{
    prepareHostedAgent                              = $true
    deployHostedAgent                               = $false
    deployAiFoundry                                 = $true
    deployContainerRegistry                         = $false
    hostedAgentContainerRegistryResourceId         = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/Microsoft.ContainerRegistry/registries/acr'
    hostedAgentContainerRegistryEndpoint           = 'acr.azurecr.io'
    hostedAgentContainerRegistryRoleAssignmentMode = 'unsupported'
}
Assert-True 'FAIL HOSTED_AGENT_REGISTRY_ROLE_MODE_INVALID raised' (Test-FindingPresent 'HOSTED_AGENT_REGISTRY_ROLE_MODE_INVALID')

# --------------------------------------------------------------------------
Write-Host 'Hosted agent: arbitrary runtime role names are rejected' -ForegroundColor Cyan
Reset-Findings
Test-HostedAgentConfiguration -P @{
    deployHostedAgent       = $true
    deployAiFoundry         = $true
    deployContainerRegistry = $true
    hostedAgent             = [pscustomobject]@{
        name           = 'sample-agent'
        image          = 'agents/sample'
        version        = "sha256:$('b' * 64)"
        startupCommand = ''
        runtime        = [pscustomobject]@{ cpu = '1'; memory = '1Gi' }
        protocols      = @([pscustomobject]@{ protocol = 'responses'; version = '2.0.0' })
        roles          = @('Reader', 'UnsupportedRoleName')
    }
}
Assert-True 'FAIL HOSTED_AGENT_ROLES_UNSUPPORTED raised' (Test-FindingPresent 'HOSTED_AGENT_ROLES_UNSUPPORTED')

# --------------------------------------------------------------------------
Write-Host 'Hosted agent: runtime resources follow the current Foundry contract' -ForegroundColor Cyan
Reset-Findings
Test-HostedAgentConfiguration -P @{
    deployHostedAgent       = $true
    deployAiFoundry         = $true
    deployContainerRegistry = $true
    hostedAgent             = [pscustomobject]@{
        name           = 'sample-agent'
        image          = 'agents/sample'
        version        = "sha256:$('c' * 64)"
        startupCommand = ''
        runtime        = [pscustomobject]@{ cpu = '500m'; memory = '512Mi' }
        protocols      = @([pscustomobject]@{ protocol = 'responses'; version = '2.0.0' })
    }
}
Assert-True 'FAIL HOSTED_AGENT_CPU_INVALID raised' (Test-FindingPresent 'HOSTED_AGENT_CPU_INVALID')
Assert-True 'FAIL HOSTED_AGENT_MEMORY_INVALID raised' (Test-FindingPresent 'HOSTED_AGENT_MEMORY_INVALID')

# --------------------------------------------------------------------------
Write-Host 'Hosted agent: immutable image digest is required' -ForegroundColor Cyan
Reset-Findings
Test-HostedAgentConfiguration -P @{
    deployHostedAgent       = $true
    deployAiFoundry         = $true
    deployContainerRegistry = $true
    hostedAgent             = [pscustomobject]@{
        name           = 'sample-agent'
        image          = 'agents/sample'
        version        = 'latest'
        startupCommand = 'python main.py'
        runtime        = [pscustomobject]@{ cpu = '1'; memory = '1Gi' }
        protocols      = @([pscustomobject]@{ protocol = 'responses'; version = '2.0.0' })
    }
}
Assert-True 'FAIL HOSTED_AGENT_IMAGE_NOT_IMMUTABLE raised' (Test-FindingPresent 'HOSTED_AGENT_IMAGE_NOT_IMMUTABLE')

# --------------------------------------------------------------------------
Write-Host 'Hosted agent: missing image digest is rejected during deployment' -ForegroundColor Cyan
Reset-Findings
Test-HostedAgentConfiguration -P @{
    prepareHostedAgent      = $true
    deployHostedAgent       = $true
    deployAiFoundry         = $true
    deployContainerRegistry = $true
    hostedAgent             = [pscustomobject]@{
        name           = 'sample-agent'
        image          = 'agents/sample'
        version        = ''
        startupCommand = 'python main.py'
        runtime        = [pscustomobject]@{ cpu = '1'; memory = '1Gi' }
        protocols      = @([pscustomobject]@{ protocol = 'responses'; version = '2.0.0' })
    }
}
Assert-True 'FAIL HOSTED_AGENT_IMAGE_NOT_IMMUTABLE raised for missing digest' (Test-FindingPresent 'HOSTED_AGENT_IMAGE_NOT_IMMUTABLE')

# --------------------------------------------------------------------------
Write-Host 'Hosted agent: noncanonical and placeholder digests are rejected' -ForegroundColor Cyan
foreach ($invalidDigest in @(
        " SHA256:$('d' * 64) ",
        "sha256:$('A' * 64)",
        "sha256:$('e' * 64)`n",
        'sha256:<64-hex-digest>'
    )) {
    Reset-Findings
    Test-HostedAgentConfiguration -P @{
        prepareHostedAgent      = $false
        deployHostedAgent       = $true
        deployAiFoundry         = $true
        deployContainerRegistry = $true
        hostedAgent             = [pscustomobject]@{
            name           = 'sample-agent'
            image          = 'agents/sample'
            version        = $invalidDigest
            startupCommand = 'python main.py'
            runtime        = [pscustomobject]@{ cpu = '1'; memory = '1Gi' }
            protocols      = @([pscustomobject]@{ protocol = 'responses'; version = '2.0.0' })
        }
    }
    Assert-True "FAIL HOSTED_AGENT_IMAGE_NOT_IMMUTABLE raised for '$invalidDigest'" (Test-FindingPresent 'HOSTED_AGENT_IMAGE_NOT_IMMUTABLE')
}

# --------------------------------------------------------------------------
Write-Host 'Hosted agent: Foundry and registry prerequisites are enforced during preparation' -ForegroundColor Cyan
Reset-Findings
Test-HostedAgentConfiguration -P @{
    prepareHostedAgent                      = $true
    deployHostedAgent                       = $false
    deployAiFoundry                         = $false
    deployContainerRegistry                 = $false
    hostedAgentContainerRegistryResourceId = ''
    hostedAgentContainerRegistryEndpoint   = ''
}
Assert-True 'FAIL HOSTED_AGENT_FOUNDRY_REQUIRED raised' (Test-FindingPresent 'HOSTED_AGENT_FOUNDRY_REQUIRED')
Assert-True 'FAIL HOSTED_AGENT_REGISTRY_REQUIRED raised' (Test-FindingPresent 'HOSTED_AGENT_REGISTRY_REQUIRED')

# --------------------------------------------------------------------------
Write-Host 'IP allow-list: invalid CIDR' -ForegroundColor Cyan
Reset-Findings
Test-AllowedIpRanges -P @{ allowedIpRanges = @('not-a-cidr', '10.0.0.0/8') }
Assert-True 'FAIL IP_FORMAT raised' (Test-FindingPresent 'IP_FORMAT')

# --------------------------------------------------------------------------
Write-Host 'IP allow-list: 0.0.0.0/0 warns' -ForegroundColor Cyan
Reset-Findings
Test-AllowedIpRanges -P @{ allowedIpRanges = @('0.0.0.0/0') }
Assert-True 'WARN IP_ANY raised' (Test-FindingPresent 'IP_ANY')

# --------------------------------------------------------------------------
Write-Host 'IP allow-list: clean list passes' -ForegroundColor Cyan
Reset-Findings
Test-AllowedIpRanges -P @{ allowedIpRanges = @('203.0.113.5/32', '198.51.100.0/24') }
Assert-True 'No IP findings on clean list' ((@($script:Findings).Count) -eq 0)

# --------------------------------------------------------------------------
Write-Host 'Local CIDR sanity: subnet outside VNet' -ForegroundColor Cyan
Reset-Findings
Test-LocalCidrSanity -P @{
    vnetAddressPrefixes        = @('192.168.0.0/22')
    peSubnetPrefix             = '10.0.0.0/27'   # outside the VNet
    azureBastionSubnetPrefix   = '192.168.2.64/26'
    azureFirewallSubnetPrefix  = '192.168.2.128/26'
    acaEnvironmentSubnetPrefix = '192.168.1.0/24'
}
Assert-True 'FAIL SUBNET_OUTSIDE_VNET raised' (Test-FindingPresent 'SUBNET_OUTSIDE_VNET')

# --------------------------------------------------------------------------
Write-Host 'Local CIDR sanity: overlapping subnets' -ForegroundColor Cyan
Reset-Findings
Test-LocalCidrSanity -P @{
    vnetAddressPrefixes        = @('192.168.0.0/22')
    peSubnetPrefix             = '192.168.2.0/26'
    azureBastionSubnetPrefix   = '192.168.2.0/26'  # collides with pe
    acaEnvironmentSubnetPrefix = '192.168.1.0/24'
}
Assert-True 'FAIL SUBNET_OVERLAP raised' (Test-FindingPresent 'SUBNET_OVERLAP')

# --------------------------------------------------------------------------
Write-Host 'Local CIDR sanity: Bastion subnet too small' -ForegroundColor Cyan
Reset-Findings
Test-LocalCidrSanity -P @{
    vnetAddressPrefixes        = @('192.168.0.0/22')
    azureBastionSubnetPrefix   = '192.168.2.64/28'  # /28 — too small (need /26)
    acaEnvironmentSubnetPrefix = '192.168.1.0/24'
}
Assert-True 'FAIL SUBNET_TOO_SMALL raised for Bastion' (Test-FindingPresent 'SUBNET_TOO_SMALL')

# --------------------------------------------------------------------------
Write-Host 'Local CIDR sanity: defaults pass' -ForegroundColor Cyan
Reset-Findings
Test-LocalCidrSanity -P @{
    vnetAddressPrefixes           = @('192.168.0.0/22')
    agentSubnetPrefix             = '192.168.0.0/24'
    acaEnvironmentSubnetPrefix    = '192.168.1.0/24'
    peSubnetPrefix                = '192.168.2.0/26'
    azureBastionSubnetPrefix      = '192.168.2.64/26'
    azureFirewallSubnetPrefix     = '192.168.2.128/26'
    jumpboxSubnetPrefix           = '192.168.3.64/27'
    devopsBuildAgentsSubnetPrefix = '192.168.3.96/27'
}
Assert-True 'No CIDR findings on default layout' ((@($script:Findings).Count) -eq 0)

# --------------------------------------------------------------------------
Write-Host 'Regional readiness: Get-NormalizedLocation' -ForegroundColor Cyan
Assert-True 'Normalize "East US 2" -> eastus2' ((Get-NormalizedLocation 'East US 2') -eq 'eastus2')
Assert-True 'Normalize empty -> empty' ((Get-NormalizedLocation '') -eq '')

# --------------------------------------------------------------------------
Write-Host 'Regional readiness: env-var skip emits REGIONAL_SKIPPED INFO' -ForegroundColor Cyan
Reset-Findings
$env:LZ_PREFLIGHT_REGIONAL_SKIP = 'true'
$script:SkipAzureLookups = $false
$script:SkipRegional = $false
try {
    Test-RegionalReadiness -P @{ location = 'eastus2' }
}
finally {
    Remove-Item Env:LZ_PREFLIGHT_REGIONAL_SKIP -ErrorAction SilentlyContinue
}
Assert-True 'REGIONAL_SKIPPED INFO present' (Test-FindingPresent 'REGIONAL_SKIPPED')
Assert-True 'Only one finding emitted under skip' (@($script:Findings).Count -eq 1)

# --------------------------------------------------------------------------
Write-Host 'Regional readiness: model quota fails when requested capacity exceeds availability' -ForegroundColor Cyan
Reset-Findings
function Invoke-AzCliRaw {
    param([string[]]$Arguments)
    if (($Arguments -join ' ') -eq 'cognitiveservices usage list --location westus3 -o json') {
        return @(
            [pscustomobject]@{
                name         = [pscustomobject]@{ value = 'OpenAI.Standard.text-embedding-3-large' }
                currentValue = 300
                limit        = 350
            }
        )
    }
    return $null
}
Test-ModelQuota -Location 'westus3' -ModelDeployments @(
    [pscustomobject]@{
        model = [pscustomobject]@{
            format = 'OpenAI'
            name   = 'text-embedding-3-large'
        }
        sku   = [pscustomobject]@{
            name     = 'Standard'
            capacity = 100
        }
    }
)
Assert-True 'MODEL_QUOTA_INSUFFICIENT FAIL raised' (Test-FindingPresent 'MODEL_QUOTA_INSUFFICIENT')

# --------------------------------------------------------------------------
Write-Host 'Regional readiness: -SkipAzureLookups suppresses block entirely' -ForegroundColor Cyan
Reset-Findings
$script:SkipAzureLookups = $true
try {
    Test-RegionalReadiness -P @{ location = 'eastus2'; deployAiFoundry = $true; modelDeploymentList = @() }
}
finally {
    $script:SkipAzureLookups = $false
}
Assert-True 'No findings emitted under SkipAzureLookups' (@($script:Findings).Count -eq 0)

# --------------------------------------------------------------------------
Write-Host 'Regional readiness: missing location emits REGIONAL_NO_LOCATION WARN' -ForegroundColor Cyan
Reset-Findings
# Stub az lookups so we don't actually call the CLI.
function Invoke-AzCliRaw { param([string[]]$Arguments) return $null }
function Get-AzdEnvValues { return @{} }
$script:SkipAzureLookups = $false
$script:SkipRegional = $false
Test-RegionalReadiness -P @{ location = '' }
Assert-True 'REGIONAL_NO_LOCATION WARN raised' (Test-FindingPresent 'REGIONAL_NO_LOCATION')

# --------------------------------------------------------------------------
Write-Host 'Search quota checks the effective region and complete resource count' -ForegroundColor Cyan
function Invoke-AzCliRaw {
    param([string[]]$Arguments)
    return @{ value = @(@{ name = @{ value = 'standard' }; limit = 12; currentValue = $script:SearchUsage }) }
}
$script:SearchUsage = 11
Reset-Findings
Test-AzureSearchSkuQuota -SubscriptionId 'offline' -Location 'eastus' -Sku 'standard' -RequiredHeadroom 2
Assert-True 'One slot rejects two requested Search services' (Test-FindingPresent 'SEARCH_QUOTA_INSUFFICIENT')
$script:SearchUsage = 10
Reset-Findings
Test-AzureSearchSkuQuota -SubscriptionId 'offline' -Location 'eastus' -Sku 'standard' -RequiredHeadroom 2
Assert-True 'Two slots permit two requested Search services' (Test-FindingAbsent 'SEARCH_QUOTA_INSUFFICIENT')

function az { }
function Get-CurrentAzureSubscriptionId { return 'offline' }
function Test-CognitiveServicesQuotaHeadroom { }
function Test-CosmosAvailabilityZone { }
function Test-ProviderLocation {
    param($ProviderNamespace, $ResourceType, $Location, $DisplayName, $CodePrefix)
    if ($ProviderNamespace -eq 'Microsoft.Search') { $script:SearchProviderLocation = $Location }
}
function Test-AzureSearchSkuQuota {
    param($SubscriptionId, $Location, $Sku, $RequiredHeadroom)
    $script:SearchQuotaLocation = $Location
    $script:SearchRequiredCount = $RequiredHeadroom
}
foreach ($case in @(
    @{ override = 'eastus'; general = $true; agents = $true; existing = ''; expected = 2; region = 'eastus' },
    @{ override = ''; general = $true; agents = $false; existing = ''; expected = 1; region = 'westus3' },
    @{ override = ' '; general = $false; agents = $true; existing = ''; expected = 1; region = 'westus3' },
    @{ override = 'eastus'; general = $true; agents = $true; existing = '/existing/search'; expected = 1; region = 'eastus' },
    @{ override = 'eastus'; general = $true; agents = $true; foundry = $false; existing = ''; expected = 1; region = 'eastus' },
    @{ override = 'eastus'; general = $false; agents = $false; existing = ''; expected = 0; region = '' }
)) {
    $script:SearchQuotaLocation = ''
    $script:SearchProviderLocation = ''
    $script:SearchRequiredCount = 0
    Test-RegionalReadiness -P @{
        location = 'westus3'; searchServiceLocation = $case.override
        deploySearchService = $case.general; deployAAfAgentSvc = $case.agents
        deployAiFoundry = if ($case.ContainsKey('foundry')) { $case.foundry } else { $true }
        aiSearchResourceId = $case.existing; deployJumpbox = $false
    }
    Assert-True "Search count $($case.expected) is checked" ($script:SearchRequiredCount -eq $case.expected)
    Assert-True "Search quota region is '$($case.region)'" ($script:SearchQuotaLocation -eq $case.region) "Actual: '$script:SearchQuotaLocation'"
    Assert-True "Search provider region is '$($case.region)'" ($script:SearchProviderLocation -eq $case.region) "Actual: '$script:SearchProviderLocation'"
}

# --------------------------------------------------------------------------
Write-Host ''
Write-Host ("Tests run: $script:TestsRun  Failures: $script:TestFailures") -ForegroundColor Cyan

if ($script:TestFailures -gt 0) { exit 1 } else { exit 0 }
