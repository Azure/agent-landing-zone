# Foundation only. Images are selected by the common pre-provision resolver;
# builds, hosted versions and hosted instance identities belong to deploy.
locals {
  compute_manifest             = jsondecode(file("${path.module}/../../manifest.json"))
  compute_tags                 = local.deployment_context.tags
  compute_application_group_id = local.deployment_context.application_rg_id
  compute_placeholder_image    = "mcr.microsoft.com/dotnet/samples:aspnetapp-9.0"
  compute_jumpbox_name         = substr(coalesce(var.vmName, "testvm${local.resource_token}"), 0, 15)
  compute_jumpbox_user         = coalesce(var.vmUserName, "testvmuser")
  # Only the input-presence bit is declassified; the secret stays sensitive.
  # Match the root contract: null/empty requests persistent generation.
  compute_generate_jumpbox_password = local.effective_flags.jumpbox && nonsensitive(var.vmAdminPassword == null ? true : var.vmAdminPassword == "")
  compute_jumpbox_password          = local.compute_generate_jumpbox_password ? random_password.jumpbox[0].result : var.vmAdminPassword

  # containerAppsList is the resolved infrastructure list, not components[].
  # The shared resolver MUST exclude azure.ai.agent components from this list.
  container_apps = {
    for app in var.containerAppsList : app.service_name => merge(app, {
      name        = coalesce(app.name, "ca-${local.resource_token}-${app.service_name}")
      image       = coalesce(try(app.image, null), local.compute_placeholder_image)
      cpu         = tonumber(coalesce(try(app.cpu, null), "0.5"))
      memory      = coalesce(try(app.memory, null), "1.0Gi")
      target_port = coalesce(try(app.target_port, null), 8080)
    }) if local.effective_flags.container_apps
  }
  # Read only exact destination apps. No resource ID/principal from this
  # read becomes a resource instance key. A failed read is fatal, not [].
  compute_live_apps = {
    for key, app in local.container_apps : key => data.azapi_resource.compute_app[key].output
  }
  compute_live_containers = {
    for key, app in local.container_apps : key => try(one([
      for container in local.compute_live_apps[key].properties.template.containers : container
      if container.name == key
    ]), null)
  }
  compute_app_environment = {
    for key, app in local.container_apps : key => merge(
      { for name, value in(var.appRuntimeConfigurationMode == "containerEnv" ? local.compute_runtime_environment : {}) : name => { value = value, secret_ref = null } },
      # These are deploy-owned values, copied by name rather than list index.
      { for env in try([for entry in local.compute_live_containers[key].env : entry], []) : env.name => { value = try(env.value, null), secret_ref = try(env.secretRef, null) } if !contains(["AZURE_CLIENT_ID", "AZURE_TENANT_ID", "APP_CONFIG_ENDPOINT"], env.name) },
      var.appRuntimeConfigurationMode == "appConfig" ? { APP_CONFIG_ENDPOINT = { value = "https://${local.resource_names.appConfigName}.azconfig.io", secret_ref = null } } : {},
      { AZURE_TENANT_ID = { value = local.deployment_context.tenant_id, secret_ref = null } },
      var.useUAI ? { AZURE_CLIENT_ID = { value = azurerm_user_assigned_identity.compute["app:${key}"].client_id, secret_ref = null } } : {}
    )
  }
  # The managed pull binding is always reconciled, not ignored. Other
  # registries remain deploy-owned, including their secret reference names.
  compute_managed_registry_servers = {
    for key, app in local.container_apps : key => endswith(split("/", app.image)[0], ".${var.acrDnsSuffix}") ? split("/", app.image)[0] : (
      var.deployContainerRegistry && try(anytrue([
        for registry in local.compute_live_apps[key].properties.configuration.registries :
        lower(registry.server) == lower("${local.resource_names.containerRegistryName}.${var.acrDnsSuffix}")
      ]), false) ? "${local.resource_names.containerRegistryName}.${var.acrDnsSuffix}" : ""
    )
  }
  compute_app_registries = {
    for key, app in local.container_apps : key => concat(
      [
        for registry in try([for entry in local.compute_live_apps[key].properties.configuration.registries : entry], []) : {
          server               = registry.server
          identity             = try(registry.identity, null)
          username             = try(registry.username, null)
          password_secret_name = try(registry.passwordSecretRef, null)
        } if lower(registry.server) != lower(local.compute_managed_registry_servers[key])
      ],
      local.compute_managed_registry_servers[key] != "" ? [{
        server               = local.compute_managed_registry_servers[key]
        identity             = var.useUAI ? azurerm_user_assigned_identity.compute["app:${key}"].id : "system"
        username             = null
        password_secret_name = null
      }] : []
    )
  }
  compute_uai_definitions = merge(
    var.useUAI && var.deployContainerEnv ? {
      environment = { name = "id-${local.resource_names.containerEnvName}", resource_group = local.deployment_context.application_rg }
    } : {},
    var.useUAI && var.deployContainerRegistry ? {
      registry = { name = "id-${local.resource_names.containerRegistryName}", resource_group = local.deployment_context.application_rg }
    } : {},
    var.useUAI && local.effective_flags.jumpbox ? {
      jumpbox = { name = "id-${local.compute_jumpbox_name}", resource_group = local.deployment_context.network_rg }
    } : {},
    var.useUAI ? {
      for key, app in local.container_apps : "app:${key}" => {
        name           = "id-ca-${local.resource_token}-${key}"
        resource_group = local.deployment_context.application_rg
      }
    } : {}
  )

  registry_context = {
    id       = var.deployContainerRegistry ? module.container_registry["this"].resource_id : ""
    name     = var.deployContainerRegistry ? module.container_registry["this"].name : ""
    endpoint = var.deployContainerRegistry ? module.container_registry["this"].resource.login_server : ""
  }
  hosted_registry = {
    resource_id = var.deployContainerRegistry ? local.registry_context.id : var.hostedAgentContainerRegistryResourceId
    endpoint    = var.deployContainerRegistry ? local.registry_context.endpoint : var.hostedAgentContainerRegistryEndpoint
    pull_role   = var.deployContainerRegistry || var.hostedAgentContainerRegistryRoleAssignmentMode == "rbac" ? "AcrPull" : "ContainerRegistryRepositoryReader"
  }

  # No secret values belong in this bootstrap. Additional values have the
  # same precedence as the Bicep containerEnv runtime mode.
  compute_runtime_environment = merge({
    SUBSCRIPTION_ID                             = local.deployment_context.subscription_id
    AZURE_RESOURCE_GROUP                        = local.deployment_context.foundry_rg
    AZURE_APP_RESOURCE_GROUP                    = local.deployment_context.application_rg
    AZURE_NETWORK_RESOURCE_GROUP                = local.deployment_context.network_rg
    LOCATION                                    = local.effective_locations.main
    ENVIRONMENT_NAME                            = var.environmentName
    RESOURCE_TOKEN                              = local.resource_token
    RELEASE                                     = local.compute_manifest.tag
    NETWORK_ISOLATION                           = tostring(var.networkIsolation)
    USE_UAI                                     = tostring(var.useUAI)
    ENABLE_AGENTIC_RETRIEVAL                    = tostring(var.enableAgenticRetrieval)
    RETRIEVAL_BACKEND                           = var.retrievalBackend
    KNOWLEDGE_BASE_NAME                         = var.retrievalBackend == "foundry_iq" ? var.knowledgeBaseName : ""
    KNOWLEDGE_BASE_ENDPOINT                     = var.retrievalBackend == "foundry_iq" ? "https://${local.resource_names.searchServiceName}.search.windows.net" : ""
    KNOWLEDGE_BASE_CONNECTION_ID                = var.retrievalBackend == "foundry_iq" ? "/subscriptions/${local.deployment_context.subscription_id}/resourceGroups/${local.deployment_context.foundry_rg}/providers/Microsoft.CognitiveServices/accounts/${local.resource_names.aiFoundryAccountName}/projects/${local.resource_names.aiFoundryProjectName}/connections/${var.knowledgeBaseConnectionName}" : ""
    FOUNDRY_IQ_API_VERSION                      = var.retrievalBackend == "foundry_iq" ? var.foundryIqApiVersion : ""
    FOUNDRY_IQ_KNOWLEDGE_RETRIEVAL_BILLING_PLAN = var.retrievalBackend == "foundry_iq" ? var.foundryIqKnowledgeRetrievalBillingPlan : ""
    FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME            = var.retrievalBackend == "foundry_iq" ? var.foundryIqKnowledgeSourceName : ""
    FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND            = var.retrievalBackend == "foundry_iq" ? coalesce(var.foundryIqKnowledgeSourceKind, var.foundryIqPattern == "searchIndex" ? "searchIndex" : "azureBlob") : ""
    FOUNDRY_IQ_FILTER_ADD_ON_ENABLED            = tostring(var.retrievalBackend == "foundry_iq" && var.foundryIqPattern == "searchIndex" && var.foundryIqFilterAddOnEnabled)
    FOUNDRY_IQ_SECURITY_FIELD_NAME              = var.retrievalBackend == "foundry_iq" && var.foundryIqPattern == "searchIndex" ? var.foundryIqSecurityFieldName : ""
    FOUNDRY_IQ_MAX_OUTPUT_DOCUMENTS             = var.retrievalBackend == "foundry_iq" ? tostring(var.foundryIqMaxOutputDocuments) : ""
    LOG_LEVEL                                   = "INFO"
    ENABLE_CONSOLE_LOGGING                      = "true"
    AI_FOUNDRY_ACCOUNT_NAME                     = local.resource_names.aiFoundryAccountName
    AI_FOUNDRY_PROJECT_NAME                     = local.resource_names.aiFoundryProjectName
    AI_FOUNDRY_ACCOUNT_ENDPOINT                 = "https://${local.resource_names.aiFoundryAccountName}.cognitiveservices.azure.com/"
    AI_FOUNDRY_OPENAI_ENDPOINT                  = "https://${local.resource_names.aiFoundryAccountName}.openai.azure.com/"
    APP_INSIGHTS_NAME                           = local.resource_names.appInsightsName
    CONTAINER_ENV_NAME                          = local.resource_names.containerEnvName
    CONTAINER_REGISTRY_NAME                     = local.resource_names.containerRegistryName
    CONTAINER_REGISTRY_LOGIN_SERVER             = "${local.resource_names.containerRegistryName}.${var.acrDnsSuffix}"
    DATABASE_ACCOUNT_NAME                       = local.resource_names.dbAccountName
    DATABASE_NAME                               = local.resource_names.dbDatabaseName
    SEARCH_SERVICE_NAME                         = local.resource_names.searchServiceName
    STORAGE_ACCOUNT_NAME                        = local.resource_names.storageAccountName
    KEY_VAULT_NAME                              = local.resource_names.keyVaultName
    APP_CONFIG_NAME                             = local.resource_names.appConfigName
    APP_RUNTIME_CONFIGURATION_MODE              = var.appRuntimeConfigurationMode
    }, {
    # Labels disappear in containerEnv mode, so select the active namespace
    # before flattening. Null/missing defaults; explicit "" is an unlabeled
    # namespace, not a fallback. App Configuration labels are case-sensitive.
    for setting in var.additionalAppConfigurationSettings : setting.name => setting.value
    if(setting.label == null ? var.appConfigLabel : setting.label) == var.appConfigLabel
  })

  compute_context = {
    environment_id   = var.deployContainerEnv ? azapi_resource.container_environment["this"].id : ""
    environment_name = var.deployContainerEnv ? local.resource_names.containerEnvName : ""
    environment_principal_id = var.deployContainerEnv ? (
      var.useUAI ? azurerm_user_assigned_identity.compute["environment"].principal_id : azapi_resource.container_environment["this"].identity[0].principal_id
    ) : ""
    apps = {
      for key, app in azurerm_container_app.shell : key => {
        id                   = app.id
        name                 = app.name
        fqdn                 = app.ingress[0].fqdn
        principal_id         = var.useUAI ? azurerm_user_assigned_identity.compute["app:${key}"].principal_id : app.identity[0].principal_id
        identity_resource_id = var.useUAI ? azurerm_user_assigned_identity.compute["app:${key}"].id : ""
      }
    }
    app_identities = {
      for key, app in azurerm_container_app.shell : key => {
        resource_id  = var.useUAI ? azurerm_user_assigned_identity.compute["app:${key}"].id : ""
        principal_id = var.useUAI ? azurerm_user_assigned_identity.compute["app:${key}"].principal_id : app.identity[0].principal_id
        client_id    = var.useUAI ? azurerm_user_assigned_identity.compute["app:${key}"].client_id : ""
      }
    }
    jumpbox_id = local.effective_flags.jumpbox ? azurerm_windows_virtual_machine.jumpbox["this"].id : (var.existingJumpboxResourceId == null ? "" : var.existingJumpboxResourceId)
  }
}

data "azapi_resource" "compute_app" {
  for_each    = local.container_apps
  type        = "Microsoft.App/containerApps@2025-01-01"
  resource_id = "${local.compute_application_group_id}/providers/Microsoft.App/containerApps/${each.value.name}"
  # AzAPI 2.13.0 distinguishes 404 via exists=false/output=null. Authorization,
  # transport and JSON failures are still fatal; never catch them as no app.
  ignore_not_found       = true
  response_export_values = ["id", "tags", "properties.template.containers", "properties.configuration.registries", "properties.configuration.secrets"]
}

resource "terraform_data" "compute_contract" {
  input = keys(local.container_apps)
  lifecycle {
    precondition {
      condition     = !var.deployContainerApps || var.deployContainerEnv
      error_message = "deployContainerApps requires deployContainerEnv."
    }
    precondition {
      condition     = !var.useCAppAPIKey || (var.deployContainerApps && var.deployKeyVault && var.deployAppConfig && var.appRuntimeConfigurationMode == "appConfig")
      error_message = "API-key bootstrap requires Container Apps, Key Vault and App Configuration in appConfig runtime mode."
    }
    precondition {
      condition     = !local.effective_flags.hosted_prerequisites || (var.deployAiFoundry && var.deployAfProject && var.deployAAfAgentSvc && (var.deployContainerRegistry || (can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.ContainerRegistry/registries/[^/]+$", var.hostedAgentContainerRegistryResourceId)) && lower(var.hostedAgentContainerRegistryEndpoint) == lower("${element(reverse(split("/", var.hostedAgentContainerRegistryResourceId)), 0)}.${var.acrDnsSuffix}"))))
      error_message = "Hosted prerequisites require Foundry and a created registry or an exact external registry ID/login-server binding."
    }
    precondition {
      condition     = contains(["rbac", "rbac-abac"], var.hostedAgentContainerRegistryRoleAssignmentMode)
      error_message = "External registry role-assignment mode must be rbac or rbac-abac."
    }
    precondition {
      condition     = var.networkIsolation || (!var.useZoneRedundancy && length(var.allowedIpRanges) == 0) || !var.deployContainerRegistry
      error_message = "The public Basic registry does not support zone redundancy or IP rules; select an isolated Premium registry."
    }
    precondition {
      condition = alltrue([
        for app in values(local.container_apps) :
        contains(concat(["Consumption"], [for profile in var.workloadProfiles : profile.name]), app.profile_name) &&
        app.min_replicas >= 0 && app.max_replicas >= max(1, app.min_replicas) &&
        floor(app.min_replicas) == app.min_replicas && floor(app.max_replicas) == app.max_replicas &&
        app.target_port >= 1 && app.target_port <= 65535 && floor(app.target_port) == app.target_port &&
        app.cpu > 0 && can(regex("^[0-9]+(\\.[0-9]+)?Gi$", app.memory))
      ])
      error_message = "Each app requires a selected workload profile, valid replica range, CPU/memory and TCP target port."
    }
    precondition {
      condition = alltrue(flatten([
        for app in values(local.container_apps) : [
          for role in app.roles : contains(concat(keys(local.app_role_specs), ["CosmosDBBuiltInDataContributor"]), role)
        ]
      ]))
      error_message = "Container Apps accept only the inventoried foundation role vocabulary; custom definitions must resolve approved capability profiles."
    }
    precondition {
      condition     = !local.effective_flags.acr_pool || (contains(["S1", "S2", "S3"], var.acrTaskAgentPoolTier) && var.acrTaskAgentPoolCount >= 0 && floor(var.acrTaskAgentPoolCount) == var.acrTaskAgentPoolCount && length(var.acrTaskAgentPoolName) <= 20)
      error_message = "ACR pool requires S1/S2/S3, a nonnegative integer count and a name of at most 20 characters."
    }
    precondition {
      condition = !(local.effective_flags.jumpbox && var.deploySoftware) || alltrue([
        for value in [var.environmentName, local.deployment_context.foundry_rg, local.effective_locations.main] :
        !can(regex("[\"%!\r\n]", value))
      ])
      error_message = "Jumpbox bootstrap arguments cannot contain command delimiters, expansion markers or line breaks."
    }
  }
}

resource "terraform_data" "compute_egress_ready" {
  input = local.network_context.egress_ready
}

# Exact release qualified against its variables.tf, outputs.tf and main.tf.
# No module-owned role assignments or private endpoints: these are composed
# centrally to avoid inter-domain cycles and to honor PE placement.
module "container_registry" {
  source   = "Azure/avm-res-containerregistry-registry/azurerm"
  version  = "0.5.0"
  for_each = var.deployContainerRegistry ? { this = true } : {}

  name                   = local.resource_names.containerRegistryName
  location               = local.effective_locations.main
  resource_group_name    = local.deployment_context.application_rg
  sku                    = var.networkIsolation ? "Premium" : "Basic"
  admin_enabled          = false
  anonymous_pull_enabled = false
  data_endpoint_enabled  = var.networkIsolation
  export_policy_enabled  = true
  # ARM's omitted networkRuleBypassOptions defaults to AzureServices;
  # AVM defaults to None, so select the existing foundation default explicitly.
  network_rule_bypass_option    = "AzureServices"
  public_network_access_enabled = local.public_access.public_network_access == "Enabled"
  zone_redundancy_enabled       = var.useZoneRedundancy
  network_rule_set = length(var.allowedIpRanges) > 0 ? {
    default_action = "Deny"
    ip_rule        = [for cidr in var.allowedIpRanges : { action = "Allow", ip_range = cidr }]
  } : null
  managed_identities = {
    system_assigned            = !var.useUAI
    user_assigned_resource_ids = var.useUAI ? [azurerm_user_assigned_identity.compute["registry"].id] : []
  }
  enable_telemetry = false
  tags             = local.compute_tags
  depends_on       = [terraform_data.compute_contract]
}

resource "azapi_resource" "acr_agent_pool" {
  for_each  = local.effective_flags.acr_pool ? { this = true } : {}
  type      = "Microsoft.ContainerRegistry/registries/agentPools@2019-06-01-preview"
  name      = var.acrTaskAgentPoolName
  parent_id = local.registry_context.id
  location  = local.effective_locations.main
  tags      = local.compute_tags
  body = {
    properties = {
      count                          = var.acrTaskAgentPoolCount
      tier                           = var.acrTaskAgentPoolTier
      os                             = "Linux"
      virtualNetworkSubnetResourceId = local.subnet_ids.devopsBuildAgents
    }
  }
  depends_on = [terraform_data.compute_egress_ready]
}

# AVM managedenvironment 0.3.0 has daprAIConnectionString, NOT the required
# appInsightsConfiguration.connectionString, and maps no logs to "" rather
# than null. The Bicep-selected 2025-01-01 API also lacks this property.
# 2025-10-02-preview/ManagedEnvironmentProperties in the published ARM schema
# includes appInsightsConfiguration; use that verified API, not schema bypass.
resource "azapi_resource" "container_environment" {
  for_each  = var.deployContainerEnv ? { this = true } : {}
  type      = "Microsoft.App/managedEnvironments@2025-10-02-preview"
  name      = local.resource_names.containerEnvName
  parent_id = local.compute_application_group_id
  location  = local.effective_locations.main
  tags      = local.compute_tags
  identity {
    type         = var.useUAI ? "UserAssigned" : "SystemAssigned"
    identity_ids = var.useUAI ? [azurerm_user_assigned_identity.compute["environment"].id] : []
  }
  body = {
    properties = {
      appLogsConfiguration = { destination = null }
      appInsightsConfiguration = local.effective_observability.connection_string != "" ? {
        connectionString = local.effective_observability.connection_string
      } : null
      zoneRedundant    = var.useZoneRedundancy
      workloadProfiles = var.workloadProfiles
      vnetConfiguration = var.networkIsolation ? {
        infrastructureSubnetId = local.subnet_ids.acaEnvironment
        internal               = true
      } : null
    }
  }
  response_export_values = ["identity", "properties.defaultDomain", "properties.staticIp"]
  depends_on             = [terraform_data.compute_contract]
}

# Direct AzureRM gives property-level lifecycle controls that an ACA AVM
# caller cannot inject. See the ownership evidence below, not ignore(template).
resource "azurerm_container_app" "shell" {
  for_each                     = local.container_apps
  name                         = each.value.name
  resource_group_name          = local.deployment_context.application_rg
  container_app_environment_id = azapi_resource.container_environment["this"].id
  workload_profile_name        = each.value.profile_name
  revision_mode                = "Single"
  tags                         = merge(local.compute_tags, { "azd-service-name" = each.key })
  identity {
    type         = var.useUAI ? "UserAssigned" : "SystemAssigned"
    identity_ids = var.useUAI ? [azurerm_user_assigned_identity.compute["app:${each.key}"].id] : []
  }
  ingress {
    external_enabled           = each.value.external
    target_port                = each.value.target_port
    transport                  = "auto"
    allow_insecure_connections = false
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
  dynamic "dapr" {
    for_each = try(each.value.dapr.enabled, false) == true ? [each.value.dapr] : []
    content {
      app_id       = coalesce(dapr.value.appId, each.key)
      app_port     = coalesce(dapr.value.appPort, each.value.target_port)
      app_protocol = coalesce(dapr.value.appProtocol, "http")
    }
  }
  dynamic "registry" {
    for_each = local.compute_app_registries[each.key]
    content {
      server               = registry.value.server
      identity             = registry.value.identity
      username             = registry.value.username
      password_secret_name = registry.value.password_secret_name
    }
  }
  dynamic "secret" {
    for_each = try([for entry in local.compute_live_apps[each.key].properties.configuration.secrets : entry], [])
    content {
      name                = secret.value.name
      key_vault_secret_id = try(secret.value.keyVaultUrl, null)
      identity            = try(lower(secret.value.identity) == "system" ? "System" : secret.value.identity, null)
    }
  }
  template {
    min_replicas = each.value.min_replicas
    max_replicas = each.value.max_replicas
    container {
      name   = each.key
      image  = each.value.image
      cpu    = each.value.cpu
      memory = each.value.memory
      dynamic "env" {
        for_each = local.compute_app_environment[each.key]
        content {
          name        = env.key
          value       = env.value.value
          secret_name = env.value.secret_ref
        }
      }
    }
  }
  lifecycle {
    # azd 1.37.1 service_target_containerapp.go calls AddRevision; shared
    # deployment may supply env/command/args. Provider 4.x reads the live app
    # and delta-updates configuration, but expands template on update.
    # Keep runtime fields while still reconciling replicas, resources,
    # workload profile, Dapr, TLS, ingress, actual MI and RBAC.
    # Registry authentication, secrets, tenant/client bootstrap, network,
    # identity and RBAC are NOT ignored. Named env and Key Vault references
    # are rehydrated from an exact-ID live read above, like azd's GET/merge.
    ignore_changes = [
      template[0].container[0].image,
      template[0].container[0].command,
      template[0].container[0].args,
      template[0].revision_suffix,
      ingress[0].traffic_weight,
    ]
    precondition {
      condition = local.compute_live_apps[each.key] == null ? true : (
        try(local.compute_live_apps[each.key].tags["azd-env-name"], "") == var.environmentName &&
        try(local.compute_live_apps[each.key].tags["azd-service-name"], "") == each.key &&
        local.compute_live_containers[each.key] != null &&
        try(length(local.compute_live_apps[each.key].properties.template.containers), 0) == 1
      )
      error_message = "Existing Container App must match the exact environment/service binding and single named shell container; no foreign app or sidecar layout may be overwritten."
    }
    precondition {
      condition = alltrue([
        for secret in try([for entry in local.compute_live_apps[each.key].properties.configuration.secrets : entry], []) :
        try(length(secret.keyVaultUrl) > 0, false)
      ])
      error_message = "Reprovision cannot safely recover inline ACA secret values from ARM GET. Use Key Vault references; refusing to clear runtime secrets."
    }
  }
  depends_on = [terraform_data.compute_contract, terraform_data.compute_egress_ready, azurerm_role_assignment.container_pull]
}

# AzureRM 4.81.0 exposes Dapr app_id/app_port/app_protocol, but not
# enableApiLogging. Own only that missing leaf with AzAPI GET/merge/PUT.
# Reapply after shell updates because the provider reconstructs the Dapr object.
resource "azapi_update_resource" "container_app_dapr_logging" {
  for_each    = { for key, app in local.container_apps : key => app if try(app.dapr.enabled, false) == true }
  type        = "Microsoft.App/containerApps@2025-01-01"
  resource_id = azurerm_container_app.shell[each.key].id
  body = {
    properties = {
      configuration = {
        dapr = {
          enableApiLogging = coalesce(try(each.value.dapr.enableApiLogging, null), false)
        }
      }
    }
  }
  lifecycle {
    replace_triggered_by = [azurerm_container_app.shell[each.key]]
  }
}

resource "azurerm_network_interface" "jumpbox" {
  for_each            = local.effective_flags.jumpbox ? { this = true } : {}
  name                = "${local.compute_jumpbox_name}-nic-01"
  location            = local.effective_locations.main
  resource_group_name = local.deployment_context.network_rg
  tags                = local.compute_tags
  ip_configuration {
    name                          = "ipconfig01"
    subnet_id                     = local.subnet_ids.jumpbox
    private_ip_address_allocation = "Dynamic"
  }
}

# Foundation credential, persisted in protected Terraform state. No keepers:
# reprovisioning and unrelated VM/network changes must not rotate it. There is
# no unused generated secret when the jumpbox is absent or input is supplied.
resource "random_password" "jumpbox" {
  count            = local.compute_generate_jumpbox_password ? 1 : 0
  length           = 24
  min_lower        = 1
  min_upper        = 1
  min_numeric      = 1
  min_special      = 1
  override_special = "!#$%&*+-=?@^_"
}

resource "azurerm_windows_virtual_machine" "jumpbox" {
  for_each            = local.effective_flags.jumpbox ? { this = true } : {}
  name                = local.compute_jumpbox_name
  computer_name       = local.compute_jumpbox_name
  location            = local.effective_locations.main
  resource_group_name = local.deployment_context.network_rg
  size                = var.vmSize
  admin_username      = local.compute_jumpbox_user
  # Never publish it in compute_context, extensions, outputs or diagnostics.
  admin_password             = local.compute_jumpbox_password
  network_interface_ids      = [azurerm_network_interface.jumpbox["this"].id]
  encryption_at_host_enabled = false
  tags                       = local.compute_tags
  identity {
    type         = var.useUAI ? "UserAssigned" : "SystemAssigned"
    identity_ids = var.useUAI ? [azurerm_user_assigned_identity.compute["jumpbox"].id] : []
  }
  os_disk {
    caching              = "ReadWrite"
    disk_size_gb         = 250
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = var.vmImagePublisher
    offer     = var.vmImageOffer
    sku       = var.vmImageSku
    version   = var.vmImageVersion
  }
}

resource "azurerm_virtual_machine_extension" "jumpbox_bootstrap" {
  for_each                   = local.effective_flags.jumpbox && var.deploySoftware ? { this = true } : {}
  name                       = "cse"
  virtual_machine_id         = azurerm_windows_virtual_machine.jumpbox["this"].id
  publisher                  = "Microsoft.Compute"
  type                       = "CustomScriptExtension"
  type_handler_version       = "1.10"
  auto_upgrade_minor_version = true
  tags                       = local.compute_tags
  settings = jsonencode({
    fileUris = ["https://raw.githubusercontent.com/Azure/bicep-ptn-aiml-landing-zone/refs/tags/${local.compute_manifest.infra.source.tag}/install.ps1"]
    commandToExecute = join(" ", [
      "powershell.exe -ExecutionPolicy Unrestricted -File install.ps1",
      "-release ${local.compute_manifest.infra.source.tag}",
      "-UseUAI ${var.useUAI}", "-ResourceToken ${local.resource_token}",
      "-AzureTenantId ${local.deployment_context.tenant_id}",
      "-AzureLocation \"${local.effective_locations.main}\"",
      "-AzureSubscriptionId ${local.deployment_context.subscription_id}",
      "-AzureResourceGroupName \"${local.deployment_context.foundry_rg}\"",
      "-AzdEnvName \"${var.environmentName}\"",
      "-ExtraRepoUrls \"${join(",", [for component in local.compute_manifest.components : component.repo])}\"",
      "-ExtraRepoTags \"${join(",", [for component in local.compute_manifest.components : component.tag])}\"",
      "-ExtraRepoNames \"${join(",", [for component in local.compute_manifest.components : component.name])}\"",
    ])
  })
  # This is the existing VM installer, not a Terraform provisioner. It does
  # not build/publish application images or hosted versions.
  depends_on = [azurerm_role_assignment.foundation, azurerm_cosmosdb_sql_role_assignment.application, terraform_data.compute_egress_ready, terraform_data.compute_contract]
}
