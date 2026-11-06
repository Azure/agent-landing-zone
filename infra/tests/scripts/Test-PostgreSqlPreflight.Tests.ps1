# AST-loaded helpers only: no tooling probes, credentials, Azure or writes.
$ErrorActionPreference = 'Stop'
$path = Join-Path $PSScriptRoot '../../../scripts/infra/Invoke-PreflightChecks.ps1'
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($fn in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    Invoke-Expression $fn.Extent.Text
}
function Assert($Value, [string]$Message) { if (-not $Value) { throw $Message } }
function Reset { $script:Findings = [System.Collections.Generic.List[pscustomobject]]::new() }
function Has([string]$Code) { return @($script:Findings | Where-Object Code -eq $Code).Count -gt 0 }
$SkipAzureLookups = $true
$SkipRegional = $true
$base = @{
    deployPostgreSql = $true; networkIsolation = $false; deployContainerEnv = $true
    workloadProfiles = @(@{ name = 'Consumption'; workloadProfileType = 'Consumption' })
    postgreSqlAdministratorObjectId = '00000000-0000-0000-0000-000000000004'
    postgreSqlAdministratorPrincipalName = 'pg-admin'; postgreSqlAdministratorPrincipalType = 'Group'
}
Reset
Test-PostgreSqlConfiguration -P @{ deployPostgreSql = $false; postgreSqlAdministratorObjectId = 'bad' }
Assert ($script:Findings.Count -eq 0) 'Disabled PostgreSQL must be a no-op.'
Reset
Test-PostgreSqlConfiguration -P $base
Assert (-not (Has 'POSTGRESQL_ADMIN_REQUIRED')) 'Valid administrator rejected.'
Assert (-not (Has 'POSTGRESQL_BASIC_PREREQUISITES')) 'Consumption profile in workload-profiles environment is supported.'
$r = @(ConvertTo-PostgreSqlIpRanges -Ranges @('198.51.100.7', '192.0.2.17/24'))
Assert ($r.Count -eq 2 -and $r[0].startIpAddress -eq '198.51.100.7' -and $r[1].startIpAddress -eq '192.0.2.0' -and $r[1].endIpAddress -eq '192.0.2.255') 'Inclusive IPv4 normalization.'
foreach ($bad in @('0.0.0.0','0.0.0.0/0','1.2.3.4/0','::1','999.1.1.1','1.2.3','01.2.3.4','1.2.3.4/33')) {
    $rejected = $false
    try { ConvertTo-PostgreSqlIpRanges -Ranges @($bad) | Out-Null } catch { $rejected = $true }
    Assert $rejected "Forbidden range accepted: $bad"
}
foreach ($case in @(
    @{ Change = @{ postgreSqlAdministratorObjectId = '' }; Code = 'POSTGRESQL_ADMIN_REQUIRED' }
    @{ Change = @{ postgreSqlHighAvailability = 'SameZone' }; Code = 'POSTGRESQL_SKU_HA_INVALID' }
    @{ Change = @{ postgreSqlSkuName = 'Standard_D2s_v3' }; Code = 'POSTGRESQL_SKU_HA_INVALID' }
    @{ Change = @{ postgreSqlBackupRetentionDays = 6 }; Code = 'POSTGRESQL_SIZING_INVALID' }
    @{ Change = @{ postgreSqlStorageSizeGb = 31 }; Code = 'POSTGRESQL_SIZING_INVALID' }
    @{ Change = @{ workloadProfiles = @() }; Code = 'POSTGRESQL_BASIC_PREREQUISITES' }
    @{ Change = @{ acaEnvironmentSubnetPrefix = '192.168.1.0/28' }; Code = 'POSTGRESQL_BASIC_PREREQUISITES' }
    @{ Change = @{ hubIntegrationEgressNextHopIp = '10.0.0.4' }; Code = 'POSTGRESQL_BASIC_FORCED_ROUTE' }
    @{ Change = @{ postgreSqlAllowedIpRanges = @('0.0.0.0') }; Code = 'POSTGRESQL_IP_RANGE_INVALID' }
    @{ Change = @{ networkIsolation = $true; policyManagedPrivateDns = $true; existingPrivateDnsZonePostgreSqlResourceId = '/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/dns/providers/Microsoft.Network/privateDnsZones/privatelink.postgres.database.azure.com' }; Code = 'POSTGRESQL_DNS_OWNERSHIP' }
    @{ Change = @{ networkIsolation = $true; existingPrivateDnsZonePostgreSqlResourceId = '/bad-zone' }; Code = 'POSTGRESQL_DNS_OWNERSHIP' }
)) {
    $p = $base.Clone()
    foreach ($key in $case.Change.Keys) { $p[$key] = $case.Change[$key] }
    Reset
    Test-PostgreSqlConfiguration -P $p
    Assert (Has $case.Code) "Missing rejection: $($case.Code)"
}
Reset
$p = $base.Clone()
$p.networkIsolation = $true
$p.deployContainerEnv = $false
Test-PostgreSqlConfiguration -P $p
Assert (-not (Has 'POSTGRESQL_BASIC_PREREQUISITES')) 'Isolated PostgreSQL does not require ACA.'
Assert (@(Get-SubnetSelection -P $base | Where-Object Managed).Count -eq 1) 'Basic PostgreSQL creates only ACA subnet.'

# Synthetic Azure reads exercise routing/DNS/admin failures, not real Azure.
function Test-AzureContext { return @{ tenantId = '00000000-0000-0000-0000-000000000001' } }
$script:Calls = [System.Collections.Generic.List[string]]::new()
$script:MockVnet = @{
    properties = @{
        addressSpace = @{ addressPrefixes = @('192.168.0.0/21') }
        subnets = @(@{ name = 'aca-environment-subnet'; properties = @{ addressPrefix = '192.168.1.0/24'; routeTable = @{ id = '/corporate-route' } } })
    }
}
$script:MockPrincipalName = 'pg-admin'
$script:MockLinks = @()
function Invoke-AzCli {
    param([string[]]$Arguments)
    $script:Calls.Add(($Arguments -join ' '))
    if ($Arguments[0] -eq 'ad') { return @{ id = $base.postgreSqlAdministratorObjectId; displayName = $script:MockPrincipalName } }
    if ($Arguments[0] -eq 'rest') { return @{ value = $script:MockLinks } }
    if ($Arguments[1] -eq 'vnet') { return $script:MockVnet }
    if ($Arguments[1] -eq 'private-dns') { return @{ name = 'privatelink.postgres.database.azure.com' } }
    if ($Arguments[0] -eq 'postgres') { return @(@{ name = 'Standard_B1ms' }) }
    throw 'Unexpected mocked Azure operation.'
}
$SkipAzureLookups = $false
$p = $base.Clone()
$p.useExistingVNet = $true
$p.existingVnetResourceId = '/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/workload'
Reset
Test-PostgreSqlConfiguration -P $p
Assert (Has 'POSTGRESQL_BASIC_FORCED_ROUTE') 'Existing corporate ACA route-table association cannot be overwritten.'
Assert (-not @($script:Calls | Where-Object { $_ -match '(create|update|delete|--method put|--method post)' }).Count) 'Preflight never writes network resources.'
$script:MockPrincipalName = 'wrong-admin'
Reset
Test-PostgreSqlConfiguration -P $base
Assert (Has 'POSTGRESQL_ADMIN_NAME_MISMATCH') 'Administrator object/name mismatch rejected.'
$script:MockPrincipalName = 'pg-admin'
$p = $base.Clone()
$p.networkIsolation = $true
$p.existingVnetResourceId = '/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/workload'
$p.existingPrivateDnsZonePostgreSqlResourceId = '/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/dns/providers/Microsoft.Network/privateDnsZones/privatelink.postgres.database.azure.com'
Reset
Test-PostgreSqlConfiguration -P $p
Assert (Has 'POSTGRESQL_DNS_BINDING_MISSING') 'Existing private zone without a selected VNet link is rejected.'
$script:MockLinks = @(@{ properties = @{ virtualNetwork = @{ id = $p.existingVnetResourceId }; provisioningState = 'Succeeded' } })
Reset
Test-PostgreSqlConfiguration -P $p
Assert (-not (Has 'POSTGRESQL_DNS_BINDING_MISSING')) 'Valid externally owned zone link is accepted without mutation.'
$count = $script:Calls.Count
$SkipAzureLookups = $true
Reset
Test-PostgreSqlConfiguration -P $p
Assert ($script:Calls.Count -eq $count) '-SkipAzureLookups prohibits Azure reads.'

Write-Host 'PostgreSQL preflight contracts passed (offline).'
