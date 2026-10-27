<#
.SYNOPSIS
    Rejects unreviewed mutations before historical resource fingerprints run.
.DESCRIPTION
    Uses exact compiled before/after deltas, not replacement fingerprints.
    Actual split scopes and same-RG projections are tested separately by
    Test-ResourceGroupScopesContract.ps1; this gate protects their compatibility
    adapter from swallowing unrelated resource, security or output drift.
#>
[CmdletBinding()]
param([string]$MainFile = (Join-Path $PSScriptRoot '..\..\main.bicep'))

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ScopedResourceGroupNormalization.ps1')
$compiled = Join-Path $PSScriptRoot ".scoped-normalization-$([guid]::NewGuid().ToString('N')).json"
try {
    & az bicep build --file $MainFile --outfile $compiled
    if ($LASTEXITCODE -ne 0) { throw 'Actual foundation compilation failed.' }
    $json = Get-Content $compiled -Raw
    $actual = $json | ConvertFrom-Json -AsHashtable -Depth 100
    $actualBefore = ConvertTo-Json -InputObject $actual -Depth 100 -Compress
    $legacy = ConvertTo-HistoricalFoundationGraph (ConvertTo-LegacyResourceGroupGraph $actual) $MainFile
    if ((ConvertTo-Json -InputObject $actual -Depth 100 -Compress) -cne $actualBefore) {
        throw 'Projection mutated the actual deployment graph.'
    }
    $historicalJson = ConvertTo-Json -InputObject $legacy -Depth 100 -Compress
    if ($legacy.resources.Contains('networkLayoutValidation') -or
        $legacy.outputs.Contains('AZURE_NETWORK_RESOURCE_GROUP') -or
        $legacy.resources.natGateway.type -cne 'Microsoft.Network/natGateways') {
        throw 'Projection did not restore historical membership and direct resource representation.'
    }

    $mutations = @(
        @{ Name = 'egress external policy adoption'; Change = { param($t) $t.resources.firewall.properties.template.outputs.policyResourceId.value = '/external/policy' } },
        @{ Name = 'egress source wildcard'; Change = { param($t) $t.outputs.HOSTED_AGENT_DEPLOYMENT.value.workloadEgress.subnets.containerapp = '*' } },
        @{ Name = 'egress isolation gate removed'; Change = { param($t) $t.outputs.HOSTED_AGENT_DEPLOYMENT.value.workloadEgress.networkIsolation = $true } },
        @{ Name = 'egress extra selector'; Change = { param($t) $t.outputs.HOSTED_AGENT_DEPLOYMENT.value.workloadEgress.subnets.unexpected = '*' } },
        @{ Name = 'wrong Foundry scope'; Change = { param($t) $t.resources.aiFoundry.resourceGroup = 'wrong-group' } },
        @{ Name = 'wrong network scope'; Change = { param($t) $t.resources.virtualNetwork.resourceGroup = 'wrong-group' } },
        @{ Name = 'grounding Storage moved to app'; Change = { param($t) $t.resources.storageAccount.resourceGroup = '[resourceGroup().name]' } },
        @{ Name = 'default same-RG fallback removed'; Change = { param($t) $t.parameters.applicationResourceGroupName.defaultValue = 'different' } },
        @{ Name = 'Foundry root rebound'; Change = { param($t) $t.variables._foundryResourceGroupName = 'wrong-group' } },
        @{ Name = 'application deployed into Foundry'; Change = { param($t) $t.resources.containerRegistry.resourceGroup = "[variables('_foundryResourceGroupName')]" } },
        @{ Name = 'application module property drift'; Change = { param($t) $t.resources.keyVault.properties.template.resources.vault.properties.enableRbacAuthorization = $false } },
        @{ Name = 'custom application output drift'; Change = { param($t) $t.outputs.AZURE_APP_RESOURCE_GROUP.value = 'wrong-group' } },
        @{ Name = 'nested Foundry PE target drift'; Change = { param($t) $t.resources.aiFoundry.properties.parameters.privateEndpointResourceGroupResourceId.value = '/wrong/target' } },
        @{ Name = 'moved NAT SKU drift'; Change = { param($t) $t.resources.natGateway.properties.template.resources[1].sku.name = 'Basic' } },
        @{ Name = 'extra resource inside moved wrapper'; Change = { param($t) $t.resources.natGateway.properties.template.resources += @{ type = 'Microsoft.Network/natGateways'; name = 'unexpected' } } },
        @{ Name = 'layout validation disabled'; Change = { param($t) $t.resources.networkLayoutValidation.condition = $false } },
        @{ Name = 'new network output drift'; Change = { param($t) $t.outputs.AZURE_NETWORK_RESOURCE_GROUP.value = 'wrong-group' } },
        @{ Name = 'new AppConfig metadata drift'; Change = { param($t) $t.resources.appConfigPopulate.properties.parameters.keyValues.value += @{ name = 'unexpected'; value = 'drift' } } },
        @{ Name = 'explicit RG role scope regressed'; Change = { param($t) $t.resources.assignTestVmRoles.properties.template.resources.roleAssignment.properties.template.resources.assignment.scope = "[if(empty(parameters('roleAssignments')[copyIndex()].resourceId), '', parameters('roleAssignments')[copyIndex()].resourceId)]" } },
        @{ Name = 'service roles promoted to RG'; Change = { param($t) $t.resources.assignExecutorRoles.properties.template.resources.roleAssignment.properties.template.resources.assignment.scope = '' } },
        @{ Name = 'role assignment GUID drift'; Change = { param($t) $t.resources.assignCrossServiceRoles.properties.template.resources.roleAssignment.properties.template.resources.assignment.name = '[newGuid()]' } },
        @{ Name = 'unrelated existing resource drift'; Change = { param($t) $t.resources.logAnalytics.name = 'unexpected' } },
        @{ Name = 'unrelated resource injection'; Change = { param($t) $t.resources.unexpected = @{ type = 'Microsoft.Storage/storageAccounts'; name = 'drift' } } },
        @{ Name = 'unrelated output injection'; Change = { param($t) $t.outputs.unexpected = @{ type = 'string'; value = 'drift' } } },
        @{ Name = 'compiled manifest spoofing'; Change = { param($t) $t.variables['$fxv#0'].repo = 'https://example.invalid/drift.git' } }
    )
    foreach ($case in $mutations) {
        $changed = $json | ConvertFrom-Json -AsHashtable -Depth 100
        & $case.Change $changed
        $caught = $false
        try {
            $projected = ConvertTo-HistoricalFoundationGraph (ConvertTo-LegacyResourceGroupGraph $changed) $MainFile
            # Unchanged fields must survive projection so the ORIGINAL graph
            # fingerprints, rather than an exemption, detect their drift.
            if ((ConvertTo-Json -InputObject $projected -Depth 100 -Compress) -cne $historicalJson) {
                throw 'SCOPED: mutation survives projection for original fingerprint rejection.'
            }
        }
        catch {
            if (-not $_.Exception.Message.StartsWith('SCOPED:')) { throw }
            $caught = $true
        }
        if (-not $caught) { throw "Normalizer swallowed $($case.Name)." }
        Write-Host "PASS rejected $($case.Name)"
    }
    Write-Host "Scoped graph normalization passed: exact projections, immutable actual graph, $($mutations.Count) rejected mutations; original fingerprints unchanged."
}
finally {
    if (Test-Path $compiled) { Remove-Item -LiteralPath $compiled -Force }
}
