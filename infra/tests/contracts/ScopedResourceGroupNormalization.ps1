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

function Get-ArchitectureSubnetProjection {
    $fixture = Get-Content (Join-Path $PSScriptRoot 'fixtures\architecture-subnets-normalization.json') -Raw |
        ConvertFrom-Json -AsHashtable -Depth 100
    # Both ownership paths emit exactly the same subnet input before AND after.
    # Reuse that reviewed rule, not a second copy of its large ARM expression.
    $resources = $fixture.projection.changes.resources.changes
    $resources.virtualNetwork.changes.properties = @{
        kind = 'object'
        changes = @{ parameters = $resources.virtualNetworkSubnets.changes.properties.changes.parameters }
    }
    # Four complete pre-change values already exist in reviewed fixtures.
    # Each was compared with the real origin/develop 9ab6ceb compile. Keep the
    # before/after association explicit without duplicating those large values.
    $snapshots = @{}
    foreach ($name in @('scoped-resource-groups-normalization.json', 'foundry-root-normalization.json')) {
        $snapshots[$name] = Get-Content (Join-Path $PSScriptRoot "fixtures\$name") -Raw |
            ConvertFrom-Json -AsHashtable -Depth 100
    }
    function Resolve-SubnetBeforeFixture($Rule) {
        if ($Rule.Contains('beforeFixture')) {
            $file, $pointer = $Rule.beforeFixture -split '#', 2
            if (-not $snapshots.Contains($file) -or -not $pointer.StartsWith('/')) {
                throw 'SCOPED: invalid subnet before-fixture reference.'
            }
            $value = $snapshots[$file]
            foreach ($key in $pointer.TrimStart('/').Split('/')) {
                if ($value -isnot [System.Collections.IDictionary] -or -not $value.Contains($key)) {
                    throw 'SCOPED: missing subnet before-fixture value.'
                }
                $value = $value[$key]
            }
            $Rule.before = $value
        }
        if ($Rule.Contains('changes')) {
            foreach ($child in $Rule.changes.Values) { Resolve-SubnetBeforeFixture $child }
        }
    }
    Resolve-SubnetBeforeFixture $fixture.projection
    return $fixture.projection
}

. (Join-Path $PSScriptRoot 'FirewallBasicNormalization.ps1')

function ConvertTo-ApplicationRootResourceGroupGraph {
    param([Parameter(Mandatory)] $Template)
    $copy = ConvertTo-Json -InputObject $Template -Depth 100 -Compress | ConvertFrom-Json -AsHashtable -Depth 100
    # ADR-0031: check only the reviewed Basic/default/subnet delta before the
    # existing adapters and original security fingerprints. Never alter actual.
    $copy = Invoke-ScopedProjection $copy (Get-FirewallBasicProjection)
    # ADR-0030: restore only the reviewed optional-application-Cosmos delta.
    # Remaining mutations still reach the original exact graph fingerprints.
    Assert-ScopedValue $copy.parameters.deployCosmosDb.defaultValue $false '/parameters/deployCosmosDb/defaultValue'
    $copy.parameters.deployCosmosDb.defaultValue = $true
    Assert-ScopedValue $copy.parameters.deployCosmosDb.metadata.description `
        'Deploy the optional application Cosmos DB account. Enable for application consumers such as classic conversation storage or panel metadata. Does not control Foundry Agent Service backing storage.' `
        '/parameters/deployCosmosDb/metadata/description'
    $copy.parameters.deployCosmosDb.metadata.description = 'Deploy an Azure Cosmos DB account for globally distributed NoSQL data storage.'
    Assert-ScopedValue $copy.resources.cosmosUAI.condition `
        "[and(variables('_useUAI'), parameters('deployCosmosDb'))]" '/resources/cosmosUAI/condition'
    $copy.resources.cosmosUAI.condition = "[variables('_useUAI')]"
    $databaseSettings = @($copy.variables.copy | Where-Object name -CEQ '_databaseContainerNamesSettings')
    if ($databaseSettings.Count -ne 1) { throw 'SCOPED: application Cosmos settings loop membership changed.' }
    $expectedSettings = @{
        name = '_databaseContainerNamesSettings'
        count = "[length(if(parameters('deployCosmosDb'), parameters('databaseContainersList'), createArray()))]"
        input = @{
            name = "[if(parameters('deployCosmosDb'), parameters('databaseContainersList'), createArray())[copyIndex('_databaseContainerNamesSettings')].canonical_name]"
            value = "[if(parameters('deployCosmosDb'), parameters('databaseContainersList'), createArray())[copyIndex('_databaseContainerNamesSettings')].name]"
            label = "[parameters('appConfigLabel')]"
            contentType = 'text/plain'
        }
    }
    Assert-ScopedValue $databaseSettings[0] $expectedSettings '/variables/copy/applicationCosmosSettings'
    $databaseSettings[0].count = "[length(parameters('databaseContainersList'))]"
    $databaseSettings[0].input.name = "[parameters('databaseContainersList')[copyIndex('_databaseContainerNamesSettings')].canonical_name]"
    $databaseSettings[0].input.value = "[parameters('databaseContainersList')[copyIndex('_databaseContainerNamesSettings')].name]"
    $databaseNames = @{ DATABASE_ACCOUNT_NAME = 'dbAccountName'; DATABASE_NAME = 'dbDatabaseName' }
    foreach ($name in $databaseNames.Keys) {
        $property = $databaseNames[$name]
        $selected = @($copy.variables._containerRuntimeEnv | Where-Object name -CEQ $name)
        if ($selected.Count -ne 1) { throw "SCOPED: application Cosmos bootstrap membership changed for $name." }
        $after = "if(parameters('deployCosmosDb'), variables('resourceNames').$property, '')"
        $before = "variables('resourceNames').$property"
        Assert-ScopedValue $selected[0].value "[$after]" "/variables/_containerRuntimeEnv/$name/value"
        $selected[0].value = "[$before]"
        $settings = $copy.resources.appConfigPopulate.properties.parameters.keyValues.value
        if ([regex]::Matches($settings, [regex]::Escape($after)).Count -ne 1) {
            throw "SCOPED: application Cosmos App Configuration gate changed for $name."
        }
        $copy.resources.appConfigPopulate.properties.parameters.keyValues.value = $settings.Replace($after, $before)
    }
    # ADR-0027: validate the complete reviewed subnet delta before restoring the
    # previous composition. Never substitute hashes or discard unchecked fields.
    # The existing adapters then protect all unchanged graph membership/values.
    $copy = Invoke-ScopedProjection $copy (Get-ArchitectureSubnetProjection)
    # ADR-0025 adds only generic handoff fields. Check their entire compiled
    # values before projecting them away for the ORIGINAL graph fingerprints.
    $egress = @{
        networkIsolation = "[variables('_networkIsolation')]"
        managedFirewallPolicyId = "[reference('firewall').outputs.policyResourceId.value]"
        subnets = @{
            containerapp = "[if(variables('_networkIsolation'), format('{0}/subnets/{1}', if(variables('_networkIsolation'), if(parameters('useExistingVNet'), parameters('existingVnetResourceId'), reference('virtualNetwork').outputs.resourceId.value), ''), parameters('acaEnvironmentSubnetName')), '')]"
            'azure.ai.agent' = "[if(variables('_networkIsolation'), format('{0}/subnets/{1}', if(variables('_networkIsolation'), if(parameters('useExistingVNet'), parameters('existingVnetResourceId'), reference('virtualNetwork').outputs.resourceId.value), ''), parameters('agentSubnetName')), '')]"
        }
    }
    Assert-ScopedValue $copy.outputs.HOSTED_AGENT_DEPLOYMENT.value.workloadEgress $egress '/outputs/HOSTED_AGENT_DEPLOYMENT/value/workloadEgress'
    $null = $copy.outputs.HOSTED_AGENT_DEPLOYMENT.value.Remove('workloadEgress')
    $policy = @{
        type = 'string'
        metadata = @{ description = 'Deployment-owned policy only; empty for non-isolated or externally managed egress.' }
        value = "[if(and(parameters('deployAzureFirewall'), parameters('networkIsolation')), resourceId('Microsoft.Network/firewallPolicies', format('{0}{1}', variables('_1.abbrs').networking.firewallPolicy, parameters('resourceToken'))), '')]"
    }
    Assert-ScopedValue $copy.resources.firewall.properties.template.outputs.policyResourceId $policy '/resources/firewall/properties/template/outputs/policyResourceId'
    $null = $copy.resources.firewall.properties.template.outputs.Remove('policyResourceId')
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
