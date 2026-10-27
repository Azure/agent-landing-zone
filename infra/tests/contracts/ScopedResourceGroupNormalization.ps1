function ConvertTo-ScopedComparable {
    param([AllowNull()] $Value, [string]$Path = '')
    if ($null -eq $Value) { return $null }
    if ($Value -is [string]) { return $Value.Replace("`r`n", "`n").Replace("`r", "`n") }
    if ($Value -is [System.Collections.IDictionary]) {
        $result = [ordered]@{}
        foreach ($key in @($Value.Keys | Sort-Object -CaseSensitive)) {
            if ($key -ceq '_generator' -and $Path.EndsWith('/metadata')) { continue }
            $result[$key] = ConvertTo-ScopedComparable $Value[$key] "$Path/$key"
        }
        return $result
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        $result = [System.Collections.Generic.List[object]]::new()
        foreach ($item in $Value) { $result.Add((ConvertTo-ScopedComparable $item $Path)) }
        return ,$result.ToArray()
    }
    return $Value
}

function Assert-ScopedValue {
    param([AllowNull()] $Actual, [AllowNull()] $Expected, [string]$Path)
    $a = ConvertTo-Json -InputObject (ConvertTo-ScopedComparable $Actual $Path) -Depth 100 -Compress
    $e = ConvertTo-Json -InputObject (ConvertTo-ScopedComparable $Expected $Path) -Depth 100 -Compress
    if ($a -cne $e) { throw "SCOPED: unreviewed compiled mutation at $Path." }
}

function Invoke-ScopedProjection {
    param([AllowNull()] $Value, $Rule, [string]$Path = '')
    switch ($Rule.kind) {
        'changed' {
            # Compiler hashes are non-deploying and can differ with source line
            # endings. No resource, parameter, variable or output is exempted.
            if ($Path.EndsWith('/metadata/_generator/templateHash')) {
                if ([string]$Value -cnotmatch '^\d+$') { throw "SCOPED: invalid compiler hash at $Path." }
            }
            else { Assert-ScopedValue $Value $Rule.after $Path }
            return ,$Rule.before
        }
        'array' {
            if ($Value -isnot [array] -or $Value.Count -ne $Rule.count) { throw "SCOPED: array membership changed at $Path." }
            foreach ($key in $Rule.changes.Keys) {
                $index = [int]$key
                $Value[$index] = Invoke-ScopedProjection $Value[$index] $Rule.changes[$key] "$Path/$index"
            }
            return ,$Value
        }
        'object' {
            if ($Value -isnot [System.Collections.IDictionary]) { throw "SCOPED: expected object at $Path." }
            if ($Rule.Contains('afterKeys')) {
                Assert-ScopedValue @($Value.Keys | Sort-Object -CaseSensitive) @($Rule.afterKeys | Sort-Object -CaseSensitive) "$Path/membership"
            }
            foreach ($key in $Rule.changes.Keys) {
                $change = $Rule.changes[$key]
                if ($change.kind -ceq 'removed') {
                    if ($Value.Contains($key)) { throw "SCOPED: removed field returned at $Path/$key." }
                    $Value[$key] = $change.before
                    continue
                }
                if (-not $Value.Contains($key)) { throw "SCOPED: missing reviewed field at $Path/$key." }
                if ($change.kind -ceq 'added') {
                    Assert-ScopedValue $Value[$key] $change.after "$Path/$key"
                    $null = $Value.Remove($key)
                }
                else { $Value[$key] = Invoke-ScopedProjection $Value[$key] $change "$Path/$key" }
            }
            if ($Rule.Contains('beforeKeys')) {
                $ordered = [ordered]@{}
                foreach ($key in $Rule.beforeKeys) { $ordered[$key] = $Value[$key] }
                return $ordered
            }
            return $Value
        }
        default { throw "SCOPED: unknown projection rule $($Rule.kind) at $Path." }
    }
}

function ConvertTo-ApplicationRootResourceGroupGraph {
    param([Parameter(Mandatory)] $Template)
    $copy = ConvertTo-Json -InputObject $Template -Depth 100 -Compress | ConvertFrom-Json -AsHashtable -Depth 100
    $foundryRoot = Get-Content (Join-Path $PSScriptRoot 'fixtures\foundry-root-normalization.json') -Raw |
        ConvertFrom-Json -AsHashtable -Depth 100
    return Invoke-ScopedProjection $copy $foundryRoot.projection
}

function ConvertTo-LegacyResourceGroupGraph {
    param([Parameter(Mandatory)] $Template)
    $copy = ConvertTo-ApplicationRootResourceGroupGraph $Template
    $fixture = Get-Content (Join-Path $PSScriptRoot 'fixtures\scoped-resource-groups-normalization.json') -Raw |
        ConvertFrom-Json -AsHashtable -Depth 100
    return Invoke-ScopedProjection $copy $fixture.projection
}

function ConvertTo-HistoricalFoundationGraph {
    param([Parameter(Mandatory)] $Template, [Parameter(Mandatory)] [string]$MainFile)
    $copy = ConvertTo-Json -InputObject $Template -Depth 100 -Compress | ConvertFrom-Json -AsHashtable -Depth 100
    $foundationRoot = Split-Path -Parent (Resolve-Path $MainFile).Path
    $umbrella = Get-Content (Join-Path $foundationRoot '..\manifest.json') -Raw | ConvertFrom-Json -AsHashtable
    $foundation = Get-Content (Join-Path $foundationRoot 'manifest.json') -Raw | ConvertFrom-Json -AsHashtable
    Assert-ScopedValue $copy.variables['$fxv#0'] $umbrella '/variables/loadedUmbrellaManifest'
    Assert-ScopedValue $umbrella.infra.source.tag $foundation.tag '/manifest/infraSourceTag'
    if ($umbrella.tag -cnotmatch '^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') {
        throw 'SCOPED: invalid umbrella release version.'
    }
    $fixture = Get-Content (Join-Path $PSScriptRoot 'fixtures\incorporated-foundation-normalization.json') -Raw |
        ConvertFrom-Json -AsHashtable -Depth 100
    # Release numbers are variable; repository URLs, component pins, source
    # provenance, manifest shape and all deployment values remain exact.
    $manifestRule = $fixture.projection.changes.variables.changes['$fxv#0']
    $manifestRule.changes.tag.after = $umbrella.tag
    $manifestRule.changes.tag.before = $foundation.tag
    $manifestRule.changes.ailz_tag.before = $foundation.ailz_tag
    $selected = [ordered]@{ resources = $copy.resources; variables = $copy.variables; outputs = $copy.outputs }
    $historical = Invoke-ScopedProjection $selected $fixture.projection
    foreach ($key in $selected.Keys) { $copy[$key] = $historical[$key] }
    return $copy
}
