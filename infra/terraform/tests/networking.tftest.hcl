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
}

run "isolated_has_exact_subnet_purposes_and_dedicated_application_pe" {
  command = plan
  variables {
    networkIsolation = true
  }
  assert {
    condition = toset(keys(local.managed_subnets)) == toset([
      "agent", "pe", "gateway", "bastion", "firewall", "appGateway", "jumpbox",
      "acaEnvironment", "devopsBuildAgents", "applicationPe", "powerPlatform", "aiGateway"
    ])
    error_message = "All twelve subnet creation flags default on independently of consumers."
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
