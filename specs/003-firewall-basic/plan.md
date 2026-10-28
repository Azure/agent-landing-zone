# Implementation Plan: Basic firewall and topology-aware subnets

**Branch:** `feature/firewall-basic`  
**Date:** 2026-10-28  
**Spec:** [spec.md](spec.md)  
**Decision:** [ADR-0031](../../docs/adr/ADR-0031-standalone-basic-firewall.md)

## Summary and scope

Implement Basic as the default firewall for new isolated standalone Agent
Landing Zone deployments, with Standard selectable. Provision all required
Basic dependencies and create firewall/gateway subnets according to the
selected topology and explicit reservation choices.

This plan covers new deployments only. BYO networking remains supported with
explicit ownership and validation. Hub resources are externally owned.
Implementation is complete. Live Azure qualification has not been performed.

## Resource matrix

| New deployment | Local data subnet/IP | Local management subnet/IP/NIC | Local GatewaySubnet |
| --- | --- | --- | --- |
| Isolated standalone Basic | Required | Required | Explicit reservation only |
| Isolated standalone Standard | Required | None | Explicit reservation only |
| External hub, with/without gateway | No firewall IP; no data subnet by default | None | Explicit local reservation only |
| Public/non-isolated | None | None | None |

`AzureFirewallSubnet` serves the data plane for both local SKUs.
`AzureFirewallManagementSubnet` is required only for standalone Basic in this
feature. A deliberate data-subnet reservation can be requested without a local
firewall. Reserving GatewaySubnet never provisions a VPN Gateway.

## Technical Context

**Languages:** Bicep; Terraform 1.13 in CI; Python shared input preparation;
PowerShell 7 and shell lifecycle hooks.  
**Dependencies:** Network ARM API `2024-07-01`; pinned Terraform firewall AVM
0.4.0, policy AVM 0.3.3, VNet/subnet modules and provider lock.  
**Storage:** azd deployment inputs and Terraform state; no runtime setting.  
**Testing:** pytest, PowerShell offline/preflight contracts, Bicep compile/lint,
Terraform mock plans and separately authorized Azure acceptance.  
**Platform:** Azure VNet-based firewall, standalone or external hub/spoke.  
**Performance:** Qualify the Basic capacity class, approximately 250 Mbps,
including image/build/ingestion peaks and SNAT pressure.  
**Constraints:** Preserve egress enforcement, explicit resource ownership,
identity/RBAC, private DNS and the 64-output contract.  
**Scope:** Platform and central `Azure/AI-Landing-Zones` product documentation;
no runtime component changes or release publication.

## Constitution Check

| Gate | Before research | After design |
| --- | --- | --- |
| Foundation/application boundary | Foundation networking only | No runtime implementation or data change |
| Explicit contracts | New deployment input/ownership matrix defined | Same defaults and input semantics in both providers |
| Identity/privacy | No additional application permission | Hub/BYO resources remain externally owned |
| Observable failures | No silent fallback | Invalid DNS/subnet/ownership inputs stop before writes |
| Evidence | Observable acceptance scenarios defined | Offline and live evidence separated |
| Bidirectional parity | Both providers in scope | Inputs, topology, dependencies and lifecycle compared |
| Architectural decision | Required before implementation | Accepted ADR recorded |

No constitution exceptions are proposed. API acceptance and measured capacity
remain execution gates; planning does not establish deployed Azure parity.

## Project Structure

Planning outputs: `spec.md`, `research.md`, `data-model.md`,
`contracts/firewall-inputs.md`, `quickstart.md`, this plan and ADR-0031.
Task-generation artifacts are outside this planning phase.

| Area | Implementation surfaces |
| --- | --- |
| Inputs | `main.parameters.json`, seed `infra/main.parameters.json` |
| Shared preparation | `config/deployment/input_types.py`, composition/preparation path, `terraform_inputs.py` |
| Lifecycle | `scripts/preProvision.ps1`, `scripts/preProvision.sh` |
| Bicep | `infra/main.bicep`, networking firewall/subnet modules, subnet validation module |
| Terraform | `infra/terraform/variables.tf`, `main.networking.tf` |
| Preflight | `infra/scripts/Invoke-PreflightChecks.ps1` and affected shared checks |
| Tests | Subnet, input-interface, DNS proxy, build/runtime egress and hook contracts |
| Docs | Central planning, configuration, network isolation, VPN, costs and impacted diagrams/inventory |

Keep resource bodies in the networking modules/domain and reuse typed shared
input preparation rather than separate provider-specific deployment logic.

## Implementation sequence

### 1. Define inputs and effective creation rules

- Introduce `azureFirewallSku` / `AZURE_FIREWALL_SKU`, Basic by default with
  Standard selectable. Firewall and policy always use the same value.
- Set equivalent defaults in both native templates and product input rendering.
- For firewall subnet creation, distinguish absent/auto from explicit true/false.
  Auto follows the local service requirement; explicit false requires a valid
  BYO subnet when a consumer needs it. Never silently force creation on.
- Create the data subnet by default for a local firewall, not external hub
  egress. Permit an explicit data-subnet reservation.
- Create/select management dependencies only for standalone local isolated
  Basic. Reject integrated local Basic instead of omitting required dependencies.
- Set `deployGatewaySubnet=false` by default, including standalone. Explicit
  opt-in reserves only the subnet for a separately configured local gateway.
- Keep local/external routing mutexes and explicit ownership inputs. A topology
  label or hub ID alone does not configure approved external egress.

### 2. Implement Bicep dependencies

- Add management-subnet name/prefix/creation inputs. Proposed default:
  `AzureFirewallManagementSubnet`, `192.168.3.192/26`.
- Validate the reserved name, IPv4 alignment, /26-or-larger size, VNet
  containment, unique names and non-overlap. Keep declared workload ranges.
- Add a deterministic Standard/static IPv4 management public IP and
  `properties.managementIpConfiguration` referencing that IP and subnet.
- Do not attach generic NSGs, workload UDRs, NAT, delegations or service
  endpoints to the management subnet. Update reserved-subnet handling for
  managed and BYO VNet paths.
- Set firewall and policy SKU together; omit unsupported DNS policy
  configuration for Basic.
- Retain source-scoped platform/build/media/application rules, serialized policy
  writes and diagnostics. Workload UDRs keep the data-plane private next hop.

### 3. Implement equivalent Terraform composition

- Add the same typed inputs, auto/default semantics and blocking validations.
- Extend subnet definitions, ownership/association maps and preconditions.
- Add the Basic-only management public IP with the same intended zone policy
  as the data public IP.
- Retain pinned AVMs and the provider lock. Set
  `firewall_management_ip_configuration` only for Basic; use matching
  `firewall_sku_tier` and `firewall_policy_sku`.
- Pass `firewall_policy_dns=null` for Basic and preserve selectable Standard DNS
  proxy behavior.
- Avoid subnet/firewall dependency cycles. BYO resources remain lookups;
  teardown owns only deployment-created resources.

### 4. Complete shared lifecycle and validation

- Resolve one effective input set before either provider runs; persist choices
  through the azd environment and propagate them in both hook variants.
- Reject Basic plus DNS proxy and missing/invalid required subnets. Enforce
  static restrictions at provider boundaries as well as shared preflight.
- Validate BYO management routing and placement. Do not silently rewrite
  network-team-owned associations.
- Keep public outputs and runtime App Configuration unchanged unless an actual
  downstream need is demonstrated.
- Preserve external-policy report-only egress and scoped managed reconciliation.

### 5. Verify behavior and parity

- Add positive and negative cases for the resource matrix and explicit
  reservations, including hub configurations with and without a gateway.
- Replace fixed subnet-count assertions with scenario-aware expectations.
- Verify exact SKU/policy/dependency wiring, absent versus explicit inputs,
  both hook paths, BYO ownership and repeat-provision stability.
- Retain protected-graph checks with narrowly reviewed topology projections;
  do not regenerate or broadly exempt security baselines.
- Assert absence of unused resources, not just presence of required ones.
- Run narrow tests, then the affected Bicep, Terraform and shared CI gates.
- With separate approval, qualify both providers in disposable Azure
  deployments: provisioning, ACR builds, selected runtime paths, allowed and
  denied traffic with logs, diagnostics, repeat provision and capacity.

### 6. Align documentation and delivery

- Update central configuration, planning, network isolation, cost planning and
  affected diagrams/inventories to describe the implemented resource matrix.
- Keep the VPN forwarder/Private Resolver design. Firewall-as-DNS requires
  explicit Standard.
- For the local-gateway VPN procedure, select `DEPLOY_GATEWAY_SUBNET=true`
  before provisioning. Do not require that reservation for a shared hub gateway.
- Keep product docs focused on the supported configuration and current behavior.
  Do not publish planned functionality as shipped.
- Deliver implementation on the feature branch targeting develop, with
  provider-specific evidence, doc changes and explicit unverified scenarios.
  Publication and production deployment are separate actions.

## Deployment and cleanup

Select topology and inputs before first provision. Review planned resource
ownership, provision the chosen foundation, and verify service traffic and
diagnostics. Repeated provisioning must retain the selected topology.

For an interrupted new deployment, inspect the created resources and retry with
the same inputs, or authorize cleanup of the exact deployment-owned resources.
Never delete shared hub/BYO subnets, policies, DNS or other shared services.

Reassess if live acceptance fails, measured demand exceeds Basic capacity,
Standard-only capabilities are required, or policy disallows the management IP.

## Planning completion

`.specify/extensions.yml` is absent, so no before/after-plan hooks apply.
Research, design and implementation artifacts are saved. Azure acceptance
remains unqualified; [quickstart.md](quickstart.md) lists the validation commands.
