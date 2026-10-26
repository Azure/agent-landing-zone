# ADR-0023: Configurable resource-group destinations with one provision flow

**Status:** Accepted for implementation<br>
**Date:** 2026-10-25<br>
**Owners:** Agent Landing Zone maintainers<br>
**Approver:** Paulo (maintainer)

## Context

Operators need separate ownership boundaries for Foundry and grounding, local
networking, and the application without being required to create three resource
groups (RGs). One, two, or three distinct destinations must work through a single
`azd provision`. The application RG remains the azd root, not a fourth control RG.
This decision is approved by the maintainer's implementation instruction; it is
not a claim that the feature is already shipped or live-validated.

The architecture discussion of 2026-10-23 and the updated architecture diagram
inform the boundaries. The diagram's XML pages were read as **Standalone**,
**Platform Hub**, and **AI Gateway + Platform Hub**. That evidence identifies
logical destinations, not an instruction to deploy every icon, build an external
hub, or require its two-private-endpoint-subnet layout. No private meeting URL or
local diagram path is part of this record.

The source baseline is `14b0861c438cc0b7df9a4881cb531b91bd3b9e45` from
`origin/develop`. Relevant executable evidence:

- `infra/main.bicep` is resource-group scoped. Naming uses the existing
  subscription/environment/location token, CAF selection, and explicit overrides.
  `privateEndpointResourceGroupName`, BYO resource IDs, `sideBySideDeploy`, and
  policy-managed DNS already affect network placement.
- Foundry has dedicated Agent Service Storage, Search, Cosmos DB, and Key Vault
  dependencies, distinct from the application Cosmos DB and Key Vault.
  The solution Storage account also contains both grounding documents and
  conversation-related containers; resource type alone cannot determine ownership.
- `azure.yaml` registers both implementations of `preprovision` and
  `postprovision`, but no `predown` guard. Both pre-provision scripts validate
  and bind the application definition before topology resolution and parameter
  composition.
- `config/deployment/hosted_access.py` currently binds both the Foundry project
  and application resources to the global RG. That validation must become
  destination-aware, not be removed.
- `contracts/platform-outputs-v1.schema.json` is closed, including nested
  objects (`additionalProperties: false`).

Affected repositories are `Azure/agent-landing-zone` (composition, incorporated
infrastructure, hooks, configurators, and contracts) and `Azure/AI-Landing-Zones`
(central product documentation). Review the equivalent infrastructure surfaces
in `Azure/bicep-ptn-aiml-landing-zone` and
`Azure/terraform-azurerm-avm-ptn-aiml-landing-zone` for coordinated adoption.
Runtime repositories are those in `manifest.json`; audit their pinned consumers
and change only consumers that actually depend on RG context. Do not duplicate
runtime code here or change pins without compatible-version evidence.

Prioritized characteristics and measures:

1. **Compatibility:** no-override resource names, enabled resources, lifecycle,
   network posture, and outputs remain equivalent to the single-RG baseline.
2. **Exact ownership and authorization:** every resource and grant uses its
   verified destination/ARM ID; no subscription deployment permission is added
   for ordinary deployments to existing RGs.
3. **Private connectivity:** all enabled services retain DNS/HTTPS connectivity
   and authorization across destinations, with zero public-access relaxation.
4. **Deterministic operation:** one provision flow, an acyclic dependency graph,
   consistent PowerShell/shell resolution, and idempotent partial-failure recovery.
5. **Safe reversibility:** a bound environment cannot silently change destinations;
   provisioning and failure recovery delete zero RGs or pre-existing resources.

## Alternatives considered

### Option A: RG-scoped root with destination-scoped modules and opt-in bootstrap

- **Benefits:** retains native azd verbs and the existing root; supports existing
  destinations using delegation at those RGs; one mapping expresses all layouts.
- **Costs and risks:** direct resources need focused wrappers, explicit IDs,
  split dependency phases, and an audit of nested Foundry private endpoints.
  RG count itself does not duplicate services; service SKUs, endpoints, logging,
  egress, and enabled network resources remain the actual cost drivers.
- **Security and identity:** managed identities and exact target grants remain;
  optional RG creation requires separately delegated subscription authorization.
- **Operation and compatibility:** one provision call; the current single-RG
  path stays the default. Application publication remains a separate lifecycle.
- **Reversibility:** easy to omit overrides in a new environment; changing an
  already-bound map is not a rollback mechanism or resource-move operation.

### Option B: Subscription-scoped root for every deployment

- **Benefits:** creates RGs and orchestrates child deployments declaratively in
  one template, including fresh destinations.
- **Costs and risks:** changes the root contract and requires subscription
  deployment access even when all target RGs already exist. It does not remove
  cross-RG resource dependencies or partial-deployment failures.
- **Security and identity:** broadens deployment scope unnecessarily; it does
  not confer resource-write, data-plane, or role-assignment permissions.
- **Operation and compatibility:** native root discovery, state, and teardown
  need a separate compatibility assessment; components still need exact IDs.
- **Reversibility:** restoring an RG-scoped root over deployed subscription
  state is not a safe automatic rollback. Not selected.

### Option C: Independently operated network, Foundry, and application deployments

- **Benefits:** teams can deploy boundaries with independently delegated identities.
- **Costs and risks:** introduces handoffs and state/output coordination; naive
  network/service separation creates PE/DNS/binding cycles and operator retries.
- **Security and identity:** permits narrower team ownership, but requires
  explicit cross-team joins, data roles, and trustworthy handoff IDs.
- **Operation and compatibility:** does not meet the required single
  `azd provision`; increases component and recovery coordination.
- **Reversibility:** each deployment needs its own state and cleanup contract.
  Viable for a future independently operated platform, not this delivery.

### Do not change

- Preserves current code, permissions, cost, and component behavior.
- Does not meet separate destination ownership; remains a supported default
  layout, not the only permitted layout.

## Decision

Adopt Option A for **new environments**, with the contracts below. Preserve
ADR-0015's repository-owned foundation and ADR-0016's foundation/application
boundary. No existing-resource migration, subscription-spanning workload
distribution, new diagram services, external hub build, or automatic cleanup is
included. Existing supported cross-subscription BYO references remain supported;
the same-subscription restriction applies to the three new workload destinations,
not to those references.

### Configuration and persistence

| Interface | Accepted contract |
| --- | --- |
| `AZURE_RESOURCE_GROUP` | Existing app/root RG; retain native azd selection and creation behavior. Never repurpose it as the Foundry or network RG. |
| `AZURE_FOUNDRY_RESOURCE_GROUP` | Optional Foundry/grounding destination; omitted or empty falls back to the app/root RG. |
| `AZURE_NETWORK_RESOURCE_GROUP` | Optional destination for locally owned networking; omitted or empty falls back to the app/root RG. |
| `CREATE_RESOURCE_GROUPS` | Strict boolean, default `false`. Only authorizes bootstrap of missing additional Foundry/network destinations. It neither controls native azd root creation nor authorizes creating BYO/external RGs. |
| Bicep `foundryResourceGroupName` | String, default `''`; resolve an empty value to `resourceGroup().name` at the root. |
| Bicep `networkResourceGroupName` | String, default `''`; resolve an empty value to `resourceGroup().name` at the root. |

Environment boolean input accepts only `true` or `false` after trimming and
case normalization; omission means `false`. Reject explicitly empty input,
numeric/truthy aliases, and malformed values before any bootstrap. Pass an actual
boolean through typed code, not a shell truthiness test.

Validate destination names and the selected subscription before use. Names that
differ only by case identify the same RG; deduplicate checks and creation by
subscription plus case-insensitive name. All-equal explicit values are valid,
as is any pair of shared destinations. No additional single/three-RG switch
is introduced. A name string cannot select another subscription.

Persist the effective subscription/app/Foundry/network mapping in the azd
environment, using one typed resolver shared by both hooks and configurators.
Bind it before additional Azure writes, retain it after partial creation, and
require the same effective mapping on retries. Once bound, conflicting changes
fail with new-environment guidance; aliases differing only in case do not create
a false conflict. Do not infer an existing environment's moved resources from
new overrides or silently fall back to root after a lookup error.

### Ownership matrix

Existing feature flags still control whether any listed resource is deployed.
Ownership is by function, not by the directory containing a module.

| Destination | Existing resources and constraints |
| --- | --- |
| Foundry/grounding | Foundry account, projects, models, connections, capability hosts, and deployed hosted agents; dedicated Agent Service Storage/Search/Cosmos DB/Key Vault dependencies; solution Search, solution grounding/document Storage, Speech and Bing grounding resources when enabled. |
| Application/root | Container Apps Environment and apps; ACR and its child task agent pool; App Configuration; application Cosmos DB/database/containers and application Key Vault/secrets; Application Gateway/WAF and its application-owned ingress resources when enabled. |
| Local network | Workload VNet, subnets and NSGs (including gateway/build subnets), UDRs/routes, local DNS zones and links, customer-owned private endpoints/NICs/DNS zone groups, peering, firewall/policy, NAT, Bastion, jumpbox and their supporting resources, only where already enabled and locally owned. |
| Shared local monitoring | Existing local Log Analytics, Application Insights and monitor private-link scope belong to app/root, not a fourth mandatory RG. Diagnostic settings remain attached to their source resources; their private endpoints and local DNS follow network placement. Preserve central monitoring overrides. |
| External hub/BYO | Use the exact configured resource IDs and existing supported join/link behavior. Do not recreate, relocate, retag, take ownership of, or silently delete platform-owned resources. |

The current solution `storageAccount` is classified as grounding/document Storage
even though it also holds existing conversation-cache and attachment containers.
Keep those containers in that account; app consumers use its exact ID/endpoint.
Do not split or duplicate the account to reproduce diagram icons. The application
Cosmos DB and Key Vault are **not** the Foundry Agent Service Cosmos DB and Key
Vault. Explicit BYO dependency IDs retain their actual ownership and subscription.

Managed identities follow their owning resources. ACR task agent pools remain
children of the app ACR while referencing a network subnet; hosted agents remain
children of the Foundry project while using app ACR images. Resource and
data-plane role assignments are scoped to their actual targets, not to a single
assumed owner RG. Application Gateway/WAF stay in app/root even though their
subnet and subnet NSG belong to network.

### Network precedence and dependency graph

Use this precedence rather than treating an RG choice as a network-mode switch:

1. Existing explicit BYO VNet, dependency, observability, and DNS resource IDs
   remain authoritative for those resources, including supported cross-subscription
   IDs. Do not replace their subscription with the workload subscription.
2. Policy-managed DNS retains its existing precedence and validation: no local
   zone/link or deployment-managed zone-group creation when that policy owns it.
   Explicit BYO DNS suppresses creation/linking of that zone; preserve the
   existing operator pre-link requirement.
3. Explicit `privateEndpointResourceGroupName` remains the PE RG override.
   Without it, preserve the existing `useExistingVNet && !sideBySideDeploy`
   placement behavior in the supported BYO scope. Otherwise locally owned PEs
   use the resolved network RG, replacing only the previous root fallback.
   Local DNS follows the equivalent existing BYO rule, otherwise network RG.
   Resolve resource IDs with their actual subscription as well as their RG.
4. `privateEndpointLocation`, existing subnet names/prefixes/IDs, delegation,
   CIDR validation, and isolation flags retain their meanings. RG choice alone
   neither enables networking nor creates another VNet or PE subnet.

Apply the PE/DNS destination contract to embedded Foundry and Agent Service
endpoints as well as the top-level PE aggregator and monitor endpoint. Do not
leave hidden endpoints in the service RG merely because a nested module created
them. Search-managed outbound shared private links are service-owned children
of Search, not customer network PEs to move or blanket-approve.

Keep the existing **single PE subnet fallback**, also for three RGs. The paired
optional `applicationPeSubnetName` and `applicationPeSubnetPrefix` parameters
enable a second subnet independently of RG count, through
`AZURE_APPLICATION_PE_SUBNET_NAME` and `AZURE_APPLICATION_PE_SUBNET_PREFIX`.
Both default to empty and must be supplied together. Application Cosmos DB,
Key Vault, App Configuration, Container Apps, ACR and monitor private endpoints
use the application subnet when configured; Foundry and grounding endpoints
retain the existing PE subnet. Validate aligned IPv4 CIDRs, subnet size,
distinct names, address-space containment and overlap before creating subnets,
without treating unchanged platform-owned BYO subnets as locally managed.

The deployment DAG is **network/base -> service resources -> dependent
PE/DNS/bindings**, with resource-specific RBAC after its target and identity
exist. Base subnet/NSG/route definitions must not depend on outputs of services
that themselves require those subnets. Separate late firewall destinations,
gateway backend configuration, DNS records, Foundry connections/capability
bindings, and PE work where required to avoid reverse dependencies. Initial
service creation may precede private connectivity, but dependent configuration
must wait for its required connectivity/readiness. Preserve current endpoint
and subnet-operation serialization across nested modules; moving scopes is not
permission to remove race-prevention dependencies or readiness guards.

Keep `infra/main.bicep` resource-group scoped; use focused modules with explicit
destination scopes. Do not use a subscription root for ordinary existing-RG
deployments. Preserve legacy/CAF names, explicit name overrides, and the root
naming seed by passing them into wrappers instead of recomputing from a module's
new RG context. Nested deployment names must be unique when destinations
coincide. Use output ARM IDs or fully qualified IDs with verified subscription
and destination; implicit `resourceId(...)` must not silently bind to root.

### Bootstrap, lifecycle, and permissions

Before bootstrap, both hooks must validate/bind the local application definition,
resolve and validate destinations and other local inputs, and check the persisted
map. Check all unique additional destinations without mutating existing RGs.
With `false`, a missing additional destination fails before service deployment.
With `true`, create only those additional destinations confirmed missing, using
the selected deployment location for new RG metadata. Do not change existing
locations, tags, locks, or policies. Never interpret access denial, a transient
failure, or invalid JSON as absence; never elevate the caller. A creation race
must converge by verifying the resulting exact RG, not overwrite an existing one.

The bootstrap uses the explicit RG-create operation, not an unconditional
subscription deployment. It runs before any cross-RG nested deployment and
never bootstraps root or an external/BYO/PE-override RG. Reused external scopes
must already satisfy their existing supported prerequisites.

Read-only lifecycle verification used local `azd version` **1.37.1**, commit
`6bd1275b6b31104034673946953533eb860dd646`, and that exact public source:

- [Command hook middleware](https://github.com/Azure/azure-dev/blob/6bd1275b6b31104034673946953533eb860dd646/cli/azd/cmd/middleware/hooks.go)
  invokes project hooks around the command action; the
  [provision graph](https://github.com/Azure/azure-dev/blob/6bd1275b6b31104034673946953533eb860dd646/cli/azd/internal/cmd/provision_graph.go)
  initializes the provider before calling the deployment manager.
- [Bicep provider](https://github.com/Azure/azure-dev/blob/6bd1275b6b31104034673946953533eb860dd646/cli/azd/pkg/infra/provisioning/bicep/bicep_provider.go)
  `Initialize`/`EnsureEnv` handles native root selection/existence for an RG-scoped
  template. A command hook is therefore before the template deployment, but must
  not assume native root creation has already happened. The local topology
  helper's older comment about pre-created root groups is not proof of all CLI
  versions' ordering.
- [Documented command hooks](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/azd-extensibility)
  place `preprovision` before provisioning. Keep bootstrap in this lifecycle,
  not in `postprovision` or only `preup`, so direct `azd provision` is covered.

Before merging hook implementation, verify first-run root availability and
parameter/azd-environment refresh with an instrumented no-Azure-write test of the
supported CLI. Preserve native default root naming/creation even if the hook
runs before root initialization; do not require an explicit root setting or
invent a new root name as an ordering workaround. An invalid local definition
must cause zero bootstrap writes; native azd root handling remains independent.
The source review establishes the hook/deployment boundary, not live acceptance.

| Operation | Required authorization and limits |
| --- | --- |
| Deploy to existing RGs | Resource writes and `Microsoft.Resources/deployments/*` at the participating RGs; no new subscription-level deployment or RG-create requirement. Contributor does not supply RBAC-assignment or data-plane access. |
| Optional additional RG creation | `Microsoft.Resources/subscriptions/resourceGroups/write` authorized at subscription scope, plus necessary reads. This does not grant rights to deploy into the new RG; those must already be inherited or delegated. No universal Owner requirement. |
| Role assignments | `Microsoft.Authorization/roleAssignments/write` at each exact target scope; for example appropriately conditioned Role Based Access Control Administrator. Do not substitute broad grants for missing target permissions. |
| Data configuration and BYO integration | Preserve service-specific data roles and VNet/subnet join, peering or DNS rights at their actual scopes. Do not widen to unrestricted subscription management. |

`azd provision` remains foundation-only: publish no app images, create no hosted
agent prematurely, and retain current Container App placeholder/re-provision
behavior. `azd deploy` publishes the selected application; `azd up` composes
the native stages. A failure reports exact attempted/created destinations and
an actionable cause through existing diagnostics, retains bindings, stops
dependent work, and performs no destructive compensation. Retry with the same
map after correcting the cause.

### Outputs and fail-closed binding

Do **not** change the JSON `AGENTLZ_PLATFORM_OUTPUTS` v1 shape, schema version,
schema integrity metadata, or closed-object validation for this feature. Add
only necessary flat azd outputs/context and App Configuration keys, with label
`agent-lz`, for destination names and exact resource IDs. Keep existing flat
`AZURE_RESOURCE_GROUP` as app/root. A future JSON extension needs a separate
versioned-contract decision, not a permissive schema workaround.

Audit Foundry setup, Container Apps, role reconciliation, existing images,
registry discovery, hosted prepare/access, panel, continuity, foundation
verification, outputs, and jumpbox/bootstrap consumers. Foundry operations use
Foundry context; application operations use app/root or their explicit resource
ID (including a custom ACR); network operations use network/BYO context.
Verify project/account/endpoint/subscription/destination, App Configuration
ownership, exact grant targets, identities, and secret references before writes.
Reject conflicting/malformed IDs and mismatched endpoints even when a resource
of the same name exists in another RG. Update guards and their negative tests;
never remove them to permit cross-RG access. Preserve OBO, document ACLs,
managed identities, Key Vault references, and existing readiness/approval gates.

### Cleanup and recovery boundary

Provisioning, re-provisioning, and partial-failure handling never delete RGs,
move resources, or clean up another destination automatically. A bootstrap
creation marker is recovery evidence, not permission to delete a group.

The inspected azd Bicep `Destroy` implementation discovers deployment resources,
groups them by RG, and can delete RGs; its root external-ownership warning is
not evidence of safe teardown for every nested destination. Force flags can
bypass confirmation. Existing `azure.yaml` has no project cleanup guard.
Therefore do not advertise unqualified `azd down` as safe for split/shared
destinations. Before enabling that path, prove scope/ownership discovery and a
fail-closed guard for unsupported deletion (including non-interactive/force
paths). Until then, split/shared-destination teardown is unsupported and must
be blocked with actionable guidance, not passed through silently. Preserve
the existing default single-RG lifecycle; do not infer that it validates a new
split/shared layout. Any later cleanup requires an exact inventory, explicit
ownership review and separate operator approval, not just environment-name tags.

## Consequences

### Positive

- Independent destination ownership without mandatory RG proliferation or a
  subscription-scoped orchestration root.
- Compatible defaults and native deployment verbs; no extra services solely to
  mirror the diagram.
- Explicit placement and binding expose previously implicit global-RG assumptions.

### Negative or accepted

- More scoped modules and cross-RG IDs require contract and security regression
  coverage, including endpoints hidden inside Foundry dependencies.
- Cross-RG provisioning is not an atomic ARM transaction. Partial resources may
  remain and incur cost until an operator resolves them.
- Creating RGs requires optional subscription authorization; successful preflight
  or what-if neither grants rights nor guarantees later deployment success.
- Portal and Terraform parity, live private connectivity, first-run azd details,
  and safe split/shared teardown require evidence before support is claimed.

## Adoption and migration

1. Accept this ADR and implement additive destination resolution/persistence and
   unchanged-v1 output contracts. Audit the exact manifest-pinned consumers.
2. If consumers need new flat context, make them compatible first and identify
   the exact compatible commits/tags before enabling the producer. Otherwise
   retain runtime pins. Record integration and rollback order in the handoff.
3. Introduce scoped foundation modules, network ordering, both hooks, and
   destination-aware configurators together; retain incorporated `infra.source`
   provenance rather than pretending a local refactor is an upstream re-sync.
4. Run the offline and separately authorized live gates below and update central
   documentation in the same delivery. Upstream implementation, publication and
   parity work are not dependencies of this repository-owned foundation change.
5. Prepare a **minor release later**, with separately approved publication and
   validated pins read from `manifest.json`; this ADR changes no version or pin.

This delivery supports new environments only; existing environments stay on
their current release and mapping. ADR-0018 is historical context, not a general
migration authorization. No in-place moves, data migration, identity replacement,
or DNS cutover tooling is included.

Before any provisioning, an operator may choose the compatible single-RG layout.
After binding/partial provisioning, keep the map and roll forward by correcting
permissions/configuration and retrying. To abandon a new environment, inventory
its exact resources and obtain separate cleanup approval; do not restore an old
root template over split deployment state. Rollback uses a prior supported
release in a **separate new environment**; it does not revert live RG scopes.

## Compliance verification

These are required fitness functions, not results claimed by this ADR:

| Acceptance criterion | Required evidence |
| --- | --- |
| Defaults and naming | Compare no overrides and explicit all-equal names against the baseline: identical resource names/flags/security posture, no extra RGs/services, legacy and CAF names preserved. |
| One/two/three destinations | Resolver and compiled-template tests cover all three shared-pair choices, three distinct names, case aliases, missing/empty override fallback and unique nested deployment names. Verify actual target IDs, including embedded Foundry dependencies. |
| Strict bootstrap | Unit/mocked-boundary tests cover default false, true/false, rejected empty/truthy values, invalid names/subscription, missing/existing groups, zero writes for invalid definitions/bindings, 403/timeout/invalid responses, creation races and partial retry. Existing RG metadata is unchanged. |
| Least privilege | Authorized live deployment to three pre-created RGs succeeds without subscription deployment/RG-create rights; separate RG-create authorization is needed only for optional bootstrap. Unauthorized data/role access still fails. |
| Exact bindings | Negative tests reject wrong RG/subscription/project/account/endpoint, same-name resources in another RG, mismatched App Configuration and custom registry IDs, and grants outside the validated target. Preserve OBO/document ACL behavior. |
| Network | Compile/DAG checks and private live probes cover base -> services -> late bindings, serialized subnet/PE operations, single-PE-subnet fallback, correct PE/DNS RGs, DNS/HTTPS, gateway app ownership and app-local shared monitoring. No public-access relaxation or BYO/hub duplication. |
| Cross-subscription BYO | Existing supported VNet/DNS/dependency/monitoring ID fixtures retain their original subscription and supported placement precedence; new workload destination names remain in the selected subscription. |
| Lifecycle/outputs | Both shells resolve/persist the same map; first-run native root handling and hook environment refresh work; provision publishes no images, deploy targets the right owners, re-provision retains images/runtime/map, and closed v1 JSON validation remains unchanged. |
| Cleanup | Read-only discovery and mocked destructive boundaries prove unsupported split/shared teardown fails closed, no automatic rollback deletes resources, and force/non-interactive paths cannot silently authorize shared-group deletion. |
| Compatibility and delivery | Cover hosted default, hosted with panel, classic and custom app definitions across representative Basic/public, private standalone and hub/BYO layouts. Record exact manifest combination, docs PR and supported-tool matrix. |

Use the existing `python -m pytest` suites, starting with affected topology,
deployment-mode, platform-output, custom-foundation, roles, Foundry, image,
re-provision, application-hook, hosted-access/prepare and private-network tests.
Extend `infra/tests/contracts/` rather than deleting baseline gates or blindly
regenerating fingerprints. Run existing Bicep build/lint checks and PowerShell/
shell syntax plus behavior checks. Test remaining combinations offline rather
than requiring an unnecessary full Cartesian Azure matrix.

**Evidence boundary and time-bounded gates:** this ADR was checked against the
read-only repository and azd sources above; no Azure writes, what-if, live
deployment or teardown occurred. Before the destination/hook implementation
merges, close the first-run root/parameter-refresh and cleanup-guard
investigations with observable tests; block those paths if the criteria fail.
Before a minor release is approved, obtain separate operator authorization for
what-if and a fresh live validation environment, then verify IDs, roles,
DNS/HTTPS, provision/deploy/re-provision, restricted-RG permissions, and recovery.
Offline compilation is not proof of those properties.

Portal and Terraform configurable-RG support remain **unsupported/unverified**
until their real entry points, parameter surfaces, permissions, and outputs pass
equivalent acceptance checks. A parity workflow/handoff is not implementation
evidence. If a channel is not verified at release, explicitly exclude this
feature for that channel rather than claim parity.

## Documentation impact

No operator-facing behavior ships with this ADR alone. Before shipping the
implementation, search and update affected pages under
`Azure/AI-Landing-Zones` `docs/agent-landing-zone/` on a feature branch: planning,
customer environments, configuration, resource naming, Bicep/full-stack/infra-only
deployment, custom applications, network isolation/private access, Application
Gateway, hosted agents, permissions/CI, operations and troubleshooting.
Document the four settings, defaults, ownership/override precedence,
pre-created-RG permissions versus bootstrap permissions, unchanged single subnet
fallback, new-environment restriction, partial recovery, teardown limits, and
the evidenced Bicep/Terraform/portal support matrix.

Use central product documentation per ADR-0014; the legacy `docs` branch is not
the source. Keep this repository and service READMEs short and link to the
published site. No duplicated product guide, new diagram service, private
validation identifier, or private meeting link belongs in the delivery.

## Review trigger

Review before the planned minor release and on an azd hook/state/teardown change,
Foundry/AVM endpoint lifecycle change, failed live fitness gate, requested
in-place migration, cross-subscription workload destinations, independently
operated deployments, further PE-subnet ownership/layout changes, separately owned ACR, or new
portal/Terraform support claim. These require their own evidence and, where they
change this contract, an explicit decision rather than an implicit fallback.
