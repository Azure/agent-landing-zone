Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    & python -m config.deployment.teardown --azure-dir (Join-Path $repoRoot '.azure')
    $guardExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $guardExitCode
