<#
.SYNOPSIS
    Compiles and validates the ADR-0027/0031 topology-aware subnet contract.
.DESCRIPTION
    Uses the existing Azure CLI Bicep compiler without Azure credentials/writes.
    Exact emitted expressions guard bounded scenario projections, not a generic
    ARM evaluator. Reused subnet discovery/properties and provider registration
    remain Azure-aware preflight responsibilities. No historical hashes change.
#>
[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'bicep/main.bicep')
)

$ErrorActionPreference = 'Stop'
$compiledFile = Join-Path ([IO.Path]::GetTempPath()) "subnet-layout-contract-$([guid]::NewGuid()).json"
$script:checks = 0

function Assert-Equal($Name, $Actual, $Expected) {
    $a = ConvertTo-Json -InputObject $Actual -Compress -Depth 100
    $e = ConvertTo-Json -InputObject $Expected -Compress -Depth 100
    if ($a -cne $e) { throw "$Name -- expected $e; got $a" }
    $script:checks++
}

function Assert-Rejected($Name, [scriptblock]$Action) {
    $rejected = $false
    try { $null = & $Action } catch { $rejected = $true }
    Assert-Equal $Name $rejected $true
}

# Each row binds purpose, creation flag, input stem, default name/CIDR, and azd
# name/prefix alias. Keeping this explicit catches a flag wired to another role.
$layout = @(
    ,@('agent', 'deployAgentSubnet', 'agentSubnet', 'agent-subnet', '192.168.0.0/24', 'AGENT', 'Microsoft.App/environments')
    ,@('pe', 'deployPeSubnet', 'peSubnet', 'pe-subnet', '192.168.2.0/26', 'PE', '')
    ,@('gateway', 'deployGatewaySubnet', 'gatewaySubnet', 'GatewaySubnet', '192.168.2.192/26', 'GATEWAY', '')
    ,@('bastion', 'deployAzureBastionSubnet', 'azureBastionSubnet', 'AzureBastionSubnet', '192.168.2.64/26', 'BASTION', '')
    ,@('firewall', 'deployAzureFirewallSubnet', 'azureFirewallSubnet', 'AzureFirewallSubnet', '192.168.2.128/26', 'FIREWALL', '')
    ,@('appGateway', 'deployAppGatewaySubnet', 'azureAppGatewaySubnet', 'AppGatewaySubnet', '192.168.3.0/27', 'APP_GATEWAY', '')
    ,@('jumpbox', 'deployJumpboxSubnet', 'jumpboxSubnet', 'jumpbox-subnet', '192.168.3.64/27', 'JUMPBOX', '')
    ,@('acaEnvironment', 'deployAcaEnvironmentSubnet', 'acaEnvironmentSubnet', 'aca-environment-subnet', '192.168.1.0/24', 'ACA_ENVIRONMENT', 'Microsoft.App/environments')
    ,@('devopsBuildAgents', 'deployDevopsBuildAgentsSubnet', 'devopsBuildAgentsSubnet', 'devops-build-agents-subnet', '192.168.3.96/27', 'DEVOPS_BUILD_AGENTS', '')
    ,@('applicationPe', 'deployApplicationPeSubnet', 'applicationPeSubnet', 'application-pe-subnet', '192.168.3.128/26', 'APPLICATION_PE', '')
    ,@('powerPlatform', 'deployPowerPlatformSubnet', 'powerPlatformSubnet', 'powerplatform-subnet', '192.168.4.0/24', 'POWER_PLATFORM', 'Microsoft.PowerPlatform/enterprisePolicies')
    ,@('aiGateway', 'deployAiGatewaySubnet', 'aiGatewaySubnet', 'ai-gateway-subnet', '192.168.5.0/24', 'AI_GATEWAY', 'Microsoft.Web/serverFarms')
    ,@('firewallManagement', 'deployAzureFirewallManagementSubnet', 'azureFirewallManagementSubnet', 'AzureFirewallManagementSubnet', '192.168.3.192/26', 'FIREWALL_MANAGEMENT', '')
)

function Assert-LayoutShape($Template, $Bindings) {
    Assert-Equal 'Exactly thirteen definitions' $Template.variables.subnetDefinitions.Count 13
    for ($i = 0; $i -lt $layout.Count; $i++) {
        $role, $flag, $stem, $name, $cidr, $alias, $delegation = $layout[$i]
        $definition = $Template.variables.subnetDefinitions[$i]
        Assert-Equal "$role purpose" $definition.purpose $role
        $creation = switch ($role) {
            'firewall' { "[coalesce(parameters('deployAzureFirewallSubnet'), variables('_localFirewall'))]" }
            'firewallManagement' { "[and(variables('_basicFirewallManagement'), coalesce(parameters('deployAzureFirewallManagementSubnet'), true()))]" }
            default { "[parameters('$flag')]" }
        }
        Assert-Equal "$role creation ownership" $definition.create $creation
        Assert-Equal "$role name wiring" $definition.name "[parameters('${stem}Name')]"
        Assert-Equal "$role prefix wiring" $definition.addressPrefix "[parameters('${stem}Prefix')]"
        Assert-Equal "$role delegation" $definition.delegation $delegation
        $default = if ($role -eq 'gateway') { $false } elseif ($role -in 'firewall', 'firewallManagement') { $null } else { $true }
        Assert-Equal "$flag Boolean type/default" @($Template.parameters[$flag].type, $Template.parameters[$flag].defaultValue) @('bool', $default)
        if ($role -in 'firewall', 'firewallManagement') { Assert-Equal "$flag nullable" $Template.parameters[$flag].nullable $true }
        Assert-Equal "$role name default" $Template.parameters["${stem}Name"].defaultValue $name
        Assert-Equal "$role prefix default" $Template.parameters["${stem}Prefix"].defaultValue $cidr
        $flagAlias = ($flag -creplace '([a-z])([A-Z])', '$1_$2').ToUpperInvariant()
        $defaultToken = if ($null -eq $default) { 'null' } else { "$default".ToLowerInvariant() }
        Assert-Equal "$flag azd binding" $Bindings[$flag].value ('${' + $flagAlias + '=' + $defaultToken + '}')
        Assert-Equal "$role name azd binding" $Bindings["${stem}Name"].value ('${AZURE_' + $alias + '_SUBNET_NAME=' + $name + '}')
        Assert-Equal "$role prefix azd binding" $Bindings["${stem}Prefix"].value ('${AZURE_' + $alias + '_SUBNET_PREFIX=' + $cidr + '}')
    }
    Assert-Equal 'Explicit root VNet array' $Bindings.vnetAddressPrefixes.value @('192.168.0.0/21')
    Assert-Equal 'Global precedence and isolation selection' $Template.variables.selectedSubnetDefinitions "[filter(variables('subnetDefinitions'), lambda('subnet', and(and(variables('_networkIsolation'), parameters('deploySubnets')), lambdaVariables('subnet').create)))]"
}

# Bounded projection of the exact selection expression above. Names and prefixes
# are read from compiled parameter defaults, preserving explicit overrides.
function Get-Selection($Template, [hashtable]$Overrides, [bool]$Isolation = $true, [bool]$Global = $true) {
    foreach ($row in $layout) {
        $role, $flag, $stem = $row[0..2]
        $create = if ($Overrides.ContainsKey($flag)) { $Overrides[$flag] } else { $Template.parameters[$flag].defaultValue }
        $localFirewall = -not $Overrides.ContainsKey('deployAzureFirewall') -or $Overrides.deployAzureFirewall
        $basic = $localFirewall -and (-not $Overrides.ContainsKey('azureFirewallSku') -or $Overrides.azureFirewallSku -eq 'Basic') -and
            (-not $Overrides.ContainsKey('deploymentMode') -or $Overrides.deploymentMode -eq 'standalone')
        if ($role -eq 'firewall' -and $null -eq $create) { $create = $localFirewall }
        if ($role -eq 'firewallManagement') { $create = $basic -and ($null -eq $create -or $create) }
        if ($create -isnot [bool]) { throw "$flag must be a Boolean" }
        if ($Isolation -and $Global -and $create) {
            $name = if ($Overrides.ContainsKey("${stem}Name")) { $Overrides["${stem}Name"] } else { $Template.parameters["${stem}Name"].defaultValue }
            $prefix = if ($Overrides.ContainsKey("${stem}Prefix")) { $Overrides["${stem}Prefix"] } else { $Template.parameters["${stem}Prefix"].defaultValue }
            @{ purpose = $role; name = $name; addressPrefix = $prefix; create = $true; required = $false }
        }
    }
}

function Get-Range([string]$Prefix) {
    if ($Prefix -notmatch '^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$') { throw 'Invalid IPv4 CIDR' }
    $ip, $bits = $Prefix.Split('/')
    $bits = [int]$bits
    $octets = @($ip.Split('.') | ForEach-Object { [int]$_ })
    if ($bits -gt 29 -or @($octets | Where-Object { $_ -gt 255 }).Count) { throw 'Invalid subnet size/address' }
    [long]$start = 0
    foreach ($octet in $octets) { $start = $start * 256 + $octet }
    [long]$size = [Math]::Pow(2, 32 - $bits)
    if ($start % $size -ne 0) { throw 'Unaligned CIDR' }
    @{ Start = $start; End = $start + $size - 1; Bits = $bits }
}

# Projection is run only after the validation predicates/output are pinned below.
function Assert-ValidSelection($Definitions, [string[]]$Vnet = @('192.168.0.0/21'), [bool]$Byo = $false, [bool]$Nsgs = $true) {
    $relevant = @($Definitions | Where-Object { $_.create -or $_.required })
    $selected = @($Definitions | Where-Object create)
    $names = @($relevant | ForEach-Object { $_.name.ToLowerInvariant() })
    if (@($names | Select-Object -Unique).Count -ne $names.Count) { throw 'Duplicate names' }
    $reserved = @{ gateway = 'GatewaySubnet'; bastion = 'AzureBastionSubnet'; firewall = 'AzureFirewallSubnet'; firewallManagement = 'AzureFirewallManagementSubnet' }
    foreach ($subnet in $relevant) {
        if ([string]::IsNullOrEmpty($subnet.name) -or $subnet.name.Length -gt 80 -or $subnet.name.Contains('/') -or $subnet.name.Contains(' ')) { throw 'Invalid name' }
        if ($reserved.ContainsKey($subnet.purpose)) {
            if ($subnet.name -cne $reserved[$subnet.purpose]) { throw 'Invalid reserved name' }
        }
        elseif ($subnet.name.ToLowerInvariant() -in @('gatewaysubnet', 'azurebastionsubnet', 'azurefirewallsubnet', 'azurefirewallmanagementsubnet', 'routeserversubnet')) { throw 'Reserved name used by another role' }
        if ([string]::IsNullOrEmpty($subnet.addressPrefix)) { throw 'Missing required prefix' }
        if (-not $Byo -and $subnet.required -and -not $subnet.create) { throw 'Missing managed subnet in new VNet' }
    }
    $vnetRanges = if (-not $Byo) { @($Vnet | ForEach-Object { Get-Range $_ }) } else { @() }
    if (-not $Byo -and $vnetRanges.Count -eq 0) { throw 'Missing VNet address space' }
    for ($i = 0; $i -lt $selected.Count; $i++) {
        $range = Get-Range $selected[$i].addressPrefix
        if (-not $Byo -and @($vnetRanges | Where-Object { $range.Start -ge $_.Start -and $range.End -le $_.End }).Count -eq 0) { throw 'Outside VNet' }
        if ($selected[$i].purpose -eq 'aiGateway' -and ($range.Bits -gt 27 -or -not $Nsgs)) { throw 'AI Gateway requires NSG and /27 or larger' }
        if ($selected[$i].purpose -in 'firewall', 'firewallManagement' -and $range.Bits -gt 26) { throw 'Firewall subnets require /26 or larger' }
        for ($j = 0; $j -lt $i; $j++) {
            $other = Get-Range $selected[$j].addressPrefix
            if ($range.Start -le $other.End -and $range.End -ge $other.Start) { throw 'Overlapping subnets' }
        }
    }
    if ($Byo -and $selected.Count -gt 0 -and -not $Nsgs) { throw 'BYO NSG safety rejection' }
}

try {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Azure CLI Bicep is required.' }
    $env:PYTHONIOENCODING = 'utf-8'
    & az bicep build --file $MainFile --outfile $compiledFile
    if ($LASTEXITCODE -ne 0) { throw "Bicep compilation failed: $LASTEXITCODE" }
    $t = Get-Content -LiteralPath $compiledFile -Raw | ConvertFrom-Json -AsHashtable -Depth 100
    $rootParameters = Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MainFile))) 'main.parameters.json'
    $bindings = (Get-Content -LiteralPath $rootParameters -Raw | ConvertFrom-Json -AsHashtable -Depth 100).parameters
    Assert-LayoutShape $t $bindings

    $new = $t.resources.virtualNetwork
    $byo = $t.resources.virtualNetworkSubnets
    Assert-Equal 'New VNet remains gated only by ownership and isolation' $new.condition "[and(variables('_networkIsolation'), not(parameters('useExistingVNet')))]"
    Assert-Equal 'BYO only writes selected subnets with NSG safety' $byo.condition "[and(and(and(and(variables('_networkIsolation'), parameters('useExistingVNet')), parameters('deploySubnets')), parameters('deployNsgs')), not(empty(variables('selectedSubnetDefinitions'))))]"
    Assert-Equal 'Identical new/BYO resource property projection' $byo.properties.parameters.subnets.value $new.properties.parameters.subnets.value
    $projection = "[map(variables('selectedSubnetDefinitions'), lambda('subnet', createObject('name', lambdaVariables('subnet').name, 'addressPrefix', lambdaVariables('subnet').addressPrefix, 'delegation', lambdaVariables('subnet').delegation, 'serviceEndpoints', lambdaVariables('subnet').serviceEndpoints, 'networkSecurityGroupResourceId', if(and(and(equals(lambdaVariables('subnet').purpose, 'bastion'), variables('_deployBastion')), parameters('deployNsgs')), reference('bastionNsg').outputs.id.value, if(and(equals(lambdaVariables('subnet').purpose, 'appGateway'), variables('_publicIngressEnabled')), reference('appGwNsg').outputs.id.value, if(and(equals(lambdaVariables('subnet').purpose, 'aiGateway'), parameters('deployNsgs')), reference('aiGatewayNsg').outputs.id.value, ''))), 'routeTableResourceId', if(contains(createArray('agent', 'pe', 'jumpbox', 'acaEnvironment', 'devopsBuildAgents', 'applicationPe'), lambdaVariables('subnet').purpose), if(variables('_hasExistingRouteTable'), parameters('hubIntegrationExistingRouteTableResourceId'), if(variables('_createRouteTable'), reference('routeTable').outputs.resourceId.value, '')), ''), 'natGatewayResourceId', if(equals(lambdaVariables('subnet').purpose, 'jumpbox'), if(variables('_deployNatGateway'), reference('natGateway').outputs.resourceId.value, if(variables('_hasExistingNatGateway'), parameters('existingNatGatewayResourceId'), '')), ''))))]"
    Assert-Equal 'Projection excludes Gateway/Power Platform/AI Gateway UDRs, Gateway NSG and delegation controls' $new.properties.parameters.subnets.value $projection
    Assert-Equal 'BYO NSG invariant uses actual writes' $t.resources.componentFlagValidation.properties.parameters.existingSubnetNsgAssociationsAreProtected.value "[not(and(and(and(parameters('networkIsolation'), parameters('useExistingVNet')), not(empty(variables('selectedSubnetDefinitions')))), not(parameters('deployNsgs'))))]"
    Assert-Equal 'Consumer association remains independent' $t.variables.subnetDefinitions[0].required "[and(parameters('deployAiFoundry'), parameters('deployAiFoundrySubnet'))]"
    Assert-Equal 'New delegated reservations have no consuming services' @($t.variables.subnetDefinitions[10].required, $t.variables.subnetDefinitions[11].required) @($false, $false)
    Assert-Equal 'ACR pool requires its own subnet' $t.variables.subnetDefinitions[8].required "[variables('_deployAcrTaskAgentPool')]"
    Assert-Equal 'Foundry, grounding and Cosmos ACL consumers require Foundry PE subnet' $t.variables.subnetDefinitions[1].required "[or(or(or(or(or(or(parameters('deployAiFoundry'), parameters('deployStorageAccount')), parameters('deploySearchService')), parameters('deploySpeechService')), variables('_deployAiFoundryStorage')), variables('_deployAiFoundrySearch')), parameters('deployCosmosDb'))]"
    Assert-Equal 'Application consumers require dedicated application PE subnet' $t.variables.subnetDefinitions[9].required "[or(or(or(or(or(parameters('deployCosmosDb'), parameters('deployKeyVault')), parameters('deployAppConfig')), parameters('deployContainerEnv')), parameters('deployContainerRegistry')), variables('_deployAmpls'))]"
    Assert-Equal 'Other subnet consumers retain their service gates and Cosmos ACA ACL prerequisite' @($t.variables.subnetDefinitions[3].required, $t.variables.subnetDefinitions[4].required, $t.variables.subnetDefinitions[5].required, $t.variables.subnetDefinitions[6].required, $t.variables.subnetDefinitions[7].required) @("[variables('_deployBastion')]", "[variables('_localFirewall')]", "[variables('_publicIngressEnabled')]", "[variables('_deployJumpbox')]", "[or(parameters('deployContainerEnv'), parameters('deployCosmosDb'))]")
    Assert-Equal 'Management consumer only active standalone isolated Basic' $t.variables.subnetDefinitions[12].required "[variables('_basicFirewallManagement')]"
    Assert-Equal 'ACR waits for serialized BYO completion' ($t.resources.acrTaskAgentPool.dependsOn -contains 'virtualNetworkSubnets') $true

    $s = $byo.properties.template
    $writes = @($s.resources | Where-Object { $_.copy.name -eq 'subnetsM' })[0]
    $nsgs = @($s.resources | Where-Object { $_.copy.name -eq 'nsgsM' })[0]
    Assert-Equal 'BYO writes serialized' @($writes.copy.mode, $writes.copy.batchSize) @('serial', 1)
    Assert-Equal 'BYO reserved NSG exclusions' $s.variables.invalidNsgSubnets @('AzureFirewallSubnet', 'AppGatewaySubnet', 'AzureBastionSubnet', 'GatewaySubnet', 'AzureFirewallManagementSubnet')
    Assert-Equal 'No duplicate/unused generic service NSG' $nsgs.condition "[and(and(and(parameters('deploySubnets'), parameters('deployNsgs')), not(contains(variables('invalidNsgSubnets'), parameters('subnets')[copyIndex()].name))), empty(coalesce(tryGet(parameters('subnets')[copyIndex()], 'networkSecurityGroupResourceId'), '')))]"
    Assert-Equal 'BYO never deploys the complete VNet collection' @($s.resources | Where-Object name -eq 'virtualNetworkDeployment')[0].condition "[and(not(parameters('useExistingVNet')), parameters('deploySubnets'))]"
    Assert-Equal 'Child writes honor target subscription' $writes.subscriptionId "[parameters('subscriptionId')]"
    Assert-Equal 'Child writes honor target resource group' $writes.resourceGroup "[parameters('resourceGroupName')]"
    Assert-Equal 'Gateway direct attachment guard' $writes.properties.template.variables.gatewayAttachmentsAreSafe "[or(not(equals(last(split(parameters('name'), '/')), 'GatewaySubnet')), and(and(empty(parameters('networkSecurityGroupId')), empty(parameters('routeTableId'))), empty(parameters('delegations'))))]"
    Assert-Equal 'Gateway guard actually blocks writes' $writes.properties.template.resources[0].properties.addressPrefix "[if(variables('gatewayAttachmentsAreSafe'), parameters('addressPrefix'), fail('GatewaySubnet must not have an NSG, route table or delegation.'))]"

    $aiNsg = $t.resources.aiGatewayNsg
    Assert-Equal 'AI Gateway NSG creation gate' $aiNsg.condition "[and(and(and(variables('_networkIsolation'), parameters('deploySubnets')), parameters('deployAiGatewaySubnet')), parameters('deployNsgs'))]"
    $rule = $aiNsg.properties.template.resources[0].properties.securityRules[0]
    Assert-Equal 'APIM Key Vault HTTPS outbound path' @($rule.name, $rule.properties.direction, $rule.properties.access, $rule.properties.protocol, $rule.properties.destinationPortRange, $rule.properties.destinationAddressPrefix) @('AllowKeyVaultOutbound', 'Outbound', 'Allow', 'Tcp', '443', 'AzureKeyVault')
    $appSubnet = "[if(variables('_networkIsolation'), format('{0}/subnets/{1}', if(variables('_networkIsolation'), if(parameters('useExistingVNet'), parameters('existingVnetResourceId'), reference('virtualNetwork').outputs.resourceId.value), ''), parameters('applicationPeSubnetName')), '')]"
    Assert-Equal 'AMPLS dedicated application subnet with no fallback' $t.resources.privateEndpointPrivateLinkScope.properties.parameters.subnetResourceId "[if(variables('_networkIsolation'), createObject('value', format('{0}/subnets/{1}', if(variables('_networkIsolation'), if(parameters('useExistingVNet'), parameters('existingVnetResourceId'), reference('virtualNetwork').outputs.resourceId.value), ''), parameters('applicationPeSubnetName'))), createObject('value', ''))]"
    Assert-Equal 'Five application PE aggregator overrides remain dedicated' ([regex]::Matches($t.resources.privateEndpoints.properties.parameters.endpoints.value, [regex]::Escape($appSubnet.Trim('[', ']'))).Count) 5

    $v = $t.resources.networkLayoutValidation.properties.template
    Assert-Equal 'Isolated validation only' $t.resources.networkLayoutValidation.condition "[variables('_networkIsolation')]"
    Assert-Equal 'Validation receives effective global ownership' $t.resources.networkLayoutValidation.properties.parameters.subnetDefinitions.value "[map(variables('subnetDefinitions'), lambda('subnet', createObject('purpose', lambdaVariables('subnet').purpose, 'name', lambdaVariables('subnet').name, 'addressPrefix', lambdaVariables('subnet').addressPrefix, 'create', and(parameters('deploySubnets'), lambdaVariables('subnet').create), 'required', lambdaVariables('subnet').required)))]"
    $predicates = @{
        relevant = "[filter(parameters('subnetDefinitions'), lambda('subnet', or(lambdaVariables('subnet').create, lambdaVariables('subnet').required)))]"
        selected = "[filter(parameters('subnetDefinitions'), lambda('subnet', lambdaVariables('subnet').create))]"
        names = "[map(variables('relevant'), lambda('subnet', toLower(lambdaVariables('subnet').name)))]"
        namesValid = "[empty(filter(variables('relevant'), lambda('subnet', or(or(or(empty(lambdaVariables('subnet').name), greater(length(lambdaVariables('subnet').name), 80)), contains(lambdaVariables('subnet').name, '/')), contains(lambdaVariables('subnet').name, ' ')))))]"
        namesUnique = "[equals(length(variables('names')), length(union(variables('names'), variables('names'))))]"
        reservedNamesValid = "[empty(filter(variables('relevant'), lambda('subnet', if(contains(variables('reservedNames'), lambdaVariables('subnet').purpose), not(equals(lambdaVariables('subnet').name, variables('reservedNames')[lambdaVariables('subnet').purpose])), contains(createArray('gatewaysubnet', 'azurebastionsubnet', 'azurefirewallsubnet', 'azurefirewallmanagementsubnet', 'routeserversubnet'), toLower(lambdaVariables('subnet').name))))))]"
        prefixesPresent = "[empty(filter(variables('relevant'), lambda('subnet', empty(lambdaVariables('subnet').addressPrefix))))]"
        prefixesValid = "[if(variables('prefixesPresent'), empty(filter(variables('selected'), lambda('subnet', not(__bicep.alignedIpv4(lambdaVariables('subnet').addressPrefix))))), false())]"
        vnetPrefixesValid = "[if(parameters('useExistingVNet'), true(), and(not(empty(parameters('vnetAddressPrefixes'))), empty(filter(parameters('vnetAddressPrefixes'), lambda('prefix', not(__bicep.alignedIpv4(lambdaVariables('prefix'))))))))]"
        rangesValid = "[and(variables('prefixesValid'), variables('vnetPrefixesValid'))]"
        overlaps = "[if(variables('rangesValid'), not(empty(filter(variables('selected'), lambda('subnet', not(empty(filter(variables('selected'), lambda('other', and(and(not(equals(lambdaVariables('subnet').name, lambdaVariables('other').name)), lessOrEquals(__bicep.cidrStart(lambdaVariables('subnet').addressPrefix), __bicep.cidrEnd(lambdaVariables('other').addressPrefix))), greaterOrEquals(__bicep.cidrEnd(lambdaVariables('subnet').addressPrefix), __bicep.cidrStart(lambdaVariables('other').addressPrefix))))))))))), false())]"
        contained = "[if(and(not(parameters('useExistingVNet')), variables('rangesValid')), empty(filter(variables('selected'), lambda('subnet', empty(filter(parameters('vnetAddressPrefixes'), lambda('prefix', and(greaterOrEquals(__bicep.cidrStart(lambdaVariables('subnet').addressPrefix), __bicep.cidrStart(lambdaVariables('prefix'))), lessOrEquals(__bicep.cidrEnd(lambdaVariables('subnet').addressPrefix), __bicep.cidrEnd(lambdaVariables('prefix')))))))))), true())]"
        aiGatewayValid = "[if(variables('prefixesValid'), empty(filter(variables('selected'), lambda('subnet', and(equals(lambdaVariables('subnet').purpose, 'aiGateway'), or(greater(int(split(lambdaVariables('subnet').addressPrefix, '/')[1]), 27), not(parameters('deployNsgs'))))))), false())]"
        firewallPrefixesValid = "[if(variables('prefixesValid'), empty(filter(variables('relevant'), lambda('subnet', and(contains(createArray('firewall', 'firewallManagement'), lambdaVariables('subnet').purpose), or(not(__bicep.alignedIpv4(lambdaVariables('subnet').addressPrefix)), greater(int(split(lambdaVariables('subnet').addressPrefix, '/')[1]), 26)))))), false())]"
        consumersHaveSubnets = "[or(parameters('useExistingVNet'), empty(filter(parameters('subnetDefinitions'), lambda('subnet', and(lambdaVariables('subnet').required, not(lambdaVariables('subnet').create))))))]"
        byoNsgsProtected = "[or(or(not(parameters('useExistingVNet')), empty(variables('selected'))), parameters('deployNsgs'))]"
    }
    foreach ($entry in $predicates.GetEnumerator()) { Assert-Equal "Validation $($entry.Key)" $v.variables[$entry.Key] $entry.Value }
    Assert-Equal 'Exact reserved purpose/name pairs' @($v.variables.reservedNames.gateway, $v.variables.reservedNames.bastion, $v.variables.reservedNames.firewall) @('GatewaySubnet', 'AzureBastionSubnet', 'AzureFirewallSubnet')
    Assert-Equal 'New VNet writes wait for fatal layout validation' ($new.dependsOn -contains 'networkLayoutValidation') $true
    Assert-Equal 'BYO writes wait for fatal layout validation' ($byo.dependsOn -contains 'networkLayoutValidation') $true
    Assert-Equal 'All predicates are fatal invariants' $v.outputs.validated.value "[if(or(or(not(variables('namesValid')), not(variables('namesUnique'))), not(variables('reservedNamesValid'))), fail('Subnet names must be nonempty, unique, valid names and use the exact reserved GatewaySubnet, AzureBastionSubnet, AzureFirewallSubnet and AzureFirewallManagementSubnet names for those purposes.'), if(or(or(not(variables('prefixesPresent')), not(variables('prefixesValid'))), not(variables('vnetPrefixesValid'))), fail('Required subnet prefixes must be nonempty; managed subnet and new VNet prefixes must be aligned IPv4 CIDRs with prefix length 0 through 29.'), if(or(variables('overlaps'), not(variables('contained'))), fail('Managed subnet CIDRs must not overlap and must be contained in the new VNet address space.'), if(not(variables('firewallPrefixesValid')), fail('Firewall data and management subnets require aligned IPv4 CIDRs of /26 or larger.'), if(not(variables('aiGatewayValid')), fail('Managed AI Gateway integration requires a /27 or larger subnet and deployNsgs=true.'), if(not(variables('consumersHaveSubnets')), fail('An enabled consumer requires a subnet that is not managed in the new VNet. Enable its subnet creation or disable the consumer.'), if(not(variables('byoNsgsProtected')), fail('Managed BYO subnet writes require deployNsgs=true to protect NSG associations.'), true())))))))]"
    $functions = $v.functions[0].members
    Assert-Equal 'Aligned IPv4 CIDR function' $functions.alignedIpv4.output.value "[if(equals(length(split(parameters('prefix'), '/')), 2), and(and(and(equals(length(split(split(parameters('prefix'), '/')[0], '.')), 4), equals(split(parameters('prefix'), '/')[0], parseCidr(parameters('prefix')).network)), greaterOrEquals(int(split(parameters('prefix'), '/')[1]), 0)), lessOrEquals(int(split(parameters('prefix'), '/')[1]), 29)), false())]"
    Assert-Equal 'CIDR start arithmetic' $functions.cidrStart.output.value "[reduce(split(parseCidr(parameters('prefix')).network, '.'), 0, lambda('value', 'octet', add(mul(lambdaVariables('value'), 256), int(lambdaVariables('octet')))))]"
    Assert-Equal 'CIDR end arithmetic' $functions.cidrEnd.output.value "[reduce(split(parseCidr(parameters('prefix')).broadcast, '.'), 0, lambda('value', 'octet', add(mul(lambdaVariables('value'), 256), int(lambdaVariables('octet')))))]"

    # Both ownership paths share this pinned selection. BYO validates actual
    # containing address space in preflight, never against new-VNet defaults.
    foreach ($isByo in @($false, $true)) {
        $defaults = @(Get-Selection $t @{})
        Assert-Equal "Twelve defaults; BYO=$isByo" $defaults.Count 12
        Assert-ValidSelection $defaults -Byo $isByo
        foreach ($row in $layout) {
            $selection = @(Get-Selection $t @{ $row[1] = $false })
            Assert-Equal "$($row[1]) omission; BYO=$isByo" @($selection.purpose) @($defaults | Where-Object { $_.purpose -ne $row[0] } | ForEach-Object { $_.purpose })
        }
        Assert-Equal "Global creation off; BYO=$isByo" @(Get-Selection $t @{} -Global $false).Count 0
        Assert-Equal "Public mode; BYO=$isByo" @(Get-Selection $t @{} -Isolation $false).Count 0
        $overrides = @{}
        foreach ($row in $layout) { $overrides["$($row[2])Prefix"] = $row[4].Replace('192.168.', '10.20.') }
        $custom = @(Get-Selection $t $overrides)
        Assert-Equal "Custom prefix propagation; BYO=$isByo" @($custom.addressPrefix) @($layout | Where-Object { $_[0] -ne 'gateway' } | ForEach-Object { $_[4].Replace('192.168.', '10.20.') })
        Assert-ValidSelection $custom -Vnet @('10.20.0.0/21') -Byo $isByo
    }
    foreach ($mutation in @(
        @{ applicationPeSubnetName = '' }
        @{ applicationPeSubnetPrefix = '' }
        @{ applicationPeSubnetName = 'pe-subnet' }
        @{ deployGatewaySubnet = $true; gatewaySubnetName = 'gateway-subnet' }
        @{ azureFirewallManagementSubnetName = 'management' }
        @{ azureFirewallManagementSubnetPrefix = '192.168.3.192/27' }
        @{ azureFirewallManagementSubnetPrefix = '192.168.3.193/26' }
        @{ azureFirewallManagementSubnetPrefix = '192.168.2.0/26' }
        @{ powerPlatformSubnetName = 'GatewaySubnet' }
        @{ aiGatewaySubnetPrefix = '192.168.5.0/28' }
        @{ powerPlatformSubnetPrefix = '192.168.4.1/24' }
        @{ powerPlatformSubnetPrefix = 'garbage' }
        @{ powerPlatformSubnetPrefix = '192.168.300.0/24' }
        @{ powerPlatformSubnetPrefix = 'fd00::/64' }
        @{ powerPlatformSubnetPrefix = '192.168.2.0/26' }
        @{ powerPlatformSubnetPrefix = '10.20.4.0/24' }
    )) {
        Assert-Rejected "Invalid layout $($mutation | ConvertTo-Json -Compress)" { Assert-ValidSelection @(Get-Selection $t $mutation) }
    }
    Assert-Rejected 'String Boolean is not accepted' { Get-Selection $t @{ deployPowerPlatformSubnet = 'false' } }
    Assert-Rejected 'AI Gateway cannot be managed without an NSG' { Assert-ValidSelection @(Get-Selection $t @{}) -Nsgs $false }
    $withoutAi = @(Get-Selection $t @{ deployAiGatewaySubnet = $false })
    Assert-Rejected 'BYO actual writes still require NSG safety' { Assert-ValidSelection $withoutAi -Byo $true -Nsgs $false }
    Assert-ValidSelection @() -Byo $true -Nsgs $false
    $reused = @{ purpose = 'applicationPe'; name = 'application-pe-subnet'; addressPrefix = '10.20.3.128/26'; create = $false; required = $true }
    Assert-ValidSelection @($reused) -Byo $true -Nsgs $false
    Assert-Rejected 'Enabled consumer cannot reuse a missing subnet in a new VNet' { Assert-ValidSelection @($reused) }
    Assert-ValidSelection @(Get-Selection $t @{ powerPlatformSubnetPrefix = '192.168.4.0/28' })
    Assert-ValidSelection @(Get-Selection $t @{ aiGatewaySubnetPrefix = '192.168.5.0/27' })
    $customName = @(Get-Selection $t @{ applicationPeSubnetName = 'my-application-pe'; powerPlatformSubnetName = 'my-powerplatform' })
    Assert-Equal 'Configured ordinary names propagate unchanged' @(@($customName | Where-Object purpose -eq applicationPe)[0].name, @($customName | Where-Object purpose -eq powerPlatform)[0].name) @('my-application-pe', 'my-powerplatform')

    # Cosmos-only isolation: all other consuming services are disabled. The
    # exact predicates above still require all three Cosmos ACL subnet targets.
    # In particular, disabling Foundry/Container Apps cannot excuse an omitted
    # PE/ACA subnet. BYO reuse is allowed, subject to Azure-aware preflight.
    Assert-Equal 'Cosmos retains PE, ACA and dedicated application PE subnet ACL references' $t.resources.cosmosDBAccount.properties.parameters.virtualNetworkSubnetIds "[if(variables('_networkIsolation'), createObject('value', union(createArray(if(variables('_networkIsolation'), format('{0}/subnets/{1}', if(variables('_networkIsolation'), if(parameters('useExistingVNet'), parameters('existingVnetResourceId'), reference('virtualNetwork').outputs.resourceId.value), ''), parameters('peSubnetName')), ''), if(variables('_networkIsolation'), format('{0}/subnets/{1}', if(variables('_networkIsolation'), if(parameters('useExistingVNet'), parameters('existingVnetResourceId'), reference('virtualNetwork').outputs.resourceId.value), ''), parameters('acaEnvironmentSubnetName')), '')), createArray(if(variables('_networkIsolation'), format('{0}/subnets/{1}', if(variables('_networkIsolation'), if(parameters('useExistingVNet'), parameters('existingVnetResourceId'), reference('virtualNetwork').outputs.resourceId.value), ''), parameters('applicationPeSubnetName')), '')))), createObject('value', createArray()))]"
    $cosmosOnly = @(Get-Selection $t @{} | Where-Object { $_.purpose -in @('pe', 'acaEnvironment', 'applicationPe') })
    Assert-Equal 'Cosmos-only required ACL targets' @($cosmosOnly.purpose) @('pe', 'acaEnvironment', 'applicationPe')
    foreach ($subnet in $cosmosOnly) { $subnet.required = $true }
    Assert-ValidSelection $cosmosOnly
    foreach ($subnet in $cosmosOnly) {
        $subnet.create = $false
        Assert-Rejected "Cosmos-only new VNet rejects missing $($subnet.purpose) despite other consumers being disabled" { Assert-ValidSelection $cosmosOnly }
        Assert-ValidSelection $cosmosOnly -Byo $true
        $subnet.create = $true
    }
    foreach ($subnet in $cosmosOnly) { $subnet.create = $false }
    Assert-Rejected 'Cosmos-only new VNet rejects global creation opt-out' { Assert-ValidSelection $cosmosOnly }
    Assert-ValidSelection $cosmosOnly -Byo $true -Nsgs $false
    foreach ($subnet in $cosmosOnly) { $subnet.required = $false }
    Assert-ValidSelection $cosmosOnly

    # Demonstrate the contract rejecting changed compiled definitions/gates,
    # not merely reporting happy-path source tokens.
    $bad = $t | ConvertTo-Json -Depth 100 | ConvertFrom-Json -AsHashtable -Depth 100
    $bad.variables.subnetDefinitions[11].delegation = 'Microsoft.App/environments'
    Assert-Rejected 'Reject delegation mutation' { Assert-LayoutShape $bad $bindings }
    $bad.variables.subnetDefinitions[11].delegation = 'Microsoft.Web/serverFarms'
    $bad.variables.selectedSubnetDefinitions = "[variables('subnetDefinitions')]"
    Assert-Rejected 'Reject global/isolation bypass mutation' { Assert-LayoutShape $bad $bindings }
    Write-Host "Subnet layout contract passed: $script:checks assertions; Bicep $($t.metadata._generator.version)." -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $compiledFile -Force -ErrorAction SilentlyContinue
}
