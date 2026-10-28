<#
.SYNOPSIS
    Proves the in-repository validation workflow YAML reader is exact and strict.

.DESCRIPTION
    Covers the block subset that validation workflows use -
    nested mappings, sequences of scalars and mappings, quoted scalars, literal and
    folded block scalars, comments, and scalar typing - and proves that constructs
    outside that subset fail explicitly instead of parsing into a partial document.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $repo 'scripts\WorkflowYaml.ps1')
$failures = 0

function Assert-Result([string]$Name, [bool]$Condition, [string]$Detail) {
    if ($Condition) { Write-Host "[PASS] $Name" -ForegroundColor Green }
    else { Write-Host "[FAIL] $Name - $Detail" -ForegroundColor Red; $script:failures++ }
}

function Assert-Rejected([string]$Name, [string]$Yaml, [string]$Pattern) {
    $message = ''
    try { ConvertFrom-WorkflowYaml -Yaml $Yaml | Out-Null }
    catch { $message = $_.Exception.Message }
    Assert-Result $Name ($message -match $Pattern) "message='$message'"
}

$document = @'
# leading comment
name: validation-sample

on:
  pull_request:
    paths:
      - 'tests/contracts/**'
      - '.github/workflows/bicep-validate.yml'
  push:
    branches:
      - develop

permissions:
  contents: read

concurrency:
  group: validation-sample
  cancel-in-progress: false

jobs:
  sample:
    name: Sample job
    if: github.event.pull_request.merged == true
    timeout-minutes: 15
    ratio: 1.5
    empty:
    steps:
      - name: Check out trusted content   # trailing comment
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: ${{ github.event.pull_request.merge_commit_sha }}
          persist-credentials: false
      - name: Run a script
        shell: pwsh
        env:
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: |
          $value = 'literal # not a comment'
          if ($value) { Write-Host "$value" }

          Write-Host 'after a blank line'
      - name: Folded description
        summary: >
          first line
          second line
      - name: Quoted values
        double: "quoted: value"
        single: 'it''s quoted'
'@

$parsed = ConvertFrom-WorkflowYaml -Yaml $document
$job = $parsed['jobs']['sample']
$steps = @(Get-WorkflowStep -Workflow $parsed)

Assert-Result 'Top-level mapping keys are preserved verbatim, including on' (
    (@($parsed.Keys) -join ',') -eq 'name,on,permissions,concurrency,jobs'
) (@($parsed.Keys) -join ',')

Assert-Result 'Nested trigger mappings and sequences are parsed' (
    @($parsed['on']['pull_request']['paths']).Count -eq 2 -and
    $parsed['on']['pull_request']['paths'][0] -eq 'tests/contracts/**' -and
    $parsed['on']['pull_request']['paths'][1] -eq '.github/workflows/bicep-validate.yml' -and
    @($parsed['on']['push']['branches']) -ceq @('develop')
) ($parsed['on'] | ConvertTo-Json -Depth 6 -Compress)

Assert-Result 'Booleans, integers, doubles, and nulls are typed like a YAML core schema' (
    $parsed['concurrency']['cancel-in-progress'] -is [bool] -and
    $parsed['concurrency']['cancel-in-progress'] -eq $false -and
    $job['timeout-minutes'] -is [int] -and $job['timeout-minutes'] -eq 15 -and
    $job['ratio'] -is [double] -and
    $null -eq $job['empty']
) ("$($job['timeout-minutes'])/$($job['ratio'])")

Assert-Result 'Plain scalars keep expression syntax and drop trailing comments' (
    "$($job['if'])" -eq 'github.event.pull_request.merged == true' -and
    $steps[0]['name'] -eq 'Check out trusted content' -and
    $steps[0]['uses'] -eq 'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1' -and
    "$($steps[0]['with']['ref'])" -eq '${{ github.event.pull_request.merge_commit_sha }}' -and
    $steps[0]['with']['persist-credentials'] -eq $false
) ($steps[0] | ConvertTo-Json -Depth 6 -Compress)

Assert-Result 'Sequence items that start a mapping parse into step mappings' (
    $steps.Count -eq 4 -and
    $steps[1]['env']['PR_NUMBER'] -eq '${{ github.event.pull_request.number }}'
) ("steps=$($steps.Count)")

$run = "$($steps[1]['run'])"
Assert-Result 'Literal block scalars keep indentation, blank lines, and hash characters' (
    $run -match "(?m)^\`$value = 'literal # not a comment'$" -and
    $run -match '(?m)^if \(\$value\) \{ Write-Host "\$value" \}$' -and
    $run -match "(?s)\}\n\nWrite-Host 'after a blank line'" -and
    $run.EndsWith("`n")
) $run

Assert-Result 'Folded block scalars join their lines' (
    "$($steps[2]['summary'])".Trim() -eq 'first line second line'
) "$($steps[2]['summary'])"

Assert-Result 'Quoted scalars keep colons and escaped quotes' (
    $steps[3]['double'] -eq 'quoted: value' -and $steps[3]['single'] -eq "it's quoted"
) ($steps[3] | ConvertTo-Json -Depth 6 -Compress)

Assert-Rejected 'Flow mappings are rejected' "jobs: { a: b }" 'flow collections'
Assert-Rejected 'Flow sequences are rejected' "branches: [develop]" 'flow collections'
Assert-Rejected 'Anchors are rejected' "base: &anchor value" 'anchors'
Assert-Rejected 'Aliases are rejected' "copy: *anchor" 'anchors'
Assert-Rejected 'Merge keys are rejected' "job:`n  <<: base" 'merge keys'
Assert-Rejected 'Tab indentation is rejected' "jobs:`n`tsample: x" 'tab indentation'
Assert-Rejected 'Multiple documents are rejected' "name: a`n---`nname: b" 'multi-document'
Assert-Rejected 'Duplicate keys are rejected' "name: a`nname: b" 'duplicate mapping key'
Assert-Rejected 'Unparsable lines are rejected' "name: a`nnot a mapping entry" 'not a supported mapping entry'
Assert-Rejected 'Unexpected indentation is rejected' "a: 1`n    b: 2" 'unexpected indentation'

foreach ($name in @('bicep-validate.yml')) {
    $path = Join-Path $repo ".github\workflows\$name"
    $workflow = ConvertFrom-WorkflowYaml -Yaml (Get-Content $path -Raw)
    $workflowSteps = @(Get-WorkflowStep -Workflow $workflow)
    $usesCount = @([regex]::Matches((Get-Content $path -Raw), '(?m)^\s*-?\s*uses:\s*\S+')).Count
    $runCount = @([regex]::Matches((Get-Content $path -Raw), '(?m)^\s*-?\s*run:\s')).Count
    Assert-Result "$name parses into a complete job and step graph" (
        $workflow.Contains('on') -and $workflow.Contains('jobs') -and
        @($workflow['jobs'].Keys).Count -ge 1 -and
        $workflowSteps.Count -ge 1 -and
        @($workflowSteps | Where-Object { $_.Contains('uses') }).Count -eq $usesCount -and
        @($workflowSteps | Where-Object { $_.Contains('run') }).Count -eq $runCount
    ) ("steps=$($workflowSteps.Count) uses=$usesCount run=$runCount")
}

if ($failures) { exit 1 }
exit 0
