<#
.SYNOPSIS
    Tests release metadata and manifest-only CI coverage without Azure access.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version 3.0
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $root 'scripts\ReleaseMetadata.ps1')
. (Join-Path $root 'scripts\WorkflowYaml.ps1')
$manifest = Get-Content (Join-Path $root 'manifest.json') -Raw | ConvertFrom-Json -AsHashtable
$changelog = Get-Content (Join-Path $root 'CHANGELOG.md') -Raw
Assert-ReleaseMetadata $manifest $changelog

foreach ($version in @('v0.0.0', 'v2.6.1', 'v2.7.0', 'v10.20.30')) {
    Assert-ReleaseMetadata @{ tag = $version; ailz_tag = $version } "## [Unreleased]`n## [$version] - Unreleased`n"
    Assert-ReleaseMetadata @{ tag = $version; ailz_tag = $version } "## [Unreleased]`r`n## [$version] - 2026-09-18`r`n"
}
$cases = @(
    foreach ($value in @('', '2.7.0', 'V2.7.0', 'v02.7.0', 'v2.07.0', 'v2.7.00', 'v2.7', 'v2.7.0-rc.1', 'v2.7.0+build', "v2.7.0`n", ' v2.7.0', 'v2.7.0 ', 27, $null)) {
        foreach ($field in @('tag', 'ailz_tag')) {
            $invalid = @{ tag = 'v2.7.0'; ailz_tag = 'v2.7.0' }
            $invalid[$field] = $value
            @{ Manifest = $invalid; Changelog = "## [v2.7.0] - Unreleased`n" }
        }
    }
    @{ Manifest = @{ tag = 'v2.7.0' }; Changelog = '## [v2.7.0]' }
    @{ Manifest = @{ ailz_tag = 'v2.7.0' }; Changelog = '## [v2.7.0]' }
    @{ Manifest = @{ tag = 'v2.7.0'; ailz_tag = 'v2.6.1' }; Changelog = '## [v2.7.0]' }
    foreach ($text in @('', '## [Unreleased]', '## [v2.6.1]', "## [v2.6.1]`n## [v2.7.0]", "## [v2.7.0]`n## [v2.7.0]", '## [V2.7.0]')) {
        @{ Manifest = @{ tag = 'v2.7.0'; ailz_tag = 'v2.7.0' }; Changelog = $text }
    }
)
foreach ($case in $cases) {
    $caught = $false
    try { Assert-ReleaseMetadata $case.Manifest $case.Changelog }
    catch {
        if (-not $_.Exception.Message.StartsWith('RELEASE:')) { throw }
        $caught = $true
    }
    if (-not $caught) { throw 'Release metadata guard accepted an invalid mutation.' }
}

foreach ($name in @('bicep-validate')) {
    $workflow = ConvertFrom-WorkflowYaml -Yaml (Get-Content (Join-Path $root ".github\workflows\$name.yml") -Raw)
    foreach ($event in @('pull_request', 'push')) {
        foreach ($path in @('manifest.json', 'CHANGELOG.md', 'scripts/ReleaseMetadata.ps1', 'tests/contracts/Test-ReleaseMetadataContract.ps1', 'scripts/WorkflowYaml.ps1', 'tests/scripts/WorkflowYaml.Tests.ps1')) {
            $covered = @($workflow['on'][$event].paths | Where-Object { $path -clike $_ }).Count -gt 0
            if (-not $covered) { throw "$name/$event does not cover $path." }
        }
    }
    $steps = @($workflow.jobs.Values | ForEach-Object { $_.steps })
    if (@($steps | Where-Object { $_.Contains('run') -and $_.run -match 'pwsh \./tests/contracts/Test-ReleaseMetadataContract\.ps1' }).Count -ne 1) {
        throw "$name must run the release metadata contract once."
    }
}
Write-Host "Release metadata contract passed: actual files, 8 valid cases, $($cases.Count) rejected mutations, Bicep workflow triggers and test step."
exit 0
