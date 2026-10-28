<#
.SYNOPSIS
    Deterministic behavioral tests for scripts/Invoke-PreflightChecks.ps1.

.DESCRIPTION
    Synthetic-input tests that exercise the deterministic checks (Test-Topology,
    Test-HostedAgentConfiguration, Test-AllowedIpRanges, Test-LocalCidrSanity)
    and consumer-aware subnet selection/reuse with mocked live Azure reads.
    No Azure credentials or writes are used.

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
$incorporatedDefaults = Get-EffectiveParameters -Path $mainParametersPath
Assert-True 'Incorporated literal true defaults do not consume empty azd aliases' (
    @('deployContainerApps', 'deployContainerRegistry', 'deployContainerEnv', 'deployNsgs' |
        Where-Object { $incorporatedDefaults[$_] -cne 'true' }).Count -eq 0
)
Assert-True 'Application Cosmos alias preserves an explicit empty value for validation' (
    $incorporatedDefaults['deployCosmosDb'] -ceq ''
)
# Exercise upstream alias expansion independently of the umbrella's literal
# parameter surface; neither missing keys nor literals are environment aliases.
$emptyBooleanFixture = Join-Path $PSScriptRoot ".boolean-aliases-$([guid]::NewGuid().ToString('N')).json"
try {
    @{
        parameters = @{
            deployCosmosDb = @{ value = '${DEPLOY_COSMOS_DB=true}' }
            deployContainerApps = @{ value = '${DEPLOY_CONTAINER_APPS=true}' }
            deployContainerRegistry = @{ value = '${DEPLOY_CONTAINER_REGISTRY=true}' }
            deployContainerEnv = @{ value = '${DEPLOY_CONTAINER_ENV=true}' }
            deployNsgs = @{ value = '${DEPLOY_NSGS=true}' }
            aiFoundryDisableLocalAuth = @{ value = '${AI_FOUNDRY_DISABLE_LOCAL_AUTH=true}' }
        }
    } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $emptyBooleanFixture -Encoding utf8
    $effectiveEmptyBooleanParams = Get-EffectiveParameters -Path $emptyBooleanFixture
}
finally { Remove-Item -LiteralPath $emptyBooleanFixture -ErrorAction SilentlyContinue }
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
Write-Host 'Topology: deployAzureFirewall + hub egress IP fails' -ForegroundColor Cyan
Reset-Findings
Test-Topology -P @{
    deployAzureFirewall              = $true
    networkIsolation                 = $true
    hubIntegrationEgressNextHopIp    = '10.100.0.4'
}
Assert-True 'FAIL FW_AND_EXTERNAL_EGRESS raised' (@($script:Findings | Where-Object { $_.Code -eq 'FW_AND_EXTERNAL_EGRESS' -and $_.Severity -eq 'FAIL' }).Count -eq 1)

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
    networkIsolation           = $true
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
    networkIsolation           = $true
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
    networkIsolation           = $true
    vnetAddressPrefixes        = @('192.168.0.0/22')
    azureBastionSubnetPrefix   = '192.168.2.64/28'  # /28 — too small (need /26)
    acaEnvironmentSubnetPrefix = '192.168.1.0/24'
}
Assert-True 'FAIL SUBNET_TOO_SMALL raised for Bastion' (Test-FindingPresent 'SUBNET_TOO_SMALL')

# --------------------------------------------------------------------------
Write-Host 'Local CIDR sanity: defaults pass' -ForegroundColor Cyan
Reset-Findings
Test-LocalCidrSanity -P @{
    networkIsolation              = $true
    vnetAddressPrefixes           = @('192.168.0.0/21')
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
Write-Host 'Architecture subnet selection, strict flags, names and addressing' -ForegroundColor Cyan
$defaultSubnets = @(Get-SubnetSelection -P @{ networkIsolation = $true })
Assert-True 'Basic defaults select twelve of thirteen definitions without GatewaySubnet' ($defaultSubnets.Count -eq 13 -and @($defaultSubnets | Where-Object Managed).Count -eq 12 -and -not ($defaultSubnets | Where-Object Flag -eq deployGatewaySubnet).Managed)
$expectedSubnets = @{
    deployAgentSubnet = @('agent-subnet', '192.168.0.0/24', 'Microsoft.App/environments')
    deployPeSubnet = @('pe-subnet', '192.168.2.0/26', '')
    deployApplicationPeSubnet = @('application-pe-subnet', '192.168.3.128/26', '')
    deployAzureBastionSubnet = @('AzureBastionSubnet', '192.168.2.64/26', '')
    deployAzureFirewallSubnet = @('AzureFirewallSubnet', '192.168.2.128/26', '')
    deployAzureFirewallManagementSubnet = @('AzureFirewallManagementSubnet', '192.168.3.192/26', '')
    deployGatewaySubnet = @('GatewaySubnet', '192.168.2.192/26', '')
    deployAppGatewaySubnet = @('AppGatewaySubnet', '192.168.3.0/27', '')
    deployJumpboxSubnet = @('jumpbox-subnet', '192.168.3.64/27', '')
    deployAcaEnvironmentSubnet = @('aca-environment-subnet', '192.168.1.0/24', 'Microsoft.App/environments')
    deployDevopsBuildAgentsSubnet = @('devops-build-agents-subnet', '192.168.3.96/27', '')
    deployPowerPlatformSubnet = @('powerplatform-subnet', '192.168.4.0/24', 'Microsoft.PowerPlatform/enterprisePolicies')
    deployAiGatewaySubnet = @('ai-gateway-subnet', '192.168.5.0/24', 'Microsoft.Web/serverFarms')
}
foreach ($s in $defaultSubnets) {
    $expected = $expectedSubnets[$s.Flag]
    Assert-True "$($s.Flag) exact name, CIDR and delegation" ($s.Name -ceq $expected[0] -and $s.Cidr -ceq $expected[1] -and $s.Delegation -ceq $expected[2])
    foreach ($byo in $true, $false) {
        $p = @{ networkIsolation = $true; useExistingVNet = $byo }
        $p[$s.Flag] = $false
        $selected = @(Get-SubnetSelection -P $p)
        Assert-True "$($s.Flag) independently omits only its creation (BYO=$byo)" (
            @($selected | Where-Object Managed).Count -eq (12 - [int]$s.Managed) -and
            -not ($selected | Where-Object Flag -eq $s.Flag).Managed -and
            ($selected | Where-Object Flag -eq $s.Flag).Required -eq $s.Required
        )
    }
}
foreach ($key in @('deploySubnets') + @($defaultSubnets.Flag)) {
    foreach ($invalid in @('', $null, 'yes', 'no', '1', '0', 1, 'banana', '${UNRESOLVED}')) {
        if ($null -eq $invalid -and $key -in 'deployAzureFirewallSubnet', 'deployAzureFirewallManagementSubnet') { continue }
        Reset-Findings
        Test-BooleanParameterValues -P @{ $key = $invalid }
        Assert-True "$key rejects explicit '$invalid'" (Test-FindingPresent 'BOOL_VALUE_INVALID')
    }
}
foreach ($byo in $true, $false) {
    $selection = @(Get-SubnetSelection -P @{ networkIsolation = $true; useExistingVNet = $byo; deploySubnets = $false })
    Assert-True "Global false suppresses all creations, not consumers (BYO=$byo)" (
        @($selection | Where-Object Managed).Count -eq 0 -and
        @($selection | Where-Object Required).Count -eq @($defaultSubnets | Where-Object Required).Count
    )
}
Reset-Findings
Test-LocalCidrSanity -P @{ networkIsolation = $false; applicationPeSubnetName = ''; aiGatewaySubnetPrefix = 'invalid' }
Assert-True 'Public mode does not acquire or validate a subnet topology' ($script:Findings.Count -eq 0)
Reset-Findings
Test-LocalCidrSanity -P @{ networkIsolation = $true; deploySubnets = $false }
Assert-True 'New VNet cannot reference required omitted subnets' (Test-FindingPresent 'SUBNET_REQUIRED_NOT_MANAGED')
$noConsumer = @{
    networkIsolation = $true; deploySubnets = $false
    deployAiFoundry = $false; deployCosmosDb = $false; deployStorageAccount = $false
    deploySearchService = $false; deploySpeechService = $false
    deployContainerEnv = $false; deployContainerApps = $false; deployContainerRegistry = $false
    deployKeyVault = $false; deployAppConfig = $false; enablePrivateLogAnalytics = $false
    deployJumpbox = $false; deployBastion = $false; deployAzureFirewall = $false
}
Reset-Findings
Test-LocalCidrSanity -P $noConsumer
Assert-True 'New VNet with no creations and no consumers is valid' ($script:Findings.Count -eq 0)
foreach ($invalidIngress in @('{"enabled":', 'not-json', '[{"enabled":true}]', 'null', '{}', @{ enabled = 'yes' }, $null)) {
    Reset-Findings
    Get-SubnetSelection -P @{ networkIsolation = $true; publicIngress = $invalidIngress } | Out-Null
    Assert-True 'Invalid publicIngress JSON or consumer shape is an explicit failure' (
        @($script:Findings | Where-Object { $_.Code -eq 'PUBLIC_INGRESS_INVALID' -and $_.Severity -eq 'FAIL' }).Count -eq 1
    )
}
Reset-Findings
$ingressSelection = @(Get-SubnetSelection -P @{
    networkIsolation = $true; publicIngress = '  {"enabled": true}  '
    containerAppsList = @(@{ name = 'frontend' })
})
Assert-True 'Valid JSON publicIngress preserves its enabled subnet consumer' (
    $script:Findings.Count -eq 0 -and ($ingressSelection | Where-Object Flag -eq deployAppGatewaySubnet).Required
)
foreach ($key in @($defaultSubnets.NameKey)) {
    Reset-Findings
    Test-LocalCidrSanity -P @{ networkIsolation = $true; deployGatewaySubnet = $true; $key = '' }
    Assert-True "Empty managed subnet name $key is rejected" (Test-FindingPresent 'SUBNET_NAME_INVALID')
}
foreach ($name in 'invalid/name', 'trailing-', ('a' * 81), ' leading') {
    Reset-Findings
    Test-LocalCidrSanity -P @{ networkIsolation = $true; peSubnetName = $name }
    Assert-True "Invalid subnet name '$name' is rejected" (Test-FindingPresent 'SUBNET_NAME_INVALID')
}
foreach ($case in @(
    @{ gatewaySubnetName = 'gateway-subnet' },
    @{ azureBastionSubnetName = 'bastion' },
    @{ azureFirewallSubnetName = 'firewall' },
    @{ aiGatewaySubnetName = 'GatewaySubnet' },
    @{ applicationPeSubnetName = 'AzureFirewallManagementSubnet' }
)) {
    Reset-Findings
    $case.networkIsolation = $true
    $case.deployGatewaySubnet = $true
    Test-LocalCidrSanity -P $case
    Assert-True "Reserved name misuse '$($case.Values -join ',')' is rejected" (Test-FindingPresent 'SUBNET_RESERVED_NAME')
}
Reset-Findings
Test-LocalCidrSanity -P @{ networkIsolation = $true; applicationPeSubnetName = 'PE-SUBNET' }
Assert-True 'Duplicate purpose names rejected case-insensitively; no shared PE fallback' (Test-FindingPresent 'SUBNET_NAME_DUPLICATE')
foreach ($cidr in '192.168.5.1/24', '192.168.005.0/24', '256.0.0.0/24', '10.0/24', '::/64', '192.168.5.0', '192.168.5.0/33', '') {
    Reset-Findings
    Test-LocalCidrSanity -P @{ networkIsolation = $true; aiGatewaySubnetPrefix = $cidr }
    Assert-True "Malformed/unaligned network '$cidr' is rejected" (Test-FindingPresent 'SUBNET_CIDR_BAD')
}
foreach ($s in $defaultSubnets | Where-Object Flag -in 'deployApplicationPeSubnet', 'deployGatewaySubnet', 'deployAppGatewaySubnet', 'deployPowerPlatformSubnet', 'deployAiGatewaySubnet') {
    Reset-Findings
    Test-LocalCidrSanity -P @{ networkIsolation = $true; $s.Flag = $true; $s.PrefixKey = '192.168.0.0/24' }
    Assert-True "Overlap rejected for $($s.PrefixKey)" (Test-FindingPresent 'SUBNET_OVERLAP')
}
Reset-Findings
Test-LocalCidrSanity -P @{ networkIsolation = $true; aiGatewaySubnetPrefix = '192.168.5.0/28' }
Assert-True 'APIM integration smaller than /27 fails' (Test-FindingPresent 'SUBNET_TOO_SMALL')
Reset-Findings
Test-LocalCidrSanity -P @{ networkIsolation = $true; aiGatewaySubnetPrefix = '192.168.5.0/27'; powerPlatformSubnetPrefix = '192.168.4.0/28' }
Assert-True 'APIM /27 passes hard minimum; recommends /24' ((Test-FindingAbsent 'SUBNET_TOO_SMALL') -and (Test-FindingPresent 'AI_GATEWAY_SUBNET_BELOW_RECOMMENDED'))
Assert-True 'Power Platform /24 is not a fabricated platform minimum' (@($script:Findings | Where-Object Severity -eq FAIL).Count -eq 0)
Reset-Findings
Test-LocalCidrSanity -P @{ networkIsolation = $true; deployNsgs = $false }
Assert-True 'Managed AI Gateway requires an NSG in either VNet path' (Test-FindingPresent 'AI_GATEWAY_NSG_REQUIRED')
foreach ($prefixes in @(@('192.168.0.1/21'), @('192.168.0.0/21', '192.168.0.0/22'), @())) {
    Reset-Findings
    Test-LocalCidrSanity -P @{ networkIsolation = $true; vnetAddressPrefixes = $prefixes }
    Assert-True 'Invalid/overlapping/empty VNet address space fails' (@($script:Findings | Where-Object { $_.Code -in 'VNET_CIDR_BAD', 'VNET_CIDR_OVERLAP' }).Count -gt 0)
}
$custom = @{ networkIsolation = $true; vnetAddressPrefixes = @('10.20.0.0/21') }
foreach ($s in $defaultSubnets) { $custom[$s.PrefixKey] = $s.Cidr.Replace('192.168.', '10.20.') }
Reset-Findings
Test-LocalCidrSanity -P $custom
Assert-True 'Custom address space and all selected operator prefixes are honored for a new VNet' ($script:Findings.Count -eq 0)

# --------------------------------------------------------------------------
Write-Host 'Basic/Standard topology, auto intent and explicit reservations' -ForegroundColor Cyan
foreach ($auto in @($null, 'null')) {
    Reset-Findings
    Test-BooleanParameterValues -P @{ deployAzureFirewallSubnet = $auto; deployAzureFirewallManagementSubnet = $auto }
    Assert-True 'Nullable firewall creation accepts auto only on nullable flags' ($script:Findings.Count -eq 0)
    $autoSelection = @(Get-SubnetSelection -P @{ networkIsolation = $true; deployAzureFirewallSubnet = $auto; deployAzureFirewallManagementSubnet = $auto })
    Assert-True 'Auto resolves both required Basic subnet creations' (
        ($autoSelection | Where-Object Flag -eq deployAzureFirewallSubnet).Managed -and
        ($autoSelection | Where-Object Flag -eq deployAzureFirewallManagementSubnet).Managed
    )
}
foreach ($case in @(
    @{ azureFirewallSku = 'Premium'; Code = 'FIREWALL_SKU_INVALID' },
    @{ azureFirewallSku = 'basic'; Code = 'FIREWALL_SKU_INVALID' },
    @{ azureFirewallSku = 'Basic'; enableFirewallDnsProxy = $true; Code = 'BASIC_FIREWALL_DNS_PROXY_UNSUPPORTED' },
    @{ deploymentMode = 'ailz-integrated'; Code = 'BASIC_FIREWALL_STANDALONE_REQUIRED' },
    @{ deployAzureFirewall = $false; Code = 'EXTERNAL_EGRESS_REQUIRED' },
    @{ hubIntegrationExistingRouteTableResourceId = '/synthetic/rt'; Code = 'FW_AND_EXTERNAL_EGRESS' }
)) {
    $code = $case.Code; $case.Remove('Code')
    $case.networkIsolation = $true
    Reset-Findings
    Test-Topology -P $case
    Assert-True "$code blocks invalid intent before writes" (@($script:Findings | Where-Object { $_.Code -eq $code -and $_.Severity -eq 'FAIL' }).Count -eq 1)
}
Reset-Findings
Test-Topology -P @{ networkIsolation = $true; azureFirewallSku = 'Standard'; enableFirewallDnsProxy = $true }
Assert-True 'Explicit Standard permits DNS proxy without fallback' (@($script:Findings | Where-Object Severity -eq FAIL).Count -eq 0)
foreach ($gateway in $false, $true) {
    foreach ($routing in 'hubIntegrationEgressNextHopIp', 'hubIntegrationExistingRouteTableResourceId') {
        $p = @{ networkIsolation = $true; deploymentMode = 'ailz-integrated'; deployAzureFirewall = $false; hubIntegrationPeeringUseRemoteGateways = $gateway }
        $p[$routing] = if ($routing -eq 'hubIntegrationEgressNextHopIp') { '10.0.0.4' } else { '/synthetic/routes' }
        $selected = @(Get-SubnetSelection -P $p)
        Assert-True "External hub (gateway=$gateway, $routing) owns no local firewall/gateway subnets" (
            @($selected | Where-Object { $_.Managed -and $_.Flag -in 'deployAzureFirewallSubnet', 'deployAzureFirewallManagementSubnet', 'deployGatewaySubnet' }).Count -eq 0
        )
        Reset-Findings
        Test-Topology -P $p
        Assert-True 'Explicit external routing with local firewall disabled is valid' (@($script:Findings | Where-Object Severity -eq FAIL).Count -eq 0)
        $p.deployAzureFirewallSubnet = $true; $p.deployGatewaySubnet = $true; $p.deployAzureFirewallManagementSubnet = $true
        $selected = @(Get-SubnetSelection -P $p)
        Assert-True 'Explicit reservations add only data and gateway, never inactive management' (
            ($selected | Where-Object Flag -eq deployAzureFirewallSubnet).Managed -and
            ($selected | Where-Object Flag -eq deployGatewaySubnet).Managed -and
            -not ($selected | Where-Object Flag -eq deployAzureFirewallManagementSubnet).Managed
        )
        $p.networkIsolation = $false
        Assert-True 'Public mode suppresses even explicit reservations' (@(Get-SubnetSelection -P $p | Where-Object Managed).Count -eq 0)
    }
}
foreach ($prefix in '192.168.3.192/27', '192.168.3.193/26', '192.168.2.0/26', '10.0.0.0/26', 'fd00::/64') {
    Reset-Findings
    Test-LocalCidrSanity -P @{ networkIsolation = $true; azureFirewallManagementSubnetPrefix = $prefix }
    Assert-True "Invalid management CIDR $prefix is blocking" (@($script:Findings | Where-Object Severity -eq FAIL).Count -gt 0)
}
foreach ($flag in 'deployAzureFirewallSubnet', 'deployAzureFirewallManagementSubnet') {
    Reset-Findings
    Test-LocalCidrSanity -P @{ networkIsolation = $true; $flag = $false }
    Assert-True "Explicit false $flag requires BYO, never silently enables creation" (Test-FindingPresent 'SUBNET_REQUIRED_NOT_MANAGED')
}

# --------------------------------------------------------------------------
Write-Host 'Consumer-aware live BYO verification (mocked read-only Azure boundary)' -ForegroundColor Cyan
$originalAzCli = ${function:Invoke-AzCli}
$byoId = '/subscriptions/network-sub/resourceGroups/network-rg/providers/Microsoft.Network/virtualNetworks/shared'
function New-TestSubnet {
    param([string]$Name, [string]$Prefix, [string]$Delegation = '')
    return [pscustomobject]@{
        name = $Name; addressPrefix = $Prefix
        delegations = @(if ($Delegation) { [pscustomobject]@{ serviceName = $Delegation } })
        serviceEndpoints = @(); networkSecurityGroup = $null; routeTable = $null; natGateway = $null; privateEndpoints = @()
    }
}
function Set-TestVnet {
    param([string[]]$Prefixes = @('192.168.0.0/21'), [object[]]$Subnets = @())
    $script:MockVnet = [pscustomobject]@{ name = 'shared'; addressSpace = [pscustomobject]@{ addressPrefixes = $Prefixes }; subnets = $Subnets }
    $script:MockSubnets = @{}
    foreach ($subnet in $Subnets) { $script:MockSubnets["$byoId/subnets/$($subnet.name)"] = $subnet }
    $script:AzCalls = [System.Collections.Generic.List[object]]::new()
    $script:MockRoutes = [pscustomobject]@{ routes = @() }
    $script:MockNsg = [pscustomobject]@{ securityRules = @(); defaultSecurityRules = @(
        [pscustomobject]@{ priority = 65001; direction = 'Outbound'; access = 'Allow'; protocol = '*'; sourceAddressPrefix = '*'; destinationAddressPrefix = 'Internet'; sourcePortRange = '*'; destinationPortRange = '*' }
        [pscustomobject]@{ priority = 65500; direction = 'Outbound'; access = 'Deny'; protocol = '*'; sourceAddressPrefix = '*'; destinationAddressPrefix = '*'; sourcePortRange = '*'; destinationPortRange = '*' }
    ) }
    $script:MissingProvider = ''
    $script:ProviderState = 'Registered'
}
function Invoke-AzCli {
    param([string[]]$Arguments)
    $script:AzCalls.Add($Arguments)
    $command = $Arguments -join ' '
    if ($command -eq 'account show -o json') { return [pscustomobject]@{ id = 'workload-sub' } }
    if ($command -like 'network vnet show --ids *') { return $script:MockVnet }
    if ($command -like 'network vnet subnet show --ids *') { return $script:MockSubnets[$Arguments[5]] }
    if ($command -like 'network nsg show --ids *') { return $script:MockNsg }
    if ($command -like 'network route-table show --ids *') { return $script:MockRoutes }
    if ($command -like 'provider show --namespace *') {
        if ($Arguments[3] -eq $script:MissingProvider) { return $null }
        return [pscustomobject]@{ registrationState = $script:ProviderState }
    }
    throw "Unexpected or non-read-only Azure call in fixture: $command"
}
try {
    $script:SkipAzureLookups = $false
    $byo = @{ networkIsolation = $true; useExistingVNet = $true; deploySubnets = $false; existingVnetResourceId = $byoId }
    $required = @($defaultSubnets | Where-Object Required | ForEach-Object { New-TestSubnet $_.Name $_.Cidr $_.Delegation })
    Set-TestVnet -Subnets $required
    Reset-Findings
    Test-LocalCidrSanity -P $byo
    Test-AzureResources -P $byo
    Assert-True 'Default consumers can reuse verified subnets without writes' (@($script:Findings | Where-Object Severity -eq FAIL).Count -eq 0)
    Assert-True 'Required reuse performs selected subnet lookups using the full cross-subscription ID' (
        @($script:AzCalls | Where-Object { ($_ -join ' ') -like "network vnet subnet show --ids $byoId/subnets/*" }).Count -eq $required.Count
    )
    $managementDefinition = $defaultSubnets | Where-Object Flag -eq deployAzureFirewallManagementSubnet
    foreach ($association in 'networkSecurityGroup', 'natGateway', 'serviceEndpoints', 'delegations') {
        $management = New-TestSubnet 'AzureFirewallManagementSubnet' '192.168.3.192/26'
        $management.$association = if ($association -eq 'delegations') { @(@{ serviceName = 'Microsoft.Web/serverFarms' }) } elseif ($association -eq 'serviceEndpoints') { @(@{ service = 'Microsoft.Storage' }) } else { @{ id = '/synthetic/association' } }
        Reset-Findings
        Test-ReusedSubnetProperties -Definition $managementDefinition -Subnet $management
        Assert-True "BYO management rejects $association" (@($script:Findings | Where-Object Severity -eq FAIL).Count -gt 0)
    }
    $management = New-TestSubnet 'AzureFirewallManagementSubnet' '192.168.3.192/26'
    $management.routeTable = @{ id = '/synthetic/management-routes' }
    foreach ($routes in @(
        $null,
        @{ routes = @(@{ addressPrefix = '0.0.0.0/0'; nextHopType = 'VirtualAppliance' }); disableBgpRoutePropagation = $true },
        @{ routes = @(@{ addressPrefix = '0.0.0.0/0'; nextHopType = 'Internet' }); disableBgpRoutePropagation = $false },
        @{ routes = @(); disableBgpRoutePropagation = $true }
    )) {
        $script:MockRoutes = $routes
        Reset-Findings
        Test-ReusedSubnetProperties -Definition $managementDefinition -Subnet $management
        Assert-True 'Unverified or incompatible BYO management routing fails closed' (@($script:Findings | Where-Object Severity -eq FAIL).Count -eq 1)
    }
    $script:MockRoutes = @{ routes = @(@{ addressPrefix = '0.0.0.0/0'; nextHopType = 'Internet' }); disableBgpRoutePropagation = $true }
    Reset-Findings
    Test-ReusedSubnetProperties -Definition $managementDefinition -Subnet $management
    Assert-True 'Explicit verified BYO management Internet path is accepted' ($script:Findings.Count -eq 0)
    Set-TestVnet -Subnets @($management)
    Reset-Findings
    $managedBasic = $byo.Clone(); $managedBasic.deploySubnets = $true
    Test-ExistingVnetSubnets -P $managedBasic | Out-Null
    Assert-True 'Managed PUT cannot erase a network-owned management route table' (Test-FindingPresent 'FIREWALL_MANAGEMENT_ASSOCIATION_REWRITE')
    foreach ($s in $defaultSubnets | Where-Object Required) {
        Set-TestVnet -Subnets @($required | Where-Object name -ne $s.Name)
        Reset-Findings
        Test-ExistingVnetSubnets -P $byo | Out-Null
        Assert-True "Missing required reused $($s.Name) fails" (Test-FindingPresent 'BYO_SUBNET_MISSING')
    }
    Set-TestVnet -Subnets $required
    $script:MockSubnets.Remove("$byoId/subnets/agent-subnet")
    Reset-Findings
    Test-ExistingVnetSubnets -P $byo | Out-Null
    Assert-True 'Name-only presence cannot silently pass unreadable required subnet properties' (Test-FindingPresent 'BYO_SUBNET_LOOKUP_FAILED')
    $isolatedConsumer = $noConsumer.Clone()
    $isolatedConsumer.useExistingVNet = $true
    $isolatedConsumer.existingVnetResourceId = $byoId
    Set-TestVnet
    Reset-Findings
    Test-ExistingVnetSubnets -P $isolatedConsumer | Out-Null
    Assert-True 'No static required-subnet list when every consumer is disabled' ($script:Findings.Count -eq 0)
    $unusedPlatformSubnet = New-TestSubnet 'powerplatform-subnet' '192.168.4.0/24' 'Microsoft.Web/serverFarms'
    $unusedPlatform = $isolatedConsumer.Clone()
    $unusedPlatform.deployPowerPlatformSubnet = $false
    Set-TestVnet -Subnets @($unusedPlatformSubnet)
    Reset-Findings
    Test-ExistingVnetSubnets -P $unusedPlatform | Out-Null
    Assert-True 'Unused opted-out platform subnet may retain a different delegation' ($script:Findings.Count -eq 0)
    Assert-True 'Unused opted-out subnet needs no per-subnet service-property lookup' (
        @($script:AzCalls | Where-Object { ($_ -join ' ') -like 'network vnet subnet show *' }).Count -eq 0
    )
    $unusedPlatform.deploySubnets = $true
    $unusedPlatformSubnet.addressPrefix = '192.168.0.0/24'
    Set-TestVnet -Subnets @($unusedPlatformSubnet)
    Reset-Findings
    Test-ExistingVnetSubnets -P $unusedPlatform | Out-Null
    Assert-True 'Retained optional same-name range still rejects overlapping managed creation' (Test-FindingPresent 'SUBNET_OVERLAP')
    $unusedPlatformSubnet.addressPrefix = $null
    Set-TestVnet -Subnets @($unusedPlatformSubnet)
    Reset-Findings
    Test-ExistingVnetSubnets -P $unusedPlatform | Out-Null
    Assert-True 'Missing optional retained subnet range fails overlap verification explicitly' (Test-FindingPresent 'BYO_NETWORK_NOT_VERIFIED')
    foreach ($case in @(
        @{ Key = 'deployAiFoundry'; Subnets = @('agent-subnet', 'pe-subnet') },
        @{ Key = 'deployKeyVault'; Subnets = @('application-pe-subnet') },
        @{ Key = 'deployContainerEnv'; Subnets = @('aca-environment-subnet', 'application-pe-subnet') },
        @{ Key = 'deployContainerRegistry'; Subnets = @('devops-build-agents-subnet', 'application-pe-subnet') },
        @{ Key = 'deployJumpbox'; Subnets = @('jumpbox-subnet') },
        @{ Key = 'deployBastion'; Subnets = @('AzureBastionSubnet') },
        @{ Key = 'deployAzureFirewall'; Subnets = @('AzureFirewallSubnet', 'AzureFirewallManagementSubnet') },
        @{ Key = 'deployStorageAccount'; Subnets = @('pe-subnet') },
        @{ Key = 'deploySearchService'; Subnets = @('pe-subnet') },
        @{ Key = 'deploySpeechService'; Subnets = @('pe-subnet') },
        @{ Key = 'deployCosmosDb'; Subnets = @('pe-subnet', 'aca-environment-subnet', 'application-pe-subnet') }
    )) {
        $p = $isolatedConsumer.Clone(); $p[$case.Key] = $true
        $actual = @((Get-SubnetSelection -P $p | Where-Object Required).Name | Sort-Object)
        Assert-True "$($case.Key) requires exactly its referenced subnets" (($actual -join ',') -ceq (($case.Subnets | Sort-Object) -join ','))
    }
    $p = $isolatedConsumer.Clone(); $p.deployAiFoundry = $true; $p.deployAiFoundrySubnet = $false
    Assert-True 'deployAiFoundrySubnet only controls association, not creation ownership' (
        -not (Get-SubnetSelection -P $p | Where-Object Flag -eq deployAgentSubnet).Required
    )
    $p.deploySubnets = $true
    Assert-True 'Agent creation remains independent of Foundry association' ((Get-SubnetSelection -P $p | Where-Object Flag -eq deployAgentSubnet).Managed)
    $p = $isolatedConsumer.Clone(); $p.deployContainerEnv = $true; $p.deployContainerApps = $true
    $p.containerAppsList = @(@{ name = 'frontend' }); $p.publicIngress = @{ enabled = $true }
    Assert-True 'Enabled public ingress requires Application Gateway subnet' ((Get-SubnetSelection -P $p | Where-Object Flag -eq deployAppGatewaySubnet).Required)
    $p = $isolatedConsumer.Clone(); $p.enablePrivateLogAnalytics = $true; $p.deployAppInsights = $true; $p.deployLogAnalytics = $true
    Assert-True 'AMPLS is an application PE subnet consumer' ((Get-SubnetSelection -P $p | Where-Object Flag -eq deployApplicationPeSubnet).Required)
    $p = $byo.Clone(); $p.deploySubnets = $true; $p.deployApplicationPeSubnet = $false
    Set-TestVnet
    Reset-Findings
    Test-ExistingVnetSubnets -P $p | Out-Null
    Assert-True 'Individual opt-out requires live reuse even when global creation is true' (Test-FindingPresent 'BYO_SUBNET_MISSING')
    Set-TestVnet -Subnets @((New-TestSubnet 'application-pe-subnet' '192.168.3.128/26'))
    $script:MockSubnets["$byoId/subnets/application-pe-subnet"] = New-TestSubnet 'application-pe-subnet' '192.168.0.0/24'
    Reset-Findings
    Test-ExistingVnetSubnets -P $p | Out-Null
    Assert-True 'Separately fetched reused ranges, not stale VNet listing, drive overlaps' (Test-FindingPresent 'SUBNET_OVERLAP')
    $p = $custom.Clone(); $p.useExistingVNet = $true; $p.existingVnetResourceId = $byoId
    $p.vnetAddressPrefixes = @('172.16.0.0/16') # Deliberately irrelevant requested BYO space.
    Set-TestVnet -Prefixes @('10.20.0.0/21')
    Reset-Findings
    Test-LocalCidrSanity -P $p
    Test-ExistingVnetSubnets -P $p | Out-Null
    Assert-True 'BYO custom selected ranges use actual address space, not requested/default space' ($script:Findings.Count -eq 0)
    Set-TestVnet -Prefixes @('10.20.0.0/24')
    Reset-Findings
    Test-ExistingVnetSubnets -P $p | Out-Null
    Assert-True 'Actual BYO space rejects overflow instead of silently resizing the VNet' (Test-FindingPresent 'SUBNET_OUTSIDE_VNET')
    Set-TestVnet -Prefixes @('10.20.0.0/21')
    $script:MockVnet.PSObject.Properties.Remove('subnets')
    Reset-Findings
    Test-ExistingVnetSubnets -P $p | Out-Null
    Assert-True 'Omitted BYO subnet collection cannot silently skip overlap verification' (Test-FindingPresent 'BYO_NETWORK_NOT_VERIFIED')
    $p = @{ networkIsolation = $true; useExistingVNet = $true; existingVnetResourceId = $byoId }
    Set-TestVnet -Subnets @($defaultSubnets | ForEach-Object { New-TestSubnet $_.Name $_.Cidr $_.Delegation })
    Reset-Findings
    Test-ExistingVnetSubnets -P $p | Out-Null
    Assert-True 'Managed subnet current range is not counted as a separate overlap' ($script:Findings.Count -eq 0)
    Set-TestVnet -Subnets @((New-TestSubnet 'unrelated-platform-subnet' '192.168.4.0/24'))
    Reset-Findings
    Test-ExistingVnetSubnets -P $p | Out-Null
    Assert-True 'Selected writes cannot overlap retained unrelated BYO subnet ranges' (Test-FindingPresent 'SUBNET_OVERLAP')
    $p = $byo.Clone()
    $customRequired = @($required | ForEach-Object { New-TestSubnet $_.name ($_.addressPrefix.Replace('192.168.', '10.20.')) (@($_.delegations)[0].serviceName) })
    Set-TestVnet -Prefixes @('10.20.0.0/21') -Subnets $customRequired
    Reset-Findings
    Test-LocalCidrSanity -P $p
    Test-ExistingVnetSubnets -P $p | Out-Null
    Assert-True 'Required reused ranges are actual Azure properties, not requested greenfield defaults' (@($script:Findings | Where-Object Severity -eq FAIL).Count -eq 0)
    $badAca = New-TestSubnet 'aca-environment-subnet' '10.20.1.0/28'
    Set-TestVnet -Prefixes @('10.20.0.0/21') -Subnets (@($customRequired | Where-Object name -ne $badAca.name) + @($badAca))
    Reset-Findings
    Test-ExistingVnetSubnets -P $p | Out-Null
    Assert-True 'Required reused ACA actual size is validated' (Test-FindingPresent 'ACA_SUBNET_TOO_SMALL')
    Assert-True 'Required reused ACA actual delegation is validated' (Test-FindingPresent 'ACA_SUBNET_NO_DELEGATION')
    Set-TestVnet
    $script:MockVnet = $null
    Reset-Findings
    Test-AzureResources -P $byo
    Assert-True 'Unreadable/missing selected BYO VNet is a failure, never an advisory success' (
        @($script:Findings | Where-Object { $_.Code -eq 'BYO_VNET_LOOKUP_FAILED' -and $_.Severity -eq 'FAIL' }).Count -eq 1
    )
    $script:SkipAzureLookups = $true
    Reset-Findings
    Test-AzureResources -P $byo
    Assert-True 'Offline bypass cannot report required reused subnet verification as success' (Test-FindingPresent 'BYO_NETWORK_NOT_VERIFIED')
    $script:SkipAzureLookups = $false
    Reset-Findings
    Test-AzureResources -P @{ networkIsolation = $true; useExistingVNet = $true }
    Assert-True 'Missing BYO VNet ID is a mandatory failure' (Test-FindingPresent 'BYO_VNET_NO_ID')
    $allOff = @{ networkIsolation = $true; useExistingVNet = $true; deployNsgs = $false }
    foreach ($s in $defaultSubnets) { $allOff[$s.Flag] = $false }
    Reset-Findings
    Test-Topology -P $allOff
    Assert-True 'NSG detach safeguard allows zero actual selected BYO writes' (Test-FindingAbsent 'BYO_SUBNET_NSG_DETACH')
    $allOff.deployGatewaySubnet = $true
    Reset-Findings
    Test-Topology -P $allOff
    Assert-True 'NSG detach safeguard retains safe rejection for an actual selected BYO write' (Test-FindingPresent 'BYO_SUBNET_NSG_DETACH')

    Write-Host 'Reservation property validators (unit coverage, not unused opt-out prerequisites)' -ForegroundColor Cyan
    function Test-ReservationPropertyValidator {
        param($Definition, $Subnet)
        Test-SubnetRange -Subnet $Definition -Cidr $Subnet.addressPrefix -VnetPrefixes @('192.168.0.0/21') -P @{}
        Test-ReusedSubnetProperties -Definition $Definition -Subnet $Subnet
    }
    $emptyByo = $isolatedConsumer.Clone()
    foreach ($purpose in 'deployGatewaySubnet', 'deployPowerPlatformSubnet', 'deployAiGatewaySubnet') {
        $definition = $defaultSubnets | Where-Object Flag -eq $purpose
        $subnet = New-TestSubnet $definition.Name $definition.Cidr $definition.Delegation
        if ($purpose -eq 'deployAiGatewaySubnet') { $subnet.networkSecurityGroup = @{ id = '/synthetic/nsg' } }
        Set-TestVnet -Subnets @($subnet)
        Reset-Findings
        Test-ExistingVnetSubnets -P $emptyByo | Out-Null
        Assert-True "$purpose valid optional reused reservation passes" ($script:Findings.Count -eq 0)
        Assert-True "$purpose unused reservation does not trigger a service-property lookup" (
            @($script:AzCalls | Where-Object { ($_ -join ' ') -like 'network vnet subnet show *' }).Count -eq 0
        )
        if ($purpose -eq 'deployGatewaySubnet') {
            $subnet.networkSecurityGroup = @{ id = '/synthetic/nsg' }
            $subnet.delegations = @(@{ serviceName = 'Microsoft.Web/serverFarms' })
            $subnet.routeTable = @{ id = '/synthetic/routes' }
            $script:MockRoutes = @{ routes = @(@{ addressPrefix = '0.0.0.0/0'; nextHopType = 'VirtualAppliance' }) }
            Reset-Findings
            Test-ReservationPropertyValidator -Definition $definition -Subnet $subnet
            Assert-True 'GatewaySubnet NSG is forbidden' (Test-FindingPresent 'GATEWAY_SUBNET_NSG_FORBIDDEN')
            Assert-True 'GatewaySubnet delegation is forbidden' (Test-FindingPresent 'BYO_SUBNET_DELEGATION_INVALID')
            Assert-True 'GatewaySubnet default UDR is forbidden' (Test-FindingPresent 'GATEWAY_SUBNET_DEFAULT_ROUTE_FORBIDDEN')
            $script:MockRoutes = $null
            Reset-Findings
            Test-ReservationPropertyValidator -Definition $definition -Subnet $subnet
            Assert-True 'Unreadable GatewaySubnet routes fail mandatory verification' (Test-FindingPresent 'BYO_SUBNET_ROUTES_NOT_VERIFIED')
        } elseif ($purpose -eq 'deployPowerPlatformSubnet') {
            $subnet.addressPrefix = '192.168.4.0/28'
            Reset-Findings
            Test-ReservationPropertyValidator -Definition $definition -Subnet $subnet
            Assert-True 'Reused Power Platform /28 is not rejected as below a false /24 minimum' ($script:Findings.Count -eq 0)
            $subnet.delegations = @(@{ serviceName = 'Microsoft.PowerPlatform/vnetaccesslinks' })
            Reset-Findings
            Test-ReservationPropertyValidator -Definition $definition -Subnet $subnet
            Assert-True 'Power Platform requires enterprisePolicies delegation' (Test-FindingPresent 'BYO_SUBNET_DELEGATION_INVALID')
        } else {
            $subnet.addressPrefix = '192.168.5.0/28'
            Reset-Findings
            Test-ReservationPropertyValidator -Definition $definition -Subnet $subnet
            Assert-True 'Reused APIM actual subnet size must satisfy /27 minimum' (Test-FindingPresent 'SUBNET_TOO_SMALL')
            $subnet.addressPrefix = '192.168.5.0/24'
            $subnet.routeTable = @{ id = '/synthetic/routes' }
            $script:MockRoutes = @{ routes = @(@{ addressPrefix = '0.0.0.0/0'; nextHopType = 'None' }) }
            Reset-Findings
            Test-ReservationPropertyValidator -Definition $definition -Subnet $subnet
            Assert-True 'Blocked/unverifiable reused APIM default-route HTTPS path fails' (Test-FindingPresent 'AI_GATEWAY_KEYVAULT_HTTPS_NOT_VERIFIED')
            $subnet.routeTable = $null
            $subnet.networkSecurityGroup = $null
            Reset-Findings
            Test-ReservationPropertyValidator -Definition $definition -Subnet $subnet
            Assert-True 'Reused APIM integration requires an attached NSG' (Test-FindingPresent 'AI_GATEWAY_NSG_REQUIRED')
            $subnet.networkSecurityGroup = @{ id = '/synthetic/nsg' }
            $script:MockNsg.securityRules = @(@{ priority = 100; direction = 'Outbound'; access = 'Deny'; protocol = 'Tcp'; sourceAddressPrefix = '*'; destinationAddressPrefix = 'AzureKeyVault'; sourcePortRange = '*'; destinationPortRange = '443' })
            Reset-Findings
            Test-ReservationPropertyValidator -Definition $definition -Subnet $subnet
            Assert-True 'Earlier outbound Key Vault HTTPS deny overrides a later allow' (Test-FindingPresent 'AI_GATEWAY_KEYVAULT_HTTPS_NOT_VERIFIED')
            $script:MockNsg = $null
            Reset-Findings
            Test-ReservationPropertyValidator -Definition $definition -Subnet $subnet
            Assert-True 'Unreadable reused APIM NSG cannot silently pass' (Test-FindingPresent 'AI_GATEWAY_KEYVAULT_HTTPS_NOT_VERIFIED')
            $subnet.delegations = @(@{ serviceName = 'Microsoft.ApiManagement/service' })
            $subnet.privateEndpoints = @(@{ id = '/synthetic/private-endpoint' })
            Reset-Findings
            Test-ReservationPropertyValidator -Definition $definition -Subnet $subnet
            Assert-True 'APIM v2 outbound integration uses Microsoft.Web/serverFarms only' (Test-FindingPresent 'BYO_SUBNET_DELEGATION_INVALID')
            Assert-True 'APIM delegated integration subnet cannot hold private endpoints' (Test-FindingPresent 'AI_GATEWAY_PRIVATE_ENDPOINT_FORBIDDEN')
        }
    }
    Write-Host 'Delegation provider prerequisites are selected and subscription-scoped' -ForegroundColor Cyan
    $p = @{ networkIsolation = $true; useExistingVNet = $true; existingVnetResourceId = $byoId }
    Set-TestVnet
    Reset-Findings
    Test-ResourceProviders -P $p
    foreach ($ns in 'Microsoft.PowerPlatform', 'Microsoft.Web', 'Microsoft.App') {
        Assert-True "$ns is queried in actual BYO network subscription" (
            @($script:AzCalls | Where-Object { ($_ -join ' ') -eq "provider show --namespace $ns -o json --subscription network-sub" }).Count -eq 1
        )
    }
    foreach ($ns in 'Microsoft.PowerPlatform', 'Microsoft.Web') {
        $script:MissingProvider = $ns
        Reset-Findings
        Test-ResourceProviders -P $p
        Assert-True "Unverifiable required $ns is FAIL, not WARN" (@($script:Findings | Where-Object { $_.Code -eq 'RP_LOOKUP_FAILED' -and $_.Severity -eq 'FAIL' }).Count -ge 1)
    }
    $script:MissingProvider = ''
    foreach ($state in 'NotRegistered', 'Registering') {
        $script:ProviderState = $state
        Reset-Findings
        Test-ResourceProviders -P $p
        Assert-True "Selected delegated provider '$state' prevents success" (
            @($script:Findings | Where-Object { $_.Severity -eq 'FAIL' -and $_.Code -in 'RP_NOT_REGISTERED', 'RP_REGISTERING' }).Count -gt 0
        )
    }
    foreach ($case in @(
        @{ networkIsolation = $false },
        @{ networkIsolation = $true; deploySubnets = $false },
        @{ networkIsolation = $true; deployPowerPlatformSubnet = $false; deployAiGatewaySubnet = $false }
    )) {
        $delegated = @(Get-RequiredResourceProviders -P $case | Where-Object { $_.Namespace -in 'Microsoft.PowerPlatform', 'Microsoft.Web' })
        Assert-True 'No delegation-only provider prerequisites for unselected subnet writes' ($delegated.Count -eq 0)
    }
    Assert-True 'Mock Azure boundary performed no mutation commands' (@($script:AzCalls | Where-Object { ($_ -join ' ') -match '\b(create|update|delete|register|set)\b' }).Count -eq 0)
} finally {
    ${function:Invoke-AzCli} = $originalAzCli
    $script:SkipAzureLookups = $false
}

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
function Test-CosmosAvailabilityZone {
    param($Location)
    $script:CosmosZoneRegions += @($Location)
}
function Test-ProviderLocation {
    param($ProviderNamespace, $ResourceType, $Location, $DisplayName, $CodePrefix)
    if ($ProviderNamespace -eq 'Microsoft.Search') { $script:SearchProviderLocation = $Location }
    if ($ProviderNamespace -eq 'Microsoft.DocumentDB') {
        $script:CosmosProviderCalls++
        $script:CosmosProviderRegions += @($Location)
    }
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
Write-Host 'Application Cosmos regional checks require an explicit selection' -ForegroundColor Cyan
foreach ($enabled in @($null, $false, $true)) {
    $script:CosmosProviderCalls = 0
    $parameters = @{
        location = 'eastus'; deployAiFoundry = $false
        deploySearchService = $false; deployJumpbox = $false
    }
    if ($null -ne $enabled) { $parameters.deployCosmosDb = $enabled }
    Test-RegionalReadiness -P $parameters
    $expectedCalls = if ($enabled -eq $true) { 1 } else { 0 }
    Assert-True "Application Cosmos '$enabled' selects $expectedCalls regional calls" (
        $script:CosmosProviderCalls -eq $expectedCalls
    )
}

Write-Host 'Foundry Cosmos regional checks remain independent of application storage' -ForegroundColor Cyan
foreach ($case in @(
    @{ application = $false; agents = $true; existing = ''; expected = @('westus3') },
    @{ application = $true; agents = $true; existing = ''; expected = @('eastus', 'westus3') },
    @{ application = $false; agents = $false; existing = ''; expected = @() },
    @{ application = $false; agents = $true; existing = '/existing/cosmos'; expected = @() }
)) {
    $script:CosmosProviderRegions = @()
    $script:CosmosZoneRegions = @()
    Test-RegionalReadiness -P @{
        location = 'westus3'; cosmosLocation = 'eastus'
        deployCosmosDb = $case.application; deployAiFoundry = $true
        deployAAfAgentSvc = $case.agents; aiFoundryCosmosDBAccountResourceId = $case.existing
        deploySearchService = $false; deployJumpbox = $false
    }
    Assert-True 'Cosmos provider readiness covers only selected application and Foundry regions' (
        ($script:CosmosProviderRegions -join ',') -ceq ($case.expected -join ',')
    )
    Assert-True 'Cosmos availability covers only selected application and Foundry regions' (
        ($script:CosmosZoneRegions -join ',') -ceq ($case.expected -join ',')
    )
}

# --------------------------------------------------------------------------
Write-Host ''
Write-Host ("Tests run: $script:TestsRun  Failures: $script:TestFailures") -ForegroundColor Cyan

if ($script:TestFailures -gt 0) { exit 1 } else { exit 0 }
