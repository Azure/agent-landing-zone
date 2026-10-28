# Foundation ownership is per App Configuration name/label, not full-store.
# Deploy/config owns live app bindings, hosted routing and validation evidence.
locals {
  services_abbreviations = jsondecode(file("${path.module}/../constants/abbreviations.json"))
  services_foundry_rg_id = local.deployment_context.foundry_rg_id
  services_app_rg_id     = local.deployment_context.application_rg_id
  services_tags          = local.deployment_context.tags
  services_legacy_keys   = var.useCAppAPIKey && !(var.prepareHostedAgent || var.deployHostedAgent)
  services_cosmos_subnets = var.networkIsolation ? [
    local.subnet_ids.pe, local.subnet_ids.acaEnvironment, local.subnet_ids.applicationPe
  ] : []
  # Optional typed inputs materialize absent properties as null. Do not send an
  # unset future-API member (e.g. fullTextIndexes) to the baseline ARM API.
  # Explicitly supplied members remain intact and subject to provider validation.
  services_indexing_policies = {
    for container in var.databaseContainersList : container.name => try({
      for key, value in container.indexingPolicy : key => value if value != null
    }, {})
  }
  services_containers = { for container in var.databaseContainersList : container.name => {
    name = container.name
    # Bicep accepts a single path, adds the slash, and deliberately uses Hash v1.
    partition_key = {
      paths   = [startswith(container.partitionKey, "/") ? container.partitionKey : "/${container.partitionKey}"]
      kind    = "Hash"
      version = 1
    }
    indexing_policy = length(keys(local.services_indexing_policies[container.name])) == 0 ? null : local.services_indexing_policies[container.name]
  } }
}

resource "terraform_data" "services_contract" {
  input = var.databaseContainersList
  lifecycle {
    precondition {
      condition = alltrue([
        for container in var.databaseContainersList :
        can(regex("^/?[^/[:space:]]+(/[^/[:space:]]+)*$", container.partitionKey))
      ])
      error_message = "Cosmos partitionKey must be a nonempty path, with no empty segments or whitespace."
    }
    precondition {
      condition = alltrue([
        for container in var.databaseContainersList :
        try(container.indexingPolicy, null) == null || can(keys(container.indexingPolicy))
      ])
      error_message = "Cosmos indexingPolicy must be an object; custom composite, spatial and path policies are preserved verbatim."
    }
    precondition {
      condition = !var.deployCosmosDb || alltrue([
        for setting in var.additionalAppConfigurationSettings :
        !contains(["COSMOS_DB_ACCOUNT_RESOURCE_ID", "COSMOS_DB_ENDPOINT"], setting.name)
      ])
      error_message = "Additional settings must not compete with the separately owned Cosmos account resource ID/endpoint."
    }
    precondition {
      condition = !local.services_legacy_keys || alltrue([
        for setting in var.additionalAppConfigurationSettings :
        !contains([for app in var.containerAppsList : "${app.canonical_name}_APIKEY"], setting.name)
      ])
      error_message = "Additional settings must not compete with infrastructure-owned legacy <APP>_APIKEY Key Vault references."
    }
  }
}

# AzureRM AVMs accept group names, not IDs. Carry the root's explicit group
# ownership dependency without making the modules depend on unrelated services.
resource "terraform_data" "services_resource_groups" {
  input = [local.services_foundry_rg_id, local.services_app_rg_id]
}

# AzAPI keeps all storage operations on ARM: no listKeys or data-plane container
# calls from a public Terraform runner. AVM 0.6.6 does not expose the source
# automaticSnapshotPolicyEnabled blob-service property.
resource "azapi_resource" "solution_storage" {
  count     = var.deployStorageAccount ? 1 : 0
  type      = "Microsoft.Storage/storageAccounts@2024-01-01"
  parent_id = local.services_foundry_rg_id
  name      = local.resource_names.storageAccountName
  location  = local.effective_locations.main
  tags      = local.services_tags
  body = {
    kind = "StorageV2"
    sku  = { name = "Standard_LRS" }
    properties = {
      allowBlobPublicAccess    = false
      allowSharedKeyAccess     = var.storageAccountAllowSharedKeyAccess
      supportsHttpsTrafficOnly = true
      minimumTlsVersion        = "TLS1_2"
      publicNetworkAccess      = local.public_access.public_network_access
      encryption = {
        keySource                       = "Microsoft.Storage"
        requireInfrastructureEncryption = true
        services = {
          blob = { enabled = true }
          file = { enabled = true }
        }
      }
      networkAcls = {
        bypass              = var.storageAccountNetworkAclsBypass
        defaultAction       = length(var.allowedIpRanges) > 0 ? "Deny" : "Allow"
        ipRules             = [for ip in var.allowedIpRanges : { value = ip, action = "Allow" }]
        virtualNetworkRules = []
        resourceAccessRules = var.storageAccountResourceAccessRules
      }
    }
  }
  response_export_values = ["properties.primaryEndpoints.blob"]
}

resource "azapi_resource" "solution_blob_service" {
  count     = var.deployStorageAccount ? 1 : 0
  type      = "Microsoft.Storage/storageAccounts/blobServices@2024-01-01"
  parent_id = azapi_resource.solution_storage[0].id
  name      = "default"
  body = {
    properties = {
      automaticSnapshotPolicyEnabled = true
      containerDeleteRetentionPolicy = { enabled = true, days = 10 }
      deleteRetentionPolicy          = { enabled = true, days = 7 }
      lastAccessTimeTrackingPolicy = {
        enable                    = true
        name                      = "AccessTimeTracking"
        trackingGranularityInDays = 1
        blobType                  = ["blockBlob"]
      }
    }
  }
}

resource "azapi_resource" "solution_blob_container" {
  for_each  = { for container in var.storageAccountContainersList : container.name => container if var.deployStorageAccount }
  type      = "Microsoft.Storage/storageAccounts/blobServices/containers@2024-01-01"
  parent_id = azapi_resource.solution_blob_service[0].id
  name      = each.key
  body      = { properties = { publicAccess = "None" } }
}

# The account and its SQL children are intentionally separate. The application
# account is serverless; database/container throughput inputs are ignored exactly
# as in the supported Bicep path, not submitted as invalid serverless offers.
resource "azapi_resource" "application_cosmos" {
  count     = var.deployCosmosDb ? 1 : 0
  type      = "Microsoft.DocumentDB/databaseAccounts@2024-11-15"
  parent_id = local.services_app_rg_id
  name      = local.resource_names.dbAccountName
  location  = local.effective_locations.cosmos
  tags      = local.services_tags
  identity {
    type         = var.useUAI ? "UserAssigned" : "SystemAssigned"
    identity_ids = var.useUAI ? [local.service_identities.cosmos.resource_id] : []
  }
  body = {
    kind = "GlobalDocumentDB"
    properties = {
      databaseAccountOfferType           = "Standard"
      backupPolicy                       = { type = "Continuous", continuousModeProperties = { tier = "Continuous30Days" } }
      capabilities                       = [{ name = "EnableServerless" }]
      minimalTlsVersion                  = "Tls12"
      capacity                           = { totalThroughputLimit = -1 }
      publicNetworkAccess                = local.public_access.public_network_access
      consistencyPolicy                  = { defaultConsistencyLevel = "Session" }
      enableMultipleWriteLocations       = false
      locations                          = [{ failoverPriority = 0, locationName = local.effective_locations.cosmos, isZoneRedundant = var.useZoneRedundancy }]
      ipRules                            = [for ip in var.allowedIpRanges : { ipAddressOrRange = ip }]
      virtualNetworkRules                = [for id in local.services_cosmos_subnets : { id = id, ignoreMissingVNetServiceEndpoint = false }]
      networkAclBypass                   = "None"
      isVirtualNetworkFilterEnabled      = length(var.allowedIpRanges) > 0 || var.networkIsolation
      enableFreeTier                     = false
      enableAutomaticFailover            = true
      enableAnalyticalStorage            = var.enableCosmosAnalyticalStorage
      disableLocalAuth                   = true
      disableKeyBasedMetadataWriteAccess = true
    }
  }
  response_export_values = ["properties.documentEndpoint"]
}

resource "azapi_resource" "application_database" {
  count     = var.deployCosmosDb ? 1 : 0
  type      = "Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15"
  parent_id = azapi_resource.application_cosmos[0].id
  name      = local.resource_names.dbDatabaseName
  body      = { properties = { resource = { id = local.resource_names.dbDatabaseName } } }
}

resource "azapi_resource" "application_container" {
  for_each  = var.deployCosmosDb ? local.services_containers : {}
  type      = "Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15"
  parent_id = azapi_resource.application_database[0].id
  name      = each.key
  body = {
    properties = {
      resource = merge({
        id                       = each.key
        defaultTtl               = -1
        partitionKey             = each.value.partition_key
        conflictResolutionPolicy = {}
      }, each.value.indexing_policy == null ? {} : { indexingPolicy = each.value.indexing_policy })
    }
  }
  depends_on = [terraform_data.services_contract]
}

# Verified AVM Search 0.3.0 only emits SystemAssigned despite accepting UAI
# inputs. AzAPI is necessary for application Search's supported UAI mode.
resource "azapi_resource" "application_search" {
  count     = var.deploySearchService ? 1 : 0
  type      = "Microsoft.Search/searchServices@2025-05-01"
  parent_id = local.services_foundry_rg_id
  name      = local.resource_names.searchServiceName
  location  = local.effective_locations.search
  tags      = local.services_tags
  identity {
    type         = var.useUAI ? "UserAssigned" : "SystemAssigned"
    identity_ids = var.useUAI ? [local.service_identities.search.resource_id] : []
  }
  body = {
    sku = { name = "standard" }
    properties = {
      replicaCount        = 1
      partitionCount      = 1
      semanticSearch      = "standard"
      disableLocalAuth    = false
      authOptions         = { aadOrApiKey = { aadAuthFailureMode = "http401WithBearerChallenge" } }
      publicNetworkAccess = local.public_access.public_network_access
      networkRuleSet = {
        bypass  = length(var.allowedIpRanges) > 0 ? "AzureServices" : "None"
        ipRules = [for ip in var.allowedIpRanges : { value = ip }]
      }
    }
  }
  response_export_values = ["identity.principalId"]
}

module "application_vault" {
  count   = var.deployKeyVault ? 1 : 0
  source  = "Azure/avm-res-keyvault-vault/azurerm"
  version = "0.10.2"

  name                           = local.resource_names.keyVaultName
  location                       = local.effective_locations.main
  resource_group_name            = local.deployment_context.application_rg
  tenant_id                      = local.deployment_context.tenant_id
  sku_name                       = "standard"
  legacy_access_policies_enabled = false
  soft_delete_retention_days     = 90
  purge_protection_enabled       = false
  public_network_access_enabled  = local.public_access.public_network_access == "Enabled"
  network_acls = {
    bypass                     = "AzureServices"
    default_action             = length(var.allowedIpRanges) > 0 ? "Deny" : "Allow"
    ip_rules                   = var.allowedIpRanges
    virtual_network_subnet_ids = []
  }
  tags              = local.services_tags
  role_assignments  = {}
  private_endpoints = {}
  enable_telemetry  = false
  depends_on        = [terraform_data.services_resource_groups]
}

# Legacy opt-in bootstrap only; hosted preparation is always keyless. Rotation is
# not Terraform-owned. Secrets never appear in root outputs or plaintext settings.
resource "azapi_resource" "legacy_application_key" {
  for_each = {
    for app in var.containerAppsList : app.canonical_name => app
    if local.services_legacy_keys && var.deployKeyVault && var.deployContainerApps && var.deployContainerEnv
  }
  type      = "Microsoft.KeyVault/vaults/secrets@2024-11-01"
  parent_id = module.application_vault[0].resource_id
  name      = replace("${each.key}_APIKEY", "_", "-")
  body      = { properties = { contentType = "text/plain", value = local.resource_token } }
  lifecycle {
    ignore_changes = [body.properties.value]
  }
}

# Verified AVM 0.5.1 exposes the ARM proxy properties. Its key_values submodule
# uses AzureRM data-plane writes, so keep it empty and use ARM children below
# for both public and isolated foundations (private-link delegation is enabled).
module "application_configuration" {
  count   = var.deployAppConfig ? 1 : 0
  source  = "Azure/avm-res-appconfiguration-configurationstore/azure"
  version = "0.5.1"

  name                          = local.resource_names.appConfigName
  location                      = local.effective_locations.main
  resource_group_resource_id    = local.services_app_rg_id
  sku                           = "standard"
  managed_identities            = { system_assigned = true }
  local_auth_enabled            = true
  public_network_access_enabled = local.public_access.public_network_access == "Enabled"
  purge_protection_enabled      = false
  data_plane_proxy = {
    authentication_mode     = "Pass-through"
    private_link_delegation = var.networkIsolation ? "Enabled" : "Disabled"
  }
  tags              = local.services_tags
  key_values        = {}
  role_assignments  = {}
  private_endpoints = {}
  enable_telemetry  = false
}

resource "azapi_resource" "legacy_application_key_reference" {
  for_each  = var.deployAppConfig && var.appRuntimeConfigurationMode == "appConfig" ? local.app_config_bootstrap.legacy_key_references : {}
  type      = "Microsoft.AppConfiguration/configurationStores/keyValues@2024-05-01"
  parent_id = module.application_configuration[0].resource_id
  name      = format("%s$%s", each.key, "agent-lz")
  body = {
    properties = {
      value       = each.value.value
      contentType = each.value.content_type
    }
  }
  depends_on = [terraform_data.services_contract, terraform_data.app_config_authorization]
}

# The identity owner supplies only the completed executor Data Owner grant.
# Do not depend on all application grants, or put this completion in data_context.
resource "terraform_data" "app_config_authorization" {
  count = var.deployAppConfig && var.appRuntimeConfigurationMode == "appConfig" ? 1 : 0
  input = local.app_config_authorization_ready
}

resource "azapi_resource" "foundation_setting" {
  for_each  = var.deployAppConfig && var.appRuntimeConfigurationMode == "appConfig" ? nonsensitive(toset(keys(local.services_foundation_settings))) : toset([])
  type      = "Microsoft.AppConfiguration/configurationStores/keyValues@2024-05-01"
  parent_id = module.application_configuration[0].resource_id
  name = local.services_foundation_settings[each.key].label == "" ? local.services_foundation_settings[each.key].name : format(
    "%s$%s", local.services_foundation_settings[each.key].name, local.services_foundation_settings[each.key].label
  )
  body = {
    properties = {
      value       = local.services_foundation_settings[each.key].value
      contentType = local.services_foundation_settings[each.key].contentType
    }
  }
  schema_validation_enabled = true
  depends_on                = [terraform_data.services_contract, terraform_data.app_config_authorization]
}

resource "azapi_resource" "speech" {
  count     = var.deploySpeechService ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  parent_id = local.services_foundry_rg_id
  name      = local.resource_names.speechServiceName
  location  = local.effective_locations.speech
  tags      = local.services_tags
  identity {
    type = "SystemAssigned"
  }
  body = {
    kind = "SpeechServices"
    sku  = { name = var.speechServiceSku }
    properties = {
      customSubDomainName = local.resource_names.speechServiceName
      disableLocalAuth    = false
      publicNetworkAccess = local.public_access.public_network_access
      networkAcls = {
        defaultAction = length(var.allowedIpRanges) > 0 ? "Deny" : "Allow"
        bypass        = "AzureServices"
        ipRules       = [for ip in var.allowedIpRanges : { value = ip }]
      }
    }
  }
  response_export_values = ["properties.endpoint"]
}

resource "azurerm_monitor_diagnostic_setting" "speech" {
  count                      = var.deploySpeechService && (local.services_existing_law != "" || local.services_create_law) ? 1 : 0
  name                       = "speech-diagnostics"
  target_resource_id         = azapi_resource.speech[0].id
  log_analytics_workspace_id = local.effective_observability.law_id
  enabled_log {
    category_group = "allLogs"
  }
  enabled_metric {
    category = "AllMetrics"
  }
}

locals {
  data_context = {
    storage = {
      id            = var.deployStorageAccount ? azapi_resource.solution_storage[0].id : ""
      name          = var.deployStorageAccount ? local.resource_names.storageAccountName : ""
      blob_endpoint = var.deployStorageAccount ? azapi_resource.solution_storage[0].output.properties.primaryEndpoints.blob : ""
      owned         = var.deployStorageAccount
      documents_container_id = length([
        for container in var.storageAccountContainersList : container.name
        if container.canonical_name == "DOCUMENTS_STORAGE_CONTAINER"
        ]) == 1 && var.deployStorageAccount ? one([
        for container in var.storageAccountContainersList :
        azapi_resource.solution_blob_container[container.name].id
        if var.deployStorageAccount && container.canonical_name == "DOCUMENTS_STORAGE_CONTAINER"
      ]) : ""
    }
    cosmos = {
      id            = var.deployCosmosDb ? azapi_resource.application_cosmos[0].id : ""
      name          = var.deployCosmosDb ? local.resource_names.dbAccountName : ""
      endpoint      = var.deployCosmosDb ? azapi_resource.application_cosmos[0].output.properties.documentEndpoint : ""
      database_name = var.deployCosmosDb ? local.resource_names.dbDatabaseName : ""
      principal_id  = var.deployCosmosDb ? (var.useUAI ? local.service_identities.cosmos.principal_id : azapi_resource.application_cosmos[0].identity[0].principal_id) : ""
      owned         = var.deployCosmosDb
    }
    search = {
      id                   = var.deploySearchService ? azapi_resource.application_search[0].id : ""
      name                 = var.deploySearchService ? local.resource_names.searchServiceName : ""
      endpoint             = var.deploySearchService ? "https://${local.resource_names.searchServiceName}.search.windows.net" : ""
      principal_id         = var.deploySearchService ? (var.useUAI ? local.service_identities.search.principal_id : azapi_resource.application_search[0].identity[0].principal_id) : ""
      identity_resource_id = var.deploySearchService && var.useUAI ? local.service_identities.search.resource_id : ""
      owned                = var.deploySearchService
    }
    key_vault = {
      id    = var.deployKeyVault ? module.application_vault[0].resource_id : ""
      name  = var.deployKeyVault ? local.resource_names.keyVaultName : ""
      uri   = var.deployKeyVault ? module.application_vault[0].uri : ""
      owned = var.deployKeyVault
    }
    app_config = {
      id       = var.deployAppConfig ? module.application_configuration[0].resource_id : ""
      name     = var.deployAppConfig ? local.resource_names.appConfigName : ""
      endpoint = var.deployAppConfig ? module.application_configuration[0].endpoint : ""
      owned    = var.deployAppConfig
    }
    speech = {
      id       = var.deploySpeechService ? azapi_resource.speech[0].id : ""
      name     = var.deploySpeechService ? local.resource_names.speechServiceName : ""
      endpoint = var.deploySpeechService ? azapi_resource.speech[0].output.properties.endpoint : ""
      location = var.deploySpeechService ? local.effective_locations.speech : ""
    }
  }

  # Executable inventory: infra/main.bicep appConfigPopulate plus the separate
  # Cosmos/canonical-name publishers. Do not copy hook guesses or Search's
  # generated payload defaults. These are foundation intent, not live routing.
  services_foundation_plain_settings = merge(
    {
      AZURE_TENANT_ID                             = local.deployment_context.tenant_id
      SUBSCRIPTION_ID                             = local.deployment_context.subscription_id
      AZURE_RESOURCE_GROUP                        = local.deployment_context.foundry_rg
      AZURE_APP_RESOURCE_GROUP                    = local.deployment_context.application_rg
      AZURE_NETWORK_RESOURCE_GROUP                = local.deployment_context.network_rg
      LOCATION                                    = local.effective_locations.main
      ENVIRONMENT_NAME                            = var.environmentName
      DEPLOYMENT_NAME                             = local.deployment_context.deployment_name
      RESOURCE_TOKEN                              = local.resource_token
      NETWORK_ISOLATION                           = tostring(var.networkIsolation)
      SEARCH_RAG_INDEX_NAME                       = "ragindex-${local.resource_token}"
      ENABLE_AGENTIC_RETRIEVAL                    = tostring(var.enableAgenticRetrieval)
      RETRIEVAL_BACKEND                           = var.retrievalBackend
      FOUNDRY_IQ_PATTERN                          = var.foundryIqPattern
      FOUNDRY_IQ_API_VERSION                      = var.retrievalBackend == "foundry_iq" ? var.foundryIqApiVersion : ""
      FOUNDRY_IQ_KNOWLEDGE_RETRIEVAL_BILLING_PLAN = var.retrievalBackend == "foundry_iq" ? var.foundryIqKnowledgeRetrievalBillingPlan : ""
      FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME            = var.retrievalBackend == "foundry_iq" ? var.foundryIqKnowledgeSourceName : ""
      FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND            = var.retrievalBackend == "foundry_iq" ? (var.foundryIqKnowledgeSourceKind != "" ? var.foundryIqKnowledgeSourceKind : (var.foundryIqPattern == "searchIndex" ? "searchIndex" : "azureBlob")) : ""
      FOUNDRY_IQ_STORAGE_CONTAINER_NAME           = var.retrievalBackend == "foundry_iq" && var.foundryIqPattern != "searchIndex" ? var.foundryIqStorageContainerName : ""
      FOUNDRY_IQ_STORAGE_FOLDER_PATH              = var.retrievalBackend == "foundry_iq" && var.foundryIqPattern != "searchIndex" ? var.foundryIqStorageFolderPath : ""
      FOUNDRY_IQ_IS_ADLS_GEN2                     = tostring(var.retrievalBackend == "foundry_iq" && var.foundryIqPattern != "searchIndex" && var.foundryIqIsAdlsGen2)
      FOUNDRY_IQ_CONTENT_EXTRACTION_MODE          = var.retrievalBackend == "foundry_iq" && var.foundryIqPattern != "searchIndex" ? var.foundryIqContentExtractionMode : ""
      FOUNDRY_IQ_AI_SERVICES_ENDPOINT             = var.retrievalBackend == "foundry_iq" && var.foundryIqPattern != "searchIndex" ? (var.foundryIqAiServicesEndpoint != "" ? var.foundryIqAiServicesEndpoint : "https://${local.resource_names.aiFoundryAccountName}.services.ai.azure.com/") : ""
      FOUNDRY_IQ_SEARCH_INDEX_NAME                = var.retrievalBackend == "foundry_iq" && var.foundryIqPattern == "searchIndex" ? var.foundryIqSearchIndexName : ""
      FOUNDRY_IQ_SEMANTIC_CONFIGURATION_NAME      = var.retrievalBackend == "foundry_iq" && var.foundryIqPattern == "searchIndex" ? var.foundryIqSemanticConfigurationName : ""
      FOUNDRY_IQ_BASE_FILTER                      = var.retrievalBackend == "foundry_iq" && var.foundryIqPattern == "searchIndex" ? var.foundryIqBaseFilter : ""
      FOUNDRY_IQ_FILTER_ADD_ON_ENABLED            = tostring(var.retrievalBackend == "foundry_iq" && var.foundryIqPattern == "searchIndex" && var.foundryIqFilterAddOnEnabled)
      FOUNDRY_IQ_SECURITY_FIELD_NAME              = var.retrievalBackend == "foundry_iq" && var.foundryIqPattern == "searchIndex" ? var.foundryIqSecurityFieldName : ""
      FOUNDRY_IQ_MAX_OUTPUT_DOCUMENTS             = var.retrievalBackend == "foundry_iq" ? var.foundryIqMaxOutputDocuments : ""
      USE_UAI                                     = tostring(var.useUAI)
      LOG_LEVEL                                   = "INFO"
      ENABLE_CONSOLE_LOGGING                      = "true"
      RELEASE                                     = local.manifest.tag
      APPLICATIONINSIGHTS_CONNECTION_STRING       = local.effective_observability.connection_string
      APPLICATIONINSIGHTS__INSTRUMENTATIONKEY     = local.effective_observability.instrumentation_key
      KEY_VAULT_RESOURCE_ID                       = local.data_context.key_vault.id
      STORAGE_ACCOUNT_RESOURCE_ID                 = local.data_context.storage.id
      DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID     = local.data_context.storage.documents_container_id
      APP_INSIGHTS_RESOURCE_ID                    = local.effective_observability.app_insights_id
      LOG_ANALYTICS_RESOURCE_ID                   = local.effective_observability.law_id
      CONTAINER_ENV_RESOURCE_ID                   = local.compute_context.environment_id
      AI_FOUNDRY_ACCOUNT_RESOURCE_ID              = local.foundry_context.account_id
      AI_FOUNDRY_PROJECT_RESOURCE_ID              = local.foundry_context.project_id
      SEARCH_SERVICE_UAI_RESOURCE_ID              = local.data_context.search.identity_resource_id
      SEARCH_SERVICE_RESOURCE_ID                  = local.data_context.search.id
      KNOWLEDGE_BASE_CONNECTION_ID                = local.foundry_context.knowledge_base_connection_id
      AZURE_SPEECH_RESOURCE_ID                    = local.data_context.speech.id
      AI_FOUNDRY_ACCOUNT_NAME                     = local.resource_names.aiFoundryAccountName
      AI_FOUNDRY_PROJECT_NAME                     = local.resource_names.aiFoundryProjectName
      AI_FOUNDRY_STORAGE_ACCOUNT_NAME             = local.resource_names.aiFoundryStorageAccountName
      APP_CONFIG_NAME                             = local.resource_names.appConfigName
      APP_INSIGHTS_NAME                           = local.resource_names.appInsightsName
      CONTAINER_ENV_NAME                          = local.resource_names.containerEnvName
      CONTAINER_REGISTRY_NAME                     = local.resource_names.containerRegistryName
      CONTAINER_REGISTRY_LOGIN_SERVER             = "${local.resource_names.containerRegistryName}.${var.acrDnsSuffix}"
      DATABASE_ACCOUNT_NAME                       = local.resource_names.dbAccountName
      DATABASE_NAME                               = local.resource_names.dbDatabaseName
      SEARCH_SERVICE_NAME                         = local.resource_names.searchServiceName
      AZURE_SPEECH_RESOURCE_NAME                  = local.data_context.speech.name
      AZURE_SPEECH_REGION                         = local.data_context.speech.location
      STORAGE_ACCOUNT_NAME                        = local.resource_names.storageAccountName
      DEPLOY_APP_CONFIG                           = tostring(var.deployAppConfig)
      DEPLOY_KEY_VAULT                            = tostring(var.deployKeyVault)
      DEPLOY_LOG_ANALYTICS                        = tostring(var.deployLogAnalytics)
      DEPLOY_APP_INSIGHTS                         = tostring(var.deployAppInsights)
      DEPLOY_SEARCH_SERVICE                       = tostring(var.deploySearchService)
      DEPLOY_SPEECH_SERVICE                       = tostring(var.deploySpeechService)
      DEPLOY_STORAGE_ACCOUNT                      = tostring(var.deployStorageAccount)
      DEPLOY_COSMOS_DB                            = tostring(var.deployCosmosDb)
      DEPLOY_CONTAINER_APPS                       = tostring(var.deployContainerApps)
      DEPLOY_CONTAINER_REGISTRY                   = tostring(var.deployContainerRegistry)
      DEPLOY_CONTAINER_ENV                        = tostring(var.deployContainerEnv)
      KEY_VAULT_URI                               = local.data_context.key_vault.uri
      STORAGE_BLOB_ENDPOINT                       = local.data_context.storage.blob_endpoint
      AI_FOUNDRY_ACCOUNT_ENDPOINT                 = local.foundry_context.account_endpoint
      AI_FOUNDRY_PROJECT_ENDPOINT                 = local.foundry_context.project_endpoint
      SEARCH_SERVICE_QUERY_ENDPOINT               = local.data_context.search.endpoint
      KNOWLEDGE_BASE_ENDPOINT                     = var.retrievalBackend == "foundry_iq" ? local.data_context.search.endpoint : ""
      AZURE_SPEECH_ENDPOINT                       = local.data_context.speech.endpoint
      SEARCH_CONNECTION_ID                        = local.foundry_context.search_connection_id
      KNOWLEDGE_BASE_NAME                         = var.retrievalBackend == "foundry_iq" ? var.knowledgeBaseName : ""
      BING_CONNECTION_ID                          = local.foundry_context.bing_connection_id
      CONTAINER_ENV_PRINCIPAL_ID                  = local.compute_context.environment_principal_id
      SEARCH_SERVICE_PRINCIPAL_ID                 = local.data_context.search.principal_id
    },
    var.deployCosmosDb ? {
      COSMOS_DB_ACCOUNT_RESOURCE_ID = local.data_context.cosmos.id
      COSMOS_DB_ENDPOINT            = local.data_context.cosmos.endpoint
    } : {},
    { for deployment in local.services_model_deployments : deployment.canonical_name => deployment.name },
    { for container in var.databaseContainersList : container.canonical_name => container.name },
    { for container in var.storageAccountContainersList : container.canonical_name => container.name }
  )
  services_foundation_json_settings = {
    FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS = var.retrievalBackend == "foundry_iq" && var.foundryIqPattern != "searchIndex" ? (var.foundryIqIngestionPermissionOptionsJson != "" ? jsonencode(jsondecode(var.foundryIqIngestionPermissionOptionsJson)) : jsonencode(var.foundryIqIngestionPermissionOptions)) : "[]"
    FOUNDRY_IQ_SOURCE_DATA_FIELDS           = jsonencode(var.foundryIqSourceDataFields)
    FOUNDRY_IQ_SEARCH_FIELDS                = jsonencode(var.foundryIqSearchFields)
    SEARCH_SHARED_PRIVATE_LINKS             = jsonencode(local.search_shared_private_link_readiness)
    MODEL_DEPLOYMENTS = jsonencode([for deployment in local.services_model_deployments : {
      canonical_name = deployment.canonical_name
      capacity       = deployment.sku.capacity
      model          = deployment.model.name
      modelFormat    = deployment.model.format
      name           = deployment.name
      version        = deployment.model.version
      apiVersion     = try(coalesce(deployment.apiVersion, "2025-01-01-preview"), "2025-01-01-preview")
      endpoint       = "https://${local.resource_names.aiFoundryAccountName}.openai.azure.com/"
    }])
  }
  services_foundation_defaults = {
    for name, value in merge(local.services_foundation_plain_settings, local.services_foundation_json_settings) :
    jsonencode([name, contains(["AZURE_APP_RESOURCE_GROUP", "AZURE_NETWORK_RESOURCE_GROUP", "DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID"], name) ? "agent-lz" : var.appConfigLabel]) => {
      name        = name
      value       = value
      label       = contains(["AZURE_APP_RESOURCE_GROUP", "AZURE_NETWORK_RESOURCE_GROUP", "DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID"], name) ? "agent-lz" : var.appConfigLabel
      contentType = contains(keys(local.services_foundation_json_settings), name) ? "application/json" : "text/plain"
    }
  }

  # Explicit additional settings win only the matching name+label, preserving
  # empty labels and content types (including arbitrary versionless KV refs).
  # Runtime entries from the shared adapter are handed back to their publisher,
  # not adopted as infrastructure children or ignored as declaration coverage.
  services_appconfig_ownership = jsondecode(file("${path.module}/../../config/deployment/appconfig_ownership.json"))
  services_runtime_setting_names = setunion(
    toset(local.services_appconfig_ownership.controlled),
    toset(keys(local.services_appconfig_ownership.evidence)),
    toset(keys(local.services_appconfig_ownership.ordinary)),
    toset(local.services_appconfig_ownership.ownerReferences),
    toset(flatten([for app in var.containerAppsList : [
      for suffix in local.services_appconfig_ownership.applicationSuffixes : "${app.canonical_name}${suffix}"
    ]]))
  )
  services_normalized_additional_settings = [
    for setting in var.additionalAppConfigurationSettings : {
      name        = setting.name
      value       = setting.value
      label       = setting.label == null ? var.appConfigLabel : setting.label
      contentType = setting.contentType == null ? "text/plain" : setting.contentType
    }
  ]
  services_runtime_additional_settings = [
    for setting in local.services_normalized_additional_settings : setting
    if setting.label == local.services_appconfig_ownership.label && !contains(keys(local.services_foundation_plain_settings), setting.name) && (
      contains(local.services_runtime_setting_names, setting.name) ||
      anytrue([for pattern in local.services_appconfig_ownership.patterns : can(regex(pattern, setting.name))])
    )
  ]
  services_runtime_additional_keys = toset([
    for setting in local.services_runtime_additional_settings : jsonencode([setting.name, setting.label])
  ])
  services_foundation_settings = merge(local.services_foundation_defaults, {
    for setting in local.services_normalized_additional_settings :
    jsonencode([setting.name, setting.label]) => setting
    if !contains(local.services_runtime_additional_keys, jsonencode([setting.name, setting.label]))
  })

  # Parent exports ownership names/labels. Runtime settings are a private typed
  # input handoff, not permission to expose arbitrary supplied values as outputs.
  # Never export this whole object: foundation values can include sensitive input.
  # The publisher must load Terraform-owned current values without overwriting
  # them, and publish runtime_settings through its existing cutover/evidence gates.
  app_config_bootstrap = {
    enabled                = var.deployAppConfig && var.appRuntimeConfigurationMode == "appConfig"
    label                  = var.appConfigLabel
    owner                  = "terraform"
    runtime_owner          = "shared-postProvision"
    runtime_settings       = local.services_runtime_additional_settings
    runtime_owned_names    = sort(tolist(local.services_runtime_setting_names))
    runtime_owned_patterns = local.services_appconfig_ownership.patterns
    foundation_owned_keys = concat([
      for key, setting in local.services_foundation_settings :
      { name = setting.name, label = setting.label, contentType = setting.contentType }
      ], [
      for key, secret in azapi_resource.legacy_application_key :
      { name = "${key}_APIKEY", label = "agent-lz", contentType = "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8" }
    ])
    legacy_reference_owner = "terraform"
    legacy_key_references = {
      for key, secret in azapi_resource.legacy_application_key :
      "${key}_APIKEY" => {
        value        = jsonencode({ uri = "${local.data_context.key_vault.uri}secrets/${secret.name}" })
        content_type = "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8"
      }
    }
  }
}
