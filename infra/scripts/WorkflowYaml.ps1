<#
.SYNOPSIS
    Deterministic in-repository reader for the validation workflow YAML subset.

.DESCRIPTION
    Parses the block-style YAML subset used by validation workflows:
    block mappings, block sequences, plain and quoted scalars, literal and
    folded block scalars, and comments. Anything outside that subset - flow
    collections, anchors, aliases, merge keys, tags, tab indentation, or multiple
    documents - fails explicitly instead of being silently ignored, so a workflow
    contract is never asserted against a partially understood document.

    This file is dot-sourced by workflow and release contract tests so they need
    no runtime module installation from a package gallery.
#>

Set-StrictMode -Version 3.0

class WorkflowYamlParser {
    [System.Collections.Generic.List[hashtable]]$Lines
    [int]$Position

    WorkflowYamlParser([string]$yaml) {
        $this.Lines = [System.Collections.Generic.List[hashtable]]::new()
        $this.Position = 0
        $normalized = $yaml -replace "`r`n", "`n" -replace "`r", "`n"
        $number = 0
        foreach ($raw in ($normalized -split "`n")) {
            $number++
            $text = $raw.TrimEnd()
            if ($text -match '^[ ]*\t') {
                throw "Line ${number}: tab indentation is not supported in workflow YAML."
            }
            $trimmed = $text.Trim()
            if ($trimmed -eq '---' -or $trimmed -eq '...' -or $trimmed.StartsWith('%')) {
                throw "Line ${number}: multi-document or directive YAML is not supported in workflow YAML."
            }
            $indent = 0
            while ($indent -lt $text.Length -and $text[$indent] -eq ' ') { $indent++ }
            $this.Lines.Add(@{
                Number = $number
                Indent = $indent
                Text = $text
                Raw = $raw
                Ignorable = ($trimmed -eq '' -or $trimmed.StartsWith('#'))
            })
        }
    }

    [object] Parse() {
        $this.SkipIgnorable()
        if ($this.Position -ge $this.Lines.Count) { return [ordered]@{} }
        $node = $this.ParseNode($this.Lines[$this.Position].Indent)
        $this.SkipIgnorable()
        if ($this.Position -lt $this.Lines.Count) {
            throw "Line $($this.Lines[$this.Position].Number): unexpected content after the document root."
        }
        return $node
    }

    [void] SkipIgnorable() {
        while ($this.Position -lt $this.Lines.Count -and $this.Lines[$this.Position].Ignorable) { $this.Position++ }
    }

    [object] ParseNode([int]$indent) {
        $this.SkipIgnorable()
        if ($this.Position -ge $this.Lines.Count) { return $null }
        $line = $this.Lines[$this.Position]
        if ($line.Indent -ne $indent) {
            throw "Line $($line.Number): unexpected indentation; expected $indent spaces."
        }
        if ($line.Text.Substring($indent) -match '^-(\s|$)') { return $this.ParseSequence($indent) }
        return $this.ParseMapping($indent)
    }

    [object] ParseMapping([int]$indent) {
        $map = [ordered]@{}
        while ($true) {
            $this.SkipIgnorable()
            if ($this.Position -ge $this.Lines.Count) { break }
            $line = $this.Lines[$this.Position]
            if ($line.Indent -lt $indent) { break }
            if ($line.Indent -gt $indent) {
                throw "Line $($line.Number): unexpected indentation inside a mapping."
            }
            $content = $line.Text.Substring($indent)
            if ($content -match '^-(\s|$)') { break }
            $match = [regex]::Match($content, '^(?<key>"[^"]*"|''[^'']*''|[^:#\s][^:]*?)\s*:(?:\s+(?<value>.*))?$')
            if (-not $match.Success) {
                throw "Line $($line.Number): '$content' is not a supported mapping entry."
            }
            $key = $this.ParseKey($match.Groups['key'].Value, $line.Number)
            if ($map.Contains($key)) {
                throw "Line $($line.Number): duplicate mapping key '$key'."
            }
            $value = $match.Groups['value'].Value
            $this.Position++
            if ([string]::IsNullOrEmpty($value)) {
                $map[$key] = $this.ParseNestedValue($indent)
            }
            elseif ($value -match '^[|>]') {
                $map[$key] = $this.ParseBlockScalar($indent, $value, $line.Number)
            }
            else {
                $map[$key] = $this.ParseScalar($value, $line.Number)
            }
        }
        return $map
    }

    [object] ParseNestedValue([int]$indent) {
        $this.SkipIgnorable()
        if ($this.Position -ge $this.Lines.Count) { return $null }
        $next = $this.Lines[$this.Position]
        if ($next.Indent -gt $indent) { return $this.ParseNode($next.Indent) }
        if ($next.Indent -eq $indent -and $next.Text.Substring($indent) -match '^-(\s|$)') {
            return $this.ParseSequence($indent)
        }
        return $null
    }

    [object[]] ParseSequence([int]$indent) {
        $items = [System.Collections.Generic.List[object]]::new()
        while ($true) {
            $this.SkipIgnorable()
            if ($this.Position -ge $this.Lines.Count) { break }
            $line = $this.Lines[$this.Position]
            if ($line.Indent -lt $indent) { break }
            if ($line.Indent -gt $indent) {
                throw "Line $($line.Number): unexpected indentation inside a sequence."
            }
            $content = $line.Text.Substring($indent)
            if (-not ($content -match '^-(\s|$)')) { break }
            $remainder = $content.Substring(1)
            $leading = 0
            while ($leading -lt $remainder.Length -and $remainder[$leading] -eq ' ') { $leading++ }
            $itemIndent = $indent + 1 + $leading
            $item = $remainder.Trim()
            if ($item -eq '') {
                $this.Position++
                $this.SkipIgnorable()
                if ($this.Position -ge $this.Lines.Count -or $this.Lines[$this.Position].Indent -le $indent) {
                    $items.Add($null)
                }
                else {
                    $items.Add($this.ParseNode($this.Lines[$this.Position].Indent))
                }
            }
            elseif ($item -match '^(?:"[^"]*"|''[^'']*''|[^:#\s][^:]*?)\s*:(?:\s+.*)?$') {
                $this.Lines[$this.Position].Indent = $itemIndent
                $this.Lines[$this.Position].Text = (' ' * $itemIndent) + $item
                $items.Add($this.ParseMapping($itemIndent))
            }
            else {
                $this.Position++
                $items.Add($this.ParseScalar($item, $line.Number))
            }
        }
        return $items.ToArray()
    }

    [string] ParseKey([string]$token, [int]$number) {
        $key = $token.Trim()
        if ($key -eq '<<') {
            throw "Line ${number}: YAML merge keys are not supported in workflow YAML."
        }
        if ($key.StartsWith("'") -or $key.StartsWith('"')) {
            return $key.Substring(1, $key.Length - 2)
        }
        return $key
    }

    [object] ParseBlockScalar([int]$indent, [string]$header, [int]$number) {
        $match = [regex]::Match($header, '^(?<style>[|>])(?<chomp>[-+]?)\s*(?:#.*)?$')
        if (-not $match.Success) {
            throw "Line ${number}: '$header' is not a supported block scalar header."
        }
        $collected = [System.Collections.Generic.List[string]]::new()
        while ($this.Position -lt $this.Lines.Count) {
            $line = $this.Lines[$this.Position]
            if ($line.Text.Trim() -eq '') { $collected.Add(''); $this.Position++; continue }
            if ($line.Indent -le $indent) { break }
            $collected.Add($line.Text)
            $this.Position++
        }
        while ($collected.Count -gt 0 -and $collected[$collected.Count - 1] -eq '') {
            $collected.RemoveAt($collected.Count - 1)
        }
        if ($collected.Count -eq 0) { return '' }
        $blockIndent = ($collected | Where-Object { $_ -ne '' } | ForEach-Object {
            $count = 0
            while ($count -lt $_.Length -and $_[$count] -eq ' ') { $count++ }
            $count
        } | Measure-Object -Minimum).Minimum
        $content = @($collected | ForEach-Object {
            if ($_ -eq '') { '' } else { $_.Substring($blockIndent) }
        })
        $text = if ($match.Groups['style'].Value -eq '>') {
            $folded = [System.Collections.Generic.List[string]]::new()
            $buffer = ''
            foreach ($entry in $content) {
                if ($entry -eq '') { $folded.Add($buffer); $buffer = ''; continue }
                $buffer = if ($buffer -eq '') { $entry } else { "$buffer $entry" }
            }
            if ($buffer -ne '') { $folded.Add($buffer) }
            $folded -join "`n"
        }
        else {
            $content -join "`n"
        }
        if ($match.Groups['chomp'].Value -eq '-') { return $text }
        return "$text`n"
    }

    [object] ParseScalar([string]$token, [int]$number) {
        $value = $token.Trim()
        if ($value.StartsWith("'")) {
            $match = [regex]::Match($value, '^''(?<text>(?:[^'']|'''')*)''\s*(?:#.*)?$')
            if (-not $match.Success) { throw "Line ${number}: unterminated single-quoted scalar." }
            return $match.Groups['text'].Value -replace "''", "'"
        }
        if ($value.StartsWith('"')) {
            $match = [regex]::Match($value, '^"(?<text>(?:[^"\\]|\\.)*)"\s*(?:#.*)?$')
            if (-not $match.Success) { throw "Line ${number}: unterminated double-quoted scalar." }
            $text = $match.Groups['text'].Value
            return $text -replace '\\n', "`n" -replace '\\t', "`t" -replace '\\"', '"' -replace '\\\\', '\'
        }
        $plain = $value
        $comment = [regex]::Match($plain, '^(?<text>.*?)\s+#.*$')
        if ($comment.Success) { $plain = $comment.Groups['text'].Value }
        $plain = $plain.Trim()
        if ($plain -match '^[\[\{\&\*\!]') {
            throw "Line ${number}: flow collections, anchors, aliases, and tags are not supported in workflow YAML."
        }
        if ($plain -eq '' -or $plain -eq '~' -or $plain -in @('null', 'Null', 'NULL')) { return $null }
        if ($plain -in @('true', 'True', 'TRUE')) { return $true }
        if ($plain -in @('false', 'False', 'FALSE')) { return $false }
        if ($plain -match '^-?[0-9]+$') { return [int]$plain }
        if ($plain -match '^-?[0-9]+\.[0-9]+$') { return [double]$plain }
        return $plain
    }
}

function ConvertFrom-WorkflowYaml {
    <#
    .SYNOPSIS
        Converts workflow YAML text into ordered dictionaries and arrays.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [AllowEmptyString()] [string]$Yaml)

    return [WorkflowYamlParser]::new($Yaml).Parse()
}

function Get-WorkflowStep {
    <#
    .SYNOPSIS
        Returns every step of every job in a parsed workflow document.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Workflow)

    $steps = [System.Collections.Generic.List[object]]::new()
    if (-not $Workflow.Contains('jobs')) { return $steps.ToArray() }
    foreach ($job in $Workflow['jobs'].Values) {
        if ($null -eq $job -or -not $job.Contains('steps')) { continue }
        foreach ($step in @($job['steps'])) {
            if ($null -ne $step) { $steps.Add($step) }
        }
    }
    return $steps.ToArray()
}
