# Issue #882 Task 1: exact bounded inverse of the deterministic subnet resourceId()
# and explicit conditional network module dependsOn migration, compiled with Bicep 0.42.1.
# Historical fixtures and downstream normalization digests remain untouched.
function Get-SubnetConditionalReferencesProjection {
    $historicalSubnets = "[map(variables('selectedSubnetDefinitions'), lambda('subnet', createObject('name', lambdaVariables('subnet').name, 'addressPrefix', lambdaVariables('subnet').addressPrefix, 'delegation', lambdaVariables('subnet').delegation, 'serviceEndpoints', lambdaVariables('subnet').serviceEndpoints, 'networkSecurityGroupResourceId', if(and(and(equals(lambdaVariables('subnet').purpose, 'bastion'), variables('_deployBastion')), parameters('deployNsgs')), reference('bastionNsg').outputs.id.value, if(and(equals(lambdaVariables('subnet').purpose, 'appGateway'), variables('_publicIngressEnabled')), reference('appGwNsg').outputs.id.value, if(and(equals(lambdaVariables('subnet').purpose, 'aiGateway'), parameters('deployNsgs')), reference('aiGatewayNsg').outputs.id.value, ''))), 'routeTableResourceId', if(contains(createArray('agent', 'pe', 'jumpbox', 'acaEnvironment', 'devopsBuildAgents', 'applicationPe'), lambdaVariables('subnet').purpose), if(variables('_hasExistingRouteTable'), parameters('hubIntegrationExistingRouteTableResourceId'), if(variables('_createRouteTable'), reference('routeTable').outputs.resourceId.value, '')), ''), 'natGatewayResourceId', if(equals(lambdaVariables('subnet').purpose, 'jumpbox'), if(variables('_deployNatGateway'), reference('natGateway').outputs.resourceId.value, if(variables('_hasExistingNatGateway'), parameters('existingNatGatewayResourceId'), '')), if(and(equals(lambdaVariables('subnet').purpose, 'acaEnvironment'), variables('_postgreSqlBasic')), reference('containerAppsPostgreSqlNat').outputs.resourceId.value, '')))))]"
    $subnetParameterRule = @{
        kind = 'object'
        changes = @{
            subnets = @{
                kind = 'object'
                changes = @{
                    value = @{
                        kind = 'changed'
                        after = "[variables('subnets')]"
                        before = $historicalSubnets
                    }
                }
            }
        }
    }
    $vnetDependencies = @('aiGatewayNsg', 'appGwNsg', 'bastionNsg', 'containerAppsPostgreSqlNat', 'natGateway', 'networkLayoutValidation', 'postgreSqlValidation', 'routeTable')
    $byoDependencies = @('aiGatewayNsg', 'appGwNsg', 'bastionNsg', 'componentFlagValidation', 'containerAppsPostgreSqlNat', 'natGateway', 'networkLayoutValidation', 'postgreSqlValidation', 'routeTable', 'virtualNetwork')
    $pgSubnetDependencies = @('containerAppsPostgreSqlNat', 'networkLayoutValidation', 'postgreSqlValidation')
    return @{
        kind = 'object'
        changes = @{
            variables = @{
                kind = 'object'
                changes = @{
                    _effectiveNatGatewayId = @{
                        kind = 'added'
                        after = "[if(variables('_deployNatGateway'), resourceId(variables('_networkResourceGroupName'), 'Microsoft.Network/natGateways', format('{0}{1}', variables('_1.abbrs').networking.natGateway, parameters('resourceToken'))), if(variables('_hasExistingNatGateway'), parameters('existingNatGatewayResourceId'), ''))]"
                    }
                    _effectiveRouteTableId = @{
                        kind = 'added'
                        after = "[if(variables('_hasExistingRouteTable'), parameters('hubIntegrationExistingRouteTableResourceId'), if(variables('_createRouteTable'), resourceId(variables('_networkResourceGroupName'), 'Microsoft.Network/routeTables', format('{0}{1}', variables('_1.abbrs').networking.routeTable, parameters('resourceToken'))), ''))]"
                    }
                    subnets = @{
                        kind = 'added'
                        after = "[map(variables('selectedSubnetDefinitions'), lambda('subnet', createObject('name', lambdaVariables('subnet').name, 'addressPrefix', lambdaVariables('subnet').addressPrefix, 'delegation', lambdaVariables('subnet').delegation, 'serviceEndpoints', lambdaVariables('subnet').serviceEndpoints, 'networkSecurityGroupResourceId', if(and(and(equals(lambdaVariables('subnet').purpose, 'bastion'), variables('_deployBastion')), parameters('deployNsgs')), resourceId(variables('_networkResourceGroupName'), 'Microsoft.Network/networkSecurityGroups', format('nsg-{0}-{1}', variables('resourceNames').vnetName, parameters('azureBastionSubnetName'))), if(and(equals(lambdaVariables('subnet').purpose, 'appGateway'), variables('_publicIngressEnabled')), resourceId(variables('_networkResourceGroupName'), 'Microsoft.Network/networkSecurityGroups', format('nsg-{0}-{1}', variables('resourceNames').vnetName, parameters('azureAppGatewaySubnetName'))), if(and(equals(lambdaVariables('subnet').purpose, 'aiGateway'), parameters('deployNsgs')), resourceId(if(parameters('useExistingVNet'), variables('varExistingVnetSubscriptionId'), subscription().subscriptionId), if(parameters('useExistingVNet'), variables('varExistingVnetResourceGroupName'), variables('_networkResourceGroupName')), 'Microsoft.Network/networkSecurityGroups', format('nsg-{0}-{1}', if(parameters('useExistingVNet'), variables('varExistingVnetName'), variables('resourceNames').vnetName), parameters('aiGatewaySubnetName'))), ''))), 'routeTableResourceId', if(contains(createArray('agent', 'pe', 'jumpbox', 'acaEnvironment', 'devopsBuildAgents', 'applicationPe'), lambdaVariables('subnet').purpose), variables('_effectiveRouteTableId'), ''), 'natGatewayResourceId', if(equals(lambdaVariables('subnet').purpose, 'jumpbox'), variables('_effectiveNatGatewayId'), if(and(equals(lambdaVariables('subnet').purpose, 'acaEnvironment'), variables('_postgreSqlBasic')), resourceId(variables('_networkResourceGroupName'), 'Microsoft.Network/natGateways', format('{0}aca-postgresql-{1}', variables('_1.abbrs').networking.natGateway, parameters('resourceToken'))), '')))))]"
                    }
                }
            }
            resources = @{
                kind = 'object'
                changes = @{
                    virtualNetwork = @{
                        kind = 'object'
                        changes = @{
                            dependsOn = @{
                                kind = 'changed'
                                after = $vnetDependencies
                                before = $vnetDependencies
                            }
                            properties = @{
                                kind = 'object'
                                changes = @{ parameters = $subnetParameterRule }
                            }
                        }
                    }
                    virtualNetworkSubnets = @{
                        kind = 'object'
                        changes = @{
                            dependsOn = @{
                                kind = 'changed'
                                after = $byoDependencies
                                before = $byoDependencies
                            }
                            properties = @{
                                kind = 'object'
                                changes = @{ parameters = $subnetParameterRule }
                            }
                        }
                    }
                    containerAppsPostgreSqlSubnet = @{
                        kind = 'object'
                        changes = @{
                            dependsOn = @{
                                kind = 'changed'
                                after = $pgSubnetDependencies
                                before = $pgSubnetDependencies
                            }
                            properties = @{
                                kind = 'object'
                                changes = @{
                                    parameters = @{
                                        kind = 'object'
                                        changes = @{
                                            natGatewayId = @{
                                                kind = 'object'
                                                changes = @{
                                                    value = @{
                                                        kind = 'changed'
                                                        after = "[resourceId(variables('_networkResourceGroupName'), 'Microsoft.Network/natGateways', format('{0}aca-postgresql-{1}', variables('_1.abbrs').networking.natGateway, parameters('resourceToken')))]"
                                                        before = "[reference('containerAppsPostgreSqlNat').outputs.resourceId.value]"
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

function ConvertTo-PreSubnetConditionalReferencesGraph {
    param([Parameter(Mandatory)] $Template)
    $copy = ConvertTo-Json -InputObject $Template -Depth 100 -Compress |
        ConvertFrom-Json -AsHashtable -Depth 100
    return Invoke-ScopedProjection $copy (Get-SubnetConditionalReferencesProjection)
}

function ConvertTo-DeterministicSubnetPrePostgreSqlGraph {
    param([Parameter(Mandatory)] $PrePostgreSqlTemplate)
    $copy = ConvertTo-Json -InputObject $PrePostgreSqlTemplate -Depth 100 -Compress |
        ConvertFrom-Json -AsHashtable -Depth 100
    $rule = Get-SubnetConditionalReferencesProjection
    $varChanges = $rule.changes.variables.changes
    $pgNatBranch = "if(and(equals(lambdaVariables('subnet').purpose, 'acaEnvironment'), variables('_postgreSqlBasic')), resourceId(variables('_networkResourceGroupName'), 'Microsoft.Network/natGateways', format('{0}aca-postgresql-{1}', variables('_1.abbrs').networking.natGateway, parameters('resourceToken'))), '')"
    if ([regex]::Matches($varChanges.subnets.after, [regex]::Escape($pgNatBranch)).Count -ne 1) {
        throw 'SCOPED: unexpected PostgreSQL NAT branch count in deterministic subnet projection.'
    }
    $copy.variables._effectiveNatGatewayId = $varChanges._effectiveNatGatewayId.after
    $copy.variables._effectiveRouteTableId = $varChanges._effectiveRouteTableId.after
    $copy.variables.subnets = $varChanges.subnets.after.Replace($pgNatBranch, "''")
    $copy.resources.virtualNetwork.properties.parameters.subnets.value = "[variables('subnets')]"
    $copy.resources.virtualNetworkSubnets.properties.parameters.subnets.value = "[variables('subnets')]"
    return $copy
}
