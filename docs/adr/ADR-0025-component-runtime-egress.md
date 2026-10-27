# ADR-0025: Declare and reconcile component runtime egress

**Status:** Accepted for implementation of #799; release approval remains separate<br>
**Date:** 2026-10-27<br>
**Owners:** Agent Landing Zone maintainers

## Context

Runtime downloads are not foundation dependencies. Both the orchestrator
(`src/connectors/aifoundry.py`) and ingestion (`tools/aoai.py`) initialize
tiktoken; a cold cache downloads encoding data over HTTPS from
`openaipublic.blob.core.windows.net`. The UI uses platform authentication,
telemetry and provisioned service endpoints, with no additional fixed runtime
destination. Configurable SQL, SharePoint and MCP destinations are operator
choices, not a reason to grant wildcard access.

The approved source review covers UI v3.3.1, orchestrator candidate
`aafde58271638e60acac52f7c6a315841181e432`, and ingestion candidate
`09e4b2546426d8d85d9e709b2f1a23a4d2d180aa`. The coordinated Foundry-root
release owns the final manifest pins. No runtime source changes are necessary.
Custom definitions currently add applications to the selected bundled
workloads; egress selection must follow that actual composition.

Prioritized characteristics and measures:

1. Compatibility: absent declarations remain valid; explicit empty arrays
   mean no additional runtime egress.
2. Least privilege: exact FQDNs, HTTP(S), valid application-rule ports, actual
   workload subnet prefixes, and no disabled-component contributions.
3. Ownership: change only this application's marked rules; retain unrelated
   rules, collections and foundation dependencies.
4. Reviewability: deterministic local plan before provisioning and a resolved
   change plan before reconciliation; invalid or stale input fails closed.
5. Isolation: no firewall creation, no mutation for non-isolated deployments,
   and report-only behavior for externally managed policies.

Affected repositories are Agent Landing Zone and the central
`Azure/AI-Landing-Zones` documentation source on `main`. Runtime repositories
are evidence sources, not implementation targets.

## Alternatives considered

### Option A: Foundation-owned application FQDN lists

- Simple ARM-only deployment, but embeds application knowledge in generic
  infrastructure and couples every dependency to foundation updates.
- Replacing existing collections risks unrelated-rule loss; omitted resources
  in incremental ARM deployments do not reliably revoke stale rules.
- Reversible through redeployment, but violates ADR-0016's boundary.

### Option B: Application declarations and a focused configuration reconciler

- Adds an optional `egress` array to each v1 application component, with
  `fqdn`, `protocol`, `port` and `purpose`.
- Keeps foundation changes generic: expose only the deployment-managed policy
  ID and workload subnet IDs, gated by existing isolation/firewall selection.
- Requires management-plane reads and a narrowly scoped child-resource write,
  explicit ownership metadata, collision checks and concurrency protection.
- Works with existing hooks and requires no runtime/configuration-label change.
- Easy to stop or roll forward without rewriting foundation rules.

### Do not change

- No new contract or operator steps, but cold-cache runtime failures persist.
- Manual allowlists drift and cannot safely track shared or disabled components.

## Decision

Choose option B. Preserve `schemaVersion: 1`; this is an additive optional
contract revision, not a new incompatible wire interpretation. Accept exact
DNS hostnames only (no URLs, IPs, wildcards or local names), protocols `https`
and `http`, ports 1 through 64000 (the Azure Firewall application-rule limit),
and a nonblank human-readable purpose.

Use the existing component selection and composition contracts, including
optional ingestion, hosted orchestration and preserved classic runtimes.
Deduplicate destination/protocol/port tuples and union only their active
owners' workload subnet sources. UI declares `[]`; orchestrator and ingestion
declare the shared tokenizer destination.

An application-owned collection in a dedicated component-egress group
contains deterministic named rules with a versioned ownership marker.
Unmarked rules and other collections survive reconciliation. A malformed
owned marker or a conflicting collection fails rather than being adopted.
Remove a requirement only when its last declared owner disappears. For an
enabled legacy component with an absent field, retain its previously owned
requirements; absence must not be interpreted as an explicit revocation.
Fresh legacy definitions add no inferred requirements.

Preprovision emits a local, credential-free declaration plan. Postprovision
and predeploy check that plan against current selections before applying,
resolve exact subnet prefixes from the foundation's subnet resource IDs,
show the resolved change plan, and reconcile only a deployment-managed
policy. Read-before-write and conditional requests protect against concurrent
changes; failures are actionable and stop the hook. Externally managed
policies get only a plan, with no policy reads or writes. Non-isolated
deployments perform no firewall operations.

Subnet rules are not per-process or per-component isolation: every workload
sharing an allowed source subnet can use its union of destinations. Existing
platform rules can already allow other traffic. Dedicated environments or
subnets and centrally reviewed policies are required for stricter isolation.
No new firewall, route, DNS, identity, RBAC role or paid service is introduced.
Build-time dependency declarations remain out of scope.

## Consequences

### Positive

- Dependencies are reviewable metadata for bundled and custom applications.
- Shared downloads remain allowed until their final owner is removed.
- Foundation policy resources, unrelated rules and external ownership survive.

### Negative or accepted

- Operators need network-policy child-resource write permission for managed
  reconciliation, in addition to management-plane subnet reads.
- The saved declaration plan must be regenerated after selection or definition
  changes; external-policy operators must implement the reported changes.
- A cold-cache tokenizer check needs public HTTPS access, not an Azure
  deployment. Mocked tests cannot establish real firewall traversal.

## Adoption and migration

Ship schema, validator, declarations, generic outputs, reconciler and both
hook variants together. Integrate after the parent-owned Foundry-root release,
then coordinate the central documentation PR against its updated `main`.
Do not change release pins, publish artifacts or merge before parent approval.

Legacy definitions need no edits. Explicit `egress: []` revokes only this
feature's owned requirements for that component. Removing a component revokes
its ownership but not another component's shared requirement.

Rollback first reviews and removes only marked component rules using an
explicit empty declaration plan; then roll back hooks/metadata. Reverting code
alone does not remove existing Azure rules. Never delete foundation groups,
shared rules or externally managed policy content as rollback.

## Compliance verification

- Schema and semantic tests reject unsafe destinations, bad protocols/ports,
  blank purposes and malformed declarations with JSON pointers.
- Selection tests cover bundled/custom, hosted/classic preservation, ingestion
  disabled, explicit empty and legacy absent fields.
- Reconciliation tests cover deduplication, final-owner removal, legacy
  retention, unrelated content, collisions and concurrency errors.
- Mocked management-plane tests prove exact subnet sources, managed-only writes
  and zero firewall operations in report-only/non-isolated modes.
- Execute both hook variants offline and initialize real tiktoken encodings
  from an empty cache; record the exact commands in the PR.
- Keep original protected graph fingerprints unchanged. Any added generic
  outputs require exact reviewed projection deltas and mutation-rejection tests,
  never regenerated security baselines or broad exemptions.

## Documentation impact

Update the central current-release application-definition and network-isolation
guidance, deployment review steps and troubleshooting. Explain managed versus
external policies, legacy semantics, source-subnet limits and rollback. Keep
product guidance out of service READMEs.

## Review trigger

Reassess when a component adds a fixed runtime download, new protocol support
is requested, shared-network isolation requirements change, or the foundation
changes workload subnet or firewall ownership outputs.
