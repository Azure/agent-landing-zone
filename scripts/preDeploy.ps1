# Works from the Agent Landing Zone repository root or any subfolder
# PowerShell 7+ recommended
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
$ProgressPreference = 'SilentlyContinue'   # hide PS progress bars

function Docker-Ready {
  try {
    $null = & docker info 2>$null
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}

function Find-RepoRoot([string]$start) {
  $p = (Resolve-Path $start).Path
  while ($true) {
    if ((Test-Path -LiteralPath (Join-Path $p 'manifest.json')) -and (Test-Path -LiteralPath (Join-Path $p 'azure.yaml'))) { return $p }
    $parent = Split-Path -Parent $p
    if ($parent -eq $p -or [string]::IsNullOrEmpty($parent)) { break }
    $p = $parent
  }
  return $null
}

function Tag-Exists([string]$repo, [string]$tag) {
  $o = git ls-remote --tags $repo $tag 2>$null
  return ($LASTEXITCODE -eq 0 -and $o)
}

function Branch-Exists([string]$repo, [string]$branch) {
  $o = git ls-remote --heads $repo $branch 2>$null
  return ($LASTEXITCODE -eq 0 -and $o)
}

function Get-AzdEnv([string]$projectPath) {
  if (-not (Get-Command azd -ErrorAction SilentlyContinue)) {
    Write-Error "azd is required to load the selected environment."
    exit 1
  }
  Push-Location $projectPath
  try {
    $out = & azd env get-values --output json
    $envExitCode = $LASTEXITCODE
  } finally {
    Pop-Location
  }
  if ($envExitCode -ne 0 -or -not $out) {
    Write-Error "Could not load the selected azd environment; refusing to deploy with stale or arbitrary environment values."
    exit 1
  }
  try {
    $values = ($out -join "`n") | ConvertFrom-Json -ErrorAction Stop
  } catch {
    Write-Error "Invalid azd environment JSON; refusing to deploy."
    exit 1
  }
  if ($values -isnot [pscustomobject] -or @($values.PSObject.Properties).Count -eq 0) {
    Write-Error "The selected azd environment must be a nonempty object."
    exit 1
  }
  foreach ($prop in $values.PSObject.Properties) {
    if ($prop.Name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$' -or $prop.Value -isnot [string] -or $prop.Value.Contains([char]0)) {
      Write-Error "Invalid azd environment key or value; refusing to deploy."
      exit 1
    }
  }
  return $values
}

function ResourceGroup-Exists([string]$rg, [string]$subscription) {
  if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Error "Azure CLI (az) not found; cannot verify resource group '$rg'."
    return $false
  }
  $args = @('group','exists','-n', $rg)
  if ($subscription) { $args += @('--subscription', $subscription) }
  $result = & az @args 2>$null
  return ($LASTEXITCODE -eq 0 -and ($result.Trim().ToLower() -eq 'true'))
}

# Prefer pwsh (PS7); fall back to Windows PowerShell only if pwsh is unavailable
$psExe = (Get-Command pwsh -ErrorAction SilentlyContinue)?.Source
if (-not $psExe) { $psExe = (Get-Command powershell -ErrorAction Stop).Source }

$start    = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$repoRoot = Find-RepoRoot $start
if (-not $repoRoot) { Write-Error "Run this from inside the Agent Landing Zone repository (a folder containing manifest.json and azure.yaml)."; exit 1 }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Error "Git not found in PATH."; exit 1 }
$pathSeparator = [IO.Path]::PathSeparator
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$repoRoot$pathSeparator$($env:PYTHONPATH)" } else { $repoRoot }
$env:AGENTLZ_REPO_ROOT = $repoRoot

function Invoke-PythonModule {
  param(
    [Parameter(Mandatory = $true)][string]$ModuleName,
    [string[]]$Arguments = @()
  )
  if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python is required for deployment prerequisites."
    exit 1
  }
  & python -c "import os, runpy, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); sys.argv = ['$ModuleName'] + sys.argv[1:]; runpy.run_module('$ModuleName', run_name='__main__')" @Arguments
}

$manifestPath = Join-Path $repoRoot 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { Write-Error "manifest.json not found at $manifestPath"; exit 1 }

$manifest   = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$baseDir    = Split-Path -Parent $repoRoot
$dotAzure   = Join-Path $repoRoot '.azure'
$globalEnv  = Get-AzdEnv -projectPath $repoRoot
$globalRG   = $globalEnv.AZURE_RESOURCE_GROUP
$globalSub  = $globalEnv.AZURE_SUBSCRIPTION_ID
foreach ($prop in $globalEnv.PSObject.Properties) {
  Set-Item -Path "Env:$($prop.Name)" -Value "$($prop.Value)"
}

# Foundation guard (first step, before any Azure change): azd deploy only
# deploys applications onto a foundation created by azd provision.
$foundationMissing = (-not $globalRG)
if ($foundationMissing) {
  Write-Error "The foundation is not provisioned. Run azd provision first."
  exit 3
}
Invoke-PythonModule -ModuleName 'config.deployment.resource_groups' -Arguments @('--azure-dir', $dotAzure, '--check') | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error "Resource-group binding check failed. No changes were made."; exit 3 }
# BEGIN deployment metadata verification
Invoke-PythonModule -ModuleName 'config.deployment.metadata' -Arguments @('--check', '--environment', $env:AZURE_ENV_NAME, '--project-root', $repoRoot)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# END deployment metadata verification

# Re-validate the application definition and compare it with the binding.
$appDefinitionPath = if ($globalEnv.AGENTLZ_APP_DEFINITION) { "$($globalEnv.AGENTLZ_APP_DEFINITION)" } elseif ($env:AGENTLZ_APP_DEFINITION) { $env:AGENTLZ_APP_DEFINITION } else { Join-Path $repoRoot 'app-definition.json' }
if (-not [IO.Path]::IsPathRooted($appDefinitionPath)) { $appDefinitionPath = Join-Path $repoRoot $appDefinitionPath }
if (Test-Path -LiteralPath $appDefinitionPath -PathType Container) { $appDefinitionPath = Join-Path $appDefinitionPath 'app-definition.json' }
if (-not (Test-Path -LiteralPath $appDefinitionPath -PathType Leaf)) {
  Write-Error "AGENTLZ_APP_DEFINITION points to $appDefinitionPath, which does not exist."
  exit 1
}
$boundAppId = "$($globalEnv.AGENTLZ_APP_ID)"
if (-not $boundAppId) {
  Write-Error "This environment is not bound to an application. Run azd provision first."
  exit 1
}
$appDefinitionArguments = @('--validate', $appDefinitionPath, '--check-binding', '--azure-dir', $dotAzure)
if ($globalEnv.AZURE_ENV_NAME) { $appDefinitionArguments += @('--env-name', "$($globalEnv.AZURE_ENV_NAME)") }
Push-Location $repoRoot
try {
  # Exit codes: 1 invalid definition, 2 binding mismatch (message names both ids).
  Invoke-PythonModule -ModuleName 'config.appdefinition' -Arguments $appDefinitionArguments
  $appDefinitionExitCode = $LASTEXITCODE
} finally {
  Pop-Location
}
if ($appDefinitionExitCode -eq 2) { Write-Error "Application definition binding check failed. No changes were made."; exit $appDefinitionExitCode }
if ($appDefinitionExitCode -ne 0) { Write-Error "Application definition validation failed. No changes were made."; exit $appDefinitionExitCode }
$appDefinition = Get-Content -LiteralPath $appDefinitionPath -Raw | ConvertFrom-Json
$appDefinitionDir = Split-Path -Parent (Resolve-Path -LiteralPath $appDefinitionPath).Path
$definitionComponents = @($appDefinition.components)

function Get-ManifestComponentForDefinition([string]$componentName) {
  foreach ($mc in $manifest.components) {
    if ("$($mc.name)" -eq $componentName -or "$($mc.name)".EndsWith("-$componentName")) { return $mc }
  }
  return $null
}
$definitionManifestNames = @(
  foreach ($dc in $definitionComponents) {
    $mc = Get-ManifestComponentForDefinition "$($dc.name)"
    if ($mc) { "$($mc.name)" }
  }
)

# Make azd outputs available to component deploy scripts (and to the topology
# read-back below). In network-isolated deployments the jumpbox intentionally
# has no Docker, so components need ACR_TASK_AGENT_POOL/NETWORK_ISOLATION to
# select remote ACR builds.
foreach ($prop in $globalEnv.PSObject.Properties) {
  if ($null -ne $prop.Value) {
    Set-Item -Path "Env:$($prop.Name)" -Value "$($prop.Value)"
  }
}

# ADR-0001 rev. 5: read back the deployment topology that scripts/preProvision
# already resolved and materialized into the azd environment (mirrored into
# process env above). preDeploy must never re-derive the fresh/existing/sticky
# decision independently -- config.deployment.topology --describe performs no
# Azure CLI lookups; canonical host/mode and feature flags are shared by all hooks.
Push-Location $repoRoot
try {
  $topologyJson = Invoke-PythonModule -ModuleName 'config.deployment.topology' -Arguments @('--describe')
  $topologyExitCode = $LASTEXITCODE
} finally {
  Pop-Location
}
if ($topologyExitCode -ne 0 -or -not $topologyJson) {
  Write-Error "Failed to resolve native application selection. Ensure scripts/preProvision ran successfully before azd deploy."
  exit 1
}
$topologyInfo = ("$topologyJson").Trim() | ConvertFrom-Json
$hostedMode = $topologyInfo.ORCHESTRATION_HOST -ceq 'hosted'
$deploymentMode = "$($topologyInfo.ORCHESTRATION_HOST)/$($topologyInfo.APPLICATION_MODE)"
$selectedComponents = @($topologyInfo.components)
Write-Host "Native application selection: $deploymentMode" -ForegroundColor Cyan

$networkIsolation = "$($globalEnv.NETWORK_ISOLATION)".ToLowerInvariant() -eq 'true'
Invoke-PythonModule -ModuleName 'config.deployment.private_network' -Arguments @('--stage', 'pre-deploy')
$networkExitCode = $LASTEXITCODE
if ($networkExitCode -ne 0) {
  Write-Error "Private deployment prerequisites failed. Use a VPN/VNet-connected host; RUN_FROM_JUMPBOX is not a connectivity bypass." -ErrorAction Continue
  exit $networkExitCode
}

# BEGIN component runtime egress
Invoke-PythonModule -ModuleName 'config.deployment.egress' -Arguments @('--apply')
if ($LASTEXITCODE -ne 0) { Write-Error "Component egress reconciliation failed; application deployment has not started."; exit $LASTEXITCODE }
# END component runtime egress

# Under network isolation the registry has no public access, so ACR Task builds
# only work through the in-VNet agent pool (#741). Fail before touching any app.
$buildModeOverride = "$($env:BUILD_MODE)".ToLowerInvariant()
if ($networkIsolation -and -not $globalEnv.ACR_TASK_AGENT_POOL -and $buildModeOverride -ne 'local') {
  Write-Error ("NETWORK_ISOLATION=true but no ACR Task agent pool was provisioned (ACR_TASK_AGENT_POOL is empty). " +
    "Run 'azd env set DEPLOY_ACR_TASK_AGENT_POOL true' and 'azd provision', or set BUILD_MODE=local on a VNet-connected host with Docker.") -ErrorAction Continue
  exit 1
}

if (-not (Docker-Ready)) {
  if ($networkIsolation -or $globalEnv.ACR_TASK_AGENT_POOL) {
    Write-Host "Docker is not available; component deploys will use ACR remote builds." -ForegroundColor Yellow
  } else {
    Write-Host "Docker daemon is not running; component deploy scripts will fall back to ACR remote builds where supported." -ForegroundColor Yellow
  }
}

$hadErrors = $false

$nativeMode = [bool]$topologyInfo.bundled_application
# BEGIN optional MCP lifecycle
if ($nativeMode) {
  Invoke-PythonModule -ModuleName 'config.deployment.mcp' -Arguments @('--deploy')
  if ($LASTEXITCODE -ne 0) { Write-Error "MCP preparation/deployment failed; consumers have not been deployed."; exit 1 }
  $globalEnv = Get-AzdEnv -projectPath $repoRoot
  foreach ($prop in $globalEnv.PSObject.Properties) {
    Set-Item -Path "Env:$($prop.Name)" -Value "$($prop.Value)"
  }
}
# END optional MCP lifecycle
# BEGIN native application lifecycle
if ($nativeMode) {
  Invoke-PythonModule -ModuleName 'config.deployment.native_deploy' -Arguments @('--deploy')
  if ($LASTEXITCODE -ne 0) { Write-Error "Native application preparation/publication failed; component deployment has not started."; exit 1 }
  # Read the exact persisted publication/backend outputs, not process defaults.
  $globalEnv = Get-AzdEnv -projectPath $repoRoot
  foreach ($prop in $globalEnv.PSObject.Properties) {
    Set-Item -Path "Env:$($prop.Name)" -Value "$($prop.Value)"
  }
  if (-not $env:APP_RUNTIME_CONFIGURATION_MODE -or $env:APP_RUNTIME_CONFIGURATION_MODE -ceq 'appConfig') {
    Invoke-PythonModule -ModuleName 'config.deployment.appconfig' -Arguments @('--require-hosted-endpoint')
    if ($LASTEXITCODE -ne 0) { Write-Error "Native runtime settings could not be published."; exit 1 }
  }
}
# END native application lifecycle

foreach ($c in $manifest.components) {
  $name = $c.name
  if ($nativeMode -and $name -eq 'agent-app-mcp') { continue }
  if ($name -notin $selectedComponents) {
    Write-Host "$name is not deployed in $deploymentMode mode." -ForegroundColor Yellow
    continue
  }
  if ($name -notin $definitionManifestNames) {
    Write-Host "$name is not part of application '$($appDefinition.id)'." -ForegroundColor Yellow
    continue
  }
  $repo = $c.repo
  $expectedCommit = "$($c.commit)"
  $desiredTag    = if ($c.tag) { $c.tag } else { $manifest.release }
  $desiredBranch = $c.branch  # explicit branch only

  # Ref resolution (no implicit fallback)
  $refType = $null; $ref = $null
  if ($desiredTag) {
    if (Tag-Exists $repo $desiredTag) { $refType = 'tag'; $ref = $desiredTag }
    else {
      Write-Warning ("{0}: tag '{1}' not found. Skipping." -f $name, $desiredTag)
      if ($hostedMode) { $hadErrors = $true }
      continue
    }
  } elseif ($desiredBranch) {
    if (Branch-Exists $repo $desiredBranch) { $refType = 'branch'; $ref = $desiredBranch }
    else {
      Write-Warning ("{0}: branch '{1}' not found. Skipping." -f $name, $desiredBranch)
      if ($hostedMode) { $hadErrors = $true }
      continue
    }
  } else {
    Write-Warning ("{0}: neither tag nor branch specified. Skipping." -f $name)
    if ($hostedMode) { $hadErrors = $true }
    continue
  }

  # Target folder (sibling to the repository root)
  $target = Join-Path $baseDir $name
  Write-Host ("Deploying {0} ({1}:{2}) -> {3}" -f $name, $refType, $ref, $target) -ForegroundColor Cyan

  if (Test-Path -LiteralPath $target) {
    Write-Host ("  ℹ️  '{0}' already exists at {1}, verifying pin." -f $name, $target) -ForegroundColor Yellow
  } else {
    try {
      if ($refType -eq 'branch') {
        git clone --depth 1 --branch $ref --no-progress -q $repo $target 1>$null 2>$null
        if ($LASTEXITCODE -ne 0) {
          throw "$name`: git clone failed."
        }
      } else {
        git clone --depth 1 --no-progress -q $repo $target 1>$null 2>$null
        if ($LASTEXITCODE -ne 0) {
          throw "$name`: git clone failed."
        }
        git -C $target fetch --tags --force --depth 1 --no-progress -q origin $ref 1>$null 2>$null
        if ($LASTEXITCODE -ne 0) {
          throw "$name`: git fetch for tag $ref failed."
        }
        git -C $target -c advice.detachedHead=false checkout -q -f $ref 1>$null 2>$null
        if ($LASTEXITCODE -ne 0) {
          throw "$name`: git checkout for tag $ref failed."
        }
      }
      git config --global --add safe.directory ($target -replace '\\','/') 1>$null 2>$null
    }
    catch {
      Write-Error ("{0}: git operation failed. {1}" -f $name, $_.Exception.Message)
      $hadErrors = $true
      continue
    }
  }

  if ($expectedCommit) {
    $actualCommitOutput = & git -C $target rev-parse HEAD 2>$null
    $revParseExitCode = $LASTEXITCODE
    $actualCommit = if ($actualCommitOutput) { "$actualCommitOutput".Trim() } else { '' }
    if ($revParseExitCode -ne 0 -or $actualCommit -ne $expectedCommit) {
      Write-Error "$name must resolve to $expectedCommit but $target is at $actualCommit. Remove or relocate the stale sibling checkout."
      $hadErrors = $true
      continue
    }
  }

  if ($nativeMode) {
    Invoke-PythonModule -ModuleName 'config.deployment.native_deploy' -Arguments @('--validate-component-source', $target, '--component', $name)
    if ($LASTEXITCODE -ne 0) { Write-Error "$name is not a compatible native component; deployment has not started."; $hadErrors = $true; continue }
  }

  # Copy shared azd env into the freshly cloned project
  if (Test-Path -LiteralPath $dotAzure) {
    Copy-Item $dotAzure $target -Recurse -Force -Container
  }

  # Run child deploy.ps1 from the component ROOT so 'docker build .' sees the Dockerfile there
  $deployPs = Join-Path $target 'scripts\deploy.ps1'
  if (Test-Path -LiteralPath $deployPs) {
    $logDir = Join-Path $target '.logs'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $log = Join-Path $logDir ("deploy_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date))

    Write-Host ("Running child deploy in {0}: scripts\deploy.ps1 -> {1}" -f $target, (Split-Path $log -Leaf))
    try {
      Push-Location $target
      $null = (& $psExe -NoProfile -ExecutionPolicy Bypass -File "scripts\deploy.ps1" 2>&1 | Tee-Object -FilePath $log)
      $exit = $LASTEXITCODE
      Pop-Location
      if ($exit -ne 0) {
        Write-Error ("{0}: deploy script failed with exit code {1}. See log: {2}" -f $name, $exit, $log)
        $hadErrors = $true
      } else {
        Write-Host ("{0}: deploy script finished. Log: {1}" -f $name, $log) -ForegroundColor Green
      }
    }
    catch {
      try { Pop-Location } catch {}
      Write-Error ("{0}: error launching deploy script. {1} (log: {2})" -f $name, $_.Exception.Message, $log)
      $hadErrors = $true
    }
  } else {
    Write-Host ("{0}: no scripts\deploy.ps1 found, skipping child deploy." -f $name)
    if ($hostedMode) { $hadErrors = $true }
  }
}

# Components from the application definition that are not release-managed
# (manifest.json) components share the definition folder's azd project.
foreach ($dc in $definitionComponents) {
  $componentName = "$($dc.name)"
  if ($nativeMode -and (Get-ManifestComponentForDefinition $componentName)) { continue }
  $componentPath = Join-Path $appDefinitionDir "$($dc.path)"
  if (-not (Test-Path -LiteralPath (Join-Path $appDefinitionDir 'azure.yaml') -PathType Leaf)) {
    Write-Error "The app folder $appDefinitionDir must contain its own azure.yaml."
    $hadErrors = $true
    continue
  }
  $sourceCommit = "$($dc.source.commit)"
  $sourceDigest = "$($dc.source.imageDigest)"
  if ($sourceCommit) {
    $actualCommit = "$(& git -C $componentPath rev-parse HEAD 2>$null)".Trim()
    if ($LASTEXITCODE -ne 0 -or $actualCommit -ne $sourceCommit) {
      Write-Error "$componentName must resolve to $sourceCommit but $componentPath is at '$actualCommit'."
      $hadErrors = $true
      continue
    }
  }
  if (Test-Path -LiteralPath $dotAzure) {
    Copy-Item $dotAzure $appDefinitionDir -Recurse -Force -Container
  }
  Write-Host ("Deploying {0} ({1}) from {2}" -f $componentName, $dc.kind, $componentPath) -ForegroundColor Cyan
  Push-Location $appDefinitionDir
  try {
    if ($sourceDigest) {
      & azd env set AGENTLZ_IMAGE_DIGEST $sourceDigest --environment "$($globalEnv.AZURE_ENV_NAME)" --no-prompt | Out-Null
      if ($LASTEXITCODE -ne 0) { Write-Error "${componentName}: failed to pin image digest."; $hadErrors = $true; continue }
    }
    if ("$($dc.kind)" -eq 'azure.ai.agent') {
      $smokeProtocol = (& python -c "import os, runpy, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); sys.argv = ['config.deployment.hosted'] + sys.argv[1:]; runpy.run_module('config.deployment.hosted', run_name='__main__')" --service-protocol (Join-Path $appDefinitionDir 'azure.yaml') --service-name $componentName | Out-String).Trim()
      if ($LASTEXITCODE -ne 0) { Write-Error "${componentName}: cannot resolve the greeting protocol."; $hadErrors = $true; continue }
      # Custom images use the shared immutable/private build path, not the
      # manifest-pinned orchestrator's derived hosted entrypoint.
      & azd env set FOUNDRY_PROJECT_ENDPOINT "$($globalEnv.AZURE_AI_PROJECT_ENDPOINT)" --environment "$($globalEnv.AZURE_ENV_NAME)" --no-prompt | Out-Null
      if ($LASTEXITCODE -ne 0) { Write-Error "${componentName}: failed to set the Foundry endpoint."; $hadErrors = $true; continue }
      & azd env set AZURE_AI_PROJECT_ID "$($globalEnv.AZURE_AI_PROJECT_RESOURCE_ID)" --environment "$($globalEnv.AZURE_ENV_NAME)" --no-prompt | Out-Null
      if ($LASTEXITCODE -ne 0) { Write-Error "${componentName}: failed to set the Foundry project ID."; $hadErrors = $true; continue }
      & python -c "import os, runpy, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); sys.argv = ['config.deployment.custom_application'] + sys.argv[1:]; runpy.run_module('config.deployment.custom_application', run_name='__main__')" --definition $appDefinitionPath --service $componentName --environment "$($globalEnv.AZURE_ENV_NAME)"
      if ($LASTEXITCODE -ne 0) { Write-Error "${componentName}: hosted agent deployment failed."; $hadErrors = $true; continue }
      $smokePayloadPath = Join-Path ([IO.Path]::GetTempPath()) "agentlz-agent-smoke-$([guid]::NewGuid().ToString('N')).json"
      try {
        $smokePayload = if ($smokeProtocol -eq 'responses') { '{"input":[{"role":"user","content":"Hello!"}],"stream":true}' } else { '{"messages":[{"role":"user","content":"Hello!"}]}' }
        $smokeOptions = if ($smokeProtocol -eq 'responses') { @('--output', 'raw') } else { @() }
        $smokeValidation = if ($smokeProtocol -eq 'responses') { '--validate-responses-smoke' } else { '--validate-smoke' }
        [IO.File]::WriteAllText($smokePayloadPath, $smokePayload, [Text.UTF8Encoding]::new($false))
        $smokeOutput = (& azd ai agent invoke $componentName --protocol $smokeProtocol --new-session --timeout 180 --environment "$($globalEnv.AZURE_ENV_NAME)" --no-prompt --input-file $smokePayloadPath @smokeOptions 2>&1 | Out-String)
        if ($LASTEXITCODE -ne 0) { Write-Error "${componentName}: smoke request failed."; $hadErrors = $true; continue }
        $smokeOutput | & python -c "import os, runpy, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); sys.argv = ['config.deployment.hosted'] + sys.argv[1:]; runpy.run_module('config.deployment.hosted', run_name='__main__')" $smokeValidation
        if ($LASTEXITCODE -ne 0) { Write-Error "${componentName}: smoke test did not pass."; $hadErrors = $true; continue }
      } finally {
        Remove-Item -LiteralPath $smokePayloadPath -Force -ErrorAction SilentlyContinue
      }
    } else {
      & python -c "import os, runpy, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); sys.argv = ['config.deployment.custom_application'] + sys.argv[1:]; runpy.run_module('config.deployment.custom_application', run_name='__main__')" --definition $appDefinitionPath --service $componentName --environment "$($globalEnv.AZURE_ENV_NAME)"
      if ($LASTEXITCODE -ne 0) { Write-Error "${componentName}: Container App deployment failed."; $hadErrors = $true; continue }
    }
    Write-Host "${componentName}: deployed." -ForegroundColor Green
  } finally {
    Pop-Location
  }
}

if ($hadErrors) { Write-Error "One or more components failed. See logs above."; exit 1 }

if ($nativeMode) {
  Invoke-PythonModule -ModuleName 'config.deployment.mcp' -Arguments @('--activate')
  if ($LASTEXITCODE -ne 0) { Write-Error "MCP caller authorization/activation failed."; exit 1 }
}

Write-Host "All components processed." -ForegroundColor Green
