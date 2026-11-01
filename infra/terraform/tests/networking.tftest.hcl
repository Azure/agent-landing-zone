# Contract plans only: mocks never authenticate to or write Azure. Positive
# assertions use complete mock plans so Terraform evaluates the asserted locals.
# Only negative guard cases target resources; pruning an asserted local crashes
# Terraform 1.13's test evaluator instead of yielding a useful assertion result.
# Complete assembled-root plans and Azure access tests remain release gates.
# Custom mock-provider source addresses come from root required_providers.
# Terraform 1.13 skips that resolution when module loading fails; initialize
# modules before diagnosing hashicorp/azapi or hashicorp/modtm cascade errors.
mock_provider "azurerm" {
  # ARM parent IDs are validated even in targeted/mock plans. Cover both
  # explicit RG ownership paths instead of letting mocks invent opaque IDs.
  mock_resource "azurerm_resource_group" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-network-contract"
      location = "eastus2"
    }
  }
  mock_data "azurerm_resource_group" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-network-contract"
      location = "eastus2"
    }
  }
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id       = "00000000-0000-0000-0000-000000000001"
      subscription_id = "00000000-0000-0000-0000-000000000002"
      object_id       = "00000000-0000-0000-0000-000000000003"
    }
  }
}
mock_provider "azapi" {
  mock_data "azapi_resource" {
    defaults = {
      # Fresh environment: exact Container App lookups return 404, not a
      # fabricated foreign app. The reused-subnet case overrides its own read.
      exists = false
      output = null
    }
  }
}
mock_provider "modtm" {}
mock_provider "random" {}
mock_provider "time" {}

# Only the management contract reads the BYO VNet itself. Other BYO reads
# retain the missing-resource default unless a scenario explicitly supplies it.
override_data {
  target = data.azapi_resource.network_existing_management_vnet[0]
  values = {
    output = {
      properties = {
        addressSpace = { addressPrefixes = ["192.168.0.0/21"] }
        subnets      = []
      }
    }
  }
}

variables {
  subscriptionId    = "00000000-0000-0000-0000-000000000002"
  tenantId          = "00000000-0000-0000-0000-000000000001"
  environmentName   = "network-contract"
  resourceGroupName = "rg-network-contract"
  location          = "eastus2"
  principalId       = "00000000-0000-0000-0000-000000000003"
  deployJumpbox     = false
  deployBastion     = false
  deployNatGateway  = false
}

run "public_default_has_no_network_resources" {
  command = plan
  assert {
    condition     = length(local.managed_subnets) == 0 && length(local.private_endpoints) == 0 && length(local.network_managed_dns) == 0
    error_message = "Public mode must not provision the isolated network, endpoints or DNS zones."
  }
  assert {
    condition     = local.public_access.public_network_access == "Enabled" && !local.public_access.apply_ip_rules
    error_message = "Public access defaults must match Bicep."
  }
  assert {
    condition     = alltrue([for id in values(local.subnet_ids) : id == ""])
    error_message = "Public deployment must not leak '/subnets/...' pseudo IDs."
  }
  assert {
    condition     = length(local.network_foundry_private_endpoints) == 0 && local.network_ingress_context.nsg_resource_id == ""
    error_message = "Public mode must not export a managed Foundry endpoint or ingress NSG."
  }
  assert {
    condition     = length(module.network_firewall) == 0 && length(module.network_firewall_policy) == 0 && length(module.network_public_ip) == 0
    error_message = "Public mode must not create either firewall IP, firewall or policy."
  }
}

run "isolated_basic_has_required_subnets_and_dedicated_application_pe" {
  command = plan
  variables {
    networkIsolation = true
    deployCosmosDb   = true
  }
  assert {
    condition = (
      alltrue([for purpose in ["agent", "pe", "bastion", "appGateway", "jumpbox", "acaEnvironment", "devopsBuildAgents", "applicationPe", "powerPlatform", "aiGateway"] : contains(keys(local.managed_subnets), purpose)]) &&
      contains(keys(local.managed_subnets), "firewall") && contains(keys(local.managed_subnets), "firewallManagement") &&
      !contains(keys(local.managed_subnets), "gateway")
    )
    error_message = "Basic requires both firewall subnets, keeps workload defaults and does not reserve GatewaySubnet."
  }
  assert {
    condition = (
      module.network_firewall[0].resource.sku_tier == "Basic" &&
      module.network_firewall_policy[0].resource.sku == "Basic" &&
      length(module.network_firewall_policy[0].resource.dns) == 0 &&
      length(module.network_firewall[0].resource.management_ip_configuration) == 1 &&
      module.network_firewall[0].resource.management_ip_configuration[0].name == "managementIpconfig" &&
      toset(keys(module.network_public_ip)) == toset(["firewall", "firewallManagement"])
    )
    error_message = "Default Basic must use matching policy, no DNS block, both IPs and the pinned AVM management interface."
  }
  assert {
    condition = (
      local.subnet_definitions.firewallManagement.address_prefix == "192.168.3.192/26" &&
      local.subnet_definitions.firewallManagement.route_table_id == "" &&
      local.subnet_definitions.firewallManagement.network_security_group_id == "" &&
      local.subnet_definitions.firewallManagement.nat_gateway_id == "" &&
      local.subnet_definitions.firewallManagement.delegation == "" &&
      length(local.subnet_definitions.firewallManagement.service_endpoints) == 0
    )
    error_message = "Basic management networking must not inherit workload NSGs, UDRs, NAT, delegations or endpoints."
  }
  assert {
    condition     = local.subnet_definitions.agent.delegation == "Microsoft.App/environments" && local.subnet_definitions.acaEnvironment.delegation == "Microsoft.App/environments"
    error_message = "The canonical case-sensitive delegation must be retained."
  }
  assert {
    condition = alltrue([
      for key in ["cosmos", "keyVault", "appConfig", "containerApps", "acr", "ampls"] :
      local.private_endpoints[key].subnet_purpose == "applicationPe"
    ])
    error_message = "Application endpoints must never fall back to the Foundry PE subnet."
  }
  assert {
    condition     = local.private_endpoints.foundry.subnet_purpose == "pe" && length(local.private_endpoints.foundry.group_ids) == 1 && local.private_endpoints.foundry.group_ids[0] == "account"
    error_message = "Foundry endpoint group and placement must match Bicep."
  }
  assert {
    condition     = local.public_access.public_network_access == "Disabled"
    error_message = "Isolated mode without an IP allow-list must disable public service access."
  }
  assert {
    condition     = !contains(local.network_endpoint_specs.ampls.zones, "AppInsights") && local.network_dns_specs.AppInsights.enabled
    error_message = "Creating the AppInsights zone is not the same as attaching it to the AMPLS endpoint."
  }
  assert {
    condition     = toset(keys(local.network_foundry_private_endpoints)) == toset(["foundry", "foundrySearch", "foundryStorage", "foundryCosmos", "foundryKeyVault"])
    error_message = "Foundry connectivity must have its own known-key endpoint resource collection."
  }
  assert {
    condition     = length(setintersection(toset(keys(local.network_foundry_private_endpoints)), toset(keys(local.network_application_private_endpoints)))) == 0
    error_message = "Foundry readiness must not wait on application/compute endpoint producers."
  }
}

run "creation_is_not_consumer_association" {
  command = plan
  variables {
    networkIsolation      = true
    deployAiFoundrySubnet = false
  }
  assert {
    condition     = contains(keys(local.managed_subnets), "agent") && !local.subnet_definitions.agent.required
    error_message = "Disabling Foundry association must not disable explicit agent subnet ownership."
  }
  assert {
    condition     = local.subnet_definitions.gateway.route_table_id == "" && local.subnet_definitions.gateway.network_security_group_id == "" && local.subnet_definitions.gateway.delegation == ""
    error_message = "GatewaySubnet cannot have an NSG, forced-tunnel UDR or delegation."
  }
}

run "isolated_ip_rules_reopen_only_the_supported_service_surface" {
  command = plan
  variables {
    networkIsolation = true
    allowedIpRanges  = ["192.0.2.0/24"]
  }
  assert {
    condition     = local.public_access.public_network_access == "Enabled" && local.public_access.apply_ip_rules
    error_message = "Isolated plus an allow-list must retain the Bicep hybrid access behavior."
  }
  assert {
    condition     = local.public_access.storage_ip_rules[0].action == "Allow" && local.public_access.cosmos_ip_rules[0] == "192.0.2.0/24"
    error_message = "Service-specific IP rule shapes must be preserved."
  }
}

run "byo_cross_subscription_placement_and_dns_precedence" {
  command = plan
  variables {
    networkIsolation                     = true
    useExistingVNet                      = true
    existingVnetResourceId               = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared"
    sideBySideDeploy                     = false
    existingPrivateDnsZoneBlobResourceId = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
  }
  assert {
    condition     = local.network_context.pe_subscription == "00000000-0000-0000-0000-000000000004" && local.network_context.pe_rg == "rg-shared" && local.network_context.dns_rg == "rg-shared"
    error_message = "Implicit endpoint and DNS placement must follow the actual BYO VNet subscription/RG."
  }
  assert {
    condition     = !contains(keys(local.network_managed_dns), "Blob") && local.private_dns_zone_ids.Blob == var.existingPrivateDnsZoneBlobResourceId
    error_message = "Per-zone BYO must suppress both creation and linking, not consumer endpoints."
  }
  assert {
    condition     = contains(keys(local.private_endpoints), "storage")
    error_message = "A BYO DNS zone must not suppress a required private endpoint."
  }
}

run "explicit_pe_rg_stays_in_workload_subscription" {
  command = plan
  variables {
    networkIsolation                 = true
    useExistingVNet                  = true
    existingVnetResourceId           = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared"
    sideBySideDeploy                 = false
    privateEndpointResourceGroupName = "rg-private-endpoints"
  }
  assert {
    condition     = local.network_context.pe_subscription == var.subscriptionId && local.network_context.pe_rg == "rg-private-endpoints" && local.network_context.dns_subscription == "00000000-0000-0000-0000-000000000004"
    error_message = "An explicit PE RG override follows the workload subscription, independently of DNS."
  }
}

run "policy_managed_dns_does_not_create_zone_groups" {
  command = plan
  variables {
    networkIsolation        = true
    policyManagedPrivateDns = true
  }
  assert {
    condition     = length(local.network_managed_dns) == 0 && alltrue([for endpoint in values(local.private_endpoints) : length(endpoint.dns_zone_ids) == 0])
    error_message = "Policy-managed DNS must suppress local zone/link/zone-group ownership while retaining endpoints."
  }
}

run "external_route_table_is_not_owned" {
  command = plan
  variables {
    networkIsolation                           = true
    deployAzureFirewall                        = false
    hubIntegrationExistingRouteTableResourceId = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-hub/providers/Microsoft.Network/routeTables/shared"
  }
  assert {
    condition     = !local.network_route_table && local.network_context.route_table_id == var.hubIntegrationExistingRouteTableResourceId
    error_message = "An existing route table must be passed through without local ownership or route writes."
  }
  assert {
    condition = (
      !contains(keys(local.managed_subnets), "firewall") &&
      !contains(keys(local.managed_subnets), "firewallManagement") &&
      !contains(keys(local.managed_subnets), "gateway") &&
      length(module.network_firewall) == 0 && length(module.network_firewall_policy) == 0 &&
      length(module.network_public_ip) == 0
    )
    error_message = "External egress must not create unused local firewall or gateway networking."
  }
}

run "byo_hub_components_are_not_replaced" {
  command = plan
  variables {
    networkIsolation             = true
    deployJumpbox                = null
    deployBastion                = null
    deployNatGateway             = null
    existingJumpboxResourceId    = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-hub/providers/Microsoft.Compute/virtualMachines/shared"
    existingBastionResourceId    = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-hub/providers/Microsoft.Network/bastionHosts/shared"
    existingNatGatewayResourceId = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-hub/providers/Microsoft.Network/natGateways/shared"
  }
  assert {
    condition     = !local.effective_flags.jumpbox && !local.effective_flags.bastion && !local.effective_flags.nat
    error_message = "Nullable hub flags must honor BYO IDs instead of creating unrelated replacements."
  }
  assert {
    condition     = local.subnet_definitions.jumpbox.nat_gateway_id == var.existingNatGatewayResourceId
    error_message = "The jumpbox subnet must retain the explicitly supplied NAT gateway."
  }
}

run "vnet_name_override_is_retained" {
  command = plan
  variables {
    networkIsolation = true
    vnetName         = "operator-vnet"
  }
  assert {
    condition     = local.network_vnet_name == "operator-vnet"
    error_message = "Explicit VNet names must override both CAF and legacy generated names."
  }
}

run "ingress_skeleton_is_deny_by_default" {
  command = plan
  variables {
    networkIsolation = true
    publicIngress    = { enabled = true }
  }
  assert {
    condition     = !local.network_ingress_live && length(local.network_nsg_rules.appGateway) == 3 && local.network_nsg_rules.appGateway[2].properties.access == "Deny"
    error_message = "Skeleton ingress must remain inaccessible from the Internet without the TLS/list allow configuration."
  }
}

run "reject_missing_byo_vnet" {
  command = plan
  variables {
    networkIsolation       = true
    useExistingVNet        = true
    existingVnetResourceId = ""
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reused_agent_subnet_is_verified_not_mutated" {
  command = plan
  variables {
    networkIsolation       = true
    useExistingVNet        = true
    existingVnetResourceId = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared"
    deployAgentSubnet      = false
  }
  override_data {
    target = data.azapi_resource.network_existing_subnet["agent"]
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared/subnets/agent-subnet"
      output = {
        properties = {
          delegations      = [{ properties = { serviceName = "Microsoft.App/environments" } }]
          serviceEndpoints = [{ service = "Microsoft.CognitiveServices" }]
        }
      }
    }
  }
  assert {
    condition     = !contains(keys(local.managed_subnets), "agent") && endswith(terraform_data.network_existing_subnet_contract["agent"].input, "/subnets/agent-subnet")
    error_message = "A required unowned subnet must be verified and reused, not replaced."
  }
}

run "reject_incompatible_byo_subnet_properties" {
  command = plan
  variables {
    networkIsolation       = true
    useExistingVNet        = true
    existingVnetResourceId = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared"
    deployAgentSubnet      = false
  }
  plan_options {
    target = [terraform_data.network_existing_subnet_contract]
  }
  expect_failures = [terraform_data.network_existing_subnet_contract["agent"]]
}

run "reject_required_unmanaged_subnet_in_new_vnet" {
  command = plan
  variables {
    networkIsolation          = true
    deployApplicationPeSubnet = false
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_case_insensitive_duplicate_names" {
  command = plan
  variables {
    networkIsolation        = true
    applicationPeSubnetName = "PE-SUBNET"
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_overlapping_cidrs" {
  command = plan
  variables {
    networkIsolation          = true
    applicationPeSubnetPrefix = "192.168.2.0/26"
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_unaligned_cidr" {
  command = plan
  variables {
    networkIsolation          = true
    applicationPeSubnetPrefix = "192.168.3.129/26"
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_subnet_outside_new_vnet" {
  command = plan
  variables {
    networkIsolation      = true
    aiGatewaySubnetPrefix = "10.0.0.0/24"
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_ai_gateway_without_nsg" {
  command = plan
  variables {
    networkIsolation = true
    deployNsgs       = false
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_isolation_without_egress" {
  command = plan
  variables {
    networkIsolation    = true
    deployAzureFirewall = false
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_competing_egress_owners" {
  command = plan
  variables {
    networkIsolation              = true
    hubIntegrationEgressNextHopIp = "10.0.0.4"
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "standard_keeps_dns_proxy_without_management_dependencies" {
  command = plan
  variables {
    networkIsolation                    = true
    azureFirewallSku                    = "Standard"
    enableFirewallDnsProxy              = true
    deployAzureFirewallManagementSubnet = true
    useZoneRedundancy                   = true
  }
  assert {
    condition = (
      module.network_firewall[0].resource.sku_tier == "Standard" &&
      module.network_firewall_policy[0].resource.sku == "Standard" &&
      module.network_firewall_policy[0].resource.dns[0].proxy_enabled &&
      length(module.network_firewall[0].resource.management_ip_configuration) == 0 &&
      !contains(keys(local.managed_subnets), "firewallManagement") &&
      toset(keys(module.network_public_ip)) == toset(["firewall"])
    )
    error_message = "Standard preserves selectable DNS proxy and never creates Basic management dependencies, even with an explicit management flag."
  }
}

run "integrated_external_hub_with_gateway_has_no_local_reservations" {
  command = plan
  variables {
    networkIsolation                       = true
    deploymentMode                         = "ailz-integrated"
    deployAzureFirewall                    = false
    hubIntegrationEgressNextHopIp          = "10.0.0.4"
    hubIntegrationPeeringUseRemoteGateways = true
    deployAzureFirewallManagementSubnet    = true
  }
  assert {
    condition = (
      !contains(keys(local.managed_subnets), "firewall") &&
      !contains(keys(local.managed_subnets), "firewallManagement") &&
      !contains(keys(local.managed_subnets), "gateway") &&
      length(module.network_firewall) == 0 && length(module.network_firewall_policy) == 0 &&
      length(module.network_public_ip) == 0
    )
    error_message = "A shared hub gateway does not require any local firewall or gateway reservation."
  }
}

run "external_hub_without_gateway_allows_explicit_reservations_only" {
  command = plan
  variables {
    networkIsolation                    = true
    deploymentMode                      = "ailz-integrated"
    deployAzureFirewall                 = false
    hubIntegrationEgressNextHopIp       = "10.0.0.4"
    deployAzureFirewallSubnet           = true
    deployGatewaySubnet                 = true
    deployAzureFirewallManagementSubnet = true
  }
  assert {
    condition = (
      contains(keys(local.managed_subnets), "firewall") && contains(keys(local.managed_subnets), "gateway") &&
      !contains(keys(local.managed_subnets), "firewallManagement") &&
      length(module.network_public_ip) == 0 && length(module.network_firewall) == 0
    )
    error_message = "Explicit data and gateway reservations must not create either service or management networking."
  }
}

run "standalone_gateway_reservation_is_opt_in" {
  command = plan
  variables {
    networkIsolation    = true
    deployGatewaySubnet = true
  }
  assert {
    condition     = contains(keys(local.managed_subnets), "gateway") && contains(keys(local.managed_subnets), "firewallManagement")
    error_message = "Standalone Basic must honor an explicit GatewaySubnet reservation."
  }
}

run "public_ignores_isolated_reservations" {
  command = plan
  variables {
    deployAzureFirewallSubnet           = true
    deployAzureFirewallManagementSubnet = true
    deployGatewaySubnet                 = true
  }
  assert {
    condition     = length(local.managed_subnets) == 0 && length(module.network_public_ip) == 0 && length(module.network_firewall) == 0
    error_message = "Isolation gates subnet and firewall/IP creation even when reservation flags are true."
  }
}

run "basic_management_wiring_keeps_data_private_next_hop" {
  command = plan
  variables {
    networkIsolation = true
  }
  # Override producers only: the firewall and policy still use their real
  # pinned AVM plans, so the management object shape is actually evaluated.
  override_module {
    target = module.network_subnet["firewall"]
    outputs = {
      resource_id = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-network-contract/providers/Microsoft.Network/virtualNetworks/vnet/subnets/AzureFirewallSubnet"
    }
  }
  override_module {
    target = module.network_subnet["firewallManagement"]
    outputs = {
      resource_id = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-network-contract/providers/Microsoft.Network/virtualNetworks/vnet/subnets/AzureFirewallManagementSubnet"
    }
  }
  override_module {
    target = module.network_public_ip["firewall"]
    outputs = {
      resource_id = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-network-contract/providers/Microsoft.Network/publicIPAddresses/data"
    }
  }
  override_module {
    target = module.network_public_ip["firewallManagement"]
    outputs = {
      resource_id = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-network-contract/providers/Microsoft.Network/publicIPAddresses/management"
    }
  }
  override_resource {
    target          = module.network_firewall[0].azurerm_firewall.this
    override_during = plan
    values = {
      id               = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-network-contract/providers/Microsoft.Network/azureFirewalls/basic"
      ip_configuration = { private_ip_address = "192.168.2.132" }
    }
  }
  assert {
    condition = (
      module.network_firewall[0].resource.management_ip_configuration[0].subnet_id == local.subnet_ids.firewallManagement &&
      module.network_firewall[0].resource.management_ip_configuration[0].public_ip_address_id == module.network_public_ip["firewallManagement"].resource_id &&
      module.network_firewall[0].resource.ip_configuration[0].subnet_id == local.subnet_ids.firewall &&
      module.network_firewall[0].resource.ip_configuration[0].public_ip_address_id == module.network_public_ip["firewall"].resource_id &&
      azapi_resource.network_default_route[0].body.properties.nextHopIpAddress == module.network_firewall[0].resource.ip_configuration[0].private_ip_address
    )
    error_message = "The management NIC must use its own subnet/IP; workload UDRs must still use the data-plane private IP."
  }
}

run "basic_reuses_required_byo_firewall_subnets_without_owning_them" {
  command = plan
  variables {
    networkIsolation                    = true
    useExistingVNet                     = true
    existingVnetResourceId              = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared"
    deployAzureFirewallSubnet           = false
    deployAzureFirewallManagementSubnet = false
  }
  override_data {
    target = data.azapi_resource.network_existing_subnet["firewall"]
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared/subnets/AzureFirewallSubnet"
      output = {
        properties = {
          addressPrefix = "192.168.2.128/26"
          delegations   = []
        }
      }
    }
  }
  override_data {
    target = data.azapi_resource.network_existing_subnet["firewallManagement"]
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared/subnets/AzureFirewallManagementSubnet"
      output = {
        properties = {
          addressPrefixes = ["192.168.3.192/26"]
          delegations     = []
        }
      }
    }
  }
  assert {
    condition = (
      !contains(keys(local.managed_subnets), "firewall") && !contains(keys(local.managed_subnets), "firewallManagement") &&
      contains(keys(data.azapi_resource.network_existing_subnet), "firewall") &&
      contains(keys(data.azapi_resource.network_existing_subnet), "firewallManagement")
    )
    error_message = "Explicit false must look up compatible required BYO subnets without acquiring create/delete ownership."
  }
}

run "reject_basic_dns_proxy" {
  command = plan
  variables {
    networkIsolation       = true
    enableFirewallDnsProxy = true
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_integrated_local_basic" {
  command = plan
  variables {
    networkIsolation = true
    deploymentMode   = "ailz-integrated"
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_unknown_firewall_sku" {
  command = plan
  variables {
    azureFirewallSku = "Premium"
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [var.azureFirewallSku]
}

run "reject_management_reserved_name" {
  command = plan
  variables {
    azureFirewallManagementSubnetName = "azurefirewallmanagementsubnet"
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [var.azureFirewallManagementSubnetName]
}

run "reject_management_prefix_too_small" {
  command = plan
  variables {
    azureFirewallManagementSubnetPrefix = "192.168.3.192/27"
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [var.azureFirewallManagementSubnetPrefix]
}

run "reject_management_unaligned_prefix" {
  command = plan
  variables {
    azureFirewallManagementSubnetPrefix = "192.168.3.193/26"
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [var.azureFirewallManagementSubnetPrefix]
}

run "reject_management_overlap" {
  command = plan
  variables {
    networkIsolation                    = true
    azureFirewallManagementSubnetPrefix = "192.168.3.128/26"
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_management_outside_new_vnet" {
  command = plan
  variables {
    networkIsolation                    = true
    azureFirewallManagementSubnetPrefix = "10.0.0.0/26"
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_required_management_disabled_without_byo" {
  command = plan
  variables {
    networkIsolation                    = true
    deployAzureFirewallManagementSubnet = false
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_required_data_disabled_without_byo" {
  command = plan
  variables {
    networkIsolation          = true
    deployAzureFirewallSubnet = false
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_global_subnets_disabled_without_byo" {
  command = plan
  variables {
    networkIsolation = true
    deploySubnets    = false
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_management_outside_actual_byo_vnet" {
  command = plan
  variables {
    networkIsolation       = true
    useExistingVNet        = true
    existingVnetResourceId = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared"
  }
  override_data {
    target = data.azapi_resource.network_existing_management_vnet[0]
    values = {
      output = { properties = { addressSpace = { addressPrefixes = ["10.0.0.0/16"] }, subnets = [] } }
    }
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_management_overlap_with_actual_byo_subnet" {
  command = plan
  variables {
    networkIsolation       = true
    useExistingVNet        = true
    existingVnetResourceId = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared"
  }
  override_data {
    target = data.azapi_resource.network_existing_management_vnet[0]
    values = {
      output = {
        properties = {
          addressSpace = { addressPrefixes = ["192.168.0.0/21"] }
          subnets = [{
            name       = "shared-workload"
            properties = { addressPrefix = "192.168.3.192/26" }
          }]
        }
      }
    }
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}

run "reject_byo_management_workload_routing" {
  command = plan
  variables {
    networkIsolation                    = true
    useExistingVNet                     = true
    existingVnetResourceId              = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared"
    deployAzureFirewallManagementSubnet = false
  }
  override_data {
    target = data.azapi_resource.network_existing_subnet["firewallManagement"]
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared/subnets/AzureFirewallManagementSubnet"
      output = {
        properties = {
          addressPrefix = "192.168.3.192/26"
          delegations   = []
          routeTable    = { id = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/routeTables/workload" }
        }
      }
    }
  }
  plan_options {
    target = [terraform_data.network_existing_subnet_contract]
  }
  expect_failures = [terraform_data.network_existing_subnet_contract["firewallManagement"]]
}

run "basic_allows_larger_aligned_management_subnet" {
  command = plan
  variables {
    networkIsolation                    = true
    azureFirewallManagementSubnetPrefix = "192.168.6.0/25"
    useZoneRedundancy                   = true
  }
  assert {
    condition     = local.managed_subnets.firewallManagement.address_prefix == "192.168.6.0/25" && length(module.network_firewall[0].resource.management_ip_configuration) == 1
    error_message = "Basic must accept an aligned management range larger than /26 without moving workload ranges."
  }
}

run "integrated_local_standard_is_supported" {
  command = plan
  variables {
    networkIsolation    = true
    deploymentMode      = "ailz-integrated"
    azureFirewallSku    = "Standard"
    deployGatewaySubnet = true
  }
  assert {
    condition     = contains(keys(local.managed_subnets), "firewall") && contains(keys(local.managed_subnets), "gateway") && !contains(keys(local.managed_subnets), "firewallManagement")
    error_message = "The Basic topology guard must not reject an integrated local Standard firewall or its explicit gateway reservation."
  }
}

run "byo_management_allows_verified_internet_only_routes" {
  command = plan
  variables {
    networkIsolation                    = true
    useExistingVNet                     = true
    existingVnetResourceId              = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared"
    deployAzureFirewallManagementSubnet = false
  }
  override_data {
    target = data.azapi_resource.network_existing_subnet["firewallManagement"]
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared/subnets/AzureFirewallManagementSubnet"
      output = {
        properties = {
          addressPrefix = "192.168.6.0/25"
          delegations   = []
          routeTable    = { id = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/routeTables/management" }
        }
      }
    }
  }
  override_data {
    target = data.azapi_resource.network_existing_management_routes[0]
    values = {
      output = {
        properties = {
          disableBgpRoutePropagation = true
          routes = [{
            properties = { addressPrefix = "0.0.0.0/0", nextHopType = "Internet" }
          }]
        }
      }
    }
  }
  assert {
    condition     = !contains(keys(local.managed_subnets), "firewallManagement") && length(data.azapi_resource.network_existing_management_routes) == 1
    error_message = "A compatible BYO management route table must be verified without acquiring ownership or changing its routes."
  }
}

run "reject_missing_byo_management_subnet" {
  command = plan
  variables {
    networkIsolation                    = true
    useExistingVNet                     = true
    existingVnetResourceId              = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared"
    deployAzureFirewallManagementSubnet = false
  }
  plan_options {
    target = [terraform_data.network_existing_subnet_contract]
  }
  expect_failures = [terraform_data.network_existing_subnet_contract["firewallManagement"]]
}

run "reject_byo_management_small_prefix_and_nsg" {
  command = plan
  variables {
    networkIsolation                    = true
    useExistingVNet                     = true
    existingVnetResourceId              = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared"
    deployAzureFirewallManagementSubnet = false
  }
  override_data {
    target = data.azapi_resource.network_existing_subnet["firewallManagement"]
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared/subnets/AzureFirewallManagementSubnet"
      output = {
        properties = {
          addressPrefix        = "192.168.3.192/27"
          networkSecurityGroup = { id = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/networkSecurityGroups/shared" }
        }
      }
    }
  }
  plan_options {
    target = [terraform_data.network_existing_subnet_contract]
  }
  expect_failures = [terraform_data.network_existing_subnet_contract["firewallManagement"]]
}

run "reject_managed_write_removing_byo_management_associations" {
  command = plan
  variables {
    networkIsolation       = true
    useExistingVNet        = true
    existingVnetResourceId = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/virtualNetworks/shared"
  }
  override_data {
    target = data.azapi_resource.network_existing_management_vnet[0]
    values = {
      output = {
        properties = {
          addressSpace = { addressPrefixes = ["192.168.0.0/21"] }
          subnets = [{
            name       = "AzureFirewallManagementSubnet"
            properties = { addressPrefix = "192.168.3.192/26", routeTable = { id = "/subscriptions/00000000-0000-0000-0000-000000000004/resourceGroups/rg-shared/providers/Microsoft.Network/routeTables/shared" } }
          }]
        }
      }
    }
  }
  plan_options {
    target = [terraform_data.network_contract]
  }
  expect_failures = [terraform_data.network_contract]
}
