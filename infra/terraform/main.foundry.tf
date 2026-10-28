# Account/project foundation only. config/search owns retrieval payloads;
# config/aifoundry owns RAI policies, blocklists and model-policy attachment;
# deploy owns hosted agent versions, images, starts and runtime principals.
locals {
  services_agent_service = var.deployAiFoundry && var.deployAAfAgentSvc
  services_project       = var.deployAiFoundry && var.deployAfProject
  services_foundry_owned = {
    storage = local.services_agent_service && var.aiFoundryStorageAccountResourceId == ""
    search  = local.services_agent_service && var.aiSearchResourceId == ""
    cosmos  = local.services_agent_service && var.aiFoundryCosmosDBAccountResourceId == ""
    vault   = local.services_agent_service && var.keyVaultResourceId == ""
  }
  services_foundry_existing = {
    for key, value in {
      storage = { id = var.aiFoundryStorageAccountResourceId, type = "Microsoft.Storage/storageAccounts@2025-01-01" }
      search  = { id = var.aiSearchResourceId, type = "Microsoft.Search/searchServices@2025-05-01" }
      cosmos  = { id = var.aiFoundryCosmosDBAccountResourceId, type = "Microsoft.DocumentDB/databaseAccounts@2025-04-15" }
      vault   = { id = var.keyVaultResourceId, type = "Microsoft.KeyVault/vaults@2024-11-01" }
    } : key => value if local.services_agent_service && value.id != ""
  }
  services_model_deployments = concat(var.modelDeploymentList, [for deployment in [
    { name = "gpt-5-nano", model = { format = "OpenAI", name = "gpt-5-nano", version = "2025-08-07" }, sku = { name = "GlobalStandard", capacity = 40 }, canonical_name = "GPT_MODEL" },
    { name = "text-embedding-3-large", model = { format = "OpenAI", name = "text-embedding-3-large", version = "1" }, sku = { name = "Standard", capacity = 10 }, canonical_name = "EMBEDDING_MODEL" }
  ] : deployment if length(var.modelDeploymentList) == 0])
}

# Read-only BYO references, including cross-subscription IDs. No associated
# account settings, keys, containers, DNS or private endpoints are adopted here.
data "azapi_resource" "foundry_existing_dependency" {
  for_each    = local.services_foundry_existing
  type        = each.value.type
  resource_id = each.value.id
  response_export_values = each.key == "storage" ? ["properties.primaryEndpoints.blob"] : (
    each.key == "cosmos" ? ["properties.documentEndpoint"] : ["name", "location"]
  )
}

resource "azapi_resource" "foundry_storage" {
  count     = local.services_foundry_owned.storage ? 1 : 0
  type      = "Microsoft.Storage/storageAccounts@2024-01-01"
  parent_id = local.services_foundry_rg_id
  name      = local.resource_names.aiFoundryStorageAccountName
  location  = local.effective_locations.main
  tags      = local.services_tags
  body = {
    kind = "StorageV2"
    sku  = { name = var.aiFoundryStorageSku }
    properties = {
      allowBlobPublicAccess    = false
      supportsHttpsTrafficOnly = true
      minimumTlsVersion        = "TLS1_2"
      publicNetworkAccess      = local.public_access.public_network_access
      networkAcls = {
        bypass              = "AzureServices"
        defaultAction       = var.networkIsolation || length(var.allowedIpRanges) > 0 ? "Deny" : "Allow"
        virtualNetworkRules = []
        ipRules             = [for ip in var.allowedIpRanges : { value = ip, action = "Allow" }]
      }
    }
  }
  response_export_values = ["properties.primaryEndpoints.blob"]
}

module "foundry_search" {
  count   = local.services_foundry_owned.search ? 1 : 0
  source  = "Azure/avm-res-search-searchservice/azurerm"
  version = "0.3.0"

  name                          = local.resource_names.aiFoundrySearchServiceName
  location                      = local.effective_locations.search
  resource_group_name           = local.deployment_context.foundry_rg
  sku                           = "standard"
  replica_count                 = 1
  partition_count               = 1
  semantic_search_sku           = "standard"
  managed_identities            = { system_assigned = true }
  local_authentication_enabled  = true
  authentication_failure_mode   = "http401WithBearerChallenge"
  public_network_access_enabled = local.public_access.public_network_access == "Enabled"
  allowed_ips                   = var.allowedIpRanges
  network_rule_bypass_option    = length(var.allowedIpRanges) > 0 ? "AzureServices" : "None"
  tags                          = local.services_tags
  role_assignments              = {}
  private_endpoints             = {}
  enable_telemetry              = false
  depends_on                    = [terraform_data.services_resource_groups]
}

# The associated Agent Service account is NOT the application serverless account.
# Do not own enterprise_memory or its service-created containers here.
resource "azapi_resource" "foundry_cosmos" {
  count     = local.services_foundry_owned.cosmos ? 1 : 0
  type      = "Microsoft.DocumentDB/databaseAccounts@2025-04-15"
  parent_id = local.services_foundry_rg_id
  name      = local.resource_names.aiFoundryCosmosDbName
  location  = local.effective_locations.main
  tags      = local.services_tags
  body = {
    kind = "GlobalDocumentDB"
    properties = {
      databaseAccountOfferType           = "Standard"
      minimalTlsVersion                  = "Tls12"
      consistencyPolicy                  = { defaultConsistencyLevel = "Session" }
      locations                          = [{ locationName = local.effective_locations.main, failoverPriority = 0, isZoneRedundant = false }]
      enableAutomaticFailover            = true
      disableKeyBasedMetadataWriteAccess = true
      disableLocalAuth                   = true
      networkAclBypass                   = "AzureServices"
      publicNetworkAccess                = var.networkIsolation ? "Disabled" : "Enabled"
    }
  }
  response_export_values = ["properties.documentEndpoint"]
}

module "foundry_vault" {
  count   = local.services_foundry_owned.vault ? 1 : 0
  source  = "Azure/avm-res-keyvault-vault/azurerm"
  version = "0.10.2"

  name                            = "${local.services_abbreviations.security.keyVault}ai-${local.resource_token}"
  location                        = local.effective_locations.main
  resource_group_name             = local.deployment_context.foundry_rg
  tenant_id                       = local.deployment_context.tenant_id
  sku_name                        = "standard"
  legacy_access_policies_enabled  = false
  soft_delete_retention_days      = 7
  purge_protection_enabled        = false
  enabled_for_deployment          = true
  enabled_for_disk_encryption     = true
  enabled_for_template_deployment = true
  public_network_access_enabled   = !var.networkIsolation
  network_acls = {
    bypass         = "AzureServices"
    default_action = var.networkIsolation ? "Deny" : "Allow"
  }
  tags              = local.services_tags
  role_assignments  = {}
  private_endpoints = {}
  enable_telemetry  = false
  depends_on        = [terraform_data.services_resource_groups]
}

locals {
  foundry_dependencies = {
    agent_service = local.services_agent_service
    storage_id    = local.services_agent_service ? (var.aiFoundryStorageAccountResourceId != "" ? data.azapi_resource.foundry_existing_dependency["storage"].id : azapi_resource.foundry_storage[0].id) : ""
    search_id     = local.services_agent_service ? (var.aiSearchResourceId != "" ? data.azapi_resource.foundry_existing_dependency["search"].id : module.foundry_search[0].resource_id) : ""
    cosmos_id     = local.services_agent_service ? (var.aiFoundryCosmosDBAccountResourceId != "" ? data.azapi_resource.foundry_existing_dependency["cosmos"].id : azapi_resource.foundry_cosmos[0].id) : ""
    vault_id      = local.services_agent_service ? (var.keyVaultResourceId != "" ? data.azapi_resource.foundry_existing_dependency["vault"].id : module.foundry_vault[0].resource_id) : ""
    storage_name  = local.services_agent_service ? (var.aiFoundryStorageAccountResourceId != "" ? reverse(split("/", var.aiFoundryStorageAccountResourceId))[0] : local.resource_names.aiFoundryStorageAccountName) : ""
    search_name   = local.services_agent_service ? (var.aiSearchResourceId != "" ? reverse(split("/", var.aiSearchResourceId))[0] : local.resource_names.aiFoundrySearchServiceName) : ""
    cosmos_name   = local.services_agent_service ? (var.aiFoundryCosmosDBAccountResourceId != "" ? reverse(split("/", var.aiFoundryCosmosDBAccountResourceId))[0] : local.resource_names.aiFoundryCosmosDbName) : ""
    vault_name    = local.services_agent_service ? (var.keyVaultResourceId != "" ? reverse(split("/", var.keyVaultResourceId))[0] : "${local.services_abbreviations.security.keyVault}ai-${local.resource_token}") : ""
    owned         = local.services_foundry_owned
  }
  services_foundry_storage_endpoint = local.services_agent_service ? (
    var.aiFoundryStorageAccountResourceId != "" ? data.azapi_resource.foundry_existing_dependency["storage"].output.properties.primaryEndpoints.blob : azapi_resource.foundry_storage[0].output.properties.primaryEndpoints.blob
  ) : ""
  services_foundry_cosmos_endpoint = local.services_agent_service ? (
    var.aiFoundryCosmosDBAccountResourceId != "" ? data.azapi_resource.foundry_existing_dependency["cosmos"].output.properties.documentEndpoint : azapi_resource.foundry_cosmos[0].output.properties.documentEndpoint
  ) : ""
  # ARM account/project connections allow 3..33 alphanumeric/underscore/hyphen
  # characters, independently of the connected resource's longer name limit.
  # Preserve already-valid generated names; bound only generated overlong names.
  # Explicit knowledgeBaseConnectionName is never silently rewritten.
  services_connection_name_candidates = {
    associated_cosmos  = local.foundry_dependencies.cosmos_name
    associated_storage = local.foundry_dependencies.storage_name
    associated_search  = local.foundry_dependencies.search_name
    storage            = "${local.resource_names.storageAccountName}-storage-connection"
    search             = "${local.resource_names.searchServiceName}-connection"
    insights           = "${local.resource_names.aiFoundryAccountName}-appinsights-connection"
    bing               = "${local.resource_names.bingSearchName}-connection"
  }
  services_connection_names = {
    for key, candidate in local.services_connection_name_candidates : key => (
      length(candidate) <= 33 ? candidate :
      "${substr(candidate, 0, 26)}-${substr(provider::azapi::unique_string([candidate]), 0, 6)}"
    )
  }
}

resource "terraform_data" "foundry_connection_contract" {
  input = var.knowledgeBaseConnectionName
  lifecycle {
    precondition {
      condition = !var.deployAiFoundry || !var.deploySearchService || var.retrievalBackend != "foundry_iq" || can(
        regex("^[a-zA-Z0-9][a-zA-Z0-9_-]{2,32}$", var.knowledgeBaseConnectionName)
      )
      error_message = "knowledgeBaseConnectionName must satisfy the Foundry connection API's 3..33 character name constraint."
    }
  }
}

resource "terraform_data" "foundry_model_contract" {
  input = var.modelDeploymentList
  lifecycle {
    precondition {
      condition = !var.deployAiFoundry || alltrue([
        for deployment in var.modelDeploymentList :
        try(deployment.dynamicThrottlingEnabled, null) == null
      ])
      # OpenAPI DeploymentProperties@2025-06-01 marks this readOnly.
      # AVM's dynamic-throttling setting belongs to the ACCOUNT, not its
      # deploymentType. Never silently reinterpret this as an account-wide flag.
      error_message = "Deployment dynamicThrottlingEnabled is read-only in API 2025-06-01 and cannot be configured per model."
    }
  }
}

# Direct resources preserve the source account/project-before-PE ordering and
# allow narrow exclusion of the postProvision-owned model RAI attachment.
resource "azapi_resource" "foundry_account" {
  count     = var.deployAiFoundry ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  parent_id = local.services_foundry_rg_id
  name      = local.resource_names.aiFoundryAccountName
  location  = local.effective_locations.main
  tags      = var.deploymentTags
  identity {
    type = "SystemAssigned"
  }
  body = {
    kind = "AIServices"
    sku  = { name = "S0" }
    properties = merge({
      customSubDomainName    = local.resource_names.aiFoundryAccountName
      allowProjectManagement = var.deployAfProject
      disableLocalAuth       = var.aiFoundryDisableLocalAuth
      # Actual source posture: the Foundry account does NOT consume the root
      # allowedIpRanges exception. Do not silently broaden isolated Foundry.
      publicNetworkAccess = var.networkIsolation ? "Disabled" : "Enabled"
      networkAcls         = { defaultAction = "Allow", bypass = "AzureServices" }
      }, var.networkIsolation && var.deployAiFoundrySubnet ? {
      networkInjections = [{
        scenario                   = "agent"
        subnetArmId                = local.subnet_ids.agent
        useMicrosoftManagedNetwork = false
      }]
    } : {})
  }
  response_export_values = ["properties.endpoint"]
}

resource "azapi_resource" "foundry_project" {
  count     = local.services_project ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-07-01-preview"
  parent_id = azapi_resource.foundry_account[0].id
  name      = local.resource_names.aiFoundryProjectName
  location  = local.effective_locations.main
  tags      = var.deploymentTags
  identity {
    type = "SystemAssigned"
  }
  body = {
    properties = {
      displayName = try(length(trimspace(var.aiFoundryProjectDisplayName)) > 0, false) ? var.aiFoundryProjectDisplayName : local.resource_names.aiFoundryProjectName
      description = try(length(trimspace(var.aiFoundryProjectDescription)) > 0, false) ? var.aiFoundryProjectDescription : "This is the default project for AI Foundry."
    }
  }
  response_export_values = ["properties.internalId", "properties.endpoints"]
  lifecycle {
    postcondition {
      condition     = can(regex("^[0-9a-fA-F]{32}$", self.output.properties.internalId))
      error_message = "Foundry project must return a 32-hex internalId before workspace-scoped authorization can be constructed."
    }
  }
}

resource "azapi_resource" "model_deployment" {
  for_each  = { for deployment in local.services_model_deployments : deployment.name => deployment if var.deployAiFoundry }
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  parent_id = azapi_resource.foundry_account[0].id
  name      = each.key
  body = {
    sku = each.value.sku
    properties = merge({
      model         = each.value.model
      raiPolicyName = try(each.value.raiPolicyName, null) == null ? "Microsoft.Default" : each.value.raiPolicyName
      }, {
      for key, value in {
        versionUpgradeOption    = try(each.value.versionUpgradeOption, null)
        spilloverDeploymentName = try(each.value.spilloverDeploymentName, null)
        scaleSettings           = try(each.value.scaleSettings, null)
        capacitySettings        = try(each.value.capacitySettings, null)
      } : key => value if value != null
    })
  }
  lifecycle {
    # config/aifoundry/setup.py owns ONLY this attachment, not capacity/model.
    ignore_changes = [body.properties.raiPolicyName]
  }
  depends_on = [terraform_data.foundry_model_contract]
}

locals {
  services_project_internal_id = local.services_project ? azapi_resource.foundry_project[0].output.properties.internalId : ""
  foundry_context = {
    account_id           = var.deployAiFoundry ? azapi_resource.foundry_account[0].id : ""
    account_name         = var.deployAiFoundry ? local.resource_names.aiFoundryAccountName : ""
    account_endpoint     = var.deployAiFoundry ? "https://${local.resource_names.aiFoundryAccountName}.cognitiveservices.azure.com/" : ""
    account_principal_id = var.deployAiFoundry ? azapi_resource.foundry_account[0].identity[0].principal_id : ""
    project_id           = local.services_project ? azapi_resource.foundry_project[0].id : ""
    project_name         = local.services_project ? local.resource_names.aiFoundryProjectName : ""
    project_endpoint     = local.services_project ? "https://${local.resource_names.aiFoundryAccountName}.services.ai.azure.com/api/projects/${local.resource_names.aiFoundryProjectName}" : ""
    project_principal_id = local.services_project ? azapi_resource.foundry_project[0].identity[0].principal_id : ""
    project_workspace_id = local.services_project ? format("%s-%s-%s-%s-%s",
      substr(local.services_project_internal_id, 0, 8),
      substr(local.services_project_internal_id, 8, 4),
      substr(local.services_project_internal_id, 12, 4),
      substr(local.services_project_internal_id, 16, 4),
      substr(local.services_project_internal_id, 20, 12)
    ) : ""
    search_connection_id         = var.deployAiFoundry && var.deploySearchService ? "${local.services_project_arm_path}/connections/${local.services_connection_names.search}" : ""
    knowledge_base_connection_id = var.deployAiFoundry && var.deploySearchService && var.retrievalBackend == "foundry_iq" ? "${local.services_project_arm_path}/connections/${var.knowledgeBaseConnectionName}" : ""
    bing_connection_id           = var.deployAiFoundry && var.deployGroundingWithBing ? "${local.services_project_arm_path}/connections/${local.services_connection_names.bing}" : ""
  }
  # This is intentionally a project-scoped runtime path, even though connections
  # are ARM account children; source consumers rely on project visibility.
  services_project_arm_path = "${var.deployAiFoundry ? azapi_resource.foundry_account[0].id : ""}/projects/${local.resource_names.aiFoundryProjectName}"
}

# Identity worker supplies initial grant resource IDs ONLY, never grants that
# depend on capability host completion. Keeping this separate avoids a cycle.
resource "terraform_data" "foundry_initial_authorization" {
  count = local.services_project && local.services_agent_service ? 1 : 0
  input = local.foundry_authorization_ready
}

resource "terraform_data" "foundry_private_connectivity" {
  count = local.services_project && local.services_agent_service ? 1 : 0
  # Completion IDs, not endpoint descriptors. BYO connectivity is an external
  # prerequisite and must not cause Terraform to adopt foreign endpoint children.
  input = var.networkIsolation ? local.foundry_private_connectivity_ready : []
}

# Separate resources preserve the existing Cosmos -> Storage -> Search ordering.
resource "azapi_resource" "project_cosmos_connection" {
  count     = local.services_project && local.services_agent_service ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-07-01-preview"
  parent_id = local.foundry_context.project_id
  name      = local.services_connection_names.associated_cosmos
  body = {
    properties = {
      category = "CosmosDB"
      target   = local.services_foundry_cosmos_endpoint
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = local.foundry_dependencies.cosmos_id
        location   = var.aiFoundryCosmosDBAccountResourceId != "" ? data.azapi_resource.foundry_existing_dependency["cosmos"].location : local.effective_locations.main
      }
    }
  }
  depends_on = [terraform_data.foundry_initial_authorization, terraform_data.foundry_private_connectivity]
}

resource "azapi_resource" "project_storage_connection" {
  count     = local.services_project && local.services_agent_service ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-07-01-preview"
  parent_id = local.foundry_context.project_id
  name      = local.services_connection_names.associated_storage
  body = {
    properties = {
      category = "AzureStorageAccount"
      target   = local.services_foundry_storage_endpoint
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = local.foundry_dependencies.storage_id
        location   = var.aiFoundryStorageAccountResourceId != "" ? data.azapi_resource.foundry_existing_dependency["storage"].location : local.effective_locations.main
      }
    }
  }
  depends_on = [azapi_resource.project_cosmos_connection]
}

resource "azapi_resource" "project_search_connection" {
  count     = local.services_project && local.services_agent_service ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-07-01-preview"
  parent_id = local.foundry_context.project_id
  name      = local.services_connection_names.associated_search
  body = {
    properties = {
      category = "CognitiveSearch"
      target   = "https://${local.foundry_dependencies.search_name}.search.windows.net/"
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = local.foundry_dependencies.search_id
        location   = var.aiSearchResourceId != "" ? data.azapi_resource.foundry_existing_dependency["search"].location : local.effective_locations.search
      }
    }
  }
  depends_on = [azapi_resource.project_storage_connection]
}

resource "azapi_resource" "account_capability_host" {
  count      = local.services_project && local.services_agent_service ? 1 : 0
  type       = "Microsoft.CognitiveServices/accounts/capabilityHosts@2025-07-01-preview"
  parent_id  = local.foundry_context.account_id
  name       = "chagent${replace(local.resource_names.aiFoundryAccountName, "-", "")}"
  body       = { properties = { capabilityHostKind = "Agents", tags = var.deploymentTags } }
  depends_on = [azapi_resource.project_search_connection]
}

resource "azapi_resource" "project_capability_host" {
  count     = local.services_project && local.services_agent_service ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-07-01-preview"
  parent_id = local.foundry_context.project_id
  name      = "chagent${replace(local.resource_names.aiFoundryProjectName, "-", "")}"
  body = {
    properties = {
      threadStorageConnections = [azapi_resource.project_cosmos_connection[0].name]
      storageConnections       = [azapi_resource.project_storage_connection[0].name]
      vectorStoreConnections   = [azapi_resource.project_search_connection[0].name]
    }
  }
  # ARM 2025-07-01-preview ProjectCapabilityHostProperties / OpenAPI
  # ProjectCapabilityHost allow connection lists only (plus read-only state).
  # capabilityHostKind and nested tags belong to the ACCOUNT capability host,
  # not this project child. Do not copy those Bicep fields or bypass validation.
  # https://github.com/Azure/azure-resource-manager-schemas/blob/main/schemas/2025-07-01-preview/Microsoft.CognitiveServices.json
  schema_validation_enabled = true
  depends_on                = [azapi_resource.account_capability_host]
}

locals {
  foundry_capability_host_id = local.services_project && local.services_agent_service ? azapi_resource.project_capability_host[0].id : ""
  services_account_connections = merge(
    var.deployAiFoundry && var.deployStorageAccount ? {
      storage = {
        name = local.services_connection_names.storage
        properties = {
          category      = "AzureStorageAccount"
          target        = local.data_context.storage.blob_endpoint
          authType      = "AAD"
          isSharedToAll = true
          metadata      = { ApiType = "Azure", ResourceId = local.data_context.storage.id }
        }
      }
    } : {},
    var.deployAiFoundry && var.deploySearchService ? {
      search = {
        name = local.services_connection_names.search
        properties = {
          category      = "CognitiveSearch"
          target        = local.data_context.search.endpoint
          authType      = "AAD"
          isSharedToAll = true
          metadata      = { ApiType = "Azure", ResourceId = local.data_context.search.id, location = local.effective_locations.search }
        }
      }
    } : {},
    var.deployAiFoundry && var.deploySearchService && var.retrievalBackend == "foundry_iq" ? {
      knowledge = {
        name = var.knowledgeBaseConnectionName
        properties = {
          category      = "CognitiveSearch"
          target        = local.data_context.search.endpoint
          authType      = "AAD"
          isSharedToAll = true
          metadata      = { ApiType = "Azure", ResourceId = local.data_context.search.id, location = local.effective_locations.search }
        }
      }
    } : {}
  )
}

resource "azapi_resource" "account_connection" {
  for_each   = local.services_account_connections
  type       = "Microsoft.CognitiveServices/accounts/connections@2025-06-01"
  parent_id  = local.foundry_context.account_id
  name       = each.value.name
  body       = { properties = each.value.properties }
  depends_on = [terraform_data.foundry_connection_contract]
}

resource "azapi_resource" "insights_connection" {
  count     = var.deployAiFoundry && (local.services_existing_ai != "" || local.services_create_ai) ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/connections@2025-06-01"
  parent_id = local.foundry_context.account_id
  name      = local.services_connection_names.insights
  body = {
    properties = {
      category      = "AppInsights"
      target        = local.effective_observability.app_insights_id
      authType      = "ApiKey"
      isSharedToAll = true
      credentials   = { key = local.effective_observability.connection_string }
      metadata      = { ApiType = "Azure", ResourceId = local.effective_observability.app_insights_id }
    }
  }
}

resource "azapi_resource" "bing" {
  count                  = var.deployAiFoundry && var.deployGroundingWithBing ? 1 : 0
  type                   = "Microsoft.Bing/accounts@2025-05-01-preview"
  parent_id              = local.services_foundry_rg_id
  name                   = local.resource_names.bingSearchName
  location               = "global"
  body                   = { kind = "Bing.Grounding", sku = { name = "G1" } }
  response_export_values = ["properties.endpoint"]
  # AzAPI 2.13.0 contains no Microsoft.Bing/accounts type at all (validate:
  # "resource type Microsoft.Bing/accounts can't be found"). This resource-only
  # coverage exception retains the exact API/location/kind/SKU in Microsoft's
  # pinned Foundry reference, which likewise suppresses missing Bicep type BCP081:
  # https://github.com/Azure-Samples/microsoft-foundry-baseline/blob/d670eb265b8c55d1a6dd97020dca3f2835c3639b/infra-as-code/bicep/bing-grounding.bicep
  # services.tftest.hcl locks this payload; it is not Azure acceptance evidence.
  # Cognitive Services connections and capability hosts keep schema validation.
  schema_validation_enabled = false
}

data "azapi_resource_action" "bing_keys" {
  count                  = var.deployAiFoundry && var.deployGroundingWithBing ? 1 : 0
  type                   = "Microsoft.Bing/accounts@2025-05-01-preview"
  resource_id            = azapi_resource.bing[0].id
  action                 = "listKeys"
  response_export_values = ["key1"]
}

resource "azapi_resource" "bing_connection" {
  count     = var.deployAiFoundry && var.deployGroundingWithBing ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/connections@2025-06-01"
  parent_id = local.foundry_context.account_id
  name      = local.services_connection_names.bing
  body = {
    properties = {
      category      = "GroundingWithBingSearch"
      target        = azapi_resource.bing[0].output.properties.endpoint
      authType      = "ApiKey"
      isSharedToAll = true
      credentials   = { key = sensitive(data.azapi_resource_action.bing_keys[0].output.key1) }
      metadata      = { ApiType = "Azure", Location = "global", ResourceId = azapi_resource.bing[0].id }
    }
  }
  schema_validation_enabled = true
}

locals {
  services_spl_token = "${substr(local.resource_names.searchServiceName, 0, min(21, length(local.resource_names.searchServiceName)))}-${substr(provider::azapi::unique_string([local.resource_names.searchServiceName]), 0, 6)}"
  services_foundry_link_groups = {
    openai_account            = "Allow AI Search private access to Azure OpenAI embeddings for Foundry IQ."
    foundry_account           = "Allow AI Search private access to Microsoft Foundry for Foundry IQ."
    cognitiveservices_account = "Allow AI Search private access to Cognitive Services for Foundry IQ standard extraction."
  }
  search_shared_private_links = merge(
    var.networkIsolation && var.deploySearchService && var.deployStorageAccount ? {
      blob = {
        name                  = "spl-${local.resource_names.searchServiceName}-blob-0"
        groupId               = "blob"
        privateLinkResourceId = local.data_context.storage.id
        requestMessage        = "Allow AI Search private access to blob storage."
      }
    } : {},
    {
      for group, message in local.services_foundry_link_groups : group => {
        name                  = length("spl-${local.resource_names.searchServiceName}-${group}-1") <= 60 ? "spl-${local.resource_names.searchServiceName}-${group}-1" : "spl-${local.services_spl_token}-${group}-1"
        groupId               = group
        privateLinkResourceId = local.foundry_context.account_id
        requestMessage        = message
      } if var.networkIsolation && var.deploySearchService && var.deployAiFoundry && var.retrievalBackend == "foundry_iq"
    }
  )
  search_shared_private_link_readiness = [
    for key in concat(contains(keys(local.search_shared_private_links), "blob") ? ["blob"] : [], [
      for group in ["openai_account", "foundry_account", "cognitiveservices_account"] : group if contains(keys(local.search_shared_private_links), group)
      ]) : {
      name                  = local.search_shared_private_links[key].name
      groupId               = local.search_shared_private_links[key].groupId
      privateLinkResourceId = local.search_shared_private_links[key].privateLinkResourceId
    }
  ]
}

# Serialize outbound updates to the Search parent. Approval/readiness is owned by
# config/search/private_link_readiness.py, not a local-exec or successful fallback.
resource "azapi_resource" "search_blob_link" {
  for_each  = { for key, link in local.search_shared_private_links : key => link if key == "blob" }
  type      = "Microsoft.Search/searchServices/sharedPrivateLinkResources@2025-05-01"
  parent_id = local.data_context.search.id
  name      = each.value.name
  body      = { properties = { groupId = each.value.groupId, privateLinkResourceId = each.value.privateLinkResourceId, requestMessage = each.value.requestMessage } }
}

resource "azapi_resource" "search_openai_link" {
  for_each   = { for key, link in local.search_shared_private_links : key => link if key == "openai_account" }
  type       = "Microsoft.Search/searchServices/sharedPrivateLinkResources@2025-05-01"
  parent_id  = local.data_context.search.id
  name       = each.value.name
  body       = { properties = { groupId = each.value.groupId, privateLinkResourceId = each.value.privateLinkResourceId, requestMessage = each.value.requestMessage } }
  depends_on = [azapi_resource.search_blob_link, azapi_resource.foundry_project]
}

resource "azapi_resource" "search_foundry_link" {
  for_each   = { for key, link in local.search_shared_private_links : key => link if key == "foundry_account" }
  type       = "Microsoft.Search/searchServices/sharedPrivateLinkResources@2025-05-01"
  parent_id  = local.data_context.search.id
  name       = each.value.name
  body       = { properties = { groupId = each.value.groupId, privateLinkResourceId = each.value.privateLinkResourceId, requestMessage = each.value.requestMessage } }
  depends_on = [azapi_resource.search_openai_link]
}

resource "azapi_resource" "search_cognitive_link" {
  for_each   = { for key, link in local.search_shared_private_links : key => link if key == "cognitiveservices_account" }
  type       = "Microsoft.Search/searchServices/sharedPrivateLinkResources@2025-05-01"
  parent_id  = local.data_context.search.id
  name       = each.value.name
  body       = { properties = { groupId = each.value.groupId, privateLinkResourceId = each.value.privateLinkResourceId, requestMessage = each.value.requestMessage } }
  depends_on = [azapi_resource.search_foundry_link]
}
