<#
.SYNOPSIS
    Regression tests for the compiled-template size gate defaults and CI caller.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$sizeGate = Join-Path $repoRoot 'scripts\infra\Measure-MainJsonSize.ps1'
$workflow = Join-Path $repoRoot '.github\workflows\infra-validate.yml'
$mainJson = Join-Path $repoRoot 'infra\bicep\main.json'
$originalBytes = if (Test-Path $mainJson) {
    [System.IO.File]::ReadAllBytes($mainJson)
}
else {
    $null
}
$failures = 0

function Assert-Result {
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [bool]$Condition,
        [Parameter(Mandatory)] [string]$Detail
    )

    if ($Condition) {
        Write-Host "  [PASS] $Name" -ForegroundColor Green
    }
    else {
        Write-Host "  [FAIL] $Name - $Detail" -ForegroundColor Red
        $script:failures++
    }
}

function Set-MainJsonSize {
    param([Parameter(Mandatory)] [double]$SizeMB)

    $stream = [System.IO.File]::Open(
        $mainJson,
        [System.IO.FileMode]::Create,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None
    )
    try {
        $stream.SetLength([long]($SizeMB * 1MB))
    }
    finally {
        $stream.Dispose()
    }
}

function Invoke-SizeGate {
    param([Parameter(Mandatory)] [double]$SizeMB)

    Set-MainJsonSize -SizeMB $SizeMB
    $output = & pwsh -NoProfile -File $sizeGate -SkipBuild 2>&1 | Out-String
    [pscustomobject]@{
        ExitCode = $LASTEXITCODE
        Output = $output
    }
}

try {
    $workflowText = Get-Content -Path $workflow -Raw
    $runnerCommandPattern = '(?m)^\s*run: \./infra/tests/Invoke-OfflineContracts\.ps1\s*$'
    Assert-Result `
        -Name 'Active workflow runs the offline size-gate regression' `
        -Condition ($workflowText -match $runnerCommandPattern) `
        -Detail 'Expected active CI to invoke the offline contract runner.'
    Assert-Result `
        -Name 'Workflow does not duplicate threshold switches' `
        -Condition ($workflowText -notmatch '-WorkingBudgetMB|-FailThresholdMB|-ArmHardCeilingMB') `
        -Detail 'Threshold switches in the workflow can diverge from local defaults.'

    $warning = Invoke-SizeGate -SizeMB 4.663
    Assert-Result `
        -Name 'Default gate warns and succeeds for the current 4.663 MB template size' `
        -Condition (
            $warning.ExitCode -eq 0 -and
            $warning.Output -match 'main\.json size:.*,\s+4\.663 MB\)' -and
            $warning.Output -match 'exceeds working budget of 3\.5 MB' -and
            $warning.Output -match 'Fail threshold\s+: 4\.7 MB' -and
            $warning.Output -match 'ARM ceiling\s+: 5 MB'
        ) `
        -Detail $warning.Output

    $failure = Invoke-SizeGate -SizeMB 4.8
    Assert-Result `
        -Name 'Default gate fails at the 4.7 MB ratchet' `
        -Condition (
            $failure.ExitCode -eq 1 -and
            $failure.Output -match 'exceeds CI fail threshold of 4\.7 MB'
        ) `
        -Detail $failure.Output

    $ceiling = Invoke-SizeGate -SizeMB 5.1
    Assert-Result `
        -Name 'Default gate enforces the 5.0 MB hard ceiling first' `
        -Condition (
            $ceiling.ExitCode -ne 0 -and
            $ceiling.Output -match 'exceeds ARM hard ceiling of 5 MB'
        ) `
        -Detail $ceiling.Output
}
finally {
    if ($null -ne $originalBytes) {
        [System.IO.File]::WriteAllBytes($mainJson, $originalBytes)
    }
    elseif (Test-Path $mainJson) {
        Remove-Item -Path $mainJson -Force
    }
}

if ($failures -gt 0) {
    exit 1
}
exit 0
