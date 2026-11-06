# Exact, bounded inverse of the optional PostgreSQL delta, compiled with 0.42.1
# against pre-feature 4d1b4506fecbe70c50f65fea95dcf5069334e6bd.
# This does NOT replace any historical fingerprint.
# Both sides of every changed field are pinned; only compiler generator metadata
# is non-deploying. Digests avoid copying two complete pinned AVM modules.
# Test-PostgreSqlContract independently checks security/wiring and disabled AST
# equivalence. Mutation tests reject every accepted path, including new modules.
$script:postgreSqlDigestCache = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
function Get-PostgreSqlDigest($Value) {
    # Mutation sweeps reuse large AVM values. Cache only byte-identical JSON,
    # using ordinal (case-sensitive) equality; changed values always rehash.
    $raw = ConvertTo-Json -InputObject $Value -Depth 100 -Compress
    if ($script:postgreSqlDigestCache.ContainsKey($raw)) { return $script:postgreSqlDigestCache[$raw] }
    $json = ConvertTo-Json -InputObject (ConvertTo-ScopedComparable $Value) -Depth 100 -Compress
    $digest = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($json))).ToLowerInvariant()
    if ($script:postgreSqlDigestCache.Count -ge 1024) { $script:postgreSqlDigestCache.Clear() }
    $script:postgreSqlDigestCache[$raw] = $digest
    return $digest
}

function Get-PostgreSqlDelta {
    @'
/parameters/deployPostgreSql|added|113a194ebb0b4c4d7cca9d1caad9fd895a8d48d5b5e7d0544778315c16b58eb7
/parameters/postgreSqlServerName|added|0becdf881dca5e4b2fa36d4a78f1a7063268ecb87af41263c2a86d1d4e70ef71
/parameters/postgreSqlDatabaseName|added|5719315a4b4a8ed867ae1c36fd99390535e2897455a06a21b4a02b1a5f1e738a
/parameters/postgreSqlVersion|added|5e8e1ba560d6b8369d32e1a01c4b06372843540c5b916e1095afe366197874ae
/parameters/postgreSqlTier|added|738b1d391df05d18ed90f5b408c8e07fef5699a714aa416f3085ca6b49183242
/parameters/postgreSqlSkuName|added|b2ab4933b8bbfb7ec0710627b019e0969684cca91d27e42feafd58ba509aac1f
/parameters/postgreSqlStorageSizeGb|added|1b0ed3cd8a07b41b9f59302f312cbefa77ee67cdaa47aa0c9e92fb5997762dbb
/parameters/postgreSqlBackupRetentionDays|added|bb0bb274f3397020b5eff583d4e84431f6d9e0a0c229b4deb7f0cea075d56d3c
/parameters/postgreSqlHighAvailability|added|5a2f5c8ac1a1598f8ebe3efdaa598d756996c0cefd536a87be341db93dc67d03
/parameters/postgreSqlGeoRedundantBackup|added|ba44fc6efe33abd43e48219f3ea5c26ae3ecfb943439e0133366810ca846c3c0
/parameters/postgreSqlStorageAutoGrow|added|ba44fc6efe33abd43e48219f3ea5c26ae3ecfb943439e0133366810ca846c3c0
/parameters/postgreSqlAdministratorObjectId|added|61b3a74851fcec26d05e79274f07425b4cd2093a696ede5afa61a53bed98e0d7
/parameters/postgreSqlAdministratorPrincipalName|added|70eada34008304f355f8d985b3c12a75b95194590f7d2229e6302ea537d87d7f
/parameters/postgreSqlAdministratorPrincipalType|added|81feb4d2fa7be4c36702ab82ab48146633a2c7b12589f83e7130136e4f63a492
/parameters/postgreSqlAllowedIpRanges|added|3abb856eb0e24cccb4821c8e199bab9e630bf2aa5ded4b0aed4d426197adeac9
/parameters/existingPrivateDnsZonePostgreSqlResourceId|added|f9382fe6d0aa9d941cd4c7ac13e0191710e7610c376473c5b1c224ee40d33feb
/variables/copy|loop|8f04ba937050a71b8d51b035f8d5865e7e5c0d8c914c74946afab6f2d70ebeec|28500a69a94af5cc6340096c177312b9e84f9484afaa323fc98cab07e5b984f5
/variables/_legacyResourceNames/postgreSqlServerName|added|200cbf2eb1ff64eba8da0e59dcfbda7a3a0b986b29fc5db84ac0e035740a5f61
/variables/_cafResourceNames/postgreSqlServerName|added|3051d777c87114f090104a21e80b658ad5f589462854b600e43137f1e8c86577
/variables/resourceNames/postgreSqlServerName|added|8065319fc9e517cf35a9557b1301134770f79312a2f0f023abad8688ff6c11c5
/variables/_postgreSqlBasic|added|88959892c8f533782ca6eae91021b9528ceb2691a3501f250cb5fd26fc8e77e3
/variables/_acaVnetIntegration|added|76a5b3e4f232b2448ab67178c073f3898867dd93f28f107315e8bec3e4a73a03
/variables/subnetDefinitions/9/required|special|5dfa0da96804a344711e712c339666ad41b25a30deb5624cfb121ef504ddd4c0|314f1af9392f7e03d10d97fc071e5e06bacbd3d7118028331d1c681829da5bdc
/variables/selectedSubnetDefinitions|special|345affaa292986240513a6f77871fc5b2f27eb28e50c0647b97605ce09a013b5|615a9c9298cc21ac3f964e43d90582dc36588d262c3ebe520e4da6cbd457b4d5
/variables/_dnsZonePostgreSqlId|added|c69556c18e2de54db89adf1519dc293b893a5f7959dd492c53e43b3824eae4ec
/variables/_byoZonePostgreSql|added|25846d236aeb3d52f5f215aa62c835fcfdb53f7ea66050c831ba9f24ea7ed530
/variables/_dnsZonesList|special|66111ae3d9e9f5e461cf670aea9198040cea632cff87f30570b1fc7567ec64cd|f7633247424c9e7e79ac51cecc56a68f3ffbac8a0a67277229daa51439a0fe91
/resources/networkLayoutValidation/condition|vnet|dd2dc31d0bb5a2ba68b6da9304cc52f2218cace1d7c8ac347436d8453c411557|128b6d2bb40ffe7243ab4189d50dcd003d5f5659a6d26af55abf988d934bc4c7
/resources/networkLayoutValidation/properties/parameters/subnetDefinitions/value|special|af4333bbc30ec7b964c909d71d8068633dc1bb129e3b17fc2a3eede1b260a817|312ced82100c365b528594db034ed8da4e80fbf6ba26e1e3e7a292b95844a77a
/resources/virtualNetworkSubnets/properties/parameters/subnets/value|special|f4d006a3f23f15d37ed16397f8e5cb7ea829d50c037c7a1f404b3a114ba6e0e3|ad01729cbbc589e9337676cf620a78cdfa8a61723edbfaef21e5950ee3e7b2a2
/resources/virtualNetworkSubnets/properties/parameters/virtualNetworkResourceId|vnet|2423e7e274607cf2b5b652e4b4181a9f999d8ab3e29f4c055fd9f2d5fbbdaa03|7755b95b4f00b6769ff9c7290146c7a78867050965bf679ba6f74911ab6d0bb0
/resources/virtualNetworkSubnets/dependsOn|dependencies|2591fda9c7d640ccd234c2525bb5d4c38204f344474e5d9ecdf37641c138c4ab|a39cca68f95e18734eea9c24269961f18f01c90d0551d733b5465e1f1f2182f1
/resources/containerAppsPostgreSqlSubnet|added|47423e418e0fae8e52a6957f5650bfafc71e03acfddb644762c0b671cae96c5d
/resources/virtualNetwork/condition|vnet|15e388507ccfe5d4ebafb2605afba5d403e22ff72b02ebd4c099fc85c3a81459|5f5ea299044d51bea5b4ad0447c3e51f7f92970b30b28cfa163eb05ce8d289db
/resources/virtualNetwork/properties/parameters/subnets/value|special|f4d006a3f23f15d37ed16397f8e5cb7ea829d50c037c7a1f404b3a114ba6e0e3|ad01729cbbc589e9337676cf620a78cdfa8a61723edbfaef21e5950ee3e7b2a2
/resources/virtualNetwork/dependsOn|dependencies|808d3a72e4bda7986465caa88ce7d21d334e734c86f36e918db5489412fc776e|9320957699c718bba1b86d5bf706016ee60b63039fd3f253fbe068f65b53b207
/resources/testVmBastionHost/properties/parameters/subnetResourceId/value|vnet|b8a96dd6e0f107c4f9d9bc51302fea74d98ff81810e65a5b4d7397c91ba9ec79|7a23d46bc2b540c533f7bb639471e6f903ee912e2e47d52315d1272ca1f0aa48
/resources/firewall/properties/parameters/virtualNetworkResourceId|vnet|2423e7e274607cf2b5b652e4b4181a9f999d8ab3e29f4c055fd9f2d5fbbdaa03|7755b95b4f00b6769ff9c7290146c7a78867050965bf679ba6f74911ab6d0bb0
/resources/testVm/properties/parameters/nicConfigurations/value/0/ipConfigurations/0/subnetResourceId|vnet|132b60f0f300080f9333d65a8dcbe6c29dbfaf6663100f4f075dddcb5a4c61ed|923bb39eff8789e194b3024281eedae79661d676e2889c7ab27b4e44c9de11eb
/resources/natGateway/properties/template/outputs/publicIpAddress|added|0a85921b13bd5e1aa92194fbd741e095e89da953ceddfe1661b7cc0d08f87652
/resources/containerAppsPostgreSqlNat|added|7c51173dd7fe0a2683bd089558f1e0c5c2ead802ac9851bf4df46a8a93f51d66
/resources/postgreSqlValidation|added|b903c41769c6a856e53ce972956e1f859a0f1a21402ea5def00fd5672268ca21
/resources/postgreSql|added|91b86e5dbedc41df746034053ab7a0ddc91933b98770097f913944b8a69562fa
/resources/postgreSqlPrivateEndpoint|added|5f249fd3d0948a375b5d7813676fcd53b91848d9e0a01d124b8f28477ffc6fb1
/resources/privateDnsZones/properties/parameters/virtualNetworkResourceId|vnet|2423e7e274607cf2b5b652e4b4181a9f999d8ab3e29f4c055fd9f2d5fbbdaa03|7755b95b4f00b6769ff9c7290146c7a78867050965bf679ba6f74911ab6d0bb0
/resources/privateEndpoints/properties/parameters/endpoints/value|vnet|1289a668e447e0512518b6ad68e6ec75c67eae8794f8217b23b57d02831749bb|bca4e608092648b6b03edc6ffa23ad50de504156c999f61050386474276b3f91
/resources/privateEndpoints/properties/parameters/subnetResourceId|vnet|de6960f83a03f665be96b26e5e6f7e8e89e0663059690b72c04f000c4aa43842|9076d154d4a4c8adad9700e24d276942ded08a7acda14bdad1e715a2382ac003
/resources/aiFoundryStorageAccount/properties/parameters/privateEndpointSubnetResourceId|vnet|0c350f29f5cd7b02a43318596e63e44b0de725b1dd6422b9dac3bb27800ce591|628998fe51786b67c5544a723e9e5e2435b017929ef664e19381c2aa9aafb465
/resources/aiFoundry/properties/parameters/privateEndpointSubnetResourceId|vnet|0c350f29f5cd7b02a43318596e63e44b0de725b1dd6422b9dac3bb27800ce591|628998fe51786b67c5544a723e9e5e2435b017929ef664e19381c2aa9aafb465
/resources/aiFoundry/properties/parameters/aiFoundryConfiguration/value/networking|vnet|e446f7c11d973739649317f89f72ec91636c8718f34c37cd3b5712755f380582|fb85726742f348925ee3bbe2bb9706e68fcca6d24acf368704997c4d7f39d6e0
/resources/privateEndpointPrivateLinkScope/properties/parameters/subnetResourceId|vnet|8d803a64be4f9ca5d58031ef238bd49191f5eff29a8cce4fbf45d80231077863|1a0a5c1bec29e5f7ce63d808465f2c3e80d1542d4742748ebd803fbb41a73065
/resources/containerEnv/properties/parameters/properties/value/vnetConfiguration|special|4da8f57328a1a7a5d662ce5216ee92c14e45b220268d17ccba47e071f2aebd99|237968f77e3a290e17c3e4b671567f39bd0f1db15100aa441e8e54bbd2fc8f3c
/resources/containerEnv/dependsOn|dependencies|51ae70a9c6f16e15da11d9ebdf4ce0686dcd445503dca813913e5636e72a088d|f78c47a1d319ed8a75494598df804c3dafd161f0cc6a4756ec32cd45757bb12b
/resources/acrTaskAgentPool/properties/parameters/subnetResourceId|vnet|d5a49f5dc9ef463270857c15836276bd139de902ac1a518b3d8a275ea4be3d5f|6c1b7f210dd66e457a5a659ff6e8d754dafdfd7561fa4a5c7de0dbcf47233170
/resources/cosmosDBAccount/properties/parameters/virtualNetworkSubnetIds|vnet|450c88b174cda16df85f37314f2118ecdcde7ff3b76acc915de73f7c3078e03c|ea1f0952b683770ba2e2334e0e5365e68a3ba621d35f09610605949f11ce9eb7
/resources/publicIngressM/properties/parameters/appGatewaySubnetResourceId/value|vnet|77ce52cbb321176514da7cb166ced969713627d7cf1803888bdf3cc66e8f47fa|e4a28a8c6b992c85a7a92227de1751c1c6cd737b98bd854872afce4e2ab31e4f
/outputs/APP_GATEWAY_SUBNET_RESOURCE_ID/value|vnet|860007eed2fc170e5ad4ae4e5635f0bc30cf75bc4922ab80f4ee1c3320872fe0|bd5fc249197543d9b908319ff3c83a5e09b7c0114b44bbfddc2f16e335e1e31e
/outputs/VNET_RESOURCE_ID/value|vnet|58a3319573c13eddab11c4f9571d1ed620cddc934397de77f86badb9d85fbc85|f4c2c7f6257cf6a9328c3da49fcc4d6249873107a7d2e9e54a52a7e9210495b3
/outputs/HOSTED_AGENT_DEPLOYMENT/value/workloadEgress/subnets/containerapp|vnet|f83984b9ff528925320da35283d837d237db9f5794a740fae8c77bd364cfc004|e8b586dee8341ea5abeed03cf6255e55a50775c7111fd818fe0ef9634e2621c8
/outputs/HOSTED_AGENT_DEPLOYMENT/value/workloadEgress/subnets/azure.ai.agent|vnet|a6cb7fcd7c36d4d5b25f9230d607626e2ee61f4ffc3ce1ab18621088d27322a4|e13db86a5233da86cb76238853067a98761a06fdab097ccf88fcbb3247b23e6c
/outputs/HOSTED_AGENT_DEPLOYMENT/value/foundry|vnet|7505ad2f573bd71cc2bec055bd7de6270cfb04e8847cf68042eca22b4076b7c4|ce0d1924cbe72ebd1b9fac7b431366d5792b1b192bf8d6fde6d9c890c778df71
/outputs/HOSTED_AGENT_DEPLOYMENT/value/privateBuild/subnetResourceId|vnet|34f5ddab99e503e884222465bc0b51ea8c80063436a4a65858a92e5e746eb350|83bfec24684a8f2ead1086863899ec326b1d172973ed8a43c69c6afc1bae9b8f
'@ -split '\r?\n' | ForEach-Object {
        $p = $_ -split '\|'
        @{ path = $p[0]; kind = $p[1]; after = $p[2]; before = $p[3] }
    }
}

function ConvertTo-PrePostgreSqlGraph($Template) {
    $copy = ConvertTo-Json -InputObject $Template -Depth 100 -Compress | ConvertFrom-Json -AsHashtable -Depth 100
    foreach ($rule in Get-PostgreSqlDelta) {
        $parts = $rule.path.TrimStart('/').Split('/')
        $parent = $copy
        foreach ($part in $parts[0..($parts.Length - 2)]) {
            if ($parent -is [array]) { $parent = $parent[[int]$part] }
            else { $parent = $parent[$part] }
        }
        $key = $parts[-1]
        if ($parent -isnot [System.Collections.IDictionary] -or -not $parent.Contains($key)) {
            throw "SCOPED: missing PostgreSQL delta at $($rule.path)."
        }
        $value = $parent[$key]
        if ((Get-PostgreSqlDigest $value) -cne $rule.after) {
            throw "SCOPED: unreviewed PostgreSQL delta at $($rule.path)."
        }
        if ($rule.kind -ceq 'added') { $null = $parent.Remove($key); continue }
        $before = switch ($rule.kind) {
            'vnet' { $value.Replace("variables('_acaVnetIntegration')", "variables('_networkIsolation')") }
            'dependencies' { ,@($value | Where-Object { $_ -cnotin @('containerAppsPostgreSqlNat', 'containerAppsPostgreSqlSubnet', 'postgreSqlValidation') }) }
            'loop' { ,@($value | Where-Object name -CNE '_postgreSqlOperatorRules') }
            'special' {
                switch ($rule.path) {
                    '/variables/subnetDefinitions/9/required' {
                        $value.Replace("or(parameters('deployPostgreSql'), parameters('deployCosmosDb'))", "parameters('deployCosmosDb')")
                    }
                    '/variables/selectedSubnetDefinitions' {
                        $value.Replace("or(variables('_networkIsolation'), and(variables('_postgreSqlBasic'), equals(lambdaVariables('subnet').purpose, 'acaEnvironment')))", "variables('_networkIsolation')")
                    }
                    '/variables/_dnsZonesList' {
                        $value.Replace("if(and(parameters('deployPostgreSql'), not(variables('_byoZonePostgreSql'))), createArray(createObject('dnsName', 'privatelink.postgres.database.azure.com', 'virtualNetworkLinkName', format('{0}-postgresql-link{1}', variables('resourceNames').vnetName, variables('_dnsZonesLinkSuffix')))), createArray()), ", '')
                    }
                    '/resources/networkLayoutValidation/properties/parameters/subnetDefinitions/value' {
                        $value.Replace("filter(variables('subnetDefinitions'), lambda('subnet', or(variables('_networkIsolation'), equals(lambdaVariables('subnet').purpose, 'acaEnvironment'))))", "variables('subnetDefinitions')")
                    }
                    '/resources/containerEnv/properties/parameters/properties/value/vnetConfiguration' {
                        $v = $value.Replace("variables('_acaVnetIntegration')", "variables('_networkIsolation')").Replace("'internal', variables('_networkIsolation')", "'internal', true()")
                        "[if(parameters('networkIsolation')," + $v.Substring("[if(variables('_networkIsolation'),".Length)
                    }
                    default {
                        if ($rule.path -cnotin @('/resources/virtualNetwork/properties/parameters/subnets/value', '/resources/virtualNetworkSubnets/properties/parameters/subnets/value')) {
                            throw "SCOPED: unknown PostgreSQL inverse at $($rule.path)."
                        }
                        $value.Replace("if(and(equals(lambdaVariables('subnet').purpose, 'acaEnvironment'), variables('_postgreSqlBasic')), reference('containerAppsPostgreSqlNat').outputs.resourceId.value, '')", "''")
                    }
                }
            }
            default { throw "SCOPED: unknown PostgreSQL rule $($rule.kind)." }
        }
        if ((Get-PostgreSqlDigest $before) -cne $rule.before) {
            throw "SCOPED: PostgreSQL inverse does not restore original at $($rule.path)."
        }
        $parent[$key] = $before
    }
    return $copy
}
