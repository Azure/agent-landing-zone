<#
.SYNOPSIS
    Guards retirement of external Terraform assessment and publication automation.
.DESCRIPTION
    Offline only. Historical ADRs, specifications and changelogs are not active
    automation and are deliberately excluded from the reference scan.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version 3.0
$ErrorActionPreference = 'Stop'
$infraRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$repoRoot = Split-Path $infraRoot -Parent

function Assert-NoExternalParityReference {
    param([string]$Text, [string]$Path)
    $retired = '(?i)terraform-parity|terraform-azurerm-avm-ptn-aiml-landing-zone|PARITY_DISPATCH|parity-proposal-requested|scripts[/\\]parity|tests[/\\]parity|\.parity-(ledger|dispatch)'
    if ($Text -match $retired) {
        throw "Retired external parity reference in ${Path}: $($Matches[0])"
    }
}

# Prove the guard rejects dispatch targets, environment/credential references,
# the ledger and old script entrypoints, but allows ordinary local Terraform CI.
Assert-NoExternalParityReference @'
on:
  workflow_dispatch:
jobs:
  validate:
    steps:
      - run: terraform -chdir=infra/terraform validate
'@ 'local validation fixture'
$mutations = @(
    'gh api --method POST /repos/Azure/terraform-azurerm-avm-ptn-aiml-landing-zone/dispatches',
    'environment: terraform-parity-publication',
    'private-key: ${{ secrets.PARITY_DISPATCH_APP_PRIVATE_KEY }}',
    'app-id: ${{ secrets.PARITY_DISPATCH_APP_ID }}',
    'event_type: parity-proposal-requested',
    'ref: terraform-parity-assessments',
    'path: .parity-ledger',
    'run: pwsh ./scripts/parity/Publish-TerraformHandoff.ps1',
    'run: pwsh ./tests/parity/Invoke-ParityWorkflow.Tests.ps1'
)
foreach ($text in $mutations) {
    $rejected = $false
    try { Assert-NoExternalParityReference $text 'mutation fixture' }
    catch {
        if (-not $_.Exception.Message.StartsWith('Retired external parity reference')) { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw "Retirement guard accepted a legacy reference: $text" }
}

foreach ($path in @(
    '.github/workflows/infra-terraform-parity.yml',
    'infra/.github/workflows/terraform-parity-assess.yml',
    'infra/.github/workflows/terraform-parity-publish.yml',
    'infra/.github/workflows/terraform-parity-validate.yml',
    'infra/.github/agents/terraform-parity.agent.md',
    'infra/.github/skills/terraform-parity-proposal',
    'infra/scripts/parity', 'infra/tests/parity', 'infra/parity',
    'infra/docs/terraform-parity.md',
    'infra/docs/terraform-parity-process.md',
    'infra/docs/terraform-parity-ownership.md'
)) {
    $item = Get-Item (Join-Path $repoRoot $path) -ErrorAction SilentlyContinue
    # Git tracks files, not empty directories left by an in-place cleanup.
    if ($null -ne $item -and (-not $item.PSIsContainer -or
        @(Get-ChildItem $item.FullName -File -Recurse -Force).Count -gt 0)) {
        throw "Retired asset still exists: $path"
    }
}

$count = 0
foreach ($base in @($repoRoot, $infraRoot)) {
    foreach ($path in @('AGENTS.md', '.github/copilot-instructions.md', 'package.json', 'package-lock.json')) {
        $file = Join-Path $base $path
        if (Test-Path $file -PathType Leaf) {
            Assert-NoExternalParityReference (Get-Content $file -Raw) $file
            $count++
        }
    }
    foreach ($directory in @(
        '.github/workflows', '.github/agents', '.github/skills',
        '.github/instructions', '.github/scripts', 'scripts'
    )) {
        foreach ($file in Get-ChildItem (Join-Path $base $directory) -File -Recurse |
            Where-Object Extension -In @('.yml', '.yaml', '.md', '.ps1', '.sh', '.py', '.mjs', '.json')) {
            Assert-NoExternalParityReference (Get-Content $file.FullName -Raw) $file.FullName
            $count++
        }
    }
}
Write-Host "External parity retirement contract passed: $count operational files, $($mutations.Count) rejected mutations, retired assets absent."
