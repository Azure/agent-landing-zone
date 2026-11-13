<#
.SYNOPSIS
    Offline compiled contracts for optional PostgreSQL; never deploys Azure.
#>
[CmdletBinding()]
param([string]$MainFile = (Join-Path $PSScriptRoot '../../bicep/main.bicep'))
$ErrorActionPreference = 'Stop'
$compiled = Join-Path ([IO.Path]::GetTempPath()) "postgresql-$([guid]::NewGuid()).json"
$beforeFile = "$compiled.before.json"
. (Join-Path $PSScriptRoot 'ScopedResourceGroupNormalization.ps1')
function Assert($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Contains($Value, [string[]]$Fragments, [string]$Message) {
    foreach ($fragment in $Fragments) { Assert ([string]$Value).Contains($fragment) "$Message ($fragment)" }
}
try {
    & az bicep build --file $MainFile --outfile $compiled --only-show-errors
    Assert ($LASTEXITCODE -eq 0) 'Bicep compilation failed.'
    $t = Get-Content $compiled -Raw | ConvertFrom-Json -Depth 100
    Assert ($t.parameters.deployPostgreSql.defaultValue -ceq $false) 'PostgreSQL must default off.'
    $defaults = @{
        postgreSqlVersion = '16'; postgreSqlTier = 'Burstable'; postgreSqlSkuName = 'Standard_B1ms'
        postgreSqlStorageSizeGb = 32; postgreSqlBackupRetentionDays = 7
        postgreSqlHighAvailability = 'Disabled'; postgreSqlGeoRedundantBackup = $false
        postgreSqlStorageAutoGrow = $false; postgreSqlDatabaseName = 'agentlz'
    }
    foreach ($key in $defaults.Keys) { Assert ($t.parameters.$key.defaultValue -ceq $defaults[$key]) "Default: $key" }
    $pg = $t.resources.postgreSql
    Contains $pg.condition @("parameters('deployPostgreSql')") 'Server must be explicitly gated.'
    Contains $pg.resourceGroup @("_applicationResourceGroupName") 'Server belongs to application RG.'
    $p = $pg.properties.parameters
    Assert ($null -eq $p.administratorLogin -and $null -eq $p.administratorLoginPassword -and $null -eq $p.lock) 'No password or IaC-owned lock.'
    Assert ($p.authConfig.value.activeDirectoryAuth -ceq 'Enabled') 'Entra enabled.'
    Assert ($p.authConfig.value.passwordAuth -ceq 'Disabled') 'Password disabled.'
    Contains $p.authConfig.value.tenantId @('tenantId') 'Resolved tenant.'
    Contains ($p.administrators.value | ConvertTo-Json -Depth 20) @('postgreSqlAdministratorObjectId', 'postgreSqlAdministratorPrincipalName', 'postgreSqlAdministratorPrincipalType', 'tenantId') 'Explicit administrator.'
    Contains ($p.databases.value | ConvertTo-Json -Depth 20) @('postgreSqlDatabaseName') 'Application database.'
    Contains $p.publicNetworkAccess @('_networkIsolation', 'Disabled', 'Enabled') 'Public only Basic, independent of global allowed IPs.'
    Assert ($null -eq $p.delegatedSubnetResourceId -and $null -eq $p.privateDnsZoneArmResourceId) 'Private Link, not delegated PostgreSQL networking.'
    Contains $t.variables._postgreSqlBasic @('deployPostgreSql', '_networkIsolation') 'Basic gate.'
    Contains $t.resources.containerAppsPostgreSqlNat.condition @('_postgreSqlBasic') 'Dedicated NAT gate.'
    $nat = $t.resources.containerAppsPostgreSqlNat.properties.template
    $gateway = @($nat.resources | Where-Object type -eq 'Microsoft.Network/natGateways')[0]
    $publicIp = @($nat.resources | Where-Object type -eq 'Microsoft.Network/publicIPAddresses')[0]
    Assert ($gateway.sku.name -ceq 'Standard') 'Standard NAT.'
    Assert ($publicIp.sku.name -ceq 'Standard') 'Standard public IP.'
    Assert ($publicIp.properties.publicIPAddressVersion -ceq 'IPv4') 'IPv4 public IP.'
    Assert ($publicIp.properties.publicIPAllocationMethod -ceq 'Static') 'Static public IP.'
    Contains $p.firewallRules @('_postgreSqlBasic', 'containerAppsPostgreSqlNat', '_postgreSqlOperatorRules') 'Firewall exact egress plus explicit ranges.'
    $operatorRules = @($t.variables.copy | Where-Object name -eq '_postgreSqlOperatorRules')
    Assert ($operatorRules.Count -eq 1) 'Operator rules have one compiled loop.'
    Contains $operatorRules[0].count @('postgreSqlAllowedIpRanges') 'Only explicit operator ranges.'
    Contains ($operatorRules[0].input | ConvertTo-Json -Depth 20) @('parseCidr', 'network', 'broadcast') 'Inclusive start/end range normalization.'
    Contains $t.resources.containerEnv.properties.parameters.properties.value.vnetConfiguration @('_acaVnetIntegration') 'ACA integrated when Basic PostgreSQL enabled.'
    Contains $t.resources.containerEnv.properties.parameters.properties.value.vnetConfiguration @('_acaVnetIntegration', '_networkIsolation') 'Basic ACA retains external ingress.'
    $pe = $t.resources.postgreSqlPrivateEndpoint
    Contains $pe.condition @('deployPostgreSql', '_networkIsolation') 'Isolated PE gate.'
    Contains $pe.properties.parameters.subnetResourceId @('applicationPeSubnetName', '_networkIsolation') 'Application PE subnet.'
    Contains ($pe.properties.parameters.privateLinkServiceConnections.value | ConvertTo-Json -Depth 20) @('postgresqlServer') 'Private Link group.'
    Contains ($t.variables._dnsZonesList | ConvertTo-Json -Depth 20) @('deployPostgreSql', 'privatelink.postgres.database.azure.com', '_byoZonePostgreSql') 'Managed/existing PostgreSQL DNS.'
    Contains $t.variables._dnsZonePostgreSqlId @('existingPrivateDnsZonePostgreSqlResourceId', 'privatelink.postgres.database.azure.com') 'Existing DNS ownership.'
    Contains $pe.properties.parameters.privateDnsZoneGroup @('policyManagedPrivateDns') 'Policy DNS creates no group.'
    $server = $pg.properties.template.resources.flexibleServer
    Assert ($server.apiVersion -ceq '2026-01-01-preview') 'Verified AVM preview API pin.'
    Contains ($server.properties.authConfig | ConvertTo-Json -Depth 20) @('authConfig') 'Server consumes explicit authentication.'
    # Module defaults never become dummy passwords; nullable fields stay null.
    Assert ($pg.properties.template.parameters.administratorLogin.defaultValue -eq $null) 'AVM login stays nullable.'
    Assert ($pg.properties.template.parameters.administratorLoginPassword.defaultValue -eq $null) 'AVM password stays nullable.'
    Assert ($null -eq $pg.properties.parameters.lock) 'Caller never owns the independent lock.'
    Assert ($pg.properties.template.parameters.lock.nullable -eq $true -and $null -eq $pg.properties.template.parameters.lock.defaultValue) 'AVM cannot create a lock by default.'
    Assert ($t.resources.virtualNetwork.properties.parameters.subnets.value -ceq "[variables('subnets')]") 'New VNet consumes deterministic subnets variable.'
    Assert ($t.resources.virtualNetworkSubnets.properties.parameters.subnets.value -ceq "[variables('subnets')]") 'BYO subnets consume deterministic subnets variable.'
    Contains $t.variables.subnets @('_postgreSqlBasic', 'acaEnvironment', 'natGatewayResourceId', 'Microsoft.Network/natGateways', 'aca-postgresql-') 'Dedicated NAT is associated to ACA subnet.'
    Contains ($t.resources.virtualNetwork.dependsOn | ConvertTo-Json) @('containerAppsPostgreSqlNat') 'New VNet waits for dedicated PostgreSQL NAT.'
    Contains ($t.resources.virtualNetworkSubnets.dependsOn | ConvertTo-Json) @('containerAppsPostgreSqlNat') 'BYO subnets wait for dedicated PostgreSQL NAT.'
    Assert ($t.resources.natGateway.properties.parameters.name.value -cnotmatch 'aca-postgresql') 'Jumpbox NAT naming is unchanged.'
    Contains ($t.resources.containerEnv.dependsOn | ConvertTo-Json) @('virtualNetwork') 'ACA waits for VNet/subnet association.'
    Contains ($pg.dependsOn | ConvertTo-Json) @('containerAppsPostgreSqlNat') 'Server/firewall waits for NAT IP.'
    # Preserve the original 64 outputs. Shared verified postProvision supplies
    # PG azd keys for both providers; native TF keys are only additive hints.
    Assert (@($t.outputs.PSObject.Properties).Count -eq 64) 'Native Bicep output budget must stay 64.'
    foreach ($name in @('POSTGRESQL_SERVER_RESOURCE_ID','POSTGRESQL_HOST','POSTGRESQL_PORT','POSTGRESQL_DATABASE_NAME','CONTAINER_APPS_POSTGRESQL_EGRESS_IP')) {
        Assert ($null -eq $t.outputs.$name) "Bicep PG key must be adapter-owned: $name"
    }
    Contains $t.outputs.VNET_RESOURCE_ID.value @('_acaVnetIntegration', 'existingVnetResourceId', 'virtualNetwork') 'Adapter can locate the effective Basic/isolated VNet.'
    Contains $nat.outputs.publicIpAddress.value @('publicIpName', 'ipAddress') 'Actual egress IP remains available inside foundation.'
    # Check both tracked seeds, including explicit typed ranges with no env alias.
    foreach ($file in @((Join-Path $PSScriptRoot '../../../main.parameters.json'), (Join-Path $PSScriptRoot '../../bicep/main.parameters.json'))) {
        $seed = (Get-Content $file -Raw | ConvertFrom-Json -Depth 100).parameters
        Assert ($seed.deployPostgreSql.value -ceq '${DEPLOY_POSTGRESQL=false}') 'Default-off seed mapping.'
        Assert ($seed.postgreSqlAllowedIpRanges.value -is [array] -and $seed.postgreSqlAllowedIpRanges.value.Count -eq 0) 'Typed operator ranges.'
    }
    $actual = Get-Content $compiled -Raw | ConvertFrom-Json -AsHashtable -Depth 100
    $preSubnet = ConvertTo-PreSubnetConditionalReferencesGraph (ConvertTo-PreModelDeploymentsOptionalGraph $actual)
    $before = ConvertTo-ModelDeploymentsOptionalPrePostgreSqlGraph (ConvertTo-DeterministicSubnetPrePostgreSqlGraph (ConvertTo-PrePostgreSqlGraph $preSubnet))
    Assert ((Get-PostgreSqlDigest 'Enabled') -cne (Get-PostgreSqlDigest 'enabled')) 'Digest caching must not swallow case-only mutations.'
    [IO.File]::WriteAllText($beforeFile, (ConvertTo-Json -InputObject $before -Depth 100 -Compress))
    & python (Join-Path $PSScriptRoot 'postgresql_disabled_ast.py') $compiled $beforeFile
    Assert ($LASTEXITCODE -eq 0) 'Disabled preexisting graph equivalence failed.'
    # Every deploying field accepted by the inverse gets a rejection mutation.
    # Original fingerprints additionally reject untouched/unrelated drift.
    $preSubnetJson = ConvertTo-Json -InputObject $preSubnet -Depth 100 -Compress
    foreach ($rule in Get-PostgreSqlDelta) {
        $changed = $preSubnetJson | ConvertFrom-Json -AsHashtable -Depth 100
        $parts = $rule.path.TrimStart('/').Split('/')
        $parent = $changed
        foreach ($part in $parts[0..($parts.Length - 2)]) {
            if ($parent -is [array]) { $parent = $parent[[int]$part] }
            else { $parent = $parent[$part] }
        }
        $parent[$parts[-1]] = 'unreviewed-postgresql-mutation'
        $rejected = $false
        try { $null = ConvertTo-PrePostgreSqlGraph $changed }
        catch {
            if (-not $_.Exception.Message.StartsWith('SCOPED:')) { throw }
            $rejected = $true
        }
        Assert $rejected "Projection swallowed mutation at $($rule.path)"
    }
    Write-Host "PostgreSQL compiled contracts passed: $(@(Get-PostgreSqlDelta).Count) exact delta mutations rejected (offline, not deployed parity)."
}
finally { Remove-Item $compiled, $beforeFile -Force -ErrorAction SilentlyContinue }
