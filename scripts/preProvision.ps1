# predeployment-network-warning.ps1
# Displays a warning to the user if AZURE_NETWORK_ISOLATION is set

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-PythonModule {
    param(
        [Parameter(Mandatory = $true)][string]$ModuleName,
        [string[]]$Arguments = @(),
        [AllowEmptyString()][string]$StandardInput
    )
    $pythonArguments = @('-c', "import os, runpy, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); sys.argv = ['$ModuleName'] + sys.argv[1:]; runpy.run_module('$ModuleName', run_name='__main__')") + $Arguments
    if ($PSBoundParameters.ContainsKey('StandardInput')) {
        $StandardInput | & python @pythonArguments
    } else {
        & python @pythonArguments
    }
}

function Get-AzdEnvironmentJson {
    $arguments = @('env', 'get-values', '--output', 'json')
    if ($env:AZURE_ENV_NAME) { $arguments += @('--environment', $env:AZURE_ENV_NAME) }
    $values = & azd @arguments
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($values -join "`n"))) {
        throw 'Cannot load the selected azd environment; provisioning has not started.'
    }
    return ($values -join "`n")
}

function Import-AzdEnvironment {
    try {
        $azdEnvironment = Get-AzdEnvironmentJson | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Error "Cannot read valid JSON from the selected azd environment; provisioning has not started."
        exit 1
    }
    if ($azdEnvironment -isnot [pscustomobject] -or @($azdEnvironment.PSObject.Properties).Count -eq 0) {
        Write-Error "The selected azd environment must be a nonempty object."
        exit 1
    }
    foreach ($property in $azdEnvironment.PSObject.Properties) {
        if ($property.Name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$' -or
            $property.Value -isnot [string] -or $property.Value.Contains([char]0)) {
            Write-Error "Invalid azd environment key or value; provisioning has not started."
            exit 1
        }
    }
    foreach ($property in $azdEnvironment.PSObject.Properties) {
        Set-Item -Path "Env:$($property.Name)" -Value $property.Value
    }
}

# Locate the repository root by its markers (manifest.json plus azure.yaml),
# not by folder name, so renamed or relocated checkouts keep working.
function Find-RepoRoot([string]$start) {
    $p = (Resolve-Path -LiteralPath $start).Path
    while ($true) {
        if ((Test-Path -LiteralPath (Join-Path $p 'manifest.json')) -and (Test-Path -LiteralPath (Join-Path $p 'azure.yaml'))) { return $p }
        $parent = Split-Path -Parent $p
        if ([string]::IsNullOrEmpty($parent) -or $parent -eq $p) { return $null }
        $p = $parent
    }
}
$projectRoot = Find-RepoRoot $PSScriptRoot
if (-not $projectRoot) {
    Write-Host "Error: Could not locate the repository root (a folder containing manifest.json and azure.yaml)." -ForegroundColor Red
    exit 1
}
$env:AGENTLZ_REPO_ROOT = $projectRoot
$infraDir = Join-Path $projectRoot "infra"
$mainBicep = Join-Path $infraDir "main.bicep"
$manifestSource = Join-Path $projectRoot "manifest.json"

# BEGIN azd environment import
Import-AzdEnvironment
# END azd environment import

# BEGIN infrastructure provider validation
$providerOutput = Invoke-PythonModule -ModuleName 'config.deployment.provider' -Arguments @('--repo-root', $projectRoot)
if ($LASTEXITCODE -ne 0) {
    Write-Error "Infrastructure provider validation failed; provisioning has not started."
    exit $LASTEXITCODE
}
try {
    $providerConfiguration = ($providerOutput -join "`n") | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-Error "Infrastructure provider validation returned invalid JSON."
    exit 1
}
$providerProperty = if ($providerConfiguration -is [pscustomobject]) {
    $providerConfiguration.PSObject.Properties['provider']
} else { $null }
if ($null -eq $providerProperty -or $providerProperty.Value -notin @('bicep', 'terraform')) {
    Write-Error "Infrastructure provider validation returned an unsupported provider."
    exit 1
}
$infrastructureProvider = $providerProperty.Value
# END infrastructure provider validation

#-------------------------------------------------------------------------------
# Application definition: validate and bind before any Azure change.
#-------------------------------------------------------------------------------
$appDefinitionPath = if ($env:AGENTLZ_APP_DEFINITION) { $env:AGENTLZ_APP_DEFINITION } else { Join-Path $projectRoot 'app-definition.json' }
if (-not [IO.Path]::IsPathRooted($appDefinitionPath)) { $appDefinitionPath = Join-Path $projectRoot $appDefinitionPath }
if (Test-Path -LiteralPath $appDefinitionPath -PathType Container) { $appDefinitionPath = Join-Path $appDefinitionPath 'app-definition.json' }
if (-not (Test-Path -LiteralPath $appDefinitionPath -PathType Leaf)) {
    Write-Host "Error: AGENTLZ_APP_DEFINITION points to $appDefinitionPath, which does not exist." -ForegroundColor Red
    exit 1
}
Write-Host "Validating and binding application definition..." -ForegroundColor Cyan
$appDefinitionArguments = @('--validate', $appDefinitionPath, '--bind', '--azure-dir', (Join-Path $projectRoot '.azure'))
if ($env:AZURE_ENV_NAME) { $appDefinitionArguments += @('--env-name', $env:AZURE_ENV_NAME) }
Push-Location $projectRoot
try {
    # Exit codes: 1 invalid definition, 2 binding mismatch (see config/appdefinition/__main__.py).
    Invoke-PythonModule -ModuleName 'config.appdefinition' -Arguments $appDefinitionArguments
    $appDefinitionExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($appDefinitionExitCode -eq 2) {
    Write-Host "Error: Application definition binding failed. No Azure changes were made." -ForegroundColor Red
    exit $appDefinitionExitCode
}
if ($appDefinitionExitCode -ne 0) {
    Write-Host "Error: Application definition validation failed. No Azure changes were made." -ForegroundColor Red
    exit $appDefinitionExitCode
}

# Terraform records ownership without creating groups; Bicep retains its bootstrap.
Write-Host "Preparing workload resource-group destinations..." -ForegroundColor Cyan
$resourceGroupArguments = @('--azure-dir', (Join-Path $projectRoot '.azure'))
if ($env:AZURE_ENV_NAME) { $resourceGroupArguments += @('--env-name', $env:AZURE_ENV_NAME) }
Push-Location $projectRoot
try {
    if ($infrastructureProvider -eq 'terraform') {
        $resourceGroupArguments += @('--environment', '-')
        $environmentJson = Get-AzdEnvironmentJson
        $resourceGroupOutput = Invoke-PythonModule -ModuleName 'config.deployment.terraform_groups' -Arguments $resourceGroupArguments -StandardInput $environmentJson
    } else {
        $resourceGroupOutput = Invoke-PythonModule -ModuleName 'config.deployment.resource_groups' -Arguments $resourceGroupArguments
    }
    $resourceGroupExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($resourceGroupExitCode -ne 0) {
    Write-Host "Error: Resource-group destination preparation failed. Review the reported configuration or access error; no automatic cleanup is performed." -ForegroundColor Red
    exit $resourceGroupExitCode
}
$resourceGroups = ($resourceGroupOutput -join "`n") | ConvertFrom-Json
foreach ($entry in @{
    AZURE_RESOURCE_GROUP = $resourceGroups.foundry
    AZURE_APP_RESOURCE_GROUP = $resourceGroups.application
    AZURE_NETWORK_RESOURCE_GROUP = $resourceGroups.network
}.GetEnumerator()) {
    if ($null -ne $entry.Value) {
        Set-Item -Path "Env:$($entry.Key)" -Value $entry.Value
    }
}
$env:CREATE_RESOURCE_GROUPS = "$($resourceGroups.create_resource_groups)".ToLowerInvariant()

#-------------------------------------------------------------------------------
# Infrastructure is repository-owned source under infra/ (no submodule).
#-------------------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $manifestSource)) {
    Write-Host "Error: manifest.json is required to resolve release pins." -ForegroundColor Red
    exit 1
}
if ($infrastructureProvider -eq 'bicep' -and -not (Test-Path -LiteralPath $mainBicep -PathType Leaf)) {
    Write-Host "Error: infra/main.bicep was not found. The infrastructure is part of this repository; restore infra/ from source control." -ForegroundColor Red
    exit 1
}

$parameterSource = Join-Path $projectRoot "main.parameters.json"
$parameterDestination = Join-Path $infraDir "main.parameters.json"

# ADR-0001 rev. 5: resolve and materialize the Agent Landing Zone deployment topology
# (fresh default, sticky existing/persisted-classic, explicit override, or a
# fail-closed error with migration guidance on conflicting persisted signals)
# before composing main.parameters.json. Materializing DEPLOYMENT_TOPOLOGY
# (and the paired legacy flags) into both the process environment and the azd
# environment here is what lets preDeploy/postProvision read back the exact
# same decision later via 'config.deployment.topology --describe', with no
# further Azure CLI lookups and no duplicated detection logic.
Write-Host "Resolving Agent Landing Zone deployment topology..." -ForegroundColor Cyan
Push-Location $projectRoot
try {
    $topologyOutput = Invoke-PythonModule -ModuleName 'config.deployment.topology'
    $topologyExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($topologyExitCode -ne 0) {
    Write-Host "Error: Agent Landing Zone deployment topology resolution failed." -ForegroundColor Red
    exit $topologyExitCode
}
$azureEnvName = $env:AZURE_ENV_NAME
Push-Location $projectRoot
try {
    $firewallOutput = Invoke-PythonModule -ModuleName 'config.deployment.firewall' -Arguments @('--input', $parameterSource)
    $firewallExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($firewallExitCode -ne 0) {
    Write-Error "Firewall input resolution failed; provisioning has not started."
    exit $firewallExitCode
}
foreach ($line in (@($topologyOutput) + @($firewallOutput))) {
    if ("$line" -match '^([^=]+)=(.*)$') {
        $name = $matches[1]
        $value = $matches[2]
        Set-Item -Path "Env:$name" -Value $value
        if ($azureEnvName) {
            & azd env set $name $value --environment $azureEnvName --no-prompt | Out-Null
        } else {
            & azd env set $name $value --no-prompt | Out-Null
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error: Failed to persist resolved topology setting $name." -ForegroundColor Red
            exit $LASTEXITCODE
        }
    }
}

Write-Host "Composing Agent Landing Zone deployment mode..." -ForegroundColor Cyan
Push-Location $projectRoot
try {
    $hostedSourceCommit = (
        Get-Content -LiteralPath $manifestSource -Raw |
            ConvertFrom-Json
    ).components |
        Where-Object { $_.name -like '*-orchestrator' } |
        Select-Object -ExpandProperty commit -First 1
    if ($infrastructureProvider -eq 'terraform') {
        $terraformDirectory = Join-Path $projectRoot $providerConfiguration.path
        $terraformParameterDestination = Join-Path $terraformDirectory "$($providerConfiguration.module).tfvars.json"
        $environmentJson = Get-AzdEnvironmentJson
        $null = Invoke-PythonModule -ModuleName 'config.deployment.terraform_inputs' -Arguments @(
            '--input', $parameterSource,
            '--environment', '-',
            '--app-definition', $appDefinitionPath,
            '--output', $terraformParameterDestination,
            '--diagnostic-output', $parameterDestination,
            '--resource-group-ownership', $resourceGroups.ownershipFile,
            '--hosted-source-commit', $hostedSourceCommit
        ) -StandardInput $environmentJson
    } else {
        Invoke-PythonModule -ModuleName 'config.deployment.composition' -Arguments @(
            '--input', $parameterSource,
            '--output', $parameterDestination,
            '--hosted-source-commit', $hostedSourceCommit
        )
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Agent Landing Zone deployment mode composition failed." -ForegroundColor Red
        exit $LASTEXITCODE
    }
    if ($infrastructureProvider -eq 'terraform') { Import-AzdEnvironment }
} finally {
    Pop-Location
}

# BEGIN component runtime egress
Invoke-PythonModule -ModuleName 'config.deployment.egress' -Arguments @('--plan', '--save')
if ($LASTEXITCODE -ne 0) { Write-Error "Component egress planning failed; provisioning has not started."; exit $LASTEXITCODE }
# END component runtime egress

# The composed infra/main.parameters.json is environment-specific; hide local
# regeneration from git status so the committed seed stays untouched.
if (Get-Command git -ErrorAction SilentlyContinue) {
    try {
        $inWorkTree = (& git -C $projectRoot rev-parse --is-inside-work-tree 2>$null)
        if ($LASTEXITCODE -eq 0 -and $inWorkTree -eq 'true') {
            & git -C $projectRoot ls-files --error-unmatch 'infra/main.parameters.json' *> $null
            if ($LASTEXITCODE -eq 0) {
                & git -C $projectRoot update-index --skip-worktree 'infra/main.parameters.json' *> $null
            }
        }
    } catch {
        Write-Host "Note: could not mark infra/main.parameters.json as skip-worktree; it may appear as modified in git status." -ForegroundColor Yellow
    }
    $global:LASTEXITCODE = 0
}

# Helper to match truthy values (1, true, t)
function Test-Truthy($value) {
    if (-not $value) { return $false }
    return $value -match '^(1|true|t)$'
}

# Agent Landing Zone regional readiness preflight
$regionalPreflightScript = Join-Path $PSScriptRoot "Invoke-RegionalPreflight.ps1"
if ((Test-Path $regionalPreflightScript) -and (-not (Test-Truthy $env:PREFLIGHT_SKIP)) -and (-not (Test-Truthy $env:AGENTLZ_REGIONAL_PREFLIGHT_SKIP))) {
    Write-Host "Running Agent Landing Zone regional preflight..." -ForegroundColor Cyan
    & pwsh -NoProfile -File $regionalPreflightScript -ProjectRoot $projectRoot -ParameterFile $parameterDestination
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Agent Landing Zone regional preflight failed. Fix the reported blockers, or set AGENTLZ_REGIONAL_PREFLIGHT_SKIP=true to bypass only this check." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

# AI Landing Zone v2.0.4+ preflight validation
# https://github.com/Azure/bicep-ptn-aiml-landing-zone/blob/v2.0.4/scripts/Invoke-PreflightChecks.ps1
# Covers parameter/topology/BYO/IP checks plus regional readiness (subscription drift,
# provider/location, AI Search & Cosmos capacity warnings, jumpbox VM SKU, model quota).
$preflightScript = Join-Path $infraDir "scripts/Invoke-PreflightChecks.ps1"
if ((Test-Path $preflightScript) -and (-not (Test-Truthy $env:PREFLIGHT_SKIP))) {
    Write-Host "Running landing-zone preflight checks..." -ForegroundColor Cyan
    & pwsh -NoProfile -File $preflightScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Preflight checks failed. Fix the reported parameter issues, or set PREFLIGHT_SKIP=true to bypass." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

# 1) Network Isolation Warning
# Accept both historical and current variable names
$networkIsolation = $env:AZURE_NETWORK_ISOLATION
if (-not $networkIsolation) { $networkIsolation = $env:NETWORK_ISOLATION }
$skipWarning = $env:AZURE_SKIP_NETWORK_ISOLATION_WARNING

if (Test-Truthy $skipWarning) { exit 0 }

if (Test-Truthy $networkIsolation) {
    Write-Host "Warning!" -ForegroundColor Yellow -NoNewline
    Write-Host " Network isolation is enabled." -ForegroundColor Yellow
    Write-Host " - After provisioning, you must switch to the" -NoNewline
    Write-Host " Jumpbox / Bastion" -ForegroundColor Green -NoNewline
    Write-Host " to continue deploying components." -ForegroundColor Yellow
    Write-Host " - Infrastructure will only be reachable from within the private network.`n" -ForegroundColor Yellow

    $prompt = "? Continue with Zero Trust provisioning? [Y/n]: "
    Write-Host $prompt -ForegroundColor Blue -NoNewline
    $confirmation = Read-Host
    if ($confirmation -and $confirmation -notin 'Y','y') { exit 1 }
}

exit 0
