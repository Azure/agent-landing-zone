"""Native types for the public foundation input boundary (camelCase).

This is not a second default catalogue: omitted values use the selected root's
defaults; null name/token/password values remain root-resolved. Contract tests
compare these names and scalar kinds with all current foundation declarations.
Open collection members are retained, never projected into lossy object types.
"""

from __future__ import annotations

from typing import Literal

InputKind = Literal["string", "bool", "int", "array", "object"]

_GROUPS: dict[InputKind, str] = {
    "bool": """
        networkIsolation policyManagedPrivateDns useExistingVNet
        deployAgentSubnet deployPeSubnet deployApplicationPeSubnet
        deployAzureBastionSubnet deployAzureFirewallSubnet deployGatewaySubnet
        deployAzureFirewallManagementSubnet
        deployAppGatewaySubnet deployJumpboxSubnet deployAcaEnvironmentSubnet
        deployDevopsBuildAgentsSubnet deployPowerPlatformSubnet deployAiGatewaySubnet
        deployGroundingWithBing deployAiFoundry deployAiFoundrySubnet deployAppConfig
        deployKeyVault deployVmKeyVault deployLogAnalytics enablePrivateLogAnalytics
        deployAppInsights allowMixedObservabilityWorkspaces hubIntegrationCreateHubPeering
        hubIntegrationPeeringAllowGatewayTransit hubIntegrationPeeringUseRemoteGateways
        deploySearchService deploySpeechService deployStorageAccount
        storageAccountAllowSharedKeyAccess deployCosmosDb deployContainerApps
        deployContainerRegistry deployContainerEnv deploySubnets deployNsgs
        deployAzureFirewall enableFirewallDnsProxy deployAcrTaskAgentPool
        prepareHostedAgent grantHostedAgentProjectManager deployHostedAgent
        extendFirewallForJumpboxBootstrap extendFirewallForAcrTaskBuilds
        bastionEnableTunneling enableAcsMediaEgress sideBySideDeploy deploySoftware
        deployAfProject deployAAfAgentSvc aiFoundryDisableLocalAuth enableAgenticRetrieval
        foundryIqIsAdlsGen2 foundryIqFilterAddOnEnabled useUAI useCAppAPIKey
        useZoneRedundancy enableCosmosAnalyticalStorage
        deployJumpbox deployBastion deployNatGateway deployVM
    """,
    "int": "acrTaskAgentPoolCount dbDatabaseThroughput",
    "array": """
        allowedIpRanges vnetAddressPrefixes additionalAcrTaskBuildFqdns
        bastionAllowedSourceIPs foundryIqIngestionPermissionOptions
        foundryIqSourceDataFields foundryIqSearchFields modelDeploymentList
        containerAppsList workloadProfiles databaseContainersList storageAccountContainersList
        additionalAppConfigurationSettings storageAccountResourceAccessRules
    """,
    "object": "deploymentTags publicIngress hostedAgent",
    "string": """
        environmentName applicationResourceGroupName networkResourceGroupName
        location cosmosLocation searchServiceLocation speechServiceLocation
        principalId principalType appConfigLabel deploymentMode privateEndpointLocation
        privateEndpointResourceGroupName existingVnetResourceId agentSubnetName peSubnetName
        applicationPeSubnetName applicationPeSubnetPrefix gatewaySubnetName azureBastionSubnetName
        azureFirewallSubnetName azureFirewallSku azureFirewallManagementSubnetName
        azureFirewallManagementSubnetPrefix azureAppGatewaySubnetName jumpboxSubnetName acaEnvironmentSubnetName
        devopsBuildAgentsSubnetName powerPlatformSubnetName aiGatewaySubnetName powerPlatformSubnetPrefix
        aiGatewaySubnetPrefix dnsZoneLinkSuffix agentSubnetPrefix acaEnvironmentSubnetPrefix
        peSubnetPrefix azureBastionSubnetPrefix azureFirewallSubnetPrefix gatewaySubnetPrefix
        azureAppGatewaySubnetPrefix jumpboxSubnetPrefix devopsBuildAgentsSubnetPrefix
        appRuntimeConfigurationMode speechServiceSku hostedAgentContainerRegistryResourceId
        hostedAgentContainerRegistryEndpoint hostedAgentContainerRegistryRoleAssignmentMode
        acrTaskAgentPoolName acrTaskAgentPoolTier bastionSkuName retrievalBackend foundryIqPattern
        foundryIqApiVersion foundryIqKnowledgeRetrievalBillingPlan knowledgeBaseName
        knowledgeBaseConnectionName foundryIqKnowledgeSourceName foundryIqKnowledgeSourceKind
        foundryIqStorageContainerName foundryIqStorageFolderPath foundryIqContentExtractionMode
        foundryIqAiServicesEndpoint foundryIqIngestionPermissionOptionsJson foundryIqSearchIndexName
        foundryIqSemanticConfigurationName foundryIqBaseFilter foundryIqSecurityFieldName
        foundryIqMaxOutputDocuments aiSearchResourceId aiFoundryStorageAccountResourceId
        aiFoundryStorageSku aiFoundryCosmosDBAccountResourceId keyVaultResourceId resourceToken
        resourceNamingMode cafWorkloadName cafEnvironmentName cafRegionName cafInstance
        aiFoundryAccountName aiFoundryProjectName aiFoundryStorageAccountName aiFoundrySearchServiceName
        aiFoundryCosmosDbName bingSearchName appConfigName appInsightsName containerEnvName
        containerRegistryName dbAccountName dbDatabaseName keyVaultName logAnalyticsWorkspaceName
        searchServiceName speechServiceName storageAccountName vnetName acrDnsSuffix vmName vmUserName
        vmAdminPassword vmSize vmImageSku vmImagePublisher vmImageOffer vmImageVersion
        existingPrivateDnsZoneCogSvcsResourceId existingPrivateDnsZoneOpenAiResourceId
        existingPrivateDnsZoneAiServicesResourceId existingPrivateDnsZoneSearchResourceId
        existingPrivateDnsZoneCosmosResourceId existingPrivateDnsZoneBlobResourceId
        existingPrivateDnsZoneKeyVaultResourceId existingPrivateDnsZoneAppConfigResourceId
        existingPrivateDnsZoneContainerAppsResourceId existingPrivateDnsZoneAcrResourceId
        existingPrivateDnsZoneAzureMonitorResourceId existingPrivateDnsZoneOmsOpsInsightsResourceId
        existingPrivateDnsZoneOdsOpsInsightsResourceId existingPrivateDnsZoneAzureAutomationResourceId
        existingPrivateDnsZoneAppInsightsResourceId existingLogAnalyticsWorkspaceResourceId
        existingApplicationInsightsResourceId existingApplicationInsightsConnectionString
        hubIntegrationEgressNextHopIp hubIntegrationExistingRouteTableResourceId
        hubIntegrationHubVnetResourceId existingBastionResourceId existingNatGatewayResourceId
        existingJumpboxResourceId aiFoundryProjectDisplayName aiFoundryProjectDescription
        storageAccountNetworkAclsBypass
    """,
}

INPUT_TYPES: dict[str, InputKind] = {
    name: kind for kind, names in _GROUPS.items() for name in names.split()
}
NULLABLE_BOOLEANS = frozenset({
    "deployJumpbox", "deployBastion", "deployNatGateway", "deployVM",
    "deployAzureFirewallSubnet", "deployAzureFirewallManagementSubnet",
})
