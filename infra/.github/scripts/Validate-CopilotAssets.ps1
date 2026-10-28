<#
.SYNOPSIS
    Validates repository GitHub Copilot agents, skills, and scoped instructions.

.DESCRIPTION
    Uses powershell-yaml for standards-compliant YAML frontmatter parsing, then
    validates repository schemas, unique names, allowed tools, and local links.
#>

[CmdletBinding()]
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$requiredYamlVersion = [version]'0.4.12'
$yamlModule = Get-Module -ListAvailable powershell-yaml |
    Where-Object Version -GE $requiredYamlVersion |
    Sort-Object Version -Descending |
    Select-Object -First 1

if (-not $yamlModule) {
    throw "powershell-yaml $requiredYamlVersion or later is required. Install it with: Install-Module powershell-yaml -RequiredVersion $requiredYamlVersion -Scope CurrentUser"
}

Import-Module $yamlModule.Path -Force

$repoRoot = (Resolve-Path $Root).Path
$allowedAgentTools = @('agent', 'edit', 'execute', 'read', 'search', 'web')
$assetNamePattern = '^[a-z0-9]+(?:-[a-z0-9]+)*$'
$localLinkPattern = '\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)'
$errors = [System.Collections.Generic.List[string]]::new()
$agentNames = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
$skillNames = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)

function Get-RelativePath {
    param([Parameter(Mandatory)][string]$Path)
    [System.IO.Path]::GetRelativePath($repoRoot, $Path).Replace('\', '/')
}

function Add-ValidationError {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Message
    )
    $errors.Add(('{0}: {1}' -f (Get-RelativePath $Path), $Message))
}

function Get-Frontmatter {
    param([Parameter(Mandatory)][string]$Path)

    $text = [System.IO.File]::ReadAllText($Path)
    $lines = $text -split "\r?\n"
    if ($lines.Count -eq 0 -or $lines[0].Trim() -ne '---') {
        throw 'missing opening YAML frontmatter boundary'
    }

    $closingIndex = -1
    for ($index = 1; $index -lt $lines.Count; $index++) {
        if ($lines[$index].Trim() -eq '---') {
            $closingIndex = $index
            break
        }
    }
    if ($closingIndex -lt 0) {
        throw 'missing closing YAML frontmatter boundary'
    }

    $yaml = ($lines[1..($closingIndex - 1)] -join "`n")
    try {
        $metadata = ConvertFrom-Yaml -Yaml $yaml
    }
    catch {
        throw "invalid YAML frontmatter: $($_.Exception.Message)"
    }
    if (-not ($metadata -is [System.Collections.IDictionary])) {
        throw 'YAML frontmatter must be a string-keyed mapping'
    }
    foreach ($key in $metadata.Keys) {
        if (-not ($key -is [string])) {
            throw 'YAML frontmatter must be a string-keyed mapping'
        }
    }

    [pscustomobject]@{
        Metadata = $metadata
        Text = $text
    }
}

function Test-RequiredString {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][System.Collections.IDictionary]$Metadata,
        [Parameter(Mandatory)][string[]]$Fields
    )
    foreach ($field in $Fields) {
        if (-not $Metadata.Contains($field) -or
            -not ($Metadata[$field] -is [string]) -or
            [string]::IsNullOrWhiteSpace($Metadata[$field])) {
            Add-ValidationError $Path "'$field' must be a non-empty string"
        }
    }
}

function Test-LocalLinks {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Text
    )
    foreach ($match in [regex]::Matches($Text, $localLinkPattern)) {
        $target = $match.Groups[1].Value
        $targetPath = ($target -split '#', 2)[0]
        if ([string]::IsNullOrWhiteSpace($targetPath)) {
            continue
        }
        $decodedTarget = [System.Uri]::UnescapeDataString($targetPath)
        $resolved = [System.IO.Path]::GetFullPath((Join-Path (Split-Path $Path -Parent) $decodedTarget))
        $relative = [System.IO.Path]::GetRelativePath($repoRoot, $resolved)
        if ($relative.StartsWith('..') -or -not (Test-Path -LiteralPath $resolved)) {
            Add-ValidationError $Path "local link does not exist: $target"
        }
    }
}

$groups = @(
    @{ Directory = '.github/agents'; Pattern = '*.agent.md'; Kind = 'agent' },
    @{ Directory = '.github/skills'; Pattern = 'SKILL.md'; Kind = 'skill' },
    @{ Directory = '.github/instructions'; Pattern = '*.instructions.md'; Kind = 'instruction' }
)

foreach ($group in $groups) {
    $directory = Join-Path $repoRoot $group.Directory
    $paths = @(Get-ChildItem -Path $directory -Filter $group.Pattern -File -Recurse)
    if ($paths.Count -eq 0) {
        $errors.Add("$($group.Directory): no matching assets")
        continue
    }

    foreach ($path in $paths) {
        try {
            $asset = Get-Frontmatter $path.FullName
        }
        catch {
            Add-ValidationError $path.FullName $_.Exception.Message
            continue
        }

        Test-LocalLinks $path.FullName $asset.Text
        $metadata = $asset.Metadata

        switch ($group.Kind) {
            'agent' {
                Test-RequiredString $path.FullName $metadata @('name', 'description')
                $name = $metadata['name']
                if ($name -is [string]) {
                    if ($name -notmatch $assetNamePattern) {
                        Add-ValidationError $path.FullName 'agent name must be lowercase kebab-case'
                    }
                    if (-not $agentNames.Add($name)) {
                        Add-ValidationError $path.FullName "duplicate agent '$name'"
                    }
                }

                $tools = @($metadata['tools'])
                if ($tools.Count -eq 0 -or @($tools | Where-Object { -not ($_ -is [string]) -or [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) {
                    Add-ValidationError $path.FullName "'tools' must be a non-empty string list"
                }
                else {
                    $unknownTools = @($tools | Where-Object { $_ -notin $allowedAgentTools } | Sort-Object -Unique)
                    if ($unknownTools.Count -gt 0) {
                        Add-ValidationError $path.FullName "unsupported tool aliases: $($unknownTools -join ', ')"
                    }
                    if (@($tools | Sort-Object -Unique).Count -ne $tools.Count) {
                        Add-ValidationError $path.FullName 'duplicate tool aliases'
                    }
                }
            }
            'skill' {
                Test-RequiredString $path.FullName $metadata @('name', 'description')
                $name = $metadata['name']
                if ($name -is [string]) {
                    if ($name -notmatch $assetNamePattern) {
                        Add-ValidationError $path.FullName 'skill name must be lowercase kebab-case'
                    }
                    if ($name -ne $path.Directory.Name) {
                        Add-ValidationError $path.FullName 'skill name must match its directory'
                    }
                    if (-not $skillNames.Add($name)) {
                        Add-ValidationError $path.FullName "duplicate skill '$name'"
                    }
                }
            }
            'instruction' {
                Test-RequiredString $path.FullName $metadata @('applyTo')
                $applyTo = $metadata['applyTo']
                if ($applyTo -is [string] -and @($applyTo.Split(',') | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) {
                    Add-ValidationError $path.FullName "'applyTo' has an empty pattern"
                }
            }
        }
    }
}

if ($errors.Count -gt 0) {
    foreach ($validationError in $errors) {
        Write-Error $validationError -ErrorAction Continue
    }
    exit 1
}

Write-Host "Validated $($agentNames.Count) agents, $($skillNames.Count) skills, and scoped instructions." -ForegroundColor Green
exit 0
