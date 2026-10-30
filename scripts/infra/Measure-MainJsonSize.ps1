<#
.SYNOPSIS
  Measure the compiled main.json size and apply the release size gate.

.DESCRIPTION
  Compiles main.bicep (unless -SkipBuild is set), then reports the resulting
  main.json size in bytes, KB and MB. Emits a warning when the size exceeds the
  working budget (3.5 MB by default) and exits non-zero when it exceeds the CI
  fail threshold (4.7 MB by default). The ARM hard ceiling is 5.0 MB and is
  treated as an unconditional failure.

.PARAMETER WorkingBudgetMB
  Soft warning threshold. Defaults to 3.5 MB per issue #58 acceptance criteria.

.PARAMETER FailThresholdMB
  CI fail threshold. Defaults to the 4.7 MB release ratchet.

.PARAMETER ArmHardCeilingMB
  ARM request payload hard ceiling. Should never be crossed; deployments will
  fail with RequestContentTooLarge. Defaults to 5.0 MB.

.PARAMETER SkipBuild
  Skip `bicep build` and measure the existing main.json. Useful in CI when an
  earlier step already produced the file.

.EXAMPLE
  pwsh scripts/infra/Measure-MainJsonSize.ps1
#>
[CmdletBinding()]
param(
  [double]$WorkingBudgetMB = 3.5,
  [double]$FailThresholdMB = 4.7,
  [double]$ArmHardCeilingMB = 5.0,
  [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '../..')
$mainBicep = Join-Path $repoRoot 'infra/bicep/main.bicep'
$mainJson  = Join-Path $repoRoot 'infra/bicep/main.json'

if (-not $SkipBuild) {
  Write-Host "Compiling main.bicep..." -ForegroundColor Cyan
  & bicep build $mainBicep
  if ($LASTEXITCODE -ne 0) {
    Write-Error "bicep build failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
  }
}

if (-not (Test-Path $mainJson)) {
  Write-Error "main.json not found at $mainJson"
  exit 1
}

$bytes = (Get-Item $mainJson).Length
$kb    = [math]::Round($bytes / 1KB, 1)
$mb    = [math]::Round($bytes / 1MB, 3)

Write-Host ""
Write-Host "main.json size: $bytes bytes ($kb KB, $mb MB)" -ForegroundColor Cyan
Write-Host "  Working budget : $WorkingBudgetMB MB" -ForegroundColor DarkGray
Write-Host "  Fail threshold : $FailThresholdMB MB" -ForegroundColor DarkGray
Write-Host "  ARM ceiling    : $ArmHardCeilingMB MB" -ForegroundColor DarkGray

if ($mb -ge $ArmHardCeilingMB) {
  Write-Host ""
  Write-Error "main.json ($mb MB) exceeds ARM hard ceiling of $ArmHardCeilingMB MB. Deployments will fail with RequestContentTooLarge."
  exit 2
}

if ($mb -ge $FailThresholdMB) {
  Write-Host ""
  Write-Error "main.json ($mb MB) exceeds CI fail threshold of $FailThresholdMB MB. See issue #58 size budget."
  exit 1
}

if ($mb -ge $WorkingBudgetMB) {
  Write-Warning "main.json ($mb MB) exceeds working budget of $WorkingBudgetMB MB but is under the CI fail threshold."
  exit 0
}

Write-Host ""
Write-Host "OK - within working budget." -ForegroundColor Green
exit 0
