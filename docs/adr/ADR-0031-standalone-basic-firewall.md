# ADR-0031: Default new standalone deployments to Basic firewall

**Status:** Accepted<br>
**Date:** 2026-10-28<br>
**Owners:** Agent Landing Zone maintainers<br>
**Scope:** New deployments only

## Context

Issue #781 requests lower standalone firewall cost while retaining required
egress security. The maintainer requests Basic with its management subnet/IP,
Standard selection, and topology-aware firewall/gateway reservations.

The inspected foundation uses HTTP(S) application FQDN and IP/service-tag
network rules. DNS proxy is optional. Basic supports those rule types but not
firewall DNS proxy/network-rule FQDNs, has an approximately 250 Mbps capacity
class, and requires separate management subnet/IP/NIC.

Priorities:

1. Cost: Basic as the new standalone default.
2. Explicitness: matching native/provider defaults and reservation intent.
3. Isolation: retained source-scoped egress and authorization boundaries.
4. Ownership: no hub/BYO resource adoption or unintended local reservations.
5. Evidence: offline contracts plus authorized Azure qualification.

Affected repositories are this platform and central `Azure/AI-Landing-Zones`
documentation. Runtime component changes and release publication are outside
scope.

## Alternatives considered

### Option A: Standard default with explicit Basic option

Supports both SKUs and their capabilities with explicit dependency provisioning,
but keeps the higher fixed allocation as the standalone default.

### Option B: Basic default with explicit Standard and conditional dependencies

Meets the cost objective while retaining Standard for DNS proxy and other
requirements. Needs management subnet/IP/NIC, capacity qualification, typed auto
creation flags and consistent topology rules. Chosen.

### Do not change

Retains Standard-only support and independent default-on subnet reservations,
but does not meet the requested standalone cost and resource-selection outcome.

## Decision

Use option B for new deployments. Standalone Basic requires both data and
management networking; standalone Standard requires data networking only in
this feature. Hub egress creates no local firewall/IPs or management subnet,
regardless of whether the hub also supplies a gateway.

Default data-subnet creation to the local firewall requirement; support explicit
reservations. Default GatewaySubnet off in every new deployment, with explicit
opt-in for a local gateway. A reservation does not deploy a service.

Both native providers and shared preparation use the same effective contract.
Explicit false disables creation but requires validated BYO when a consumer
needs the subnet. Reject unsupported selections instead of silently changing
SKU, DNS or ownership intent.

Use proposed management prefix `192.168.3.192/26` without moving declared
workload ranges. Exclude management networking from generic NSGs, workload UDRs,
NAT and delegation. Reject Basic plus DNS proxy; omit its unsupported DNS
configuration. Keep rules, diagnostics, private endpoints and output meanings.

Retain the verified Terraform AVM pins and provider lock, which expose the
required interfaces. Hub/BYO policy and subnets remain outside spoke ownership.

## Consequences

### Positive

Lower fixed standalone allocation, explicit Standard selection, fewer unused
subnet reservations and equivalent provider behavior. No runtime setting or
application authorization change.

### Negative or accepted

Basic consumes a management /26-or-larger subnet and an extra public IP and
requires capacity qualification. DNS/policy requirements or public-IP rules can
make Standard the appropriate explicit choice.

## Delivery and cleanup

Implement typed inputs, shared hooks, provider resources and validation together,
then align central documentation with shipped behavior. Review plans before
provisioning; authorize Azure qualification separately.

If a new deployment is interrupted, inspect its exact resources before retrying
or authorizing scoped cleanup. Shared hub/BYO resources must remain untouched.
Repeated provisioning must retain the selected topology and rule ownership.

## Compliance verification

Assert Basic/Standard/local/external/public resource matrices, reservation
overrides, BYO validation, subnet boundaries and absence of unused resources.
Run Bicep, Terraform and shared hook tests. Retain protected-graph checks with
narrowly reviewed projections.

Separately qualify provisioning, builds/runtime, allowed/denied requests and
logs, diagnostics, repeat provision and capacity for both providers. Offline
checks do not establish deployed Azure parity.

## Documentation impact

Update central configuration, planning, networking, costs and affected
inventories/diagrams. The VPN DNS design retains its forwarder/resolver path;
firewall-as-DNS requires Standard. The local-gateway procedure explicitly
selects `DEPLOY_GATEWAY_SUBNET=true`; a hub gateway needs no local reservation.
Publish guidance only when it describes supported shipped behavior.

## Review trigger

Reassess if live acceptance fails, workload peaks exceed Basic capacity,
Standard-only features are required or management IP policy prevents Basic.
