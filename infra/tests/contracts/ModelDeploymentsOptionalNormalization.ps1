# Issue #882 Task 3: exact bounded inverse of the optional local AI Foundry
# model deployments gate (deployModelDeployments, default true), compiled with
# Bicep 0.42.1. Historical fixtures and downstream normalization digests remain
# untouched.
function Get-ModelDeploymentsOptionalProjection {
    $historicalModels = "[if(not(empty(parameters('modelDeploymentList'))), parameters('modelDeploymentList'), createArray(createObject('model', createObject('format', 'OpenAI', 'name', 'gpt-5-nano', 'version', '2025-08-07'), 'name', 'gpt-5-nano', 'sku', createObject('name', 'GlobalStandard', 'capacity', 40)), createObject('model', createObject('format', 'OpenAI', 'name', 'text-embedding-3-large', 'version', '1'), 'name', 'text-embedding-3-large', 'sku', createObject('name', 'GlobalStandard', 'capacity', 10))))]"
    $gatedModels = "[if(parameters('deployModelDeployments'), $($historicalModels.Substring(1, $historicalModels.Length - 2)), createArray())]"

    $beforeListExpr = "parameters('modelDeploymentList')"
    $afterListExpr = "if(parameters('deployModelDeployments'), parameters('modelDeploymentList'), createArray())"

    $namesLoopBefore = [ordered]@{
        name  = '_modelDeploymentNamesSettings'
        count = "[length($beforeListExpr)]"
        input = [ordered]@{
            name        = "[${beforeListExpr}[copyIndex('_modelDeploymentNamesSettings')].canonical_name]"
            value       = "[${beforeListExpr}[copyIndex('_modelDeploymentNamesSettings')].name]"
            label       = "[parameters('appConfigLabel')]"
            contentType = 'text/plain'
        }
    }
    $namesLoopAfter = [ordered]@{
        name  = '_modelDeploymentNamesSettings'
        count = "[length($afterListExpr)]"
        input = [ordered]@{
            name        = "[${afterListExpr}[copyIndex('_modelDeploymentNamesSettings')].canonical_name]"
            value       = "[${afterListExpr}[copyIndex('_modelDeploymentNamesSettings')].name]"
            label       = "[parameters('appConfigLabel')]"
            contentType = 'text/plain'
        }
    }

    $settingsLoopBefore = [ordered]@{
        name  = '_modelDeploymentSettings'
        count = "[length($beforeListExpr)]"
        input = [ordered]@{
            canonical_name = "[${beforeListExpr}[copyIndex('_modelDeploymentSettings')].canonical_name]"
            capacity       = "[${beforeListExpr}[copyIndex('_modelDeploymentSettings')].sku.capacity]"
            model          = "[${beforeListExpr}[copyIndex('_modelDeploymentSettings')].model.name]"
            modelFormat    = "[${beforeListExpr}[copyIndex('_modelDeploymentSettings')].model.format]"
            name           = "[${beforeListExpr}[copyIndex('_modelDeploymentSettings')].name]"
            version        = "[${beforeListExpr}[copyIndex('_modelDeploymentSettings')].model.version]"
            apiVersion     = "[coalesce(tryGet(${beforeListExpr}[copyIndex('_modelDeploymentSettings')], 'apiVersion'), '2025-01-01-preview')]"
            endpoint       = "[format('https://{0}.openai.azure.com/', variables('resourceNames').aiFoundryAccountName)]"
        }
    }
    $settingsLoopAfter = [ordered]@{
        name  = '_modelDeploymentSettings'
        count = "[length($afterListExpr)]"
        input = [ordered]@{
            canonical_name = "[${afterListExpr}[copyIndex('_modelDeploymentSettings')].canonical_name]"
            capacity       = "[${afterListExpr}[copyIndex('_modelDeploymentSettings')].sku.capacity]"
            model          = "[${afterListExpr}[copyIndex('_modelDeploymentSettings')].model.name]"
            modelFormat    = "[${afterListExpr}[copyIndex('_modelDeploymentSettings')].model.format]"
            name           = "[${afterListExpr}[copyIndex('_modelDeploymentSettings')].name]"
            version        = "[${afterListExpr}[copyIndex('_modelDeploymentSettings')].model.version]"
            apiVersion     = "[coalesce(tryGet(${afterListExpr}[copyIndex('_modelDeploymentSettings')], 'apiVersion'), '2025-01-01-preview')]"
            endpoint       = "[format('https://{0}.openai.azure.com/', variables('resourceNames').aiFoundryAccountName)]"
        }
    }

    return @{
        kind    = 'object'
        changes = @{
            parameters = @{
                kind    = 'object'
                changes = @{
                    deployModelDeployments = @{
                        kind  = 'added'
                        after = @{
                            type         = 'bool'
                            defaultValue = $true
                            metadata     = @{
                                description = 'Deploy local AI Foundry model deployments. Set to false when all inference routes through an external AI Gateway.'
                            }
                        }
                    }
                }
            }
            variables  = @{
                kind    = 'object'
                changes = @{
                    _deploymentMetadataModels = @{
                        kind   = 'changed'
                        after  = $gatedModels
                        before = $historicalModels
                    }
                    copy                      = @{
                        kind    = 'array'
                        count   = 20
                        changes = @{
                            '15' = @{
                                kind   = 'changed'
                                after  = $namesLoopAfter
                                before = $namesLoopBefore
                            }
                            '18' = @{
                                kind   = 'changed'
                                after  = $settingsLoopAfter
                                before = $settingsLoopBefore
                            }
                        }
                    }
                }
            }
        }
    }
}

function ConvertTo-PreModelDeploymentsOptionalGraph {
    param([Parameter(Mandatory)] $Template)
    $copy = ConvertTo-Json -InputObject $Template -Depth 100 -Compress |
        ConvertFrom-Json -AsHashtable -Depth 100
    return Invoke-ScopedProjection $copy (Get-ModelDeploymentsOptionalProjection)
}

function ConvertTo-ModelDeploymentsOptionalPrePostgreSqlGraph {
    param([Parameter(Mandatory)] $PrePostgreSqlTemplate)
    $copy = ConvertTo-Json -InputObject $PrePostgreSqlTemplate -Depth 100 -Compress |
        ConvertFrom-Json -AsHashtable -Depth 100
    $rule = Get-ModelDeploymentsOptionalProjection
    $copy.parameters.deployModelDeployments = $rule.changes.parameters.changes.deployModelDeployments.after
    $copy.variables._deploymentMetadataModels = $rule.changes.variables.changes._deploymentMetadataModels.after
    for ($i = 0; $i -lt $copy.variables.copy.Count; $i++) {
        $loopName = $copy.variables.copy[$i].name
        if ($loopName -ceq '_modelDeploymentNamesSettings') {
            $copy.variables.copy[$i] = $rule.changes.variables.changes.copy.changes['15'].after
        }
        elseif ($loopName -ceq '_modelDeploymentSettings') {
            $copy.variables.copy[$i] = $rule.changes.variables.changes.copy.changes['18'].after
        }
    }
    return $copy
}
