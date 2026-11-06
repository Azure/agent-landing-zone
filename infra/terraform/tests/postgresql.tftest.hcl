# Offline mock plans only. Live SNAT, DNS, SQL auth and lock behavior are not
# established by these tests; the independent lock is lifecycle-owned.
mock_provider "azurerm" {
  mock_data "azurerm_resource_group" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-postgresql-contract"
      location = "eastus2"
    }
  }
  mock_data "azurerm_client_config" {
    defaults = {
      subscription_id = "00000000-0000-0000-0000-000000000002"
      tenant_id       = "00000000-0000-0000-0000-000000000001"
      object_id       = "00000000-0000-0000-0000-000000000003"
    }
  }
  mock_resource "azurerm_public_ip" {
    override_during = plan
    defaults = {
      id         = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-postgresql-contract/providers/Microsoft.Network/publicIPAddresses/pip-aca"
      ip_address = "203.0.113.10"
    }
  }
  mock_resource "azurerm_nat_gateway" {
    override_during = plan
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-postgresql-contract/providers/Microsoft.Network/natGateways/ng-aca"
    }
  }
  mock_resource "azurerm_postgresql_flexible_server" {
    defaults = {
      id   = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-postgresql-contract/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-contract"
      fqdn = "psql-contract.postgres.database.azure.com"
    }
  }
}
mock_provider "azapi" {
  mock_data "azapi_resource" { defaults = { exists = false, output = null } }
}
mock_provider "random" {}
mock_provider "modtm" {}
mock_provider "time" {}

variables {
  subscriptionId                       = "00000000-0000-0000-0000-000000000002"
  tenantId                             = "00000000-0000-0000-0000-000000000001"
  environmentName                      = "postgresql-contract"
  resourceGroupName                    = "rg-postgresql-contract"
  principalId                          = "00000000-0000-0000-0000-000000000003"
  location                             = "eastus2"
  deployJumpbox                        = false
  deployBastion                        = false
  deployNatGateway                     = false
  postgreSqlAdministratorObjectId      = "00000000-0000-0000-0000-000000000004"
  postgreSqlAdministratorPrincipalName = "postgresql-admin"
  postgreSqlAdministratorPrincipalType = "Group"
}

run "disabled_default_graph" {
  command = plan
  assert {
    condition     = length(module.postgresql) == 0 && length(module.container_apps_postgresql_nat) == 0 && length(local.managed_subnets) == 0 && length(module.network_vnet) == 0
    error_message = "Default-off PostgreSQL must add no server/NAT/VNet/subnet."
  }
  assert {
    condition     = output.POSTGRESQL_HOST == "" && output.POSTGRESQL_PORT == "" && output.POSTGRESQL_SERVER_RESOURCE_ID == "" && output.POSTGRESQL_DATABASE_NAME == "" && output.CONTAINER_APPS_POSTGRESQL_EGRESS_IP == ""
    error_message = "Disabled outputs must be empty strings."
  }
  assert {
    condition     = azapi_resource.container_environment["this"].body.properties.vnetConfiguration == null
    error_message = "Default Basic ACA must stay unintegrated."
  }
}

run "basic_explicit_defaults" {
  command = plan
  variables {
    deployPostgreSql          = true
    postgreSqlAllowedIpRanges = ["198.51.100.7", "192.0.2.17/24"]
  }
  assert {
    condition     = length(module.postgresql) == 1 && length(module.container_apps_postgresql_nat) == 1 && length(module.network_nat) == 0 && toset(keys(local.managed_subnets)) == toset(["acaEnvironment"])
    error_message = "Basic must create only ACA subnet and a dedicated NAT, never jumpbox NAT."
  }
  assert {
    condition     = local.postgresql_settings.sku_name == "B_Standard_B1ms" && local.postgresql_settings.storage_mb == 32768 && local.postgresql_settings.server_version == "16" && local.postgresql_settings.backup_retention_days == 7 && local.postgresql_settings.high_availability == null && !local.postgresql_settings.geo_redundant_backup_enabled && !local.postgresql_settings.auto_grow_enabled
    error_message = "Effective economical defaults must be explicit and equivalent."
  }
  assert {
    condition     = local.postgresql_settings.authentication.active_directory_auth_enabled && !local.postgresql_settings.authentication.password_auth_enabled && local.postgresql_settings.authentication.tenant_id == var.tenantId && local.postgresql_settings.ad_administrator.admin.object_id == var.postgreSqlAdministratorObjectId
    error_message = "Entra only with the explicitly configured administrator and tenant."
  }
  assert {
    condition     = !azapi_resource.container_environment["this"].body.properties.vnetConfiguration.internal && local.subnet_definitions.acaEnvironment.delegation == "Microsoft.App/environments" && local.subnet_definitions.acaEnvironment.route_table_id == ""
    error_message = "Basic custom VNet must retain external ingress without forced UDR."
  }
  assert {
    condition     = local.postgresql_firewall_rules.aca.start_ip_address == "203.0.113.10" && local.postgresql_firewall_rules.aca.end_ip_address == "203.0.113.10" && local.postgresql_firewall_rules["operator-1"].start_ip_address == "192.0.2.0" && local.postgresql_firewall_rules["operator-1"].end_ip_address == "192.0.2.255" && length(local.postgresql_firewall_rules) == 3
    error_message = "Firewall must use exact NAT IP plus normalized inclusive operator ranges."
  }
  assert {
    condition     = local.postgresql_settings.public_network_access_enabled && length(local.private_endpoints) == 0 && output.POSTGRESQL_PORT == "5432" && output.POSTGRESQL_DATABASE_NAME == "agentlz"
    error_message = "Basic public endpoint and enabled output contract."
  }
}

run "isolated_managed_dns" {
  command = plan
  variables {
    deployPostgreSql = true
    networkIsolation = true
  }
  assert {
    condition     = !local.postgresql_settings.public_network_access_enabled && length(local.postgresql_firewall_rules) == 0 && length(module.container_apps_postgresql_nat) == 0 && output.CONTAINER_APPS_POSTGRESQL_EGRESS_IP == ""
    error_message = "Isolated PostgreSQL must have no public access/firewall/dedicated ACA NAT."
  }
  assert {
    condition     = local.private_endpoints.postgresql.subnet_purpose == "applicationPe" && local.private_endpoints.postgresql.group_ids == ["postgresqlServer"] && local.network_managed_dns.PostgreSql.name == "privatelink.postgres.database.azure.com"
    error_message = "Private Link must use app PE subnet and correct private DNS."
  }
}

run "isolated_existing_dns" {
  command = plan
  variables {
    deployPostgreSql                           = true
    networkIsolation                           = true
    existingPrivateDnsZonePostgreSqlResourceId = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-shared-dns/providers/Microsoft.Network/privateDnsZones/privatelink.postgres.database.azure.com"
  }
  assert {
    condition     = !contains(keys(local.network_managed_dns), "PostgreSql") && local.private_dns_zone_ids.PostgreSql == var.existingPrivateDnsZonePostgreSqlResourceId
    error_message = "Existing PostgreSQL DNS must not be owned or recreated."
  }
}

run "isolated_policy_dns" {
  command = plan
  variables {
    deployPostgreSql        = true
    networkIsolation        = true
    policyManagedPrivateDns = true
  }
  assert {
    condition     = length(local.network_managed_dns) == 0 && length(local.private_endpoints.postgresql.dns_zone_ids) == 0 && !contains(keys(azapi_resource.network_endpoint_dns), "postgresql")
    error_message = "Policy DNS must not create competing zones/groups."
  }
}

run "invalid_admin" {
  command = plan
  variables {
    deployPostgreSql                = true
    postgreSqlAdministratorObjectId = ""
  }
  expect_failures = [terraform_data.postgresql_contract]
}
run "invalid_burstable_ha" {
  command = plan
  variables {
    deployPostgreSql           = true
    postgreSqlHighAvailability = "SameZone"
  }
  expect_failures = [terraform_data.postgresql_contract]
}
run "invalid_all_addresses" {
  command = plan
  variables {
    deployPostgreSql          = true
    postgreSqlAllowedIpRanges = ["0.0.0.0/0"]
  }
  expect_failures = [var.postgreSqlAllowedIpRanges]
}
run "invalid_azure_services" {
  command = plan
  variables {
    deployPostgreSql          = true
    postgreSqlAllowedIpRanges = ["0.0.0.0"]
  }
  expect_failures = [var.postgreSqlAllowedIpRanges]
}
run "invalid_legacy_consumption" {
  command = plan
  variables {
    deployPostgreSql  = true
    workloadProfiles  = []
    containerAppsList = []
  }
  expect_failures = [terraform_data.postgresql_contract]
}

run "general_purpose_sizing" {
  command = plan
  variables {
    deployPostgreSql              = true
    postgreSqlTier                = "GeneralPurpose"
    postgreSqlSkuName             = "Standard_D2s_v3"
    postgreSqlStorageSizeGb       = 128
    postgreSqlBackupRetentionDays = 14
    postgreSqlHighAvailability    = "SameZone"
    postgreSqlGeoRedundantBackup  = true
    postgreSqlStorageAutoGrow     = true
  }
  assert {
    condition     = local.postgresql_settings.sku_name == "GP_Standard_D2s_v3" && local.postgresql_settings.storage_mb == 131072 && local.postgresql_settings.high_availability.mode == "SameZone" && local.postgresql_settings.geo_redundant_backup_enabled && local.postgresql_settings.auto_grow_enabled && local.postgresql_settings.backup_retention_days == 14
    error_message = "Configurable sizing must map without fallback."
  }
}

run "invalid_storage" {
  command = plan
  variables {
    postgreSqlStorageSizeGb = 33
  }
  expect_failures = [var.postgreSqlStorageSizeGb]
}

run "invalid_dns_competing_owners" {
  command = plan
  variables {
    deployPostgreSql                           = true
    networkIsolation                           = true
    policyManagedPrivateDns                    = true
    existingPrivateDnsZonePostgreSqlResourceId = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/dns/providers/Microsoft.Network/privateDnsZones/privatelink.postgres.database.azure.com"
  }
  expect_failures = [terraform_data.postgresql_contract]
}

run "disabled_isolated_graph" {
  command = plan
  variables {
    networkIsolation = true
  }
  assert {
    condition     = length(module.postgresql) == 0 && length(module.container_apps_postgresql_nat) == 0 && !contains(keys(local.private_endpoints), "postgresql") && !contains(keys(local.network_managed_dns), "PostgreSql") && output.POSTGRESQL_SERVER_RESOURCE_ID == ""
    error_message = "Disabled isolated deployments must keep existing network but add no PostgreSQL artifacts."
  }
}
run "invalid_forced_route" {
  command = plan
  variables {
    deployPostgreSql              = true
    hubIntegrationEgressNextHopIp = "10.0.0.4"
  }
  expect_failures = [terraform_data.postgresql_contract]
}

run "basic_byo_fresh_subnet" {
  command = plan
  variables {
    deployPostgreSql       = true
    useExistingVNet        = true
    existingVnetResourceId = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/workload"
  }
  override_data {
    target = data.azapi_resource.postgresql_basic_vnet[0]
    values = {
      output = { properties = { addressSpace = { addressPrefixes = ["192.168.0.0/21"] }, subnets = [] } }
    }
  }
  assert {
    condition     = length(module.network_vnet) == 0 && toset(keys(local.managed_subnets)) == toset(["acaEnvironment"]) && local.network_vnet_id == var.existingVnetResourceId
    error_message = "Basic BYO must create only the fresh ACA subnet, not replace a VNet."
  }
}

run "basic_byo_rejects_corporate_routes" {
  command = plan
  variables {
    deployPostgreSql       = true
    useExistingVNet        = true
    existingVnetResourceId = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/workload"
  }
  override_data {
    target = data.azapi_resource.postgresql_basic_vnet[0]
    values = {
      output = {
        properties = {
          addressSpace = { addressPrefixes = ["192.168.0.0/21"] }
          subnets = [{
            name       = "aca-environment-subnet"
            properties = { addressPrefix = "192.168.1.0/24", routeTable = { id = "/corporate-routes" } }
          }]
        }
      }
    }
  }
  expect_failures = [terraform_data.postgresql_contract]
}

run "basic_byo_rejects_shared_nat" {
  command = plan
  variables {
    deployPostgreSql       = true
    useExistingVNet        = true
    existingVnetResourceId = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/workload"
  }
  override_data {
    target = data.azapi_resource.postgresql_basic_vnet[0]
    values = {
      output = {
        properties = {
          addressSpace = { addressPrefixes = ["192.168.0.0/21"] }
          subnets = [{
            name       = "aca-environment-subnet"
            properties = { addressPrefix = "192.168.1.0/24", natGateway = { id = "/jumpbox-nat" } }
          }]
        }
      }
    }
  }
  expect_failures = [terraform_data.postgresql_contract]
}

run "basic_byo_rejects_overlap" {
  command = plan
  variables {
    deployPostgreSql       = true
    useExistingVNet        = true
    existingVnetResourceId = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/workload"
  }
  override_data {
    target = data.azapi_resource.postgresql_basic_vnet[0]
    values = {
      output = {
        properties = {
          addressSpace = { addressPrefixes = ["192.168.0.0/21"] }
          subnets = [{
            name       = "corporate-subnet"
            properties = { addressPrefix = "192.168.1.0/24" }
          }]
        }
      }
    }
  }
  expect_failures = [terraform_data.postgresql_contract]
}

run "existing_legacy_environment_rejected" {
  command = plan
  variables {
    deployPostgreSql = true
  }
  override_data {
    target = data.azapi_resource.postgresql_existing_environment[0]
    values = { exists = true, output = { properties = { workloadProfiles = [] } } }
  }
  expect_failures = [terraform_data.postgresql_contract]
}
