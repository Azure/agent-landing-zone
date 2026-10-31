# Native Container Apps backend. No agent/workflow application publication,
# Functions, Redis, Service Bus or application checkpoint database.
resource "azapi_resource" "durable_scheduler" {
  count     = var.deployDurableTaskScheduler ? 1 : 0
  type      = "Microsoft.DurableTask/schedulers@2026-02-01"
  parent_id = local.deployment_context.application_rg_id
  name      = coalesce(var.durableTaskSchedulerName, "dts-${local.resource_token}")
  location  = local.effective_locations.main
  tags      = local.deployment_context.tags
  body = {
    properties = {
      sku                 = { name = var.durableTaskSchedulerSku, capacity = var.durableTaskSchedulerCapacity }
      ipAllowlist         = []
      publicNetworkAccess = var.networkIsolation ? "Disabled" : "Enabled"
    }
  }
  response_export_values = ["properties.endpoint"]
}

resource "azapi_resource" "durable_hub" {
  count     = var.deployDurableTaskScheduler ? 1 : 0
  type      = "Microsoft.DurableTask/schedulers/taskHubs@2026-02-01"
  parent_id = azapi_resource.durable_scheduler[0].id
  name      = var.durableTaskHubName
  body      = { properties = {} }
}

locals {
  durable_backend = var.deployDurableTaskScheduler ? {
    resourceId        = azapi_resource.durable_scheduler[0].id
    endpoint          = azapi_resource.durable_scheduler[0].output.properties.endpoint
    taskHubName       = azapi_resource.durable_hub[0].name
    taskHubResourceId = azapi_resource.durable_hub[0].id
  } : null
}

resource "azurerm_role_assignment" "durable_data" {
  for_each = {
    for service, app in local.container_apps : service => app
    if var.deployDurableTaskScheduler && contains(["frontend", "orchestrator"], service)
  }
  scope                            = azapi_resource.durable_hub[0].id
  role_definition_id               = "/subscriptions/${local.deployment_context.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.identity_roles.DurableTaskDataContributor.guid}"
  principal_id                     = local.compute_context.app_identities[each.key].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
