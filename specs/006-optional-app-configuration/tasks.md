# Tasks: Optional App Configuration in deployment flows

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts](contracts/deployment-metadata-interface.md)
and [quickstart.md](quickstart.md).

**Branch**: `feature/optional-app-configuration`, based on `develop`.

**Tests**: Required by FR-014, SC-001 through SC-005, SC-007 and constitution
principles V/VI. For new or changed behavior, add focused regressions before
implementation and observe failure for the intended missing behavior.
Complementary acceptance tests in US3/US4 may pass immediately when the
foundational protections already satisfy them. Use synthetic metadata and mocked
Azure boundaries.
No new validation application, runtime/sample rewrite or live reference-app
demonstration is required or authorized by this task list.

**Organization**: Shared contract/source/verification foundations precede five
story phases. Security enforcement belongs in the foundation, not a later
optional hardening pass. US3/US4 provide additional acceptance evidence for
those protections.

## Format: `[ID] [P?] [Story] Description`

- Every executable task starts with `- [ ] Tnnn`.
- `[P]` identifies disjoint-file work eligible for parallel execution only after
  its prerequisites in the dependency table are complete.
- `[US1]` through `[US5]` map to the specification's stories.
- An unchecked task is planned work, not implementation or approval evidence.

## Path Conventions

Paths are relative to the owning repository and use Windows separators.
Unless prefixed with `Azure/AI-Landing-Zones`, paths belong to
`Azure/agent-landing-zone`. Central product documentation must not be copied
into this repository. Proposed new files are explicitly created by their tasks.
Read the applicable `.github\instructions\` rules before changing production
files.

## Phase 1: Setup

**Purpose**: Establish approval, compatibility and setting ownership without
inventing a new project or application.

- [X] T001 Obtain explicit maintainer acceptance of the concrete output/consumer migration in `docs\adr\ADR-0041-provider-owned-deployment-metadata.md` after T002. Record the already selected `DEPLOYMENT_METADATA` direction separately from approval of specific output consolidation/retirement. If migration acceptance is unavailable, stop before Phase 2. Do not self-approve unspecified output removals.
- [X] T002 Inventory current Bicep/Terraform root outputs and their consumers, including hooks, Python modules, contracts, tests, samples and central documentation. Propose the exact consolidation/retirement, old-to-new mappings, consumer changes, mixed-version restrictions and recovery in `docs\adr\ADR-0041-provider-owned-deployment-metadata.md` to make room for a dedicated `DEPLOYMENT_METADATA` output within ARM's 64-output limit. Preserve runtime v1 and hosted handoff semantics. Complete the consumed-key ownership table in `specs\006-optional-app-configuration\contracts\deployment-metadata-interface.md` for Foundry/toolbox, Search, governance, Container Apps, panel and MCP/native setup. Record the original and proposed root-output sets, runtime-v1 schema/hash, manifest combination and pinned tools in `specs\006-optional-app-configuration\quickstart.md`. Do not choose an arbitrary output or alter runtime/sample behavior.

**Checkpoint**: The concrete output/consumer migration is accepted and the
metadata/runtime/secret boundaries are explicit. Direction approval alone and
task generation do not satisfy T001.

## Phase 2: Foundational

**Purpose**: Supply both producers and a fail-closed, typed, independently
verified metadata boundary before migrating any setup consumer.

### Tests and contract

- [X] T003 [P] Create `tests\test_deployment_metadata.py` and synthetic `tests\fixtures\deployment-metadata-v1.json` from the feature-local schema/example. Add failing coverage for the closed versioned shape, managed/referenced/disabled slots, model/app/data-child mappings, system/user-assigned identity shapes, approved provider requests, explicit selection and missing/invalid output failures. Build optional-service variants in memory rather than adding an application fixture.
- [X] T004 [P] Add failing producer/compatibility coverage in `tests\test_terraform_interface.py`, `tests\test_custom_foundation_outputs.py`, `tests\test_native_foundation.py`, `infra\terraform\tests\root.tftest.hcl` and affected consumer suites identified by T002 for the dedicated `DEPLOYMENT_METADATA` output across hosted/classic/custom/software-disabled selections. Assert the approved old-to-new root-output/consumer mappings, at most 64 Bicep outputs, five Terraform PostgreSQL adapter contracts, disabled-service representation and unchanged hosted handoff semantics. Do not retain obsolete root-name assertions or weaken runtime contracts.
- [X] T005 Promote the accepted draft from `specs\006-optional-app-configuration\contracts\deployment-metadata-v1.schema.json` to `contracts\deployment-metadata-v1.schema.json`, set its production identifier/title, generate `contracts\deployment-metadata-v1.schema.json.sha256` from exact committed bytes and register it in `contracts\README.md`. Preserve `contracts\platform-outputs-v1.schema.json` and its integrity file byte-for-byte.

### Producers and transport gate

- [X] T006 [P] Add the dedicated `DEPLOYMENT_METADATA` root output to `infra\bicep\main.bicep` from evaluated resource/module outputs and declared bindings. Apply only the output reorganization accepted in T001 to stay within ARM's 64-output limit. Populate all six contract sections and all resource slots, preserve hosted handoff semantics, and avoid runtime setting bags, guessed model defaults, connection strings or resolved secrets.
- [X] T007 [P] Add the equivalent dedicated `DEPLOYMENT_METADATA` root declaration with explicit literal `sensitive = false` in `infra\terraform\outputs.tf`. Apply the accepted equivalent output reorganization, use evaluated native resource/module values, preserve hosted handoff semantics and PostgreSQL adapter contracts, and do not use `nonsensitive()` or alter provider locks/module pins.
- [X] T008 Apply the approved old-to-new output-consumer mappings from T002 in every affected repository-owned consumer and prove compatibility using its identified suites plus `tests\test_terraform_interface.py`, `tests\test_hosted_prepare.py`, `tests\test_hosted_access.py` and `tests\test_native_foundation.py`. Prove the dedicated output's native JSON serialization, persisted azd-value decoding where present and output-size budget with pinned tools before setup consumers adopt the new loader. Record results and mixed-version/recovery constraints in `specs\006-optional-app-configuration\quickstart.md`. Stop and revisit ADR-0041 if migration or transport cannot be established. Do not restore a hosted wrapper, local-artifact fallback or change runtime/sample behavior.

### Shared source and verification

- [X] T009 [P] Add a verified compatible, pinned `python-hcl2` dependency to `config\requirements.txt` for root-output declaration inspection, following the existing exact-version convention. Restore the configuration dependencies with the existing command in `specs\006-optional-app-configuration\quickstart.md` only after that manifest change.
- [X] T010 Implement typed candidate loading in new `config\deployment\metadata.py`, reusing `config\deployment\provider.py`, `resolution.py`, `egress.selected_environment`, `resource_groups.py` and `context.py`. Bind the explicit environment, original declared inputs, subscription/groups and Bicep deployment locator independently of the payload. Query only `properties.outputs.DEPLOYMENT_METADATA.value` and a separate bounded deployment-success projection, with one metadata-value request per invocation and no App Configuration client.
- [X] T011 Implement the Terraform source adapter in `config\deployment\metadata.py`: validate the native selected provider directory and existing environment backend binding, parse root HCL with `python-hcl2`, and require exactly one approved output with literal false sensitivity before invoking `terraform output -json DEPLOYMENT_METADATA`. Consume the closed object directly without a hosted wrapper. Reject missing/true/nonliteral/malformed declarations and unavailable/mismatched backends without raw-state, bulk-output, generated-tfvars or store fallback.
- [X] T012 Implement schema, selected-input and live-resource verification in `config\deployment\metadata.py`, reusing existing ARM/group/endpoint helpers. Verify tenant/subscription/groups, application/mode/deployment, expected resource types/parents/names, declared external ownership, exact Foundry account/project endpoint, model/app/data mappings and selected principal/client bindings. Reject stale overlapping saved aliases or cached metadata structurally, preserve supported normalization and specialized handoff validation, and distinguish disabled resources from missing enabled resources before any dependent mutation.
- [X] T013 Expose the read-only `--check --environment` entry point with optional `--project-root` and `--input` in `config\deployment\metadata.py`. Return typed verified contexts to Python callers, scope live checks to the selected operation, use configured logging with redacted field/category failures and bounded existing retry/timeout behavior, and re-read/verify on every independent invocation. Do not dump metadata, set global environment state or persist a verified flag.
- [X] T014 [P] Create `tests\test_deployment_setup_settings.py` with failing cases for typed declared defaults, resource-derived legacy mappings, explicit preference ownership, setting conflicts, required/disabled services, unsupported store-dependent feature selection and modes `containerEnv`, `appConfig` and `none`. Assert preferences cannot replace resource IDs/endpoints/identities and no store client is constructed in store-free resolution.
- [X] T015 Implement focused `config\deployment\setup_settings.py` using T002's explicit consumed-key classification, the verified context and existing typed/ownership helpers. Supply in-memory legacy setup shapes such as `MODEL_DEPLOYMENTS` and `CONTAINER_APPS`, preserve allowlisted appConfig operational preferences with their existing owners, expose required-service/prerequisite decisions to consumers, and keep secret values and arbitrary runtime settings out of deployment metadata.

**Checkpoint**: Both producers, native transport and secure shared resolution
are ready. Existing runtime v1 and handoff readers still work. No consumer may
use an unchecked payload or a store fallback while later safety tests are pending.

## Phase 3: User Story 1 - Complete deployment without a configuration store (P1)

**Goal**: Complete selected platform setup and deploy-hook work without creating
or accessing a store in `containerEnv`.

**Independent Test**: Exercise both providers with `deployAppConfig=false` and
`APP_RUNTIME_CONFIGURATION_MODE=containerEnv`. Fail on every store-client
construction or store CLI/SDK request, assert actual selected setup calls and
targets, execute both hook variants, then run a separate deploy invocation twice
using only persisted selection/native-output fixtures. No application deployment
or health endpoint is a substitute for these observations.

### Tests

- [X] T016 [P] [US1] Add failing four-boundary Bicep/Terraform provision-output and deploy-hook cases in `tests\test_infra_provider_hooks.py`, `tests\test_deploy_environment.py` and `tests\test_provision_rerun.py`. Execute shipped hook blocks with the existing PowerShell/Bash harness style, record delegated commands/order/nonzero propagation, deny store requests, and cover independent processes plus two unchanged-input deploy runs without prior transient values.
- [X] T017 [P] [US1] Add failing no-store selected-operation tests in `tests\test_aifoundry_setup.py`, `tests\test_knowledge_toolbox.py` and `config\search\tests\test_foundry_iq_templates.py`. Assert actual RAI/evaluation-vault, model/connection/toolbox and template-rendered Search/Foundry IQ operations with verified IDs, rather than only successful guards or mocked top-level returns.
- [X] T018 [P] [US1] Add failing service-boundary tests in `config\governance\tests\test_setup.py`, `tests\test_panel_setup.py` and new `tests\test_containerapps_setup.py`. Cover audit HMAC Key Vault creation/reuse and reference delivery, selected Cosmos database binding, and exact app/registry/identity configuration while rejecting store discovery.
- [X] T019 [P] [US1] Add failing runtime-aware role and probe cases in `tests\test_app_definition_roles.py`, `tests\test_private_network.py` and `tests\test_private_network_hooks.py`. Disabled stores must not cause reader grants or probes, required ACR/other grants and private DNS/TLS/runner checks must remain, and genuine incompatible feature prerequisites must fail explicitly.
- [X] T020 [P] [US1] Add failing metadata-only discovery cases in `tests\test_mcp_component.py`, `tests\test_native_application.py`, `tests\test_native_knowledge_connection.py` and `tests\test_hosted_prepare.py`. Distinguish resource lookup from genuine selected store/Entra retry state, and preserve Durable Task, workload egress, private-build and hosted/native handoff behavior.

### Implementation

- [X] T021 [P] [US1] Migrate `config\aifoundry\setup.py`, `config\aifoundry\keyvault.py` and `config\aifoundry\toolbox.py` to verified metadata/setup settings for account, project, model, Search, vault and connection discovery. Preserve selected RAI, evaluation-secret and toolbox operations and direct-entry verification. Absence of the store must not skip required setup.
- [X] T022 [P] [US1] Migrate `config\search\setup.py` from bulk store hydration to verified metadata plus declared setup settings. Preserve StrictUndefined template rendering, required model validation and selected Search/Foundry IQ/MCP provisioning. Compute derived settings in memory before optional runtime publication instead of making a write to the store a setup prerequisite.
- [X] T023 [P] [US1] Migrate `config\containerapps\setup.py` and `config\containerapps\registry.py` to verified selected app, registry and managed-identity mappings. Preserve registry/auth configuration and existing permissions without endpoint/name guessing or store reads.
- [X] T024 [P] [US1] Decouple selected audit HMAC secret creation/reuse in `config\governance\setup.py` from store publication. Obtain resource destinations through the shared context, keep legitimate Key Vault operations mandatory and pass only secret references to subsequent configuration.
- [X] T025 [P] [US1] Replace Cosmos account/database discovery fallback in `config\panel\setup.py` with verified resource and named data-child metadata. Preserve selected panel setup and its authorization requirements without requiring a store or accepting an undeclared account.
- [X] T026 [P] [US1] Replace resource-discovery fallback in `config\deployment\mcp.py`, `config\deployment\native_access.py`, `config\deployment\native.py`, `config\deployment\hosted_prepare.py` and `config\deployment\hosted_access.py` with the shared verified context. Preserve genuine selected store-owned state, Entra retries, owner access rules and specialized handoff checks, and reject incompatible selections instead of silently disabling them.
- [X] T027 [P] [US1] Make implicit App Configuration reader requirements mode-aware in `config\appdefinition\profiles.py` and `config\appdefinition\roles.py`, retaining required ACR/other access and explicit profile prerequisites. Assess matching grants in `infra\bicep\main.bicep` and `infra\terraform\main.identity.tf`, update both affected providers or document/test the counterpart's existing equivalent behavior, and do not add bypass privileges.
- [X] T028 [P] [US1] Select connectivity probes from verified required-service decisions in `config\deployment\private_network.py`. Remove only the implicit store dependency, preserve registry/Foundry/scheduler/egress/private-runner safeguards and visible existing deferral behavior, and ensure directly invoked checks also validate their destinations.
- [X] T029 [P] [US1] Separate foundation discovery/verification from runtime publication in `config\deployment\outputs.py`. Replace unconditional store guards and hydration with the shared metadata boundary, preserve existing runtime-v1 builders/consumer semantics, and do not require or fabricate an App Configuration endpoint for store-free foundation readiness.
- [X] T030 [P] [US1] Wire `scripts\postProvision.ps1` and `scripts\postProvision.sh` to verify metadata before PostgreSQL protection, RBAC, egress, publication or selected setup mutations. Replace relevant PowerShell-only flat discovery/model-default seeding with shared Python resolution, invoke all selected service modules, preserve visible private deferral, and propagate every required-step failure.
- [X] T031 [P] [US1] Wire `scripts\preDeploy.ps1` and `scripts\preDeploy.sh` to verify metadata and actual feature prerequisites before builds, registration, application or feature mutations. Preserve explicit environment reuse across component checkouts, safe path quoting, retry/failure semantics and the selected mode without a prior post-provision process.
- [X] T032 [US1] Run T016-T020's focused regressions and selected-mode cases in `tests\test_deployment_modes.py`, `tests\test_optional_ingestion.py` and `tests\test_resource_group_consumers.py`. Record commands and observed service/target coverage in `specs\006-optional-app-configuration\quickstart.md`, proving zero store requests, no missing-required-step skips and separate/repeated invocation behavior for both providers and shells.

**Checkpoint / MVP**: The store-free platform path is independently testable
after Phase 2 and US1. This is an engineering MVP, not approval to release:
remaining P1 compatibility/security evidence and coordinated documentation are
still required. Cloud parity and application readiness remain unverified.

## Phase 4: User Story 2 - Keep centralized runtime configuration working (P1)

**Goal**: Preserve default `appConfig` runtime settings, feature flags, access
and secret references while using provider metadata for deployment discovery.

**Independent Test**: Run both providers' `appConfig` provision/deploy boundaries
with a verified store and assert unchanged runtime-v1/flat-key publication,
`agent-lz`, setting ownership, feature flags and Key Vault-reference semantics.
Permit only owner-approved runtime store operations, never metadata hydration.
Also cover `containerEnv` with a provisioned store, `none`, and missing/unusable
store failure before dependent changes. Runtime behavior is checked through
existing publication/consumer contracts, not an unauthorized live app run.

### Tests

- [X] T033 [P] [US2] Add failing metadata-versus-runtime ownership regressions in `tests\test_platform_outputs.py`, `tests\test_appconfig_intent.py` and `tests\test_appconfig_seed.py`. Assert unchanged runtime schema/hash, flat keys and label, seed-only/user-owned behavior, feature flags, secret references and output-derived destinations for both providers.
- [X] T034 [P] [US2] Add failing mode/prerequisite cases in `tests\test_app_settings_resolution.py`, `tests\test_deployment_modes.py` and `tests\test_native_application.py`. Cover default appConfig, missing/wrong/unusable store before mutation, containerEnv with a store, no-injection `none`, and hosted/native publication overlays that remain separate from the dedicated metadata output. Exercise independent processes and two unchanged-input deploy runs in each provider's appConfig case, retaining user settings/flags/references.

### Implementation

- [X] T035 [US2] Build existing runtime publication from verified destinations in `config\deployment\outputs.py` and `config\deployment\appconfig.py`. Verify the exact selected store before its legitimate runtime operations and preserve `AGENTLZ_PLATFORM_OUTPUTS`, all supported flat discovery keys, `agent-lz`, feature flags and Key Vault references without changing runtime v1 or reading infrastructure metadata from the store.
- [X] T036 [P] [US2] Preserve explicit intent, seed-only updates and user-owned operational preferences in `config\deployment\appconfig_intent.py`, `config\deployment\appconfig_seed.py` and `config\deployment\app_settings.py`. Gate runtime store operations on actual selection, retain declared defaults and curated containerEnv/reference delivery, and leave `none` without new injection.
- [X] T037 [P] [US2] Preserve hosted/native publication overlay behavior in `config\deployment\native_deploy.py` and existing hosted handoff semantics. Keep mutable routed-agent publication separate from the independent `DEPLOYMENT_METADATA` output and its immutable comparisons. Retain genuine appConfig registration/retry behavior.
- [X] T038 [P] [US2] Preserve existing appConfig migration and publication ownership for derived Search settings and audit references in `config\search\setup.py` and `config\governance\setup.py`. Publish only for a selected runtime consumer, retain allowed operational preferences, and never let those reads replace provider resource/model/identity metadata.
- [X] T039 [US2] Run T033/T034's compatibility matrix with `tests\test_platform_outputs.py`, `tests\test_appconfig_intent.py`, `tests\test_appconfig_seed.py`, `tests\test_app_settings_resolution.py`, `tests\test_deployment_modes.py` and `tests\test_native_application.py`. Record permitted runtime calls separately from forbidden discovery calls in `specs\006-optional-app-configuration\quickstart.md`, including separate/repeated appConfig invocations, the unchanged default and both additional mode cases.

**Checkpoint**: Default centralized runtime behavior remains supported in both
providers. Store presence never implicitly selects that mode.

## Phase 5: User Story 3 - Refuse an unsafe or incomplete destination (P1)

**Goal**: Demonstrate that malformed, stale, conflicting or unverifiable targets
cannot reach dependent mutations, including direct service entry points.

**Independent Test**: Parameterize both providers/modes with invalid context,
metadata and live responses. Assert actionable redacted errors and zero
dependent mutation calls. Include permission/connectivity failures and explicit
private deferral, which must not be reported as completed setup.

### Tests

- [X] T040 [P] [US3] Extend `tests\test_deployment_metadata.py` with the complete negative matrix from `specs\006-optional-app-configuration\quickstart.md`: wrong environment/provider/mode/application/deployment/tenant/subscription/group, stale cached output/aliases, malformed/unknown schema, wrong type/parent/ID despite matching names, undeclared external scope, duplicate or missing selected mappings, incorrect principals/client IDs and exact Foundry endpoint mismatch. Assert no store fallback or dependent mutation.
- [X] T041 [P] [US3] Extend executed hook-ordering cases in `tests\test_infra_provider_hooks.py` and `tests\test_private_network_hooks.py` for failed/partial provisioning, forbidden/DNS/TLS/timeout checks and explicit private deferral. Prove metadata rejection precedes PostgreSQL protection, roles, egress, builds, registration, publication and selected setup in both shells.
- [X] T042 [P] [US3] Add direct-entry destination regressions in `tests\test_resource_group_consumers.py` and `tests\test_app_definition_binding.py`. Invoke selected setup/role entry points with wrong group/resource/project/identity bindings and verify that importing a module directly or reusing a saved snapshot cannot bypass live verification or alter another environment.

### Integration and evidence

- [X] T043 [US3] Standardize field/category-specific corrective actions in `config\deployment\metadata.py` and their propagation through `config\deployment\setup_settings.py` for missing old output, unsupported contract, stale aliases, source approval, live binding, access/connectivity and feature prerequisites. Preserve the foundation's fail-closed guards and redaction, distinguish refresh from same-provider reprovision, and do not log embedded candidate values.
- [X] T044 [US3] Run T040-T042 and relevant `tests\test_resource_groups.py`/`tests\test_private_network.py` cases against the migrated entry points. Record zero-dependent-mutation observations and any unavailable runner/topology coverage in `specs\006-optional-app-configuration\quickstart.md`, including successful approved shared-resource cases and disabled-resource cases that must not suppress required checks.

**Checkpoint**: Validation failure is distinguishable from setup success, and
the operator receives a supported recovery action without destination guessing.

## Phase 6: User Story 4 - Discover resources without exposing secrets (P1)

**Goal**: Restrict metadata retrieval to approved non-secret outputs and retain
the existing Key Vault/least-privilege boundary.

**Independent Test**: Mix approved metadata with unrelated/sensitive output
fixtures. Inspect requested commands, captured diagnostics and persisted files.
Reject sensitive declarations before value retrieval and secret-bearing
candidates without disclosure. Permission-denied secret/setup operations must
remain denied without new grants.

### Tests

- [X] T045 [P] [US4] Add confidentiality/source-preflight cases in `tests\test_deployment_metadata.py` for missing/duplicate/true/nonliteral/malformed sensitivity declarations, unrelated sensitive outputs, unapproved names, credentialed/query-bearing endpoints and provider failures containing secret canaries. Assert no value request for rejected sources, no bulk output/state/show/environment dump, and no secret in logs, stdout/stderr or persistent artifacts.
- [X] T046 [P] [US4] Add producer non-secret regressions in `tests\test_terraform_interface.py` and `infra\terraform\tests\root.tftest.hcl`, inspecting the approved output and its metadata derivation for prohibited declassification/secret-bearing dependencies. Exercise the closed contract for both providers and preserve Terraform's own sensitivity propagation rather than relying on a self-reported payload flag.
- [X] T047 [P] [US4] Add least-privilege and secret-reference cases in `config\governance\tests\test_setup.py`, `tests\test_aifoundry_setup.py` and `tests\test_app_definition_roles.py`. Prove legitimate HMAC/evaluation Key Vault create/reuse/reference paths still run when selected, values never enter metadata/publication diagnostics, and denied target/vault access cannot trigger broader role assignments.

### Integration and evidence

- [X] T048 [US4] Constrain provider-command failure handling and candidate lifetime in `config\deployment\metadata.py`: sanitize subprocess/SDK errors through the typed diagnostic path, avoid payload representations in exception messages, and never persist raw responses, full environment values or state. Preserve the exact approved request/preflight contract and do not attempt to detect arbitrary disguised secrets with schema validation alone.
- [X] T049 [US4] Run T045-T047 plus the named-output/backend regressions in `tests\test_terraform_backend.py` and `tests\test_terraform_interface.py`. Record requested-output and disclosure/denied-access observations in `specs\006-optional-app-configuration\quickstart.md`, distinguishing native Terraform backend use from prohibited deployment-code state inspection.

**Checkpoint**: Source approval, producer sensitivity, closed fields, redaction
and existing secret access controls jointly enforce the boundary. A schema by
itself is not proof that arbitrary content is non-secret.

## Phase 7: User Story 5 - Understand and recover the deployment configuration (P2)

**Goal**: Provide current central guidance for configuration categories, supported
selections, provenance, permissions and same-provider recovery.

**Independent Test**: Review each documented provider/mode journey against the
implemented CLI and regression evidence. An operator must identify input,
metadata, runtime and secret authorities without manually copying infrastructure
values into a store or using undocumented steps. This is a documentation review,
not a requirement to deploy a reference application.

### Documentation discovery and updates

- [X] T050 [US5] Search the complete `Azure/AI-Landing-Zones` source on `main` for `deployAppConfig`, `APP_CONFIG_ENDPOINT`, `APP_RUNTIME_CONFIGURATION_MODE`, `DEPLOYMENT_METADATA`, `HOSTED_AGENT_DEPLOYMENT`, every reorganized output identified by T002, runtime outputs and metadata/recovery terminology. Record affected exact paths and the source revision in `specs\006-optional-app-configuration\quickstart.md`. Use the confirmed pages below as a minimum, not a complete search result.
- [X] T051 [P] [US5] Update `Azure/AI-Landing-Zones` pages `docs\agent-landing-zone\configuration.md`, `docs\agent-landing-zone\application-settings.md` and `docs\agent-landing-zone\build-your-own-app.md` for the four configuration categories, mode/store combinations, output provenance, runtime-v1 separation and genuine store-dependent features. Keep current samples explicitly store-dependent and describe latest shipped behavior without release-comparison blocks.
- [X] T052 [P] [US5] Update `Azure/AI-Landing-Zones` pages `docs\agent-landing-zone\deploy-bicep.md`, `docs\agent-landing-zone\deploy-full-stack.md`, `docs\agent-landing-zone\deploy-infra-only.md`, `docs\agent-landing-zone\deploy-terraform.md`, `docs\agent-landing-zone\deploy-terraform-full-stack.md` and `docs\agent-landing-zone\deploy-terraform-infra-only.md` for approved output delivery, original input/group/backend binding, read/configuration permissions and equivalent selected setup. Update any additional affected provider guide found by T050.
- [X] T053 [P] [US5] Update `Azure/AI-Landing-Zones` pages `docs\agent-landing-zone\deployment-operations.md`, `docs\agent-landing-zone\troubleshooting.md` and `docs\agent-landing-zone\private-access.md` with `metadata --check`, stale-cache refresh, missing-output same-provider reprovision, preserved backend/ownership and permission/connectivity repair. Explain that store deletion/in-place mode conversion is not included and old store-dependent hooks are not a safe store-free rollback.
- [X] T054 [US5] Align the implemented contract/adoption references in `contracts\README.md` and `specs\006-optional-app-configuration\contracts\deployment-metadata-interface.md` with the actual schema, CLI and owners. Link to the central guidance rather than duplicating product documentation, and ensure unchanged runtime v1 and absent runtime/component pin changes are explicit.
- [X] T055 [US5] Validate all T050-identified central pages, command examples and links against implemented modes, errors and regression scenarios. Use the actual documentation validation commands, update `Azure/AI-Landing-Zones` `mkdocs.yml` only if a page is added, and record the coordinated documentation revision in `specs\006-optional-app-configuration\quickstart.md`. Keep test results and evidence limitations in the feature validation record and engineering handoff, not generic validation-status warnings on product pages. Do not publish planned support before the matching implementation is delivered.

**Checkpoint**: Guidance matches delivered behavior, includes every affected
page and does not imply store-free support in unchanged applications.

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Consolidate implementation evidence and a reviewable coordinated
handoff without a release, Azure mutation or new application.

- [X] T056 [P] Run the focused Python/service/hook suites listed in `specs\006-optional-app-configuration\quickstart.md`, including new `tests\test_deployment_metadata.py`, `tests\test_deployment_setup_settings.py` and `tests\test_containerapps_setup.py`. Exercise PowerShell and Bash on supported runners, distinguish missing prerequisites from passes, and broaden to CI's full `tests` suite only when needed with its manifest-matched UI/PYTHONPATH prerequisites.
- [X] T057 [P] Run the existing pinned Bicep build/lint commands against `infra\bicep\main.bicep` with a unique temporary compilation output, then `pwsh -NoProfile -File infra\tests\Invoke-OfflineContracts.ps1`. Remove only the named temporary output and retain compiled-contract results without claiming deployed Azure parity.
- [X] T058 [P] From `infra\terraform`, run `terraform fmt -check -recursive`, `terraform init -backend=false -lockfile=readonly`, `terraform validate` and `terraform test`. Preserve `infra\terraform\.terraform.lock.hcl`, explicit module pins and existing backend bindings, and do not initialize a live remote backend or inspect raw state.
- [X] T059 Consolidate source/documentation revisions, manifest combination, tool versions, exact commands/results, four primary rows, additional modes, selected service calls, both hook variants, approved provider differences and unverified scenarios in `specs\006-optional-app-configuration\quickstart.md`. Separate simulation/compilation from cloud parity, private-topology operation and application readiness, with no fabricated live evidence.
- [X] T060 Prepare the feature handoff targeting `develop` under `.github\copilot-instructions.md`, checking `manifest.json`, `contracts\platform-outputs-v1.schema.json`, its hash and `infra\terraform\.terraform.lock.hcl` against T002's baseline. Report both-provider changes or justified tested non-impact, documentation revision, migration/roll-forward constraints and residual risks. Confirm no runtime/sample rewrite, added application, unapproved provenance/pin change, secret or private validation environment name is included.

## Dependencies & Execution Order

### Phase and story graph

```text
Phase 1: approval + compatibility/ownership baseline
  -> Phase 2: contract + both producers + transport gate + verified resolver
    -> US1: all selected store-free consumers and hooks
      -> US2: appConfig compatibility and mode evidence
      -> US3: destination/direct-entry safety evidence
      -> US4: source/confidentiality evidence
    US1 + US2 + US3 + US4
      -> US5: coordinated, current operator documentation
        -> Phase 8: final evidence and handoff
```

US2-US4 consume the integrated path but have independently runnable acceptance
selectors. Do not defer core security to them. Shared-file scheduling edges
below serialize edits to the loader, hook tests and service tests even where
the stories have no additional conceptual dependency. This is one coordinated
platform change, not separately releasable one-provider or partial-consumer work.

### Task prerequisites

An entry listing a range applies to every task in that range. Prerequisites are
task completion, not just starting the phase. `[P]` never overrides this table.

| Task(s) | Prerequisites / scheduling constraint |
| --- | --- |
| T002 | Existing spec/plan and maintainer-selected neutral-output direction |
| T001 | T002's concrete output/consumer migration proposal |
| T003, T004 | T001 and T002 |
| T005 | T003 and T004 have reproduced their relevant failures |
| T006, T007 | T005 |
| T008 | T006 and T007 |
| T009 | T001 and T002. Independent of producer implementation |
| T010 | T003, T005 and T009 |
| T011 | T010 |
| T012 | T011 |
| T013 | T012 |
| T014 | T002 and T003. Independent of loader implementation |
| T015 | T013 and T014 |
| T016-T020 | T003-T015 (all of Phase 2), including T008's transport gate |
| T021-T029 | T016-T020 have reproduced relevant failures. Source files are disjoint within this implementation wave |
| T030 | T021-T029 |
| T031 | T021-T029. Disjoint from T030 |
| T032 | T030 and T031 |
| T033, T034 | T032 |
| T035 | T033 and T034 |
| T036-T038 | T035. Disjoint source files within this wave |
| T039 | T036-T038 |
| T040-T042 | T032. May overlap US2 only with exclusive ownership of shared test files |
| T043 | T040-T042 and T039. Serializes shared metadata/setup policy work after runtime compatibility |
| T044 | T043 |
| T045-T047 | T044. Serializes loader, role and service test edits |
| T048 | T045-T047 |
| T049 | T048 |
| T050 | T032, T039, T044 and T049 |
| T051-T053 | T050. Separate central page sets |
| T054 | T051-T053 |
| T055 | T054 |
| T056-T058 | T055. Independent checks with separate outputs, no shared evidence-file edits |
| T059 | T056-T058 have completed or have explicit blocked/unverified results |
| T060 | T059. A blocked required check remains a handoff blocker, not a pass |

### Within each story

Tests for new or changed behavior precede the relevant implementation and must
fail for the intended missing behavior, not merely an unavailable dependency.
Complementary acceptance tests in US3/US4 may pass immediately when the
foundational protections already satisfy them. Do not weaken, remove or defer
those protections to manufacture a failing test. Reuse shared metadata validation
rather than copying checks into each consumer. Run the narrow affected suites
after each coherent change before final combined checks.

Capture final results in T059 without making parallel validation tasks edit the
same evidence file. Do not mark an acceptance task done when its required
assertions could not run.

## Parallel Examples

These are scheduling examples, not instructions to spawn agents automatically.
Use one writer per file and the task prerequisites above.

### Shared foundation

After T005, T006 (Bicep) and T007 (Terraform) can proceed together. T009 can run
independently after Setup. T014's setup-settings tests can run while T010-T013
implement the loader, since their source/test files are distinct.

### User Story 1

```text
After Phase 2: T016 | T017 | T018 | T019 | T020
After the failing tests: T021 | T022 | T023 | T024 | T025 | T026 | T027 | T028 | T029
After all selected consumers: T030 | T031
Then: T032
```

### User Story 2

```text
After T032: T033 | T034
After T035: T036 | T037 | T038
Then: T039
```

### User Story 3

```text
After T032: T040 | T041 | T042
After their results and T039: T043 -> T044
```

Do not concurrently modify `tests\test_deployment_modes.py` or
`tests\test_native_application.py` from other stories while their US2 work runs.

### User Story 4

```text
After T044: T045 | T046 | T047
Then: T048 -> T049
```

### User Story 5

```text
After T050: T051 (configuration/apps) | T052 (provider guides) | T053 (recovery/private access)
Then: T054 -> T055
```

## Implementation Strategy

### MVP first

Complete approved Setup, the entire shared foundation and US1. Stop at T032 to
check the two store-free provider paths and both shells. This is the smallest
meaningful engineering increment because removing only guards or migrating one
provider/consumer cannot satisfy FR-001/FR-003. All source approval, destination,
identity, secret and network safeguards are already mandatory in this increment.

Do not publish partial support as complete. US2-US4's P1 acceptance evidence and
US5's coordinated documentation remain completion gates.

### Incremental delivery

Retain existing behavior while adding producers, then migrate shared resolution,
all selected consumers and both hook variants together. Verify store-free setup,
runtime compatibility, negative destinations and confidentiality in that order.
Complete current central documentation and final evidence before handoff.
Preserve the manifest-pinned runtime combination and provider state mechanics.

Old foundations require same-provider reprovision from original inputs.
Stale saved outputs require supported refresh and revalidation. Missing metadata
never authorizes store hydration, guessed names, backend switching or state
inspection. Old store-dependent hooks are not a rollback for store-free
environments. No store deletion or in-place runtime-mode conversion is promised.

## Coverage and Completion Summary

| Scope | Tasks | Acceptance focus |
| --- | --- | --- |
| Setup | T001-T002 (2) | Human decision, ownership and compatibility baseline |
| Foundation | T003-T015 (13) | Closed non-secret contract, both producers, transport, selected output, secure live binding and typed settings |
| US1 | T016-T032 (17) | FR-001, FR-003, FR-004, FR-011, FR-013 and SC-001, SC-002, SC-005, SC-007. Zero store calls, real selected setup, both providers/shells, separate/repeated runs |
| US2 | T033-T039 (7) | FR-009, FR-010, FR-015. Runtime-v1/settings/flags/references and defaults preserved, no implicit mode switch |
| US3 | T040-T044 (5) | FR-005, FR-006, FR-012 and SC-003. Invalid destinations fail before mutation, direct invocation is not a bypass |
| US4 | T045-T049 (5) | FR-007, FR-008, FR-012 and SC-004. Approved non-secret output only, no disclosure/state inspection/bypass grants |
| US5 | T050-T055 (6) | FR-016, SC-006. Four categories, accurate prerequisites, both-provider delivery and recovery |
| Cross-cutting | T056-T060 (5) | FR-002, FR-014, FR-015 and all success criteria consolidated, locked tools, explicit residual risks |

**Total**: 60 tasks. The dependency table, per-story criteria and coverage table
are part of the execution contract, not optional background.

No live Azure parity, private-topology operation or store-free application
readiness is established by this list or by mocked/compiled checks. No release,
tag, package/image publication or production deployment is authorized here.
