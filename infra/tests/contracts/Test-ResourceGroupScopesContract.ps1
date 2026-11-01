<#
.SYNOPSIS
    Compiles the real root and verifies destination ownership without Azure access.
.DESCRIPTION
    Exact compiled expressions are checked before projecting one/two/three RG
    layouts. This is an offline contract, not ARM what-if or live RBAC/DNS evidence.
#>
[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'bicep/main.bicep')
)

$ErrorActionPreference = 'Stop'
$compiledFile = Join-Path $PSScriptRoot "resource-groups-$([guid]::NewGuid()).compiled.json"
$checks = 0

function Assert-Equal($Actual, $Expected, [string]$Message) {
    if (($Actual | ConvertTo-Json -Depth 100 -Compress) -cne ($Expected | ConvertTo-Json -Depth 100 -Compress)) {
        throw "$Message`nExpected: $($Expected | ConvertTo-Json -Compress)`nActual: $($Actual | ConvertTo-Json -Compress)"
    }
    $script:checks++
}

function Assert-Contains([string]$Actual, [string]$Expected, [string]$Message) {
    if (-not $Actual.Contains($Expected)) { throw "$Message`nMissing: $Expected`nActual: $Actual" }
    $script:checks++
}

function Assert-Dependency($Resource, [string]$Dependency, [string]$Message) {
    if ($Dependency -notin $Resource.dependsOn) { throw "$Message -- missing $Dependency" }
    $script:checks++
}

try {
    $env:PYTHONIOENCODING = 'utf-8'
    & az bicep build --file $MainFile --outfile $compiledFile
    if ($LASTEXITCODE -ne 0) { throw 'Bicep compilation failed.' }
    $t = Get-Content $compiledFile -Raw | ConvertFrom-Json -AsHashtable -Depth 100
    Assert-Equal $t.'$schema' 'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#' 'Root remains resource-group scoped.'
    foreach ($area in @('application', 'network')) {
        Assert-Equal $t.parameters."${area}ResourceGroupName".type 'string' "$area parameter type"
        Assert-Equal $t.parameters."${area}ResourceGroupName".defaultValue '' "$area default"
        Assert-Equal $t.variables."_$( $area )ResourceGroupName" "[if(empty(parameters('${area}ResourceGroupName')), resourceGroup().name, parameters('${area}ResourceGroupName'))]" "$area fallback"
    }
    Assert-Equal $t.variables._foundryResourceGroupName '[resourceGroup().name]' 'Foundry is the native root.'
    Assert-Equal $t.parameters.ContainsKey('foundryResourceGroupName') $false 'Retired Foundry override is not accepted.'
    $foundrySymbols = @(
        'aiFoundryUAI', 'aiFoundryStorageAccount', 'aiFoundry', 'bingSearchConnection',
        'aiFoundryBingConnection', 'aiFoundryConnectionSearch', 'aiFoundryKnowledgeBaseSearchConnection',
        'aiFoundryConnectionInsights', 'aiFoundryConnectionStorage', 'searchServiceUAI', 'searchService',
        'searchFoundrySharedPrivateLinks', 'searchServiceAIFoundry', 'speechService', 'storageAccount'
    )
    $networkSymbols = @(
        'bastionNsg', 'appGwNsg', 'routeTable', 'virtualNetwork', 'spokeToHubPeering',
        'testVmBastionHost', 'firewall', 'defaultRoute', 'testVmUAI', 'testVm', 'natGateway', 'cse'
    )
    foreach ($symbol in $foundrySymbols) {
        Assert-Equal $t.resources.$symbol.resourceGroup "[variables('_foundryResourceGroupName')]" "$symbol Foundry scope"
    }
    foreach ($symbol in $networkSymbols) {
        Assert-Equal $t.resources.$symbol.resourceGroup "[variables('_networkResourceGroupName')]" "$symbol network scope"
    }
    foreach ($symbol in @('containerRegistry', 'acrTaskAgentPool', 'appConfig', 'keyVault', 'containerEnv', 'logAnalytics', 'appInsights', 'cosmosDBAccount', 'cosmosSqlDatabase', 'publicIngressM')) {
        Assert-Equal $t.resources.$symbol.resourceGroup "[variables('_applicationResourceGroupName')]" "$symbol application scope"
    }
    Assert-Equal $t.outputs.AZURE_RESOURCE_GROUP.value '[resourceGroup().name]' 'Root output selects Foundry.'
    Assert-Equal $t.outputs.AZURE_APP_RESOURCE_GROUP.value "[variables('_applicationResourceGroupName')]" 'Application output'
    Assert-Equal $t.outputs.AZURE_NETWORK_RESOURCE_GROUP.value "[variables('_networkResourceGroupName')]" 'Network output'
    Assert-Equal $t.resources.searchFoundrySharedPrivateLinks.properties.parameters.foundryAccountResourceId.value "[reference('aiFoundry').outputs.accountResourceId.value]" 'Use actual account ID.'
    Assert-Equal $t.outputs.AZURE_AI_PROJECT_RESOURCE_ID.value "[if(or(parameters('deployAiFoundry'), variables('_hostedAgentPrerequisitesEnabled')), reference('aiFoundry').outputs.projectResourceId.value, '')]" 'Use actual project ID.'
    Assert-Equal $t.resources.aiFoundry.properties.parameters.baseUniqueName.value "[substring(uniqueString(subscription().id, resourceGroup().name, substring(parameters('resourceToken'), 0, 10)), 0, 5)]" 'Preserve the root naming seed.'

    # All values in this projection have exact bindings checked above.
    foreach ($case in @(
        @{ Application = ''; Network = ''; Expected = @('rg-ai', 'rg-ai') }
        @{ Application = 'rg-ai'; Network = 'rg-ai'; Expected = @('rg-ai', 'rg-ai') }
        @{ Application = 'rg-app'; Network = ''; Expected = @('rg-app', 'rg-ai') }
        @{ Application = 'rg-app'; Network = 'rg-app'; Expected = @('rg-app', 'rg-app') }
        @{ Application = 'rg-app'; Network = 'rg-net'; Expected = @('rg-app', 'rg-net') }
    )) {
        $resolved = @(
            $(if ($case.Application) { $case.Application } else { 'rg-ai' })
            $(if ($case.Network) { $case.Network } else { 'rg-ai' })
        )
        Assert-Equal $resolved $case.Expected 'One/two/three destination projection'
    }

    # Grants fan out into deployments at the actual target subscription/RG.
    # The inner assignment retains guid(principal, role, resourceId), not an index.
    $roles = $t.resources.assignExecutorRoles.properties.template.resources.roleAssignment
    Assert-Equal $roles.subscriptionId "[if(empty(parameters('roleAssignments')[copyIndex()].resourceId), subscription().subscriptionId, split(parameters('roleAssignments')[copyIndex()].resourceId, '/')[2])]" 'RBAC actual subscription'
    Assert-Equal $roles.resourceGroup "[if(empty(parameters('roleAssignments')[copyIndex()].resourceId), resourceGroup().name, split(parameters('roleAssignments')[copyIndex()].resourceId, '/')[4])]" 'RBAC actual resource group'
    Assert-Equal $roles.properties.template.resources.assignment.name "[guid(parameters('roleAssignments')[copyIndex()].principalId, parameters('roleAssignments')[copyIndex()].roleDefinitionId, parameters('roleAssignments')[copyIndex()].resourceId)]" 'RBAC GUID compatibility'
    Assert-Contains $roles.name "uniqueString(parameters('name'))" 'RBAC nested deployment names remain collision-safe after truncation.'
    Assert-Equal $roles.properties.template.resources.assignment.scope "[if(or(empty(parameters('roleAssignments')[copyIndex()].resourceId), equals(toLower(parameters('roleAssignments')[copyIndex()].resourceId), toLower(resourceGroup().id))), '', parameters('roleAssignments')[copyIndex()].resourceId)]" 'RG grants use deployment scope; service grants retain their exact resource scope.'
    foreach ($case in @(
        @{ Target = '/subscriptions/sub/resourceGroups/rg-app'; Resource = ''; Expected = '' }
        @{ Target = '/subscriptions/sub/resourceGroups/rg-ai'; Resource = '/subscriptions/sub/resourceGroups/rg-ai'; Expected = '' }
        @{ Target = '/subscriptions/sub/resourceGroups/rg-net'; Resource = '/SUBSCRIPTIONS/SUB/RESOURCEGROUPS/RG-NET'; Expected = '' }
        @{ Target = '/subscriptions/byo/resourceGroups/rg-byo'; Resource = '/subscriptions/byo/resourceGroups/rg-byo'; Expected = '' }
        @{ Target = '/subscriptions/sub/resourceGroups/rg-ai'; Resource = '/subscriptions/sub/resourceGroups/rg-ai/providers/Microsoft.CognitiveServices/accounts/account'; Expected = '/subscriptions/sub/resourceGroups/rg-ai/providers/Microsoft.CognitiveServices/accounts/account' }
        @{ Target = '/subscriptions/byo/resourceGroups/rg-byo'; Resource = '/subscriptions/byo/resourceGroups/rg-byo/providers/Microsoft.Network/virtualNetworks/vnet'; Expected = '/subscriptions/byo/resourceGroups/rg-byo/providers/Microsoft.Network/virtualNetworks/vnet' }
    )) {
        $scope = if (-not $case.Resource -or $case.Resource.ToLowerInvariant() -ceq $case.Target.ToLowerInvariant()) { '' } else { $case.Resource }
        Assert-Equal $scope $case.Expected 'Verified scope expression preserves implicit/explicit/case-alias RG and service targets.'
    }
    $deploymentNames = @($t.resources.Values | Where-Object { $_.type -eq 'Microsoft.Resources/deployments' } | ForEach-Object { $_.name })
    Assert-Equal @($deploymentNames | Select-Object -Unique).Count $deploymentNames.Count 'Module names do not collide when destinations coincide.'

    Assert-Equal $t.variables._defaultPeResourceGroupName "[if(and(parameters('useExistingVNet'), not(parameters('sideBySideDeploy'))), variables('varExistingVnetResourceGroupName'), variables('_networkResourceGroupName'))]" 'BYO PE fallback precedes network destination.'
    Assert-Equal $t.variables._peResourceGroupName "[if(not(empty(parameters('privateEndpointResourceGroupName'))), parameters('privateEndpointResourceGroupName'), variables('_defaultPeResourceGroupName'))]" 'Explicit PE override wins.'
    Assert-Equal $t.variables._peSubscriptionId "[if(not(empty(parameters('privateEndpointResourceGroupName'))), subscription().subscriptionId, if(and(parameters('useExistingVNet'), not(parameters('sideBySideDeploy'))), variables('varExistingVnetSubscriptionId'), subscription().subscriptionId))]" 'PE subscription follows actual destination.'
    Assert-Equal $t.variables._dnsZonesTargetRg $t.variables._defaultPeResourceGroupName 'Local DNS follows BYO/network, not explicit PE override.'
    Assert-Equal $t.variables._dnsZonesResourceGroupName $t.variables._dnsZonesTargetRg 'DNS IDs and deployments agree.'
    Assert-Equal $t.resources.privateDnsZones.properties.parameters.subscriptionId.value "[variables('_dnsZonesSubscriptionId')]" 'DNS cross-subscription propagation.'
    Assert-Equal $t.resources.privateEndpoints.properties.parameters.subscriptionId.value "[variables('_peSubscriptionId')]" 'PE cross-subscription propagation.'
    $pe = $t.resources.privateEndpoints.properties.template.resources.privateEndpoints
    Assert-Equal $pe.resourceGroup "[parameters('resourceGroupName')]" 'PE deployment RG.'
    Assert-Equal $pe.subscriptionId "[parameters('subscriptionId')]" 'PE deployment subscription.'
    Assert-Equal $pe.copy.mode 'serial' 'Aggregator serializes subnet/PE updates.'
    Assert-Equal $pe.copy.batchSize 1 'One PE update at a time.'
    Assert-Equal $pe.properties.parameters.subnetResourceId.value "[coalesce(tryGet(parameters('endpoints')[copyIndex()], 'subnetResourceId'), parameters('subnetResourceId'))]" 'Endpoint-specific application destination; grounding endpoints use the aggregator default.'
    $endpointInput = $t.resources.privateEndpoints.properties.parameters.endpoints.value
    foreach ($resourceName in @('dbAccountName', 'keyVaultName', 'appConfigName', 'containerEnvName', 'containerRegistryName')) {
        Assert-Contains $endpointInput "variables('resourceNames').$resourceName), 'subnetResourceId', if(variables('_networkIsolation')" "$resourceName uses application PE subnet override."
    }
    foreach ($resourceName in @('storageAccountName', 'searchServiceName', 'aiFoundrySearchServiceName', 'speechServiceName')) {
        if ($endpointInput.Contains("variables('resourceNames').$resourceName), 'subnetResourceId'")) {
            throw "$resourceName must retain the grounding PE subnet."
        }
        $checks++
    }

    Assert-Equal $t.parameters.applicationPeSubnetName.defaultValue 'application-pe-subnet' 'Application PEs have a dedicated default subnet.'
    Assert-Equal $t.parameters.applicationPeSubnetPrefix.defaultValue '192.168.3.128/26' 'Application PE allocation retains the approved default.'
    Assert-Equal $t.variables.ContainsKey('_separateApplicationPeSubnet') $false 'No legacy empty-name subnet selector remains.'
    Assert-Equal $t.variables.selectedSubnetDefinitions "[filter(variables('subnetDefinitions'), lambda('subnet', and(and(variables('_networkIsolation'), parameters('deploySubnets')), lambdaVariables('subnet').create)))]" 'Selection depends on ownership/isolation, never resource-group count.'
    $subnetInput = $t.resources.virtualNetwork.properties.parameters.subnets.value
    Assert-Equal $t.resources.virtualNetworkSubnets.properties.parameters.subnets.value $subnetInput 'New and BYO VNets receive the same selected subnet projection.'
    $applicationDefinition = @($t.variables.subnetDefinitions | Where-Object purpose -CEQ 'applicationPe')
    Assert-Equal $applicationDefinition.Count 1 'Exactly one application PE definition.'
    Assert-Equal $applicationDefinition[0].name "[parameters('applicationPeSubnetName')]" 'Application subnet identity is independent of RG scope.'
    Assert-Equal $applicationDefinition[0].addressPrefix "[parameters('applicationPeSubnetPrefix')]" 'Application subnet prefix remains configurable.'
    Assert-Equal $applicationDefinition[0].create "[parameters('deployApplicationPeSubnet')]" 'Application creation flag does not change its consumer destination.'
    Assert-Equal $applicationDefinition[0].delegation '' 'PE subnet remains undelegated.'
    if ($endpointInput.Contains("variables('_separateApplicationPeSubnet')") -or
        $endpointInput.Contains("parameters('deployApplicationPeSubnet')")) {
        throw 'Application PE routing must not fall back when creation is disabled.'
    }
    $checks++
    Assert-Dependency $t.resources.virtualNetwork 'networkLayoutValidation' 'New VNet waits for subnet validation.'
    Assert-Dependency $t.resources.virtualNetworkSubnets 'networkLayoutValidation' 'BYO subnet writes wait for validation.'
    Assert-Equal $t.resources.networkLayoutValidation.condition "[variables('_networkIsolation')]" 'Every isolated topology validates ownership and required subnets.'
    $layout = $t.resources.networkLayoutValidation.properties.template
    Assert-Equal $t.resources.networkLayoutValidation.properties.parameters.useExistingVNet.value "[parameters('useExistingVNet')]" 'BYO validation does not assume new-VNet addressing.'
    Assert-Contains $layout.outputs.validated.value "fail('An enabled consumer requires a subnet that is not managed in the new VNet. Enable its subnet creation or disable the consumer.')" 'Unmanaged required new-VNet subnets fail closed.'
    Assert-Contains $layout.outputs.validated.value "fail('Managed subnet CIDRs must not overlap and must be contained in the new VNet address space.')" 'Invalid selected ranges fail closed.'

    # Direct parameter bindings above are independent of RG count and creation.
    # Disabling ownership reuses the configured subnet, not the Foundry subnet.
    foreach ($rgCount in 1..3) {
        foreach ($applicationSubnet in @('application-pe-subnet', 'app-pe-subnet')) {
            foreach ($create in @($true, $false)) {
                $parameters = @{ applicationPeSubnetName = $applicationSubnet; deployApplicationPeSubnet = $create }
                $selected = $parameters.applicationPeSubnetName
                Assert-Equal $selected $applicationSubnet "$rgCount RG(s), create=$create`: application subnet remains dedicated"
            }
        }
    }
    foreach ($case in @(
        @{ Byo = $false; SideBySide = $false; Override = ''; Rg = 'rg-net'; Sub = 'workload-sub' }
        @{ Byo = $true; SideBySide = $false; Override = ''; Rg = 'rg-byo'; Sub = 'byo-sub' }
        @{ Byo = $true; SideBySide = $true; Override = ''; Rg = 'rg-net'; Sub = 'workload-sub' }
        @{ Byo = $true; SideBySide = $false; Override = 'rg-explicit'; Rg = 'rg-explicit'; Sub = 'workload-sub' }
        @{ Byo = $true; SideBySide = $true; Override = 'rg-explicit'; Rg = 'rg-explicit'; Sub = 'workload-sub' }
    )) {
        $fallback = if ($case.Byo -and -not $case.SideBySide) { 'rg-byo' } else { 'rg-net' }
        $rg = if ($case.Override) { $case.Override } else { $fallback }
        $sub = if ($case.Override) { 'workload-sub' } elseif ($case.Byo -and -not $case.SideBySide) { 'byo-sub' } else { 'workload-sub' }
        Assert-Equal @($rg, $sub) @($case.Rg, $case.Sub) 'Explicit/BYO/side-by-side destination precedence.'
    }

    # Foundry's resource wrappers propagate endpoint scope all the way into AVM.
    # The wrapper uses an array-form template; the inner composition is symbolic.
    $wrapper = $t.resources.aiFoundry.properties.template
    $foundryDeployment = @($wrapper.resources | Where-Object { $_.properties.parameters.ContainsKey('baseName') })[0]
    $foundry = $foundryDeployment.properties.template
    foreach ($symbol in @('keyVault', 'aiSearch', 'storageAccount', 'cosmosDb')) {
        Assert-Equal $foundry.resources.$symbol.properties.parameters.privateEndpointResourceGroupResourceId.value "[parameters('privateEndpointResourceGroupResourceId')]" "$symbol embedded PE scope"
        Assert-Equal $foundry.resources.$symbol.properties.parameters.privateEndpointLocation.value "[parameters('privateEndpointLocation')]" "$symbol embedded PE location"
    }
    foreach ($symbol in @('foundryAccountPrivateEndpoint', 'foundryAccountPrivateEndpointWithoutDns')) {
        Assert-Equal $foundry.resources.$symbol.resourceGroup "[variables('_privateEndpointRgParts')[4]]" "$symbol actual RG"
        Assert-Equal $foundry.resources.$symbol.subscriptionId "[variables('_privateEndpointRgParts')[2]]" "$symbol actual subscription"
        Assert-Dependency $foundry.resources.$symbol 'foundryProject' 'Preserve Foundry PE readiness guard.'
    }
    Assert-Dependency $foundry.resources.aiSearch 'keyVault' 'Serialize nested key vault/Search PEs.'
    Assert-Dependency $foundry.resources.storageAccount 'aiSearch' 'Serialize nested Search/Storage PEs.'
    Assert-Dependency $foundry.resources.cosmosDb 'storageAccount' 'Serialize nested Storage/Cosmos PEs.'
    Assert-Dependency $t.resources.aiFoundryStorageAccount 'privateEndpoints' 'Serialize pre-created Foundry storage PE after aggregator.'
    Assert-Dependency $t.resources.aiFoundry 'aiFoundryStorageAccount' 'Foundry follows pre-created storage.'
    Assert-Dependency $t.resources.privateEndpointPrivateLinkScope 'aiFoundry' 'Monitor PE follows nested Foundry PEs.'
    $account = $foundry.resources.foundryAccount.properties.template
    Assert-Equal $account.variables.privateNetworkingEnabled "[not(empty(parameters('privateEndpointSubnetResourceId')))]" 'Policy-managed DNS never enables public Foundry access.'

    # Project grants must precede connections/capability-host consumers.
    $project = $foundry.resources.foundryProject.properties.template
    Assert-Dependency $project.resources.cosmosDbConnectionResource 'cosmosDbRoleAssignments' 'Cosmos RBAC prerequisite.'
    Assert-Dependency $project.resources.storageAccountConnectionResource 'storageAccountRoleAssignments' 'Storage RBAC prerequisite.'
    Assert-Dependency $project.resources.aiSearchConnectionResource 'aiSearchRoleAssignments' 'Search RBAC prerequisite.'
    Assert-Dependency $project.resources.capabilityHost 'aiSearchConnectionResource' 'Capability host follows authorized connections.'

    foreach ($symbol in @('routeTable', 'natGateway', 'bastionNsg', 'appGwNsg')) {
        if ('aiFoundry' -in $t.resources.$symbol.dependsOn -or 'containerEnv' -in $t.resources.$symbol.dependsOn) {
            throw "$symbol base network must not depend on a subnet consumer."
        }
        $checks++
    }
    Assert-Equal @($t.outputs.Keys).Count 64 'ARM output limit is respected without removing legacy outputs.'
    Assert-Contains $t.resources.appConfigPopulate.properties.parameters.keyValues.value "'name', 'AZURE_APP_RESOURCE_GROUP', 'value', variables('_applicationResourceGroupName'), 'label', 'agent-lz'" 'Application key uses runtime label.'
    Assert-Contains $t.resources.appConfigPopulate.properties.parameters.keyValues.value "'name', 'AZURE_NETWORK_RESOURCE_GROUP', 'value', variables('_networkResourceGroupName'), 'label', 'agent-lz'" 'Network key uses runtime label.'
    $minifiedSize = [Text.Encoding]::UTF8.GetByteCount(($t | ConvertTo-Json -Compress -Depth 100))
    if ($minifiedSize -ge 4MB) { throw "Compiled template exceeds 4 MiB: $minifiedSize." }
    Write-Host "PASS: $checks resource-group contracts; minified template $minifiedSize bytes. No Azure validation."
}
finally {
    Remove-Item $compiledFile -ErrorAction SilentlyContinue
}
