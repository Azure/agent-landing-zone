<#
.SYNOPSIS
    Tests the solution Storage access input contract for issue #160 (S1-S9).

.DESCRIPTION
    Requires PowerShell 7 and Azure CLI Bicep 0.42.1, not the standalone CLI.
    Compiles the actual root once, checks its exported/imported types (including
    compiled provenance) and native parameter defaults, and follows exact
    root -> AVM 0.26.2 -> Storage bindings.
    A bounded resolver accepts only the pinned shallowMerge shape; it does not
    evaluate arbitrary ARM, discover resources, read credentials, or deploy.

    Positive and negative .bicepparam fixtures use the actual -MainFile. Scalar
    negatives are grouped across independent parameters; malformed rule entries
    share an array, with a required type error at EACH entry. Schema and exact
    binding checks let the eight bypass values and network matrix reuse one
    compiled template instead of rebuilding main for every matrix row.

    Bicep 0.42.1 treats top-level null assignments to defaulted parameters as
    absent for validation, but emits the null assignments in parameter JSON.
    An explicit-null positive fixture and bounded default resolution cover this
    compiler behavior; nested rule nulls remain invalid. This is not live ARM
    evidence and does not add permissive product coercion or nullable schemas.

    Safety hashes are from validated e3d94e5 (unchanged Bicep at c8ae418), compiled
    with 0.42.1. They normalize object key order, line endings and _generator,
    never resource properties. Only the three intended solution bindings are
    normalized to their old defaults. Other resources, variables and outputs,
    including auxiliary Storage, RBAC and private endpoints, remain protected.
    The ACR pool is also protected: only its original dependency list or the
    precise #159 virtualNetworkSubnets edge is accepted. Per-resource hashes
    identify unexpected changes without printing parameter values. Do not
    regenerate these hashes merely to obtain a passing test.
    The subnet guard also permits only #168's exact AzureBastionSubnet addition
    to generic-NSG exclusions; other nested properties remain fingerprinted.
    Historical foundation metadata is checked against its explicit fixture first.
    Only tag and ailz_tag on the pinned $fxv#0 object behind _manifest are then
    normalized to v2.6.1 for the historical fingerprint. The actual compiled
    umbrella manifest is checked before projection by the scoped normalizer.

    Uses a unique temporary directory beside MainFile for portable relative
    'using' paths (also across Windows drives). Deletes only its own files.
    No fixture uses live IDs or a usable password. No parameter values are logged.
    S4 here proves declared forwarding, NOT two-deployment persistence. Azure
    Policy, authentication and Defender scanning require separate live evidence.

.EXAMPLE
    pwsh -NoProfile -File infra/tests/contracts/Test-SolutionStorageAccessContract.ps1
.EXAMPLE
    pwsh -NoProfile -File infra/tests/contracts/Test-SolutionStorageAccessContract.ps1 -MainFile ./infra/bicep/main.bicep
#>

[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'bicep/main.bicep')
)

$ErrorActionPreference = 'Stop'
$exitCode = 0
$createdFiles = [System.Collections.Generic.List[string]]::new()
$createdDirectory = $false
$oldPythonEncoding = $env:PYTHONIOENCODING
$inputNames = @(
    'storageAccountNetworkAclsBypass'
    'storageAccountResourceAccessRules'
    'storageAccountAllowSharedKeyAccess'
)
$bypassValues = @(
    'None', 'AzureServices', 'Logging', 'Metrics',
    'AzureServices, Logging', 'AzureServices, Metrics',
    'AzureServices, Logging, Metrics', 'Logging, Metrics'
)

function Assert-Contract {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "CONTRACT: $Message" }
}

function ConvertTo-Canonical {
    param([AllowNull()]$Value, [switch]$PreserveGeneratorMetadata)
    if ($null -eq $Value) { return $null }
    if ($Value -is [string]) { return $Value.Replace("`r`n", "`n").Replace("`r", "`n") }
    if ($Value -is [System.Collections.IDictionary]) {
        $result = [ordered]@{}
        [string[]]$keys = @($Value.Keys)
        [Array]::Sort($keys, [StringComparer]::Ordinal)
        foreach ($key in $keys) {
            if ($key -ceq '_generator' -and -not $PreserveGeneratorMetadata) { continue }
            $result[$key] = ConvertTo-Canonical $Value[$key] -PreserveGeneratorMetadata:($PreserveGeneratorMetadata -or $key -cin @('_manifest', '$fxv#0'))
        }
        return $result
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        $result = [System.Collections.Generic.List[object]]::new()
        foreach ($item in $Value) { $result.Add((ConvertTo-Canonical $item -PreserveGeneratorMetadata:$PreserveGeneratorMetadata)) }
        return ,$result.ToArray()
    }
    return $Value
}

function Assert-Equal {
    param([string]$Message, [AllowNull()]$Actual, [AllowNull()]$Expected)
    $a = ConvertTo-Json -InputObject (ConvertTo-Canonical $Actual) -Depth 100 -Compress
    $e = ConvertTo-Json -InputObject (ConvertTo-Canonical $Expected) -Depth 100 -Compress
    Assert-Contract ($a -ceq $e) $Message
}

function Get-ContractHash {
    param($Value)
    $json = ConvertTo-Json -InputObject (ConvertTo-Canonical $Value) -Depth 100 -Compress
    return [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($json))
    ).ToLowerInvariant()
}

function Test-UnchangedGraph {
    param($Template, $OriginalSolution, $Manifest)
    # These are the SAME e3d94e5 objects as the original aggregate fingerprint,
    # now individually fingerprinted for actionable diagnostics. No new graph
    # baseline or mutation exemption is introduced. Keep all nested properties,
    # including unused definitions (which exposed the wildcard-import issue).
    $resourceHashes = [ordered]@{}
    foreach ($line in (@'
acrTaskAgentPool 59455d8d09e7a4c34414e59c961730a3eedab94bdee765dd984205f750e03531
aiFoundry d7ca9b33a4688f3187dd3f1ad5a7422d7b0e49da4f19b2b8d62d491644cb016c
aiFoundryBingConnection 038638cd824ffa57763e9f40e54571d3b2f0cb38975085596d1eed44de1930a1
aiFoundryConnectionInsights 024035f738879db794f64c89ae7ba1bbe34e918fca67fc4f4daf60d504a53369
aiFoundryConnectionSearch 6e29e297e25352fe55343b63991ff6d2d709cbf73457a448978b0cb03f9aa134
aiFoundryConnectionStorage 8157c8aed1f5fd8541f8a6ed7931224ca586abe894245a28496a46de3955e885
aiFoundryKnowledgeBaseSearchConnection 05e424c8de7c4c068d274e347b6a31b70492e3c946d59aed83d08c36cf2a4d9a
aiFoundryStorageAccount 54aedc61a7ecef8a3630d0792baa3bc3cca244c36d110e49b860b85ea67924a5
aiFoundryUAI 312fcfb8afa4d4bc8c411a3154de3519a95729cf6644d1965eb8107c60e88981
appConfig c83d5f5e51090b04c1d586020551533a4e4ccb598f910cd840b4044130d7e1d7
appConfigDataOwner 4bf82e6d508a3c71f3b13c5d2a876491c77c416a043917a1ab02eb7176cc5193
appConfigKeyVaultPopulate 9bd9565aadc0e54d5e4f5ae9a813ed55e671e604b19446e1fc9ae29209197dae
appConfigPopulate d583386ad55dc9b3bb30cc07e1deaa7292a71cff27ae650b563b41ab2a99d21c
appGwNsg 6bdaea95f79c6450cf19fa509c749e5575ac8f5d0ba8f93212aed79bb96f4484
appInsights 137722220517c39dc6101a8c7ca11c1b3f17bc90e72ac59a627de506544a123c
assignContainerAppRoles c39e35506de9d1853d8ca02cc3cbd032e4db5473de5e03b8e533f88d2922a1e7
assignCosmosDBCosmosDbBuiltInDataContributorContainerApps 19f5d912bd55cebdf393a45629b118b6bb8b7a931704b0a46422984ff4727a29
assignCosmosDBCosmosDbBuiltInDataContributorExecutor 302a178af43527acc424da88bf38fb9c8fd4302263aaaaf0efa55caf529f67b9
assignCosmosDBCosmosDbBuiltInDataContributorTestVm 57664b1903ea95431d8ff9c2b2599b148b0c21787b10ef82a8063e7ddf29fed3
assignCrossServiceRoles a717091dc9594c872b0f4af45ebe55fefa16e0ff41dc32494eb3f2238c7b382b
assignExecutorRoles d39efd52696e94fde6c43873d33186b864b906ecd6e1414224a8e05522ef7b29
assignTestVmRoles bb0cc459f41673648d7776a1447d26ea0855156dd20f04715dd03192c32a1d2b
bastionNsg 6f17e605f7a848c1abeb60f598128abb106ef316377990c6dfa79500cb5a8bc9
bastionPublicIp f6daa47c433385322e5edd202ccf961edb595f9bc52b62f7eead4bce597afcbb
bingSearchConnection c05901e0b66ed1656ec5ccd27061cc3560c87353a90108aecaca344f412847bd
componentFlagValidation 6747c3531b99d80bb2a230ea48df2d5ea36c1993a60cad78b4288e05e191244d
containerApps 52b1d765e1ee523b2749e323f631b85f06d3d7263dc486690adae1fdc02d2f85
containerAppsSettings 2e4d5a57d38201d7b96fd453b0a809ada9ea4df89441ab4756562bd212c7443c
containerAppsUAI 1d9d04daee57ad2e1eb5f3f5a91c73b3907c65a2be760d82c8207374f9205485
containerEnv cb2ca6cf980f3bdf445199be3657081d3b9d7ed1ffe74a69bd12ff4c794295cb
containerEnvUAI 15be0daf3205606933607687273cb0d36ca03dfaa47706253ab37188b5011c19
containerRegistry 510b4e95c927e052a52b56644e93a4f8f1e431196e6829cd08e5d9d7a0d1f2bb
containerRegistryUAI ddae0aee0201c2b1c818fa27c23ad15b4615ae501fdbe8f1a4f9a7ef0731fdf3
cosmosConfigKeyVaultPopulate 3633def927e655e4aa677e52bce0772d2bfb0074e590f53017a05b3788bc3f99
cosmosDBAccount b026fb96fb53c4bda90444b569d86d7e63ba0c5bd982f082f8f20fac4f1ddb9f
cosmosSqlDatabase c01f8c78d7e75593248cc76761b764efbfad6692daeaf5a4ea97fd623dd64e17
cosmosUAI 7d50ef21b1ba89a9c5b380d6588be97d117f4ebdb6b300d65d88436e7d7fae4f
cse 98cabfe4efc592a5eb3df6a4f6fddd9d19d4654de317630bc4ad27ead7003aa7
defaultRoute c5631093d241ceb3d5187dcb18b02baad89715b52f807725a8d3a904d8786b97
firewall c9533493913cf2f5272973e3e77ab327430f6bb69d5b23e19de420c17461acf3
keyVault 1cd398535b18dc6fed9a46cbbc7b3f6391fa5ae3d49e02f9f62a3f6e25587b12
logAnalytics 41e7b62a8b5661e1b88a048fd89990a346091f857723c3a1ebff35d714d6744c
natGateway 23c1ca0db5b5dbbb5a3a099305bd47ea344f7c6b7447fefd7c9ea6625ddafdc7
natPublicIp 5765a6d9b3b1d44b299eecefeb214976fc823d4297bd5b6d06ffd106d72ce4c8
privateDnsZones 1fc4434b1e228d4b42221bbfbdc5f371d8f335994c919e959e6ab7bb0965ef16
privateEndpointPrivateLinkScope e20fe2ba0e1be588163994521ddee1fc73da0c2e377b8b3e941af4ad769c6f05
privateEndpoints c4d397c2ff47e58fb3de23078086581fba8b1f6cfdd0fe3ee8abbfa22b94c148
privateLinkScope 76902e45e4bbaa2898d2abee18e56c4011434689d79e94432a08ee20e8e9f262
privateLinkScopedResources1 da5edb4ff0b131726f0a9981326c6c51c395414ae9c3c36ba646dfa362b980a4
privateLinkScopedResources2 536d9e321f5d86e7bc13a5d5ff8e5df52f2f0651510ea54cc5d77da43ce3799d
publicIngressM 5e7918645357bec5d11947a16438b6fae9a8779dd1116f8aa76e009109cb556c
routeTable fa606fa6fcbb47768288697b7237d514c3c02ab1008f679a7a9215423e731980
searchFoundrySharedPrivateLinks 60d13242bc5a4e0f9c413e76b81d6d6d7718323a7e61db65e89d3433c66648bf
searchService 7e4e319977c1938422cc3f9fff72eae1b95a89e2afda7e5c01f702afe9431dea
searchServiceAIFoundry 5ea0818c7b014a155f99e1e0e6fc0efee0cd2e782569fe28dc0a7128cdccb95e
searchServiceResource e7e2b5927566541bd28d16f83bdaedd59518116f6cf67edaa5b56d99209ecac8
searchServiceUAI 217a792277ef840502412537fdda132fab1f6e47742d22a708f5fa37cb7270cc
secret f5315872b2b7bdfea1cf66d73b7a2d2580ba7bdd871488c9b6142ad268708c7d
speechService c3b23481e88bdb6a61c6422fb4f0daae0f9adebc64b32b214135aad9c35975af
spokeToHubPeering bd3e01dbb3f8214b5c53bae4bf0871a461947e118b0ff19db6cd2f026af7c5e9
spokeVnetForPeering fcd6fcc0f6a8b51a6c4df73e5cba7133795b437e9decec754c22c380a7d15e00
storageAccount 1e92db4298ee93161fdac8ef4cd64ac6be1608b471870ef5f4747f619b4cf2e3
testVm f0eae7a939a3937f6e5f3e99d9b81d28471b678dec52654633cfbe52a64ab6a6
testVmBastionHost 04b4ad18b35da639c5cb2b544e14d587e70ba306d06b7d3b7f141d2e8484fa30
testVmUAI ecd19dda2465de72edd8ccdf2299126d25e3f8b32845d68be28c8eadeb509dcd
virtualNetwork 608b8c58afb110619363ebbae8e6e796f878758c18aa51ffa22f0e496bf1bf3a
virtualNetworkSubnets df346eb5b939add3fea49a9177b2a0a116b0e931a62e5d3ca7354a1f6241a976
'@ -split '\r?\n')) {
        $name, $hash = $line -split ' ', 2
        $resourceHashes[$name] = $hash
    }
    $added = @($Template.resources.Keys | Where-Object { -not $resourceHashes.Contains($_) })
    $missing = @($resourceHashes.Keys | Where-Object { -not $Template.resources.Contains($_) })
    Assert-Contract ($added.Count -eq 0 -and $missing.Count -eq 0) "Root resource membership changed; added [$($added -join ', ')], missing [$($missing -join ', ')]."

    $acr = $Template.resources.acrTaskAgentPool | ConvertTo-Json -Depth 100 | ConvertFrom-Json -AsHashtable -Depth 100
    $originalDependencies = @('containerRegistry', 'virtualNetwork')
    $acceptedDependencies = if (@($acr.dependsOn).Count -eq 3) {
        @('containerRegistry', 'virtualNetwork', 'virtualNetworkSubnets')
    }
    else { $originalDependencies }
    Assert-Equal 'resources.acrTaskAgentPool.dependsOn: only the exact original list or the single #159 virtualNetworkSubnets edge is permitted.' $acr.dependsOn $acceptedDependencies
    $acr.dependsOn = $originalDependencies
    $subnets = $Template.resources.virtualNetworkSubnets | ConvertTo-Json -Depth 100 | ConvertFrom-Json -AsHashtable -Depth 100
    $originalNsgExclusions = @('AzureFirewallSubnet', 'AppGatewaySubnet')
    $acceptedNsgExclusions = if (@($subnets.properties.template.variables.invalidNsgSubnets).Count -eq 3) {
        @('AzureFirewallSubnet', 'AppGatewaySubnet', 'AzureBastionSubnet')
    }
    else { $originalNsgExclusions }
    Assert-Equal 'resources.virtualNetworkSubnets: only the exact #168 reserved Bastion NSG exclusion is permitted.' `
        $subnets.properties.template.variables.invalidNsgSubnets $acceptedNsgExclusions
    $subnets.properties.template.variables.invalidNsgSubnets = $originalNsgExclusions
    $changed = [System.Collections.Generic.List[string]]::new()
    foreach ($name in $resourceHashes.Keys) {
        $resource = if ($name -ceq 'storageAccount') { $OriginalSolution }
        elseif ($name -ceq 'acrTaskAgentPool') { $acr }
        elseif ($name -ceq 'virtualNetworkSubnets') { $subnets }
        else { $Template.resources[$name] }
        if ((Get-ContractHash $resource) -cne $resourceHashes[$name]) { $changed.Add("resources.$name") }
    }
    $historicalManifest = Get-Content (Join-Path $PSScriptRoot 'fixtures/historical-foundation-manifest.json') -Raw | ConvertFrom-Json -AsHashtable
    Assert-Equal 'Historical foundation manifest must match the incorporated release fixture exactly.' `
        @{ _manifest = $Manifest } @{ _manifest = $historicalManifest }
    Assert-Equal 'Compiled _manifest must retain its exact compiler binding.' $Template.variables._manifest '[variables(''$fxv#0'')]'
    Assert-Equal 'Compiled _manifest must match the actual manifest before release normalization.' @{ _manifest = $Template.variables['$fxv#0'] } @{ _manifest = $Manifest }
    $variables = $Template.variables | ConvertTo-Json -Depth 100 | ConvertFrom-Json -AsHashtable -Depth 100
    $variables['$fxv#0'].tag = 'v2.6.1'
    $variables['$fxv#0'].ailz_tag = 'v2.6.1'
    if ((Get-ContractHash $variables) -cne 'd46fe765f8a6b5f30f73b8c0a66c1d06fa02475718205658c5a74ec805378906') { $changed.Add('root.variables') }
    if ((Get-ContractHash $Template.outputs) -cne '529fe5c247e2cf87232f0fbfee048317643f11b8d62b527c4b1247d8b4dc0d92') { $changed.Add('root.outputs') }
    Assert-Contract ($changed.Count -eq 0) "S3/S8 unexpected baseline change at [$($changed -join ', ')]. Nested properties/definitions remain protected; no resource is exempt."
}

function Get-Schema {
    param($Template, $Schema)
    Assert-Contract ($Schema -is [System.Collections.IDictionary]) 'Expected an ARM parameter/type schema.'
    if ($Schema.Contains('$ref')) {
        Assert-Contract ($Schema['$ref'] -cmatch '^#/definitions/([^/]+)$') 'Unsupported schema reference.'
        $definition = $Template.definitions[$Matches[1]]
        Assert-Contract ($definition -is [System.Collections.IDictionary]) 'Referenced type definition is missing.'
        Assert-Contract (-not $definition.Contains('$ref')) 'Unexpected chained type reference.'
        Assert-Contract (-not $Schema.nullable) 'Storage input/reference must not be nullable.'
        return $definition
    }
    return $Schema
}

function Get-ImportedStorageSchema {
    param($Template, $Schema, [string]$TypeName)
    Assert-Contract ($Schema -is [System.Collections.IDictionary]) "Missing root schema reference for $TypeName."
    $referencePattern = '^#/definitions/(?:_\d+\.)?' + [regex]::Escape($TypeName) + '$'
    Assert-Contract ($Schema['$ref'] -cmatch $referencePattern) "Root must reference the shared $TypeName definition."
    $definition = Get-Schema $Template $Schema
    Assert-Contract ($definition.metadata -is [System.Collections.IDictionary]) "$TypeName must retain compiler import provenance."
    $provenance = $definition.metadata['__bicep_imported_from!']
    Assert-Equal "$TypeName must originate in the focused Storage type file, not a duplicate local schema." $provenance.sourceTemplate 'constants/storage-types.bicep'
    return $definition
}

function Test-RuleSchema {
    param($Schema)
    Assert-Equal 'Rule type must be an object.' $Schema.type 'object'
    Assert-Equal 'Rule type must be sealed.' $Schema.additionalProperties $false
    Assert-Equal 'Rule fields must be exactly resourceId and tenantId.' @($Schema.properties.Keys | Sort-Object) @('resourceId', 'tenantId')
    Assert-Contract (-not $Schema.nullable) 'Rule objects must not be nullable.'
    foreach ($field in @('resourceId', 'tenantId')) {
        $property = $Schema.properties[$field]
        Assert-Equal "$field must be a string." $property.type 'string'
        Assert-Equal "$field must be nonempty." $property.minLength 1
        # In Bicep's ARM schema an optional property is emitted as nullable.
        Assert-Contract (-not $property.nullable) "$field must be required and non-null."
    }
}

function Get-PinnedStorageFields {
    param($Expression)
    Assert-Contract ($Expression -is [string]) 'Unsupported AVM Storage properties shape: expected shallowMerge expression.'
    # Full-expression equality by digest guards ALL branches, including the two
    # later merge objects, against overrides. Parsing below is just projection,
    # not an ARM interpreter or a token-presence assertion.
    Assert-Equal 'Unsupported AVM 0.26.2 Storage shallowMerge expression.' (Get-ContractHash $Expression) 'ed72e920542136e956b42336193cd7330c711e22560a1980a4d48db63f63ff23'
    $prefix = '[shallowMerge(createArray(createObject('
    $suffix = "), if(not(empty(parameters('azureFilesIdentityBasedAuthentication'))), createObject('azureFilesIdentityBasedAuthentication', parameters('azureFilesIdentityBasedAuthentication')), createObject()), if(not(equals(parameters('enableHierarchicalNamespace'), null())), createObject('isHnsEnabled', parameters('enableHierarchicalNamespace')), createObject())))]"
    Assert-Contract ($Expression.StartsWith($prefix) -and $Expression.EndsWith($suffix)) 'Unsupported shallowMerge envelope.'
    $body = $Expression.Substring($prefix.Length, $Expression.Length - $prefix.Length - $suffix.Length)
    $parts = [System.Collections.Generic.List[string]]::new()
    $depth = 0
    $quoted = $false
    $start = 0
    for ($i = 0; $i -lt $body.Length; $i++) {
        $character = $body[$i]
        if ($character -eq "'") {
            if ($quoted -and $i + 1 -lt $body.Length -and $body[$i + 1] -eq "'") { $i++; continue }
            $quoted = -not $quoted
        }
        elseif (-not $quoted) {
            if ($character -eq '(') { $depth++ }
            elseif ($character -eq ')') { $depth-- }
            elseif ($character -eq ',' -and $depth -eq 0) {
                $parts.Add($body.Substring($start, $i - $start).Trim())
                $start = $i + 1
            }
            Assert-Contract ($depth -ge 0) 'Unbalanced pinned expression.'
        }
    }
    Assert-Contract (-not $quoted -and $depth -eq 0) 'Unbalanced pinned expression.'
    $parts.Add($body.Substring($start).Trim())
    Assert-Contract ($parts.Count % 2 -eq 0) 'Unsupported createObject argument list.'
    $fields = [ordered]@{}
    for ($i = 0; $i -lt $parts.Count; $i += 2) {
        Assert-Contract ($parts[$i] -cmatch "^'([A-Za-z][A-Za-z0-9]*)'$") 'Unsupported Storage property name.'
        $key = $Matches[1]
        Assert-Contract (-not $fields.Contains($key)) 'Duplicate Storage property.'
        $fields[$key] = $parts[$i + 1]
    }
    return $fields
}

function Resolve-DirectBinding {
    param($Expression, [string]$ParameterName, $Inputs)
    Assert-Equal "Exact forwarding required for $ParameterName." $Expression "[parameters('$ParameterName')]"
    Assert-Contract ($Inputs.Contains($ParameterName)) "Missing controlled value for $ParameterName."
    return ,$Inputs[$ParameterName]
}

function Resolve-DefaultedRootInput {
    param($Template, [string]$ParameterName, $Assignments)
    # Bicep v0.42.1 SemanticModel parameter-file validation considers a top-level
    # NullType assignment absent. Only these defaulted ROOT inputs are resolved;
    # nested rule values are never visited or normalized.
    # https://github.com/Azure/bicep/blob/v0.42.1/src/Bicep.Core/Semantics/SemanticModel.cs
    if ($Assignments.Contains($ParameterName) -and $null -ne $Assignments[$ParameterName]) {
        return ,$Assignments[$ParameterName]
    }
    $definition = $Template.parameters[$ParameterName]
    Assert-Contract ($null -ne $definition -and $definition.Contains('defaultValue')) "Cannot resolve omitted/null $ParameterName without an actual root default."
    return ,$definition.defaultValue
}

function Resolve-StorageProfile {
    param($RootInputs, $ModuleParameters, $Fields)
    # Root expressions and the IP copy loop are checked exactly before entry.
    # Only native booleans and the table's string arrays are accepted here.
    Assert-Contract ($RootInputs.networkIsolation -is [bool]) 'Unsupported isolation input in controlled resolver.'
    Assert-Contract ($RootInputs.deployStorageAccount -is [bool]) 'Unsupported Storage gate input in controlled resolver.'
    $applyIpRules = $RootInputs.allowedIpRanges.Count -gt 0
    $pna = if (-not $RootInputs.networkIsolation -or $applyIpRules) { 'Enabled' } else { 'Disabled' }
    $ipRules = @($RootInputs.allowedIpRanges | ForEach-Object { @{ value = $_; action = 'Allow' } })
    $acls = $ModuleParameters.networkAcls.value
    $avmInputs = [ordered]@{
        allowSharedKeyAccess = Resolve-DirectBinding $ModuleParameters.allowSharedKeyAccess.value 'storageAccountAllowSharedKeyAccess' $RootInputs
        networkAcls = [ordered]@{
            bypass = Resolve-DirectBinding $acls.bypass 'storageAccountNetworkAclsBypass' $RootInputs
            resourceAccessRules = Resolve-DirectBinding $acls.resourceAccessRules 'storageAccountResourceAccessRules' $RootInputs
            virtualNetworkRules = $acls.virtualNetworkRules
            ipRules = $ipRules
            defaultAction = $(if ($applyIpRules) { 'Deny' } else { 'Allow' })
        }
        publicNetworkAccess = $pna
    }
    Assert-Equal 'AVM Shared Key forwarding must be direct.' $Fields.allowSharedKeyAccess "parameters('allowSharedKeyAccess')"
    Assert-Equal 'AVM network ACL forwarding must retain exact list, bypass and IP behavior.' $Fields.networkAcls "if(not(empty(parameters('networkAcls'))), union(createObject('resourceAccessRules', tryGet(parameters('networkAcls'), 'resourceAccessRules'), 'defaultAction', coalesce(tryGet(parameters('networkAcls'), 'defaultAction'), 'Deny'), 'virtualNetworkRules', tryGet(parameters('networkAcls'), 'virtualNetworkRules'), 'ipRules', tryGet(parameters('networkAcls'), 'ipRules')), if(contains(parameters('networkAcls'), 'bypass'), createObject('bypass', tryGet(parameters('networkAcls'), 'bypass')), createObject())), createObject('bypass', 'AzureServices', 'defaultAction', 'Deny'))"
    Assert-Equal 'AVM PNA forwarding must remain unchanged.' $Fields.publicNetworkAccess "if(not(empty(parameters('publicNetworkAccess'))), parameters('publicNetworkAccess'), if(and(not(empty(parameters('privateEndpoints'))), empty(parameters('networkAcls'))), 'Disabled', null()))"
    # The exact expressions above select their nonempty branches for these
    # controlled inputs. union adds bypass to four disjoint ACL keys; no merge,
    # filtering, sorting, deduplication or inferred rule is performed.
    return @{
        deployed = $RootInputs.deployStorageAccount
        allowSharedKeyAccess = $avmInputs.allowSharedKeyAccess
        publicNetworkAccess = $avmInputs.publicNetworkAccess
        networkAcls = $avmInputs.networkAcls
    }
}

function ConvertTo-BicepLiteral {
    param([AllowNull()]$Value)
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [string]) {
        return "'" + $Value.Replace('\', '\\').Replace("'", "\'").Replace('${', '\${') + "'"
    }
    if ($Value -is [bool]) { return $Value.ToString().ToLowerInvariant() }
    if ($Value -is [System.Collections.IDictionary]) {
        $lines = @('{')
        foreach ($key in $Value.Keys) { $lines += "$key`: $(ConvertTo-BicepLiteral $Value[$key])" }
        return ($lines + '}') -join "`n"
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        $lines = @('[')
        foreach ($item in $Value) { $lines += ConvertTo-BicepLiteral $item }
        return ($lines + ']') -join "`n"
    }
    if ($Value -is [int]) { return [string]$Value }
    throw 'Unsupported synthetic fixture value.'
}

function Invoke-TypedFixture {
    param(
        [string]$Name,
        $Assignments,
        [string[]]$InvalidParameters = @(),
        [object[]]$InvalidRules = @()
    )
    $fixturePath = Join-Path $tempDirectory "$Name.bicepparam"
    $outputPath = Join-Path $tempDirectory "$Name.json"
    $createdFiles.Add($fixturePath)
    $createdFiles.Add($outputPath)
    $relativeRoot = [IO.Path]::GetRelativePath($tempDirectory, $MainFile).Replace('\', '/')
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("using $(ConvertTo-BicepLiteral $relativeRoot)")
    foreach ($entry in $requiredInputs.GetEnumerator()) {
        $lines.Add("param $($entry.Key) = $(ConvertTo-BicepLiteral $entry.Value)")
    }
    # Expand strings before recording diagnostic line ranges.
    $text = ($lines -join "`n") + "`n"
    $expectedErrors = [System.Collections.Generic.List[object]]::new()
    foreach ($entry in $Assignments.GetEnumerator()) {
        $firstLine = ($text -split "`n").Count
        $literal = ConvertTo-BicepLiteral $entry.Value
        $text += "param $($entry.Key) = $literal`n"
        if ($entry.Key -in $InvalidParameters) {
            $expectedErrors.Add(@{ First = $firstLine; Last = ($text -split "`n").Count - 1; Name = $entry.Key })
        }
    }
    if ($InvalidRules.Count -gt 0) {
        $text += "param storageAccountResourceAccessRules = [`n"
        foreach ($rule in $InvalidRules) {
            $firstLine = ($text -split "`n").Count
            $text += (ConvertTo-BicepLiteral $rule.Value) + "`n"
            $expectedErrors.Add(@{ First = $firstLine; Last = ($text -split "`n").Count - 1; Name = $rule.Name })
        }
        $text += "]`n"
    }
    [IO.File]::WriteAllText($fixturePath, $text)
    $diagnostics = @(& az bicep build-params --file $fixturePath --outfile $outputPath --no-restore 2>&1)
    $compilerExit = $LASTEXITCODE
    if ($expectedErrors.Count -eq 0) {
        if ($compilerExit -ne 0) { throw "Typed positive fixture '$Name' failed to compile (exit $compilerExit); not a valid negative-test result." }
        $built = Get-Content -LiteralPath $outputPath -Raw | ConvertFrom-Json -AsHashtable -Depth 100
        foreach ($entry in $Assignments.GetEnumerator()) {
            Assert-Contract ($built.parameters.Contains($entry.Key) -and $built.parameters[$entry.Key].Contains('value')) "$Name must emit the explicit $($entry.Key) assignment, including null."
            Assert-Equal "$Name must retain native $($entry.Key)." $built.parameters[$entry.Key].value $entry.Value
        }
        foreach ($key in $inputNames | Where-Object { -not $Assignments.Contains($_) }) {
            Assert-Contract (-not $built.parameters.Contains($key)) "$Name must leave $key omitted."
        }
    }
    else {
        Assert-Contract ($compilerExit -ne 0) "S9/${Name}: compiler accepted invalid typed inputs."
        $typedErrors = @()
        foreach ($diagnostic in $diagnostics) {
            $message = [string]$diagnostic
            if ($message -notmatch 'Error BCP\d+:') { continue }
            # An unrelated root/module/tool or syntax error must never satisfy a
            # negative test. Require both fixture-local location and type reason.
            $locationPattern = [regex]::Escape($fixturePath) + '\((?<line>\d+),\d+\)\s*:\s*Error BCP\d+:'
            Assert-Contract ($message -match $locationPattern) "S9/${Name}: unrelated compiler error, not typed fixture rejection."
            $line = [int]$Matches.line
            Assert-Contract ($message -match '(?i)(expected ((a value|an item) of|the value to be of) type|requires the following properties|missing the following required properties|property .+ is not allowed|minimum (allowable )?length|too short)') "S9/${Name}: diagnostic is not an expected type/constraint error."
            Assert-Contract (@($expectedErrors | Where-Object { $line -ge $_.First -and $line -le $_.Last }).Count -gt 0) "S9/${Name}: error is outside the invalid value."
            $typedErrors += $line
        }
        foreach ($expected in $expectedErrors) {
            Assert-Contract (@($typedErrors | Where-Object { $_ -ge $expected.First -and $_ -le $expected.Last }).Count -gt 0) "S9/$Name/$($expected.Name): missing individual typed rejection."
        }
    }
    $rejectionSummary = if ($expectedErrors.Count -gt 0) { " ($($expectedErrors.Count) individually rejected values)" } else { '' }
    Write-Host "  [PASS] Typed fixture $Name$rejectionSummary" -ForegroundColor Green
}

try {
    Assert-Contract ($PSVersionTable.PSVersion.Major -ge 7) 'PowerShell 7 is required.'
    $MainFile = (Resolve-Path -LiteralPath $MainFile).Path
    $root = Split-Path -Parent $MainFile
    $manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'fixtures/historical-foundation-manifest.json') -Raw | ConvertFrom-Json -AsHashtable
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Azure CLI is required; standalone Bicep is not used.' }
    $env:PYTHONIOENCODING = 'utf-8'
    $versionOutput = (& az bicep version 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0 -or $versionOutput -notmatch 'Bicep CLI version 0\.42\.1(?:\s|$)') {
        throw 'Azure CLI Bicep 0.42.1 is required. Install it explicitly; this test does not upgrade tooling or AVM.'
    }
    $tempDirectory = Join-Path $root ".solution-storage-contract-$([guid]::NewGuid().ToString('N'))"
    $null = New-Item -ItemType Directory -Path $tempDirectory
    $createdDirectory = $true
    $compiledFile = Join-Path $tempDirectory 'main.json'
    $createdFiles.Add($compiledFile)
    Write-Host 'Solution Storage access contract (issue #160; Azure CLI Bicep 0.42.1)' -ForegroundColor Cyan
    & az bicep build --file $MainFile --outfile $compiledFile
    if ($LASTEXITCODE -ne 0) { throw 'Root compilation failed; this is not the expected missing-contract RED.' }
    $template = Get-Content -LiteralPath $compiledFile -Raw | ConvertFrom-Json -AsHashtable -Depth 100
    Write-Host '  [PASS] Actual root compiled successfully.' -ForegroundColor Green

    # Fail here on the pre-implementation root, not via incidental null access,
    # expected negative-fixture errors, or a missing compiler.
    $missing = @($inputNames | Where-Object { -not $template.parameters.Contains($_) })
    Assert-Contract ($missing.Count -eq 0) "S1/S9 missing public Storage input contract: $($missing -join ', ')."

    $source = Get-Content -LiteralPath $MainFile -Raw
    Assert-Contract ($source -match "module\s+storageAccount\s+'br/public:avm/res/storage/storage-account:0\.26\.2'") 'Solution Storage AVM must remain pinned at 0.26.2.'
    # Check the actual compiled references and their source, not an alias or a
    # commented-out source declaration that merely contains the expected tokens.
    $bypassSchema = Get-ImportedStorageSchema $template $template.parameters.storageAccountNetworkAclsBypass 'storageAccountNetworkAclsBypassType'
    $rulesSchema = Get-Schema $template $template.parameters.storageAccountResourceAccessRules
    $ruleSchema = Get-ImportedStorageSchema $template $rulesSchema.items 'storageAccountResourceAccessRuleType'
    $constantsFile = Join-Path $root $bypassSchema.metadata['__bicep_imported_from!'].sourceTemplate
    $constantsOutput = Join-Path $tempDirectory 'constants.json'
    $createdFiles.Add($constantsOutput)
    & az bicep build --file $constantsFile --outfile $constantsOutput --no-restore
    if ($LASTEXITCODE -ne 0) { throw 'Constants compilation failed.' }
    $constants = Get-Content -LiteralPath $constantsOutput -Raw | ConvertFrom-Json -AsHashtable -Depth 100
    foreach ($name in @('storageAccountNetworkAclsBypassType', 'storageAccountResourceAccessRuleType')) {
        $definition = $constants.definitions[$name]
        Assert-Contract ($null -ne $definition) "Missing exported type $name."
        Assert-Equal "$name must be exported." $definition.metadata['__bicep_export!'] $true
        Assert-Contract (-not [string]::IsNullOrWhiteSpace($definition.metadata.description)) "$name must be described."
    }
    Assert-Equal 'Bypass must be a string union.' $bypassSchema.type 'string'
    Assert-Equal 'Bypass must have exactly the eight pinned spellings.' @($bypassSchema.allowedValues | Sort-Object) @($bypassValues | Sort-Object)
    Assert-Equal 'Exported bypass must have the same eight spellings.' @($constants.definitions.storageAccountNetworkAclsBypassType.allowedValues | Sort-Object) @($bypassValues | Sort-Object)
    Assert-Contract (-not $bypassSchema.nullable) 'Bypass must not be nullable.'
    Assert-Equal 'Resource rules must be a typed array.' $rulesSchema.type 'array'
    Assert-Contract (-not $rulesSchema.nullable) 'Rule list must not be nullable.'
    Test-RuleSchema $ruleSchema
    Test-RuleSchema $constants.definitions.storageAccountResourceAccessRuleType
    $sharedKeySchema = $template.parameters.storageAccountAllowSharedKeyAccess
    Assert-Equal 'Shared Key input must be a native Boolean.' $sharedKeySchema.type 'bool'
    Assert-Contract (-not $sharedKeySchema.nullable) 'Shared Key input must not be nullable.'
    $defaults = [ordered]@{
        storageAccountNetworkAclsBypass = 'AzureServices'
        storageAccountResourceAccessRules = @()
        storageAccountAllowSharedKeyAccess = $true
    }
    $parameterFile = Get-Content -LiteralPath (Join-Path $root 'main.parameters.json') -Raw | ConvertFrom-Json -AsHashtable -Depth 100
    foreach ($name in $inputNames) {
        Assert-Contract ($template.parameters[$name].Contains('defaultValue')) "$name must have an omitted-input default."
        Assert-Contract (-not [string]::IsNullOrWhiteSpace($template.parameters[$name].metadata.description)) "$name must be described."
        Assert-Equal "$name Bicep default must retain native type and value." $template.parameters[$name].defaultValue $defaults[$name]
        if ($parameterFile.parameters.Contains($name)) {
            Assert-Equal "$name explicit parameter-file default must be native, without an environment alias." $parameterFile.parameters[$name].value $defaults[$name]
        }
        else {
            Assert-Equal "$name omitted from incorporated parameter file must use its proven native Bicep default." $template.parameters[$name].defaultValue $defaults[$name]
        }
    }
    Write-Host '  [PASS] S1/S2/S6/S9 public types, defaults, exact union and native parameter surface.' -ForegroundColor Green

    $solution = $template.resources.storageAccount
    Assert-Equal 'Solution deployment name is stable.' $solution.name 'storageAccountSolution'
    Assert-Equal 'S8 solution deployment gate must remain direct.' $solution.condition "[parameters('deployStorageAccount')]"
    $moduleParameters = $solution.properties.parameters
    Assert-Equal 'Root -> AVM bypass binding.' $moduleParameters.networkAcls.value.bypass "[parameters('storageAccountNetworkAclsBypass')]"
    Assert-Equal 'Root -> AVM complete rule-list binding.' $moduleParameters.networkAcls.value.resourceAccessRules "[parameters('storageAccountResourceAccessRules')]"
    Assert-Equal 'Root -> AVM Boolean binding.' $moduleParameters.allowSharedKeyAccess.value "[parameters('storageAccountAllowSharedKeyAccess')]"
    $avm = $solution.properties.template
    Assert-Equal 'Nested Storage resource type.' $avm.resources.storageAccount.type 'Microsoft.Storage/storageAccounts'
    Assert-Equal 'Nested Storage API pin.' $avm.resources.storageAccount.apiVersion '2024-01-01'
    $fields = Get-PinnedStorageFields $avm.resources.storageAccount.properties

    Assert-Equal 'Isolation fallback expression must remain unchanged.' $template.variables._networkIsolation "[if(empty(string(parameters('networkIsolation'))), false(), bool(parameters('networkIsolation')))]"
    Assert-Equal 'IP allow-list gate must remain unchanged.' $template.variables._applyIpRules "[not(empty(parameters('allowedIpRanges')))]"
    Assert-Equal 'PNA decision must remain unchanged.' $template.variables._publicNetworkAccess "[if(or(not(variables('_networkIsolation')), variables('_applyIpRules')), 'Enabled', 'Disabled')]"
    Assert-Equal 'PNA binding must remain unchanged.' $moduleParameters.publicNetworkAccess.value "[variables('_publicNetworkAccess')]"
    Assert-Equal 'Default action must remain IP-controlled.' $moduleParameters.networkAcls.value.defaultAction "[if(variables('_applyIpRules'), 'Deny', 'Allow')]"
    Assert-Equal 'IP rules must remain allow-list-controlled.' $moduleParameters.networkAcls.value.ipRules "[variables('_storageIpRules')]"
    Assert-Equal 'VNet rules must remain empty.' $moduleParameters.networkAcls.value.virtualNetworkRules @()
    Assert-Equal 'Exact Storage IP copy loop.' @($template.variables.copy | Where-Object name -CEQ '_storageIpRules') @(@{
        name = '_storageIpRules'
        count = "[length(parameters('allowedIpRanges'))]"
        input = @{ value = "[parameters('allowedIpRanges')[copyIndex('_storageIpRules')]]"; action = 'Allow' }
    })
    foreach ($field in @('allowBlobPublicAccess', 'supportsHttpsTrafficOnly')) {
        Assert-Equal "Nested $field forwarding." $fields[$field] "parameters('$field')"
    }

    # Equivalent defaults, not byte-identical JSON: normalize ONLY new bindings
    # after proving them above. Everything else in the entire module stays pinned.
    . (Join-Path $PSScriptRoot 'ScopedResourceGroupNormalization.ps1')
    $graphTemplate = ConvertTo-HistoricalFoundationGraph (ConvertTo-LegacyResourceGroupGraph $template) $MainFile
    $oldSolution = $graphTemplate.resources.storageAccount | ConvertTo-Json -Depth 100 | ConvertFrom-Json -AsHashtable -Depth 100
    $null = $oldSolution.properties.parameters.Remove('allowSharedKeyAccess')
    $null = $oldSolution.properties.parameters.networkAcls.value.Remove('resourceAccessRules')
    $oldSolution.properties.parameters.networkAcls.value.bypass = 'AzureServices'
    Test-UnchangedGraph $graphTemplate $oldSolution $manifest
    $graphMutations = @(
        @{ Name = 'unrelated subnet exclusion'; Expected = 'resources.virtualNetworkSubnets'; Change = { param($t, $m) $t.resources.virtualNetworkSubnets.properties.template.variables.invalidNsgSubnets += 'workload' } },
        @{ Name = 'subnet explicit NSG priority drift'; Expected = 'resources.virtualNetworkSubnets'; Change = { param($t, $m) $child = @($t.resources.virtualNetworkSubnets.properties.template.resources | Where-Object { $_.Contains('copy') -and $_.copy.name -ceq 'subnetsM' })[0]; $child.properties.parameters.networkSecurityGroupId = @{ value = '' } } },
        @{ Name = 'manifest repo drift'; Expected = 'Historical foundation manifest'; Change = { param($t, $m) $m.repo = 'https://example.invalid/changed.git'; $t.variables['$fxv#0'].repo = $m.repo } },
        @{ Name = 'manifest components drift'; Expected = 'Historical foundation manifest'; Change = { param($t, $m) $m.components = @(@{ repo = 'https://example.invalid/component.git'; tag = 'v1.0.0' }); $t.variables['$fxv#0'].components = $m.components } },
        @{ Name = 'extra manifest field'; Expected = 'Historical foundation manifest'; Change = { param($t, $m) $m.extra = 'drift'; $t.variables['$fxv#0'].extra = 'drift' } },
        @{ Name = 'manifest generator is not compiler metadata'; Expected = 'Historical foundation manifest'; Change = { param($t, $m) $m._generator = 'drift'; $t.variables['$fxv#0']._generator = 'drift' } },
        @{ Name = 'unrelated root variable'; Expected = 'root.variables'; Change = { param($t, $m) $t.variables._publicNetworkAccess = 'Enabled' } },
        @{ Name = 'compiled release mismatch'; Expected = 'Compiled _manifest'; Change = { param($t, $m) $t.variables['$fxv#0'].tag = 'v99.0.0'; $t.variables['$fxv#0'].ailz_tag = 'v99.0.0' } },
        @{ Name = 'compiler manifest binding drift'; Expected = 'Compiled _manifest'; Change = { param($t, $m) $t.variables._manifest = '[variables(''other'')]' } },
        @{ Name = 'manifest tag mismatch'; Expected = 'Historical foundation manifest'; Change = { param($t, $m) $m.ailz_tag = 'v99.0.0'; $t.variables['$fxv#0'].ailz_tag = $m.ailz_tag } },
        @{ Name = 'invalid release format'; Expected = 'Historical foundation manifest'; Change = { param($t, $m) $m.tag = 'v2.7.0-rc.1'; $m.ailz_tag = $m.tag; $t.variables['$fxv#0'].tag = $m.tag; $t.variables['$fxv#0'].ailz_tag = $m.tag } },
        @{ Name = 'historical release mismatch'; Expected = 'Historical foundation manifest'; Change = { param($t, $m) $m.tag = 'v99.0.0'; $m.ailz_tag = $m.tag; $t.variables['$fxv#0'].tag = $m.tag; $t.variables['$fxv#0'].ailz_tag = $m.tag } },
        @{ Name = 'unrelated resource'; Expected = 'resources.aiFoundryStorageAccount'; Change = { param($t, $m) $t.resources.aiFoundryStorageAccount.condition = $false } },
        @{ Name = 'unrelated output'; Expected = 'root.outputs'; Change = { param($t, $m) $t.outputs.extra = @{ type = 'string'; value = 'drift' } } }
    )
    foreach ($mutation in $graphMutations) {
        $changedTemplate = $graphTemplate | ConvertTo-Json -Depth 100 | ConvertFrom-Json -AsHashtable -Depth 100
        $changedManifest = $manifest | ConvertTo-Json -Depth 100 | ConvertFrom-Json -AsHashtable -Depth 100
        & $mutation.Change $changedTemplate $changedManifest
        $caught = $false
        try { Test-UnchangedGraph $changedTemplate $oldSolution $changedManifest }
        catch {
            if ($_.Exception.Message -notmatch [regex]::Escape($mutation.Expected)) { throw }
            $caught = $true
        }
        Assert-Contract $caught "Graph guard accepted $($mutation.Name)."
    }
    Write-Host "  [PASS] $($graphMutations.Count) release/manifest/graph mutations rejected without replacing fingerprints." -ForegroundColor Green
    # Also prevent misdirected consumption, including the separately owned ACR.
    $outsideSolution = ConvertTo-Json -InputObject @{
        resources = @($template.resources.GetEnumerator() | Where-Object Key -CNE 'storageAccount' | ForEach-Object Value)
        variables = $template.variables
        outputs = $template.outputs
    } -Depth 100 -Compress
    foreach ($name in $inputNames) {
        Assert-Contract (-not $outsideSolution.Contains("parameters('$name')")) "$name must reach only solution Storage."
    }
    Write-Host '  [PASS] Exact bindings, pinned shallowMerge and unchanged Storage/security envelope.' -ForegroundColor Green

    # Deliberately synthetic, distinct, reverse-sorted and mixed-case identifiers:
    # equality catches dropping, normalization, sorting and implicit merging.
    $ruleOne = [ordered]@{
        resourceId = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/Contract-Z/providers/Microsoft.Security/dataScanners/StorageDataScanner'
        tenantId = '00000000-0000-0000-0000-000000000001'
    }
    $ruleTwo = [ordered]@{
        resourceId = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/Contract-A/providers/Microsoft.Security/dataScanners/StorageDataScanner'
        tenantId = '00000000-0000-0000-0000-000000000002'
    }
    $profiles = @(
        @{ Name = 'S1/S2 omitted'; Values = @{} },
        @{ Name = 'S1/S2 top-level null (compiler default semantics)'; Values = @{ storageAccountNetworkAclsBypass = $null; storageAccountAllowSharedKeyAccess = $null; storageAccountResourceAccessRules = $null } },
        @{ Name = 'S3 keyless/no-scanner'; Values = @{ storageAccountNetworkAclsBypass = 'None'; storageAccountAllowSharedKeyAccess = $false; storageAccountResourceAccessRules = @() } },
        @{ Name = 'S4 one rule'; Values = @{ storageAccountNetworkAclsBypass = 'None'; storageAccountAllowSharedKeyAccess = $false; storageAccountResourceAccessRules = @($ruleOne) } },
        @{ Name = 'S5 multiple rules'; Values = @{ storageAccountNetworkAclsBypass = 'None'; storageAccountAllowSharedKeyAccess = $false; storageAccountResourceAccessRules = @($ruleOne, $ruleTwo) } }
    )
    foreach ($bypass in $bypassValues) {
        foreach ($sharedKey in @($true, $false)) {
            $profiles += @{ Name = "S6 $bypass / SharedKey=$sharedKey"; Values = @{
                storageAccountNetworkAclsBypass = $bypass
                storageAccountAllowSharedKeyAccess = $sharedKey
                storageAccountResourceAccessRules = @($ruleOne, $ruleTwo)
            } }
        }
    }
    $matrixRows = 0
    foreach ($profile in $profiles) {
        foreach ($isolated in @($false, $true)) {
            foreach ($withIps in @($false, $true)) {
                foreach ($enabled in @($true, $false)) {
                    $inputs = [ordered]@{}
                    foreach ($name in $inputNames) {
                        $inputs[$name] = Resolve-DefaultedRootInput $template $name $profile.Values
                        if (-not $profile.Values.Contains($name) -or $null -eq $profile.Values[$name]) {
                            Assert-Equal "$($profile.Name): omitted/top-level-null $name retains its declared default." $inputs[$name] $defaults[$name]
                        }
                    }
                    $inputs.networkIsolation = $isolated
                    $inputs.allowedIpRanges = @(if ($withIps) { '192.0.2.8/32'; '198.51.100.0/24' })
                    $inputs.deployStorageAccount = $enabled
                    $actual = Resolve-StorageProfile $inputs $moduleParameters $fields
                    $expected = @{
                        deployed = $enabled
                        allowSharedKeyAccess = $inputs.storageAccountAllowSharedKeyAccess
                        publicNetworkAccess = $(if ($isolated -and -not $withIps) { 'Disabled' } else { 'Enabled' })
                        networkAcls = @{
                            bypass = $inputs.storageAccountNetworkAclsBypass
                            resourceAccessRules = $inputs.storageAccountResourceAccessRules
                            defaultAction = $(if ($withIps) { 'Deny' } else { 'Allow' })
                            virtualNetworkRules = @()
                            ipRules = @(if ($withIps) { @{ value = '192.0.2.8/32'; action = 'Allow' }; @{ value = '198.51.100.0/24'; action = 'Allow' } })
                        }
                    }
                    Assert-Equal "$($profile.Name)/S7/S8 controlled forwarding matrix." $actual $expected
                    $matrixRows++
                }
            }
        }
    }
    Write-Host "  [PASS] S1-S8: $matrixRows bounded profile/isolation/IP/deployment-gate cases." -ForegroundColor Green

    # Supply only mandatory root inputs, never the operator's azd environment.
    # Empty password is intentionally unusable and only compiled, never deployed.
    $requiredInputs = [ordered]@{
        environmentName = 'storage-contract'
        principalId = '00000000-0000-0000-0000-000000000000'
        modelDeploymentList = @()
        containerAppsList = @()
        databaseContainersList = @()
        vmAdminPassword = ''
        storageAccountContainersList = @()
    }
    Invoke-TypedFixture 'omitted-defaults' ([ordered]@{})
    Invoke-TypedFixture 'explicit-top-level-null' ([ordered]@{
        storageAccountNetworkAclsBypass = $null
        storageAccountAllowSharedKeyAccess = $null
        storageAccountResourceAccessRules = $null
    })
    $nativeDefaults = [ordered]@{}
    foreach ($name in $inputNames) {
        $nativeDefaults[$name] = if ($parameterFile.parameters.Contains($name)) { $parameterFile.parameters[$name].value } else { $defaults[$name] }
    }
    Invoke-TypedFixture 'native-parameter-file' $nativeDefaults
    Invoke-TypedFixture 'keyless-multiple-disabled' ([ordered]@{
        storageAccountNetworkAclsBypass = 'None'
        storageAccountAllowSharedKeyAccess = $false
        storageAccountResourceAccessRules = @($ruleOne, $ruleTwo)
        networkIsolation = $true
        allowedIpRanges = @('192.0.2.8/32')
        deployStorageAccount = $false
    })

    # Each grouped assignment must have its own fixture-local type diagnostic.
    $scalarNegatives = @(
        @{ Name = 'unsupported-stringified'; Bypass = 'Bogus'; SharedKey = 'false'; Rules = '[]' },
        @{ Name = 'case-and-stringified-types'; Bypass = 'azureservices'; SharedKey = 'true'; Rules = 'null' },
        @{ Name = 'order-and-wrong-types'; Bypass = 'Metrics, Logging'; SharedKey = 0; Rules = @{} },
        @{ Name = 'spacing-and-containers'; Bypass = 'Logging,Metrics'; SharedKey = @(); Rules = $false },
        @{ Name = 'empty-and-wrong-types'; Bypass = ''; SharedKey = @{}; Rules = 1 }
    )
    foreach ($case in $scalarNegatives) {
        Invoke-TypedFixture $case.Name ([ordered]@{
            storageAccountNetworkAclsBypass = $case.Bypass
            storageAccountAllowSharedKeyAccess = $case.SharedKey
            storageAccountResourceAccessRules = $case.Rules
        }) -InvalidParameters $inputNames
    }
    Invoke-TypedFixture 'boolean-bypass' ([ordered]@{ storageAccountNetworkAclsBypass = $true }) -InvalidParameters @('storageAccountNetworkAclsBypass')
    $invalidRules = @(
        @{ Name = 'missing-both'; Value = @{} },
        @{ Name = 'missing-resourceId'; Value = @{ tenantId = $ruleOne.tenantId } },
        @{ Name = 'missing-tenantId'; Value = @{ resourceId = $ruleOne.resourceId } },
        @{ Name = 'extra-field'; Value = @{ resourceId = $ruleOne.resourceId; tenantId = $ruleOne.tenantId; extra = 'not-allowed' } },
        @{ Name = 'misspelled-field'; Value = @{ resourceId = $ruleOne.resourceId; tenantIDTypo = $ruleOne.tenantId } },
        @{ Name = 'empty-resourceId'; Value = @{ resourceId = ''; tenantId = $ruleOne.tenantId } },
        @{ Name = 'empty-tenantId'; Value = @{ resourceId = $ruleOne.resourceId; tenantId = '' } },
        @{ Name = 'null-resourceId'; Value = @{ resourceId = $null; tenantId = $ruleOne.tenantId } },
        @{ Name = 'null-tenantId'; Value = @{ resourceId = $ruleOne.resourceId; tenantId = $null } },
        @{ Name = 'wrong-resourceId'; Value = @{ resourceId = 1; tenantId = $ruleOne.tenantId } },
        @{ Name = 'wrong-tenantId'; Value = @{ resourceId = $ruleOne.resourceId; tenantId = $false } },
        @{ Name = 'null-entry'; Value = $null },
        @{ Name = 'string-entry'; Value = 'not-an-object' },
        @{ Name = 'array-entry'; Value = @() }
    )
    Invoke-TypedFixture 'malformed-rule-entries' ([ordered]@{}) -InvalidRules $invalidRules
    Write-Host "`nSolution Storage access contract passed. Live persistence/authentication/scanning are not proven." -ForegroundColor Green
}
catch {
    if ($_.Exception.Message.StartsWith('CONTRACT:')) {
        Write-Host "  [FAIL] $($_.Exception.Message)" -ForegroundColor Red
        $exitCode = 1
    }
    else {
        Write-Host "  [TOOL/TEST ERROR] $($_.Exception.Message)" -ForegroundColor Red
        $exitCode = 2
    }
}
finally {
    $env:PYTHONIOENCODING = $oldPythonEncoding
    foreach ($path in $createdFiles) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }
    if ($createdDirectory) {
        # Non-recursive deletion refuses to remove any unowned/unexpected file.
        [IO.Directory]::Delete($tempDirectory, $false)
    }
}
exit $exitCode
