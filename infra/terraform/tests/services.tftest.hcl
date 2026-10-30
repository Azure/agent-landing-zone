# Offline provider mocks are contract evidence, not Azure availability/RBAC,
# private-link readiness, quota, consent or document-authorization evidence.
mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      subscription_id = "00000000-0000-0000-0000-000000000001"
      tenant_id       = "00000000-0000-0000-0000-000000000002"
      object_id       = "00000000-0000-0000-0000-000000000003"
      client_id       = "00000000-0000-0000-0000-000000000004"
    }
  }
  mock_data "azurerm_resource_group" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-services"
      location = "eastus"
    }
  }
}
mock_provider "azapi" {
  mock_data "azapi_resource" {
    defaults = {
      location = "eastus"
      output = {
        properties = {
          primaryEndpoints = { blob = "https://tfservices.blob.core.windows.net/" }
          documentEndpoint = "https://tfservices.documents.azure.com:443/"
        }
      }
    }
  }
  mock_resource "azapi_resource" {
    defaults = {
      output = {
        properties = {
          primaryEndpoints   = { blob = "https://tfservices.blob.core.windows.net/" }
          documentEndpoint   = "https://tfservices.documents.azure.com:443/"
          endpoint           = "https://tfservices.azconfig.io"
          ConnectionString   = "InstrumentationKey=00000000-0000-0000-0000-000000000005;IngestionEndpoint=https://eastus.in.applicationinsights.azure.com/"
          InstrumentationKey = "00000000-0000-0000-0000-000000000005"
          internalId         = "00112233445566778899aabbccddeeff"
          endpoints          = {}
        }
      }
    }
  }
}
mock_provider "modtm" {}
mock_provider "random" {}
mock_provider "time" {}

variables {
  subscriptionId          = "00000000-0000-0000-0000-000000000001"
  environmentName         = "tf-services"
  resourceGroupName       = "rg-tf-services"
  location                = "eastus"
  principalId             = "00000000-0000-0000-0000-000000000003"
  resourceToken           = "tfservices001"
  deployContainerApps     = false
  deployContainerEnv      = false
  deployContainerRegistry = false
  deployJumpbox           = false
  deployBastion           = false
  deployNatGateway        = false
  deployGroundingWithBing = false
  deployCosmosDb          = true
  databaseContainersList = [{
    name           = "history"
    canonical_name = "HISTORY_CONTAINER"
    partitionKey   = "principal_id"
    throughput     = 600
    indexingPolicy = {
      automatic     = true
      indexingMode  = "consistent"
      includedPaths = [{ path = "/*" }]
      excludedPaths = [{ path = "/_etag/?" }]
      compositeIndexes = [
        [{ path = "/isDeleted", order = "ascending" }, { path = "/_ts", order = "descending" }]
      ]
    }
  }]
}

run "serverless_data_and_keyless_defaults" {
  command = plan

  assert {
    condition = (
      azapi_resource.application_cosmos[0].body.properties.disableLocalAuth &&
      azapi_resource.application_cosmos[0].body.properties.disableKeyBasedMetadataWriteAccess &&
      azapi_resource.application_cosmos[0].body.properties.backupPolicy.continuousModeProperties.tier == "Continuous30Days" &&
      azapi_resource.application_cosmos[0].body.properties.capabilities[0].name == "EnableServerless"
    )
    error_message = "Application Cosmos must retain keyless, continuous-backup, serverless defaults."
  }
  assert {
    condition = (
      azapi_resource.application_container["history"].body.properties.resource.partitionKey.paths[0] == "/principal_id" &&
      azapi_resource.application_container["history"].body.properties.resource.partitionKey.kind == "Hash" &&
      azapi_resource.application_container["history"].body.properties.resource.partitionKey.version == 1 &&
      azapi_resource.application_container["history"].body.properties.resource.defaultTtl == -1 &&
      !can(azapi_resource.application_container["history"].body.properties.options) &&
      !can(azapi_resource.application_container["history"].body.depends_on)
    )
    error_message = "Partition normalization/Hash-v1/TTL must match Bicep; serverless must not submit throughput."
  }
  assert {
    condition = (
      jsonencode(azapi_resource.application_container["history"].body.properties.resource.indexingPolicy) ==
      jsonencode({ for key, value in var.databaseContainersList[0].indexingPolicy : key => value if value != null }) &&
      !can(azapi_resource.application_container["history"].body.properties.resource.indexingPolicy.fullTextIndexes)
    )
    error_message = "Custom indexing, including composite indexes, must survive unchanged."
  }
  assert {
    condition = (
      !azapi_resource.solution_storage[0].body.properties.allowBlobPublicAccess &&
      azapi_resource.solution_storage[0].body.properties.encryption.requireInfrastructureEncryption &&
      azapi_resource.solution_blob_service[0].body.properties.automaticSnapshotPolicyEnabled &&
      azapi_resource.solution_blob_service[0].body.properties.containerDeleteRetentionPolicy.days == 10 &&
      azapi_resource.solution_blob_service[0].body.properties.deleteRetentionPolicy.days == 7 &&
      length(azapi_resource.legacy_application_key) == 0 &&
      local.app_config_bootstrap.label == "agent-lz" &&
      local.app_config_bootstrap.owner == "terraform" &&
      local.app_config_bootstrap.runtime_owner == "shared-postProvision"
    )
    error_message = "Storage protection and single-owner keyless configuration bootstrap must be preserved."
  }
  assert {
    condition = (
      azapi_resource.foundry_account[0].identity[0].type == "SystemAssigned" &&
      azapi_resource.foundry_account[0].body.properties.disableLocalAuth &&
      azapi_resource.foundry_project[0].identity[0].type == "SystemAssigned" &&
      length(azapi_resource.project_capability_host) == 1
    )
    error_message = "Foundry project MI and Agent Service capability prerequisites must not be replaced by hosted runtime resources."
  }
  assert {
    condition = (
      azapi_resource.project_capability_host[0].schema_validation_enabled &&
      toset(keys(azapi_resource.project_capability_host[0].body)) == toset(["properties"]) &&
      toset(keys(azapi_resource.project_capability_host[0].body.properties)) ==
      toset(["threadStorageConnections", "storageConnections", "vectorStoreConnections"]) &&
      length(azapi_resource.project_capability_host[0].body.properties.threadStorageConnections) == 1 &&
      length(azapi_resource.project_capability_host[0].body.properties.storageConnections) == 1 &&
      length(azapi_resource.project_capability_host[0].body.properties.vectorStoreConnections) == 1 &&
      azapi_resource.account_capability_host[0].body.properties.capabilityHostKind == "Agents"
    )
    error_message = "The exact 2025-07-01-preview project capability-host payload accepts connection lists, not account-only capabilityHostKind/tags; embedded validation must remain enabled."
  }
  assert {
    condition = (
      alltrue([
        for key, name in local.services_connection_names :
        can(regex("^[a-zA-Z0-9][a-zA-Z0-9_-]{2,32}$", name))
      ]) &&
      azapi_resource.project_cosmos_connection[0].name == local.services_connection_names.associated_cosmos &&
      azapi_resource.account_connection["search"].name == local.services_connection_names.search
    )
    error_message = "Generated CAF connection names must honor the independent 33-character connection API limit."
  }
}

run "disabled_application_cosmos_preserves_foundry_storage" {
  command = plan
  variables {
    deployCosmosDb   = false
    useUAI           = true
    networkIsolation = true
  }
  assert {
    condition = (
      length(azapi_resource.application_cosmos) == 0 &&
      length(azapi_resource.application_database) == 0 &&
      length(azapi_resource.application_container) == 0 &&
      length(azurerm_cosmosdb_sql_role_assignment.application) == 0 &&
      !contains(keys(azurerm_user_assigned_identity.service), "cosmos") &&
      !contains(keys(local.private_endpoints), "cosmos") &&
      local.services_foundation_plain_settings.DATABASE_ACCOUNT_NAME == "" &&
      local.services_foundation_plain_settings.DATABASE_NAME == "" &&
      !contains(keys(local.services_foundation_plain_settings), "COSMOS_DB_ENDPOINT") &&
      !contains(keys(local.services_foundation_plain_settings), "HISTORY_CONTAINER")
    )
    error_message = "Disabled application Cosmos must not create dedicated artifacts or publish phantom database settings."
  }
  assert {
    condition = (
      length(azapi_resource.foundry_cosmos) == 1 &&
      length(azapi_resource.project_cosmos_connection) == 1 &&
      length(azapi_resource.project_capability_host) == 1 &&
      contains(keys(local.network_foundry_private_endpoints), "foundryCosmos") &&
      contains(keys(local.network_managed_dns), "Cosmos")
    )
    error_message = "Application Cosmos selection must not remove Foundry storage, its capability host, endpoint or shared DNS."
  }
}

run "bing_provider_coverage_exception_keeps_reference_payload" {
  command = plan
  variables {
    deployGroundingWithBing = true
  }
  assert {
    condition = (
      azapi_resource.bing[0].type == "Microsoft.Bing/accounts@2025-05-01-preview" &&
      azapi_resource.bing[0].location == "global" &&
      jsonencode(azapi_resource.bing[0].body) == jsonencode({ kind = "Bing.Grounding", sku = { name = "G1" } }) &&
      !azapi_resource.bing[0].schema_validation_enabled &&
      azapi_resource.bing_connection[0].schema_validation_enabled &&
      azapi_resource.project_capability_host[0].schema_validation_enabled
    )
    error_message = "Only the Bing resource missing from AzAPI 2.13.0's type registry may skip validation; its payload must match the pinned Microsoft reference."
  }
  assert {
    condition = (
      azapi_resource.bing_connection[0].body.properties.category == "GroundingWithBingSearch" &&
      azapi_resource.bing_connection[0].body.properties.authType == "ApiKey" &&
      toset(keys(azapi_resource.bing_connection[0].body.properties.credentials)) == toset(["key"]) &&
      azapi_resource.bing_connection[0].name == local.services_connection_names.bing &&
      can(regex("^[a-zA-Z0-9][a-zA-Z0-9_-]{2,32}$", azapi_resource.bing_connection[0].name))
    )
    error_message = "Bing grounding must retain its API-key connection contract and bounded child name."
  }
}

run "disabled_services_have_concrete_absent_values" {
  command = plan
  variables {
    deployStorageAccount = false
    deployCosmosDb       = false
    deploySearchService  = false
    deployKeyVault       = false
    deployAppConfig      = false
    deployAiFoundry      = false
    deploySpeechService  = false
    deployLogAnalytics   = false
    deployAppInsights    = false
  }
  assert {
    condition = (
      local.data_context.storage.id == "" &&
      local.data_context.storage.documents_container_id == "" &&
      local.data_context.cosmos.endpoint == "" &&
      local.data_context.cosmos.database_name == "" &&
      local.data_context.search.endpoint == "" &&
      local.data_context.key_vault.uri == "" &&
      local.data_context.app_config.endpoint == "" &&
      local.foundry_context.project_id == "" &&
      local.foundry_dependencies.storage_id == "" &&
      local.effective_observability.connection_string == "" &&
      !local.effective_observability.ampls &&
      length(azapi_resource.foundation_setting) == 0 &&
      length(azapi_resource.legacy_application_key_reference) == 0
    )
    error_message = "Disabled optional scalar values must be typed empty strings, not dynamic nulls or phantom resource IDs."
  }
}

run "existing_foundry_dependencies_are_read_only" {
  command = plan
  variables {
    aiFoundryStorageAccountResourceId  = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.Storage/storageAccounts/sharedstorage"
    aiSearchResourceId                 = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.Search/searchServices/sharedsearch"
    aiFoundryCosmosDBAccountResourceId = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.DocumentDB/databaseAccounts/sharedcosmos"
    keyVaultResourceId                 = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.KeyVault/vaults/sharedvault"
  }
  # Read-only data-source IDs must model real ARM IDs, not generated random
  # strings. No resource body/name or schema validation is overridden.
  override_data {
    target = data.azapi_resource.foundry_existing_dependency["storage"]
    values = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.Storage/storageAccounts/sharedstorage"
      location = "eastus"
      output   = { properties = { primaryEndpoints = { blob = "https://sharedstorage.blob.core.windows.net/" } } }
    }
  }
  override_data {
    target = data.azapi_resource.foundry_existing_dependency["search"]
    values = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.Search/searchServices/sharedsearch"
      location = "eastus"
    }
  }
  override_data {
    target = data.azapi_resource.foundry_existing_dependency["cosmos"]
    values = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.DocumentDB/databaseAccounts/sharedcosmos"
      location = "eastus"
      output   = { properties = { documentEndpoint = "https://sharedcosmos.documents.azure.com:443/" } }
    }
  }
  override_data {
    target = data.azapi_resource.foundry_existing_dependency["vault"]
    values = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.KeyVault/vaults/sharedvault"
      location = "eastus"
    }
  }
  assert {
    condition = (
      !anytrue(values(local.foundry_dependencies.owned)) &&
      length(azapi_resource.foundry_storage) == 0 &&
      length(azapi_resource.foundry_cosmos) == 0 &&
      length(module.foundry_search) == 0 &&
      length(module.foundry_vault) == 0 &&
      length(data.azapi_resource.foundry_existing_dependency) == 4 &&
      local.foundry_dependencies.storage_name == "sharedstorage"
    )
    error_message = "BYO Agent Service dependencies must suppress creation, not adopt shared resources into state."
  }
}

run "disabled_project_has_no_project_authorization_or_capability_hosts" {
  command = plan
  variables {
    deployAfProject = false
  }
  assert {
    condition = (
      local.foundry_context.project_id == "" &&
      local.foundry_context.project_principal_id == "" &&
      local.foundry_context.project_workspace_id == "" &&
      local.foundry_capability_host_id == "" &&
      length(azapi_resource.foundry_project) == 0 &&
      length(azapi_resource.project_capability_host) == 0 &&
      length(local.foundry_authorization_ready) == 0 &&
      length(azapi_resource.foundry_memory) == 0 &&
      length(azurerm_role_assignment.foundry_workspace_storage) == 0 &&
      length([
        for key in keys(local.rbac_assignments) : key
        if startswith(key, "cross:project_") || startswith(key, "cross:associated_") || startswith(key, "post:")
      ]) == 0
    )
    error_message = "deployAfProject=false must suppress project identities, capability hosts and all initial/post-host project grants."
  }
}

run "byo_cosmos_authorization_preserves_foreign_subscription" {
  command = plan
  variables {
    aiFoundryCosmosDBAccountResourceId = "/subscriptions/00000000-0000-0000-0000-000000000099/resourceGroups/rg-shared/providers/Microsoft.DocumentDB/databaseAccounts/sharedcosmos"
  }
  override_data {
    target = data.azapi_resource.foundry_existing_dependency["cosmos"]
    values = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000099/resourceGroups/rg-shared/providers/Microsoft.DocumentDB/databaseAccounts/sharedcosmos"
      location = "eastus"
      output   = { properties = { documentEndpoint = "https://sharedcosmos.documents.azure.com:443/" } }
    }
  }
  assert {
    condition = (
      length(azapi_resource.foundry_cosmos) == 0 &&
      azapi_resource.foundry_memory["this"].parent_id == var.aiFoundryCosmosDBAccountResourceId &&
      azapi_resource.foundry_memory["this"].body.properties.scope == "${var.aiFoundryCosmosDBAccountResourceId}/dbs/enterprise_memory" &&
      startswith(azapi_resource.foundry_memory["this"].body.properties.roleDefinitionId, "${var.aiFoundryCosmosDBAccountResourceId}/sqlRoleDefinitions/") &&
      local.foundation_rbac_assignments["cross:associated_cosmos"].role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000099/providers/Microsoft.Authorization/roleDefinitions/${local.identity_roles.CosmosDBOperator.guid}"
    )
    error_message = "BYO Cosmos SQL and ARM authorization must target the exact foreign account subscription, never the default provider subscription."
  }
}

run "no_law_means_no_insights_or_ampls" {
  command = plan
  variables {
    deployLogAnalytics = false
    deployAppInsights  = true
  }
  assert {
    condition     = !local.effective_observability.create_app_insights && !local.effective_observability.ampls && length(azapi_resource.app_insights) == 0
    error_message = "Application Insights requires an effective LAW."
  }
}

run "legacy_bootstrap_is_labeled_key_vault_reference_only" {
  command = plan
  plan_options {
    target = [azapi_resource.legacy_application_key_reference]
  }
  variables {
    useCAppAPIKey       = true
    deployContainerApps = true
    deployContainerEnv  = true
  }
  # Faithful 404 reads: generic AzAPI mocks otherwise look like foreign apps.
  # Do not override shell resource inputs, payloads or preservation guards.
  override_data {
    target = data.azapi_resource.compute_app["frontend"]
    values = { exists = false, output = null }
  }
  override_data {
    target = data.azapi_resource.compute_app["orchestrator"]
    values = { exists = false, output = null }
  }
  override_data {
    target = data.azapi_resource.compute_app["dataingest"]
    values = { exists = false, output = null }
  }
  override_module {
    target          = module.application_vault[0]
    override_during = plan
    outputs = {
      resource_id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-services/providers/Microsoft.KeyVault/vaults/tfservices-vault"
      name        = "tfservices-vault"
      uri         = "https://tfservices-vault.vault.azure.net/"
    }
  }
  assert {
    condition = alltrue([
      for key, reference in azapi_resource.legacy_application_key_reference :
      endswith(reference.name, "$agent-lz") &&
      reference.body.properties.contentType == "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8" &&
      jsondecode(reference.body.properties.value).uri == "https://tfservices-vault.vault.azure.net/secrets/${replace(key, "_", "-")}"
    ]) && length(azapi_resource.legacy_application_key_reference) == length(var.containerAppsList)
    error_message = "Legacy opt-in keys must be versionless Key Vault references under agent-lz, never plaintext App Configuration values."
  }
}

run "embedding_declared_default_reaches_resource" {
  command = plan
  assert {
    condition = (
      length(azapi_resource.model_deployment) == 2 &&
      azapi_resource.model_deployment["text-embedding"].body.sku.name == "GlobalStandard" &&
      azapi_resource.model_deployment["text-embedding"].body.sku.capacity == 100 &&
      azapi_resource.model_deployment["text-embedding"].body.properties.model.name == "text-embedding-3-large" &&
      azapi_resource.model_deployment["text-embedding"].body.properties.model.version == "1" &&
      azapi_resource.model_deployment["text-embedding"].type == "Microsoft.CognitiveServices/accounts/deployments@2025-06-01" &&
      var.modelDeploymentList[1].apiVersion == "2025-01-01-preview" &&
      var.modelDeploymentList[1].canonical_name == "EMBEDDING_DEPLOYMENT_NAME"
    )
    error_message = "The typed declared embedding default must reach the actual resource as GlobalStandard/100 without model, version, name or API drift."
  }
}

run "embedding_empty_list_fallback_reaches_resource" {
  command = plan
  variables {
    modelDeploymentList = []
  }
  assert {
    condition = (
      length(azapi_resource.model_deployment) == 2 &&
      azapi_resource.model_deployment["text-embedding-3-large"].body.sku.name == "GlobalStandard" &&
      azapi_resource.model_deployment["text-embedding-3-large"].body.sku.capacity == 10 &&
      azapi_resource.model_deployment["text-embedding-3-large"].body.properties.model.format == "OpenAI" &&
      azapi_resource.model_deployment["text-embedding-3-large"].body.properties.model.name == "text-embedding-3-large" &&
      azapi_resource.model_deployment["text-embedding-3-large"].body.properties.model.version == "1" &&
      azapi_resource.model_deployment["gpt-5-nano"].body.sku.capacity == 40
    )
    error_message = "An explicit empty list must retain the foundation fallback names/models/capacities, changing only the embedding SKU."
  }
}

run "embedding_explicit_standard_override_reaches_resource" {
  command = plan
  variables {
    modelDeploymentList = [{
      name           = "custom-embedding"
      canonical_name = "CUSTOM_EMBEDDING"
      apiVersion     = "2025-01-01-preview"
      model          = { format = "OpenAI", name = "text-embedding-3-large", version = "1" }
      sku            = { name = "Standard", capacity = 37 }
    }]
  }
  assert {
    condition = (
      length(azapi_resource.model_deployment) == 1 &&
      azapi_resource.model_deployment["custom-embedding"].body.sku.name == "Standard" &&
      azapi_resource.model_deployment["custom-embedding"].body.sku.capacity == 37 &&
      azapi_resource.model_deployment["custom-embedding"].body.properties.model.name == "text-embedding-3-large" &&
      azapi_resource.model_deployment["custom-embedding"].body.properties.model.version == "1"
    )
    error_message = "Explicit Standard lists must not be rewritten or supplemented by the GlobalStandard fallback."
  }
}

run "model_settings_and_runtime_api_version_remain_distinct" {
  command = plan
  variables {
    modelDeploymentList = [{
      name                 = "custom-chat"
      canonical_name       = "CUSTOM_CHAT"
      apiVersion           = "2025-12-01-preview"
      model                = { format = "OpenAI", name = "gpt-5-nano", version = "2025-08-07" }
      sku                  = { name = "GlobalStandard", capacity = 40 }
      versionUpgradeOption = "NoAutoUpgrade"
      capacitySettings     = { designatedCapacity = 40, priority = 1 }
      raiPolicyName        = "Microsoft.DefaultV2"
    }]
  }
  assert {
    condition = (
      azapi_resource.model_deployment["custom-chat"].type == "Microsoft.CognitiveServices/accounts/deployments@2025-06-01" &&
      azapi_resource.model_deployment["custom-chat"].body.sku.capacity == 40 &&
      azapi_resource.model_deployment["custom-chat"].body.properties.versionUpgradeOption == "NoAutoUpgrade" &&
      azapi_resource.model_deployment["custom-chat"].body.properties.capacitySettings.designatedCapacity == 40 &&
      !can(azapi_resource.model_deployment["custom-chat"].body.properties.dynamicThrottlingEnabled) &&
      azapi_resource.model_deployment["custom-chat"].body.properties.raiPolicyName == "Microsoft.DefaultV2"
    )
    error_message = "Model/SKU/capacity/upgrade settings must survive; runtime OpenAI apiVersion must not select the ARM resource API."
  }
}

run "read_only_deployment_throttling_is_rejected" {
  command = plan
  plan_options {
    target = [terraform_data.foundry_model_contract]
  }
  variables {
    modelDeploymentList = [{
      name                     = "custom-chat"
      canonical_name           = "CUSTOM_CHAT"
      model                    = { format = "OpenAI", name = "gpt-5-nano", version = "2025-08-07" }
      sku                      = { name = "GlobalStandard", capacity = 40 }
      dynamicThrottlingEnabled = true
    }]
  }
  expect_failures = [terraform_data.foundry_model_contract]
}

run "isolated_iq_links_keep_exact_groups_and_bounded_names" {
  command = plan
  # Exercise service composition without turning this into a duplicate network
  # topology test. In particular no fallback PE subnet is needed to shape SPLs.
  plan_options {
    target = [azapi_resource.search_cognitive_link]
  }
  variables {
    networkIsolation      = true
    deployAiFoundrySubnet = false
    allowedIpRanges       = ["203.0.113.0/24"]
    searchServiceName     = "search-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  assert {
    condition = (
      provider::azapi::unique_string(["fu", "bar"]) == "q5wxoscxs5j6k" &&
      length(local.search_shared_private_links) == 4 &&
      alltrue([
        for key, link in local.search_shared_private_links :
        key == "blob" || (length(link.name) <= 60 && endswith(link.name, "-${link.groupId}-1"))
      ]) &&
      toset([for link in local.search_shared_private_links : link.groupId]) ==
      toset(["blob", "openai_account", "foundry_account", "cognitiveservices_account"])
    )
    error_message = "Isolated Foundry IQ requires Blob and all three Foundry outbound groups with stable bounded Foundry names."
  }
  assert {
    condition = (
      azapi_resource.foundry_account[0].body.properties.publicNetworkAccess == "Disabled" &&
      azapi_resource.solution_storage[0].body.properties.publicNetworkAccess == "Enabled" &&
      azapi_resource.solution_storage[0].body.properties.networkAcls.defaultAction == "Deny" &&
      azapi_resource.solution_storage[0].body.properties.networkAcls.ipRules[0].value == "203.0.113.0/24"
    )
    error_message = "Preserve the documented Foundry exception: root IP allowlisting must not broaden isolated Foundry."
  }
}

run "central_observability_does_not_create_local_topology" {
  command = plan
  variables {
    existingLogAnalyticsWorkspaceResourceId     = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.OperationalInsights/workspaces/shared-law"
    existingApplicationInsightsResourceId       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.Insights/components/shared-ai"
    existingApplicationInsightsConnectionString = "InstrumentationKey=00000000-0000-0000-0000-000000000005;IngestionEndpoint=https://eastus.in.applicationinsights.azure.com/"
  }
  override_data {
    target = data.azapi_resource.existing_app_insights[0]
    values = {
      output = {
        properties = {
          WorkspaceResourceId = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.OperationalInsights/workspaces/shared-law"
        }
      }
    }
  }
  assert {
    condition = (
      !local.effective_observability.create_law &&
      !local.effective_observability.create_app_insights &&
      !local.effective_observability.ampls &&
      length(module.log_analytics) == 0 &&
      length(azapi_resource.app_insights) == 0 &&
      length(azapi_resource.monitor_scope) == 0
    )
    error_message = "Central observability reuse must not adopt a foreign LAW, component or AMPLS topology."
  }
}

run "invalid_partition_key_is_rejected" {
  command = plan
  variables {
    databaseContainersList = [{ name = "bad", canonical_name = "BAD_CONTAINER", partitionKey = "" }]
  }
  expect_failures = [terraform_data.services_contract]
}

run "existing_insights_requires_explicit_connection_string" {
  command = plan
  variables {
    deployLogAnalytics                          = false
    existingApplicationInsightsResourceId       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.Insights/components/shared-ai"
    existingApplicationInsightsConnectionString = null
    allowMixedObservabilityWorkspaces           = true
  }
  expect_failures = [terraform_data.observability_contract]
}

run "mismatched_central_workspace_is_rejected" {
  command = plan
  variables {
    existingLogAnalyticsWorkspaceResourceId     = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.OperationalInsights/workspaces/shared-law"
    existingApplicationInsightsResourceId       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-shared/providers/Microsoft.Insights/components/shared-ai"
    existingApplicationInsightsConnectionString = "InstrumentationKey=00000000-0000-0000-0000-000000000005"
  }
  override_data {
    target = data.azapi_resource.existing_app_insights[0]
    values = { output = { properties = { WorkspaceResourceId = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-other/providers/Microsoft.OperationalInsights/workspaces/other-law" } } }
  }
  expect_failures = [terraform_data.observability_contract]
}

run "foundation_inventory_is_actually_published_with_real_connection_paths" {
  command = plan
  # Only mock computed IDs, never Azure payloads/names/schema settings.
  override_resource {
    target          = azapi_resource.foundry_account[0]
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-services/providers/Microsoft.CognitiveServices/accounts/tfservices-foundry"
    }
  }
  variables {
    retrievalBackend        = "ai_search"
    deployGroundingWithBing = true
  }
  assert {
    # Exact current Bicep publisher inventory, excluding its deploy-owned
    # CONTAINER_APPS collection. Anchoring excludes the commented workspace key.
    condition = (
      toset([for setting in azapi_resource.foundation_setting : split("$", setting.name)[0]]) ==
      setunion(
        toset([
          for match in regexall("(?m)^[ \\t]*\\{ name: '([^']+)'", split("// OUTPUTS", split("module appConfigPopulate ", file("${path.module}/../bicep/main.bicep"))[1])[0]) :
          match[0] if match[0] != "CONTAINER_APPS"
        ]),
        toset(["COSMOS_DB_ACCOUNT_RESOURCE_ID", "COSMOS_DB_ENDPOINT"]),
        toset([for deployment in local.services_model_deployments : deployment.canonical_name]),
        toset([for container in var.databaseContainersList : container.canonical_name]),
        toset([for container in var.storageAccountContainersList : container.canonical_name])
      )
    )
    error_message = "Every Bicep foundation key and declared canonical name must have a real ARM child, not merely an output or variable."
  }
  assert {
    condition = (
      azapi_resource.foundation_setting[jsonencode(["SEARCH_CONNECTION_ID", "agent-lz"])].body.properties.value ==
      "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-services/providers/Microsoft.CognitiveServices/accounts/tfservices-foundry/projects/${local.resource_names.aiFoundryProjectName}/connections/${local.services_connection_names.search}" &&
      azapi_resource.foundation_setting[jsonencode(["BING_CONNECTION_ID", "agent-lz"])].body.properties.value ==
      "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-services/providers/Microsoft.CognitiveServices/accounts/tfservices-foundry/projects/${local.resource_names.aiFoundryProjectName}/connections/${local.services_connection_names.bing}" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_API_VERSION", "agent-lz"])].body.properties.value == "" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND", "agent-lz"])].body.properties.value == "" &&
      azapi_resource.foundation_setting[jsonencode(["NETWORK_ISOLATION", "agent-lz"])].body.properties.value == "false" &&
      azapi_resource.foundation_setting[jsonencode(["HISTORY_CONTAINER", "agent-lz"])].body.properties.value == "history"
    )
    error_message = "Connection paths, feature gates and custom canonical names must use resolved foundation values rather than hook defaults."
  }
  assert {
    condition = (
      azapi_resource.foundation_setting[jsonencode(["MODEL_DEPLOYMENTS", "agent-lz"])].body.properties.contentType == "application/json" &&
      length(jsondecode(azapi_resource.foundation_setting[jsonencode(["MODEL_DEPLOYMENTS", "agent-lz"])].body.properties.value)) == length(local.services_model_deployments) &&
      alltrue([
        for deployment in jsondecode(azapi_resource.foundation_setting[jsonencode(["MODEL_DEPLOYMENTS", "agent-lz"])].body.properties.value) :
        can(regex("^https://", deployment.endpoint)) && can(regex(".+", deployment.model)) && can(regex(".+", deployment.modelFormat)) &&
        can(regex(".+", deployment.apiVersion))
      ]) &&
      !contains([for setting in azapi_resource.foundation_setting : setting.name], "CONTAINER_APPS$agent-lz")
    )
    error_message = "Publish input-shaped model metadata as JSON; never adopt the live application collection."
  }
}

run "additional_settings_override_only_matching_label_and_keep_key_vault_references" {
  command = plan
  variables {
    additionalAppConfigurationSettings = [
      { name = "SEARCH_RAG_INDEX_NAME", value = "custom-rag" },
      { name = "CUSTOM_SETTING", value = "default-label" },
      { name = "CUSTOM_SETTING", value = "staging-label", label = "staging" },
      { name = "CUSTOM_SETTING", value = "unlabeled-value", label = "" },
      { name = "UNLABELED_SETTING", value = "no-label", label = "" },
      { name = "CUSTOM_JSON", value = "{\"enabled\":true}", contentType = "application/json" },
      { name = "HOSTED_CUSTOM_EXTENSION", value = "explicit-extension" },
      {
        name        = "CUSTOM_CREDENTIAL"
        value       = "{\"uri\":\"https://tfservices-vault.vault.azure.net/secrets/custom-credential\"}"
        contentType = "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8"
      },
      { name = "CHAT_BACKEND", value = "orchestrator" },
      { name = "HOSTED_AGENT_BASE_URL", value = "https://runtime.example.test" },
      { name = "HOSTED_AGENT_BASE_URL", value = "https://staging.example.test", label = "staging" },
      { name = "PANEL_HISTORY_OWNER_BINDING_VALIDATED", value = "false" }
    ]
  }
  assert {
    condition = (
      azapi_resource.foundation_setting[jsonencode(["SEARCH_RAG_INDEX_NAME", "agent-lz"])].body.properties.value == "custom-rag" &&
      azapi_resource.foundation_setting[jsonencode(["CUSTOM_SETTING", "agent-lz"])].body.properties.value == "default-label" &&
      azapi_resource.foundation_setting[jsonencode(["CUSTOM_SETTING", "staging"])].name == "CUSTOM_SETTING$staging" &&
      azapi_resource.foundation_setting[jsonencode(["CUSTOM_SETTING", "staging"])].body.properties.value == "staging-label" &&
      azapi_resource.foundation_setting[jsonencode(["CUSTOM_SETTING", ""])].body.properties.value == "unlabeled-value" &&
      azapi_resource.foundation_setting[jsonencode(["UNLABELED_SETTING", ""])].name == "UNLABELED_SETTING" &&
      azapi_resource.foundation_setting[jsonencode(["CUSTOM_JSON", "agent-lz"])].body.properties.contentType == "application/json" &&
      jsondecode(azapi_resource.foundation_setting[jsonencode(["CUSTOM_JSON", "agent-lz"])].body.properties.value).enabled
      && azapi_resource.foundation_setting[jsonencode(["HOSTED_CUSTOM_EXTENSION", "agent-lz"])].body.properties.value == "explicit-extension"
    )
    error_message = "Additional settings must be consumed with name+label override precedence, explicit empty labels and content types intact."
  }
  assert {
    condition = (
      azapi_resource.foundation_setting[jsonencode(["CUSTOM_CREDENTIAL", "agent-lz"])].body.properties.contentType == "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8" &&
      jsondecode(azapi_resource.foundation_setting[jsonencode(["CUSTOM_CREDENTIAL", "agent-lz"])].body.properties.value).uri == "https://tfservices-vault.vault.azure.net/secrets/custom-credential" &&
      !contains(keys(azapi_resource.foundation_setting), jsonencode(["CHAT_BACKEND", "agent-lz"])) &&
      !contains(keys(azapi_resource.foundation_setting), jsonencode(["HOSTED_AGENT_BASE_URL", "agent-lz"])) &&
      azapi_resource.foundation_setting[jsonencode(["HOSTED_AGENT_BASE_URL", "staging"])].body.properties.value == "https://staging.example.test" &&
      !contains(keys(azapi_resource.foundation_setting), jsonencode(["PANEL_HISTORY_OWNER_BINDING_VALIDATED", "agent-lz"])) &&
      one([for setting in local.app_config_bootstrap.runtime_settings : setting.value if setting.name == "HOSTED_AGENT_BASE_URL"]) == "https://runtime.example.test" &&
      length(local.app_config_bootstrap.runtime_settings) == 3 &&
      length(local.app_config_bootstrap.foundation_owned_keys) == length(azapi_resource.foundation_setting)
    )
    error_message = "Key Vault references must stay references; runtime inputs must be explicitly handed off, never reset by provision or silently discarded."
  }
}

run "blob_iq_foundation_settings_preserve_typed_inputs" {
  command = plan
  variables {
    retrievalBackend                        = "foundry_iq"
    foundryIqPattern                        = "azureBlob"
    foundryIqKnowledgeSourceKind            = ""
    foundryIqKnowledgeSourceName            = "custom-blob-source"
    foundryIqAiServicesEndpoint             = "https://custom-ai.services.ai.azure.com/"
    foundryIqStorageContainerName           = "custom-documents"
    foundryIqStorageFolderPath              = "restricted/folder"
    foundryIqIsAdlsGen2                     = true
    foundryIqIngestionPermissionOptions     = ["userIds"]
    foundryIqIngestionPermissionOptionsJson = "[\"rbacScope\",\"userIds\"]"
    foundryIqSourceDataFields               = ["id", "content"]
    foundryIqSearchFields                   = ["content"]
  }
  assert {
    condition = (
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND", "agent-lz"])].body.properties.value == "azureBlob" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME", "agent-lz"])].body.properties.value == "custom-blob-source" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_STORAGE_CONTAINER_NAME", "agent-lz"])].body.properties.value == "custom-documents" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_STORAGE_FOLDER_PATH", "agent-lz"])].body.properties.value == "restricted/folder" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_AI_SERVICES_ENDPOINT", "agent-lz"])].body.properties.value == "https://custom-ai.services.ai.azure.com/" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_IS_ADLS_GEN2", "agent-lz"])].body.properties.value == "true" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS", "agent-lz"])].body.properties.contentType == "application/json" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS", "agent-lz"])].body.properties.value == "[\"rbacScope\",\"userIds\"]" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_SOURCE_DATA_FIELDS", "agent-lz"])].body.properties.value == "[\"id\",\"content\"]" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_SEARCH_FIELDS", "agent-lz"])].body.properties.value == "[\"content\"]"
    )
    error_message = "Blob/ADLS intent, JSON-over-list permission precedence and field arrays must be materialized without hook re-derivation."
  }
}

run "isolated_search_index_iq_foundation_uses_arm_proxy" {
  command = plan
  variables {
    networkIsolation                   = true
    deployAiFoundrySubnet              = false
    retrievalBackend                   = "foundry_iq"
    foundryIqPattern                   = "searchIndex"
    foundryIqKnowledgeSourceKind       = ""
    foundryIqSearchIndexName           = "custom-security-index"
    foundryIqSemanticConfigurationName = "custom-semantic"
    foundryIqBaseFilter                = "tenant_id eq 'test'"
    foundryIqFilterAddOnEnabled        = true
    foundryIqSecurityFieldName         = "tenant_id"
  }
  assert {
    condition = (
      length(azapi_resource.foundation_setting) > 0 &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_SEARCH_INDEX_NAME", "agent-lz"])].body.properties.value == "custom-security-index" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_SEMANTIC_CONFIGURATION_NAME", "agent-lz"])].body.properties.value == "custom-semantic" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_BASE_FILTER", "agent-lz"])].body.properties.value == "tenant_id eq 'test'" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_FILTER_ADD_ON_ENABLED", "agent-lz"])].body.properties.value == "true" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_SECURITY_FIELD_NAME", "agent-lz"])].body.properties.value == "tenant_id" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND", "agent-lz"])].body.properties.value == "searchIndex" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_STORAGE_CONTAINER_NAME", "agent-lz"])].body.properties.value == "" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_IS_ADLS_GEN2", "agent-lz"])].body.properties.value == "false" &&
      azapi_resource.foundation_setting[jsonencode(["FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS", "agent-lz"])].body.properties.value == "[]" &&
      azapi_resource.foundation_setting[jsonencode(["NETWORK_ISOLATION", "agent-lz"])].body.properties.value == "true"
    )
    error_message = "Isolated provision must own the same ARM foundation entries and preserve searchIndex gates, not rely on guessed private hook defaults."
  }
}

run "additional_cosmos_endpoint_cannot_compete_with_foundation_owner" {
  command = plan
  variables {
    additionalAppConfigurationSettings = [{
      name = "COSMOS_DB_ENDPOINT", value = "https://unrelated.documents.azure.com:443/"
    }]
  }
  expect_failures = [terraform_data.services_contract]
}
