# Pin verified against Registry and tagged v0.2.3 source. Null credentials
# support Entra-only. Never inherit AVM's allow-all firewall or HA defaults.
# Independent CanNotDelete protection belongs to shared lifecycle, not state.
locals {
  postgresql_basic       = var.deployPostgreSql && !var.networkIsolation
  aca_vnet_integration   = var.networkIsolation || local.postgresql_basic
  postgresql_tier_prefix = { Burstable = "B", GeneralPurpose = "GP", MemoryOptimized = "MO" }
  postgresql_egress_ip   = local.postgresql_basic ? module.container_apps_postgresql_nat[0].public_ip_resource.aca.ip_address : ""
  postgresql_firewall_rules = local.postgresql_basic ? merge(
    { aca = { name = "ContainerAppsNat", start_ip_address = local.postgresql_egress_ip, end_ip_address = local.postgresql_egress_ip } },
    { for index, ip in var.postgreSqlAllowedIpRanges : "operator-${index}" => {
      name             = "Operator-${index}"
      start_ip_address = cidrhost(strcontains(ip, "/") ? ip : "${ip}/32", 0)
      end_ip_address   = cidrhost(strcontains(ip, "/") ? ip : "${ip}/32", -1)
    } }
  ) : {}
  postgresql_settings = {
    server_version                = var.postgreSqlVersion
    sku_name                      = "${local.postgresql_tier_prefix[var.postgreSqlTier]}_${var.postgreSqlSkuName}"
    storage_mb                    = var.postgreSqlStorageSizeGb * 1024
    backup_retention_days         = var.postgreSqlBackupRetentionDays
    high_availability             = var.postgreSqlHighAvailability == "Disabled" ? null : { mode = var.postgreSqlHighAvailability }
    geo_redundant_backup_enabled  = var.postgreSqlGeoRedundantBackup
    auto_grow_enabled             = var.postgreSqlStorageAutoGrow
    public_network_access_enabled = !var.networkIsolation
    authentication = {
      active_directory_auth_enabled = true
      password_auth_enabled         = false
      tenant_id                     = local.deployment_context.tenant_id
    }
    ad_administrator = {
      admin = {
        object_id      = var.postgreSqlAdministratorObjectId
        principal_name = var.postgreSqlAdministratorPrincipalName
        principal_type = var.postgreSqlAdministratorPrincipalType
        tenant_id      = local.deployment_context.tenant_id
      }
    }
  }
}

resource "terraform_data" "postgresql_contract" {
  count = var.deployPostgreSql ? 1 : 0
  lifecycle {
    precondition {
      condition     = can(regex("^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$", var.postgreSqlAdministratorObjectId)) && var.postgreSqlAdministratorObjectId != "00000000-0000-0000-0000-000000000000" && trimspace(var.postgreSqlAdministratorPrincipalName) != "" && contains(["User", "Group", "ServicePrincipal"], var.postgreSqlAdministratorPrincipalType)
      error_message = "Enabled PostgreSQL requires an explicit administrator object UUID, principal name and User/Group/ServicePrincipal type."
    }
    precondition {
      condition     = (var.postgreSqlTier != "Burstable" || var.postgreSqlHighAvailability == "Disabled") && can(regex({ Burstable = "^Standard_B(1ms|2s|2ms|4ms|8ms|12ms|16ms|20ms)$", GeneralPurpose = "^Standard_D[0-9]+d?s_v[3456]$", MemoryOptimized = "^Standard_E[0-9]+d?s_v[3456]$" }[var.postgreSqlTier], var.postgreSqlSkuName))
      error_message = "PostgreSQL SKU must match its tier, and Burstable cannot use HA; no fallback is performed."
    }
    precondition {
      condition     = !local.postgresql_basic || (var.deployContainerEnv && length(var.workloadProfiles) > 0 && var.deploySubnets && var.deployAcaEnvironmentSubnet && (!var.useExistingVNet || var.deployNsgs) && try(tonumber(split("/", var.acaEnvironmentSubnetPrefix)[1]) <= 27, false))
      error_message = "Basic PostgreSQL requires fresh workload-profiles ACA and a managed delegated ACA subnet of /27 or larger."
    }
    precondition {
      condition     = !local.postgresql_basic || (trimspace(coalesce(var.hubIntegrationEgressNextHopIp, " ")) == "" && trimspace(coalesce(var.hubIntegrationExistingRouteTableResourceId, " ")) == "")
      error_message = "Basic PostgreSQL cannot use forced hub/NVA egress or override a corporate route-table binding; dedicated NAT must own ACA egress."
    }
    precondition {
      condition     = !var.networkIsolation || !var.policyManagedPrivateDns || var.existingPrivateDnsZonePostgreSqlResourceId == ""
      error_message = "PostgreSQL policy-managed DNS and an existing DNS zone ID are competing owners."
    }
    precondition {
      condition = !local.postgresql_basic || !var.useExistingVNet || try(
        anytrue([for cidr in data.azapi_resource.postgresql_basic_vnet[0].output.properties.addressSpace.addressPrefixes :
          sum([for i, octet in split(".", cidrhost(var.acaEnvironmentSubnetPrefix, 0)) : tonumber(octet) * pow(256, 3 - i)]) >= sum([for i, octet in split(".", cidrhost(cidr, 0)) : tonumber(octet) * pow(256, 3 - i)]) &&
          sum([for i, octet in split(".", cidrhost(var.acaEnvironmentSubnetPrefix, -1)) : tonumber(octet) * pow(256, 3 - i)]) <= sum([for i, octet in split(".", cidrhost(cidr, -1)) : tonumber(octet) * pow(256, 3 - i)])
        ]) &&
        alltrue([for subnet in data.azapi_resource.postgresql_basic_vnet[0].output.properties.subnets :
          try(subnet.properties.routeTable.id, "") == "" && try(subnet.properties.networkSecurityGroup.id, "") == "" &&
          contains(["", "/subscriptions/${var.subscriptionId}/resourceGroups/${local.deployment_context.network_rg}/providers/Microsoft.Network/natGateways/${local.network_abbreviations.networking.natGateway}aca-postgresql-${local.resource_token}"], try(subnet.properties.natGateway.id, ""))
          if subnet.name == var.acaEnvironmentSubnetName
        ]) &&
        alltrue(flatten([for subnet in data.azapi_resource.postgresql_basic_vnet[0].output.properties.subnets : [
          for cidr in try(subnet.properties.addressPrefixes, [subnet.properties.addressPrefix]) :
          sum([for i, octet in split(".", cidrhost(var.acaEnvironmentSubnetPrefix, -1)) : tonumber(octet) * pow(256, 3 - i)]) < sum([for i, octet in split(".", cidrhost(cidr, 0)) : tonumber(octet) * pow(256, 3 - i)]) ||
          sum([for i, octet in split(".", cidrhost(cidr, -1)) : tonumber(octet) * pow(256, 3 - i)]) < sum([for i, octet in split(".", cidrhost(var.acaEnvironmentSubnetPrefix, 0)) : tonumber(octet) * pow(256, 3 - i)])
        ] if subnet.name != var.acaEnvironmentSubnetName])),
        false
      )
      error_message = "Basic PostgreSQL ACA subnet must fit the actual BYO VNet without overlaps, existing route-table/NSG removal or reuse of an unrelated NAT."
    }
    precondition {
      condition     = !local.postgresql_basic || try(!data.azapi_resource.postgresql_existing_environment[0].exists || length(data.azapi_resource.postgresql_existing_environment[0].output.properties.workloadProfiles) > 0, false)
      error_message = "Basic PostgreSQL cannot use or recreate a legacy Consumption-only ACA environment; fresh adoption/recovery is additionally lifecycle-guarded."
    }
  }
}

data "azapi_resource" "postgresql_basic_vnet" {
  count                  = local.postgresql_basic && var.useExistingVNet ? 1 : 0
  type                   = "Microsoft.Network/virtualNetworks@2024-07-01"
  resource_id            = var.existingVnetResourceId
  response_export_values = ["properties.addressSpace", "properties.subnets"]
}

data "azapi_resource" "postgresql_existing_environment" {
  count                  = local.postgresql_basic ? 1 : 0
  type                   = "Microsoft.App/managedEnvironments@2025-10-02-preview"
  resource_id            = "${local.deployment_context.application_rg_id}/providers/Microsoft.App/managedEnvironments/${local.resource_names.containerEnvName}"
  ignore_not_found       = true
  response_export_values = ["properties.workloadProfiles"]
}

module "postgresql" {
  source                        = "Azure/avm-res-dbforpostgresql-flexibleserver/azurerm"
  version                       = "0.2.3"
  count                         = var.deployPostgreSql ? 1 : 0
  name                          = local.resource_names.postgreSqlServerName
  resource_group_name           = local.deployment_context.application_rg
  location                      = local.effective_locations.main
  server_version                = local.postgresql_settings.server_version
  sku_name                      = local.postgresql_settings.sku_name
  storage_mb                    = local.postgresql_settings.storage_mb
  backup_retention_days         = local.postgresql_settings.backup_retention_days
  high_availability             = local.postgresql_settings.high_availability
  geo_redundant_backup_enabled  = local.postgresql_settings.geo_redundant_backup_enabled
  auto_grow_enabled             = local.postgresql_settings.auto_grow_enabled
  authentication                = local.postgresql_settings.authentication
  ad_administrator              = local.postgresql_settings.ad_administrator
  public_network_access_enabled = local.postgresql_settings.public_network_access_enabled
  firewall_rules                = local.postgresql_firewall_rules
  databases                     = { application = { name = var.postgreSqlDatabaseName, charset = "UTF8", collation = "en_US.utf8" } }
  # No delegated subnet/private DNS server injection, nested PE, app identity
  # assignment, SQL bootstrap or credentials. Root network owns Private Link.
  lock             = null
  enable_telemetry = false
  tags             = local.deployment_context.tags
  depends_on       = [terraform_data.postgresql_contract, terraform_data.network_contract, module.container_apps_postgresql_nat]
}
