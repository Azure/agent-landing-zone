<#
.SYNOPSIS
    Offline ADR-0031 firewall dependency/ownership contract.
.DESCRIPTION
    Pins the emitted native boundary expressions before bounded scenario
    projections, like Test-SubnetLayoutContract. Not an ARM evaluator, live
    service acceptance, throughput measurement or deployed provider parity.
#>
[CmdletBinding()]
param([string]$MainFile = (Join-Path $PSScriptRoot '..\..\bicep\main.bicep'))
$ErrorActionPreference = 'Stop'
$MainFile = (Resolve-Path -LiteralPath $MainFile).Path
. (Join-Path $PSScriptRoot 'ScopedResourceGroupNormalization.ps1')
$compiled = Join-Path ([IO.Path]::GetTempPath()) "firewall-basic-contract-$([guid]::NewGuid()).json"
$script:checks = 0
function Assert-Equal($Name, $Actual, $Expected) {
    Assert-ScopedValue $Actual $Expected "/firewall-contract/$Name"
    $script:checks++
}
try {
    & az bicep build --file $MainFile --outfile $compiled
    if ($LASTEXITCODE -ne 0) { throw 'Bicep compilation failed.' }
    $t = Get-Content $compiled -Raw | ConvertFrom-Json -AsHashtable -Depth 100
    $before = ConvertTo-Json -InputObject $t -Depth 100 -Compress
    $clone = $before | ConvertFrom-Json -AsHashtable -Depth 100
    $null = Invoke-ScopedProjection $clone (Get-FirewallBasicProjection)
    Assert-Equal 'projection never mutates deployed graph' (ConvertTo-Json -InputObject $t -Depth 100 -Compress) $before
    Assert-Equal 'ARM output budget unchanged' $t.outputs.Count 64
    $f = $t.resources.firewall.properties.template
    Assert-Equal 'native and module SKU defaults agree' @($t.parameters.azureFirewallSku.defaultValue, $f.parameters.azureFirewallSku.defaultValue) @('Basic', 'Basic')
    Assert-Equal 'native SKU enum' $t.parameters.azureFirewallSku.allowedValues @('Basic', 'Standard')
    Assert-Equal 'module SKU enum' $f.parameters.azureFirewallSku.allowedValues @('Basic', 'Standard')
    $active = "[and(parameters('deployAzureFirewall'), parameters('networkIsolation'))]"
    foreach ($resource in 'firewallPublicIp', 'firewallPolicy', 'azureFirewall', 'firewallPolicyDefaultRuleCollectionGroup') {
        Assert-Equal "$resource requires active isolated local firewall" $f.resources[$resource].condition $active
    }
    Assert-Equal 'management IP uses Basic-only gate' $f.resources.firewallManagementPublicIp.condition "[variables('_basicManagement')]"
    Assert-Equal 'management public IP same zone policy as data IP' $f.resources.firewallManagementPublicIp.Contains('zones') $f.resources.firewallPublicIp.Contains('zones')
    Assert-Equal 'management IP Standard static IPv4' @($f.resources.firewallManagementPublicIp.sku.name, $f.resources.firewallManagementPublicIp.properties.publicIPAllocationMethod, $f.resources.firewallManagementPublicIp.properties.publicIPAddressVersion) @('Standard', 'Static', 'IPv4')
    Assert-Equal 'data subnet ID unchanged' $f.variables._firewallSubnetId "[if(parameters('networkIsolation'), format('{0}/subnets/{1}', parameters('virtualNetworkResourceId'), parameters('azureFirewallSubnetName')), '')]"
    Assert-Equal 'UDR consumes data-plane private IP, never management IP' $t.resources.defaultRoute.properties.parameters.nextHopIpAddress "[if(parameters('deployAzureFirewall'), createObject('value', reference('firewall').outputs.privateIp.value), if(variables('_hasExternalEgress'), createObject('value', parameters('hubIntegrationEgressNextHopIp')), createObject('value', '')))]"
    Assert-Equal 'firewall validation orders BYO and new paths' ($t.resources.firewall.dependsOn -contains 'networkLayoutValidation') $true
    Assert-Equal 'media policy writes serialized' $f.resources.firewallPolicyAcsMediaRuleCollectionGroup.dependsOn @('firewallPolicy', 'firewallPolicyDefaultRuleCollectionGroup')
    Assert-Equal 'build policy writes serialized behind firewall and both groups' $f.resources.firewallPolicyAcrTaskAgentPoolRuleCollectionGroup.dependsOn @('azureFirewall', 'firewallPolicy', 'firewallPolicyAcsMediaRuleCollectionGroup', 'firewallPolicyDefaultRuleCollectionGroup')
    Assert-Equal 'diagnostics preserved on active firewall' $f.resources.firewallDiagnostics.condition "[and(and(parameters('deployAzureFirewall'), parameters('networkIsolation')), parameters('hasEffectiveLaw'))]"
    $root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MainFile))
    $bindings = (Get-Content (Join-Path $root 'main.parameters.json') -Raw | ConvertFrom-Json -AsHashtable).parameters
    $seed = (Get-Content (Join-Path (Split-Path -Parent $MainFile) 'main.parameters.json') -Raw | ConvertFrom-Json -AsHashtable).parameters
    foreach ($key in 'azureFirewallSku', 'azureFirewallManagementSubnetName', 'azureFirewallManagementSubnetPrefix', 'deployAzureFirewallSubnet', 'deployAzureFirewallManagementSubnet', 'deployGatewaySubnet') {
        Assert-Equal "$key native seed/root transport agrees" $seed[$key] $bindings[$key]
    }

    # Compare production preflight selection with the exact native expressions
    # checked above, using compiled defaults rather than a second default table.
    $script:Findings = [System.Collections.Generic.List[pscustomobject]]::new()
    $preflightSource = Get-Content (Join-Path $PSScriptRoot '..\..\..\scripts\infra\Invoke-PreflightChecks.ps1') -Raw
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($preflightSource, [ref]$null, [ref]$null)
    foreach ($function in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
        Invoke-Expression $function.Extent.Text
    }
    $defaults = @{}
    foreach ($key in $t.parameters.Keys) {
        if ($t.parameters[$key].Contains('defaultValue')) { $defaults[$key] = $t.parameters[$key].defaultValue }
        elseif ($t.parameters[$key].nullable) { $defaults[$key] = $null }
    }
    foreach ($isolated in $false, $true) {
        foreach ($local in $false, $true) {
            foreach ($sku in 'Basic', 'Standard') {
                foreach ($hubGateway in $false, $true) {
                    $activeFirewall = $isolated -and $local
                    $management = $activeFirewall -and $sku -ceq 'Basic'
                    foreach ($intent in @($null, $false, $true)) {
                        foreach ($global in $false, $true) {
                            $p = $defaults.Clone()
                            $p.networkIsolation = $isolated; $p.deployAzureFirewall = $local; $p.azureFirewallSku = $sku
                            $p.hubIntegrationPeeringUseRemoteGateways = $hubGateway
                            $p.deploySubnets = $global
                            $p.deployAzureFirewallSubnet = $intent; $p.deployAzureFirewallManagementSubnet = $intent
                            $selected = @(Get-SubnetSelection -P $p)
                            Assert-Equal 'data selection agrees with native auto/explicit intent' ($selected | Where-Object Flag -eq deployAzureFirewallSubnet).Managed ($isolated -and $global -and ($intent ?? $activeFirewall))
                            Assert-Equal 'management selection agrees with native Basic-only intent' ($selected | Where-Object Flag -eq deployAzureFirewallManagementSubnet).Managed ($global -and $management -and ($intent ?? $true))
                            Assert-Equal 'GatewaySubnet never follows hub gateway transit' ($selected | Where-Object Flag -eq deployGatewaySubnet).Managed $false
                            $p.deployGatewaySubnet = $true
                            Assert-Equal 'explicit local gateway reservation respects global and isolation gates' (Get-SubnetSelection -P $p | Where-Object Flag -eq deployGatewaySubnet).Managed ($global -and $isolated)
                        }
                    }
                }
            }
        }
    }
    Write-Host "Basic firewall contract passed: $script:checks assertions; exact native gates, dependencies and unchanged 64 outputs; Bicep $($t.metadata._generator.version)."
}
finally {
    Remove-Item -LiteralPath $compiled -Force -ErrorAction SilentlyContinue
}
