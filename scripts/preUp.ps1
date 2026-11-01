Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'manifest.json'))) {
    throw 'Cannot locate the Agent Landing Zone repository.'
}
$arguments = @('--validate', '--check-binding', '--azure-dir', (Join-Path $repoRoot '.azure'))
if ($env:AZURE_ENV_NAME) { $arguments += @('--env-name', $env:AZURE_ENV_NAME) }

# azd can create a resource group before preprovision; reject invalid input at preup.
Push-Location $repoRoot
try {
    & python -m config.appdefinition @arguments
    $validationExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $validationExitCode
