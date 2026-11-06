# ADR-0039: Optional PostgreSQL with mode-aware application connectivity

**Status:** Implementation authorized by requester; independent maintainer review pending<br>
**Date:** 2026-11-05<br>
**Owners:** Agent Landing Zone maintainers

## Context

Issue #864 requests optional PostgreSQL with provider parity. During planning,
Paulo selected public restricted access through fixed ACA NAT in Basic and
Private Link in isolation. On 2026-11-05 the requester explicitly authorized
implementation of these decisions and reconciliation of the live issue body.
Issue #864 now records mode-aware/fresh-only scope and explicitly deferred live
validation. This is a record of the request, not fabricated independent approval.
First delivery supports fresh deployments/custom
consumers/manual bootstrap, not retrofit, runtime changes or Cosmos migration.

Owners: Agent Landing Zone foundation/lifecycle/operator CLI and central
Azure/AI-Landing-Zones product docs. Runtime repositories/pins and platform
outputs v1 are unchanged.

Prioritized characteristics with measures:

1. Compatibility: zero feature-owned resources/settings when disabled.
2. Predictability: stable Basic SNAT and private isolated DNS; unauthorized
   sources/identities denied.
3. Data safety: disable/replacement/down blocked; independent lock before ready.
4. Least privilege: Entra-only schema CRUD, no DDL/admin or logged tokens.
5. Parity: same typed inputs/defaults/outputs and paired live acceptance.

## Alternatives considered

### Always-private

Strong private boundary, but current Basic ACA still needs new VNet integration.
Does not follow selected network-mode semantics; future alternative.

### Public Basic with discovered outbound IPs

Smaller initial scope/no NAT charge, but platform-address changes require
firewall reconciliation and risk interruption. Rejected for predictability.
Broad Azure-services firewall rule also rejected.

### Mode-aware networking with dedicated ACA NAT

External Basic ACA ingress remains, with VNet and fixed SNAT at extra cost.
Isolation stays private. Requires fresh workload-profiles environments and
route validation; cannot override corporate routing. Selected.

### Do not change

Avoids cost/lifecycle responsibilities but leaves custom relational persistence
outside the supported foundation and does not fulfill #864.

## Decision

Default off in both roots/configuration. Pinned AVMs, explicit economical
settings, no module-default drift or dummy password.
Basic uses dedicated Standard ACA NAT/exact-IP PG firewall and explicit
operator ranges; jumpbox NAT is unchanged. Isolation uses app PE/private
DNS/public disabled, with no delegated PG server subnet.

Fresh deployments only, with same-binding recovery reruns. Reject retrofit,
mode migration and implicit resource recreation.
Explicit Entra admin; manual utility maps app OID and grants schema CRUD,
not DDL/admin. Add flat agent-lz discovery, preserve outputs v1.
Reject application membership in a Group administrator's transitive Entra
membership before requesting a SQL token; directory enumeration must complete
with readable membership and validated same-scope pagination.

Lifecycle owns server-scoped CanNotDelete lock outside both provider graphs.
Normal hooks guard destructive transitions; independently verified lock must
precede readiness publication. Backup review/owner approval precedes deliberate
lock removal/resource cleanup.

### Output transport within ARM's fixed budget

The existing Bicep root already uses ARM's maximum 64 outputs. Adding five
native fields fails compilation. Increasing/suppressing the limit is not a
deployable alternative. Removing or renaming existing outputs breaks consumers;
extending the closed platform outputs v1 JSON also breaks its contract. Even
one new consolidated root output exceeds the budget.

Retain all existing Bicep outputs and use the shared post-provision adapter,
consistent with existing platform metadata hydration. Derive the server ID
from persisted creation intent, independently read/verify server, database,
directory, ownership and deletion lock, then persist the five documented
PostgreSQL azd environment values. Basic egress follows the verified ACA
subnet/NAT/static IPv4 association, not guessed names or ingress IPs.
Terraform can expose additive native outputs; the same adapter verifies them
against live resources. No unchecked value becomes ready discovery.

This is a provider transport difference, not a feature or consumer difference.
Fresh disabled deployments perform no PostgreSQL discovery or metadata writes.
Verification/persistence failure fails the hook; rerunning the same immutable
binding recovers partial metadata. Tests must preserve the complete old Bicep
output set and disabled graph, and verify missing, conflicting and malformed
metadata, both network modes and failed azd writes.

## Consequences

### Positive

Disabled architecture/runtimes unchanged. Fixed SNAT avoids changing-IP lists.
SQL grants are separate from RBAC. Independent lock prevents Terraform from
destroying its own lock first.

### Negative or accepted

Basic PG adds network/NAT cost; existing Basic cannot opt in without migration.
Operator arranges admin networking and schema ownership.
Creation before lock verification is an incomplete-provision window, not
protected readiness. Privileged removal can bypass locks; direct templates
bypass some lifecycle guards. Selected Bicep AVM uses a preview server API;
policy compatibility is an explicit deployment gate, not an assumed exception.

## Adoption and migration

Retain maintainer review before merge. Coordinate typed
contracts, both providers, lifecycle protection, bootstrap and central docs.
Feature PR targets develop; docs use their own feature branch. Runtime pins
and Bicep upstream provenance remain unchanged; no resynchronization occurs.

Initial adoption is fresh-only. Code rollback does not authorize data/lock
deletion; preserve binding and use roll-forward recovery after partial provision.
Intentional removal reviews backups, stops consumers, inventories exact scope,
removes independent protection with approval and reconciles provider state.
Never delete shared DNS/RGs automatically.

## Compliance verification

Use [quickstart](../../specs/004-optional-postgresql/quickstart.md) for typed
contracts, Bicep compiled checks, Terraform mock/validation, Windows/Linux
hooks/CLI and paired live networking/SQL/data-safety acceptance.
Actual SNAT/DNS, repeated mapping/grants, negative permissions and independent
lock denial are required; compilation/mocks alone are not deployed parity.
The latest requester instruction explicitly excludes Azure deployment and
destructive acceptance: T039/T040 remain **NOT EXECUTED / deferred**.
See the quickstart evidence ledger for passing offline Python/hook checks and
the integrated offline validation results and remaining live-only risks.

## Documentation impact

Central configuration, provider deployment, network isolation, custom
application, sizing/cost and operations pages; new registered optional PG guide.
Explain fresh-only support, NAT cost, manual grants and explicit removal.
No legacy docs-branch/README product documentation.
Central source updated on `Azure/AI-Landing-Zones:feature/postgresql-opcional`,
latest documentation commit `50b46aa68c63e6017a1ca979af0229a10dd790f0`.
The change registers `postgresql.md` and updates configuration, both providers'
actual deployment guides/entry pages, networking, custom apps, operations and
cost guidance. A source search covered all 55 Agent Landing Zone pages.

## Review trigger

Reassess before implementation if AVM API policy/provider compatibility fails.
Revisit for existing-environment adoption, replicas/HA operation, bundled SQL
consumer, Basic corporate forced routes or another cloud.
