# Product inputs retain the Bicep camelCase contract. Defaults here are the
# effective Agent Landing Zone defaults, not the reusable Bicep module defaults.
variable "subscriptionId" {
  type        = string
  description = "Selected Azure subscription; must agree with the provider and azd context."
  nullable    = false
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscriptionId))
    error_message = "subscriptionId must be an Azure subscription UUID."
  }
}
variable "tenantId" {
  type        = string
  default     = null
  description = "Optional tenant binding, checked against the authenticated provider."
}
variable "azureCloud" {
  type = object({
    environment        = string
    storage_dns_suffix = string
  })
  default = {
    environment        = "public"
    storage_dns_suffix = "core.windows.net"
  }
  nullable    = false
  description = "Native Azure cloud context resolved by the adapter; independent of the ACR DNS override and not a runtime setting."
  validation {
    # Provider environment names come from the installed AzureRM 4.81 schema;
    # storage suffixes match Azure CLI azure/cli/core/cloud.py KNOWN_CLOUDS.
    condition = try({
      public       = "core.windows.net"
      usgovernment = "core.usgovcloudapi.net"
      china        = "core.chinacloudapi.cn"
    }[var.azureCloud.environment] == var.azureCloud.storage_dns_suffix, false)
    error_message = "azureCloud must pair public/core.windows.net, usgovernment/core.usgovcloudapi.net, or china/core.chinacloudapi.cn."
  }
}
variable "resourceGroupName" {
  type        = string
  nullable    = false
  description = "Root/Foundry resource group; ownership is explicit in createResourceGroup."
  validation {
    condition     = length(trimspace(var.resourceGroupName)) > 0
    error_message = "resourceGroupName cannot be empty."
  }
}
variable "deploymentName" {
  type        = string
  default     = null
  description = "Stable diagnostic correlation name; defaults to the environment name."
}
variable "existingVnetSubscriptionId" {
  type        = string
  default     = null
  description = "Explicit subscription for the existing-network provider alias."
}
variable "createResourceGroup" {
  type        = bool
  default     = false
  nullable    = false
  description = "Create and own the root group. False means lookup only; no implicit import."
}
variable "createApplicationResourceGroup" {
  type        = bool
  default     = false
  nullable    = false
  description = "Create and own a distinct application group; ignored when it is the root group."
}
variable "createNetworkResourceGroup" {
  type        = bool
  default     = false
  nullable    = false
  description = "Create and own a distinct networking group; ignored when it is the root group."
}
variable "environmentName" {
  type     = string
  nullable = false
  validation {
    condition     = length(trimspace(var.environmentName)) > 0
    error_message = "environmentName cannot be empty."
  }
}
variable "applicationResourceGroupName" {
  type    = string
  default = ""
}
variable "networkResourceGroupName" {
  type    = string
  default = ""
}
variable "location" {
  type        = string
  default     = null
  description = "Azure location; lookup-owned roots may inherit their group location."
}
variable "cosmosLocation" {
  type    = string
  default = null
}
variable "searchServiceLocation" {
  type    = string
  default = ""
}
variable "speechServiceLocation" {
  type    = string
  default = ""
}
variable "principalId" {
  type     = string
  nullable = false
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.principalId))
    error_message = "principalId must be an Entra object UUID, not an application name or client credential."
  }
}
variable "principalType" {
  type     = string
  default  = "User"
  nullable = false
  validation {
    condition     = contains(["User", "Group", "ServicePrincipal"], var.principalType)
    error_message = "principalType must be User, Group or ServicePrincipal."
  }
}
variable "deploymentTags" {
  type     = map(string)
  default  = {}
  nullable = false
}
variable "appConfigLabel" {
  type     = string
  default  = "agent-lz"
  nullable = false
}
variable "additionalAppConfigurationSettings" {
  type = list(object({
    name        = string
    value       = string
    label       = optional(string)
    contentType = optional(string, "text/plain")
  }))
  default  = []
  nullable = false
  validation {
    condition     = length(distinct([for s in var.additionalAppConfigurationSettings : jsonencode([s.name, s.label == null ? var.appConfigLabel : s.label])])) == length(var.additionalAppConfigurationSettings)
    error_message = "Additional App Configuration name/label pairs must be unique."
  }
}
variable "networkIsolation" {
  type     = bool
  default  = false
  nullable = false
}
variable "deploymentMode" {
  type     = string
  default  = "standalone"
  nullable = false
  validation {
    condition     = contains(["standalone", "ailz-integrated"], var.deploymentMode)
    error_message = "deploymentMode must be standalone or ailz-integrated."
  }
}
variable "allowedIpRanges" {
  type     = list(string)
  default  = []
  nullable = false
}
variable "policyManagedPrivateDns" {
  type     = bool
  default  = false
  nullable = false
}
variable "existingPrivateDnsZoneCogSvcsResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneOpenAiResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneAiServicesResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneSearchResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneCosmosResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneBlobResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneKeyVaultResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneAppConfigResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneContainerAppsResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneAcrResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneAzureMonitorResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneOmsOpsInsightsResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneOdsOpsInsightsResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneAzureAutomationResourceId" {
  type    = string
  default = null
}
variable "existingPrivateDnsZoneAppInsightsResourceId" {
  type    = string
  default = null
}
variable "privateEndpointLocation" {
  type    = string
  default = ""
}
variable "privateEndpointResourceGroupName" {
  type    = string
  default = ""
}
variable "useExistingVNet" {
  type     = bool
  default  = false
  nullable = false
}
variable "existingVnetResourceId" {
  type     = string
  default  = ""
  nullable = false
}
variable "agentSubnetName" {
  type     = string
  default  = "agent-subnet"
  nullable = false
}
variable "peSubnetName" {
  type     = string
  default  = "pe-subnet"
  nullable = false
}
variable "applicationPeSubnetName" {
  type     = string
  default  = "application-pe-subnet"
  nullable = false
}
variable "applicationPeSubnetPrefix" {
  type     = string
  default  = "192.168.3.128/26"
  nullable = false
}
variable "gatewaySubnetName" {
  type     = string
  default  = "GatewaySubnet"
  nullable = false
}
variable "azureBastionSubnetName" {
  type     = string
  default  = "AzureBastionSubnet"
  nullable = false
}
variable "azureFirewallSubnetName" {
  type     = string
  default  = "AzureFirewallSubnet"
  nullable = false
}
variable "azureAppGatewaySubnetName" {
  type     = string
  default  = "AppGatewaySubnet"
  nullable = false
}
variable "jumpboxSubnetName" {
  type     = string
  default  = "jumpbox-subnet"
  nullable = false
}
variable "acaEnvironmentSubnetName" {
  type     = string
  default  = "aca-environment-subnet"
  nullable = false
}
variable "devopsBuildAgentsSubnetName" {
  type     = string
  default  = "devops-build-agents-subnet"
  nullable = false
}
variable "powerPlatformSubnetName" {
  type     = string
  default  = "powerplatform-subnet"
  nullable = false
}
variable "aiGatewaySubnetName" {
  type     = string
  default  = "ai-gateway-subnet"
  nullable = false
}
variable "powerPlatformSubnetPrefix" {
  type     = string
  default  = "192.168.4.0/24"
  nullable = false
}
variable "aiGatewaySubnetPrefix" {
  type     = string
  default  = "192.168.5.0/24"
  nullable = false
}
variable "deployAgentSubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployPeSubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployApplicationPeSubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployAzureBastionSubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployAzureFirewallSubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployGatewaySubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployAppGatewaySubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployJumpboxSubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployAcaEnvironmentSubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployDevopsBuildAgentsSubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployPowerPlatformSubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployAiGatewaySubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "vnetAddressPrefixes" {
  type     = list(string)
  default  = ["192.168.0.0/21"]
  nullable = false
  validation {
    condition     = length(var.vnetAddressPrefixes) > 0 && alltrue([for p in var.vnetAddressPrefixes : can(cidrhost(p, 0))])
    error_message = "vnetAddressPrefixes must contain valid CIDRs."
  }
}
variable "dnsZoneLinkSuffix" {
  type     = string
  default  = ""
  nullable = false
}
variable "agentSubnetPrefix" {
  type     = string
  default  = "192.168.0.0/24"
  nullable = false
}
variable "acaEnvironmentSubnetPrefix" {
  type     = string
  default  = "192.168.1.0/24"
  nullable = false
}
variable "peSubnetPrefix" {
  type     = string
  default  = "192.168.2.0/26"
  nullable = false
}
variable "azureBastionSubnetPrefix" {
  type     = string
  default  = "192.168.2.64/26"
  nullable = false
}
variable "azureFirewallSubnetPrefix" {
  type     = string
  default  = "192.168.2.128/26"
  nullable = false
}
variable "gatewaySubnetPrefix" {
  type     = string
  default  = "192.168.2.192/26"
  nullable = false
}
variable "azureAppGatewaySubnetPrefix" {
  type     = string
  default  = "192.168.3.0/27"
  nullable = false
}
variable "jumpboxSubnetPrefix" {
  type     = string
  default  = "192.168.3.64/27"
  nullable = false
}
variable "devopsBuildAgentsSubnetPrefix" {
  type     = string
  default  = "192.168.3.96/27"
  nullable = false
}
variable "deployGroundingWithBing" {
  type     = bool
  default  = false
  nullable = false
}
variable "deployAiFoundry" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployAiFoundrySubnet" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployAppConfig" {
  type     = bool
  default  = true
  nullable = false
}
variable "appRuntimeConfigurationMode" {
  type     = string
  default  = "appConfig"
  nullable = false
  validation {
    condition     = contains(["appConfig", "containerEnv", "none"], var.appRuntimeConfigurationMode)
    error_message = "appRuntimeConfigurationMode must be appConfig, containerEnv or none."
  }
}
variable "deployKeyVault" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployVmKeyVault" {
  type     = bool
  default  = false
  nullable = false
}
variable "deployLogAnalytics" {
  type     = bool
  default  = true
  nullable = false
}
variable "existingLogAnalyticsWorkspaceResourceId" {
  type    = string
  default = null
}
variable "enablePrivateLogAnalytics" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployAppInsights" {
  type     = bool
  default  = true
  nullable = false
}
variable "existingApplicationInsightsResourceId" {
  type    = string
  default = null
}
variable "existingApplicationInsightsConnectionString" {
  type      = string
  default   = null
  sensitive = true
}
variable "allowMixedObservabilityWorkspaces" {
  type     = bool
  default  = false
  nullable = false
}
variable "hubIntegrationEgressNextHopIp" {
  type    = string
  default = null
}
variable "hubIntegrationExistingRouteTableResourceId" {
  type    = string
  default = null
}
variable "hubIntegrationHubVnetResourceId" {
  type    = string
  default = null
}
variable "hubIntegrationCreateHubPeering" {
  type     = bool
  default  = true
  nullable = false
}
variable "hubIntegrationPeeringAllowGatewayTransit" {
  type     = bool
  default  = false
  nullable = false
}
variable "hubIntegrationPeeringUseRemoteGateways" {
  type     = bool
  default  = false
  nullable = false
}
variable "deploySearchService" {
  type     = bool
  default  = true
  nullable = false
}
variable "deploySpeechService" {
  type     = bool
  default  = false
  nullable = false
}
variable "speechServiceSku" {
  type     = string
  default  = "S0"
  nullable = false
  validation {
    condition     = contains(["F0", "S0"], var.speechServiceSku)
    error_message = "speechServiceSku must be F0 or S0."
  }
}
variable "deployStorageAccount" {
  type     = bool
  default  = true
  nullable = false
}
variable "storageAccountNetworkAclsBypass" {
  type     = string
  default  = "AzureServices"
  nullable = false
  validation {
    condition     = contains(["None", "AzureServices", "Logging", "Metrics", "AzureServices, Logging", "AzureServices, Metrics", "AzureServices, Logging, Metrics", "Logging, Metrics"], var.storageAccountNetworkAclsBypass)
    error_message = "storageAccountNetworkAclsBypass must be a supported Azure Storage bypass combination."
  }
}
variable "storageAccountResourceAccessRules" {
  type     = list(object({ resourceId = string, tenantId = string }))
  default  = []
  nullable = false
}
variable "storageAccountAllowSharedKeyAccess" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployCosmosDb" {
  type        = bool
  default     = false
  nullable    = false
  description = "Deploy application Cosmos DB for selected consumers; does not control Foundry Agent Service backing storage."
}
variable "deployContainerApps" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployContainerRegistry" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployContainerEnv" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployJumpbox" {
  type    = bool
  default = null
}
variable "deployBastion" {
  type    = bool
  default = null
}
variable "deployNatGateway" {
  type    = bool
  default = null
}
variable "existingBastionResourceId" {
  type    = string
  default = null
}
variable "existingNatGatewayResourceId" {
  type    = string
  default = null
}
variable "existingJumpboxResourceId" {
  type    = string
  default = null
}
variable "deployVM" {
  type    = bool
  default = true
}
variable "deploySubnets" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployNsgs" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployAzureFirewall" {
  type     = bool
  default  = true
  nullable = false
}
variable "enableFirewallDnsProxy" {
  type     = bool
  default  = false
  nullable = false
}
variable "deployAcrTaskAgentPool" {
  type     = bool
  default  = true
  nullable = false
}
variable "prepareHostedAgent" {
  type     = bool
  default  = false
  nullable = false
}
variable "grantHostedAgentProjectManager" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployHostedAgent" {
  type     = bool
  default  = false
  nullable = false
}
variable "hostedAgent" {
  type = object({
    name           = string
    image          = string
    version        = string
    startupCommand = string
    runtime        = object({ cpu = string, memory = string })
    protocols      = list(object({ protocol = string, version = optional(string) }))
  })
  default = {
    name           = "agent-app-orchestrator"
    image          = "agent-app-orchestrator"
    version        = ""
    startupCommand = "uvicorn src.api.hosted_entrypoint:app --host 0.0.0.0 --port 8088"
    runtime        = { cpu = "2", memory = "4Gi" }
    protocols      = [{ protocol = "responses", version = "2.0.0" }, { protocol = "invocations", version = "1.0.0" }]
  }
  nullable = false
  validation {
    condition = (
      can(tonumber(var.hostedAgent.runtime.cpu)) &&
      try(tonumber(var.hostedAgent.runtime.cpu) >= 0.25 && tonumber(var.hostedAgent.runtime.cpu) <= 4, false) &&
      can(regex("^([0-9]+(\\.[0-9]+)?)Gi$", var.hostedAgent.runtime.memory)) &&
      try(tonumber(trimsuffix(var.hostedAgent.runtime.memory, "Gi")) >= 0.5 && tonumber(trimsuffix(var.hostedAgent.runtime.memory, "Gi")) <= 8, false) &&
      length(var.hostedAgent.protocols) > 0 &&
      alltrue([for p in var.hostedAgent.protocols : contains(["responses", "invocations", "invocations_ws", "a2a"], p.protocol)])
    )
    error_message = "Hosted runtime requires CPU 0.25..4, memory 0.5Gi..8Gi and supported protocols."
  }
}
variable "hostedAgentContainerRegistryResourceId" {
  type     = string
  default  = ""
  nullable = false
}
variable "hostedAgentContainerRegistryEndpoint" {
  type     = string
  default  = ""
  nullable = false
}
variable "hostedAgentContainerRegistryRoleAssignmentMode" {
  type     = string
  default  = "rbac"
  nullable = false
  validation {
    condition     = contains(["rbac", "rbac-abac"], var.hostedAgentContainerRegistryRoleAssignmentMode)
    error_message = "Registry role assignment mode must be rbac or rbac-abac."
  }
}
variable "acrTaskAgentPoolName" {
  type     = string
  default  = "build-pool"
  nullable = false
  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9-]{0,19}$", var.acrTaskAgentPoolName))
    error_message = "ACR pool name must be alphanumeric/hyphen and at most 20 characters."
  }
}
variable "acrTaskAgentPoolTier" {
  type     = string
  default  = "S1"
  nullable = false
  validation {
    condition     = contains(["S1", "S2", "S3"], var.acrTaskAgentPoolTier)
    error_message = "ACR pool tier must be S1, S2 or S3."
  }
}
variable "acrTaskAgentPoolCount" {
  type     = number
  default  = 1
  nullable = false
  validation {
    condition     = var.acrTaskAgentPoolCount >= 0 && floor(var.acrTaskAgentPoolCount) == var.acrTaskAgentPoolCount
    error_message = "ACR pool count must be a nonnegative integer."
  }
}
variable "extendFirewallForJumpboxBootstrap" {
  type     = bool
  default  = true
  nullable = false
}
variable "extendFirewallForAcrTaskBuilds" {
  type     = bool
  default  = true
  nullable = false
}
variable "additionalAcrTaskBuildFqdns" {
  type     = list(string)
  default  = []
  nullable = false
}
variable "bastionAllowedSourceIPs" {
  type     = list(string)
  default  = []
  nullable = false
}
variable "bastionSkuName" {
  type     = string
  default  = "Standard"
  nullable = false
  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.bastionSkuName)
    error_message = "Bastion SKU must be Basic, Standard or Premium."
  }
}
variable "bastionEnableTunneling" {
  type     = bool
  default  = false
  nullable = false
}
variable "enableAcsMediaEgress" {
  type     = bool
  default  = false
  nullable = false
}
variable "publicIngress" {
  type = object({
    enabled                      = bool
    backendAppIndex              = optional(number, 0)
    frontendHostName             = optional(string, "")
    sslCertSecretId              = optional(string, "")
    allowedSourceAddressPrefixes = optional(list(string), [])
    wafMode                      = optional(string, "Prevention")
    # Deliberately open ARM extension subtrees, not an untyped root input.
    # AVM/AzAPI passes these through without dropping custom match conditions.
    wafCustomRules = optional(any, [])
    capacity       = optional(object({ minCapacity = number, maxCapacity = number }), { minCapacity = 0, maxCapacity = 2 })
    sslPolicy      = optional(any)
  })
  default  = { enabled = false }
  nullable = false
  validation {
    condition = (
      contains(["Detection", "Prevention"], var.publicIngress.wafMode) &&
      var.publicIngress.backendAppIndex >= 0 && floor(var.publicIngress.backendAppIndex) == var.publicIngress.backendAppIndex &&
      var.publicIngress.capacity.minCapacity >= 0 && var.publicIngress.capacity.maxCapacity >= var.publicIngress.capacity.minCapacity
    )
    error_message = "Public ingress requires a valid WAF mode, nonnegative integer backend index and valid capacity range."
  }
}
variable "sideBySideDeploy" {
  type     = bool
  default  = true
  nullable = false
}
variable "deploySoftware" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployAfProject" {
  type     = bool
  default  = true
  nullable = false
}
variable "deployAAfAgentSvc" {
  type     = bool
  default  = true
  nullable = false
}
variable "aiFoundryDisableLocalAuth" {
  type     = bool
  default  = true
  nullable = false
}
variable "enableAgenticRetrieval" {
  type     = bool
  default  = false
  nullable = false
}
variable "retrievalBackend" {
  type     = string
  default  = "foundry_iq"
  nullable = false
  validation {
    condition     = contains(["ai_search", "foundry_iq"], var.retrievalBackend)
    error_message = "retrievalBackend must be ai_search or foundry_iq."
  }
}
variable "foundryIqPattern" {
  type     = string
  default  = "azureBlob"
  nullable = false
  validation {
    condition     = contains(["azureBlob", "managed", "searchIndex"], var.foundryIqPattern)
    error_message = "foundryIqPattern must be azureBlob, managed or searchIndex."
  }
}
variable "foundryIqApiVersion" {
  type     = string
  default  = "2026-05-01-preview"
  nullable = false
}
variable "foundryIqKnowledgeRetrievalBillingPlan" {
  type     = string
  default  = "free"
  nullable = false
  validation {
    condition     = contains(["free", "standard"], var.foundryIqKnowledgeRetrievalBillingPlan)
    error_message = "Knowledge retrieval billing plan must be free or standard."
  }
}
variable "knowledgeBaseName" {
  type     = string
  default  = "knowledge-base"
  nullable = false
}
variable "knowledgeBaseConnectionName" {
  type     = string
  default  = "knowledge-base-connection"
  nullable = false
}
variable "foundryIqKnowledgeSourceName" {
  type     = string
  default  = "knowledge-base-blob-ks"
  nullable = false
}
variable "foundryIqKnowledgeSourceKind" {
  type     = string
  default  = "azureBlob"
  nullable = false
  validation {
    condition     = contains(["", "azureBlob", "searchIndex"], var.foundryIqKnowledgeSourceKind)
    error_message = "Knowledge source kind must be empty, azureBlob or searchIndex."
  }
}
variable "foundryIqStorageContainerName" {
  type     = string
  default  = "documents"
  nullable = false
}
variable "foundryIqStorageFolderPath" {
  type     = string
  default  = ""
  nullable = false
}
variable "foundryIqIsAdlsGen2" {
  type     = bool
  default  = false
  nullable = false
}
variable "foundryIqContentExtractionMode" {
  type     = string
  default  = "standard"
  nullable = false
  validation {
    condition     = contains(["minimal", "standard"], var.foundryIqContentExtractionMode)
    error_message = "Content extraction mode must be minimal or standard."
  }
}
variable "foundryIqAiServicesEndpoint" {
  type     = string
  default  = ""
  nullable = false
}
variable "foundryIqIngestionPermissionOptions" {
  type     = list(string)
  default  = ["rbacScope"]
  nullable = false
}
variable "foundryIqIngestionPermissionOptionsJson" {
  type     = string
  default  = "[\"rbacScope\"]"
  nullable = false
  validation {
    condition     = var.foundryIqIngestionPermissionOptionsJson == "" || can(tolist(jsondecode(var.foundryIqIngestionPermissionOptionsJson)))
    error_message = "Ingestion permission options JSON must be empty or a JSON array."
  }
}
variable "foundryIqSearchIndexName" {
  type     = string
  default  = "agent-lz-index"
  nullable = false
}
variable "foundryIqSemanticConfigurationName" {
  type     = string
  default  = "default"
  nullable = false
}
variable "foundryIqSourceDataFields" {
  type     = list(string)
  default  = ["id", "title", "filepath", "url", "content"]
  nullable = false
}
variable "foundryIqSearchFields" {
  type     = list(string)
  default  = ["content"]
  nullable = false
}
variable "foundryIqBaseFilter" {
  type     = string
  default  = ""
  nullable = false
}
variable "foundryIqFilterAddOnEnabled" {
  type     = bool
  default  = false
  nullable = false
}
variable "foundryIqSecurityFieldName" {
  type     = string
  default  = "metadata_security_id"
  nullable = false
}
variable "foundryIqMaxOutputDocuments" {
  type     = string
  default  = ""
  nullable = false
}
variable "aiSearchResourceId" {
  type     = string
  default  = ""
  nullable = false
}
variable "aiFoundryStorageAccountResourceId" {
  type     = string
  default  = ""
  nullable = false
}
variable "aiFoundryStorageSku" {
  type     = string
  default  = "Standard_LRS"
  nullable = false
  validation {
    condition     = contains(["Standard_LRS", "Standard_GRS", "Standard_RAGRS", "Standard_ZRS", "Standard_GZRS", "Standard_RAGZRS", "Premium_LRS", "Premium_ZRS"], var.aiFoundryStorageSku)
    error_message = "aiFoundryStorageSku must be a supported storage SKU."
  }
}
variable "aiFoundryCosmosDBAccountResourceId" {
  type     = string
  default  = ""
  nullable = false
}
variable "keyVaultResourceId" {
  type     = string
  default  = ""
  nullable = false
}
variable "useUAI" {
  type     = bool
  default  = false
  nullable = false
}
variable "useCAppAPIKey" {
  type     = bool
  default  = false
  nullable = false
}
variable "useZoneRedundancy" {
  type     = bool
  default  = false
  nullable = false
}
variable "resourceToken" {
  type        = string
  default     = null
  description = "Optional stable lowercase alphanumeric token, 3..20 characters; not an ARM uniqueString."
  validation {
    condition     = var.resourceToken == null ? true : can(regex("^[a-z0-9]{3,20}$", var.resourceToken))
    error_message = "resourceToken must be null or 3..20 lowercase alphanumeric characters."
  }
}
variable "resourceNamingMode" {
  type     = string
  default  = "caf"
  nullable = false
  validation {
    condition     = contains(["caf", "legacy"], var.resourceNamingMode)
    error_message = "resourceNamingMode must be caf or legacy."
  }
}
variable "cafWorkloadName" {
  type     = string
  default  = ""
  nullable = false
}
variable "cafEnvironmentName" {
  type     = string
  default  = ""
  nullable = false
}
variable "cafRegionName" {
  type     = string
  default  = ""
  nullable = false
}
variable "cafInstance" {
  type     = string
  default  = "001"
  nullable = false
}
variable "aiFoundryAccountName" {
  type    = string
  default = null
}
variable "aiFoundryProjectName" {
  type    = string
  default = null
}
variable "aiFoundryProjectDisplayName" {
  type    = string
  default = null
}
variable "aiFoundryProjectDescription" {
  type    = string
  default = null
}
variable "aiFoundryStorageAccountName" {
  type    = string
  default = null
}
variable "aiFoundrySearchServiceName" {
  type    = string
  default = null
}
variable "aiFoundryCosmosDbName" {
  type    = string
  default = null
}
variable "bingSearchName" {
  type    = string
  default = null
}
variable "appConfigName" {
  type    = string
  default = null
}
variable "appInsightsName" {
  type    = string
  default = null
}
variable "containerEnvName" {
  type    = string
  default = null
}
variable "containerRegistryName" {
  type    = string
  default = null
}
variable "dbAccountName" {
  type    = string
  default = null
}
variable "dbDatabaseName" {
  type    = string
  default = null
}
variable "keyVaultName" {
  type    = string
  default = null
}
variable "logAnalyticsWorkspaceName" {
  type    = string
  default = null
}
variable "searchServiceName" {
  type    = string
  default = null
}
variable "speechServiceName" {
  type    = string
  default = null
}
variable "storageAccountName" {
  type    = string
  default = null
}
variable "vnetName" {
  type    = string
  default = null
}
variable "modelDeploymentList" {
  type = list(object({
    name           = string
    canonical_name = string
    apiVersion     = optional(string)
    model = object({
      format        = string
      name          = string
      version       = optional(string)
      source        = optional(string)
      sourceAccount = optional(string)
      publisher     = optional(string)
    })
    sku = object({
      name     = string
      capacity = optional(number)
      tier     = optional(string)
      size     = optional(string)
      family   = optional(string)
    })
    raiPolicyName            = optional(string)
    versionUpgradeOption     = optional(string)
    dynamicThrottlingEnabled = optional(bool)
    spilloverDeploymentName  = optional(string)
    capacitySettings         = optional(object({ designatedCapacity = optional(number), priority = optional(number) }))
    scaleSettings            = optional(object({ scaleType = optional(string), capacity = optional(number) }))
  }))
  default = [
    { name = "chat", model = { format = "OpenAI", name = "gpt-5-nano", version = "2025-08-07" }, sku = { name = "GlobalStandard", capacity = 100 }, canonical_name = "CHAT_DEPLOYMENT_NAME", apiVersion = "2025-12-01-preview" },
    { name = "text-embedding", model = { format = "OpenAI", name = "text-embedding-3-large", version = "1" }, sku = { name = "Standard", capacity = 100 }, canonical_name = "EMBEDDING_DEPLOYMENT_NAME", apiVersion = "2025-01-01-preview" }
  ]
  nullable = false
  validation {
    condition     = length(distinct([for m in var.modelDeploymentList : m.name])) == length(var.modelDeploymentList) && length(distinct([for m in var.modelDeploymentList : m.canonical_name])) == length(var.modelDeploymentList)
    error_message = "Model deployment names and canonical keys must be unique."
  }
}
variable "containerAppsList" {
  type = list(object({
    name           = optional(string)
    external       = bool
    service_name   = string
    profile_name   = string
    min_replicas   = number
    max_replicas   = number
    canonical_name = string
    roles          = list(string)
    image          = optional(string)
    cpu            = optional(number)
    memory         = optional(string)
    target_port    = optional(number, 8080)
    dapr = optional(object({
      enabled          = bool
      appId            = optional(string)
      appPort          = optional(number)
      appProtocol      = optional(string, "http")
      enableApiLogging = optional(bool, false)
    }))
  }))
  default = [
    { name = null, external = true, service_name = "orchestrator", profile_name = "main", min_replicas = 1, max_replicas = 1, canonical_name = "ORCHESTRATOR_APP", dapr = { enabled = true }, roles = ["AppConfigurationDataReader", "CognitiveServicesUser", "CognitiveServicesOpenAIUser", "AcrPull", "CosmosDBBuiltInDataContributor", "SearchIndexDataReader", "StorageBlobDataReader", "KeyVaultSecretsUser"] },
    { name = null, external = true, service_name = "frontend", profile_name = "main", min_replicas = 1, max_replicas = 1, canonical_name = "FRONTEND_APP", dapr = { enabled = true }, roles = ["AppConfigurationDataReader", "AcrPull", "StorageBlobDataReader", "StorageBlobDelegator", "KeyVaultSecretsUser"] },
    { name = null, external = true, service_name = "dataingest", profile_name = "main", min_replicas = 1, max_replicas = 1, cpu = 1, memory = "3.0Gi", canonical_name = "DATA_INGEST_APP", dapr = { enabled = true }, roles = ["AppConfigurationDataReader", "CognitiveServicesUser", "CognitiveServicesOpenAIUser", "CosmosDBBuiltInDataContributor", "AcrPull", "SearchIndexDataContributor", "StorageBlobDataContributor", "KeyVaultSecretsUser"] }
  ]
  nullable = false
  validation {
    condition = (
      length(distinct([for a in var.containerAppsList : a.service_name])) == length(var.containerAppsList) &&
      length(distinct([for a in var.containerAppsList : a.canonical_name])) == length(var.containerAppsList) &&
      alltrue([for a in var.containerAppsList : a.min_replicas >= 0 && a.max_replicas >= a.min_replicas && floor(a.min_replicas) == a.min_replicas && floor(a.max_replicas) == a.max_replicas && a.target_port >= 1 && a.target_port <= 65535 && floor(a.target_port) == a.target_port])
    )
    error_message = "Container Apps require unique service/canonical names, valid integer replica bounds and target ports."
  }
}
variable "workloadProfiles" {
  type = list(object({
    name                = string
    workloadProfileType = string
    minimumCount        = optional(number)
    maximumCount        = optional(number)
  }))
  default = [
    { name = "Consumption", workloadProfileType = "Consumption" },
    { name = "main", workloadProfileType = "D4", minimumCount = 0, maximumCount = 1 }
  ]
  nullable = false
}
variable "acrDnsSuffix" {
  type        = string
  default     = "azurecr.io"
  nullable    = false
  description = "Cloud-specific registry suffix; adapter supplies azurecr.us/azurecr.cn for sovereign clouds."
}
variable "dbDatabaseThroughput" {
  type    = number
  default = null
  validation {
    condition     = var.dbDatabaseThroughput == null ? true : var.dbDatabaseThroughput >= 400 && floor(var.dbDatabaseThroughput) == var.dbDatabaseThroughput
    error_message = "Database throughput must be null or an integer of at least 400 RU/s."
  }
}
variable "databaseContainersList" {
  type = list(object({
    name           = string
    canonical_name = string
    partitionKey   = string
    throughput     = optional(number)
    # Explicit nested types preserve heterogeneous per-container policies
    # without list(any)'s common-type conversion or an untyped root object.
    indexingPolicy = optional(object({
      automatic    = optional(bool)
      indexingMode = optional(string)
      includedPaths = optional(list(object({
        path = string
        indexes = optional(list(object({
          kind      = string
          dataType  = string
          precision = optional(number)
        })))
      })))
      excludedPaths    = optional(list(object({ path = string })))
      compositeIndexes = optional(list(list(object({ path = string, order = string }))))
      spatialIndexes = optional(list(object({
        path        = string
        types       = list(string)
        boundingBox = optional(object({ xmin = number, ymin = number, xmax = number, ymax = number }))
      })))
      vectorIndexes = optional(list(object({
        path                   = string
        type                   = string
        quantizationByteSize   = optional(number)
        indexingSearchListSize = optional(number)
        vectorIndexShardKey    = optional(list(string))
      })))
      fullTextIndexes = optional(list(object({ path = string })))
    }))
  }))
  default = [
    {
      name = "conversations", canonical_name = "CONVERSATIONS_DATABASE_CONTAINER", partitionKey = "/principal_id",
      indexingPolicy = { compositeIndexes = [
        [{ path = "/isDeleted", order = "Ascending" }, { path = "/_ts", order = "Descending" }],
        [{ path = "/isDeleted", order = "Ascending" }, { path = "/name", order = "Ascending" }, { path = "/_ts", order = "Descending" }]
      ] }
    },
    { name = "datasources", canonical_name = "DATASOURCES_DATABASE_CONTAINER", partitionKey = "/id" },
    { name = "prompts", canonical_name = "PROMPTS_CONTAINER", partitionKey = "/id" },
    { name = "mcp", canonical_name = "MCP_CONTAINER", partitionKey = "/id" }
  ]
  nullable = false
  validation {
    condition     = length(distinct([for c in var.databaseContainersList : c.name])) == length(var.databaseContainersList) && length(distinct([for c in var.databaseContainersList : c.canonical_name])) == length(var.databaseContainersList)
    error_message = "Database container names and canonical keys must be unique."
  }
}
variable "enableCosmosAnalyticalStorage" {
  type     = bool
  default  = false
  nullable = false
}
variable "vmName" {
  type    = string
  default = ""
}
variable "vmUserName" {
  type    = string
  default = ""
}
variable "vmAdminPassword" {
  type        = string
  sensitive   = true
  default     = null
  description = "Sensitive managed-jumpbox password override; null/empty requests persistent state-owned generation. Never commit generated inputs."
}
variable "vmSize" {
  type     = string
  default  = "Standard_D2s_v3"
  nullable = false
}
variable "vmImageSku" {
  type     = string
  default  = "2022-datacenter-azure-edition"
  nullable = false
}
variable "vmImagePublisher" {
  type     = string
  default  = "MicrosoftWindowsServer"
  nullable = false
}
variable "vmImageOffer" {
  type     = string
  default  = "WindowsServer"
  nullable = false
}
variable "vmImageVersion" {
  type     = string
  default  = "latest"
  nullable = false
}
variable "storageAccountContainersList" {
  type = list(object({
    name           = string
    canonical_name = string
  }))
  default = [
    { name = "documents-images", canonical_name = "DOCUMENTS_IMAGES_STORAGE_CONTAINER" },
    { name = "documents", canonical_name = "DOCUMENTS_STORAGE_CONTAINER" },
    { name = "conversation-cache", canonical_name = "CONVERSATION_CACHE_STORAGE_CONTAINER" },
    { name = "conversation-documents", canonical_name = "CONVERSATION_DOCUMENTS_STORAGE_CONTAINER" },
    { name = "nl2sql", canonical_name = "NL2SQL_STORAGE_CONTAINER" }
  ]
  nullable = false
  validation {
    condition     = length(distinct([for c in var.storageAccountContainersList : c.name])) == length(var.storageAccountContainersList) && length(distinct([for c in var.storageAccountContainersList : c.canonical_name])) == length(var.storageAccountContainersList)
    error_message = "Storage container names and canonical keys must be unique."
  }
}
