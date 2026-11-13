<#
.SYNOPSIS
    Offline compiled contract for #882 Task 1 deterministic subnet resource IDs.
.DESCRIPTION
    Proves why conditional/cross-RG 1-argument reference(...) inside map() is
    forbidden, asserts zero reference( calls in compiled subnet expressions,
    verifies exact deterministic resourceId(...) scopes and names across
    single-RG, split network RG, and cross-subscription BYO VNet topologies,
    verifies BYO route table and NAT gateway passthrough, and checks explicit
    conditional network module dependsOn on both VNet and BYO subnet paths.
#>
[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'bicep/main.bicep')
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ScopedResourceGroupNormalization.ps1')
$scratchDir = Join-Path ([IO.Path]::GetTempPath()) "subnet-cond-refs-$([guid]::NewGuid().ToString('N'))"
$null = New-Item -ItemType Directory -Path $scratchDir
$compiledFile = Join-Path $scratchDir 'main.json'
$script:checks = 0

function Assert-Equal($Name, $Actual, $Expected) {
    $a = ConvertTo-Json -InputObject $Actual -Compress -Depth 100
    $e = ConvertTo-Json -InputObject $Expected -Compress -Depth 100
    if ($a -cne $e) { throw "$Name -- expected $e; got $a" }
    $script:checks++
}

function Assert-True($Name, [bool]$Condition) {
    Assert-Equal $Name $Condition $true
}

function Assert-Rejected($Name, [scriptblock]$Action) {
    $rejected = $false
    try { $null = & $Action }
    catch {
        if (-not $_.Exception.Message.StartsWith('SCOPED:')) { throw }
        $rejected = $true
    }
    Assert-Equal $Name $rejected $true
}

# Bounded evaluator for the exact resourceId / passthrough expressions checked
# against the compiled template below. Not a general ARM evaluator.
function Resolve-SubnetAttachments {
    param(
        [string]$WorkloadSubscriptionId = '00000000-0000-0000-0000-000000000001',
        [string]$FoundryResourceGroup = 'rg-foundry',
        [string]$NetworkResourceGroupName = '',
        [bool]$NetworkIsolation = $true,
        [bool]$UseExistingVNet = $false,
        [string]$ExistingVnetResourceId = '',
        [string]$ManagedVnetName = 'vnet-spoke',
        [string]$ResourceToken = 'abc123token',
        [string]$RouteTableAbbr = 'rt-',
        [string]$NatGatewayAbbr = 'ng-',
        [bool]$DeployBastion = $true,
        [bool]$DeployNsgs = $true,
        [bool]$PublicIngressEnabled = $true,
        [bool]$PostgreSqlBasic = $false,
        [bool]$DeployNatGateway = $true,
        [string]$ExistingRouteTableResourceId = '',
        [string]$ExistingNatGatewayResourceId = '',
        [string]$BastionSubnetName = 'AzureBastionSubnet',
        [string]$AppGatewaySubnetName = 'AppGatewaySubnet',
        [string]$AiGatewaySubnetName = 'ai-gateway-subnet'
    )

    $effectiveNetworkRg = if ([string]::IsNullOrEmpty($NetworkResourceGroupName)) { $FoundryResourceGroup } else { $NetworkResourceGroupName }
    $segments = if ([string]::IsNullOrEmpty($ExistingVnetResourceId)) { @('') } else { $ExistingVnetResourceId.Split('/') }
    $existingSub = if ($segments.Count -ge 3) { $segments[2] } else { $WorkloadSubscriptionId }
    $existingRg = if ($segments.Count -ge 5) { $segments[4] } else { $FoundryResourceGroup }
    $existingVnetName = if ($segments.Count -ge 9) { $segments[8] } else { '' }

    $hasExistingRt = -not [string]::IsNullOrEmpty($ExistingRouteTableResourceId)
    $createRt = $NetworkIsolation -and (-not $hasExistingRt)
    $effectiveRouteTableId = if ($hasExistingRt) {
        $ExistingRouteTableResourceId
    }
    elseif ($createRt) {
        "/subscriptions/$WorkloadSubscriptionId/resourceGroups/$effectiveNetworkRg/providers/Microsoft.Network/routeTables/$RouteTableAbbr$ResourceToken"
    }
    else { '' }

    $hasExistingNat = -not [string]::IsNullOrEmpty($ExistingNatGatewayResourceId)
    $effectiveNatGatewayId = if ($DeployNatGateway) {
        "/subscriptions/$WorkloadSubscriptionId/resourceGroups/$effectiveNetworkRg/providers/Microsoft.Network/natGateways/$NatGatewayAbbr$ResourceToken"
    }
    elseif ($hasExistingNat) {
        $ExistingNatGatewayResourceId
    }
    else { '' }

    $purposes = @(
        'agent', 'pe', 'gateway', 'bastion', 'firewall', 'appGateway',
        'jumpbox', 'acaEnvironment', 'devopsBuildAgents', 'applicationPe',
        'powerPlatform', 'aiGateway', 'firewallManagement'
    )
    $routedPurposes = @('agent', 'pe', 'jumpbox', 'acaEnvironment', 'devopsBuildAgents', 'applicationPe')
    $result = [ordered]@{}
    foreach ($purpose in $purposes) {
        $nsgId = if ($purpose -ceq 'bastion' -and $DeployBastion -and $DeployNsgs) {
            "/subscriptions/$WorkloadSubscriptionId/resourceGroups/$effectiveNetworkRg/providers/Microsoft.Network/networkSecurityGroups/nsg-$ManagedVnetName-$BastionSubnetName"
        }
        elseif ($purpose -ceq 'appGateway' -and $PublicIngressEnabled) {
            "/subscriptions/$WorkloadSubscriptionId/resourceGroups/$effectiveNetworkRg/providers/Microsoft.Network/networkSecurityGroups/nsg-$ManagedVnetName-$AppGatewaySubnetName"
        }
        elseif ($purpose -ceq 'aiGateway' -and $DeployNsgs) {
            $aiSub = if ($UseExistingVNet) { $existingSub } else { $WorkloadSubscriptionId }
            $aiRg = if ($UseExistingVNet) { $existingRg } else { $effectiveNetworkRg }
            $aiVnet = if ($UseExistingVNet) { $existingVnetName } else { $ManagedVnetName }
            "/subscriptions/$aiSub/resourceGroups/$aiRg/providers/Microsoft.Network/networkSecurityGroups/nsg-$aiVnet-$AiGatewaySubnetName"
        }
        else { '' }

        $rtId = if ($purpose -cin $routedPurposes) { $effectiveRouteTableId } else { '' }
        $natId = if ($purpose -ceq 'jumpbox') {
            $effectiveNatGatewayId
        }
        elseif ($purpose -ceq 'acaEnvironment' -and $PostgreSqlBasic) {
            "/subscriptions/$WorkloadSubscriptionId/resourceGroups/$effectiveNetworkRg/providers/Microsoft.Network/natGateways/${NatGatewayAbbr}aca-postgresql-$ResourceToken"
        }
        else { '' }

        $result[$purpose] = @{
            networkSecurityGroupResourceId = $nsgId
            routeTableResourceId           = $rtId
            natGatewayResourceId           = $natId
        }
    }
    return $result
}

try {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Azure CLI Bicep is required.' }
    $env:PYTHONIOENCODING = 'utf-8'

    # 1. Reproduce why conditional cross-RG module outputs inside map() are forbidden:
    # Bicep compiles `nsg!.outputs.id` inside `map(...)` to a 1-arg `reference('nsg')`
    # inside `lambda(...)` under ARM languageVersion 2.0, which ARM deployment
    # validation rejects when `nsg` is conditional or scoped to another RG.
    $reproModFile = Join-Path $scratchDir 'nsg-mod.bicep'
    $reproBadFile = Join-Path $scratchDir 'repro-bad.bicep'
    $reproGoodFile = Join-Path $scratchDir 'repro-good.bicep'
    $reproBadJson = Join-Path $scratchDir 'repro-bad.json'
    $reproGoodJson = Join-Path $scratchDir 'repro-good.json'

    Set-Content -LiteralPath $reproModFile -Value @'
param name string
param location string
resource nsg 'Microsoft.Network/networkSecurityGroups@2024-07-01' = {
  name: name
  location: location
}
output id string = nsg.id
'@
    Set-Content -LiteralPath $reproBadFile -Value @'
param netRg string = 'rg-net'
param location string = resourceGroup().location
param deployNsg bool = false
param existingNsgId string?
param defs array = [{ purpose: 'bastion', name: 'AzureBastionSubnet' }]
module nsg 'nsg-mod.bicep' = if (deployNsg) {
  scope: resourceGroup(netRg)
  name: 'nsgDeploy'
  params: { name: 'nsg-vnet-AzureBastionSubnet', location: location }
}
#disable-next-line BCP318
var subnets = map(defs, s => {
  name: s.name
  nsgId: !empty(existingNsgId ?? '') ? existingNsgId! : (s.purpose == 'bastion' && deployNsg ? nsg!.outputs.id : '')
})
output projected array = subnets
'@
    Set-Content -LiteralPath $reproGoodFile -Value @'
param netRg string = 'rg-net'
param location string = resourceGroup().location
param deployNsg bool = false
param existingNsgId string?
param defs array = [{ purpose: 'bastion', name: 'AzureBastionSubnet' }]
module nsg 'nsg-mod.bicep' = if (deployNsg) {
  scope: resourceGroup(netRg)
  name: 'nsgDeploy'
  params: { name: 'nsg-vnet-AzureBastionSubnet', location: location }
}
var subnets = map(defs, s => {
  name: s.name
  nsgId: !empty(existingNsgId ?? '') ? existingNsgId! : (s.purpose == 'bastion' && deployNsg ? resourceId(netRg, 'Microsoft.Network/networkSecurityGroups', 'nsg-vnet-AzureBastionSubnet') : '')
})
module consumer 'nsg-mod.bicep' = {
  scope: resourceGroup(netRg)
  name: 'consumerDeploy'
  params: { name: first(subnets).name, location: location }
  dependsOn: [nsg]
}
'@
    & az bicep build --file $reproBadFile --outfile $reproBadJson --only-show-errors
    Assert-Equal 'Repro bad Bicep compiles offline despite invalid ARM lambda reference' $LASTEXITCODE 0
    $badDoc = Get-Content -LiteralPath $reproBadJson -Raw | ConvertFrom-Json -AsHashtable -Depth 50
    Assert-Equal 'Repro uses symbolic ARM languageVersion 2.0' $badDoc.languageVersion '2.0'
    Assert-True 'Unfixed map() emits 1-arg reference(nsg) inside lambda()' `
        ($badDoc.outputs.projected.value -cmatch "lambda\('s',.*reference\('nsg'\)\.outputs\.id\.value")

    & az bicep build --file $reproGoodFile --outfile $reproGoodJson --only-show-errors
    Assert-Equal 'Fixed deterministic resourceId counterpart compiles cleanly' $LASTEXITCODE 0
    $goodDoc = Get-Content -LiteralPath $reproGoodJson -Raw | ConvertFrom-Json -AsHashtable -Depth 50
    Assert-Equal 'Fixed map() contains zero reference() calls' ([string]$goodDoc.variables.subnets).Contains('reference(') $false
    Assert-True 'Fixed consumer preserves explicit symbolic dependsOn on conditional module' ($goodDoc.resources.consumer.dependsOn -contains 'nsg')

    # 2. Compile infra/bicep/main.bicep and assert zero reference( calls in subnet expressions.
    & az bicep build --file $MainFile --outfile $compiledFile --only-show-errors
    Assert-Equal 'Foundation Bicep compiles cleanly' $LASTEXITCODE 0
    $rawJson = Get-Content -LiteralPath $compiledFile -Raw
    $t = $rawJson | ConvertFrom-Json -AsHashtable -Depth 100

    foreach ($varName in @('subnets', '_effectiveRouteTableId', '_effectiveNatGatewayId')) {
        Assert-True "Compiled variables contains $varName" $t.variables.ContainsKey($varName)
        Assert-Equal "Zero reference( calls in variables.$varName" ([string]$t.variables[$varName]).Contains('reference(') $false
    }
    Assert-Equal 'virtualNetwork.subnets binds variables(subnets)' $t.resources.virtualNetwork.properties.parameters.subnets.value "[variables('subnets')]"
    Assert-Equal 'virtualNetworkSubnets.subnets binds variables(subnets)' $t.resources.virtualNetworkSubnets.properties.parameters.subnets.value "[variables('subnets')]"
    Assert-Equal 'Zero reference( calls in virtualNetwork.subnets parameter' ([string]$t.resources.virtualNetwork.properties.parameters.subnets.value).Contains('reference(') $false
    Assert-Equal 'Zero reference( calls in virtualNetworkSubnets.subnets parameter' ([string]$t.resources.virtualNetworkSubnets.properties.parameters.subnets.value).Contains('reference(') $false
    Assert-Equal 'Zero reference( calls in containerAppsPostgreSqlSubnet.natGatewayId parameter' ([string]$t.resources.containerAppsPostgreSqlSubnet.properties.parameters.natGatewayId.value).Contains('reference(') $false

    # 3. Verify exact module target scopes, types, and names match deterministic resourceId(...) expressions.
    $expectedBastionId = "resourceId(variables('_networkResourceGroupName'), 'Microsoft.Network/networkSecurityGroups', format('nsg-{0}-{1}', variables('resourceNames').vnetName, parameters('azureBastionSubnetName')))"
    $expectedAppGwId = "resourceId(variables('_networkResourceGroupName'), 'Microsoft.Network/networkSecurityGroups', format('nsg-{0}-{1}', variables('resourceNames').vnetName, parameters('azureAppGatewaySubnetName')))"
    $expectedAiGwId = "resourceId(if(parameters('useExistingVNet'), variables('varExistingVnetSubscriptionId'), subscription().subscriptionId), if(parameters('useExistingVNet'), variables('varExistingVnetResourceGroupName'), variables('_networkResourceGroupName')), 'Microsoft.Network/networkSecurityGroups', format('nsg-{0}-{1}', if(parameters('useExistingVNet'), variables('varExistingVnetName'), variables('resourceNames').vnetName), parameters('aiGatewaySubnetName')))"
    $expectedRouteTableId = "resourceId(variables('_networkResourceGroupName'), 'Microsoft.Network/routeTables', format('{0}{1}', variables('_1.abbrs').networking.routeTable, parameters('resourceToken')))"
    $expectedNatGatewayId = "resourceId(variables('_networkResourceGroupName'), 'Microsoft.Network/natGateways', format('{0}{1}', variables('_1.abbrs').networking.natGateway, parameters('resourceToken')))"
    $expectedPgNatId = "resourceId(variables('_networkResourceGroupName'), 'Microsoft.Network/natGateways', format('{0}aca-postgresql-{1}', variables('_1.abbrs').networking.natGateway, parameters('resourceToken')))"

    Assert-Equal 'bastionNsg module scope and name match deterministic resourceId' `
        @($t.resources.bastionNsg.subscriptionId, $t.resources.bastionNsg.resourceGroup, $t.resources.bastionNsg.properties.parameters.name.value, $t.resources.bastionNsg.properties.template.resources[0].type) `
        @($null, "[variables('_networkResourceGroupName')]", "[format('nsg-{0}-{1}', variables('resourceNames').vnetName, parameters('azureBastionSubnetName'))]", 'Microsoft.Network/networkSecurityGroups')
    Assert-Equal 'appGwNsg module scope and name match deterministic resourceId' `
        @($t.resources.appGwNsg.subscriptionId, $t.resources.appGwNsg.resourceGroup, $t.resources.appGwNsg.properties.parameters.name.value, $t.resources.appGwNsg.properties.template.resources[0].type) `
        @($null, "[variables('_networkResourceGroupName')]", "[format('nsg-{0}-{1}', variables('resourceNames').vnetName, parameters('azureAppGatewaySubnetName'))]", 'Microsoft.Network/networkSecurityGroups')
    Assert-Equal 'aiGatewayNsg module cross-sub/RG scope and name match deterministic resourceId' `
        @($t.resources.aiGatewayNsg.subscriptionId, $t.resources.aiGatewayNsg.resourceGroup, $t.resources.aiGatewayNsg.properties.parameters.name.value, $t.resources.aiGatewayNsg.properties.template.resources[0].type) `
        @(
            "[if(parameters('useExistingVNet'), variables('varExistingVnetSubscriptionId'), subscription().subscriptionId)]",
            "[if(parameters('useExistingVNet'), variables('varExistingVnetResourceGroupName'), variables('_networkResourceGroupName'))]",
            "[format('nsg-{0}-{1}', if(parameters('useExistingVNet'), variables('varExistingVnetName'), variables('resourceNames').vnetName), parameters('aiGatewaySubnetName'))]",
            'Microsoft.Network/networkSecurityGroups'
        )
    Assert-Equal 'routeTable module scope and name match deterministic resourceId' `
        @($t.resources.routeTable.subscriptionId, $t.resources.routeTable.resourceGroup, $t.resources.routeTable.properties.parameters.name.value, $t.resources.routeTable.properties.template.resources[0].type) `
        @($null, "[variables('_networkResourceGroupName')]", "[format('{0}{1}', variables('_1.abbrs').networking.routeTable, parameters('resourceToken'))]", 'Microsoft.Network/routeTables')
    $natTypes = @($t.resources.natGateway.properties.template.resources | ForEach-Object { $_.type })
    Assert-True 'natGateway module deploys Microsoft.Network/natGateways' ($natTypes -contains 'Microsoft.Network/natGateways')
    Assert-Equal 'natGateway module scope and name match deterministic resourceId' `
        @($t.resources.natGateway.subscriptionId, $t.resources.natGateway.resourceGroup, $t.resources.natGateway.properties.parameters.name.value) `
        @($null, "[variables('_networkResourceGroupName')]", "[format('{0}{1}', variables('_1.abbrs').networking.natGateway, parameters('resourceToken'))]")
    Assert-Equal 'containerAppsPostgreSqlNat module scope and name match deterministic resourceId' `
        @($t.resources.containerAppsPostgreSqlNat.subscriptionId, $t.resources.containerAppsPostgreSqlNat.resourceGroup, $t.resources.containerAppsPostgreSqlNat.properties.parameters.name.value) `
        @($null, "[variables('_networkResourceGroupName')]", "[format('{0}aca-postgresql-{1}', variables('_1.abbrs').networking.natGateway, parameters('resourceToken'))]")

    Assert-Equal 'Exact _effectiveRouteTableId expression preserves BYO passthrough and deterministic ID' `
        $t.variables._effectiveRouteTableId `
        "[if(variables('_hasExistingRouteTable'), parameters('hubIntegrationExistingRouteTableResourceId'), if(variables('_createRouteTable'), $expectedRouteTableId, ''))]"
    Assert-Equal 'Exact _effectiveNatGatewayId expression preserves BYO passthrough and deterministic ID' `
        $t.variables._effectiveNatGatewayId `
        "[if(variables('_deployNatGateway'), $expectedNatGatewayId, if(variables('_hasExistingNatGateway'), parameters('existingNatGatewayResourceId'), ''))]"
    Assert-Equal 'Exact subnets map expression uses deterministic resourceId() for all NSGs, route table, and NAT gateways' `
        $t.variables.subnets `
        "[map(variables('selectedSubnetDefinitions'), lambda('subnet', createObject('name', lambdaVariables('subnet').name, 'addressPrefix', lambdaVariables('subnet').addressPrefix, 'delegation', lambdaVariables('subnet').delegation, 'serviceEndpoints', lambdaVariables('subnet').serviceEndpoints, 'networkSecurityGroupResourceId', if(and(and(equals(lambdaVariables('subnet').purpose, 'bastion'), variables('_deployBastion')), parameters('deployNsgs')), $expectedBastionId, if(and(equals(lambdaVariables('subnet').purpose, 'appGateway'), variables('_publicIngressEnabled')), $expectedAppGwId, if(and(equals(lambdaVariables('subnet').purpose, 'aiGateway'), parameters('deployNsgs')), $expectedAiGwId, ''))), 'routeTableResourceId', if(contains(createArray('agent', 'pe', 'jumpbox', 'acaEnvironment', 'devopsBuildAgents', 'applicationPe'), lambdaVariables('subnet').purpose), variables('_effectiveRouteTableId'), ''), 'natGatewayResourceId', if(equals(lambdaVariables('subnet').purpose, 'jumpbox'), variables('_effectiveNatGatewayId'), if(and(equals(lambdaVariables('subnet').purpose, 'acaEnvironment'), variables('_postgreSqlBasic')), $expectedPgNatId, '')))))]"
    Assert-Equal 'containerAppsPostgreSqlSubnet uses identical deterministic PostgreSQL NAT resourceId' `
        $t.resources.containerAppsPostgreSqlSubnet.properties.parameters.natGatewayId.value `
        "[$expectedPgNatId]"

    # 4. Verify explicit conditional network module dependsOn on both VNet and BYO subnet paths.
    $conditionalNetworkModules = @('bastionNsg', 'appGwNsg', 'aiGatewayNsg', 'routeTable', 'natGateway', 'containerAppsPostgreSqlNat')
    foreach ($moduleName in $conditionalNetworkModules) {
        Assert-True "virtualNetwork.dependsOn contains $moduleName" ($t.resources.virtualNetwork.dependsOn -contains $moduleName)
        Assert-True "virtualNetworkSubnets.dependsOn contains $moduleName" ($t.resources.virtualNetworkSubnets.dependsOn -contains $moduleName)
    }
    Assert-Equal 'virtualNetwork.dependsOn exact set' `
        @($t.resources.virtualNetwork.dependsOn | Sort-Object -CaseSensitive) `
        @('aiGatewayNsg', 'appGwNsg', 'bastionNsg', 'containerAppsPostgreSqlNat', 'natGateway', 'networkLayoutValidation', 'postgreSqlValidation', 'routeTable')
    Assert-Equal 'virtualNetworkSubnets.dependsOn exact set' `
        @($t.resources.virtualNetworkSubnets.dependsOn | Sort-Object -CaseSensitive) `
        @('aiGatewayNsg', 'appGwNsg', 'bastionNsg', 'componentFlagValidation', 'containerAppsPostgreSqlNat', 'natGateway', 'networkLayoutValidation', 'postgreSqlValidation', 'routeTable', 'virtualNetwork')
    Assert-Equal 'containerAppsPostgreSqlSubnet.dependsOn exact set' `
        @($t.resources.containerAppsPostgreSqlSubnet.dependsOn | Sort-Object -CaseSensitive) `
        @('containerAppsPostgreSqlNat', 'networkLayoutValidation', 'postgreSqlValidation')

    # 5. Bounded scenario verification: single-RG, split _networkResourceGroupName,
    # cross-subscription/RG useExistingVNet, and BYO route table / NAT gateway passthrough.
    $abbrsFile = Join-Path (Split-Path -Parent (Split-Path -Parent $MainFile)) 'shared/abbreviations.json'
    $abbrs = Get-Content -LiteralPath $abbrsFile -Raw | ConvertFrom-Json -AsHashtable
    $rtAbbr = $abbrs.networking.routeTable
    $ngAbbr = $abbrs.networking.natGateway

    # 5a. Default single-RG new VNet
    $singleRg = Resolve-SubnetAttachments -RouteTableAbbr $rtAbbr -NatGatewayAbbr $ngAbbr
    Assert-Equal 'Single-RG bastion NSG ID' $singleRg.bastion.networkSecurityGroupResourceId '/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-foundry/providers/Microsoft.Network/networkSecurityGroups/nsg-vnet-spoke-AzureBastionSubnet'
    Assert-Equal 'Single-RG appGateway NSG ID' $singleRg.appGateway.networkSecurityGroupResourceId '/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-foundry/providers/Microsoft.Network/networkSecurityGroups/nsg-vnet-spoke-AppGatewaySubnet'
    Assert-Equal 'Single-RG aiGateway NSG ID' $singleRg.aiGateway.networkSecurityGroupResourceId '/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-foundry/providers/Microsoft.Network/networkSecurityGroups/nsg-vnet-spoke-ai-gateway-subnet'
    foreach ($routed in @('agent', 'pe', 'jumpbox', 'acaEnvironment', 'devopsBuildAgents', 'applicationPe')) {
        Assert-Equal "Single-RG $routed route table ID" $singleRg[$routed].routeTableResourceId "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-foundry/providers/Microsoft.Network/routeTables/${rtAbbr}abc123token"
    }
    foreach ($unrouted in @('gateway', 'bastion', 'firewall', 'appGateway', 'powerPlatform', 'aiGateway', 'firewallManagement')) {
        Assert-Equal "Single-RG $unrouted has no forced-tunnel route table" $singleRg[$unrouted].routeTableResourceId ''
    }
    Assert-Equal 'Single-RG jumpbox NAT gateway ID' $singleRg.jumpbox.natGatewayResourceId "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-foundry/providers/Microsoft.Network/natGateways/${ngAbbr}abc123token"
    Assert-Equal 'Isolated ACA subnet has no Basic PG NAT gateway' $singleRg.acaEnvironment.natGatewayResourceId ''

    # 5b. Split _networkResourceGroupName + Basic PostgreSQL NAT
    $splitRg = Resolve-SubnetAttachments -NetworkResourceGroupName 'rg-network-spoke' -RouteTableAbbr $rtAbbr -NatGatewayAbbr $ngAbbr
    Assert-Equal 'Split-RG bastion NSG scopes to network RG' $splitRg.bastion.networkSecurityGroupResourceId '/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-network-spoke/providers/Microsoft.Network/networkSecurityGroups/nsg-vnet-spoke-AzureBastionSubnet'
    Assert-Equal 'Split-RG appGateway NSG scopes to network RG' $splitRg.appGateway.networkSecurityGroupResourceId '/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-network-spoke/providers/Microsoft.Network/networkSecurityGroups/nsg-vnet-spoke-AppGatewaySubnet'
    Assert-Equal 'Split-RG new-VNet aiGateway NSG scopes to network RG' $splitRg.aiGateway.networkSecurityGroupResourceId '/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-network-spoke/providers/Microsoft.Network/networkSecurityGroups/nsg-vnet-spoke-ai-gateway-subnet'
    Assert-Equal 'Split-RG route table scopes to network RG' $splitRg.agent.routeTableResourceId "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-network-spoke/providers/Microsoft.Network/routeTables/${rtAbbr}abc123token"
    Assert-Equal 'Split-RG jumpbox NAT scopes to network RG' $splitRg.jumpbox.natGatewayResourceId "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-network-spoke/providers/Microsoft.Network/natGateways/${ngAbbr}abc123token"

    $basicPg = Resolve-SubnetAttachments -NetworkIsolation $false -NetworkResourceGroupName 'rg-network-spoke' -PostgreSqlBasic $true -DeployBastion $false -PublicIngressEnabled $false -DeployNatGateway $false -RouteTableAbbr $rtAbbr -NatGatewayAbbr $ngAbbr
    Assert-Equal 'Basic PostgreSQL ACA subnet NAT scopes to network RG' $basicPg.acaEnvironment.natGatewayResourceId "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-network-spoke/providers/Microsoft.Network/natGateways/${ngAbbr}aca-postgresql-abc123token"
    Assert-Equal 'Basic mode leaves route table empty' $basicPg.acaEnvironment.routeTableResourceId ''

    # 5c. Cross-subscription / cross-RG useExistingVNet=true
    $byoVnetId = '/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-byo-vnet/providers/Microsoft.Network/virtualNetworks/vnet-corp'
    $crossSubByo = Resolve-SubnetAttachments -NetworkResourceGroupName 'rg-spoke-net' -UseExistingVNet $true -ExistingVnetResourceId $byoVnetId -RouteTableAbbr $rtAbbr -NatGatewayAbbr $ngAbbr
    Assert-Equal 'Cross-sub BYO aiGateway NSG targets BYO subscription, BYO RG, and BYO VNet name' `
        $crossSubByo.aiGateway.networkSecurityGroupResourceId `
        '/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-byo-vnet/providers/Microsoft.Network/networkSecurityGroups/nsg-vnet-corp-ai-gateway-subnet'
    Assert-Equal 'Cross-sub BYO bastion NSG stays in spoke network RG' `
        $crossSubByo.bastion.networkSecurityGroupResourceId `
        '/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-spoke-net/providers/Microsoft.Network/networkSecurityGroups/nsg-vnet-spoke-AzureBastionSubnet'
    Assert-Equal 'Cross-sub BYO appGateway NSG stays in spoke network RG' `
        $crossSubByo.appGateway.networkSecurityGroupResourceId `
        '/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-spoke-net/providers/Microsoft.Network/networkSecurityGroups/nsg-vnet-spoke-AppGatewaySubnet'

    # 5d. BYO Route Table & BYO NAT Gateway passthrough (including cross-subscription IDs)
    $byoRtId = '/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-hub-shared/providers/Microsoft.Network/routeTables/rt-platform-spoke'
    $byoNatId = '/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-hub-shared/providers/Microsoft.Network/natGateways/ng-platform-spoke'
    $byoAttachments = Resolve-SubnetAttachments -DeployNatGateway $false -ExistingRouteTableResourceId $byoRtId -ExistingNatGatewayResourceId $byoNatId -DeployBastion $false -PublicIngressEnabled $false -DeployNsgs $false -RouteTableAbbr $rtAbbr -NatGatewayAbbr $ngAbbr
    foreach ($routed in @('agent', 'pe', 'jumpbox', 'acaEnvironment', 'devopsBuildAgents', 'applicationPe')) {
        Assert-Equal "BYO route table preserved verbatim on $routed" $byoAttachments[$routed].routeTableResourceId $byoRtId
    }
    Assert-Equal 'BYO NAT gateway preserved verbatim on jumpbox' $byoAttachments.jumpbox.natGatewayResourceId $byoNatId
    Assert-Equal 'Disabled NSGs emit empty NSG IDs' @($byoAttachments.bastion.networkSecurityGroupResourceId, $byoAttachments.appGateway.networkSecurityGroupResourceId, $byoAttachments.aiGateway.networkSecurityGroupResourceId) @('', '', '')

    # 6. Negative mutation checks on the bounded inverse projection.
    foreach ($moduleName in $conditionalNetworkModules) {
        $mutatedVnet = $rawJson | ConvertFrom-Json -AsHashtable -Depth 100
        $mutatedVnet.resources.virtualNetwork.dependsOn = @($mutatedVnet.resources.virtualNetwork.dependsOn | Where-Object { $_ -cne $moduleName })
        Assert-Rejected "Reject missing $moduleName in virtualNetwork.dependsOn" { ConvertTo-PreSubnetConditionalReferencesGraph $mutatedVnet }

        $mutatedByo = $rawJson | ConvertFrom-Json -AsHashtable -Depth 100
        $mutatedByo.resources.virtualNetworkSubnets.dependsOn = @($mutatedByo.resources.virtualNetworkSubnets.dependsOn | Where-Object { $_ -cne $moduleName })
        Assert-Rejected "Reject missing $moduleName in virtualNetworkSubnets.dependsOn" { ConvertTo-PreSubnetConditionalReferencesGraph $mutatedByo }
    }

    $negativeCases = @(
        @{ Name = 'reintroduced reference(bastionNsg) in subnets'; Change = { param($m) $m.variables.subnets = $m.variables.subnets.Replace($expectedBastionId, "reference('bastionNsg').outputs.id.value") } }
        @{ Name = 'dropped cross-sub scope on aiGatewayNsg'; Change = { param($m) $m.variables.subnets = $m.variables.subnets.Replace("if(parameters('useExistingVNet'), variables('varExistingVnetSubscriptionId'), subscription().subscriptionId), ", '') } }
        @{ Name = 'dropped BYO route table passthrough'; Change = { param($m) $m.variables._effectiveRouteTableId = "[$expectedRouteTableId]" } }
        @{ Name = 'dropped BYO NAT gateway passthrough'; Change = { param($m) $m.variables._effectiveNatGatewayId = "[$expectedNatGatewayId]" } }
        @{ Name = 'containerAppsPostgreSqlSubnet reverted to reference()'; Change = { param($m) $m.resources.containerAppsPostgreSqlSubnet.properties.parameters.natGatewayId.value = "[reference('containerAppsPostgreSqlNat').outputs.resourceId.value]" } }
        @{ Name = 'containerAppsPostgreSqlSubnet lost NAT dependsOn'; Change = { param($m) $m.resources.containerAppsPostgreSqlSubnet.dependsOn = @('networkLayoutValidation', 'postgreSqlValidation') } }
    )
    foreach ($case in $negativeCases) {
        $mutated = $rawJson | ConvertFrom-Json -AsHashtable -Depth 100
        & $case.Change $mutated
        Assert-Rejected "Reject $($case.Name)" { ConvertTo-PreSubnetConditionalReferencesGraph $mutated }
    }

    Write-Host "Subnet conditional references contract passed: $script:checks assertions; Bicep $($t.metadata._generator.version)." -ForegroundColor Green
}
finally {
    if (Test-Path $scratchDir) { Remove-Item -LiteralPath $scratchDir -Recurse -Force -ErrorAction SilentlyContinue }
}
