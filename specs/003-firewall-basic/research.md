# Research: Basic firewall for new deployments

## 1. Topology and creation defaults

**Decision:** Default new standalone deployments to Basic, support explicit
Standard, omit local firewall resources for external hub egress, and make
GatewaySubnet opt-in.

**Rationale:** Hub firewall ownership is independent of gateway transit.
Firewall subnet auto defaults should follow local resource requirements.
Explicit data/gateway reservation remains available without deploying services.

The inspected input file defaults both data-firewall and gateway subnet flags
to true. Bicep binds their creation directly to the flags; selection filters
isolation/global/individual creation rather than service use. Terraform follows
the same input model. The planned auto/default rules remove unused reservations.

**Alternatives:** Keep Standard as the default with optional Basic: technically
viable, but does not deliver the requested lower-cost default. Disable resources
solely from a hub ID: rejected because peering does not establish approved egress.

## 2. Shared input semantics

**Decision:** Use equivalent defaults in native templates and shared preparation.
Basic/Standard is an enum; firewall subnet creation uses auto/nullable boolean;
GatewaySubnet defaults false. Persist the resolved azd input set.

**Rationale:** One explicit contract avoids divergent defaults among providers
and hook variants. False disables creation but does not satisfy a consumer's
subnet requirement: require validated BYO or fail. Management dependencies
remain conditional on active standalone Basic.

**Alternatives:** Independently infer behavior in every hook/provider: duplicates
logic. Ignore false for a required subnet: overrides operator ownership intent.

## 3. Pinned Terraform interfaces

**Decision:** Retain firewall AVM 0.4.0, policy AVM 0.3.3 and the provider lock.

The registry download endpoint for firewall 0.4.0 resolves to commit
`afb64c30508354ec414b0b6194f4380be58a8b09`; its tag is `0.4.0`.
Verified inputs:

```text
firewall_sku_tier: string, including Basic
firewall_management_ip_configuration: nullable object
  name: string
  public_ip_address_id: string
  subnet_id: string
```

The module emits management configuration only for a non-null input. Policy
0.3.3 exposes Basic `firewall_policy_sku` and nullable `firewall_policy_dns`;
null omits the DNS block. Interface support is not live Azure acceptance.

Sources:

- [Registry metadata](https://registry.terraform.io/v1/modules/Azure/avm-res-network-azurefirewall/azurerm/0.4.0/download)
- [Pinned firewall variables](https://github.com/Azure/terraform-azurerm-avm-res-network-azurefirewall/blob/afb64c30508354ec414b0b6194f4380be58a8b09/variables.tf)
- [Pinned firewall rendering](https://github.com/Azure/terraform-azurerm-avm-res-network-azurefirewall/blob/afb64c30508354ec414b0b6194f4380be58a8b09/main.tf)
- [Policy variables](https://github.com/Azure/terraform-azurerm-avm-res-network-firewallpolicy/blob/v0.3.3/variables.tf)
- [Policy rendering](https://github.com/Azure/terraform-azurerm-avm-res-network-firewallpolicy/blob/v0.3.3/main.tf)

## 4. Management topology and DNS

**Decision:** Add Basic management subnet/IP/NIC together; proposed subnet
`192.168.3.192/26`, without moving declared workload ranges. Omit Basic DNS
policy configuration and reject proxy=true.

**Rationale:** Basic requires a management NIC, a separate public IP and a
management subnet of at least /26. Management routing must allow the documented
platform path rather than inherit workload UDRs. BYO routing needs validation.
The generic NSG exclusion list also needs the management subnet.

The proposed /26 fits the /21 without overlapping declared ranges. Custom
address plans must be checked. Basic supports the inspected HTTP(S) application
FQDN and IP/service-tag rule types, but not firewall DNS proxy or network-rule
FQDN filtering. The VPN runbook already uses a forwarder/Private Resolver path.

**Alternatives:** Silently disable DNS proxy: rejected. Automatically add a
resolver: adds a paid service outside scope. Apply generic workload UDR/NSG:
does not respect the management subnet's service requirements.

Sources:

- [Management NIC](https://learn.microsoft.com/en-us/azure/firewall/management-nic)
- [SKU features](https://learn.microsoft.com/en-us/azure/firewall/features-by-sku)
- [ARM API](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2024-07-01/azurefirewalls)
- [VPN DNS procedure](https://github.com/Azure/AI-Landing-Zones/blob/main/docs/agent-landing-zone/private-access.md#3-connect-dns-and-routes)

## 5. Acceptance

**Decision:** Verify creation/absence and policy wiring offline, then qualify
both providers in separately authorized disposable deployments.

**Rationale:** Template/provider interface checks do not prove actual identity,
ACR builds, hosted runtime, denial/logging or capacity. Basic's approximately
250 Mbps class must be assessed against build/image/ingestion peaks, not chat
count alone.

**Alternatives:** Accept a successful compile or TCP handshake as proof:
insufficient to establish intended application traffic and blocking.

Source:
[Container Apps firewall integration](https://learn.microsoft.com/en-us/azure/container-apps/use-azure-firewall).

## Status

Design inputs are resolved. Live service acceptance and capacity remain explicit
execution gates. No Azure resource or infrastructure implementation was changed
while preparing this plan.
