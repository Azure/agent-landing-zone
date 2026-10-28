<#
.SYNOPSIS
    Validates ACR Task agent-pool subnet ordering for issue #159.

.DESCRIPTION
    Compiles the real orchestrator with Azure CLI Bicep and checks exact symbolic
    dependencies, bounded expressions, pool properties, and serialized cross-scope
    child subnet deployments. ADR-0024 application wrappers are checked by an
    exact before/after projection before the original assertions. No original
    fingerprint is replaced and no Azure access is used.

    A1/A2 cover BYO subnet creation/reuse; A3 covers a new VNet; A4-A6 cover
    disabled gates; A7 covers count zero in both BYO paths; A8 protects the
    existing invalid BYO/NSG combination; A9 protects cross-scope declarations.
    Scenario projections run only after their compiled expressions match exactly.
    They are not a general ARM evaluator or evidence of runtime deployment order,
    capacity, unrelated-subnet preservation, or successful pool provisioning.
    The separate firewall contract remains necessary.
    Issue #168 additionally guards reserved-subnet NSG fallback and precedence
    of the dedicated NSG when Bastion is enabled.

    Use the repository's Azure CLI Bicep 0.42.1 toolchain; deliberately do not fall
    back to an older standalone compiler. The unique compiled artifact is removed
    in finally, including on compilation or assertion failure.

.EXAMPLE
    pwsh ./tests/contracts/Test-AcrTaskAgentPoolSubnetContract.ps1

.EXAMPLE
    pwsh ./tests/contracts/Test-AcrTaskAgentPoolSubnetContract.ps1 -MainFile /isolated-copy/main.bicep
#>

[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'main.bicep')
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ScopedResourceGroupNormalization.ps1')
$failures = [System.Collections.Generic.List[string]]::new()
$compiledFile = Join-Path ([System.IO.Path]::GetTempPath()) "acr-task-agent-pool-subnet-contract-$([guid]::NewGuid()).json"

function Add-Failure {
    param([string]$Message)
    $failures.Add($Message) | Out-Null
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Test-Equal {
    param([string]$Name, [AllowNull()]$Actual, [AllowNull()]$Expected)
    # JSON preserves Boolean/integer/string distinctions, nulls, and array shape.
    $actualJson = ConvertTo-Json -InputObject $Actual -Depth 100 -Compress
    $expectedJson = ConvertTo-Json -InputObject $Expected -Depth 100 -Compress
    if ($actualJson -cne $expectedJson) {
        Add-Failure "$Name -- expected $expectedJson; got $actualJson."
    }
    else {
        Write-Host "  [PASS] $Name" -ForegroundColor Green
    }
}

function Test-Set {
    param([string]$Name, [AllowNull()]$Actual, [string[]]$Expected)
    # Sort only sets of names/dependencies, never expressions or property values.
    Test-Equal $Name @($Actual | Sort-Object -CaseSensitive) @($Expected | Sort-Object -CaseSensitive)
}

try {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        throw 'Azure CLI Bicep is required (az bicep install --version v0.42.1); standalone Bicep is not used.'
    }
    $env:PYTHONIOENCODING = 'utf-8'
    & az bicep build --file $MainFile --outfile $compiledFile
    if ($LASTEXITCODE -ne 0) {
        throw "Bicep compilation failed with exit code $LASTEXITCODE."
    }
    $actual = Get-Content -LiteralPath $compiledFile -Raw | ConvertFrom-Json -AsHashtable -Depth 100
    $subnetGraph = $actual | ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json -Depth 100
    $template = ConvertTo-ApplicationRootResourceGroupGraph $actual |
        ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json -Depth 100
    Write-Host "ACR Task agent pool subnet contract (#159); compilation succeeded with Bicep $($template.metadata._generator.version)." -ForegroundColor Cyan

    $pool = $template.resources.acrTaskAgentPool
    # Pool wrappers retain the historical representation, but subnet selection,
    # NSG safety and child writes must be checked on the actual ADR-0027 graph.
    $subnets = $subnetGraph.resources.virtualNetworkSubnets
    $validation = $subnetGraph.resources.componentFlagValidation
    if ($null -eq $pool -or $null -eq $subnets -or $null -eq $validation) {
        throw 'Required symbolic resources acrTaskAgentPool, virtualNetworkSubnets, and componentFlagValidation must exist.'
    }

    # One exact graph assertion gives a single actionable RED on the pre-fix
    # template. An output-derived, conditional, or child-resource edge is not a
    # substitute for the direct orchestrating-module symbol.
    Test-Set 'Pool dependsOn must contain exactly containerRegistry, virtualNetwork, virtualNetworkSubnets (direct symbolic subnet-completion edge)' `
        $pool.dependsOn @('containerRegistry', 'virtualNetwork', 'virtualNetworkSubnets')

    Test-Set 'Pool declaration has no additional scope, copy, identity, or resource fields' `
        $pool.PSObject.Properties.Name @('condition', 'type', 'apiVersion', 'name', 'location', 'tags', 'properties', 'dependsOn')
    $poolFields = [ordered]@{
        type       = 'Microsoft.ContainerRegistry/registries/agentPools'
        apiVersion = '2019-06-01-preview'
        name       = "[format('{0}/{1}', variables('resourceNames').containerRegistryName, parameters('acrTaskAgentPoolName'))]"
        location   = "[parameters('location')]"
        tags       = "[variables('_tags')]"
    }
    foreach ($entry in $poolFields.GetEnumerator()) {
        Test-Equal "Pool $($entry.Key) unchanged" $pool.($entry.Key) $entry.Value
    }
    Test-Set 'Pool property surface unchanged' $pool.properties.PSObject.Properties.Name @('count', 'tier', 'os', 'virtualNetworkSubnetResourceId')
    Test-Equal 'Pool OS unchanged' $pool.properties.os 'Linux'
    Test-Equal 'Registry gate unchanged' $template.resources.containerRegistry.condition "[parameters('deployContainerRegistry')]"
    Test-Equal 'Registry Premium/private and Basic/standard SKU selection unchanged' `
        $template.resources.containerRegistry.sku.name "[if(variables('_networkIsolation'), 'Premium', 'Basic')]"

    $parameterContracts = [ordered]@{
        networkIsolation        = @{ Type = 'bool'; Default = $false }
        useExistingVNet         = @{ Type = 'bool'; Default = $false }
        deploySubnets           = @{ Type = 'bool'; Default = $true }
        deployNsgs              = @{ Type = 'bool'; Default = $true }
        deployContainerRegistry = @{ Type = 'bool'; Default = $true }
        deployAcrTaskAgentPool   = @{ Type = 'bool'; Default = $true }
        prepareHostedAgent      = @{ Type = 'bool'; Default = $false }
        deployHostedAgent       = @{ Type = 'bool'; Default = $false }
        acrTaskAgentPoolName     = @{ Type = 'string'; Default = 'build-pool' }
        acrTaskAgentPoolTier     = @{ Type = 'string'; Default = 'S1' }
        acrTaskAgentPoolCount    = @{ Type = 'int'; Default = 1 }
    }
    foreach ($entry in $parameterContracts.GetEnumerator()) {
        $parameter = $template.parameters.($entry.Key)
        Test-Equal "$($entry.Key) type/default" @($parameter.type, $parameter.defaultValue) @($entry.Value.Type, $entry.Value.Default)
    }
    Test-Equal 'Pool name length contract' $template.parameters.acrTaskAgentPoolName.maxLength 20
    Test-Equal 'Pool tiers unchanged' $template.parameters.acrTaskAgentPoolTier.allowedValues @('S1', 'S2', 'S3')
    Test-Equal 'Pool count permits zero' $template.parameters.acrTaskAgentPoolCount.minValue 0
    Test-Equal 'Pool output remains string' $template.outputs.ACR_TASK_AGENT_POOL.type 'string'
    Test-Equal 'Hosted-agent handoff remains object' $template.outputs.HOSTED_AGENT_DEPLOYMENT.type 'object'

    # These exact bindings are the only supported scenario semantics. Do not
    # evaluate arbitrary ARM expressions or infer correctness from token presence.
    $bindings = [ordered]@{
        Isolation = @(
            $template.variables._networkIsolation
            "[if(empty(string(parameters('networkIsolation'))), false(), bool(parameters('networkIsolation')))]"
        )
        PoolGate = @(
            $template.variables._deployAcrTaskAgentPool
            "[and(and(parameters('deployContainerRegistry'), variables('_networkIsolation')), parameters('deployAcrTaskAgentPool'))]"
        )
        PoolCondition = @($pool.condition, "[variables('_deployAcrTaskAgentPool')]")
        SubnetCondition = @(
            $subnets.condition
            "[and(and(and(and(variables('_networkIsolation'), parameters('useExistingVNet')), parameters('deploySubnets')), parameters('deployNsgs')), not(empty(variables('selectedSubnetDefinitions'))))]"
        )
        NewVnetCondition = @(
            $template.resources.virtualNetwork.condition
            "[and(variables('_networkIsolation'), not(parameters('useExistingVNet')))]"
        )
        NsgProtection = @(
            $validation.properties.parameters.existingSubnetNsgAssociationsAreProtected.value
            "[not(and(and(and(parameters('networkIsolation'), parameters('useExistingVNet')), not(empty(variables('selectedSubnetDefinitions')))), not(parameters('deployNsgs'))))]"
        )
        NsgRejection = @(
            $validation.properties.template.outputs.validated.value
            "[if(parameters('containerAppsRequireEnvironment'), if(parameters('containerAppApiKeysHavePrerequisites'), if(parameters('existingSubnetNsgAssociationsAreProtected'), true(), fail('A network-isolated deployment cannot update subnets in an existing VNet while deployNsgs is false.')), fail('Container App API keys require Container Apps, Key Vault, App Configuration, and appConfig runtime mode.')), fail('Container Apps require the Container Apps Environment.'))]"
        )
        SubnetId = @(
            $pool.properties.virtualNetworkSubnetResourceId
            "[if(variables('_networkIsolation'), format('{0}/subnets/{1}', if(variables('_networkIsolation'), if(parameters('useExistingVNet'), parameters('existingVnetResourceId'), reference('virtualNetwork').outputs.resourceId.value), ''), parameters('devopsBuildAgentsSubnetName')), '')]"
        )
        Count = @($pool.properties.count, "[parameters('acrTaskAgentPoolCount')]")
        Tier = @($pool.properties.tier, "[parameters('acrTaskAgentPoolTier')]")
        Output = @(
            $template.outputs.ACR_TASK_AGENT_POOL.value
            "[if(variables('_deployAcrTaskAgentPool'), parameters('acrTaskAgentPoolName'), '')]"
        )
        HostedPrerequisites = @(
            $template.variables._hostedAgentPrerequisitesEnabled
            "[or(parameters('prepareHostedAgent'), parameters('deployHostedAgent'))]"
        )
        Handoff = @(
            $template.outputs.HOSTED_AGENT_DEPLOYMENT.value.privateBuild.acrTaskAgentPoolName
            "[if(and(variables('_hostedAgentPrerequisitesEnabled'), variables('_deployAcrTaskAgentPool')), parameters('acrTaskAgentPoolName'), '')]"
        )
    }
    $bindingFailureCount = $failures.Count
    foreach ($entry in $bindings.GetEnumerator()) {
        Test-Equal "Exact $($entry.Key) expression" $entry.Value[0] $entry.Value[1]
    }
    Test-Equal 'NSG validation module remains unconditional' $validation.condition $null
    Test-Equal 'NSG validation parameter stays Boolean' $validation.properties.template.parameters.existingSubnetNsgAssociationsAreProtected.type 'bool'

    if ($failures.Count -eq $bindingFailureCount) {
        # Fixed truth table for Boolean inputs only, after ALL relevant compiled
        # bindings above matched. A8 intentionally has a true pool gate but an
        # invalid overall configuration, not a newly invented pool condition.
        $cases = @(
            # ID, isolation, BYO, subnets, NSGs, registry, pool, count,
            # expected pool, subnet module, new VNet, valid NSG combination
            @('A1',  $true,  $true,  $true,  $true,  $true,  $true,  1, $true,  $true,  $false, $true),
            @('A2',  $true,  $true,  $false, $true,  $true,  $true,  1, $true,  $false, $false, $true),
            @('A3',  $true,  $false, $true,  $true,  $true,  $true,  1, $true,  $false, $true,  $true),
            @('A4',  $true,  $true,  $true,  $true,  $true,  $false, 1, $false, $true,  $false, $true),
            @('A5',  $true,  $true,  $true,  $true,  $false, $true,  1, $false, $true,  $false, $true),
            @('A6',  $false, $true,  $true,  $true,  $true,  $true,  1, $false, $false, $false, $true),
            @('A7-create', $true, $true, $true,  $true, $true, $true, 0, $true, $true,  $false, $true),
            @('A7-reuse',  $true, $true, $false, $true, $true, $true, 0, $true, $false, $false, $true),
            @('A8',  $true,  $true,  $true,  $false, $true,  $true,  1, $true,  $false, $false, $false),
            @('A9',  $true,  $true,  $true,  $true,  $true,  $true,  1, $true,  $true,  $false, $true)
        )
        foreach ($case in $cases) {
            $id, $isolation, $byo, $createSubnets, $nsgs, $registry, $requestedPool, $count,
                $expectedPool, $expectedSubnets, $expectedVnet, $expectedValid = $case
            $enabled = $registry -and $isolation -and $requestedPool
            $subnetEnabled = $isolation -and $byo -and $createSubnets -and $nsgs
            $vnetEnabled = $isolation -and -not $byo
            $valid = -not ($isolation -and $byo -and $createSubnets -and -not $nsgs)
            Test-Equal "$id bounded pool/subnet/new-VNet/NSG truth table" `
                @($enabled, $subnetEnabled, $vnetEnabled, $valid) @($expectedPool, $expectedSubnets, $expectedVnet, $expectedValid)

            # Forward through the exact direct parameter bindings checked above;
            # use a non-default name and every supported tier, including count 0.
            $poolName = 'contract-pool'
            foreach ($tier in @('S1', 'S2', 'S3')) {
                $directInputs = @{
                    "[parameters('acrTaskAgentPoolCount')]" = $count
                    "[parameters('acrTaskAgentPoolTier')]" = $tier
                }
                $forwardedCount = $directInputs[[string]$pool.properties.count]
                $forwardedTier = $directInputs[[string]$pool.properties.tier]
                Test-Equal "$id forwards requested $tier / $count without scale-up" @($forwardedTier, $forwardedCount) @($tier, $count)
            }
            $output = if ($enabled) { $poolName } else { '' }
            $expectedOutput = if ($expectedPool) { 'contract-pool' } else { '' }
            Test-Equal "$id pool output/fallback" $output $expectedOutput
            foreach ($hostedFlags in @(@($false, $false), @($true, $false), @($false, $true), @($true, $true))) {
                $prepared = $hostedFlags[0] -or $hostedFlags[1]
                $handoff = if ($prepared -and $enabled) { $poolName } else { '' }
                $expectedHandoff = if ($prepared -and $expectedPool) { 'contract-pool' } else { '' }
                Test-Equal "$id handoff (prepare=$($hostedFlags[0]), deploy=$($hostedFlags[1])); never forces a pool" $handoff $expectedHandoff
            }
        }
    }
    else {
        Write-Host '  Scenario projection skipped: unsupported compiled binding(s); contract fails closed.' -ForegroundColor Yellow
    }

    # A9: inspect real scope declarations rather than pretending to deploy a
    # synthetic subscription. The module stays local; its children target the
    # subscription/RG extracted from the supplied existing VNet resource ID.
    Test-Equal 'Subnet orchestrator deployment name' $subnets.name 'virtualNetworkSubnetsDeployment'
    Test-Equal 'Subnet orchestrator deployment type' $subnets.type 'Microsoft.Resources/deployments'
    Test-Equal 'Subnet orchestrator remains in caller scope' @($subnets.subscriptionId, $subnets.resourceGroup) @($null, $null)
    Test-Equal 'Subnet orchestrator exposes no new outputs' $subnets.properties.template.outputs $null
    $scopeVariables = [ordered]@{
        varVnetIdSegments = "[if(empty(parameters('existingVnetResourceId')), createArray(''), split(parameters('existingVnetResourceId'), '/'))]"
        varExistingVnetSubscriptionId = "[if(greaterOrEquals(length(variables('varVnetIdSegments')), 3), variables('varVnetIdSegments')[2], subscription().subscriptionId)]"
        varExistingVnetResourceGroupName = "[if(greaterOrEquals(length(variables('varVnetIdSegments')), 5), variables('varVnetIdSegments')[4], resourceGroup().name)]"
        varExistingVnetName = "[if(greaterOrEquals(length(variables('varVnetIdSegments')), 9), variables('varVnetIdSegments')[8], '')]"
    }
    foreach ($entry in $scopeVariables.GetEnumerator()) {
        Test-Equal "A9 $($entry.Key) extraction" $template.variables.($entry.Key) $entry.Value
    }
    $scopeBindings = [ordered]@{
        vnetName = "[if(parameters('useExistingVNet'), createObject('value', variables('varExistingVnetName')), createObject('value', variables('resourceNames').vnetName))]"
        subscriptionId = "[if(parameters('useExistingVNet'), createObject('value', variables('varExistingVnetSubscriptionId')), createObject('value', subscription().subscriptionId))]"
        resourceGroupName = "[if(parameters('useExistingVNet'), createObject('value', variables('varExistingVnetResourceGroupName')), createObject('value', variables('_networkResourceGroupName')))]"
        virtualNetworkResourceId = "[if(variables('_networkIsolation'), if(parameters('useExistingVNet'), createObject('value', parameters('existingVnetResourceId')), createObject('value', reference('virtualNetwork').outputs.resourceId.value)), createObject('value', ''))]"
    }
    foreach ($entry in $scopeBindings.GetEnumerator()) {
        Test-Equal "A9 $($entry.Key) forwarding" $subnets.properties.parameters.($entry.Key) $entry.Value
    }
    foreach ($name in @('useExistingVNet', 'deploySubnets', 'deployNsgs')) {
        Test-Equal "Subnet module $name forwarding" $subnets.properties.parameters.$name.value "[parameters('$name')]"
    }
    # Check the real build definition, including its independent ownership flag.
    # The common projection supplies routing/NSGs, not per-consumer fallbacks.
    $subnetExpression = [string]$subnets.properties.parameters.subnets.value
    $buildDefinitions = @($subnetGraph.variables.subnetDefinitions | Where-Object purpose -CEQ 'devopsBuildAgents')
    Test-Equal 'Exactly one build subnet definition' $buildDefinitions.Count 1
    Test-Set 'Build subnet definition property surface' $buildDefinitions[0].PSObject.Properties.Name @('purpose', 'create', 'required', 'name', 'addressPrefix', 'delegation', 'serviceEndpoints')
    foreach ($entry in ([ordered]@{
        purpose = 'devopsBuildAgents'
        create = "[parameters('deployDevopsBuildAgentsSubnet')]"
        required = "[variables('_deployAcrTaskAgentPool')]"
        name = "[parameters('devopsBuildAgentsSubnetName')]"
        addressPrefix = "[parameters('devopsBuildAgentsSubnetPrefix')]"
        delegation = ''
        serviceEndpoints = @()
    }).GetEnumerator()) {
        Test-Equal "Build subnet $($entry.Key)" $buildDefinitions[0].($entry.Key) $entry.Value
    }
    Test-Equal 'Subnet creation does not disable the build pool or retarget its subnet' `
        $subnetGraph.variables._deployAcrTaskAgentPool "[and(and(parameters('deployContainerRegistry'), variables('_networkIsolation')), parameters('deployAcrTaskAgentPool'))]"
    Test-Equal 'New and BYO paths share the exact subnet resource projection' `
        $subnetExpression $subnetGraph.resources.virtualNetwork.properties.parameters.subnets.value
    Test-Equal 'Build subnet retains actual route-table selection in the common projection' `
        $subnetExpression.Contains("'routeTableResourceId', if(contains(createArray('agent', 'pe', 'jumpbox', 'acaEnvironment', 'devopsBuildAgents', 'applicationPe'), lambdaVariables('subnet').purpose), if(variables('_hasExistingRouteTable'), parameters('hubIntegrationExistingRouteTableResourceId'), if(variables('_createRouteTable'), reference('routeTable').outputs.resourceId.value, '')), '')") $true

    $children = @($subnets.properties.template.resources)
    Test-Equal 'Subnet orchestrator retains exactly three child deployment declarations' $children.Count 3
    foreach ($child in $children) {
        Test-Equal "Child $($child.name) is a scoped deployment" `
            @($child.type, $child.subscriptionId, $child.resourceGroup, $child.properties.mode, $child.properties.expressionEvaluationOptions.scope) `
            @('Microsoft.Resources/deployments', "[parameters('subscriptionId')]", "[parameters('resourceGroupName')]", 'Incremental', 'inner')
    }
    $subnetChildren = @($children | Where-Object { $_.copy.name -ceq 'subnetsM' })
    $nsgChildren = @($children | Where-Object { $_.copy.name -ceq 'nsgsM' })
    $vnetChildren = @($children | Where-Object { $_.name -ceq 'virtualNetworkDeployment' })
    Test-Equal 'Exactly one subnet/NSG/new-VNet child declaration each' @($subnetChildren.Count, $nsgChildren.Count, $vnetChildren.Count) @(1, 1, 1)
    if ($subnetChildren.Count -ne 1 -or $nsgChildren.Count -ne 1 -or $vnetChildren.Count -ne 1) {
        throw 'Cannot inspect changed child-deployment shapes.'
    }
    Test-Equal 'BYO path cannot PUT the complete VNet subnet collection' `
        $vnetChildren[0].condition "[and(not(parameters('useExistingVNet')), parameters('deploySubnets'))]"
    Test-Equal 'NSG child gate excludes reserved subnets and duplicate dedicated NSGs' $nsgChildren[0].condition "[and(and(and(parameters('deploySubnets'), parameters('deployNsgs')), not(contains(variables('invalidNsgSubnets'), parameters('subnets')[copyIndex()].name))), empty(coalesce(tryGet(parameters('subnets')[copyIndex()], 'networkSecurityGroupResourceId'), '')))]"
    $subnetChild = $subnetChildren[0]
    Test-Equal 'Subnet child gate unchanged' $subnetChild.condition "[and(parameters('useExistingVNet'), parameters('deploySubnets'))]"
    Test-Equal 'Subnet children serialize one PUT at a time' @($subnetChild.copy.mode, $subnetChild.copy.batchSize) @('serial', 1)
    Test-Equal 'Subnet copy covers only the supplied subnets' $subnetChild.copy.count "[length(range(0, length(parameters('subnets'))))]"
    Test-Equal 'Subnet child targets a named VNet/subnet, not a whole VNet' `
        $subnetChild.properties.parameters.name.value "[format('{0}/{1}', parameters('vnetName'), parameters('subnets')[range(0, length(parameters('subnets')))[copyIndex()]].name)]"
    Test-Set 'Subnet child waits for its cross-scope NSG' $subnetChild.dependsOn @(
        "[extensionResourceId(format('/subscriptions/{0}/resourceGroups/{1}', parameters('subscriptionId'), parameters('resourceGroupName')), 'Microsoft.Resources/deployments', format('{0}{1}-{2}', parameters('prefix'), parameters('vnetName'), parameters('subnets')[range(0, length(parameters('subnets')))[copyIndex()]].name))]"
    )
    $excluded = @($subnets.properties.template.variables.invalidNsgSubnets)
    Test-Equal 'Generic NSG exclusions retain reserved service subnets including Basic management' `
        $excluded @('AzureFirewallSubnet', 'AppGatewaySubnet', 'AzureBastionSubnet', 'GatewaySubnet', 'AzureFirewallManagementSubnet')
    $selection = @'
[if(not(empty(coalesce(tryGet(parameters('subnets')[range(0, length(parameters('subnets')))[copyIndex()]], 'networkSecurityGroupResourceId'), ''))), createObject('value', string(parameters('subnets')[range(0, length(parameters('subnets')))[copyIndex()]].networkSecurityGroupResourceId)), if(and(parameters('deployNsgs'), not(contains(variables('invalidNsgSubnets'), parameters('subnets')[range(0, length(parameters('subnets')))[copyIndex()]].name))), createObject('value', reference(extensionResourceId(format('/subscriptions/{0}/resourceGroups/{1}', parameters('subscriptionId'), parameters('resourceGroupName')), 'Microsoft.Resources/deployments', format('{0}{1}-{2}', parameters('prefix'), parameters('vnetName'), parameters('subnets')[range(0, length(parameters('subnets')))[copyIndex()]].name)), '2025-04-01').outputs.id.value), createObject('value', '')))]
'@
    Test-Equal '#168 explicit NSG selection precedes the unchanged generic fallback' `
        $subnetChild.properties.parameters.networkSecurityGroupId $selection
    Test-Equal '#168 dedicated Bastion NSG stays gated on Bastion and NSGs' `
        $template.resources.bastionNsg.condition "[and(variables('_deployBastion'), parameters('deployNsgs'))]"
    $bastionDefinitions = @($subnetGraph.variables.subnetDefinitions | Where-Object purpose -CEQ 'bastion')
    Test-Equal '#168 Bastion creation is independent of host deployment' `
        @($bastionDefinitions.Count, $bastionDefinitions[0].create, $bastionDefinitions[0].name, $bastionDefinitions[0].delegation) `
        @(1, "[parameters('deployAzureBastionSubnet')]", "[parameters('azureBastionSubnetName')]", '')
    Test-Equal '#168 enabled Bastion retains its dedicated NSG binding in the common projection' `
        $subnetExpression.Contains("'networkSecurityGroupResourceId', if(and(and(equals(lambdaVariables('subnet').purpose, 'bastion'), variables('_deployBastion')), parameters('deployNsgs')), reference('bastionNsg').outputs.id.value,") $true
    if ($subnetChild.properties.parameters.networkSecurityGroupId -ceq $selection) {
        foreach ($case in @(
            @{ Name = 'Bastion disabled'; Subnet = 'AzureBastionSubnet'; Explicit = ''; Nsgs = $true; Expected = '' }
            @{ Name = 'Bastion enabled'; Subnet = 'AzureBastionSubnet'; Explicit = 'dedicated-bastion-nsg'; Nsgs = $true; Expected = 'dedicated-bastion-nsg' }
            @{ Name = 'NSGs disabled'; Subnet = 'AzureBastionSubnet'; Explicit = ''; Nsgs = $false; Expected = '' }
            @{ Name = 'Explicit override'; Subnet = 'AzureBastionSubnet'; Explicit = 'operator-nsg'; Nsgs = $false; Expected = 'operator-nsg' }
            @{ Name = 'Firewall exclusion'; Subnet = 'AzureFirewallSubnet'; Explicit = ''; Nsgs = $true; Expected = '' }
            @{ Name = 'Gateway exclusion'; Subnet = 'AppGatewaySubnet'; Explicit = ''; Nsgs = $true; Expected = '' }
            @{ Name = 'VPN gateway exclusion'; Subnet = 'GatewaySubnet'; Explicit = ''; Nsgs = $true; Expected = '' }
            @{ Name = 'Basic management exclusion'; Subnet = 'AzureFirewallManagementSubnet'; Explicit = ''; Nsgs = $true; Expected = '' }
            @{ Name = 'Build subnet'; Subnet = 'devops-build-agents-subnet'; Explicit = ''; Nsgs = $true; Expected = 'generic-nsg' }
            @{ Name = 'Custom idle subnet'; Subnet = 'unused-bastion-subnet'; Explicit = ''; Nsgs = $true; Expected = 'generic-nsg' }
            @{ Name = 'Ordinary explicit NSG'; Subnet = 'workload'; Explicit = 'operator-nsg'; Nsgs = $true; Expected = 'operator-nsg' }
            @{ Name = 'Ordinary NSGs disabled'; Subnet = 'workload'; Explicit = ''; Nsgs = $false; Expected = '' }
        )) {
            $selected = if ($case.Explicit) { $case.Explicit }
            elseif ($case.Nsgs -and $case.Subnet -cnotin $excluded) { 'generic-nsg' }
            else { '' }
            Test-Equal "#168 $($case.Name)" $selected $case.Expected
        }
    }
    $subnetResources = @($subnetChild.properties.template.resources)
    Test-Equal 'Child template contains only one subnet resource' $subnetResources.Count 1
    if ($subnetResources.Count -eq 1) {
        $resource = $subnetResources[0]
        Test-Equal 'Child resource is a subnet PUT, not a VNet collection replacement' `
            @($resource.type, $resource.apiVersion, $resource.name) @('Microsoft.Network/virtualNetworks/subnets', '2024-07-01', "[parameters('name')]")
        $subnetProperties = [ordered]@{
            addressPrefix = "[if(variables('gatewayAttachmentsAreSafe'), parameters('addressPrefix'), fail('GatewaySubnet must not have an NSG, route table or delegation.'))]"
            delegations = "[parameters('delegations')]"
            serviceEndpoints = "[parameters('serviceEndpoints')]"
            networkSecurityGroup = "[if(empty(parameters('networkSecurityGroupId')), null(), createObject('id', parameters('networkSecurityGroupId')))]"
            routeTable = "[if(empty(parameters('routeTableId')), null(), createObject('id', parameters('routeTableId')))]"
            natGateway = "[if(empty(parameters('natGatewayId')), null(), createObject('id', parameters('natGatewayId')))]"
        }
        Test-Set 'Child subnet property surface unchanged' $resource.properties.PSObject.Properties.Name @($subnetProperties.Keys)
        foreach ($entry in $subnetProperties.GetEnumerator()) {
            Test-Equal "Child subnet $($entry.Key) forwarding" $resource.properties.($entry.Key) $entry.Value
        }
        Test-Equal 'Reserved GatewaySubnet guard rejects NSG, route table and delegation attachments before PUT' `
            $subnetChild.properties.template.variables.gatewayAttachmentsAreSafe `
            "[or(not(equals(last(split(parameters('name'), '/')), 'GatewaySubnet')), and(and(empty(parameters('networkSecurityGroupId')), empty(parameters('routeTableId'))), empty(parameters('delegations'))))]"
    }
}
catch {
    Add-Failure "Unable to complete subnet contract: $($_.Exception.Message)"
}
finally {
    Remove-Item -LiteralPath $compiledFile -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    Write-Host "`n$($failures.Count) ACR Task agent pool subnet contract check(s) failed." -ForegroundColor Red
    exit 1
}

Write-Host "`nACR Task agent pool subnet contract checks passed (offline evidence only)." -ForegroundColor Green
exit 0
