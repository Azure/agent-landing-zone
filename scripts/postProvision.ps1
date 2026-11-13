# postProvision.ps1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Write-Host "Running post-provision steps..."

# Mirror the selected snapshot into this process only.
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

# Private deployment-host prerequisite (before data-plane configuration)
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:AGENTLZ_REPO_ROOT = $repoRoot
$pathSeparator = [IO.Path]::PathSeparator
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$repoRoot$pathSeparator$($env:PYTHONPATH)" } else { $repoRoot }
Set-Location $repoRoot

function Invoke-PythonModule {
    param([string]$ModuleName, [string[]]$Arguments = @())
    & python -c "import os, runpy, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); sys.argv = ['$ModuleName'] + sys.argv[1:]; runpy.run_module('$ModuleName', run_name='__main__')" @Arguments
}

Invoke-PythonModule -ModuleName 'config.deployment.resource_groups' -Arguments @('--azure-dir', (Join-Path $repoRoot '.azure'), '--bind-only') | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# BEGIN deployment metadata verification
Invoke-PythonModule -ModuleName 'config.deployment.metadata' -Arguments @('--check', '--environment', $env:AZURE_ENV_NAME, '--project-root', $repoRoot)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# END deployment metadata verification
# BEGIN PostgreSQL protection
Invoke-PythonModule -ModuleName 'config.deployment.postgresql' -Arguments @('protect', '--azure-dir', (Join-Path $repoRoot '.azure'))
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# END PostgreSQL protection
Invoke-PythonModule -ModuleName 'config.deployment.private_network' -Arguments @('--stage', 'post-provision')
$networkExitCode = $LASTEXITCODE
if ($networkExitCode -eq 20) {
    Write-Warning "Post-provision configuration explicitly deferred; application setup is incomplete."
    exit 0
}
if ($networkExitCode -ne 0) {
    Write-Error "Private post-provision prerequisites failed. Connect through VPN/VNet and rerun postProvision; configuration has not started." -ErrorAction Continue
    exit $networkExitCode
}
# BEGIN component runtime egress
Invoke-PythonModule -ModuleName 'config.deployment.egress' -Arguments @('--apply')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# END component runtime egress

if ($env:USE_CAPP_API_KEY -match '^(?i:true)$') {
    Write-Warning "Each Container App API key was initialized with resourceToken. Update to a custom API key."
}

# Python owns discovery, typed settings and runtime publication in both shells.
$runtimeMode = if ($env:APP_RUNTIME_CONFIGURATION_MODE) { $env:APP_RUNTIME_CONFIGURATION_MODE } else { 'appConfig' }
# BEGIN runtime configuration publication
if ($runtimeMode -ceq 'appConfig') {
    Invoke-PythonModule -ModuleName 'config.deployment.appconfig'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
# END runtime configuration publication

# Setup Python environment. Keep the existing jumpbox interpreter fallback.
& python -c "import venv" 2>$null
$venvSupported = ($LASTEXITCODE -eq 0)
if ($venvSupported) {
    & python -m venv --without-pip config/.venv_temp
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & config/.venv_temp/Scripts/Activate.ps1
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -UseBasicParsing |
        Select-Object -ExpandProperty Content | & python
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "Python venv is unavailable; using the current interpreter and site-packages."
    & python -m pip --version
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& python -m pip install -r config/requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Placeholder plan and capability-profile roles; no application image builds.
Invoke-PythonModule -ModuleName 'config.deployment.existing_images'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Invoke-PythonModule -ModuleName 'config.appdefinition' -Arguments @('--assign-roles')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($runtimeMode -ceq 'appConfig') {
    Invoke-PythonModule -ModuleName 'config.deployment.outputs'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# Selected services decide applicability using the shared verified setup resolver,
# not the presence of a runtime store endpoint.
foreach ($module in @(
    'config.governance.setup',
    'config.aifoundry.setup',
    'config.containerapps.setup'
)) {
    Invoke-PythonModule -ModuleName $module
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
# BEGIN selected Search setup
# Selection comes from original typed controls, not ambient flags or endpoint
# presence. Required prerequisites remain the selected service's responsibility.
& python -c "import runpy; from config.deployment.setup_settings import load_setup_settings; s = load_setup_settings(); search = s['DEPLOY_SOFTWARE'] == 'true' and s['DEPLOY_SEARCH_SERVICE'] == 'true'; operations = [('config.search.setup', search), ('config.aifoundry.toolbox', search and s['DEPLOY_AF_PROJECT'] == 'true' and s['RETRIEVAL_BACKEND'] == 'foundry_iq')]; [runpy.run_module(module, run_name='__main__') for module, selected in operations if selected]"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# END selected Search setup
Invoke-PythonModule -ModuleName 'config.panel.setup'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "postProvision completed."
