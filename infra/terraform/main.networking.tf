# Network composition follows terraform-parity-baseline.json / ADR-0028.
# Subnet ownership is independent of consumer association (ADR-0027).
# Keep producer dependencies out of subnet_ids: endpoints consume service IDs,
# never the reverse. All for_each keys below are derived from deployment intent.
locals {
  network_abbreviations    = jsondecode(file("${path.module}/../shared/abbreviations.json"))
  network_rg_id            = local.deployment_context.network_rg_id
  network_byo_parts        = split("/", var.existingVnetResourceId)
  network_vnet_id          = var.networkIsolation ? (var.useExistingVNet ? var.existingVnetResourceId : module.network_vnet[0].resource_id) : ""
  network_vnet_sub         = var.useExistingVNet ? try(local.network_byo_parts[2], "") : var.subscriptionId
  network_vnet_rg          = var.useExistingVNet ? try(local.network_byo_parts[4], "") : local.deployment_context.network_rg
  network_vnet_name        = var.useExistingVNet ? try(local.network_byo_parts[8], "") : local.resource_names.vnetName
  network_byo_placement    = var.useExistingVNet && !var.sideBySideDeploy
  network_pe_sub           = var.privateEndpointResourceGroupName != "" ? var.subscriptionId : (local.network_byo_placement ? local.network_vnet_sub : var.subscriptionId)
  network_pe_rg            = var.privateEndpointResourceGroupName != "" ? var.privateEndpointResourceGroupName : (local.network_byo_placement ? local.network_vnet_rg : local.deployment_context.network_rg)
  network_dns_sub          = local.network_byo_placement ? local.network_vnet_sub : var.subscriptionId
  network_dns_rg           = local.network_byo_placement ? local.network_vnet_rg : local.deployment_context.network_rg
  network_firewall         = var.networkIsolation && var.deployAzureFirewall
  network_basic_management = local.network_firewall && var.deploymentMode == "standalone" && var.azureFirewallSku == "Basic"
  network_route_table      = var.networkIsolation && coalesce(var.hubIntegrationExistingRouteTableResourceId, " ") == " "
  network_route_id         = local.network_route_table ? module.network_route_table[0].resource_id : coalesce(var.hubIntegrationExistingRouteTableResourceId, " ")
  network_nat_id           = local.effective_flags.nat ? module.network_nat[0].resource_id : (var.existingNatGatewayResourceId == null ? "" : var.existingNatGatewayResourceId)
  network_ingress_live     = var.publicIngress.sslCertSecretId != "" && var.publicIngress.frontendHostName != ""

  public_access = {
    apply_ip_rules        = length(var.allowedIpRanges) > 0
    public_network_access = !var.networkIsolation || length(var.allowedIpRanges) > 0 ? "Enabled" : "Disabled"
    storage_ip_rules      = [for ip in var.allowedIpRanges : { value = ip, action = "Allow" }]
    acr_ip_rules          = [for ip in var.allowedIpRanges : { value = ip, action = "Allow" }]
    key_vault_ip_rules    = [for ip in var.allowedIpRanges : { value = ip }]
    search_ip_rules       = [for ip in var.allowedIpRanges : { value = ip }]
    cognitive_ip_rules    = [for ip in var.allowedIpRanges : { value = ip }]
    cosmos_ip_rules       = var.allowedIpRanges
  }

  network_subnet_inputs = {
    agent = {
      name       = var.agentSubnetName, address_prefix = var.agentSubnetPrefix, create = var.deployAgentSubnet
      required   = var.deployAiFoundry && var.deployAiFoundrySubnet
      delegation = "Microsoft.App/environments", service_endpoints = ["Microsoft.CognitiveServices"]
    }
    pe = {
      name       = var.peSubnetName, address_prefix = var.peSubnetPrefix, create = var.deployPeSubnet
      required   = var.deployAiFoundry || var.deployStorageAccount || var.deploySearchService || var.deploySpeechService || var.deployCosmosDb
      delegation = "", service_endpoints = ["Microsoft.AzureCosmosDB"]
    }
    gateway = {
      name     = var.gatewaySubnetName, address_prefix = var.gatewaySubnetPrefix, create = var.deployGatewaySubnet
      required = false, delegation = "", service_endpoints = []
    }
    bastion = {
      name     = var.azureBastionSubnetName, address_prefix = var.azureBastionSubnetPrefix, create = var.deployAzureBastionSubnet
      required = local.effective_flags.bastion, delegation = "", service_endpoints = []
    }
    firewall = {
      name     = var.azureFirewallSubnetName, address_prefix = var.azureFirewallSubnetPrefix, create = coalesce(var.deployAzureFirewallSubnet, local.network_firewall)
      required = local.network_firewall, delegation = "", service_endpoints = []
    }
    firewallManagement = {
      name     = var.azureFirewallManagementSubnetName, address_prefix = var.azureFirewallManagementSubnetPrefix
      create   = local.network_basic_management && coalesce(var.deployAzureFirewallManagementSubnet, true)
      required = local.network_basic_management, delegation = "", service_endpoints = []
    }
    appGateway = {
      name     = var.azureAppGatewaySubnetName, address_prefix = var.azureAppGatewaySubnetPrefix, create = var.deployAppGatewaySubnet
      required = local.effective_flags.public_ingress, delegation = "", service_endpoints = []
    }
    jumpbox = {
      name     = var.jumpboxSubnetName, address_prefix = var.jumpboxSubnetPrefix, create = var.deployJumpboxSubnet
      required = local.effective_flags.jumpbox, delegation = "", service_endpoints = []
    }
    acaEnvironment = {
      name       = var.acaEnvironmentSubnetName, address_prefix = var.acaEnvironmentSubnetPrefix, create = var.deployAcaEnvironmentSubnet
      required   = var.deployContainerEnv || var.deployCosmosDb
      delegation = "Microsoft.App/environments", service_endpoints = ["Microsoft.AzureCosmosDB"]
    }
    devopsBuildAgents = {
      name     = var.devopsBuildAgentsSubnetName, address_prefix = var.devopsBuildAgentsSubnetPrefix, create = var.deployDevopsBuildAgentsSubnet
      required = local.effective_flags.acr_pool, delegation = "", service_endpoints = []
    }
    applicationPe = {
      name       = var.applicationPeSubnetName, address_prefix = var.applicationPeSubnetPrefix, create = var.deployApplicationPeSubnet
      required   = var.deployCosmosDb || var.deployKeyVault || var.deployAppConfig || var.deployContainerEnv || var.deployContainerRegistry || local.effective_observability.ampls
      delegation = "", service_endpoints = ["Microsoft.AzureCosmosDB"]
    }
    powerPlatform = {
      name     = var.powerPlatformSubnetName, address_prefix = var.powerPlatformSubnetPrefix, create = var.deployPowerPlatformSubnet
      required = false, delegation = "Microsoft.PowerPlatform/enterprisePolicies", service_endpoints = []
    }
    aiGateway = {
      name     = var.aiGatewaySubnetName, address_prefix = var.aiGatewaySubnetPrefix, create = var.deployAiGatewaySubnet
      required = false, delegation = "Microsoft.Web/serverFarms", service_endpoints = []
    }
  }
  subnet_definitions = {
    for purpose, subnet in local.network_subnet_inputs : purpose => merge(subnet, {
      route_table_id            = contains(["agent", "pe", "jumpbox", "acaEnvironment", "devopsBuildAgents", "applicationPe"], purpose) ? trimspace(local.network_route_id) : ""
      nat_gateway_id            = purpose == "jumpbox" ? local.network_nat_id : ""
      network_security_group_id = contains(keys(azapi_resource.network_nsg), purpose) ? azapi_resource.network_nsg[purpose].id : ""
    })
  }
  managed_subnets = {
    for purpose, subnet in local.subnet_definitions : purpose => subnet
    if var.networkIsolation && var.deploySubnets && subnet.create
  }
  subnet_ids = {
    for purpose, subnet in local.subnet_definitions : purpose => !var.networkIsolation ? "" : (
      contains(keys(local.managed_subnets), purpose) ? module.network_subnet[purpose].resource_id : (
        contains(keys(data.azapi_resource.network_existing_subnet), purpose) ? terraform_data.network_existing_subnet_contract[purpose].output : "${local.network_vnet_id}/subnets/${subnet.name}"
      )
    )
  }
  network_relevant_subnets = {
    for purpose, subnet in local.network_subnet_inputs : purpose => subnet
    if var.networkIsolation && ((var.deploySubnets && subnet.create) || subnet.required)
  }
  # Numeric intervals allow containment/overlap checks without provider calls.
  # Invalid inputs remain invalid (-1), never become an accepted fallback CIDR.
  network_cidr_ranges = {
    for purpose, subnet in local.network_relevant_subnets : purpose => {
      start  = try(sum([for i, octet in split(".", cidrhost(subnet.address_prefix, 0)) : tonumber(octet) * pow(256, 3 - i)]), -1)
      end    = try(sum([for i, octet in split(".", cidrhost(subnet.address_prefix, -1)) : tonumber(octet) * pow(256, 3 - i)]), -1)
      prefix = try(tonumber(split("/", subnet.address_prefix)[1]), -1)
      valid  = try(cidrhost(subnet.address_prefix, 0) == split("/", subnet.address_prefix)[0] && length(split(".", cidrhost(subnet.address_prefix, 0))) == 4, false)
    }
  }
  network_vnet_ranges = [
    for cidr in var.vnetAddressPrefixes : {
      start = try(sum([for i, octet in split(".", cidrhost(cidr, 0)) : tonumber(octet) * pow(256, 3 - i)]), -1)
      end   = try(sum([for i, octet in split(".", cidrhost(cidr, -1)) : tonumber(octet) * pow(256, 3 - i)]), -1)
      valid = try(cidrhost(cidr, 0) == split("/", cidr)[0] && length(split(".", cidrhost(cidr, 0))) == 4, false)
    }
  ]
  network_management_vnet_ranges = [
    for cidr in try(data.azapi_resource.network_existing_management_vnet[0].output.properties.addressSpace.addressPrefixes, []) : {
      start = try(sum([for i, octet in split(".", cidrhost(cidr, 0)) : tonumber(octet) * pow(256, 3 - i)]), -1)
      end   = try(sum([for i, octet in split(".", cidrhost(cidr, -1)) : tonumber(octet) * pow(256, 3 - i)]), -1)
    }
  ]
  network_management_peer_ranges = flatten([
    for subnet in try(data.azapi_resource.network_existing_management_vnet[0].output.properties.subnets, []) : [
      for cidr in try(subnet.properties.addressPrefixes, [subnet.properties.addressPrefix]) : {
        start = try(sum([for i, octet in split(".", cidrhost(cidr, 0)) : tonumber(octet) * pow(256, 3 - i)]), -1)
        end   = try(sum([for i, octet in split(".", cidrhost(cidr, -1)) : tonumber(octet) * pow(256, 3 - i)]), -1)
      }
    ] if subnet.name != var.azureFirewallManagementSubnetName
  ])
  network_existing_firewall_ranges = {
    for purpose, subnet in data.azapi_resource.network_existing_subnet : purpose => [
      for cidr in try(subnet.output.properties.addressPrefixes, [subnet.output.properties.addressPrefix], []) : {
        start = try(sum([for i, octet in split(".", cidrhost(cidr, 0)) : tonumber(octet) * pow(256, 3 - i)]), -1)
        end   = try(sum([for i, octet in split(".", cidrhost(cidr, -1)) : tonumber(octet) * pow(256, 3 - i)]), -1)
        valid = try(length(split(".", cidrhost(cidr, 0))) == 4 && cidrhost(cidr, 0) == split("/", cidr)[0] && tonumber(split("/", cidr)[1]) <= 26, false)
      }
    ] if contains(["firewall", "firewallManagement"], purpose)
  }
}

# Preconditions fail the plan (unlike advisory check blocks). This resource has
# no Azure side effects. It also carries the root-owned RG creation dependency.
resource "terraform_data" "network_contract" {
  input = {
    network_rg_id     = local.network_rg_id
    application_rg_id = local.deployment_context.application_rg_id
  }
  lifecycle {
    precondition {
      condition     = !var.networkIsolation || !var.useExistingVNet || can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/virtualNetworks/[^/]+$", var.existingVnetResourceId))
      error_message = "useExistingVNet requires a complete existingVnetResourceId; no replacement VNet is created."
    }
    precondition {
      condition     = !var.networkIsolation || var.useExistingVNet || alltrue([for s in values(local.network_relevant_subnets) : !s.required || (var.deploySubnets && s.create)])
      error_message = "Every required subnet in a new VNet must be managed; consumer flags do not create missing subnets."
    }
    precondition {
      condition     = length(distinct([for s in values(local.network_relevant_subnets) : lower(s.name)])) == length(local.network_relevant_subnets)
      error_message = "Relevant subnet names must be unique case-insensitively."
    }
    precondition {
      condition     = alltrue([for s in values(local.network_relevant_subnets) : can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,78}[A-Za-z0-9_]$|^[A-Za-z0-9]$", s.name))])
      error_message = "Subnet names must be valid Azure names of at most 80 characters."
    }
    precondition {
      condition = alltrue([
        for purpose, name in { gateway = "GatewaySubnet", bastion = "AzureBastionSubnet", firewall = "AzureFirewallSubnet", firewallManagement = "AzureFirewallManagementSubnet" } :
        !contains(keys(local.network_relevant_subnets), purpose) || local.network_subnet_inputs[purpose].name == name
      ])
      error_message = "Gateway, Bastion and Firewall data/management subnet names must match Azure's reserved names exactly."
    }
    precondition {
      condition     = !local.network_firewall || var.azureFirewallSku != "Basic" || var.deploymentMode == "standalone"
      error_message = "Local Basic firewall is supported only in standalone mode; integrated deployments must select Standard or external egress."
    }
    precondition {
      condition     = var.azureFirewallSku != "Basic" || !var.enableFirewallDnsProxy
      error_message = "Basic firewall does not support DNS proxy; explicitly select Standard to enable it."
    }
    precondition {
      condition = alltrue([
        for purpose, r in local.network_cidr_ranges : r.valid && r.prefix >= 0 && r.prefix <= 26
        if contains(["firewall", "firewallManagement"], purpose) && var.deploySubnets && local.network_subnet_inputs[purpose].create
      ])
      error_message = "Managed firewall data and management subnets require aligned IPv4 prefixes of /26 or larger."
    }
    precondition {
      condition = alltrue([
        for purpose, r in local.network_cidr_ranges : r.valid && r.prefix >= 0 && r.prefix <= 29
        if var.deploySubnets && local.network_subnet_inputs[purpose].create
      ])
      error_message = "Managed subnet prefixes must be aligned IPv4 CIDRs with prefix lengths 0..29."
    }
    precondition {
      condition = alltrue(flatten([
        for a, ra in local.network_cidr_ranges : [
          for b, rb in local.network_cidr_ranges : a == b || ra.end < rb.start || rb.end < ra.start
          if var.deploySubnets && local.network_subnet_inputs[a].create && local.network_subnet_inputs[b].create
        ]
      ]))
      error_message = "Managed subnet IPv4 prefixes must not overlap."
    }
    precondition {
      condition = !var.networkIsolation || var.useExistingVNet || (
        length(local.network_vnet_ranges) > 0 && alltrue([for r in local.network_vnet_ranges : r.valid]) &&
        alltrue([for purpose, r in local.network_cidr_ranges : anytrue([for v in local.network_vnet_ranges : r.start >= v.start && r.end <= v.end]) if var.deploySubnets && local.network_subnet_inputs[purpose].create])
      )
      error_message = "Every managed subnet must be contained in an aligned IPv4 VNet address prefix."
    }
    precondition {
      condition = !local.network_basic_management || !var.useExistingVNet || !(var.deploySubnets && local.network_subnet_inputs.firewallManagement.create) || try(
        anytrue([for v in local.network_management_vnet_ranges : local.network_cidr_ranges.firewallManagement.start >= v.start && local.network_cidr_ranges.firewallManagement.end <= v.end]) &&
        alltrue([
          for r in local.network_management_peer_ranges : local.network_cidr_ranges.firewallManagement.end < r.start || r.end < local.network_cidr_ranges.firewallManagement.start
        ]),
        false
      )
      error_message = "A managed Basic management subnet must fit the actual BYO VNet address space without overlapping its other subnets."
    }
    precondition {
      condition = !local.network_basic_management || !var.useExistingVNet || !(var.deploySubnets && local.network_subnet_inputs.firewallManagement.create) || try(alltrue([
        for subnet in data.azapi_resource.network_existing_management_vnet[0].output.properties.subnets :
        try(subnet.properties.routeTable.id, "") == "" &&
        try(subnet.properties.networkSecurityGroup.id, "") == "" &&
        try(subnet.properties.natGateway.id, "") == "" &&
        length(try(subnet.properties.delegations, [])) == 0 &&
        length(try(subnet.properties.serviceEndpoints, [])) == 0
        if subnet.name == var.azureFirewallManagementSubnetName
      ]), false)
      error_message = "Managed management-subnet creation must not remove existing shared associations; disable creation and validate BYO reuse instead."
    }
    precondition {
      condition     = !var.networkIsolation || !var.deploySubnets || !var.deployAiGatewaySubnet || (var.deployNsgs && try(local.network_cidr_ranges.aiGateway.prefix <= 27, false))
      error_message = "The managed AI Gateway subnet requires deployNsgs and a /27 or larger prefix."
    }
    precondition {
      condition     = !var.networkIsolation || var.deployAzureFirewall || trimspace(coalesce(var.hubIntegrationEgressNextHopIp, " ")) != "" || trimspace(coalesce(var.hubIntegrationExistingRouteTableResourceId, " ")) != ""
      error_message = "Isolated egress requires the local firewall, an external next-hop IP, or an existing route table."
    }
    precondition {
      condition     = !var.networkIsolation || !(var.deployAzureFirewall && (trimspace(coalesce(var.hubIntegrationEgressNextHopIp, " ")) != "" || trimspace(coalesce(var.hubIntegrationExistingRouteTableResourceId, " ")) != ""))
      error_message = "Local firewall and BYO egress options are mutually exclusive."
    }
    precondition {
      condition     = !local.effective_flags.public_ingress || var.publicIngress.backendAppIndex < length(var.containerAppsList)
      error_message = "publicIngress.backendAppIndex must select a configured Container App."
    }
    precondition {
      condition = var.publicIngress.sslPolicy == null ? true : try(alltrue([
        for key in keys(var.publicIngress.sslPolicy) : contains(["cipherSuites", "disabledSslProtocols", "minProtocolVersion", "policyName", "policyType"], key)
      ]), false)
      error_message = "sslPolicy must be an ARM SSL policy object; unsupported fields cannot be silently discarded."
    }
  }
}

# Inspect BYO address space rather than assuming the new-VNet defaults apply.
data "azapi_resource" "network_existing_management_vnet" {
  count                  = local.network_basic_management && var.useExistingVNet && var.existingVnetResourceId != "" ? 1 : 0
  type                   = "Microsoft.Network/virtualNetworks@2024-07-01"
  resource_id            = var.existingVnetResourceId
  response_export_values = ["properties.addressSpace", "properties.subnets"]
}

module "network_vnet" {
  source           = "Azure/avm-res-network-virtualnetwork/azurerm"
  version          = "0.22.3"
  count            = var.networkIsolation && !var.useExistingVNet ? 1 : 0
  name             = local.resource_names.vnetName
  parent_id        = local.network_rg_id
  location         = local.effective_locations.main
  address_space    = toset(var.vnetAddressPrefixes)
  tags             = local.deployment_context.tags
  enable_telemetry = false
  # Separate child modules avoid a VNet -> subnet -> firewall -> VNet cycle.
  subnets    = {}
  depends_on = [terraform_data.network_contract]
}

module "network_subnet" {
  source            = "Azure/avm-res-network-virtualnetwork/azurerm//modules/subnet"
  version           = "0.22.3"
  for_each          = local.managed_subnets
  parent_id         = local.network_vnet_id
  name              = each.value.name
  address_prefix    = each.value.address_prefix
  service_endpoints = toset(each.value.service_endpoints)
  delegations = each.value.delegation == "" ? [] : [{
    name               = each.value.delegation
    service_delegation = { name = each.value.delegation }
  }]
  route_table            = each.value.route_table_id == "" ? null : { id = each.value.route_table_id }
  nat_gateway            = each.value.nat_gateway_id == "" ? null : { id = each.value.nat_gateway_id }
  network_security_group = each.value.network_security_group_id == "" ? null : { id = each.value.network_security_group_id }
  # Match Bicep's subnet policy/default-outbound behavior, not AVM defaults.
  private_endpoint_network_policies = "Disabled"
  # null omits the property through AzAPI; retain the Azure/Bicep default
  # instead of explicitly enabling default Internet outbound access.
  default_outbound_access_enabled = null
  # Verified AVM implementation locks the parent VNet for every child write.
  depends_on = [terraform_data.network_contract]
}

data "azapi_resource" "network_existing_subnet" {
  for_each = {
    for purpose, subnet in local.network_subnet_inputs : purpose => subnet
    if var.networkIsolation && var.useExistingVNet && subnet.required && !(var.deploySubnets && subnet.create)
  }
  type                   = "Microsoft.Network/virtualNetworks/subnets@2024-07-01"
  parent_id              = var.existingVnetResourceId
  name                   = each.value.name
  response_export_values = ["properties"]
}

# A BYO management table is read-only and must preserve direct Internet egress.
data "azapi_resource" "network_existing_management_routes" {
  count                  = trimspace(coalesce(try(data.azapi_resource.network_existing_subnet["firewallManagement"].output.properties.routeTable.id, null), " ")) != "" ? 1 : 0
  type                   = "Microsoft.Network/routeTables@2024-07-01"
  resource_id            = data.azapi_resource.network_existing_subnet["firewallManagement"].output.properties.routeTable.id
  response_export_values = ["properties"]
}

resource "terraform_data" "network_existing_subnet_contract" {
  for_each = data.azapi_resource.network_existing_subnet
  input    = each.value.id
  lifecycle {
    precondition {
      condition = !contains(["firewall", "firewallManagement"], each.key) || try(
        lower(each.value.id) == lower("${var.existingVnetResourceId}/subnets/${local.network_subnet_inputs[each.key].name}") &&
        alltrue([for r in local.network_existing_firewall_ranges[each.key] : r.valid]) &&
        length(local.network_existing_firewall_ranges[each.key]) > 0,
        false
      )
      error_message = "A reused firewall subnet must belong to the selected VNet and have aligned IPv4 prefixes of /26 or larger."
    }
    precondition {
      condition = each.key != "firewallManagement" || try(
        alltrue([
          for r in local.network_existing_firewall_ranges[each.key] :
          anytrue([for v in local.network_management_vnet_ranges : r.start >= v.start && r.end <= v.end]) &&
          alltrue([for peer in local.network_management_peer_ranges : r.end < peer.start || peer.end < r.start]) &&
          alltrue([
            for purpose, managed in local.network_cidr_ranges : r.end < managed.start || managed.end < r.start
            if purpose != each.key && var.deploySubnets && local.network_subnet_inputs[purpose].create
          ])
        ]) &&
        try(each.value.output.properties.networkSecurityGroup.id, "") == "" &&
        try(each.value.output.properties.natGateway.id, "") == "" &&
        length(try(each.value.output.properties.privateEndpoints, [])) == 0 &&
        length(try(each.value.output.properties.serviceEndpoints, [])) == 0,
        false
      )
      error_message = "A reused management subnet must fit the actual VNet without overlap and have no NSG, NAT or service endpoints; shared associations are never rewritten."
    }
    precondition {
      condition = each.key != "firewallManagement" || try(each.value.output.properties.routeTable.id, "") == "" || try(
        data.azapi_resource.network_existing_management_routes[0].output.properties.disableBgpRoutePropagation &&
        anytrue([
          for route in data.azapi_resource.network_existing_management_routes[0].output.properties.routes :
          route.properties.addressPrefix == "0.0.0.0/0" && route.properties.nextHopType == "Internet"
        ]) &&
        alltrue([
          for route in data.azapi_resource.network_existing_management_routes[0].output.properties.routes :
          route.properties.nextHopType == "Internet"
        ]),
        false
      )
      error_message = "A BYO management route table must disable BGP propagation, route 0.0.0.0/0 directly to Internet and contain no redirecting/blocking routes."
    }
    precondition {
      condition = local.network_subnet_inputs[each.key].delegation == "" ? (
        length(try(each.value.output.properties.delegations, [])) == 0
        ) : contains(
        [for d in try(each.value.output.properties.delegations, []) : d.properties.serviceName],
        local.network_subnet_inputs[each.key].delegation
      )
      error_message = "A reused subnet must have the expected delegation; it is not modified or replaced."
    }
    precondition {
      condition = alltrue([
        for endpoint in local.network_subnet_inputs[each.key].service_endpoints :
        contains([for s in try(each.value.output.properties.serviceEndpoints, []) : s.service], endpoint)
      ])
      error_message = "A reused subnet is missing a required service endpoint; it is not modified or replaced."
    }
  }
}

module "network_route_table" {
  source                        = "Azure/avm-res-network-routetable/azurerm"
  version                       = "0.4.1"
  count                         = local.network_route_table ? 1 : 0
  name                          = "${local.network_abbreviations.networking.routeTable}${local.resource_token}"
  location                      = local.effective_locations.main
  resource_group_name           = local.deployment_context.network_rg
  bgp_route_propagation_enabled = false
  tags                          = local.deployment_context.tags
  enable_telemetry              = false
  routes                        = {}
  depends_on                    = [terraform_data.network_contract]
}

# A separate route child is necessary: attaching a table containing the
# computed firewall IP during subnet creation would introduce a graph cycle.
resource "azapi_resource" "network_default_route" {
  count     = local.network_route_table && (var.deployAzureFirewall || trimspace(coalesce(var.hubIntegrationEgressNextHopIp, " ")) != "") ? 1 : 0
  type      = "Microsoft.Network/routeTables/routes@2024-07-01"
  name      = "default-to-firewall"
  parent_id = module.network_route_table[0].resource_id
  body = {
    properties = {
      addressPrefix    = "0.0.0.0/0"
      nextHopType      = "VirtualAppliance"
      nextHopIpAddress = local.network_firewall ? module.network_firewall[0].resource.ip_configuration[0].private_ip_address : var.hubIntegrationEgressNextHopIp
    }
  }
  locks = [module.network_route_table[0].resource_id]
}

module "network_nat" {
  source              = "Azure/avm-res-network-natgateway/azurerm"
  version             = "0.2.1"
  count               = local.effective_flags.nat ? 1 : 0
  name                = "${local.network_abbreviations.networking.natGateway}${local.resource_token}"
  location            = local.effective_locations.main
  resource_group_name = local.deployment_context.network_rg
  sku_name            = "Standard"
  public_ips = {
    jumpbox = { name = "${local.network_abbreviations.networking.publicIPAddress}${local.network_abbreviations.networking.natGateway}${local.resource_token}" }
  }
  public_ip_configuration = {
    domain_name_label = "${local.network_abbreviations.networking.publicIPAddress}${local.network_abbreviations.networking.natGateway}${local.resource_token}"
    zones             = []
  }
  tags             = local.deployment_context.tags
  enable_telemetry = false
  depends_on       = [terraform_data.network_contract]
}

module "network_public_ip" {
  source  = "Azure/avm-res-network-publicipaddress/azurerm"
  version = "0.2.0"
  for_each = merge(
    local.network_firewall ? { firewall = "${local.network_abbreviations.networking.publicIPAddress}${local.network_abbreviations.networking.firewall}${local.resource_token}" } : {},
    local.network_basic_management ? { firewallManagement = "${local.network_abbreviations.networking.publicIPAddress}${local.network_abbreviations.networking.firewall}management-${local.resource_token}" } : {},
    local.effective_flags.bastion ? { bastion = "${local.network_abbreviations.networking.publicIPAddress}bastion-${local.resource_token}" } : {},
    local.effective_flags.public_ingress ? { ingress = "${local.network_ingress_prefix}-pip" } : {}
  )
  name                = each.value
  location            = local.effective_locations.main
  resource_group_name = each.key == "ingress" ? local.deployment_context.application_rg : local.deployment_context.network_rg
  allocation_method   = "Static"
  ip_version          = "IPv4"
  sku                 = "Standard"
  zones               = !contains(["firewall", "firewallManagement"], each.key) && var.useZoneRedundancy ? [1, 2, 3] : []
  tags                = local.deployment_context.tags
  enable_telemetry    = false
  depends_on          = [terraform_data.network_contract]
}

module "network_bastion" {
  source              = "Azure/avm-res-network-bastionhost/azurerm"
  version             = "0.7.2"
  count               = local.effective_flags.bastion ? 1 : 0
  name                = "${local.network_abbreviations.security.bastion}testvm-${local.resource_token}"
  location            = local.effective_locations.main
  resource_group_name = local.deployment_context.network_rg
  sku                 = var.bastionSkuName
  tunneling_enabled   = var.bastionEnableTunneling
  zones               = var.useZoneRedundancy ? ["1", "2", "3"] : []
  ip_configuration = {
    name                 = "ipconfig"
    subnet_id            = local.subnet_ids.bastion
    create_public_ip     = false
    public_ip_address_id = module.network_public_ip["bastion"].resource_id
  }
  tags             = local.deployment_context.tags
  enable_telemetry = false
}

module "network_firewall_policy" {
  source                                   = "Azure/avm-res-network-firewallpolicy/azurerm"
  version                                  = "0.3.3"
  count                                    = local.network_firewall ? 1 : 0
  name                                     = "${local.network_abbreviations.networking.firewallPolicy}${local.resource_token}"
  location                                 = local.effective_locations.main
  resource_group_name                      = local.deployment_context.network_rg
  firewall_policy_sku                      = var.azureFirewallSku
  firewall_policy_threat_intelligence_mode = "Alert"
  firewall_policy_dns                      = var.azureFirewallSku == "Basic" ? null : { proxy_enabled = var.enableFirewallDnsProxy }
  tags                                     = local.deployment_context.tags
  enable_telemetry                         = false
  depends_on                               = [terraform_data.network_contract]
}

module "network_firewall" {
  source              = "Azure/avm-res-network-azurefirewall/azurerm"
  version             = "0.4.0"
  count               = local.network_firewall ? 1 : 0
  name                = "${local.network_abbreviations.networking.firewall}${local.resource_token}"
  location            = local.effective_locations.main
  resource_group_name = local.deployment_context.network_rg
  firewall_sku_name   = "AZFW_VNet"
  firewall_sku_tier   = var.azureFirewallSku
  firewall_zones      = []
  firewall_policy_id  = module.network_firewall_policy[0].resource_id
  ip_configurations = {
    primary = {
      name                 = "ipconfig1"
      public_ip_address_id = module.network_public_ip["firewall"].resource_id
      subnet_id            = local.subnet_ids.firewall
    }
  }
  firewall_management_ip_configuration = local.network_basic_management ? {
    name                 = "managementIpconfig"
    public_ip_address_id = module.network_public_ip["firewallManagement"].resource_id
    subnet_id            = local.subnet_ids.firewallManagement
  } : null
  tags             = local.deployment_context.tags
  enable_telemetry = false
}

# Both local and foreign VNet subnet NSGs use explicit ARM parent IDs.
# The verified NSG AVM 0.5.0 is AzureRM/RG-name scoped and cannot route a
# per-instance subscription dynamically; AzAPI preserves this BYO contract.
locals {
  network_nsg_specs = merge(
    local.effective_flags.bastion && var.deployNsgs ? { bastion = { parent_id = local.network_rg_id, name = "nsg-${local.resource_names.vnetName}-${var.azureBastionSubnetName}" } } : {},
    local.effective_flags.public_ingress ? { appGateway = { parent_id = local.network_rg_id, name = "nsg-${local.resource_names.vnetName}-${var.azureAppGatewaySubnetName}" } } : {},
    var.networkIsolation && var.deploySubnets && var.deployAiGatewaySubnet && var.deployNsgs ? { aiGateway = { parent_id = "/subscriptions/${local.network_vnet_sub}/resourceGroups/${local.network_vnet_rg}", name = "nsg-${local.network_vnet_name}-${var.aiGatewaySubnetName}" } } : {}
  )
  network_nsg_rule_base = { sourcePortRange = "*", destinationAddressPrefix = "*", access = "Allow", direction = "Inbound" }
  network_nsg_rules = {
    bastion = concat([
      { name = "AllowGatewayManagerInbound", properties = merge(local.network_nsg_rule_base, { protocol = "Tcp", destinationPortRange = "443", sourceAddressPrefix = "GatewayManager", priority = 100 }) },
      { name = "AllowAzureLoadBalancerInbound", properties = merge(local.network_nsg_rule_base, { protocol = "Tcp", destinationPortRange = "443", sourceAddressPrefix = "AzureLoadBalancer", priority = 110 }) },
      { name = "AllowBastionHostCommunicationInbound", properties = merge(local.network_nsg_rule_base, { protocol = "*", destinationPortRanges = ["8080", "5701"], sourceAddressPrefix = "VirtualNetwork", destinationAddressPrefix = "VirtualNetwork", priority = 120 }) },
      { name = "DenyAllInternetInbound", properties = merge(local.network_nsg_rule_base, { protocol = "*", destinationPortRange = "*", sourceAddressPrefix = "Internet", priority = 4096, access = "Deny" }) },
      { name = "AllowSshRdpOutbound", properties = merge(local.network_nsg_rule_base, { protocol = "Tcp", destinationPortRanges = ["22", "3389"], sourceAddressPrefix = "*", destinationAddressPrefix = "VirtualNetwork", priority = 100, direction = "Outbound" }) },
      { name = "AllowAzureCloudOutbound", properties = merge(local.network_nsg_rule_base, { protocol = "Tcp", destinationPortRange = "443", sourceAddressPrefix = "*", destinationAddressPrefix = "AzureCloud", priority = 110, direction = "Outbound" }) },
      { name = "AllowBastionHostCommunicationOutbound", properties = merge(local.network_nsg_rule_base, { protocol = "*", destinationPortRanges = ["8080", "5701"], sourceAddressPrefix = "VirtualNetwork", destinationAddressPrefix = "VirtualNetwork", priority = 120, direction = "Outbound" }) },
      { name = "AllowGetSessionInformationOutbound", properties = merge(local.network_nsg_rule_base, { protocol = "*", destinationPortRange = "80", sourceAddressPrefix = "*", destinationAddressPrefix = "Internet", priority = 130, direction = "Outbound" }) }
      ], [
      for i, ip in var.bastionAllowedSourceIPs : { name = "AllowHttpsFromTrustedIP-${i}", properties = merge(local.network_nsg_rule_base, { protocol = "Tcp", destinationPortRange = "443", sourceAddressPrefix = ip, priority = 200 + i }) }
    ])
    appGateway = concat([
      { name = "AllowGatewayManagerInbound", properties = merge(local.network_nsg_rule_base, { protocol = "Tcp", destinationPortRange = "65200-65535", sourceAddressPrefix = "GatewayManager", priority = 100 }) },
      { name = "AllowAzureLoadBalancerInbound", properties = merge(local.network_nsg_rule_base, { protocol = "*", destinationPortRange = "*", sourceAddressPrefix = "AzureLoadBalancer", priority = 110 }) },
      { name = "DenyAllInternetInbound", properties = merge(local.network_nsg_rule_base, { protocol = "*", destinationPortRange = "*", sourceAddressPrefix = "Internet", priority = 4096, access = "Deny" }) }
      ], length(try(var.publicIngress.allowedSourceAddressPrefixes, [])) == 0 ? [] : [
      { name = "AllowHttpsFromAllowedSources", properties = merge(local.network_nsg_rule_base, { protocol = "Tcp", destinationPortRange = "443", sourceAddressPrefixes = var.publicIngress.allowedSourceAddressPrefixes, priority = 200 }) }
    ])
    aiGateway = [{
      name = "AllowKeyVaultOutbound"
      properties = merge(local.network_nsg_rule_base, {
        description = "APIM outbound HTTPS access to Azure Key Vault."
        protocol    = "Tcp", destinationPortRange = "443", sourceAddressPrefix = "VirtualNetwork", destinationAddressPrefix = "AzureKeyVault", priority = 100, direction = "Outbound"
      })
    }]
  }
}

resource "azapi_resource" "network_nsg" {
  for_each   = local.network_nsg_specs
  type       = "Microsoft.Network/networkSecurityGroups@2024-07-01"
  parent_id  = each.value.parent_id
  name       = each.value.name
  location   = local.effective_locations.main
  body       = { properties = { securityRules = local.network_nsg_rules[each.key] } }
  depends_on = [terraform_data.network_contract]
}

resource "azapi_resource" "network_spoke_peering" {
  count     = var.networkIsolation && !var.useExistingVNet && var.hubIntegrationCreateHubPeering && trimspace(coalesce(var.hubIntegrationHubVnetResourceId, " ")) != "" ? 1 : 0
  type      = "Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-07-01"
  parent_id = local.network_vnet_id
  name      = "to-hub-${try(reverse(split("/", var.hubIntegrationHubVnetResourceId))[0], "")}"
  body = {
    properties = {
      remoteVirtualNetwork      = { id = var.hubIntegrationHubVnetResourceId }
      allowVirtualNetworkAccess = true
      allowForwardedTraffic     = true
      allowGatewayTransit       = var.hubIntegrationPeeringAllowGatewayTransit
      useRemoteGateways         = var.hubIntegrationPeeringUseRemoteGateways
    }
  }
  locks = [local.network_vnet_id]
}

locals {
  network_storage_suffix = local.deployment_context.storage_suffix
  network_runtime_fqdns  = ["www.python.org", "*.python.org", "pypi.org", "*.pypi.org", "files.pythonhosted.org", "*.pythonhosted.org", "bootstrap.pypa.io", "*.pypa.io", "registry.npmjs.org", "*.npmjs.org"]
  network_firewall_rule_specs = {
    AllowMicrosoftContainerRegistry = { sources = ["*"], ports = ["Https"], fqdns = ["mcr.microsoft.com", "*.data.mcr.microsoft.com"] }
    AllowEntraIdAuth                = { sources = ["*"], ports = ["Https"], fqdns = ["login.microsoftonline.com", "login.windows.net", "management.azure.com", "graph.microsoft.com", "*.applicationinsights.azure.com"] }
    AllowGitHub                     = { sources = ["*"], ports = ["Https"], fqdns = ["github.com", "*.github.com", "raw.githubusercontent.com", "codeload.github.com", "objects.githubusercontent.com", "*.githubusercontent.com"] }
    AllowContainerAppsPlatform = {
      sources = ["*"], ports = ["Https"]
      fqdns = [
        "*.servicebus.windows.net", "*.identity.azure.net", "*.azurecontainerapps.io", "*.azurecontainerapps.dev",
        "*.in.applicationinsights.azure.com", "*.livediagnostics.monitor.azure.com", "*.ingest.monitor.azure.com",
        "*.monitor.azure.com", "*.monitor.core.windows.net", "*.opinsights.azure.com", "*.loganalytics.io",
        "oneocsp.microsoft.com", "ocsp.digicert.com", "crl.microsoft.com", "crl2.microsoft.com", "crl3.microsoft.com",
        "crl.digicert.com", "crl3.digicert.com", "crl4.digicert.com", "ctldl.windowsupdate.com", "agent365.svc.cloud.microsoft"
      ]
    }
    AllowJumpboxBootstrap = {
      sources = [var.jumpboxSubnetPrefix], ports = ["Https", "Http"]
      fqdns = var.extendFirewallForJumpboxBootstrap ? concat([
        "community.chocolatey.org", "packages.chocolatey.org", "*.chocolatey.org", "api.nuget.org", "www.nuget.org",
        "dist.nuget.org", "*.nuget.org", "download.visualstudio.microsoft.com", "*.visualstudio.microsoft.com",
        "download.microsoft.com", "*.download.microsoft.com", "aka.ms", "go.microsoft.com", "downloads.bicep.azure.com",
        "github.com", "*.githubusercontent.com", "objects.githubusercontent.com", "codeload.github.com", "*.core.windows.net", "*.azureedge.net"
      ], var.deploySpeechService ? ["*.cognitiveservices.azure.com", "*.tts.speech.microsoft.com", "*.stt.speech.microsoft.com"] : []) : []
    }
    AllowJumpboxDevRuntimes = { sources = [var.jumpboxSubnetPrefix], ports = ["Https"], fqdns = var.extendFirewallForJumpboxBootstrap ? local.network_runtime_fqdns : [] }
    AllowJumpboxEditors     = { sources = [var.jumpboxSubnetPrefix], ports = ["Https"], fqdns = var.extendFirewallForJumpboxBootstrap ? ["update.code.visualstudio.com", "*.vo.msecnd.net", "*.vscode-cdn.net"] : [] }
    AllowJumpboxAcme        = { sources = [var.jumpboxSubnetPrefix], ports = ["Https"], fqdns = var.extendFirewallForJumpboxBootstrap ? ["api.github.com", "acme-v02.api.letsencrypt.org"] : [] }
    AllowAcrTasks = {
      sources = [var.devopsBuildAgentsSubnetPrefix], ports = ["Https"]
      fqdns   = local.effective_flags.acr_pool ? ["*.azurecr.io", "*.data.azurecr.io", "*.blob.${local.network_storage_suffix}", "*.queue.${local.network_storage_suffix}", "*.table.${local.network_storage_suffix}"] : []
    }
    AllowAcrTaskDevRuntimes = {
      sources = [var.devopsBuildAgentsSubnetPrefix], ports = ["Https"]
      fqdns = local.effective_flags.acr_pool && var.extendFirewallForAcrTaskBuilds ? distinct(concat(
        local.network_runtime_fqdns,
        ["ms-feed-2.pkgs.visualstudio.com", "ms-feed-12.pkgs.visualstudio.com", "ms-feed-17.pkgs.visualstudio.com", "ms-feed-25.pkgs.visualstudio.com", "*.vsblob.vsassets.io"],
        var.additionalAcrTaskBuildFqdns
      )) : []
    }
    AllowAcrTaskOsPackages = {
      sources = [var.devopsBuildAgentsSubnetPrefix], ports = ["Https", "Http"]
      fqdns   = local.effective_flags.acr_pool && var.extendFirewallForAcrTaskBuilds ? ["deb.debian.org", "security.debian.org", "archive.ubuntu.com", "security.ubuntu.com", "dl.yarnpkg.com", "packages.microsoft.com"] : []
    }
  }
  network_firewall_application_rules = [
    for name, rule in local.network_firewall_rule_specs : {
      name      = name, ruleType = "ApplicationRule", sourceAddresses = rule.sources, targetFqdns = rule.fqdns
      protocols = [for protocol in rule.ports : { protocolType = protocol, port = protocol == "Https" ? 443 : 80 }]
    } if length(rule.fqdns) > 0
  ]
  network_firewall_collections = merge({
    DefaultRuleCollectionGroup = {
      priority = 200
      ruleCollections = [{
        name   = "AllowEssentialOutbound", priority = 100, ruleCollectionType = "FirewallPolicyFilterRuleCollection"
        action = { type = "Allow" }, rules = local.network_firewall_application_rules
      }]
    }
    }, local.effective_flags.acr_pool ? {
    AcrTaskAgentPoolRuleCollectionGroup = {
      priority = 250
      ruleCollections = [{
        name   = "AllowAcrTaskAgentPoolPlatform", priority = 100, ruleCollectionType = "FirewallPolicyFilterRuleCollection"
        action = { type = "Allow" }
        rules = [
          for name, tag in { KeyVault = "AzureKeyVault", Storage = "Storage", EventHub = "EventHub", AzureAD = "AzureActiveDirectory", Monitor = "AzureMonitor" } : {
            name                      = "AllowAcrTaskAgentPool${name}", ruleType = "NetworkRule", ipProtocols = ["TCP"]
            sourceAddresses           = [var.devopsBuildAgentsSubnetPrefix], destinationAddresses = [tag]
            destinationPorts          = tag == "AzureMonitor" ? ["443", "12000"] : ["443"]
          }
        ]
      }]
    }
    } : {}, var.enableAcsMediaEgress ? {
    AcsMediaRuleCollectionGroup = {
      priority = 300
      ruleCollections = [{
        name = "AllowAcsMedia", priority = 100, ruleCollectionType = "FirewallPolicyFilterRuleCollection", action = { type = "Allow" }
        rules = [
          for protocol in ["UDP", "TCP"] : {
            name                 = protocol == "UDP" ? "AllowAcsMediaUdp" : "AllowAcsMediaTcp", ruleType = "NetworkRule", ipProtocols = [protocol]
            sourceAddresses      = [var.jumpboxSubnetPrefix, var.acaEnvironmentSubnetPrefix, var.agentSubnetPrefix]
            destinationAddresses = ["AzureCloud"], destinationPorts = protocol == "UDP" ? ["3478-3481"] : ["443", "3478-3481"]
          }
        ]
      }]
    }
  } : {})
}

# Complement the policy AVM with ARM-native rule collections. All writes lock
# the shared policy; all wait for firewall association to finish (source #597).
resource "azapi_resource" "network_firewall_rules" {
  for_each   = { for name, group in local.network_firewall_collections : name => group if local.network_firewall }
  type       = "Microsoft.Network/firewallPolicies/ruleCollectionGroups@2024-07-01"
  parent_id  = module.network_firewall_policy[0].resource_id
  name       = each.key
  body       = { properties = each.value }
  locks      = [module.network_firewall_policy[0].resource_id]
  depends_on = [module.network_firewall]
}

locals {
  network_dns_suffix = "${var.useExistingVNet ? "-byon" : ""}${var.dnsZoneLinkSuffix == "" ? "" : "-${var.dnsZoneLinkSuffix}"}"
  network_dns_specs = {
    CogSvcs         = { name = "privatelink.cognitiveservices.azure.com", link = "cogsvcs", byo = var.existingPrivateDnsZoneCogSvcsResourceId, enabled = true }
    OpenAi          = { name = "privatelink.openai.azure.com", link = "openai", byo = var.existingPrivateDnsZoneOpenAiResourceId, enabled = true }
    AiServices      = { name = "privatelink.services.ai.azure.com", link = "aiservices", byo = var.existingPrivateDnsZoneAiServicesResourceId, enabled = true }
    Search          = { name = "privatelink.search.windows.net", link = "search-std", byo = var.existingPrivateDnsZoneSearchResourceId, enabled = true }
    Cosmos          = { name = "privatelink.documents.azure.com", link = "cosmos-std", byo = var.existingPrivateDnsZoneCosmosResourceId, enabled = true }
    Blob            = { name = "privatelink.blob.${local.network_storage_suffix}", link = "blob-std", byo = var.existingPrivateDnsZoneBlobResourceId, enabled = true }
    KeyVault        = { name = "privatelink.vaultcore.azure.net", link = "kv", byo = var.existingPrivateDnsZoneKeyVaultResourceId, enabled = true }
    AppConfig       = { name = "privatelink.azconfig.io", link = "appcfg", byo = var.existingPrivateDnsZoneAppConfigResourceId, enabled = true }
    ContainerApps   = { name = "privatelink.${local.effective_locations.main}.azurecontainerapps.io", link = "containerapps", byo = var.existingPrivateDnsZoneContainerAppsResourceId, enabled = var.deployContainerEnv }
    Acr             = { name = "privatelink.${var.acrDnsSuffix}", link = "containerregistry", byo = var.existingPrivateDnsZoneAcrResourceId, enabled = var.deployContainerRegistry }
    AzureMonitor    = { name = "privatelink.monitor.azure.com", link = "azure-monitor", byo = var.existingPrivateDnsZoneAzureMonitorResourceId, enabled = local.effective_observability.ampls }
    OmsOpsInsights  = { name = "privatelink.oms.opinsights.azure.com", link = "oms-opinsights", byo = var.existingPrivateDnsZoneOmsOpsInsightsResourceId, enabled = local.effective_observability.ampls }
    OdsOpsInsights  = { name = "privatelink.ods.opinsights.azure.com", link = "ods-opinsights", byo = var.existingPrivateDnsZoneOdsOpsInsightsResourceId, enabled = local.effective_observability.ampls }
    AzureAutomation = { name = "privatelink.agentsvc.azure.automation.net", link = "azure-automation", byo = var.existingPrivateDnsZoneAzureAutomationResourceId, enabled = local.effective_observability.ampls }
    AppInsights     = { name = "privatelink.applicationinsights.io", link = "appi", byo = var.existingPrivateDnsZoneAppInsightsResourceId, enabled = local.effective_observability.ampls }
  }
  network_managed_dns = {
    for namespace, zone in local.network_dns_specs : namespace => zone
    if var.networkIsolation && !var.policyManagedPrivateDns && zone.enabled && trimspace(coalesce(zone.byo, " ")) == ""
  }
  private_dns_zone_ids = {
    for namespace, zone in local.network_dns_specs : namespace => (
      !var.networkIsolation || var.policyManagedPrivateDns || !zone.enabled ? "" :
      (trimspace(coalesce(zone.byo, " ")) != "" ? zone.byo : module.network_private_dns[namespace].resource_id)
    )
  }
}

module "network_private_dns" {
  source           = "Azure/avm-res-network-privatednszone/azurerm"
  version          = "0.4.2"
  for_each         = local.network_managed_dns
  domain_name      = each.value.name
  parent_id        = "/subscriptions/${local.network_dns_sub}/resourceGroups/${local.network_dns_rg}"
  tags             = local.deployment_context.tags
  enable_telemetry = false
  virtual_network_links = {
    spoke = {
      name                 = "${local.resource_names.vnetName}-${each.value.link}-link${local.network_dns_suffix}"
      virtual_network_id   = local.network_vnet_id
      registration_enabled = false
    }
  }
  depends_on = [terraform_data.network_contract, module.network_subnet]
}

# A tiny dependency carrier ensures the account endpoint waits for the project
# child when present, without making subnet or DNS locals depend on Foundry.
resource "terraform_data" "network_foundry_ready" {
  count = var.deployAiFoundry ? 1 : 0
  input = {
    account_id = local.foundry_context.account_id
    project_id = local.foundry_context.project_id
  }
}

resource "terraform_data" "network_ampls_ready" {
  count = local.effective_observability.ampls ? 1 : 0
  input = {
    ampls_id            = local.effective_observability.ampls_id
    scoped_resource_ids = local.effective_observability.ampls_scoped_resource_ids
  }
}

locals {
  # Keep the two producer maps separate all the way through resource expansion.
  # Filtering a mixed map later still leaves its resource node dependent on
  # compute_context; Foundry connections must not acquire that dependency.
  network_application_endpoint_specs = {
    storage = {
      enabled    = var.deployStorageAccount, target = local.data_context.storage.id
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.resource_names.storageAccountName}"
      connection = "blobConnection", subnet = "pe", groups = ["blob"], zones = ["Blob"], zone_group = "blobDnsZoneGroup"
    }
    cosmos = {
      enabled    = var.deployCosmosDb, target = local.data_context.cosmos.id
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.resource_names.dbAccountName}"
      connection = "cosmosConnection", subnet = "applicationPe", groups = ["Sql"], zones = ["Cosmos"], zone_group = "cosmosDnsZoneGroup"
    }
    search = {
      enabled    = var.deploySearchService, target = local.data_context.search.id
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.resource_names.searchServiceName}"
      connection = "searchConnection", subnet = "pe", groups = ["searchService"], zones = ["Search"], zone_group = "searchDnsZoneGroup"
    }
    keyVault = {
      enabled    = var.deployKeyVault, target = local.data_context.key_vault.id
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.resource_names.keyVaultName}"
      connection = "kvConnection", subnet = "applicationPe", groups = ["vault"], zones = ["KeyVault"], zone_group = "kvDnsZoneGroup"
    }
    appConfig = {
      enabled    = var.deployAppConfig, target = local.data_context.app_config.id
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.resource_names.appConfigName}"
      connection = "appConfigConnection", subnet = "applicationPe", groups = ["configurationStores"], zones = ["AppConfig"], zone_group = "appConfigDnsZoneGroup"
    }
    containerApps = {
      enabled    = var.deployContainerEnv, target = local.compute_context.environment_id
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.resource_names.containerEnvName}"
      connection = "ccaConnection", subnet = "applicationPe", groups = ["managedEnvironments"], zones = ["ContainerApps"], zone_group = "ccaDnsZoneGroup"
    }
    acr = {
      enabled    = var.deployContainerRegistry, target = local.registry_context.id
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.resource_names.containerRegistryName}"
      connection = "${local.resource_names.containerRegistryName}-registry-connection", subnet = "applicationPe", groups = ["registry"], zones = ["Acr"], zone_group = "acrDnsZoneGroup"
    }
    speech = {
      enabled    = var.deploySpeechService, target = local.data_context.speech.id
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.resource_names.speechServiceName}"
      connection = "speechConnection", subnet = "pe", groups = ["account"], zones = ["CogSvcs"], zone_group = "cogSvcsDnsZoneGroup"
    }
    ampls = {
      enabled    = local.effective_observability.ampls, target = local.effective_observability.ampls ? terraform_data.network_ampls_ready[0].output.ampls_id : ""
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.network_abbreviations.networking.privateLinkScope}${local.resource_token}"
      connection = "azuremonitor", subnet = "applicationPe", groups = ["azuremonitor"], zones = ["AzureMonitor", "OmsOpsInsights", "OdsOpsInsights", "AzureAutomation"], zone_group = "default"
    }
  }
  network_foundry_endpoint_specs = {
    foundrySearch = {
      enabled    = var.deployAiFoundry && var.deployAAfAgentSvc && var.aiSearchResourceId == "", target = local.foundry_dependencies.search_id
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.resource_names.aiFoundrySearchServiceName}"
      connection = "searchAIFConnection", subnet = "pe", groups = ["searchService"], zones = ["Search"], zone_group = "searchDnsZoneGroup"
    }
    foundryStorage = {
      enabled    = var.deployAiFoundry && var.deployAAfAgentSvc && var.aiFoundryStorageAccountResourceId == "", target = local.foundry_dependencies.storage_id
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.resource_names.aiFoundryStorageAccountName}-blob"
      connection = "foundryBlobConnection", subnet = "pe", groups = ["blob"], zones = ["Blob"], zone_group = "default"
    }
    foundry = {
      enabled    = var.deployAiFoundry, target = var.deployAiFoundry ? terraform_data.network_foundry_ready[0].output.account_id : ""
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.resource_names.aiFoundryAccountName}-account"
      connection = "${local.network_abbreviations.networking.privateEndpoint}${local.resource_names.aiFoundryAccountName}-account", subnet = "pe", groups = ["account"], zones = ["CogSvcs", "OpenAi", "AiServices"], zone_group = "default"
    }
    foundryCosmos = {
      enabled    = var.deployAiFoundry && var.deployAAfAgentSvc && var.aiFoundryCosmosDBAccountResourceId == "", target = local.foundry_dependencies.cosmos_id
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.foundry_dependencies.cosmos_name}-sql"
      connection = "foundryCosmosConnection", subnet = "pe", groups = ["Sql"], zones = ["Cosmos"], zone_group = "default"
    }
    foundryKeyVault = {
      enabled    = var.deployAiFoundry && var.deployAAfAgentSvc && var.keyVaultResourceId == "", target = local.foundry_dependencies.vault_id
      name       = "${local.network_abbreviations.networking.privateEndpoint}${local.foundry_dependencies.vault_name}-vault"
      connection = "foundryVaultConnection", subnet = "pe", groups = ["vault"], zones = ["KeyVault"], zone_group = "default"
    }
  }
  network_application_private_endpoints = {
    for key, endpoint in local.network_application_endpoint_specs : key => {
      name               = endpoint.name
      connection_name    = "${endpoint.connection}${var.useExistingVNet && !contains(["containerApps", "acr"], key) ? "-byon" : ""}"
      target_resource_id = endpoint.target
      group_ids          = endpoint.groups
      subnet_purpose     = endpoint.subnet
      subnet_id          = local.subnet_ids[endpoint.subnet]
      dns_zone_ids       = var.policyManagedPrivateDns ? [] : [for zone in endpoint.zones : local.private_dns_zone_ids[zone]]
      dns_zone_group     = endpoint.zone_group
      location           = local.effective_locations.private_endpoint
      subscription       = local.network_pe_sub
      resource_group     = local.network_pe_rg
    } if var.networkIsolation && endpoint.enabled
  }
  network_foundry_private_endpoints = {
    for key, endpoint in local.network_foundry_endpoint_specs : key => {
      name               = endpoint.name
      connection_name    = "${endpoint.connection}${var.useExistingVNet && !contains(["containerApps", "acr", "foundry"], key) ? "-byon" : ""}"
      target_resource_id = endpoint.target
      group_ids          = endpoint.groups
      subnet_purpose     = endpoint.subnet
      subnet_id          = local.subnet_ids[endpoint.subnet]
      dns_zone_ids       = var.policyManagedPrivateDns ? [] : [for zone in endpoint.zones : local.private_dns_zone_ids[zone]]
      dns_zone_group     = endpoint.zone_group
      location           = local.effective_locations.private_endpoint
      subscription       = local.network_pe_sub
      resource_group     = local.network_pe_rg
    } if var.networkIsolation && endpoint.enabled
  }
  # Aggregates are output/metadata contracts only, never resource inputs for
  # either collection or prerequisites of Foundry resource producers.
  network_endpoint_specs = merge(local.network_application_endpoint_specs, local.network_foundry_endpoint_specs)
  private_endpoints      = merge(local.network_application_private_endpoints, local.network_foundry_private_endpoints)
}

# AzAPI is deliberate here: service AVMs' nested endpoints couple resource
# creation to endpoint creation and cannot share this cross-service VNet lock.
resource "azapi_resource" "network_private_endpoint" {
  for_each  = local.network_application_private_endpoints
  type      = "Microsoft.Network/privateEndpoints@2024-07-01"
  parent_id = "/subscriptions/${each.value.subscription}/resourceGroups/${each.value.resource_group}"
  name      = each.value.name
  location  = each.value.location
  tags      = local.deployment_context.tags
  body = {
    properties = {
      customNetworkInterfaceName = "nic-${each.value.name}"
      subnet                     = { id = each.value.subnet_id }
      privateLinkServiceConnections = [{
        name = each.value.connection_name
        properties = {
          privateLinkServiceId = each.value.target_resource_id
          groupIds             = each.value.group_ids
        }
      }]
    }
  }
  locks = [local.network_vnet_id]
  retry = {
    error_message_regex = ["AnotherOperationInProgress", "ReferencedResourceNotProvisioned"]
  }
  response_export_values = ["properties.customDnsConfigs", "properties.networkInterfaces"]
  depends_on             = [terraform_data.network_contract, module.network_subnet, module.network_private_dns]
}

resource "azapi_resource" "network_endpoint_dns" {
  for_each  = { for key, endpoint in local.network_application_private_endpoints : key => endpoint if !var.policyManagedPrivateDns }
  type      = "Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-07-01"
  parent_id = azapi_resource.network_private_endpoint[each.key].id
  name      = each.value.dns_zone_group
  body = {
    properties = {
      privateDnsZoneConfigs = [
        for i, id in each.value.dns_zone_ids : { name = "zone-${i}", properties = { privateDnsZoneId = id } }
      ]
    }
  }
  locks = [local.network_vnet_id]
}

# A separate resource collection is required for Foundry connectivity:
# capability hosts/project connections wait for these completed PEs and DNS
# groups, without waiting for ACA, ACR, AMPLS or application endpoint producers.
resource "azapi_resource" "network_foundry_private_endpoint" {
  for_each  = local.network_foundry_private_endpoints
  type      = "Microsoft.Network/privateEndpoints@2024-07-01"
  parent_id = "/subscriptions/${each.value.subscription}/resourceGroups/${each.value.resource_group}"
  name      = each.value.name
  location  = each.value.location
  tags      = local.deployment_context.tags
  body = {
    properties = {
      customNetworkInterfaceName = "nic-${each.value.name}"
      subnet                     = { id = each.value.subnet_id }
      privateLinkServiceConnections = [{
        name = each.value.connection_name
        properties = {
          privateLinkServiceId = each.value.target_resource_id
          groupIds             = each.value.group_ids
        }
      }]
    }
  }
  locks = [local.network_vnet_id]
  retry = {
    error_message_regex = ["AnotherOperationInProgress", "ReferencedResourceNotProvisioned"]
  }
  response_export_values = ["properties.customDnsConfigs", "properties.networkInterfaces"]
  depends_on             = [terraform_data.network_contract, module.network_subnet, module.network_private_dns]
}

resource "azapi_resource" "network_foundry_endpoint_dns" {
  for_each  = { for key, endpoint in local.network_foundry_private_endpoints : key => endpoint if !var.policyManagedPrivateDns }
  type      = "Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-07-01"
  parent_id = azapi_resource.network_foundry_private_endpoint[each.key].id
  name      = each.value.dns_zone_group
  body = {
    properties = {
      privateDnsZoneConfigs = [
        for i, id in each.value.dns_zone_ids : { name = "zone-${i}", properties = { privateDnsZoneId = id } }
      ]
    }
  }
  locks = [local.network_vnet_id]
}

locals {
  # Completion IDs, not endpoint descriptors/constructed ARM IDs. Policy-owned
  # DNS contributes no local DNS-group ID; BYO dependencies contribute no owned
  # endpoint ID. Their private connectivity remains an external prerequisite.
  # Do not place this in subnet_ids, network_context or Foundry producer locals.
  foundry_private_connectivity_ready = concat(
    [for endpoint in azapi_resource.network_foundry_private_endpoint : endpoint.id],
    [for zone_group in azapi_resource.network_foundry_endpoint_dns : zone_group.id]
  )
  network_completed_private_endpoints = merge(
    azapi_resource.network_private_endpoint,
    azapi_resource.network_foundry_private_endpoint
  )
}

resource "azapi_resource" "network_firewall_diagnostics" {
  count     = local.network_firewall && (local.effective_observability.create_law || trimspace(coalesce(var.existingLogAnalyticsWorkspaceResourceId, " ")) != "") ? 1 : 0
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  parent_id = module.network_firewall[0].resource_id
  name      = "fw-diagnostics"
  body = {
    properties = {
      workspaceId = local.effective_observability.law_id
      logs        = [{ categoryGroup = "allLogs", enabled = true }]
      metrics     = [{ category = "AllMetrics", enabled = true }]
    }
  }
}

locals {
  # This object is safe for resource producers to consume. Do not add endpoint
  # or Application Gateway outputs here: doing so creates cross-service cycles.
  network_context = {
    vnet_id             = local.network_vnet_id
    vnet_subscription   = local.network_vnet_sub
    vnet_rg             = local.network_vnet_rg
    vnet_name           = local.network_vnet_name
    pe_subscription     = local.network_pe_sub
    pe_rg               = local.network_pe_rg
    pe_rg_id            = "/subscriptions/${local.network_pe_sub}/resourceGroups/${local.network_pe_rg}"
    dns_subscription    = local.network_dns_sub
    dns_rg              = local.network_dns_rg
    route_table_id      = trimspace(local.network_route_id)
    nat_gateway_id      = local.network_nat_id
    bastion_id          = local.effective_flags.bastion ? module.network_bastion[0].resource_id : (var.existingBastionResourceId == null ? "" : var.existingBastionResourceId)
    firewall_policy_id  = local.network_firewall ? module.network_firewall_policy[0].resource_id : ""
    firewall_private_ip = local.network_firewall ? module.network_firewall[0].resource.ip_configuration[0].private_ip_address : ""
    # Compute uses this for ACA shell/ACR pool ordering, never all endpoints.
    egress_ready = concat([for route in azapi_resource.network_default_route : route.id], [for group in azapi_resource.network_firewall_rules : group.id])
  }
  network_private_metadata = {
    endpoint_ids = { for key, endpoint in local.network_completed_private_endpoints : key => endpoint.id }
    endpoints = {
      for key, endpoint in local.private_endpoints : key => {
        id                 = local.network_completed_private_endpoints[key].id, subnet_id = endpoint.subnet_id
        target_resource_id = endpoint.target_resource_id, group_ids = endpoint.group_ids
        dns_zone_ids       = endpoint.dns_zone_ids
        custom_dns_configs = try(local.network_completed_private_endpoints[key].output.properties.customDnsConfigs, [])
        network_interface_ids = [
          for nic in try(local.network_completed_private_endpoints[key].output.properties.networkInterfaces, []) : nic.id
        ]
      }
    }

  }
}

locals {
  network_ingress_prefix = "${local.network_abbreviations.networking.applicationGateway}${local.resource_token}"
  network_ingress_backend = try(
    local.compute_context.apps[var.containerAppsList[var.publicIngress.backendAppIndex].service_name].fqdn,
    null
  )
  # AzureRM's SSL-policy expansion omits minimum TLS/cipher fields for
  # Predefined policies; retain the verified AVM rather than duplicating it.
  network_ingress_ssl_policy = try(length(keys(var.publicIngress.sslPolicy)), 0) == 0 ? null : {
    cipher_suites        = try(var.publicIngress.sslPolicy.cipherSuites, null)
    disabled_protocols   = try(var.publicIngress.sslPolicy.disabledSslProtocols, null)
    min_protocol_version = try(var.publicIngress.sslPolicy.minProtocolVersion, null)
    policy_name          = try(var.publicIngress.sslPolicy.policyName, null)
    policy_type          = try(var.publicIngress.sslPolicy.policyType, null)
  }
}

# Keep identity creation separate from gateway creation so the identity worker
# can grant certificate access without a Gateway -> RBAC -> Gateway cycle.
resource "azurerm_user_assigned_identity" "network_ingress" {
  count               = local.effective_flags.public_ingress ? 1 : 0
  name                = "${local.network_ingress_prefix}-id"
  resource_group_name = local.deployment_context.application_rg
  location            = local.effective_locations.main
  tags                = local.deployment_context.tags
  depends_on          = [terraform_data.network_contract]
}

locals {
  network_ingress_identity = {
    resource_id  = local.effective_flags.public_ingress ? azurerm_user_assigned_identity.network_ingress[0].id : ""
    principal_id = local.effective_flags.public_ingress ? azurerm_user_assigned_identity.network_ingress[0].principal_id : ""
  }
}

# WAF AVM 0.2.0 was verified: its typed custom_rules schema cannot pass the
# full ARM custom rule subtree (notably groupByUserSession). Preserve the
# supported opaque Bicep option rather than silently dropping these properties.
resource "azapi_resource" "network_ingress_waf" {
  count     = local.effective_flags.public_ingress ? 1 : 0
  type      = "Microsoft.Network/ApplicationGatewayWebApplicationFirewallPolicies@2024-07-01"
  parent_id = local.deployment_context.application_rg_id
  name      = "${local.network_ingress_prefix}-waf"
  location  = local.effective_locations.main
  tags      = local.deployment_context.tags
  body = {
    properties = {
      policySettings = {
        state                  = "Enabled", mode = var.publicIngress.wafMode, requestBodyCheck = true
        maxRequestBodySizeInKb = 128, fileUploadLimitInMb = 100
      }
      customRules = var.publicIngress.wafCustomRules
      managedRules = {
        managedRuleSets = [{ ruleSetType = "OWASP", ruleSetVersion = "3.2" }]
      }
    }
  }
}

# Identity worker exports the actual completed certificate grant IDs, not
# assignment intents. Empty is valid only when no landing-zone vault is used.
resource "terraform_data" "network_ingress_authorization" {
  count = local.effective_flags.public_ingress ? 1 : 0
  input = local.network_ingress_role_assignment_ids
}

module "network_ingress" {
  source              = "Azure/avm-res-network-applicationgateway/azurerm"
  version             = "0.4.2"
  count               = local.effective_flags.public_ingress ? 1 : 0
  name                = "${local.network_ingress_prefix}-agw"
  location            = local.effective_locations.main
  resource_group_name = local.deployment_context.application_rg
  enable_telemetry    = false
  tags                = local.deployment_context.tags
  zones               = var.useZoneRedundancy ? ["1", "2", "3"] : []
  sku                 = { name = "WAF_v2", tier = "WAF_v2" }
  autoscale_configuration = {
    min_capacity = var.publicIngress.capacity.minCapacity
    max_capacity = var.publicIngress.capacity.maxCapacity
  }
  http2_enable                          = true
  app_gateway_waf_policy_resource_id    = azapi_resource.network_ingress_waf[0].id
  create_public_ip                      = false
  public_ip_resource_id                 = module.network_public_ip["ingress"].resource_id
  frontend_ip_configuration_public_name = "frontend-public"
  gateway_ip_configuration              = { name = "gateway-ip-config", subnet_id = local.subnet_ids.appGateway }
  managed_identities                    = { user_assigned_resource_ids = [local.network_ingress_identity.resource_id] }
  frontend_ports = merge(
    { http = { name = "port_80", port = 80 } },
    local.network_ingress_live ? { https = { name = "port_443", port = 443 } } : {}
  )
  backend_address_pools = {
    aca = { name = "aca-backend", fqdns = [local.network_ingress_backend] }
  }
  backend_http_settings = {
    aca = {
      name                                = "aca-https", port = 443, protocol = "Https", cookie_based_affinity = "Disabled"
      pick_host_name_from_backend_address = true, request_timeout = 30, probe_name = "aca-probe"
    }
  }
  probe_configurations = {
    aca = {
      name                                      = "aca-probe", protocol = "Https", path = "/", port = 443
      interval                                  = 30, timeout = 30, unhealthy_threshold = 3
      pick_host_name_from_backend_http_settings = true
      match                                     = { status_code = ["200-499"] }
    }
  }
  ssl_certificates = local.network_ingress_live ? {
    tls = { name = "tlsCert", key_vault_secret_id = var.publicIngress.sslCertSecretId }
  } : {}
  ssl_policy = local.network_ingress_ssl_policy
  http_listeners = merge({
    http = { name = "http-listener", frontend_port_name = "port_80", frontend_ip_configuration_name = "frontend-public", require_sni = false }
    }, local.network_ingress_live ? {
    https = {
      name        = "https-listener", frontend_port_name = "port_443", frontend_ip_configuration_name = "frontend-public"
      require_sni = true, host_name = var.publicIngress.frontendHostName, ssl_certificate_name = "tlsCert"
    }
  } : {})
  redirect_configuration = local.network_ingress_live ? {
    https = { name = "http-to-https", redirect_type = "Permanent", target_listener_name = "https-listener", include_path = true, include_query_string = true }
  } : {}
  request_routing_rules = merge({
    http = {
      name                        = local.network_ingress_live ? "http-redirect-rule" : "http-rule", rule_type = "Basic", priority = 100
      http_listener_name          = "http-listener"
      backend_address_pool_name   = local.network_ingress_live ? null : "aca-backend"
      backend_http_settings_name  = local.network_ingress_live ? null : "aca-https"
      redirect_configuration_name = local.network_ingress_live ? "http-to-https" : null
    }
    }, local.network_ingress_live ? {
    https = {
      name                      = "https-rule", rule_type = "Basic", priority = 110, http_listener_name = "https-listener"
      backend_address_pool_name = "aca-backend", backend_http_settings_name = "aca-https"
    }
  } : {})
  diagnostic_settings = local.effective_observability.create_law || trimspace(coalesce(var.existingLogAnalyticsWorkspaceResourceId, " ")) != "" ? {
    law = { name = "diag-${local.network_ingress_prefix}-agw", workspace_resource_id = local.effective_observability.law_id }
  } : {}
  depends_on = [terraform_data.network_ingress_authorization]
}

locals {
  network_ingress_context = {
    enabled                = local.effective_flags.public_ingress
    live_mode              = local.effective_flags.public_ingress && local.network_ingress_live
    public_ip              = local.effective_flags.public_ingress ? module.network_public_ip["ingress"].public_ip_address : ""
    public_ip_resource_id  = local.effective_flags.public_ingress ? module.network_public_ip["ingress"].resource_id : ""
    gateway_resource_id    = local.effective_flags.public_ingress ? module.network_ingress[0].resource_id : ""
    gateway_name           = local.effective_flags.public_ingress ? "${local.network_ingress_prefix}-agw" : ""
    nsg_resource_id        = local.effective_flags.public_ingress ? azapi_resource.network_nsg["appGateway"].id : ""
    waf_policy_resource_id = local.effective_flags.public_ingress ? azapi_resource.network_ingress_waf[0].id : ""
    identity_resource_id   = local.network_ingress_identity.resource_id
    identity_principal_id  = local.network_ingress_identity.principal_id
  }
}
