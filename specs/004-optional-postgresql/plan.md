# Implementation Plan: Optional application PostgreSQL

**Branch**: `feature/postgresql-opcional` | **Date**: 2026-11-05 | **Spec**: [spec.md](spec.md)

**Input**: Issue #864 and Paulo's clarification record in `spec.md`.

**Status**: Requester-authorized implementation in the shared feature worktree.
Both providers, lifecycle/bootstrap and central docs implemented with offline
integration evidence; independent maintainer review pending. Azure validation explicitly
excluded/deferred by the latest request.

## Summary

Add optional Entra-only PostgreSQL Flexible Server through both providers.
Fresh Basic deployments use dedicated Standard NAT egress for VNet-integrated,
externally accessible Container Apps and a restricted public database.
Isolated deployments use Private Link and current DNS ownership conventions.
Manual bootstrap grants a custom application identity schema CRUD, without DDL.
An independently owned deletion lock and shared lifecycle guards protect data.

Disabled deployments remain unchanged. Bundled runtime code, Cosmos, NL2SQL and
platform outputs v1 do not change. Existing-environment retrofit is out of scope.
The live issue's private-only wording has been reconciled with the selected design.
Review [ADR-0039](../../docs/adr/ADR-0039-optional-application-postgresql.md)
before implementation.

## Technical Context

**Language/Version**: Bicep CLI v0.42.1; Terraform >=1.13,<2; Python >=3.10
for the manual utility; existing PowerShell and POSIX shell hooks.

**Primary Dependencies**: Bicep PostgreSQL AVM 0.16.1; Terraform PostgreSQL
AVM 0.2.3; existing network AVMs, Azure CLI and azure-identity; proposed
`psycopg[binary]==3.3.6` in utility requirements, matching the validated driver.
Do not introduce an ORM or token-pooling library for a manual CLI.
Preserve exact root provider constraints and `.terraform.lock.hcl`.
Bicep AVM uses a preview server API; validate subscription governance rather
than claiming a GA-only resource composition. See [research.md](research.md).

**Storage**: PostgreSQL 16; Burstable/Standard_B1ms, 32 GiB, backup 7 days,
HA disabled, geo-backup disabled, auto-grow disabled.
Unsupported regional capacity fails; no automatic SKU/HA downgrade.

**Testing**: Existing pytest deployment/hook contracts, compiled Bicep offline
contracts, Terraform formatting/validation/mock tests, Windows/Linux utility
tests and approved live Azure cases for both providers/network modes.

**Target Platform**: Azure public cloud, fresh workload-profiles ACA
environments; BYO VNet/DNS with explicitly validated ownership/routing.

**Project Type**: Foundation extension and manual operator CLI.

**Performance Goals**: No application throughput/SLA claim. Verify stable
Basic SNAT across ACA revision/restart operations and positive/negative SQL
access. Economical sizing is not a production HA guarantee.

**Constraints**: Default-off no-op, Entra-only, verified TLS, scoped grants,
no implicit deletion, no corporate-route bypass, no platform v1 changes,
manual SQL bootstrap and no secret outputs.

**Scale/Scope**: One server/application database per deployment; one SQL
access binding per bootstrap invocation. App owners manage drivers/token
renewal and migrations. Replicas, PgBouncer, CMK, runtime adapters and
existing-environment migration are out of scope.

## Constitution Check

Constitution v2.1.0 governs the design. Phase 0 entry and Phase 1 re-evaluation
pass for this plan, not for unimplemented behavior:

| Principle | Entry check / post-design evidence |
| --- | --- |
| I. Boundaries | Foundation in both roots; focused lifecycle module; manual util; no duplicated runtime or product docs. |
| II. Contracts | Shared typed inputs and additive flat agent-lz keys; platform outputs v1 unchanged; binding/recovery documented. |
| III. Identity/data | Explicit admin, non-admin app OID, manual grants and independent lock; user selected lifecycle/network trade-offs. |
| IV. Errors | Preflight, lock-readback and role-mapping failures are explicit; no downgrade or readiness after partial protection. |
| V. Evidence | Real repository runners and paired live acceptance matrix identified; implementation must deliver evidence. |
| VI. Parity | Every input/default/resource/output/lifecycle case covers both providers; module-shape differences are documented. |

**Implementation gates**: The requester authorized implementation and issue
reconciliation on 2026-11-05; independent maintainer review is not invented.
Before merge, retain review of ADR and reconciled issue;
compatible pinned modules and subscription policies; both provider checks;
Windows/Linux hook/utility behavior; coordinated central documentation; live
Azure evidence or explicit unverified scenarios. No release or deployment is
authorized by planning.

## Project Structure

### Documentation (this feature)

```text
specs/004-optional-postgresql/
|-- spec.md
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
`-- contracts/postgresql.md
docs/adr/ADR-0039-optional-application-postgresql.md
```

### Source Code (planned surfaces)

```text
main.parameters.json
infra/bicep/{main.bicep,main.parameters.json}
infra/terraform/{variables,main.networking,main.compute,outputs}.tf
infra/terraform/main.postgresql.tf                      (new)
infra/terraform/tests/
infra/shared/                                         (shared naming if needed)
config/deployment/{input_types,composition,outputs,teardown}.py
config/deployment/postgresql.py                        (new lifecycle module)
util/postgresql_bootstrap.py                           (new manual CLI)
util/requirements.txt
scripts/{preProvision,postProvision,preDown}.{ps1,sh}
scripts/infra/Invoke-PreflightChecks.ps1
tests/
infra/tests/contracts/
```

**Structure Decision**: Extend existing foundation/composition surfaces;
keep lock/binding lifecycle separate from operator SQL behavior.
Keep Bicep's complete existing 64-output interface; shared post-provision
resource verification materializes PostgreSQL azd metadata for both providers.
Terraform native metadata is additive and checked against the same binding.
See ADR-0039 for the transport alternatives and compatibility constraints.
Product docs belong in `Azure/AI-Landing-Zones` on a coordinated feature branch.
`tasks.md` is a later `/speckit-tasks` artifact, not generated by this command.

## Implementation sequence

1. Reconcile scope/ADR and freeze typed contracts/defaults. Add disabled and
   invalid-input regressions before feature wiring.
2. Implement server/database/admin in both providers with explicit AVM inputs,
   shared naming, output contracts and paired tests.
3. Wire Basic ACA VNet/NAT/firewall and isolated PE/DNS paths. Keep their
   resource graphs conditional and free of application/SQL-bootstrap cycles.
4. Add shared fresh-binding/replacement checks, independent-lock creation and
   readback, disable/down guards and additive discovery through both hooks.
5. Build/test manual bootstrap; run paired live network, authentication,
   authorization, rerun and data-safety acceptance.
6. Update central docs and hand off counterpart evidence, compatibility and
   residual risks. Feature PR targets `develop`; no runtime pin changes.

Steps 3 and 4 consume the frozen identity contract from step 2. Bootstrap
consumes it only after lock/readiness succeeds. Documentation tracks all
operator-visible behavior in the same coordinated delivery.

## Compatibility and recovery

Enabled Basic modifies ACA network shape only on fresh creation; disable,
mode changes, unsafe adoption or immutable replacement are rejected by the
supported lifecycle. Same-binding enabled recovery reruns remain supported.
Existing jumpbox NAT is unchanged; dedicated ACA NAT is absent in isolated
mode. Conflicting forced routes fail rather than being overwritten.

Lifecycle owns a deterministic server-scoped `CanNotDelete` lock outside
Terraform state and the Bicep graph. Verify exact subscription/RG/server
binding and lock readback before publishing readiness. Failure after resource
creation but before protection is incomplete provisioning; report it explicitly
and recover by verified same-binding protection/publication.

Normal teardown is blocked while PostgreSQL remains bound, even after switching
the enablement variable off. Manual cleanup requires exact inventory, backup/
PITR review, consumer shutdown, explicit owner approval, independent-lock
removal and provider-specific state reconciliation. Never delete shared DNS/RGs.
Code rollback does not authorize data/lock removal. Direct-provider callers
bypass some guards; the lock helps but cannot stop privileged lock removal.

## Evidence and documentation

Follow [quickstart.md](quickstart.md). Compilation/mocks are not live parity.
Verify actual SNAT, DNS resolution, SQL permission boundaries, deletion denial
and partial-provision recovery. Regional capacity, policy-managed DNS convergence
and private Entra operations remain live acceptance risks, not assumed success.

Central docs search found affected configuration, network-isolation and custom
application guidance. Update provider deployment guides, operations and
`sizing-cost-planner.md`; `cost-planning.md` is a redirect, not a new guide
location. Add/register a focused PostgreSQL page in `mkdocs.yml`. Explain NAT
cost, fresh-only scope, bootstrap access and lock bypass. Do not duplicate
product documentation here or in runtime READMEs.
