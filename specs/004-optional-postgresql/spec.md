# Feature Specification: Optional application PostgreSQL

**Feature Branch**: `feature/postgresql-opcional`

**Created**: 2026-11-05

**Status**: Implementation and offline verification complete; maintainer review pending; Azure acceptance excluded by requester

**Input**: [Issue #864](https://github.com/Azure/agent-landing-zone/issues/864)
and Paulo's planning decisions in this conversation.

## Scope and clarification record

This is an optional foundation extension for a custom application, initially
running on Container Apps. It does not change bundled runtime code, replace
Cosmos DB, migrate application data, or connect NL2SQL to a new database.

The conversation changes the issue's original private-only requirement:

| Question | Selected behavior |
| --- | --- |
| Enabled by default? | No; both providers and configuration flows default off. |
| Basic, `NETWORK_ISOLATION=false` | Public PostgreSQL endpoint, restricted to dedicated Container Apps NAT egress and explicitly authorized operator addresses. |
| Isolated, `NETWORK_ISOLATION=true` | Application Private Endpoint, private DNS, public database access disabled. |
| Existing environments | First delivery supports fresh deployments only; reject implicit environment recreation or network-mode migration. |
| Authentication | Entra-only; no database password or dummy secret. |
| Application SQL permissions | CRUD in the application schema; no DDL, role management, or administration. |
| Bootstrap | Operator-run cross-platform utility plus central documentation; never automatic SQL grants in deployment hooks. |
| Default sizing | Economical development profile; HA off and other cost-sensitive settings explicit. |
| Discovery | Flat non-secret App Configuration keys under `agent-lz`; preserve platform outputs v1. |
| Data protection | Independent Azure deletion lock, not owned by Terraform state; explicit backup review and removal procedure. |

The initial planning restriction was superseded by the requester's explicit
2026-11-05 implementation instruction: implement autonomously and reconcile the
live issue with these choices. Issue #864 was read and updated accordingly.
This does not claim independent ADR approval. Azure deployment/destructive
validation, cleanup, releases and manifest pin updates remain excluded.
T039/T040 are **NOT EXECUTED / deferred**, not completed live acceptance.

## User Scenarios & Testing

### User Story 1 - Keep the standard deployment unchanged (Priority: P1)

An operator who does not request PostgreSQL retains the shipped foundation.

**Independent Test**: Compare disabled/default resource graphs, input
composition, outputs and application selection with the current baseline.

**Acceptance Scenarios**:

1. **Given** fresh default inputs, **when** either provider plans deployment,
   **then** there is no PostgreSQL server, database, administrator, firewall
   rule, endpoint, dedicated DNS zone, lock, NAT, public IP or new ACA VNet
   integration attributable to this feature.
2. **Given** PostgreSQL is disabled, **when** platform settings are published,
   **then** no PostgreSQL discovery keys are created and the v1 JSON is unchanged.

### User Story 2 - Use PostgreSQL from a Basic Container App (Priority: P1)

An operator enables PostgreSQL before creating a new Basic foundation.

**Independent Test**: Connect from a test Container App using its managed
identity through fixed NAT egress, then exercise SQL permission boundaries.

**Acceptance Scenarios**:

1. **Given** a fresh supported workload-profiles environment, **when**
   PostgreSQL is enabled, **then** ACA has external ingress and VNet integration,
   a dedicated Standard NAT Gateway and public egress IP; PostgreSQL firewall
   permits that IP and only explicitly configured additional operator ranges.
2. **Given** the application identity has been bootstrapped, **when** it uses
   an Entra token and verified TLS, **then** schema CRUD succeeds.
3. **Given** an unauthorized source or identity, **when** it attempts access,
   **then** network access or database authorization rejects it.
4. **Given** a conflicting forced route or legacy Consumption-only environment,
   **when** provision is requested, **then** preflight rejects the configuration;
   it must not silently allow all Azure services or bypass governance routes.

### User Story 3 - Use PostgreSQL privately (Priority: P1)

An operator enables PostgreSQL in a new isolated foundation.

**Independent Test**: Verify private DNS and connect from an authorized
VNet-connected application; verify public access is disabled.

**Acceptance Scenarios**:

1. **Given** isolation is enabled, **when** either provider deploys PostgreSQL,
   **then** a Private Endpoint uses the application PE subnet and the supported
   DNS ownership model; no PostgreSQL delegated server subnet is introduced.
2. **Given** BYO VNet, existing private DNS or policy-managed DNS, **when**
   inputs are validated, **then** ownership and required links/records are
   explicit, with no duplicate zone creation or silent DNS fallback.

### User Story 4 - Bootstrap and preserve application data (Priority: P1)

An authorized administrator explicitly enables database access for one
application identity and can repeat the operation safely.

**Independent Test**: Run bootstrap twice, verify identical identity mapping
and grants, and preview disable, replacement and teardown after inserting data.

**Acceptance Scenarios**:

1. **Given** an administrator, application object ID, schema and DDL owner,
   **when** bootstrap runs, **then** the non-admin role is mapped to the correct
   Entra identity and receives schema-scoped CRUD and sequence access.
2. **Given** a role-name or object-ID conflict, **when** bootstrap runs,
   **then** it fails with an actionable error rather than remapping the role.
3. **Given** future objects created by the declared DDL owner, **when** the
   application accesses them, **then** intended default grants apply.
4. **Given** the application role, **when** it attempts DDL, cross-schema
   access or privileged role creation, **then** permission is denied.
5. **Given** a protected database, **when** an operator disables the option,
   changes immutable binding, or requests `azd down`, **then** the supported
   lifecycle stops before destructive execution.
6. **Given** direct Terraform destruction outside the lifecycle, **when** the
   independent lock is present, **then** Azure rejects server deletion.
   A sufficiently privileged operator can deliberately remove the lock;
   this is not a guarantee against privileged bypass.

## Requirements

### Functional Requirements

- **FR-001**: Both providers MUST implement an explicit, strictly typed
  `deployPostgreSql` opt-in, default false, through the shared native resolver.
- **FR-002**: PostgreSQL MUST belong to the configured application resource
  group; networking and DNS MUST retain existing ownership conventions.
- **FR-003**: Basic MUST use dedicated ACA NAT egress and restricted public
  PostgreSQL connectivity. Broad Azure-services firewall rules are prohibited.
- **FR-004**: Isolated MUST use Private Link, private DNS and public access
  disabled, without mixing PostgreSQL delegated-subnet networking.
- **FR-005**: Both providers MUST use compatible, explicitly pinned AVM
  modules and equivalent effective settings rather than module defaults.
- **FR-006**: Engine, tier/SKU, storage, backup retention, geo-backup and HA
  MUST be configurable and validated. Unsupported regional capacity or policy
  MUST fail explicitly; there is no automatic SKU or HA downgrade.
- **FR-007**: An explicit administrator Entra principal MUST be provisioned.
  SQL grants MUST be separate from Azure RBAC and deployed application identity.
- **FR-008**: Bootstrap MUST be manual, cross-platform, identity-bound,
  idempotent and least privilege, with safe SQL identifier handling and no
  tokens in arguments, logs or persistent settings.
  The first utility targets dedicated base-table/sequence schemas; view,
  materialized-view and foreign-table wrappers and user SECURITY DEFINER
  functions/triggers are rejected rather than promising cross-schema isolation.
- **FR-009**: App Configuration MUST publish only non-secret connection
  metadata under `agent-lz`; platform outputs v1 and bundled consumers remain
  unchanged.
- **FR-010**: Shared lifecycle MUST create and verify an independently owned
  `CanNotDelete` lock before reporting ready, guard destructive transitions,
  and document partial-provision recovery and explicit removal.
- **FR-011**: Initial adoption MUST require a fresh compatible environment;
  immutable server/network changes or retrofit MUST be rejected, not recreated.
- **FR-012**: PowerShell and shell lifecycle behavior MUST be equivalent.
- **FR-013**: Central AI Landing Zones documentation MUST cover both providers,
  network paths, costs, prerequisites, grants, limits and removal.

### Edge Cases

- Disabled PostgreSQL-specific settings never enable the feature implicitly.
- Duplicate/mismatched administrator, application or SQL role identity fails.
- NAT subnet with forced firewall/NVA default route cannot promise NAT SNAT.
- Existing DNS is external ownership, not a deletion target.
- Lock creation fails after server provision: fail, report incomplete protection,
  do not publish ready discovery, and permit an explicit safe recovery rerun.
- Failure between role creation and schema grants: rerun verifies prior mapping
  and completes grants; do not swallow errors or assume cross-database atomicity.
- Shared schemas/databases and existing application data are not bootstrap targets.

### Key Entities

- Deployment selection and immutable binding.
- PostgreSQL server, application database and connection metadata.
- ACA subnet, dedicated NAT egress and PostgreSQL firewall rules.
- Private Endpoint, DNS zone ownership and resolution readiness.
- Administrator principal, application managed identity and SQL access binding.
- Independently owned server deletion lock and explicit cleanup review.

## Success Criteria

- **SC-001**: Disabled deployments have zero feature-owned resource additions
  and preserve current application selection and outputs in both providers.
- **SC-002**: Fresh Basic and isolated deployments pass real connectivity,
  authentication and authorization scenarios for both providers.
- **SC-003**: Two bootstrap executions produce the same identity mapping and
  effective privileges; conflicting identity mapping is rejected.
- **SC-004**: All destructive-transition scenarios stop or are denied with data
  intact; intentional removal follows the documented approval procedure.
- **SC-005**: Every public input, default and output has counterpart coverage
  and documentation; mocked evidence is distinguished from deployed Azure evidence.

## Assumptions

The application owner supplies a custom ACA consumer and owns its driver,
token renewal and database migrations. No bundled component is a new consumer.
The operator supplies the administrator principal, and has required deployment
and lock-management rights. Runtime pins do not change for this feature.
