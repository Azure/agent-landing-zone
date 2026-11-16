# Exact bounded inverse of the ARM literal-safety fix (Bicep 0.42.1):
# - additionalAppConfigurationSettings passthrough moved from variable copy
#   loops to map() so ARM keeps values such as "[]" literal;
# - DEPLOYMENT_METADATA derives Cosmos values from names, because a reference()
#   to the conditional cross-RG deployment fails preflight or the deployment.
# Only these compiled values are restored. Historical fingerprints still verify
# every other resource, variable and output.
function Get-ArmLiteralSafetyProjection {
    $list = "parameters('additionalAppConfigurationSettings')"
    return @{
        containerEnvIndex = 10
        containerEnvAfter = "[map($list, lambda('s', createObject('name', lambdaVariables('s').name, 'value', lambdaVariables('s').value)))]"
        containerEnvBefore = [ordered]@{
            name  = '_additionalContainerEnv'
            count = "[length($list)]"
            input = [ordered]@{
                name  = "[${list}[copyIndex('_additionalContainerEnv')].name]"
                value = "[${list}[copyIndex('_additionalContainerEnv')].value]"
            }
        }
        appConfigIndex = 19
        appConfigAfter = "[map($list, lambda('s', createObject('name', lambdaVariables('s').name, 'value', lambdaVariables('s').value, 'label', coalesce(tryGet(lambdaVariables('s'), 'label'), parameters('appConfigLabel')), 'contentType', coalesce(tryGet(lambdaVariables('s'), 'contentType'), 'text/plain'))))]"
        appConfigBefore = [ordered]@{
            name  = '_normalizedAdditionalAppConfigSettings'
            count = "[length($list)]"
            input = [ordered]@{
                name        = "[${list}[copyIndex('_normalizedAdditionalAppConfigSettings')].name]"
                value       = "[${list}[copyIndex('_normalizedAdditionalAppConfigSettings')].value]"
                label       = "[coalesce(tryGet(${list}[copyIndex('_normalizedAdditionalAppConfigSettings')], 'label'), parameters('appConfigLabel'))]"
                contentType = "[coalesce(tryGet(${list}[copyIndex('_normalizedAdditionalAppConfigSettings')], 'contentType'), 'text/plain')]"
            }
        }
        copyCount = 18
        cosmosAfter = "reference(resourceId(variables('_applicationResourceGroupName'), 'Microsoft.Resources/deployments', 'CosmosDBAccount'), '2022-09-01')"
        cosmosBefore = "reference('cosmosDBAccount')"
        cosmosUses = [ordered]@{ cosmosResource = 3; cosmosDatabases = 1; cosmosContainers = 1 }
        cosmosIdDerived = "[format('/subscriptions/{0}/resourceGroups/{1}/providers/Microsoft.DocumentDB/databaseAccounts/{2}', subscription().subscriptionId, variables('_applicationResourceGroupName'), variables('resourceNames').dbAccountName)]"
        cosmosResourceDerived = "[if(parameters('deployCosmosDb'), createObject('resourceId', variables('_cosmosMetadataResourceId'), 'name', variables('resourceNames').dbAccountName, 'endpoint', format('https://{0}.documents.azure.com:443/', variables('resourceNames').dbAccountName)), null())]"
    }
}

function ConvertTo-PreArmLiteralSafetyGraph {
    param([Parameter(Mandatory)] $Template)
    $copy = ConvertTo-Json -InputObject $Template -Depth 100 -Compress |
        ConvertFrom-Json -AsHashtable -Depth 100
    $rule = Get-ArmLiteralSafetyProjection

    Assert-ScopedValue $copy.variables._additionalContainerEnv $rule.containerEnvAfter '/variables/_additionalContainerEnv'
    Assert-ScopedValue $copy.variables._normalizedAdditionalAppConfigSettings $rule.appConfigAfter '/variables/_normalizedAdditionalAppConfigSettings'
    $loops = [System.Collections.Generic.List[object]]::new()
    foreach ($loop in @($copy.variables.copy)) { $loops.Add($loop) }
    if ($loops.Count -ne $rule.copyCount -or
        @($loops | Where-Object { $_.name -ceq '_additionalContainerEnv' -or $_.name -ceq '_normalizedAdditionalAppConfigSettings' }).Count -ne 0) {
        throw 'SCOPED: ARM literal-safety copy loop membership changed.'
    }
    $loops.Insert($rule.containerEnvIndex, $rule.containerEnvBefore)
    $loops.Insert($rule.appConfigIndex, $rule.appConfigBefore)
    $copy.variables.copy = $loops.ToArray()
    $null = $copy.variables.Remove('_additionalContainerEnv')
    $null = $copy.variables.Remove('_normalizedAdditionalAppConfigSettings')

    $metadata = $copy.outputs.DEPLOYMENT_METADATA.value
    # Cosmos metadata is derived from names. Restore the deployment-output form
    # first, then the shared inverse below restores the historical reference.
    $idRef = "variables('_cosmosMetadataResourceId')"
    $nameRef = "variables('resourceNames').dbAccountName"
    $out = "$($rule.cosmosAfter).outputs"
    Assert-ScopedValue $copy.variables._cosmosMetadataResourceId $rule.cosmosIdDerived '/variables/_cosmosMetadataResourceId'
    Assert-ScopedValue $metadata.resources.cosmos.resource $rule.cosmosResourceDerived '/outputs/DEPLOYMENT_METADATA/cosmosResource'
    Assert-ScopedValue $metadata.dataResources.cosmosContainers "[variables('_deploymentMetadataCosmosBindings')]" '/outputs/DEPLOYMENT_METADATA/cosmosContainers'
    $bindings = [string]$copy.variables._deploymentMetadataCosmosBindings
    $databases = [string]$metadata.dataResources.cosmosDatabases
    if ([regex]::Matches($bindings, [regex]::Escape($idRef)).Count -ne 1 -or
        [regex]::Matches($databases, [regex]::Escape($idRef)).Count -ne 1) {
        throw 'SCOPED: unreviewed derived Cosmos metadata reference.'
    }
    $metadata.resources.cosmos.resource = $rule.cosmosResourceDerived.
        Replace("'resourceId', $idRef", "'resourceId', $out.resourceId.value").
        Replace("'name', $nameRef, 'endpoint', format('https://{0}.documents.azure.com:443/', $nameRef)", "'name', $out.name.value, 'endpoint', $out.endpoint.value")
    $metadata.dataResources.cosmosDatabases = $databases.Replace($idRef, "$out.resourceId.value")
    $metadata.dataResources.cosmosContainers = $bindings.Replace($idRef, "$out.resourceId.value")
    $null = $copy.variables.Remove('_cosmosMetadataResourceId')
    $null = $copy.variables.Remove('_deploymentMetadataCosmosBindings')

    $targets = [ordered]@{
        cosmosResource   = @{ Parent = $metadata.resources.cosmos; Key = 'resource' }
        cosmosDatabases  = @{ Parent = $metadata.dataResources; Key = 'cosmosDatabases' }
        cosmosContainers = @{ Parent = $metadata.dataResources; Key = 'cosmosContainers' }
    }
    foreach ($name in $targets.Keys) {
        $target = $targets[$name]
        $value = [string]$target.Parent[$target.Key]
        if ($value.Contains($rule.cosmosBefore) -or
            [regex]::Matches($value, [regex]::Escape($rule.cosmosAfter)).Count -ne $rule.cosmosUses[$name]) {
            throw "SCOPED: unreviewed Cosmos metadata reference at /outputs/DEPLOYMENT_METADATA/$name."
        }
        $target.Parent[$target.Key] = $value.Replace($rule.cosmosAfter, $rule.cosmosBefore)
    }
    return $copy
}
