# Tasks: Optional application PostgreSQL

**Input**: Design artifacts in `specs/004-optional-postgresql/`.

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`,
`contracts/postgresql.md`, `quickstart.md`, and constitution v2.1.0.

**Organization**: Setup, shared foundation, four P1 user stories, then
cross-cutting delivery. Tests are required by the feature specification.
Write regression tests before their implementation and record the initial
failure where feasible. Check tasks only after their observable result passes.

## Format and scope

- Every task uses a checkbox, sequential ID, optional `[P]`, and `[USn]` in
  story phases. `[P]` allows parallel work only after stated prerequisites
  and only on distinct files.
- Paths are repository-relative; `Azure/AI-Landing-Zones:` qualifies central
  documentation source, not a local directory in this repository.
- Existing bundled runtimes, Cosmos, platform outputs v1 and manifest pins
  are not implementation targets.
- No deployment, release or destructive cleanup is authorized by this task
  file. Azure acceptance tasks require explicit approval and a validation scope.
- The latest requester direction excludes Azure validation from this delivery.
  T039/T040 remain visible but are separate, unexecuted acceptance work; they
  do not block the requested offline implementation/handoff and are not checked.
- Do not equate compiled templates or mocked plans with deployed parity.

## Phase 1: Setup

**Purpose**: Resolve delivery gates and verify the existing project/tooling.

- [x] T001 Reconcile issue #864 with the selected public-Basic/private-isolated and fresh-only scope; record maintainer review/decision status in `docs/adr/ADR-0039-optional-application-postgresql.md` and `specs/004-optional-postgresql/spec.md` without inventing approval.
- [X] T002 Verify the feature branch derives from develop, scoped instructions, real commands, and ignored state/private inputs in `.gitignore` and `infra/terraform/.terraformignore`; preserve tracked `infra/terraform/.terraform.lock.hcl`, adding only missing critical ignore patterns and recording unavailable tooling in `specs/004-optional-postgresql/quickstart.md`.

**Checkpoint**: Scope and architecture gate reviewed; no unrelated setup,
new testing framework or dependency installation.

## Phase 2: Foundational prerequisites

**Purpose**: Shared typed inputs, explicit module mappings and server identity.

- [x] T003 Add input/default/invalid-value regression cases in `tests/test_deployment_inputs.py` for every field in `specs/004-optional-postgresql/contracts/postgresql.md`, strict enablement Booleans, required enabled administrator, incompatible tier/SKU/HA, storage/backup bounds and forbidden broad IPv4 rules.
- [x] T004 Implement matching native/environment inputs in `main.parameters.json`, `infra/bicep/main.parameters.json`, `config/deployment/input_types.py` and `config/deployment/composition.py`; use typed PostgreSQL validation in `config/deployment/postgresql.py`, keep disabled selection a no-op, and never silently choose a replacement SKU or HA mode.
- [X] T005 Verify exact AVM schemas/pins and transitive compatibility before module wiring in `infra/bicep/main.bicep`, `infra/terraform/versions.tf` and `infra/terraform/.terraform.lock.hcl`: Bicep PostgreSQL 0.16.1 and Terraform PostgreSQL 0.2.3; preserve exact provider pins and readonly lock, and document the preview-API policy gate in `specs/004-optional-postgresql/research.md`.
- [X] T006 [P] Add compiled optional-server tests in `infra/tests/contracts/Test-PostgreSqlContract.ps1` covering explicit Entra-only/no dummy password, application-RG ownership, configured administrator, database, economical defaults, output identity and no foundation-owned protection lock.
- [X] T007 [P] Add matching Terraform server/default tests in `infra/terraform/tests/postgresql.tftest.hcl`, including tier-prefix SKU conversion, GiB-to-MiB storage, null HA when disabled, explicit geo-backup/authentication, administrator identity and absent module-owned lock.
- [X] T008 Implement equivalent conditional server/database/admin modules in `infra/bicep/main.bicep`, `infra/terraform/main.postgresql.tf`, `infra/terraform/variables.postgresql.tf` and `infra/terraform/outputs.tf`; preserve the complete 64-output Bicep interface and use shared verified post-provision azd metadata per ADR-0039; reuse both roots' naming/resource-group conventions.

**Checkpoint**: T003-T008 pass with enabled/disabled fixtures; provider resource
identities and verified azd metadata are stable inputs for all later stories.
Foundation modules do not create the independently owned deletion lock.

## Phase 3: US1 - Keep the standard deployment unchanged (P1)

**Goal**: Default-off PostgreSQL adds no feature resources or discovery keys.

**Independent test**: Compare default/disabled resource graphs, composition
and publication with the develop baseline, for both network modes/providers.

- [X] T009 [P] [US1] Extend `infra/tests/contracts/Test-PostgreSqlContract.ps1` to assert no PostgreSQL server/database/admin/firewall/PE/DNS/NAT/public-IP/lock and no new ACA VNet integration when disabled; preserve current shared and Foundry resources.
- [X] T010 [P] [US1] Extend `infra/terraform/tests/postgresql.tftest.hcl` and `infra/terraform/tests/compute.tftest.hcl` with equivalent disabled/default resource/output assertions, empty PostgreSQL native outputs and unchanged current application composition.
- [x] T011 [US1] Add publication no-op and closed-v1 regression cases in `tests/test_platform_outputs.py`, and keep `config/deployment/outputs.py` from publishing PostgreSQL keys when disabled without editing `contracts/platform-outputs-v1.schema.json`.
- [X] T012 [US1] Run focused input/output/compiled-provider checks from `specs/004-optional-postgresql/quickstart.md`; record exact disabled baseline evidence and any remaining regressions there, fixing only feature-related failures.

**Checkpoint**: Safe default-off foundation increment. This is not a usable
enabled PostgreSQL release; all P1 stories and protection gates still apply.

## Phase 4: US2 - Use PostgreSQL from a Basic Container App (P1)

**Goal**: Fresh externally accessible ACA uses fixed public NAT egress and
PostgreSQL permits only that source plus explicit operator ranges.

**Independent test**: Inspect paired network/firewall contracts first; after
US4 and deployment approval, verify actual app source IP and positive/negative
SQL access in a fresh Basic environment for each provider.

- [X] T013 [P] [US2] Add Basic subnet/delegation/Standard NAT/public-IP/external-ingress/firewall dependency cases to `infra/tests/contracts/Test-PostgreSqlContract.ps1`, distinguishing outbound NAT IP from ACA ingress IP and preserving jumpbox NAT.
- [X] T014 [P] [US2] Add equivalent Basic graph cases in `infra/terraform/tests/postgresql.tftest.hcl`, `infra/terraform/tests/networking.tftest.hcl` and `infra/terraform/tests/compute.tftest.hcl`; verify no application-runtime or SQL-bootstrap dependency cycles.
- [X] T015 [US2] Test and implement Basic prerequisites and normalized explicit operator IPv4/CIDR ranges in `tests/test_postgresql_deployment.py`, `config/deployment/postgresql.py` and `scripts/infra/Invoke-PreflightChecks.ps1`; require fresh workload-profiles ACA, valid delegated subnet capacity, and reject legacy Consumption-only and conflicting forced default routes without broad Azure-services access.
- [X] T016 [P] [US2] Implement dedicated Standard ACA NAT/public IP/subnet association and the effective Basic PostgreSQL ACA VNet-integration condition in `infra/bicep/main.bicep`, preserving external ingress and all disabled and isolated defaults.
- [X] T017 [P] [US2] Implement the matching conditional ACA NAT/public IP/subnet association and external-ACA VNet configuration in `infra/terraform/main.networking.tf` and `infra/terraform/main.compute.tf`, without reusing jumpbox NAT or overriding corporate routes.
- [X] T018 [US2] Wire exact NAT-IP plus explicit operator-range PostgreSQL firewall rules and verified `CONTAINER_APPS_POSTGRESQL_EGRESS_IP` azd metadata through the common adapter; retain Terraform's additive native output and Bicep's complete legacy output set; prohibit all-address and Azure-services 0.0.0.0 exception rules.
- [X] T019 [US2] Execute Basic compiled/Terraform/preflight regression cases from `specs/004-optional-postgresql/quickstart.md` and verify subnet-before-ACA and NAT-IP-before-firewall dependency order; retain no-op US1 evidence.

**Checkpoint**: Paired Basic topology validates offline. Do not deploy or claim
app SQL access until US4 protection/bootstrap and approved live evidence.

## Phase 5: US3 - Use PostgreSQL privately (P1)

**Goal**: Isolated PostgreSQL uses app PE subnet/private DNS with public access
disabled and no PostgreSQL delegated-server subnet.

**Independent test**: Validate each DNS ownership path in both providers;
after US4/approval, observe private DNS and private SQL access plus public denial.

- [X] T020 [P] [US3] Add isolated PE/subresource/app-subnet/zone/public-disabled/zero-dedicated-ACA-NAT cases in `infra/tests/contracts/Test-PostgreSqlContract.ps1`, including managed, existing and policy-managed DNS.
- [X] T021 [P] [US3] Add equivalent isolated resource and DNS ownership cases in `infra/terraform/tests/postgresql.tftest.hcl` and `infra/terraform/tests/networking.tftest.hcl`; assert absent delegated PostgreSQL networking.
- [X] T022 [US3] Implement conditional PostgreSQL PE and `privatelink.postgres.database.azure.com` integration in `infra/bicep/main.bicep` and `infra/terraform/main.networking.tf`; preserve existing network RG/subscription/link ownership, existing-zone IDs and policy-managed DNS without duplicates.
- [X] T023 [US3] Extend `tests/test_postgresql_deployment.py`, `config/deployment/postgresql.py` and `scripts/infra/Invoke-PreflightChecks.ps1` to validate private subnet/DNS ownership, reject competing DNS modes and surface missing bindings; do not copy delegated-server egress rules into PE networking.
- [X] T024 [US3] Run the paired isolated/default regression checks in `specs/004-optional-postgresql/quickstart.md`, checking endpoint/DNS dependencies and no impact on shared Foundry/ACA/jumpbox networking.

**Checkpoint**: Private path validates offline; DNS convergence and Entra
operation over private access remain live acceptance requirements.

## Phase 6: US4 - Bootstrap and preserve application data (P1)

**Goal**: Manual idempotent OID-bound SQL grants and independent deletion
protection, with no automatic privileged bootstrap or destructive transitions.

**Independent test**: Mock identity/lock/binding/error boundaries, then run
bootstrap twice and exercise CRUD/denials and protected teardown with real
data in approved validation environments.

- [x] T025 [P] [US4] Add lifecycle/binding/lock tests in `tests/test_postgresql_deployment.py` for fresh adoption, unchanged-binding recovery, disabled-after-created, mode/immutable changes, corrupt/missing records, wrong ARM binding, lock permission/readback failure and no premature readiness.
- [x] T026 [P] [US4] Add bootstrap boundary tests in `tests/test_postgresql_bootstrap.py` for argument/tenant/OID/type validation, role conflicts, unsafe identifiers, privileged inherited roles, repeatability, correct DDL-owner defaults, secret-safe errors and cross-database partial failure.
- [x] T027 [US4] Implement non-secret persisted binding, live server/auth/ownership verification and deterministic `agentlz-postgresql-data-protection` CanNotDelete lock creation/readback in `config/deployment/postgresql.py`; keep the lock outside both provider graphs/state and fail before ready publication on incomplete protection.
- [x] T028 [US4] Invoke shared fresh-binding/disable/replacement guards from `scripts/preProvision.ps1` and `scripts/preProvision.sh`, after resolved provider/input identity and before destructive provision; add Windows/POSIX parity coverage in `tests/test_infra_provider_hooks.py`.
- [x] T029 [US4] Invoke protection/readiness verification from `scripts/postProvision.ps1` and `scripts/postProvision.sh` before PostgreSQL discovery publication, without executing SQL bootstrap; extend `tests/test_infra_provider_hooks.py` and `tests/test_postgresql_deployment.py` for ordering and recovery parity.
- [x] T030 [US4] Implement additive host/port/database/verify-full/entra agent-lz publication in `config/deployment/outputs.py`, verified against the protected resource identity; extend `tests/test_platform_outputs.py` for enabled values, failures, disabled no-op and unchanged platform outputs v1.
- [x] T031 [US4] Add PostgreSQL teardown guard before every successful provider branch in `config/deployment/teardown.py`, wire equivalent `scripts/preDown.ps1` and `scripts/preDown.sh` behavior, and test recorded bindings/options cannot bypass protection in `tests/test_postgresql_deployment.py` and `tests/test_infra_provider_hooks.py`.
- [x] T032 [US4] Add pinned `psycopg[binary]==3.3.6` to `util/requirements.txt`, align Azure Identity with configuration requirements, and implement manual CLI/resource/directory/admin-role validation in `util/postgresql_bootstrap.py` using existing AzureCliCredential and verified TLS, bounded timeouts and token-only-in-memory connection parameters.
- [x] T033 [US4] Implement verified OID principal mapping, schema-owner checks, CONNECT/schema USAGE/table CRUD/sequence grants and actual-DDL-owner future privileges in `util/postgresql_bootstrap.py`; reject DDL/admin/ownership or inherited privilege bypass and reuse only exact role mappings without broad duplicate-role catches.
- [X] T034 [US4] Run and fix focused bootstrap/lifecycle/output/hook regressions through existing PowerShell/Bash runners; record idempotency, partial-failure recovery and protection/publication ordering evidence in `specs/004-optional-postgresql/quickstart.md`, distinguishing local Windows/Git Bash from native-Linux CI.

**Checkpoint**: Enabled feature is ready for approved live validation, not
automatically authorized to provision resources or delete data.

## Phase 7: Polish and coordinated delivery

**Purpose**: Operator documentation, complete parity evidence and review.

- [x] T035 Create the optional PostgreSQL enablement/network/auth/bootstrap/removal guide in `Azure/AI-Landing-Zones:docs/agent-landing-zone/postgresql.md` and register it in `Azure/AI-Landing-Zones:mkdocs.yml` on a feature branch; use only implemented keys, defaults and CLI.
- [x] T036 Search and update all affected central pages, including `Azure/AI-Landing-Zones:docs/agent-landing-zone/configuration.md`, `network-isolation.md`, `build-your-own-app.md`, `deploy-bicep.md`, `deploy-terraform.md`, `deployment-operations.md` and `sizing-cost-planner.md`; explain NAT cost, operator source access, fresh-only support, no runtime integration and explicit backup/lock removal, without adding product docs to this repository or redirect pages.
- [X] T037 Include newly added compiled/Python/Terraform and Windows/Linux behavior cases in existing `.github/workflows/infra-validate.yml` runners and verify native azd provider/backend contracts without expanding unrelated CI or dropping compiler/provider pins.
- [X] T038 Run focused and then broader existing checks from `specs/004-optional-postgresql/quickstart.md`: Bicep build/lint/offline contracts, Terraform fmt/readonly init/validate/test and pytest deployment/hook/CLI tests; resolve feature-related failures and preserve `infra/terraform/.terraform.lock.hcl`.
- [ ] T039 **NOT EXECUTED / deferred by latest requester instruction (no Azure deployment validation).** After separate explicit Azure approval, execute disabled and enabled Basic/isolated, BYO/existing/policy DNS, stable NAT source-IP, Entra CRUD and unauthorized network/SQL cases for both providers from `specs/004-optional-postgresql/quickstart.md`; capture sanitized evidence, never invent deployed parity.
- [ ] T040 **NOT EXECUTED / deferred by latest requester instruction (no live/destructive validation or cleanup).** After separate explicit approval, run repeat bootstrap, future-owner grants, disable/replacement/down and direct-deletion denial plus partial-provision recovery; approve exact-resource cleanup only after backup review and preserve shared DNS/RGs.
- [x] T041 Reconcile implemented behavior and evidence across `specs/004-optional-postgresql/spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/postgresql.md`, `quickstart.md` and `docs/adr/ADR-0039-optional-application-postgresql.md`; distinguish completed offline checks, actual live results and blocked/unverified scenarios, and leave unsatisfied tasks unchecked.
- [ ] T042 Prepare the reviewed feature handoff/PR to develop using `specs/004-optional-postgresql/tasks.md`, paired-provider evidence and the central-docs branch/PR; include compatible pins, approved differences, recovery order and residual risks, and never publish a release or alter `manifest.json` runtime/provenance pins for this feature.

**Checkpoint**: All P1 stories, docs and evidence gates satisfied or explicitly
reported blocked. Passing mocks alone does not finish live acceptance tasks.

## Dependencies and execution order

### Phase graph

```text
Setup T001-T002
  -> Foundation T003-T008
     -> US1 T009-T012
        -> US2 T013-T019
        -> US3 T020-T024
           -> US4 T025-T034 integration
              -> Documentation/CI T035-T038
                 -> Offline reconciliation/handoff T041-T042
                    -> Separately approved live evidence T039-T040 (excluded here)
```

US2 and US3 consume the common server contract and can be tested independently
in different environments. Their implementations touch the same provider/preflight
files, so the default executor completes US2 then US3; do not run whole stories
concurrently against the same worktree. US4's test drafting can follow the
foundation, but its hook/publication integration requires both network paths.
All user stories are P1; there is no partial enabled-feature release.

### Task prerequisites

- T003 precedes T004. T005 and the test tasks T006/T007 precede T008.
  T005 validates schemas/pins without creating a feature resource.
- T006 and T007 are independent counterpart test files after T005.
- T009 and T010 are independent after T008; T011 precedes T012.
- T013/T014 are independent after T012. T015 validates the shared network
  input contract before T016/T017; those implementation tasks can run in
  parallel on different providers. T018 integrates their outputs; T019 follows.
- T020/T021 are independent after T019. T022 follows their tests;
  T023 precedes T024.
- T025/T026 are independent after T024. T027 follows T025; T028/T029
  consume it; T030 follows T029. T031 must preserve prior teardown guards.
- T032 follows T026; T033 follows T032; T034 requires T027-T033.
  T026 and SQL implementation do not depend on automatic SQL deployment.
- T035 follows implemented CLI/contracts; T036 follows the registered guide.
  T037/T038 cover all added cases; T039/T040 require finished local checks
  and explicit approval in a separate validation scope; T041/T042 require
  reconciled docs/offline evidence and explicit disclosure of that exclusion.
- Work in shared files is always sequential, including updates to
  `tests/test_postgresql_deployment.py`, output publisher and both root templates.

## Parallel examples

| Story | Parallel batch | Shared prerequisite |
| --- | --- | --- |
| US1 | T009 Bicep disabled tests + T010 Terraform disabled tests | T008 |
| US2 | T013 Bicep graph tests + T014 Terraform graph tests | T012 |
| US2 | T016 Bicep NAT/ACA + T017 Terraform NAT/ACA | T015 and respective failing tests |
| US3 | T020 Bicep private tests + T021 Terraform private tests | T019 |
| US4 | T025 lifecycle tests + T026 manual-bootstrap tests | T024 |

`[P]` is a file/dependency property, not authorization to spawn agents or deploy.

## Implementation strategy

Start with setup/foundation and US1 as the regression-safety MVP: the option
exists, defaults off and preserves shipped behavior. This increment deliberately
does not claim enabled database usability. Deliver Basic and isolated paths,
then integrate protection/discovery and manual bootstrap; validate each story
at its checkpoint. US4 is mandatory before any enabled-feature release.

Central docs remain on their source repository feature branch. Preserve all
provider pins and v1 runtime contracts; use session artifacts for private/live
evidence. Obtain Azure/cleanup approval separately. Do not mark blocked live
tasks complete merely because a mock, compiled contract or PR passed.

## Verified completion ledger

Completed Python/lifecycle/docs tasks above are supported by the exact offline
commands/results in `quickstart.md`: 185 focused tests, 297 consolidated
own-scope/coupled tests plus 82 subtests, the full 65-case
preprovision PowerShell/Bash harness, executed postprovision failure blocks,
teardown checks and the restored-jq environment/private-hook regression run.
The final expanded five-file resource-readback/teardown check passed 239 tests;
it includes seven additional pending-child/ACA/BYO/DNS regressions.
T031 reuses the already-shared preDown entrypoints unchanged; the guard now runs
before either provider path and includes retained local PG metadata.
T032 selects exact driver/binary 3.3.6, available from the configured package
index and matching the tested versions. Initial 3.3.8 restore attempts failed
TLS; no TLS bypass/fallback was added. Azure Identity is aligned at 1.27.0 so
the combined CI manifests resolve without conflicting exact versions.
Native Linux/remote Windows-Linux CI is not inferred from Git Bash on this
Windows host. The complete local PowerShell/Bash harness passed 97 cases and
82 subtests; the full Python regression and both provider offline runners also
passed. T034/T037/T038 refer to this implemented/executed offline scope, not
unexecuted remote CI or Azure acceptance.

Central docs branch: `Azure/AI-Landing-Zones:feature/postgresql-opcional`,
latest commit `50b46aa68c63e6017a1ca979af0229a10dd790f0`, 13 files; all 55
Agent Landing Zone source pages searched and new nav/YAML/links verified.
T036 added links to the provider guide entry pages and updated the actual
Bicep/Terraform guides; the cost redirect remains untouched.

Provider tasks are checked from the completed infrastructure evidence, not
merely the presence of edits: 142 Terraform tests, 19 compiled contract suites,
7 Python interface tests, preserved historical fingerprints and mutation
rejection. ADR-0039 preserves the complete Bicep output interface through the
shared verified metadata adapter. The integrated Python run passed 1496 tests;
the final directly affected files and provider interfaces passed 283 tests
after additional Entra administrative-group inheritance protection and shared
catalog naming. See quickstart for exact commands,
subtests and exclusions. No release, Azure deployment or cleanup was performed.
