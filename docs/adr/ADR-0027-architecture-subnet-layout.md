# ADR-0027: Explicit architecture subnet layout and creation ownership

**Status:** Accepted<br>
**Date:** 2026-10-27<br>
**Owners:** Agent Landing Zone maintainers<br>
**Approver:** Paulo (maintainer)

## Context

The networking diagram separates application and Foundry private endpoints and
reserves delegated subnets for Power Platform and AI Gateway. The template
instead shares private endpoints by default, omits both delegated reservations,
and uses a non-reserved VPN gateway subnet name. New and existing VNet paths
also differ in their treatment of the global subnet creation switch.

Prioritized characteristics are predictable defaults (twelve isolated-network
subnets), explicit ownership (one creation switch per subnet), valid platform
constraints (names, delegation, sizing and NSGs), configurable addressing, and
preserved private endpoint authorization and DNS boundaries.

## Alternatives considered

### Individual creation switches with a common subnet definition list

Explicit Boolean parameters fit the existing deployment interface and allow
omitting unused reservations or reusing platform-owned subnets. The cost is a
larger parameter surface and consumer-aware validation. Names and CIDRs remain
configurable; identity and service deployment flags stay independent.

### Generic caller-supplied topology object

A generic object is extensible but exposes service-sensitive properties and
requires operators to reconstruct the supported layout. It increases validation
and compatibility burden without an immediate requirement for arbitrary roles.

### Do not change

This preserves existing allocations but leaves the diagram inconsistent with
the template and keeps application private endpoints shared by default.

## Decision

Use twelve default subnet definitions when network isolation is enabled.
Preserve existing address allocations and the Foundry `pe-subnet` name. Add
`application-pe-subnet` at `192.168.3.128/26`, `powerplatform-subnet` at
`192.168.4.0/24`, and `ai-gateway-subnet` at `192.168.5.0/24`. Use the reserved
`GatewaySubnet` name without NSG, default-route UDR, or delegation.

Delegate Power Platform to `Microsoft.PowerPlatform/enterprisePolicies`. Its
/24 is a configurable capacity default, not a universal platform minimum.
Delegate AI Gateway to `Microsoft.Web/serverFarms` for APIM Standard v2/Premium
v2 outbound integration, requiring an NSG and at least /27. The /24 default
provides scaling capacity. It is not a private endpoint subnet.

Expose individual creation switches defaulting to true, subordinate to the
global `deploySubnets` and network isolation switches. Apply the same selection
in both ownership paths; update existing VNets only through serialized subnet
child deployments. Never replace their entire subnet collection.

Not creating a subnet does not disable a service. Enabled consumers require a
valid existing subnet or a managed creation. Application private endpoints
never silently fall back to the Foundry subnet. Preserve the existing
`deployAiFoundrySubnet` association control independently of creation ownership.
Reject missing prerequisites explicitly and retain existing BYO NSG safeguards.

Prepare subnets only. APIM, VPN/ExpressRoute gateways, Power Platform enterprise
policy and environment association are outside this change. Runtime component
versions, managed identities, document authorization and service RBAC do not
change. Preparing a reservation must not provision a billable consuming service.

## Consequences

The default topology matches the diagram and supports customized CIDRs and
individual opt-outs. The larger parameter surface requires consistent root
bindings, composition, preflight checks and compiled contracts.

Additional provider registrations and subnet delegations may require scoped
operator permissions. No subscription-wide role grants are added. Delegation
does not imply a functioning service integration or compatible geographic
pairing for Power Platform.

## Adoption and migration

Ship templates, parameter bindings, validation and central documentation as a
coordinated change. Do not automatically rename occupied subnets, move existing
private endpoints, or change reused VNet address spaces. Explicit operator
configuration must be evaluated against actual existing network properties.

Creation flags are ownership controls, not deletion commands. Updating a
deployment-owned VNet's submitted subnet collection can remove unused subnets
or be rejected for occupied subnets. Reverting templates is not a safe automatic
rollback after allocations or endpoint placement change; retain the validated
network layout and roll forward, or review Azure what-if and resource
dependencies before changing it.

## Compliance verification

Compile and test all twelve defaults, custom addressing, every individual
opt-out, global precedence, public mode, both VNet paths, required reused
subnets, invalid CIDRs/names, NSG/delegation requirements and dedicated PE
destinations. Preserve serialized BYO writes, actual cross-subscription IDs,
ACR Tasks ordering and existing resource-group/DNS boundaries. Offline evidence
must not be represented as a live Azure service integration test.

## Documentation impact

Update the central `Azure/AI-Landing-Zones` subnet configuration and network
pages and directly affected existing runbook references. Describe supported
behavior directly without release-comparison blocks or new service procedures.

## Review trigger

Reassess when APIM integration mode changes, Power Platform sizing/delegation
requirements change, or a request requires arbitrary subnet roles or automated
network migration.
