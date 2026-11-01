locals {
  services_existing_law = var.existingLogAnalyticsWorkspaceResourceId == null ? "" : trimspace(var.existingLogAnalyticsWorkspaceResourceId)
  services_existing_ai  = var.existingApplicationInsightsResourceId == null ? "" : trimspace(var.existingApplicationInsightsResourceId)
  services_create_law   = var.deployLogAnalytics && local.services_existing_law == ""
  services_create_ai    = var.deployAppInsights && local.services_existing_ai == "" && (local.services_create_law || local.services_existing_law != "")
  services_ampls        = var.networkIsolation && local.services_create_law && local.services_create_ai && var.enablePrivateLogAnalytics
}

module "log_analytics" {
  count   = local.services_create_law ? 1 : 0
  source  = "Azure/avm-res-operationalinsights-workspace/azurerm"
  version = "0.4.2"

  name                                                  = local.resource_names.logAnalyticsWorkspaceName
  location                                              = local.effective_locations.main
  resource_group_name                                   = local.deployment_context.application_rg
  log_analytics_workspace_sku                           = "PerGB2018"
  log_analytics_workspace_retention_in_days             = 30
  log_analytics_workspace_identity                      = { type = "SystemAssigned" }
  log_analytics_workspace_local_authentication_disabled = false
  log_analytics_workspace_internet_ingestion_enabled    = true
  log_analytics_workspace_internet_query_enabled        = true
  tags                                                  = local.services_tags
  role_assignments                                      = {}
  private_endpoints                                     = {}
  enable_telemetry                                      = false
  depends_on                                            = [terraform_data.services_resource_groups]
}

# Read-only BYO verification; never adopt or mutate a central workspace, component
# or its private-link topology. Cross-subscription reads use their actual ARM IDs.
data "azapi_resource" "existing_app_insights" {
  count                  = local.services_existing_ai != "" ? 1 : 0
  type                   = "Microsoft.Insights/components@2020-02-02"
  resource_id            = local.services_existing_ai
  response_export_values = ["properties.WorkspaceResourceId", "properties.ConnectionString"]
}

resource "terraform_data" "observability_contract" {
  input = {
    law_id          = local.services_existing_law
    app_insights_id = local.services_existing_ai
  }
  lifecycle {
    precondition {
      condition = local.services_existing_ai == "" || var.allowMixedObservabilityWorkspaces || (
        lower(try(data.azapi_resource.existing_app_insights[0].output.properties.WorkspaceResourceId, "")) ==
        lower(local.services_existing_law != "" ? local.services_existing_law : (local.services_create_law ? module.log_analytics[0].resource_id : ""))
      )
      error_message = "Existing Application Insights must use the effective LAW unless allowMixedObservabilityWorkspaces explicitly permits a mixed binding."
    }
    precondition {
      condition     = local.services_existing_ai == "" || try(length(trimspace(var.existingApplicationInsightsConnectionString)) > 0, false)
      error_message = "Existing Application Insights requires its explicit connection string."
    }
  }
}

resource "azapi_resource" "app_insights" {
  count     = local.services_create_ai ? 1 : 0
  type      = "Microsoft.Insights/components@2020-02-02"
  parent_id = local.services_app_rg_id
  name      = local.resource_names.appInsightsName
  location  = lower(local.effective_locations.main) == "westcentralus" ? "eastus" : local.effective_locations.main
  tags      = local.services_tags
  body = {
    kind = "web"
    properties = {
      Application_Type                = "web"
      WorkspaceResourceId             = local.services_existing_law != "" ? local.services_existing_law : module.log_analytics[0].resource_id
      DisableIpMasking                = false
      publicNetworkAccessForIngestion = "Enabled"
      publicNetworkAccessForQuery     = "Enabled"
    }
  }
  response_export_values = ["properties.ConnectionString", "properties.InstrumentationKey"]
}

resource "azapi_resource" "monitor_scope" {
  count     = local.services_ampls ? 1 : 0
  type      = "Microsoft.Insights/privateLinkScopes@2021-07-01-preview"
  parent_id = local.services_app_rg_id
  name      = "${local.services_abbreviations.networking.privateLinkScope}${local.resource_token}"
  location  = "global"
  body = {
    properties = {
      accessModeSettings = { queryAccessMode = "Open", ingestionAccessMode = "Open" }
    }
  }
}

resource "azapi_resource" "monitor_scoped_resource" {
  for_each = local.services_ampls ? {
    law          = { name = local.resource_names.logAnalyticsWorkspaceName, id = module.log_analytics[0].resource_id }
    app_insights = { name = local.resource_names.appInsightsName, id = azapi_resource.app_insights[0].id }
  } : {}
  type      = "Microsoft.Insights/privateLinkScopes/scopedResources@2021-07-01-preview"
  parent_id = azapi_resource.monitor_scope[0].id
  name      = each.value.name
  body      = { properties = { linkedResourceId = each.value.id } }
}

resource "terraform_data" "monitor_scope_ready" {
  count = local.services_ampls ? 1 : 0
  input = {
    id     = azapi_resource.monitor_scope[0].id
    scopes = [for resource in azapi_resource.monitor_scoped_resource : resource.id]
  }
}

locals {
  effective_observability = {
    create_law          = local.services_create_law
    create_app_insights = local.services_create_ai
    law_id              = local.services_existing_law != "" ? local.services_existing_law : (local.services_create_law ? module.log_analytics[0].resource_id : "")
    app_insights_id     = local.services_existing_ai != "" ? local.services_existing_ai : (local.services_create_ai ? azapi_resource.app_insights[0].id : "")
    connection_string   = local.services_existing_ai != "" ? (var.existingApplicationInsightsConnectionString == null ? "" : var.existingApplicationInsightsConnectionString) : (local.services_create_ai ? azapi_resource.app_insights[0].output.properties.ConnectionString : "")
    instrumentation_key = local.services_existing_ai != "" ? try(split("=", split(";", var.existingApplicationInsightsConnectionString)[0])[1], "") : (local.services_create_ai ? azapi_resource.app_insights[0].output.properties.InstrumentationKey : "")
    ampls               = local.services_ampls
    ampls_id            = local.services_ampls ? terraform_data.monitor_scope_ready[0].output.id : ""
    # Resource IDs of scope memberships are an explicit PE readiness dependency.
    ampls_scoped_resource_ids = [for resource in azapi_resource.monitor_scoped_resource : resource.id]
  }
}
