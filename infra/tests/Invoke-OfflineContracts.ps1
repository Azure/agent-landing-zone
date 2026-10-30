<#
.SYNOPSIS
    Runs all compiled foundation contracts and deterministic script tests.
.DESCRIPTION
    No Azure credentials or writes. Requires PowerShell 7 and the pinned Azure
    CLI Bicep compiler. Includes external-sync retirement guards.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$oldTmpDir = $env:TMPDIR
$artifactRoot = Join-Path $PSScriptRoot ".offline-contracts-$([guid]::NewGuid().ToString('N'))"
$failures = [System.Collections.Generic.List[string]]::new()
$total = [System.Diagnostics.Stopwatch]::StartNew()
try {
    $null = New-Item -ItemType Directory -Path $artifactRoot
    $env:TEMP = $artifactRoot
    $env:TMP = $artifactRoot
    $env:TMPDIR = $artifactRoot
    $tests = @(
        Get-ChildItem (Join-Path $PSScriptRoot 'contracts') -Filter 'Test-*Contract.ps1' | Sort-Object Name
        Get-ChildItem (Join-Path $PSScriptRoot 'scripts') -Filter '*.Tests.ps1' | Sort-Object Name
    )
    foreach ($test in $tests) {
        $timer = [System.Diagnostics.Stopwatch]::StartNew()
        & pwsh -NoProfile -File $test.FullName
        if ($LASTEXITCODE -ne 0) { $failures.Add($test.Name) }
        Write-Host ("{0}: exit={1}, {2:N1}s" -f $test.Name, $LASTEXITCODE, $timer.Elapsed.TotalSeconds)
    }
}
finally {
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    $env:TMPDIR = $oldTmpDir
    if (Test-Path $artifactRoot) { Remove-Item -LiteralPath $artifactRoot -Recurse -Force }
}
Write-Host ("Offline foundation contracts: {0} failures, {1:N1}s total." -f $failures.Count, $total.Elapsed.TotalSeconds)
if ($failures.Count) {
    Write-Error "Failed contracts: $($failures -join ', ')"
    exit 1
}
