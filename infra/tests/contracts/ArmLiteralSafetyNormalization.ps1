# Exact bounded inverse of the ARM literal-safety fix (Bicep 0.42.1):
# - additionalAppConfigurationSettings passthrough moved from variable copy
#   loops to map() so ARM keeps values such as "[]" literal;
# - DEPLOYMENT_METADATA reads the conditional cross-RG Cosmos deployment with an
#   explicit apiVersion so preflight accepts deployCosmosDb=false.
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
