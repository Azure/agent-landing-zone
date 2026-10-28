# All foundation control-plane/data-plane grants are centralized here.
# Actual hosted instance and panel-container grants stay config/deploy-owned.
resource "azurerm_user_assigned_identity" "compute" {
  for_each            = local.compute_uai_definitions
  name                = each.value.name
  resource_group_name = each.value.resource_group
  location            = local.effective_locations.main
  tags                = local.compute_tags
}

resource "azurerm_user_assigned_identity" "service" {
  for_each = {
    for key, definition in {
      search = { enabled = var.deploySearchService, name = local.resource_names.searchServiceName, group = local.deployment_context.foundry_rg }
      cosmos = { enabled = var.deployCosmosDb, name = local.resource_names.dbAccountName, group = local.deployment_context.application_rg }
    } : key => definition if var.useUAI && definition.enabled
  }
  name                = "id-${each.value.name}"
  resource_group_name = each.value.group
  location            = local.effective_locations.main
  tags                = local.compute_tags
}

locals {
  service_identities = {
    for key in ["search", "cosmos"] : key => {
      resource_id  = try(azurerm_user_assigned_identity.service[key].id, "")
      principal_id = try(azurerm_user_assigned_identity.service[key].principal_id, "")
      client_id    = try(azurerm_user_assigned_identity.service[key].client_id, "")
    }
  }
  identity_roles = merge(
    jsondecode(file("${path.module}/../constants/roles.json")),
    # This newer ABAC role is not yet in the incorporated role vocabulary.
    { ContainerRegistryRepositoryReader = { guid = "b93aa761-3e63-49ed-ac28-beffa264f7ac", key = "ContainerRegistryRepositoryReader" } }
  )
  identity_scope_definitions = {
    registry   = { enabled = var.deployContainerRegistry, id = local.registry_context.id }
    key_vault  = { enabled = var.deployKeyVault, id = local.data_context.key_vault.id }
    search     = { enabled = var.deploySearchService, id = local.data_context.search.id }
    storage    = { enabled = var.deployStorageAccount, id = local.data_context.storage.id }
    foundry    = { enabled = var.deployAiFoundry, id = local.foundry_context.account_id }
    speech     = { enabled = var.deploySpeechService, id = local.data_context.speech.id }
    app_config = { enabled = var.deployAppConfig, id = local.data_context.app_config.id }
    project    = { enabled = var.deployAiFoundry && var.deployAfProject && local.effective_flags.hosted_prerequisites && var.grantHostedAgentProjectManager, id = local.foundry_context.project_id }
    root       = { enabled = true, id = "/subscriptions/${local.deployment_context.subscription_id}/resourceGroups/${local.deployment_context.foundry_rg}" }
  }
  executor_role_specs = {
    registry   = ["AcrPush", "AcrPull"]
    key_vault  = ["KeyVaultContributor", "KeyVaultSecretsOfficer"]
    search     = ["SearchServiceContributor", "SearchIndexDataContributor", "SearchIndexDataReader"]
    storage    = ["StorageBlobDataContributor"]
    foundry    = ["CognitiveServicesOpenAIUser", "CognitiveServicesUser"]
    speech     = ["CognitiveServicesContributor", "CognitiveServicesUser"]
    app_config = ["AppConfigurationDataOwner"]
    project    = ["AzureAIProjectManager"]
  }
  jumpbox_principal_id = local.effective_flags.jumpbox ? (
    var.useUAI ? azurerm_user_assigned_identity.compute["jumpbox"].principal_id : azurerm_windows_virtual_machine.jumpbox["this"].identity[0].principal_id
  ) : ""
  jumpbox_role_specs = {
    root       = concat(["Reader"], var.deployAppConfig && var.deployContainerRegistry ? ["ContainerAppsContributor", "ManagedIdentityOperator"] : [])
    registry   = concat(["AcrPush"], var.deployAppConfig ? ["ContainerRegistryRepositoryWriter", "ContainerRegistryContributorDataAccessConfigurationAdministrator", "ContainerRegistryTasksContributor"] : [])
    key_vault  = ["KeyVaultContributor", "KeyVaultSecretsOfficer", "KeyVaultCertificatesOfficer"]
    search     = ["SearchServiceContributor", "SearchIndexDataContributor"]
    storage    = ["StorageBlobDataContributor"]
    foundry    = ["CognitiveServicesContributor", "CognitiveServicesOpenAIUser"]
    speech     = ["CognitiveServicesContributor", "CognitiveServicesUser"]
    app_config = ["AppConfigurationDataOwner"]
  }
  # Scope selection is a closed vocabulary, NOT arbitrary role/scope input.
  # OBO/document trimming remains a runtime obligation. MI data access does
  # not grant a user access to every document.
  app_role_specs = {
    KeyVaultSecretsUser         = ["key_vault"]
    AppConfigurationDataReader  = var.appRuntimeConfigurationMode == "appConfig" ? ["app_config"] : []
    CognitiveServicesUser       = ["foundry", "speech"]
    CognitiveServicesOpenAIUser = ["foundry"]
    AcrPull                     = ["registry"]
    SearchIndexDataReader       = ["search"]
    SearchIndexDataContributor  = ["search"]
    StorageBlobDataContributor  = ["storage"]
    StorageBlobDataReader       = ["storage"]
    StorageBlobDelegator        = ["storage"]
  }
  executor_grants = flatten([
    for scope_key, roles in local.executor_role_specs : [
      for role in roles : {
        key            = "executor:${scope_key}:${role}"
        scope          = local.identity_scope_definitions[scope_key].id
        role           = role
        principal_id   = var.principalId
        principal_type = var.principalType
      } if local.identity_scope_definitions[scope_key].enabled
    ]
  ])
  jumpbox_grants = flatten([
    for scope_key, roles in local.jumpbox_role_specs : [
      for role in roles : {
        key            = "jumpbox:${scope_key}:${role}"
        scope          = local.identity_scope_definitions[scope_key].id
        role           = role
        principal_id   = local.jumpbox_principal_id
        principal_type = "ServicePrincipal"
      } if local.effective_flags.jumpbox && local.identity_scope_definitions[scope_key].enabled
    ]
  ])
  # Group NAMES, not resource IDs/principals, determine stable instance keys.
  jumpbox_reader_destinations = toset([
    for name in [local.deployment_context.application_rg, local.deployment_context.network_rg] :
    lower(name) if lower(name) != lower(local.deployment_context.foundry_rg)
  ])
  jumpbox_destination_grants = [
    for name in local.jumpbox_reader_destinations : {
      key            = "jumpbox:destination:${name}:Reader"
      scope          = "/subscriptions/${local.deployment_context.subscription_id}/resourceGroups/${name}"
      role           = "Reader"
      principal_id   = local.jumpbox_principal_id
      principal_type = "ServicePrincipal"
    } if local.effective_flags.jumpbox
  ]
  app_grants = flatten([
    for key, app in local.container_apps : [
      for role in distinct(app.roles) : [
        for scope_key in lookup(local.app_role_specs, role, []) : {
          key            = "app:${key}:${scope_key}:${role}"
          scope          = local.identity_scope_definitions[scope_key].id
          role           = role
          principal_id   = local.compute_context.app_identities[key].principal_id
          principal_type = "ServicePrincipal"
        } if local.identity_scope_definitions[scope_key].enabled && !(var.useUAI && role == "AcrPull")
      ]
    ]
  ])
  cross_service_specs = {
    search_foundry = {
      enabled      = var.deploySearchService && var.deployAiFoundry
      scope        = local.foundry_context.account_id
      principal_id = local.data_context.search.principal_id
      role         = "CognitiveServicesUser"
    }
    search_storage = {
      enabled      = var.deploySearchService && var.deployStorageAccount
      scope        = local.data_context.storage.id
      principal_id = local.data_context.search.principal_id
      role         = "StorageBlobDataReader"
    }
    project_search = {
      enabled      = var.deployAiFoundry && var.deployAfProject && var.deploySearchService
      scope        = local.data_context.search.id
      principal_id = local.foundry_context.project_principal_id
      role         = "SearchIndexDataReader"
    }
    project_storage = {
      enabled      = var.deployAiFoundry && var.deployAfProject && var.deployStorageAccount
      scope        = local.data_context.storage.id
      principal_id = local.foundry_context.project_principal_id
      role         = "StorageBlobDataReader"
    }
    project_registry = {
      enabled      = var.deployAiFoundry && var.deployAfProject && local.effective_flags.hosted_prerequisites
      scope        = local.hosted_registry.resource_id
      principal_id = local.foundry_context.project_principal_id
      role         = local.hosted_registry.pull_role
    }
    associated_search_contributor = {
      enabled      = var.deployAiFoundry && var.deployAfProject && var.deployAAfAgentSvc
      scope        = local.foundry_dependencies.search_id
      principal_id = local.foundry_context.project_principal_id
      role         = "SearchIndexDataContributor"
    }
    associated_search_service = {
      enabled      = var.deployAiFoundry && var.deployAfProject && var.deployAAfAgentSvc
      scope        = local.foundry_dependencies.search_id
      principal_id = local.foundry_context.project_principal_id
      role         = "SearchServiceContributor"
    }
    associated_cosmos = {
      enabled      = var.deployAiFoundry && var.deployAfProject && var.deployAAfAgentSvc
      scope        = local.foundry_dependencies.cosmos_id
      principal_id = local.foundry_context.project_principal_id
      role         = "CosmosDBOperator"
    }
    associated_storage = {
      enabled      = var.deployAiFoundry && var.deployAfProject && var.deployAAfAgentSvc
      scope        = local.foundry_dependencies.storage_id
      principal_id = local.foundry_context.project_principal_id
      role         = "StorageBlobDataContributor"
    }
  }
  cross_service_grants = [
    for key, grant in local.cross_service_specs : merge(grant, {
      key            = "cross:${key}"
      principal_type = "ServicePrincipal"
    }) if grant.enabled
  ]
  # Known configuration keys, never computed principal IDs, select instances.
  foundation_rbac_assignments = {
    for grant in concat(local.executor_grants, local.jumpbox_grants, local.jumpbox_destination_grants, local.app_grants, local.cross_service_grants) :
    grant.key => {
      scope              = grant.scope
      principal_id       = grant.principal_id
      principal_type     = grant.principal_type
      role_definition_id = "/subscriptions/${split("/", grant.scope)[2]}/providers/Microsoft.Authorization/roleDefinitions/${local.identity_roles[grant.role].guid}"
      condition          = null
      condition_version  = null
    }
  }

  cosmos_application_grants = merge(
    var.deployCosmosDb ? { executor = var.principalId } : {},
    var.deployCosmosDb && local.effective_flags.jumpbox ? { jumpbox = local.jumpbox_principal_id } : {},
    {
      for key, app in local.container_apps : "app:${key}" => local.compute_context.app_identities[key].principal_id
      if var.deployCosmosDb && contains(app.roles, "CosmosDBBuiltInDataContributor")
    }
  )
  # Services can use this explicit pre-capability-host completion handle.
  # Post-host conditional/data-plane grants below MUST NOT be included.
  foundry_authorization_ready = [
    for key in ["cross:associated_search_contributor", "cross:associated_search_service", "cross:associated_cosmos", "cross:associated_storage"] :
    azurerm_role_assignment.foundation[key].id if var.deployAiFoundry && var.deployAfProject && var.deployAAfAgentSvc
  ]
  # Store-scoped executor grant completion only, not a role intent or an
  # application/publication dependency. Keep this outside data_context so the
  # store/role -> settings ordering never makes the store depend on its grants.
  # Creation completion is not a guarantee of Azure RBAC cache propagation.
  app_config_authorization_ready = var.deployAppConfig ? [
    azurerm_role_assignment.app_config_executor["this"].id
  ] : []
}

resource "azurerm_role_assignment" "foundation" {
  for_each = {
    for key, grant in local.foundation_rbac_assignments : key => grant
    if key != "executor:app_config:AppConfigurationDataOwner"
  }
  name                             = uuidv5("url", lower("${each.value.scope}|${each.value.principal_id}|${each.value.role_definition_id}"))
  scope                            = each.value.scope
  principal_id                     = each.value.principal_id
  principal_type                   = each.value.principal_type
  role_definition_id               = each.value.role_definition_id
  condition                        = each.value.condition
  condition_version                = each.value.condition_version
  skip_service_principal_aad_check = each.value.principal_type == "ServicePrincipal"
}

# A member lookup on the shared foundation collection still inherits that
# block's application-principal dependencies. Isolate this existing grant so
# ARM settings publication waits on the executor, never on application grants.
# Preserve its deterministic ARM assignment name and published RBAC context.
moved {
  from = azurerm_role_assignment.foundation["executor:app_config:AppConfigurationDataOwner"]
  to   = azurerm_role_assignment.app_config_executor["this"]
}

resource "azurerm_role_assignment" "app_config_executor" {
  for_each = var.deployAppConfig ? {
    this = {
      scope              = local.data_context.app_config.id
      role_definition_id = "/subscriptions/${split("/", local.data_context.app_config.id)[2]}/providers/Microsoft.Authorization/roleDefinitions/${local.identity_roles.AppConfigurationDataOwner.guid}"
    }
  } : {}
  name                             = uuidv5("url", lower("${each.value.scope}|${var.principalId}|${each.value.role_definition_id}"))
  scope                            = each.value.scope
  principal_id                     = var.principalId
  principal_type                   = var.principalType
  role_definition_id               = each.value.role_definition_id
  skip_service_principal_aad_check = var.principalType == "ServicePrincipal"
}

# A UAI exists before its app. Grant requested managed-registry pull permission
# before creating a shell with an explicit private image, without depending on
# SAMI/app creation or the complete cross-service authorization collection.
resource "azurerm_role_assignment" "container_pull" {
  for_each = {
    for key, app in local.container_apps : key => app
    if var.useUAI && var.deployContainerRegistry && contains(app.roles, "AcrPull")
  }
  name                             = uuidv5("url", lower("${local.registry_context.id}|${azurerm_user_assigned_identity.compute["app:${each.key}"].principal_id}|/subscriptions/${local.deployment_context.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.identity_roles.AcrPull.guid}"))
  scope                            = local.registry_context.id
  principal_id                     = azurerm_user_assigned_identity.compute["app:${each.key}"].principal_id
  principal_type                   = "ServicePrincipal"
  role_definition_id               = "/subscriptions/${local.deployment_context.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.identity_roles.AcrPull.guid}"
  skip_service_principal_aad_check = true
}

resource "azurerm_cosmosdb_sql_role_assignment" "application" {
  for_each            = local.cosmos_application_grants
  name                = uuidv5("url", lower("${local.data_context.cosmos.id}|${each.value}|${local.identity_roles.CosmosDBBuiltInDataContributor.guid}"))
  resource_group_name = local.deployment_context.application_rg
  account_name        = local.data_context.cosmos.name
  principal_id        = each.value
  role_definition_id  = "${local.data_context.cosmos.id}/sqlRoleDefinitions/${local.identity_roles.CosmosDBBuiltInDataContributor.guid}"
  scope               = local.data_context.cosmos.id
}

# Capability host completion is provided by services, not a guessed block
# name. It keeps native enterprise_memory grants after service creation.
resource "terraform_data" "foundry_capability_ready" {
  for_each = var.deployAiFoundry && var.deployAfProject && var.deployAAfAgentSvc ? { this = true } : {}
  input    = local.foundry_capability_host_id
}

resource "azurerm_role_assignment" "foundry_workspace_storage" {
  for_each           = var.deployAiFoundry && var.deployAfProject && var.deployAAfAgentSvc ? { this = true } : {}
  name               = uuidv5("url", lower("${local.foundry_dependencies.storage_id}|${local.foundry_context.project_principal_id}|${local.identity_roles.StorageBlobDataOwner.guid}"))
  scope              = local.foundry_dependencies.storage_id
  principal_id       = local.foundry_context.project_principal_id
  principal_type     = "ServicePrincipal"
  role_definition_id = "/subscriptions/${split("/", local.foundry_dependencies.storage_id)[2]}/providers/Microsoft.Authorization/roleDefinitions/${local.identity_roles.StorageBlobDataOwner.guid}"
  condition_version  = "2.0"
  # Exact predicate from storageAccountDataPlane.bicep. Preserve the negated
  # action conjunction and the workspace-prefix AND agent-suffix constraint.
  condition                        = <<-CONDITION
    (
      (
        !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/read'})
        AND  !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/filter/action'})
        AND  !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/write'})
      )
      OR
      (@Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringStartsWithIgnoreCase '${local.foundry_context.project_workspace_id}'
      AND @Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringLikeIgnoreCase '*-azureml-agent')
    )
  CONDITION
  skip_service_principal_aad_check = true
  depends_on                       = [terraform_data.foundry_capability_ready]
}

resource "azapi_resource" "foundry_memory" {
  for_each  = var.deployAiFoundry && var.deployAfProject && var.deployAAfAgentSvc ? { this = true } : {}
  type      = "Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15"
  parent_id = local.foundry_dependencies.cosmos_id
  name      = uuidv5("url", lower("${local.foundry_dependencies.cosmos_id}|${local.foundry_context.project_principal_id}|enterprise_memory"))
  body = {
    properties = {
      principalId      = local.foundry_context.project_principal_id
      roleDefinitionId = "${local.foundry_dependencies.cosmos_id}/sqlRoleDefinitions/${local.identity_roles.CosmosDBBuiltInDataContributor.guid}"
      scope            = "${local.foundry_dependencies.cosmos_id}/dbs/enterprise_memory"
    }
  }
  # AzAPI honors the full BYO parent ID, including a foreign subscription;
  # AzureRM's native SQL assignment would use the default provider subscription.
  # Never create the service-owned enterprise_memory database/containers.
  depends_on = [terraform_data.foundry_capability_ready]
}

# Separate from the application-grant collection: the gateway depends on this
# completed grant, but must never depend on its own FQDN/backend output.
resource "azurerm_role_assignment" "ingress_certificate" {
  for_each                         = local.effective_flags.public_ingress && var.deployKeyVault ? { this = true } : {}
  name                             = uuidv5("url", lower("${local.data_context.key_vault.id}|${local.network_ingress_identity.principal_id}|${local.identity_roles.KeyVaultSecretsUser.guid}"))
  scope                            = local.data_context.key_vault.id
  principal_id                     = local.network_ingress_identity.principal_id
  principal_type                   = "ServicePrincipal"
  role_definition_id               = "/subscriptions/${local.deployment_context.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.identity_roles.KeyVaultSecretsUser.guid}"
  skip_service_principal_aad_check = true
}

locals {
  network_ingress_role_assignment_ids = [for assignment in azurerm_role_assignment.ingress_certificate : assignment.id]
  # Expose the complete ARM authorization context without making the initial
  # grant collection depend on post-capability-host or ingress completion.
  # Instance keys remain configuration-known; Cosmos SQL stays separate.
  rbac_assignments = merge(
    local.foundation_rbac_assignments,
    {
      for key, assignment in azurerm_role_assignment.container_pull : "app:${key}:registry:AcrPull" => {
        scope              = assignment.scope
        principal_id       = assignment.principal_id
        principal_type     = assignment.principal_type
        role_definition_id = assignment.role_definition_id
        condition          = null
        condition_version  = null
      }
    },
    {
      for key, assignment in azurerm_role_assignment.foundry_workspace_storage : "post:foundry_workspace_storage" => {
        scope              = assignment.scope
        principal_id       = assignment.principal_id
        principal_type     = assignment.principal_type
        role_definition_id = assignment.role_definition_id
        condition          = assignment.condition
        condition_version  = assignment.condition_version
      }
    },
    {
      for key, assignment in azurerm_role_assignment.ingress_certificate : "ingress:certificate" => {
        scope              = assignment.scope
        principal_id       = assignment.principal_id
        principal_type     = assignment.principal_type
        role_definition_id = assignment.role_definition_id
        condition          = null
        condition_version  = null
      }
    }
  )
}
