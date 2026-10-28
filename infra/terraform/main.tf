# Flat composition: domain files consume these locals in this same root module.
# No deployment or application publication is performed by this file.
data "azurerm_client_config" "root" {}

locals {
  application_rg = coalesce(var.applicationResourceGroupName, var.resourceGroupName)
  network_rg     = coalesce(var.networkResourceGroupName, var.resourceGroupName)
  # Names, not provider-returned IDs, are the known keys. A group shared by
  # multiple domains has one owner and one state entry.
  resource_group_definitions = merge(
    { (var.resourceGroupName) = { create = var.createResourceGroup } },
    local.application_rg == var.resourceGroupName ? {} : { (local.application_rg) = { create = var.createApplicationResourceGroup } },
    contains([var.resourceGroupName, local.application_rg], local.network_rg) ? {} : { (local.network_rg) = { create = var.createNetworkResourceGroup } }
  )
  root_location = try(coalesce(var.location, try(data.azurerm_resource_group.existing[var.resourceGroupName].location, null)), "")
}

data "azurerm_resource_group" "existing" {
  for_each = { for name, definition in local.resource_group_definitions : name => definition if !definition.create }
  name     = each.key
}

resource "azurerm_resource_group" "managed" {
  for_each = { for name, definition in local.resource_group_definitions : name => definition if definition.create }
  name     = each.key
  location = local.root_location
  tags     = local.tags
}

locals {
  manifest = jsondecode(file("${path.module}/../../manifest.json"))
  tags = merge({
    "azd-env-name" = var.environmentName
    deploymentMode = var.deploymentMode
  }, var.deploymentTags)
  resource_group_ids = merge(
    { for name, group in data.azurerm_resource_group.existing : name => group.id },
    { for name, group in azurerm_resource_group.managed : name => group.id }
  )
  deployment_context = {
    subscription_id   = var.subscriptionId
    tenant_id         = data.azurerm_client_config.root.tenant_id
    foundry_rg        = var.resourceGroupName
    application_rg    = local.application_rg
    network_rg        = local.network_rg
    foundry_rg_id     = local.resource_group_ids[var.resourceGroupName]
    application_rg_id = local.resource_group_ids[local.application_rg]
    network_rg_id     = local.resource_group_ids[local.network_rg]
    location          = local.root_location
    environment_name  = var.environmentName
    deployment_name   = coalesce(var.deploymentName, var.environmentName)
    storage_suffix    = var.azureCloud.storage_dns_suffix
    tags              = local.tags
  }
  effective_locations = {
    main             = local.root_location
    cosmos           = coalesce(var.cosmosLocation, local.root_location)
    search           = coalesce(var.searchServiceLocation, local.root_location)
    speech           = coalesce(var.speechServiceLocation, local.root_location)
    private_endpoint = coalesce(var.privateEndpointLocation, local.root_location)
  }
  # Terraform-native deterministic token. This is intentionally NOT presented
  # as ARM/Bicep uniqueString byte parity. No random resource or plan-time clock.
  resource_token = coalesce(var.resourceToken, substr(sha256(jsonencode([
    lower(var.subscriptionId), var.environmentName, lower(local.root_location)
  ])), 0, 13))

  abbreviations = jsondecode(file("${path.module}/../constants/abbreviations.json"))
  naming_definitions = {
    aiFoundryAccountName        = { prefix = local.abbreviations.ai.aiFoundry, max = 64, compact = false }
    aiFoundryProjectName        = { prefix = local.abbreviations.ai.aiFoundryProject, max = 64, compact = false }
    aiFoundryStorageAccountName = { prefix = "${local.abbreviations.storage.storageAccount}${local.abbreviations.ai.aiFoundry}", max = 24, compact = true }
    aiFoundrySearchServiceName  = { prefix = "${local.abbreviations.ai.aiSearch}${local.abbreviations.ai.aiFoundry}", max = 60, compact = false }
    aiFoundryCosmosDbName       = { prefix = "${local.abbreviations.databases.cosmosDBDatabase}${local.abbreviations.ai.aiFoundry}", max = 44, compact = false }
    bingSearchName              = { prefix = local.abbreviations.ai.bing, max = 64, compact = false }
    appConfigName               = { prefix = local.abbreviations.configuration.appConfiguration, max = 50, compact = false }
    appInsightsName             = { prefix = local.abbreviations.managementGovernance.applicationInsights, max = 64, compact = false }
    containerEnvName            = { prefix = local.abbreviations.containers.containerAppsEnvironment, max = 32, compact = false }
    containerRegistryName       = { prefix = local.abbreviations.containers.containerRegistry, max = 50, compact = true }
    dbAccountName               = { prefix = local.abbreviations.databases.cosmosDBDatabase, max = 44, compact = false }
    dbDatabaseName              = { prefix = "${local.abbreviations.databases.cosmosDBDatabase}db", max = 63, compact = false }
    keyVaultName                = { prefix = local.abbreviations.security.keyVault, max = 24, compact = false }
    logAnalyticsWorkspaceName   = { prefix = local.abbreviations.managementGovernance.logAnalyticsWorkspace, max = 63, compact = false }
    searchServiceName           = { prefix = local.abbreviations.ai.aiSearch, max = 60, compact = false }
    speechServiceName           = { prefix = local.abbreviations.ai.speechService, max = 64, compact = false }
    storageAccountName          = { prefix = local.abbreviations.storage.storageAccount, max = 24, compact = true }
    vnetName                    = { prefix = local.abbreviations.networking.virtualNetwork, max = 64, compact = false }
  }
  name_overrides = {
    aiFoundryAccountName        = var.aiFoundryAccountName
    aiFoundryProjectName        = var.aiFoundryProjectName
    aiFoundryStorageAccountName = var.aiFoundryStorageAccountName
    aiFoundrySearchServiceName  = var.aiFoundrySearchServiceName
    aiFoundryCosmosDbName       = var.aiFoundryCosmosDbName
    bingSearchName              = var.bingSearchName
    appConfigName               = var.appConfigName
    appInsightsName             = var.appInsightsName
    containerEnvName            = var.containerEnvName
    containerRegistryName       = var.containerRegistryName
    dbAccountName               = var.dbAccountName
    dbDatabaseName              = var.dbDatabaseName
    keyVaultName                = var.keyVaultName
    logAnalyticsWorkspaceName   = var.logAnalyticsWorkspaceName
    searchServiceName           = var.searchServiceName
    speechServiceName           = var.speechServiceName
    storageAccountName          = var.storageAccountName
    vnetName                    = var.vnetName
  }
  # Normalize generated names only. Overrides are preserved, then validated;
  # never silently rewrite an operator's explicit name.
  caf_region_abbreviations = {
    eastus           = "eus", eastus2 = "eus2", westus = "wus", westus2 = "wus2", westus3 = "wus3"
    centralus        = "cus", northcentralus = "ncus", southcentralus = "scus", westcentralus = "wcus"
    canadacentral    = "cac", canadaeast = "cae", brazilsouth = "brs"
    northeurope      = "neu", westeurope = "weu", uksouth = "uks", ukwest = "ukw"
    francecentral    = "frc", francesouth = "frs", germanywestcentral = "gwc"
    swedencentral    = "swc", switzerlandnorth = "swn", norwayeast = "noe"
    australiaeast    = "aue", australiasoutheast = "ause", southeastasia = "sea", eastasia = "ea"
    japaneast        = "jpe", japanwest = "jpw", koreacentral = "krc", centralindia = "cin"
    southafricanorth = "san", uaenorth = "uan"
  }
  caf_region_input = replace(lower(coalesce(var.cafRegionName, local.root_location)), "/[^a-z0-9]/", "")
  caf_parts = [
    coalesce(replace(lower(var.cafWorkloadName), "/[^a-z0-9]/", ""), substr(local.resource_token, 0, 6)),
    coalesce(replace(lower(coalesce(var.cafEnvironmentName, var.environmentName)), "/[^a-z0-9]/", ""), "env"),
    lookup(local.caf_region_abbreviations, local.caf_region_input, substr(local.caf_region_input, 0, 5)),
    coalesce(replace(lower(var.cafInstance), "/[^a-z0-9]/", ""), "001")
  ]
  caf_stem = join("-", local.caf_parts)
  generated_name_candidates = {
    for key, spec in local.naming_definitions : key => (
      var.resourceNamingMode == "legacy" ?
      "${spec.compact ? replace(spec.prefix, "-", "") : spec.prefix}${local.resource_token}" :
      spec.compact ? "${replace(spec.prefix, "-", "")}${join("", local.caf_parts)}" :
      "${trimsuffix(spec.prefix, "-")}-${local.caf_stem}"
    )
  }
  generated_resource_names = {
    for key, candidate in local.generated_name_candidates : key => (
      length(candidate) <= local.naming_definitions[key].max ? candidate :
      "${trimsuffix(substr(candidate, 0, local.naming_definitions[key].max - 7), "-")}${local.naming_definitions[key].compact ? "" : "-"}${substr(sha256(candidate), 0, 6)}"
    )
  }
  resource_names = {
    for key, generated in local.generated_resource_names : key => coalesce(local.name_overrides[key], generated)
  }
  effective_jumpbox = var.deployJumpbox != null ? var.deployJumpbox : (
    coalesce(var.deployVM, true) && var.networkIsolation && coalesce(var.existingJumpboxResourceId, " ") == " "
  )
  effective_bastion = var.deployBastion != null ? var.deployBastion : (
    coalesce(var.deployVM, true) && var.networkIsolation && local.effective_jumpbox && coalesce(var.existingBastionResourceId, " ") == " "
  )
  effective_nat = var.deployNatGateway != null ? var.deployNatGateway : (
    coalesce(var.deployVM, true) && var.networkIsolation && local.effective_jumpbox && coalesce(var.existingNatGatewayResourceId, " ") == " "
  )
  effective_flags = {
    network_isolation    = var.networkIsolation
    use_uai              = var.useUAI
    use_capp_api_key     = var.useCAppAPIKey
    hosted_prerequisites = var.prepareHostedAgent || var.deployHostedAgent
    container_apps       = var.deployContainerApps && var.deployContainerEnv && (!var.useCAppAPIKey || (var.deployKeyVault && var.deployAppConfig && var.appRuntimeConfigurationMode == "appConfig"))
    acr_pool             = var.deployContainerRegistry && var.networkIsolation && var.deployAcrTaskAgentPool
    public_ingress       = var.publicIngress.enabled && var.networkIsolation && var.deployContainerEnv && var.deployContainerApps && length(var.containerAppsList) > 0
    jumpbox              = local.effective_jumpbox
    bastion              = local.effective_bastion
    nat                  = local.effective_nat
  }
}

# Validation only: this has no provider, remote operation, readiness signal or
# replacement output. It does not stand in for any infrastructure resource.
resource "terraform_data" "root_contract" {
  lifecycle {
    precondition {
      condition     = !var.createResourceGroup || try(length(trimspace(var.location)) > 0, false)
      error_message = "A Terraform-owned root group requires an explicit location."
    }
    precondition {
      condition     = var.tenantId == null ? true : lower(var.tenantId) == lower(data.azurerm_client_config.root.tenant_id)
      error_message = "tenantId must agree with the authenticated provider."
    }
    precondition {
      condition     = lower(var.subscriptionId) == lower(data.azurerm_client_config.root.subscription_id)
      error_message = "subscriptionId must agree with the authenticated provider."
    }
    precondition {
      condition     = local.application_rg == var.resourceGroupName || local.application_rg != local.network_rg || var.createApplicationResourceGroup == var.createNetworkResourceGroup
      error_message = "A shared application/network group must have a single consistent ownership decision."
    }
    precondition {
      condition     = !var.deployContainerApps || var.deployContainerEnv
      error_message = "deployContainerApps requires deployContainerEnv."
    }
    precondition {
      condition     = !var.useCAppAPIKey || (var.deployContainerApps && var.deployKeyVault && var.deployAppConfig && var.appRuntimeConfigurationMode == "appConfig")
      error_message = "Container App API keys require Container Apps, Key Vault and appConfig runtime mode."
    }
    precondition {
      condition     = !var.bastionEnableTunneling || contains(["Standard", "Premium"], var.bastionSkuName)
      error_message = "Bastion tunneling requires Standard or Premium."
    }
    precondition {
      condition     = !var.publicIngress.enabled || (local.effective_flags.public_ingress && var.publicIngress.backendAppIndex < length(var.containerAppsList))
      error_message = "Public ingress requires isolated Container Apps and an existing backend index."
    }
    precondition {
      condition     = !var.useExistingVNet || can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/virtualNetworks/[^/]+$", var.existingVnetResourceId))
      error_message = "useExistingVNet requires a full VNet resource ID."
    }
    precondition {
      condition     = var.existingVnetSubscriptionId == null ? true : try(lower(split("/", var.existingVnetResourceId)[2]) == lower(var.existingVnetSubscriptionId), false)
      error_message = "existingVnetSubscriptionId must match existingVnetResourceId."
    }
    precondition {
      condition     = coalesce(var.hubIntegrationEgressNextHopIp, " ") == " " || coalesce(var.hubIntegrationExistingRouteTableResourceId, " ") == " "
      error_message = "An external next hop and an existing route table are mutually exclusive."
    }
    precondition {
      condition     = !local.effective_flags.hosted_prerequisites || (var.deployAiFoundry && var.deployAfProject && (var.deployContainerRegistry || (var.hostedAgentContainerRegistryResourceId != "" && var.hostedAgentContainerRegistryEndpoint != "")))
      error_message = "Hosted prerequisites require a Foundry project and a managed or explicitly bound registry."
    }
    precondition {
      condition     = !var.deployHostedAgent || can(regex("^sha256:[0-9a-f]{64}$", var.hostedAgent.version))
      error_message = "Hosted deployment requires an immutable lowercase sha256 image digest."
    }
    precondition {
      condition     = !local.effective_jumpbox || (var.vmAdminPassword == null ? true : var.vmAdminPassword == "" || length(var.vmAdminPassword) >= 12)
      error_message = "An explicit managed-jumpbox admin password must have at least 12 characters; null/empty requests persistent state-owned generation."
    }
    precondition {
      condition = alltrue([
        for key, name in local.generated_resource_names :
        length(name) <= local.naming_definitions[key].max &&
        can(regex(local.naming_definitions[key].compact ? "^[a-z0-9]{3,}$" : "^[a-z0-9][a-z0-9-]*[a-z0-9]$", name)) &&
        !strcontains(name, "--")
      ])
      error_message = "Generated resource names must meet Azure character and length limits."
    }
    precondition {
      # Explicit names retain each service's rules rather than inheriting the
      # shorter, lowercase-only CAF generation policy. Other service overrides
      # are checked by their provider/API schemas, without root normalization.
      condition = (
        alltrue([for key in ["storageAccountName", "aiFoundryStorageAccountName"] : can(regex("^[a-z0-9]{3,24}$", local.resource_names[key]))]) &&
        can(regex("^[a-zA-Z0-9]{5,50}$", local.resource_names.containerRegistryName)) &&
        can(regex("^[a-zA-Z][a-zA-Z0-9-]{1,22}[a-zA-Z0-9]$", local.resource_names.keyVaultName)) &&
        !strcontains(local.resource_names.keyVaultName, "--") &&
        alltrue([for key in ["searchServiceName", "aiFoundrySearchServiceName"] : can(regex("^[a-z0-9][a-z0-9-]{0,58}[a-z0-9]$", local.resource_names[key])) && !strcontains(local.resource_names[key], "--")]) &&
        alltrue([for key in ["dbAccountName", "aiFoundryCosmosDbName"] : can(regex("^[a-z0-9][a-z0-9-]{1,42}[a-z0-9]$", local.resource_names[key]))])
      )
      error_message = "Explicit Storage, ACR, Key Vault, Search and Cosmos account names must meet their service-specific rules."
    }
    precondition {
      condition = length(distinct(concat(
        [for m in var.modelDeploymentList : m.canonical_name],
        [for a in var.containerAppsList : a.canonical_name],
        [for c in var.databaseContainersList : c.canonical_name],
        [for c in var.storageAccountContainersList : c.canonical_name]
      ))) == length(var.modelDeploymentList) + length(var.containerAppsList) + length(var.databaseContainersList) + length(var.storageAccountContainersList)
      error_message = "Canonical App Configuration keys must be unique across all collections."
    }
  }
}
