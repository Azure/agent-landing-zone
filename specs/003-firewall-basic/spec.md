# Feature: Basic firewall and topology-aware subnets

**Issue:** #781  
**Date:** 2026-10-28  
**Scope:** New deployments only  
**Status:** Implemented; offline qualification recorded in the release evidence.
Live Azure provisioning and capacity qualification have not been performed.

## Outcome

Default new isolated standalone deployments to Azure Firewall Basic, keep
Standard selectable, and provision every required dependency in both Bicep and
Terraform. Create firewall/gateway subnets according to actual requirements or
an explicit reservation, rather than creating unused reservations by default.

Hub integration, with or without a hub gateway, uses the externally owned
firewall when external egress is configured. The spoke does not control hub SKU,
policy or subnets. Ownership flags and routing must be configured explicitly.

## Requirements

1. Use the same Basic/Standard selection, defaults and typed input contract in
   both native templates and shared azd preparation.
2. Resolve and persist a deterministic input set for repeated provisioning.
   Invalid or conflicting selections fail explicitly before writes.
3. Basic requires a matching Basic policy, a data-plane public IP, an additional
   Standard/static IPv4 management public IP, and a management NIC attached to
   `AzureFirewallManagementSubnet` of /26 or larger.
4. Expose management-subnet prefix and creation ownership. Proposed default:
   `192.168.3.192/26`, within the declared `192.168.0.0/21` VNet and without
   moving any declared workload subnet.
5. Create management dependencies only for standalone local isolated Basic.
   Reject integrated local Basic rather than partially provisioning it.
6. Distinguish auto/absent creation intent from explicit true/false. A required
   subnet with creation disabled must be validated as BYO or fail. An explicit
   data-subnet reservation does not deploy a firewall.
7. Exclude the management subnet from generic NSGs, workload UDRs, NAT,
   delegations and service endpoints. Validate BYO management routing.
8. Reject Basic with firewall DNS proxy enabled. Do not silently select
   Standard, disable proxy, rewrite client DNS or deploy a resolver. Omit
   unsupported DNS policy configuration for Basic.
9. Preserve source-scoped egress, serialized policy writes, default-deny,
   diagnostics and runtime-egress ownership.
10. External hub egress creates no local firewall, policy, management subnet or
    firewall IPs; the data subnet is absent unless explicitly reserved.
11. GatewaySubnet is opt-in in all new product deployments. A reservation
    creates no VPN Gateway and does not change gateway-transit settings.
12. Public/non-isolated mode creates none of these network resources.
13. Shared/BYO networking remains externally owned and is not deleted by the
    deployment's teardown.
14. Retain dependency pins, provider lock, runtime contracts, identity/RBAC and
    public output meanings. No runtime configuration key is added.
15. Update central documentation with the implemented behavior.

## Resource matrix

| New deployment | Data subnet/public IP | Management subnet/public IP | GatewaySubnet |
| --- | --- | --- | --- |
| Isolated standalone Basic | Required | Required | Explicit reservation only |
| Isolated standalone Standard | Required | None | Explicit reservation only |
| External hub, with/without gateway | No IP; subnet only if explicitly reserved | None | Explicit local reservation only |
| Public/non-isolated | None | None | None |

Both local SKUs need `AzureFirewallSubnet`. Only Basic needs management
resources in this feature. Standard forced tunneling is outside this scope.

## Acceptance

- Default standalone creates Basic with matching policy and both IP configs.
- Explicit Standard creates the Standard data-plane topology without management
  dependencies and can enable DNS proxy.
- External hub paths create no unintended local firewall/gateway reservations,
  with or without a hub gateway.
- Explicit data/gateway reservations create only requested subnets.
- Invalid SKU, DNS selection, CIDRs or required BYO subnets fail before writes.
- Public mode creates none of the scoped networking resources.
- Repeat provision is stable; provider teardown preserves shared/BYO resources.
- Allowed traffic works; a controlled unapproved destination is denied/logged.

## Scope boundary

Foundation networking, shared preparation/lifecycle and central documentation.
No new VPN gateway/resolver, Premium SKU, Standard forced tunneling, runtime
component changes, production deployment or unrelated subnet-default changes.

## Evidence boundary

Offline contracts establish intended input/resource behavior. Separately
authorized Azure deployments establish actual service connectivity, blocking,
diagnostics and performance. Chat volume alone is not bandwidth evidence.
