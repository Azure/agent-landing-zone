# ADR-0031's exact, bounded projection onto the unchanged v5.5.2 graph.
# Before-values below were compared with HEAD 5a302bc (Bicep 0.42.1).
# Reuse the reviewed ADR-0027 before-values rather than duplicating snapshots.
# No rule collections, routing consumers, outputs or fingerprints are replaced.
function Get-FirewallBasicProjection {
    $architecture = Get-ArchitectureSubnetProjection
    $projection = @{ kind = 'object'; changes = @{} }
    function Add-FirewallRule([string]$Path, $Rule) {
        $parts = $Path.Split('/')
        $node = $projection
        for ($i = 0; $i -lt $parts.Count - 1; $i++) {
            $key = $parts[$i]
            if (-not $node.changes.Contains($key)) {
                $node.changes[$key] = if ($parts[$i + 1] -match '^\d+$') {
                    @{ kind = 'array'; count = 3; changes = @{} } # Existing BYO wrapper's three deployments.
                } else { @{ kind = 'object'; changes = @{} } }
            }
            $node = $node.changes[$key]
        }
        $node.changes[$parts[-1]] = $Rule
    }
    function Add-FirewallAdded([string]$Path, $After) {
        Add-FirewallRule $Path @{ kind = 'added'; after = $After }
    }
    function Add-FirewallChanged([string]$Path, $Before, $After) {
        Add-FirewallRule $Path @{ kind = 'changed'; before = $Before; after = $After }
    }
    function Copy-FirewallValue($Value) {
        ConvertTo-Json -InputObject $Value -Depth 100 | ConvertFrom-Json -AsHashtable -Depth 100 -NoEnumerate
    }

    $sku = @{ type = 'string'; defaultValue = 'Basic'; allowedValues = @('Basic', 'Standard') }
    $managementName = @{ type = 'string'; defaultValue = 'AzureFirewallManagementSubnet'; allowedValues = @('AzureFirewallManagementSubnet') }
    $mode = @{ type = 'string'; defaultValue = 'standalone'; allowedValues = @('standalone', 'ailz-integrated') }
    $mainSku = Copy-FirewallValue $sku
    $mainSku.metadata = @{ description = 'SKU for the deployment-owned firewall and policy. Basic requires standalone management networking and does not support DNS proxy.' }
    Add-FirewallAdded 'parameters/azureFirewallSku' $mainSku
    Add-FirewallAdded 'parameters/azureFirewallManagementSubnetName' $managementName
    Add-FirewallAdded 'parameters/azureFirewallManagementSubnetPrefix' @{
        type = 'string'; defaultValue = '192.168.3.192/26'
        metadata = @{ description = 'Basic firewall management subnet — aligned IPv4 /26 or larger, without workload NSG, UDR, NAT, delegation or service endpoints.' }
    }
    Add-FirewallAdded 'parameters/deployAzureFirewallManagementSubnet' @{
        type = 'bool'; nullable = $true
        metadata = @{ description = 'Create/manage the management subnet only for active standalone isolated Basic. Null creates it; false requires a verified BYO subnet.' }
    }
    Add-FirewallChanged 'parameters/deployAzureFirewallSubnet' $architecture.changes.parameters.changes.deployAzureFirewallSubnet.after @{
        type = 'bool'; nullable = $true
        metadata = @{ description = 'Create/manage AzureFirewallSubnet. Null follows the local isolated firewall requirement; true can reserve it without a firewall; false requires BYO when needed.' }
    }
    Add-FirewallChanged 'parameters/deployGatewaySubnet/defaultValue' $true $false
    Add-FirewallAdded 'variables/_localFirewall' "[and(variables('_networkIsolation'), parameters('deployAzureFirewall'))]"
    Add-FirewallAdded 'variables/_basicFirewallManagement' "[and(and(variables('_localFirewall'), equals(parameters('deploymentMode'), 'standalone')), equals(variables('_validatedAzureFirewallSku'), 'Basic'))]"
    Add-FirewallAdded 'variables/_validatedAzureFirewallSku' "[if(and(equals(parameters('azureFirewallSku'), 'Basic'), parameters('enableFirewallDnsProxy')), fail('Azure Firewall Basic does not support DNS proxy. Select Standard explicitly or disable enableFirewallDnsProxy.'), if(and(and(variables('_localFirewall'), not(equals(parameters('deploymentMode'), 'standalone'))), equals(parameters('azureFirewallSku'), 'Basic')), fail('Local Azure Firewall Basic is supported only in standalone mode. Use external hub egress with deployAzureFirewall=false or explicitly select Standard.'), if(and(variables('_networkIsolation'), or(and(variables('_hasExternalEgress'), variables('_hasExistingRouteTable')), and(parameters('deployAzureFirewall'), or(variables('_hasExternalEgress'), variables('_hasExistingRouteTable'))))), fail('Select exactly one egress owner: local firewall, external next-hop IP, or existing route table. Local firewall and external routing are mutually exclusive.'), if(and(and(and(variables('_networkIsolation'), not(parameters('deployAzureFirewall'))), not(variables('_hasExternalEgress'))), not(variables('_hasExistingRouteTable'))), fail('Network isolation with deployAzureFirewall=false requires an explicit external next-hop IP or existing route table. A hub VNet or deployment mode alone does not configure egress.'), parameters('azureFirewallSku')))))]"
    $definitionsBefore = $architecture.changes.variables.changes.subnetDefinitions.after
    $definitionsAfter = Copy-FirewallValue $definitionsBefore
    $definitionsAfter[4].create = "[coalesce(parameters('deployAzureFirewallSubnet'), variables('_localFirewall'))]"
    $definitionsAfter[4].required = "[variables('_localFirewall')]"
    $definitionsAfter += @{
        purpose = 'firewallManagement'
        create = "[and(variables('_basicFirewallManagement'), coalesce(parameters('deployAzureFirewallManagementSubnet'), true()))]"
        required = "[variables('_basicFirewallManagement')]"
        name = "[parameters('azureFirewallManagementSubnetName')]"
        addressPrefix = "[parameters('azureFirewallManagementSubnetPrefix')]"
        delegation = ''; serviceEndpoints = @()
    }
    Add-FirewallChanged 'variables/subnetDefinitions' $definitionsBefore $definitionsAfter

    Add-FirewallAdded 'resources/firewall/properties/parameters/azureFirewallSku' @{ value = "[variables('_validatedAzureFirewallSku')]" }
    Add-FirewallAdded 'resources/firewall/properties/parameters/azureFirewallManagementSubnetName' @{ value = "[parameters('azureFirewallManagementSubnetName')]" }
    Add-FirewallAdded 'resources/firewall/properties/parameters/deploymentMode' @{ value = "[parameters('deploymentMode')]" }
    Add-FirewallChanged 'resources/firewall/dependsOn' @('logAnalytics', 'virtualNetwork', 'virtualNetworkSubnets') @('logAnalytics', 'networkLayoutValidation', 'virtualNetwork', 'virtualNetworkSubnets')
    $f = 'resources/firewall/properties/template'
    Add-FirewallAdded "$f/parameters/azureFirewallSku" $sku
    Add-FirewallAdded "$f/parameters/azureFirewallManagementSubnetName" $managementName
    Add-FirewallAdded "$f/parameters/deploymentMode" $mode
    Add-FirewallAdded "$f/variables/_validatedSku" "[if(and(equals(parameters('azureFirewallSku'), 'Basic'), parameters('enableFirewallDnsProxy')), fail('Azure Firewall Basic does not support DNS proxy. Select Standard explicitly or disable enableFirewallDnsProxy.'), if(and(and(and(parameters('deployAzureFirewall'), parameters('networkIsolation')), not(equals(parameters('deploymentMode'), 'standalone'))), equals(parameters('azureFirewallSku'), 'Basic')), fail('Local Azure Firewall Basic is supported only in standalone mode.'), parameters('azureFirewallSku')))]"
    Add-FirewallAdded "$f/variables/_basicManagement" "[and(and(and(parameters('deployAzureFirewall'), parameters('networkIsolation')), equals(parameters('deploymentMode'), 'standalone')), equals(variables('_validatedSku'), 'Basic'))]"
    Add-FirewallAdded "$f/resources/firewallManagementPublicIp" @{
        condition = "[variables('_basicManagement')]"
        type = 'Microsoft.Network/publicIPAddresses'; apiVersion = '2024-07-01'
        name = "[format('{0}{1}{2}-management', variables('_1.abbrs').networking.publicIPAddress, variables('_1.abbrs').networking.firewall, parameters('resourceToken'))]"
        location = "[parameters('location')]"; tags = "[parameters('tags')]"
        sku = @{ name = 'Standard'; tier = 'Regional' }
        properties = @{ publicIPAllocationMethod = 'Static'; publicIPAddressVersion = 'IPv4' }
    }
    Add-FirewallChanged "$f/resources/firewallPolicy/properties" ([ordered]@{
        sku = [ordered]@{ tier = 'Standard' }; threatIntelMode = 'Alert'
        dnsSettings = [ordered]@{ enableProxy = "[parameters('enableFirewallDnsProxy')]" }
    }) "[shallowMerge(createArray(createObject('sku', createObject('tier', variables('_validatedSku')), 'threatIntelMode', 'Alert'), if(equals(variables('_validatedSku'), 'Standard'), createObject('dnsSettings', createObject('enableProxy', parameters('enableFirewallDnsProxy'))), createObject())))]"
    Add-FirewallChanged "$f/resources/azureFirewall/properties" ([ordered]@{
        sku = [ordered]@{ name = 'AZFW_VNet'; tier = 'Standard' }
        ipConfigurations = @([ordered]@{
            name = 'ipconfig1'
            properties = [ordered]@{
                publicIPAddress = [ordered]@{ id = "[resourceId('Microsoft.Network/publicIPAddresses', format('{0}{1}{2}', variables('_1.abbrs').networking.publicIPAddress, variables('_1.abbrs').networking.firewall, parameters('resourceToken')))]" }
                subnet = [ordered]@{ id = "[variables('_firewallSubnetId')]" }
            }
        })
        firewallPolicy = [ordered]@{ id = "[resourceId('Microsoft.Network/firewallPolicies', format('{0}{1}', variables('_1.abbrs').networking.firewallPolicy, parameters('resourceToken')))]" }
    }) "[shallowMerge(createArray(createObject('sku', createObject('name', 'AZFW_VNet', 'tier', variables('_validatedSku')), 'ipConfigurations', createArray(createObject('name', 'ipconfig1', 'properties', createObject('publicIPAddress', createObject('id', resourceId('Microsoft.Network/publicIPAddresses', format('{0}{1}{2}', variables('_1.abbrs').networking.publicIPAddress, variables('_1.abbrs').networking.firewall, parameters('resourceToken')))), 'subnet', createObject('id', variables('_firewallSubnetId')))))), if(variables('_basicManagement'), createObject('managementIpConfiguration', createObject('name', 'managementIpconfig', 'properties', createObject('publicIPAddress', createObject('id', resourceId('Microsoft.Network/publicIPAddresses', format('{0}{1}{2}-management', variables('_1.abbrs').networking.publicIPAddress, variables('_1.abbrs').networking.firewall, parameters('resourceToken')))), 'subnet', createObject('id', format('{0}/subnets/{1}', parameters('virtualNetworkResourceId'), parameters('azureFirewallManagementSubnetName')))))), createObject()), createObject('firewallPolicy', createObject('id', resourceId('Microsoft.Network/firewallPolicies', format('{0}{1}', variables('_1.abbrs').networking.firewallPolicy, parameters('resourceToken')))))))]"
    Add-FirewallChanged "$f/resources/azureFirewall/dependsOn" @('firewallPolicy', 'firewallPublicIp') @('firewallManagementPublicIp', 'firewallPolicy', 'firewallPublicIp')

    # Build the exact validation delta atop the already reviewed, complete
    # resource-free validator. All original predicates/functions stay protected.
    $validationBefore = $architecture.changes.resources.changes.networkLayoutValidation.after
    $validationAfter = Copy-FirewallValue $validationBefore
    $v = $validationAfter.properties.template
    $v.variables.reservedNames.firewallManagement = 'AzureFirewallManagementSubnet'
    $v.variables.reservedNamesValid = $v.variables.reservedNamesValid.Replace("'azurefirewallsubnet'", "'azurefirewallsubnet', 'azurefirewallmanagementsubnet', 'routeserversubnet'")
    $v.variables.firewallPrefixesValid = "[if(variables('prefixesValid'), empty(filter(variables('relevant'), lambda('subnet', and(contains(createArray('firewall', 'firewallManagement'), lambdaVariables('subnet').purpose), or(not(__bicep.alignedIpv4(lambdaVariables('subnet').addressPrefix)), greater(int(split(lambdaVariables('subnet').addressPrefix, '/')[1]), 26)))))), false())]"
    $v.outputs.validated.value = $v.outputs.validated.value.Replace(
        'GatewaySubnet, AzureBastionSubnet and AzureFirewallSubnet',
        'GatewaySubnet, AzureBastionSubnet, AzureFirewallSubnet and AzureFirewallManagementSubnet'
    ).Replace("if(not(variables('aiGatewayValid'))", "if(not(variables('firewallPrefixesValid')), fail('Firewall data and management subnets require aligned IPv4 CIDRs of /26 or larger.'), if(not(variables('aiGatewayValid'))")
    $v.outputs.validated.value = $v.outputs.validated.value.TrimEnd(']') + ')]'
    Add-FirewallChanged 'resources/networkLayoutValidation' $validationBefore $validationAfter

    $s = 'resources/virtualNetworkSubnets/properties/template'
    Add-FirewallAdded "$s/variables/managementAttachmentsAreSafe" "[empty(filter(parameters('subnets'), lambda('subnet', and(equals(lambdaVariables('subnet').name, 'AzureFirewallManagementSubnet'), or(or(or(or(not(empty(coalesce(tryGet(lambdaVariables('subnet'), 'networkSecurityGroupResourceId'), ''))), not(empty(coalesce(tryGet(lambdaVariables('subnet'), 'routeTableResourceId'), '')))), not(empty(coalesce(tryGet(lambdaVariables('subnet'), 'natGatewayResourceId'), '')))), not(empty(coalesce(tryGet(lambdaVariables('subnet'), 'delegation'), '')))), not(empty(coalesce(tryGet(lambdaVariables('subnet'), 'serviceEndpoints'), createArray()))))))))]"
    Add-FirewallAdded "$s/variables/validatedSubnets" "[if(variables('managementAttachmentsAreSafe'), parameters('subnets'), fail('AzureFirewallManagementSubnet must not have an NSG, route table, NAT gateway, delegation or service endpoints.'))]"
    $exclusions = @('AzureFirewallSubnet', 'AppGatewaySubnet', 'AzureBastionSubnet', 'GatewaySubnet')
    Add-FirewallChanged "$s/variables/invalidNsgSubnets" $exclusions ($exclusions + 'AzureFirewallManagementSubnet')
    Add-FirewallChanged "$s/resources/0/properties/parameters/subnets/value" "[parameters('subnets')]" "[variables('validatedSubnets')]"
    Add-FirewallChanged "$s/resources/2/properties/parameters/addressPrefix" @{ value = "[parameters('subnets')[range(0, length(parameters('subnets')))[copyIndex()]].addressPrefix]" } "[if(variables('managementAttachmentsAreSafe'), createObject('value', parameters('subnets')[range(0, length(parameters('subnets')))[copyIndex()]].addressPrefix), createObject('value', fail('AzureFirewallManagementSubnet must not have an NSG, route table, NAT gateway, delegation or service endpoints.')))]"
    return $projection
}
