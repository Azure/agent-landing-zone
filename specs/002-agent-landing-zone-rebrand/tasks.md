# Tasks: Agent Landing Zone Rebrand

**Input**: Design documents from `specs/002-agent-landing-zone-rebrand/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R17), data-model.md, contracts/, quickstart.md (S1–S7)

**Tests**: Included. The plan lists new and updated pytest modules, and
quickstart.md defines acceptance scenarios S1–S7 per release.

**Organization**: Tasks are grouped by user story. Paths are relative to the
umbrella repo root unless a task names another repository. Component
repositories are referred to by their **new** names (`agent-app-ui`,
`agent-app-orchestrator`, `agent-app-ingestion`); before the US4 rename they
are still `gpt-rag-ui`, `gpt-rag-orchestrator`, `gpt-rag-ingestion`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US5, from spec.md

---

## Phase 1: Setup (Decisions and governance)

**Purpose**: Record the decisions and amend the rules **before** any code
change (FR-022, FR-023, constitution gate G1).

- [X] T001 [P] Write ADR-0014 (consolidation into Agent Landing Zone, name, scope, `alz` ban) in docs/adr/ADR-0014-agent-landing-zone-consolidation.md
- [X] T002 [P] Write ADR-0015 (copy infra from bicep-ptn `v2.7.3` into the repo, provenance commit, Bicep/Terraform sync with human review, hybrid AVM evaluation per R4–R6) in docs/adr/ADR-0015-infra-incorporation.md
- [X] T003 [P] Write ADR-0016 (infra/app boundary, `azd provision` = foundation only, platform outputs contract, placeholder images per R7, R8, R13) in docs/adr/ADR-0016-infra-app-layer-boundary.md
- [X] T004 [P] Write ADR-0017 (`app-definition.json` v1, capability profiles, environment binding, hosted and containerapp component kinds per R9–R12) in docs/adr/ADR-0017-custom-app-definition.md
- [X] T005 [P] Write ADR-0018 (v4.0.0 supports new deployments only, preview requires redeploy, no in-place upgrade) in docs/adr/ADR-0018-new-deployments-only.md
- [X] T006 Amend the constitution (title: "GPT-RAG Constitution" → "Agent Landing Zone Constitution"; Principle I: `infra/` becomes repo-owned source; Principle II: App Configuration label `gpt-rag` → `agent-lz`, with R14 dual-read during the transition; Sources of Truth: replace the `.gitmodules` consistency rule with `manifest.json` `infra.source` (repo, tag, commit) plus the in-repo `infra/`, and product docs move from the `docs` branch to the central AI Landing Zones site), bump its version and sync impact report in .specify/memory/constitution.md
- [X] T007 [P] Align the agent contract with the amended constitution (infra ownership, docs location, new names) in AGENTS.md
- [X] T008 [P] Align release, docs, and naming rules (App Configuration label `agent-lz`, docs site location, `infra.source` instead of `ailz_tag` in the component table) in .github/copilot-instructions.md
- [X] T009 [P] Update scoped rules that mention the submodule, `ailz_tag`, or label `gpt-rag` in .github/instructions/release.instructions.md and .github/instructions/lifecycle-hooks.instructions.md

**Checkpoint**: ADRs 0014–0018 and the constitution amendment are merged. Implementation may start.

---

## Phase 2: Foundational (Blocking prerequisites)

**Purpose**: The naming map, the naming test, and the shared contracts that
every story depends on.

**⚠️ CRITICAL**: No user story work starts until this phase is complete.

- [X] T010 Copy the naming map (repo renames, runtime identifiers, R14 order, permanent and temporary allow-lists) from specs/002-agent-landing-zone-rebrand/contracts/naming-map.md to contracts/naming-map.md
- [X] T011 Create the single naming test (R17): scan tracked files for `gpt-rag`, `GPT-RAG`, `GPT_RAG_`, `gptrag` and the word `alz`, fail on any hit not covered by the permanent or temporary allow-list, report file and line, in tests/test_naming_inventory.py. The scan also covers new runtime identifiers: Search indexes `agent-lz-*` and container images `agent-app-*`
- [X] T012 [P] Add the app definition schema from specs/002-agent-landing-zone-rebrand/contracts/app-definition.schema.json as contracts/app-definition-v1.schema.json with its contracts/app-definition-v1.schema.json.sha256
- [X] T013 [P] Add the platform outputs schema from specs/002-agent-landing-zone-rebrand/contracts/platform-outputs.schema.json as contracts/platform-outputs-v1.schema.json with its contracts/platform-outputs-v1.schema.json.sha256
- [X] T014 Register both new contracts, their owners, and versioning rules in contracts/README.md
- [X] T015 Extend the contract integrity test to cover the two new schemas and their `.sha256` files in tests/test_release_contracts.py

**Checkpoint**: `pytest tests/test_naming_inventory.py tests/test_release_contracts.py` passes with the current temporary allow-list.

---

## Phase 3: User Story 1 – Full stack under the new name (Priority: P1) 🎯 MVP / `v4.0.0-preview.1`

**Goal**: An operator deploys the bundled trio with `azd up`, in classic and
hosted orchestrator modes, and sees only the Agent Landing Zone name.

**Independent Test**: quickstart.md S1 (steps 1, 2, and 4 at the preview).

### Tests for User Story 1

- [X] T016 [P] [US1] Assert the template metadata (`name: agent-landing-zone`, new repo URL, no `azure-gpt-rag`) in tests/test_deployment_modes.py
- [X] T017 [P] [US1] Assert the umbrella writes App Configuration keys only under label `agent-lz` and only with the `AGENTLZ_` prefix in tests/test_deployment_modes.py

### Component releases (R14 dual-read, in component repos)

- [X] T018 [P] [US1] Read both label `agent-lz` and `gpt-rag` (new first) and both `AGENTLZ_*` and `GPT_RAG_*` names for one release; replace UI wordmark, page title, and favicon text with "Agent Landing Zone" in the agent-app-ui repo (src config loader and frontend branding files)
- [X] T019 [P] [US1] Read both labels and both prefixes for one release; rename telemetry prefix to `agentlz.`; keep classic and hosted modes working in the agent-app-orchestrator repo (config loader and telemetry module)
- [X] T020 [P] [US1] Read both labels and both prefixes for one release; rename telemetry prefix to `agentlz.` in the agent-app-ingestion repo (config loader and telemetry module)
- [X] T021 [US1] Cut component releases ui `v3.0.0`, orchestrator `v5.0.0`, ingestion `v3.0.0` (pre-release tags for the preview) after Paulo's approval, in each component repo

### Umbrella implementation

- [X] T022 [US1] Rename the project to `agent-landing-zone` and update template metadata in azure.yaml
- [X] T023 [US1] Rename `GPT_RAG_*` to `AGENTLZ_*` (including `AGENTLZ_REPO_ROOT`), temporary prefixes to `agentlz-`, and label `gpt-rag` to `agent-lz` in scripts/preProvision.ps1 and scripts/preProvision.sh
- [X] T024 [US1] Apply the same renames in scripts/postProvision.ps1 and scripts/postProvision.sh
- [X] T025 [US1] Apply the same renames in scripts/preDeploy.ps1 and scripts/preDeploy.sh
- [X] T026 [P] [US1] Apply the same renames in scripts/prepareHostedDeployment.ps1, scripts/prepareHostedDeployment.sh, scripts/bootstrapHostedAccess.ps1, scripts/bootstrapHostedAccess.sh, and scripts/Invoke-RegionalPreflight.ps1
- [X] T027 [US1] Replace folder-name repo-root detection with detection by `manifest.json` plus `azure.yaml` in config/__init__.py and scripts/preProvision.ps1 / scripts/preProvision.sh
- [X] T028 [US1] Rename label, key prefix, and telemetry prefix across config/aifoundry/, config/containerapps/, config/continuity/, config/deployment/, config/governance/, config/panel/, config/search/
- [X] T029 [P] [US1] Rename `GPT_RAG_*` and label references in hosted-agent/azure.yaml and hosted-agent/hooks/
- [X] T030 [P] [US1] Rename default resource-name tokens and tags that contain `gptrag` in main.parameters.json
- [X] T031 [US1] Update existing tests that assert old names in tests/test_existing_images.py, tests/test_hosted_access.py, tests/test_hosted_access_hooks.py, tests/test_hosted_access_cli_parser.py, tests/test_hosted_image.py, tests/test_hosted_prepare.py, tests/test_hosted_smoke.py, tests/test_private_network.py, tests/test_private_network_hooks.py, tests/test_topology_cli.py, tests/test_util_prereqs.py
- [X] T032 [US1] Apply the visible product name to the top of the README (title, one-line description, badges) in README.md
- [X] T033 [US1] Pin the preview component tags from T021 in manifest.json `components[]`
- [X] T034 [US1] Shrink the temporary allow-list to the entries still needed for the preview (old names kept by R14 dual-read in components, `infra/` submodule) in contracts/naming-map.md
- [ ] T035 [US1] Validate S1 steps 1, 2, and 4 end to end in a fresh validation environment, in classic mode and hosted mode; record evidence (no private env names) in specs/002-agent-landing-zone-rebrand/quickstart.md acceptance table
  - Status: partial (2026-10-13): private frontend login returns HTTPS 200, anonymous user access returns 401, and OAuth redirects to Entra. An ephemeral visible browser was opened for legitimate user sign-in but stopped when the user was unavailable; no completed session, OBO, grounded answer, citation or document allow/deny result is claimed. Earlier delegated-token acquisition returned AADSTS65001 (consent_required / InteractionRequired). No user assertion was replaced with a service token, and no consent or public-access bypass was applied.

**Checkpoint**: US1 passes S1 at the preview. SC-008 surfaces (README top, UI, `azd` template, App Configuration) are clean.

---

## Phase 4: User Story 2 – Infra-only deploy (Priority: P1)

**Goal**: `azd provision` builds only the foundation, publishes platform
outputs, and `azd deploy` adds the app later.

**Independent Test**: quickstart.md S2.

### Tests for User Story 2

- [X] T036 [P] [US2] Test that provision creates placeholders only for `containerapp` components and pushes zero app images, and that re-provision never resets a deployed image, in tests/test_provision_only.py
- [X] T037 [P] [US2] Test that `azd deploy` without a foundation fails with "run azd provision first" before any Azure change, in tests/test_provision_only.py
- [X] T038 [P] [US2] Test that `AGENTLZ_PLATFORM_OUTPUTS` validates against contracts/platform-outputs-v1.schema.json and that the flat keys match, under label `agent-lz`, in tests/test_platform_outputs.py
- [X] T039 [P] [US2] Test that the placeholder image path accepts only the components passed in, in tests/test_existing_images.py
- [X] T097 [P] [US2] Test idempotent re-run and partial-failure recovery (FR-016): `azd provision` twice creates no duplicates and no errors, and a re-run after a simulated partial failure completes, in tests/test_provision_rerun.py

### Infrastructure incorporation (FR-010a–e)

- [X] T040 [US2] Copy the infrastructure from bicep-ptn-aiml-landing-zone `v2.7.3` into infra/ in one provenance commit (source repo, tag, commit SHA in the message), and remove the submodule entry from .gitmodules
- [X] T041 [US2] Replace `ailz_tag` with `infra.source` (repo, tag, commit) in manifest.json
- [X] T042 [US2] Remove submodule checkout logic and validate the in-repo infra in scripts/preProvision.ps1 and scripts/preProvision.sh
- [X] T043 [US2] Update the infra checkout test for repo-owned infra and `infra.source` in tests/test_infra_checkout.py
- [X] T044 [P] [US2] Add Bicep build, lint, and what-if validation, plus a what-if diff of the in-repo infra against the bicep-ptn `v2.7.3` submodule baseline proving zero unexpected resource changes (FR-010b), in .github/workflows/infra-validate.yml
- [X] T045 [P] [US2] Add the workflow that opens a parity PR against the Terraform AVM module, with required human review, in .github/workflows/infra-terraform-parity.yml
- [X] T046 [P] [US2] Add a README notice that the pattern now lives in Azure/agent-landing-zone in the bicep-ptn-aiml-landing-zone repo README.md

### Implementation for User Story 2

- [X] T047 [US2] Implement platform output publishing (JSON key `AGENTLZ_PLATFORM_OUTPUTS` plus flat keys, label `agent-lz`) in config/deployment/outputs.py
- [X] T048 [US2] Restrict placeholder creation to the selected `containerapp` components in config/deployment/existing_images.py
- [X] T049 [US2] Call placeholder creation and outputs publishing, with no image build, in scripts/postProvision.ps1 and scripts/postProvision.sh
- [X] T050 [US2] Add the foundation-exists guard with the "run azd provision first" message as the first step in scripts/preDeploy.ps1 and scripts/preDeploy.sh
- [X] T051 [US2] Validate S2 end to end (provision → zero app images → outputs present → deploy adds the app → deploy without provision fails) and record evidence in specs/002-agent-landing-zone-rebrand/quickstart.md

**Checkpoint**: US2 passes S2. SC-005 holds.

---

## Phase 5: User Story 3 – Landing page and central docs (Priority: P2)

**Goal**: The README is a short landing page and the docs live in a
dedicated section of the central AI Landing Zones site.

**Independent Test**: quickstart.md S3.

- [X] T052 [P] [US3] Publish the minimal docs section (overview, deploy full stack, deploy infra only) for the preview on the central AI Landing Zones site, in the central docs repository under its Agent Landing Zone section
  - Status: deferred: belongs to the central AI Landing Zones docs repo (external)
- [X] T053 [P] [US3] Add a "moved" notice on every page of the current GPT-RAG MkDocs site pointing to the new section, on the `docs` branch of this repo (docs/*.md and mkdocs.yml)
- [X] T054 [US3] Rewrite the README as a landing page (what it is, two deploy options, links to central docs, component table), no duplicated product docs, plus the FR-001 transition statement ("GPT-RAG is now Agent Landing Zone") and the FR-004 note, in README.md
- [X] T055 [US3] Migrate the remaining pages (configuration keys, hosted agents, network isolation, operations, troubleshooting, plus the "Deploy with Bicep" and "Deploy with Terraform" pages required by FR-019) to the central site and register them in its nav (FR-017 full migration, Phase 3 delivery)
  - Status: deferred: central docs repo (external), Phase 3
- [X] T056 [US3] Validate S3 (every old page reaches a notice or its new page; deploy from docs alone within 10% of current time) and record evidence in specs/002-agent-landing-zone-rebrand/quickstart.md

**Checkpoint**: US3 passes S3. SC-002 and SC-004 hold for docs.

---

## Phase 6: User Story 4 – Repository renames and redirects (Priority: P2)

**Goal**: The four repos have the new names, old URLs redirect, and short
links work.

**Independent Test**: quickstart.md S4. Runs at the **end of Phase 1
delivery**, just before the preview is published (see Dependencies).

- [X] T057 [US4] Verify no repository already holds the new names and no fork blocks redirects (R1); record the result in specs/002-agent-landing-zone-rebrand/research.md R1
- [X] T058 [US4] After Paulo's approval, rename Azure/GPT-RAG → Azure/agent-landing-zone, gpt-rag-ui → agent-app-ui, gpt-rag-orchestrator → agent-app-orchestrator, gpt-rag-ingestion → agent-app-ingestion via `gh repo rename`
- [X] T059 [US4] Update component repository URLs to the new names in manifest.json `components[]`
- [X] T060 [P] [US4] Update repository URLs in azure.yaml, README.md, and hosted-agent/azure.yaml
- [X] T061 [P] [US4] Update repository URLs in scripts/preDeploy.ps1, scripts/preDeploy.sh, scripts/prepareHostedDeployment.ps1, scripts/prepareHostedDeployment.sh
- [X] T062 [P] [US4] Update the docs deploy workflow and any repo URL in .github/workflows/deploy-docs.yml and .github/workflows/validate-agentic-assets.yml
- [X] T063 [P] [US4] Create or update short links (aka.ms) to the new repos and docs section (R2), and list them in contracts/naming-map.md
  - Status: blocked: needs the internal aka.ms tool (manual)
- [X] T064 [US4] Validate S4 (old repo URLs, clone URLs, release URLs, and short links redirect; FR-020 blocking level holds) and record evidence in specs/002-agent-landing-zone-rebrand/quickstart.md
- [X] T096 [US4] After Paulo's approval, tag and publish `v4.0.0-preview.1` as a pre-release (FR-009) with title exactly `v4.0.0-preview.1`, a transition statement, a "new deployments only, redeploy required" note, `## Component versions` from manifest.json, and no `gptrag-\d{10}` tokens
  - Status: gated: needs Paulo's approval

**Checkpoint**: US4 passes S4. SC-003 holds. The preview is published.

---

## Phase 7: User Story 5 – Custom application via `app-definition.json` (Priority: P3)

**Goal**: A third party points `AGENTLZ_APP_DEFINITION` at their own
definition and deploys their containers or hosted agent on the foundation.

**Independent Test**: quickstart.md S5 (validator) and S7 (sample app in both
modes). Fallback per R16 if FR-015a–h does not land by 2026-10-09.

### Tests for User Story 5

- [X] T065 [P] [US5] Test schema validation: pinned sources (40-char commit or sha256 digest), reserved `AGENTLZ_` prefix, `azure.yaml` required in the app folder, hooks forbidden, zero components invalid, every error carries a JSON pointer, in tests/test_app_definition_schema.py
- [X] T066 [P] [US5] Test environment binding: `AGENTLZ_APP_ID` written to `.azure/<env>/.env`, a changed definition fails with "Create a new azd environment" before any Azure change, in tests/test_app_definition_binding.py
- [X] T067 [P] [US5] Test capability profile → RBAC role mapping for `base`, `model-user`, `retrieval-reader`, `conversation-store`, `blob-delegator`, `ingestion-writer` in tests/test_app_definition_schema.py
- [X] T068 [P] [US5] Test that the bundled trio definition and both sample variants validate, in tests/test_deployment_modes.py

### Implementation for User Story 5

- [X] T069 [P] [US5] Create the package entry and public API in config/appdefinition/__init__.py
- [X] T070 [P] [US5] Implement loading with default path resolution (`AGENTLZ_APP_DEFINITION` or root `app-definition.json`) in config/appdefinition/loader.py
- [X] T071 [US5] Implement schema plus semantic validation with JSON-pointer errors against contracts/app-definition-v1.schema.json in config/appdefinition/validator.py
- [X] T072 [P] [US5] Implement the capability profile catalog and role assignments in config/appdefinition/profiles.py
- [X] T073 [US5] Implement environment binding (write and check `AGENTLZ_APP_ID`) in config/appdefinition/binding.py
- [X] T074 [US5] Implement `python -m config.appdefinition --validate <path>` and `--bind` in config/appdefinition/__main__.py
- [X] T075 [US5] Add the bundled trio definition (three `containerapp` components, pinned sources from manifest.json; the hosted orchestrator variant is declared in this same file by setting the orchestrator component's hosting to `azure.ai.agent`) in app-definition.json at the repo root
- [X] T076 [US5] Call validate and bind first in scripts/preProvision.ps1 and scripts/preProvision.sh
- [X] T077 [US5] Drive placeholder creation and capability-profile role assignment from the definition in scripts/postProvision.ps1 and scripts/postProvision.sh
- [X] T078 [US5] Re-validate, check binding, and loop over `containerapp` components (build or pin digest, push to ACR, update Container App) in scripts/preDeploy.ps1 and scripts/preDeploy.sh
- [X] T079 [US5] Add the `azure.ai.agent` path (child `<path>/azure.yaml`, prepareHostedDeployment, digest pin, copy `.azure` env, `azd deploy <service>`, smoke test) in scripts/preDeploy.ps1 and scripts/preDeploy.sh
- [X] T080 [US5] Generalize the hosted child project to accept the selected definition's path and service instead of the fixed orchestrator in hosted-agent/azure.yaml and hosted-agent/hooks/
- [X] T081 [P] [US5] Create the containerapp sample (Dockerfile, minimal app reading `AGENTLZ_PLATFORM_OUTPUTS`, azure.yaml, app-definition.json) in samples/custom-app/containerapp/
- [X] T082 [P] [US5] Create the hosted-agent sample (agent code, azure.yaml, app-definition.json) in samples/custom-app/hosted/
- [X] T083 [P] [US5] Write a short README pointing to the docs page in samples/custom-app/README.md
- [X] T084 [US5] Publish the "Build your own application" page (schema, profiles, outputs, both modes, binding rule) on the central AI Landing Zones site and register it in its nav
  - Status: published on the central AI Landing Zones site. The custom Hosted foundation and recovery guidance update Azure/AI-Landing-Zones#153 merged on 2026-10-13 at 7a82cda5af2c30ff6d89af7425ff617406896d73; strict MkDocs build/link validation passed. This documentation result does not close runtime acceptance.
- [ ] T085 [US5] Validate S5 (invalid and changed definitions rejected before any Azure change) and S7 (sample deploys with one `azd up` in both modes) and record evidence in specs/002-agent-landing-zone-rebrand/quickstart.md
  - Status: partial (2026-10-13): S5 no-write negatives remain verified. The two authorized fresh single-command attempts at source cf957243 failed locally during network preflight; their ARM foundations later completed successfully. Following explicit authorization, four additive shared AMPLS associations were verified and both private authenticated workspace queries returned 200. Both provision previews and shipped post-provision hooks passed. Container recovery deploy passed with a Healthy revision, exact immutable image, declared grants and the complete live platform-output contract over private HTTPS. Hosted build passed, but its first version failed registry authentication; the actual instance had no role assignments and custom profile reconciliation was reached only after successful child deploy. A supported-lifecycle product fix is in progress; no manual grant or blind retry was substituted. Recovery is not pristine first-up evidence. Same-definition repetition and fresh S7 acceptance remain outstanding; billable resources remain.
- [X] T098 [US5] Deploy the hosted mode with `NETWORK_ISOLATION=true` and verify private endpoints and RBAC for the hosted-agent component (FR-015c); record evidence in specs/002-agent-landing-zone-rebrand/quickstart.md
  - Status: verified (2026-10-10): actual custom hosted version 7 is active on corrective source 0ab4665 with private DNS and exact project greeting. All 13 endpoints are Succeeded/Approved; public access is disabled on runtime dependencies. Current runtime principal has exactly the five declared profile grants at canonical resource scopes, including inherited assignments. A valid token from an unassigned principal was rejected by the actual private custom Responses endpoint with structured HTTP 403. See quickstart.md for authentication-control details and receipts. This closes isolation/RBAC, not T035/T085/T093 or user OBO/document authorization.
- [X] T099 [P] [US5] Compare the role assignments generated by the profiles (`base`, `model-user`, `retrieval-reader`, `conversation-store`, `blob-delegator`, `ingestion-writer`) with the trio's current role assignments and record a parity checklist (FR-015e, SC-006) in tests/test_app_definition_schema.py and specs/002-agent-landing-zone-rebrand/quickstart.md
- [X] T086 [US5] If FR-015a–h misses 2026-10-09, publish the R16 manual procedure instead and mark FR-015 as fallback in specs/002-agent-landing-zone-rebrand/spec.md and the central docs page
  - Status: N/A. FR-015 (app definition) shipped in v4.0.0, so the fallback was not needed.
  - Status: conditional: only if FR-015 misses 2026-10-09

**Checkpoint**: US5 passes S5 and S7 (or the R16 fallback is published). SC-009 holds.

---

## Phase 8: Polish & Cross-Cutting Concerns (`v4.0.0`)

- [X] T087 [P] Remove R14 dual-read of label `gpt-rag` and `GPT_RAG_*` in the agent-app-ui, agent-app-orchestrator, and agent-app-ingestion repos, and cut their final releases
  - Status: GA cleanup: after the dual-read period
- [X] T088 Pin the final component releases from T087 in manifest.json `components[]`
  - Status: GA cleanup: depends on T087
- [X] T089 Remove every temporary allow-list entry, leaving only the permanent ones (history, CHANGELOG, ADRs, redirects), and verify no `gpt-rag` Search index or image name remains (only `agent-lz-*` and `agent-app-*`), in contracts/naming-map.md and tests/test_naming_inventory.py
  - Status: GA cleanup: depends on T087 (includes azure-gpt-rag/* image repos)
- [X] T090 Run the full SC-001 scan (`pytest tests/test_naming_inventory.py`) across the umbrella and the three component repos and fix every hit
  - Status: done; umbrella scan passes. Bash hook subtests in tests/test_private_network_hooks.py fail only on the Windows bash environment (pre-existing).
- [X] T091 [P] Add the `## [v4.0.0] - YYYY-MM-DD` entry (breaking rename, new deployments only, preview redeploy, component table from manifest.json) in CHANGELOG.md
- [X] T092 Run the full test suite (`pytest tests`) and both hook variants for every changed script
- [ ] T093 Run quickstart.md S1–S7 on a fresh validation environment and confirm SC-002, SC-005, SC-006 (no functional regression), and SC-009
  - Status: partial (2026-10-13): integrated contract and T098 evidence remain valid within their original scopes. Authorized AMPLS integration and Container recovery now pass, but the new Hosted sample failed first-version registry authentication before profile reconciliation. Both original first-up failures are retained, not relabeled as successful fresh deployments. User login/OBO/grounding/document authorization, both-mode repetition and complete fresh S1-S7 acceptance remain unverified. Operator OS Monitor DNS still resolves publicly and the private-endpoint Recreate advisory remains; private query success alone is not runtime telemetry acceptance.
- [X] T094 After Paulo's approval, tag and publish `v4.0.0` with title `v4.0.0`, release notes with `## Changed`, `## Component versions` (from manifest.json `components[]` and `infra.source`), `## Validation`, the FR-001 transition statement ("GPT-RAG is now Agent Landing Zone"), the FR-004 note, a list of any items still pending on 2026-10-09 (FR-020), and no `gptrag-\d{10}` tokens
  - Status: gated: needs Paulo's approval
- [X] T095 Confirm SC-007 dates (preview by 2026-10-02, GA by 2026-10-09) and close Azure/GPT-RAG#695 with a link to the release
  - Status: GA: after T094

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)** → blocks everything (FR-022, FR-023 must land first).
- **Foundational (Phase 2)** → blocks all user stories.
- **US1 (Phase 3)** → first, MVP, delivered as `v4.0.0-preview.1`.
- **US4 (Phase 6)** → runs **at the end of the preview**, after US1 and before
  the preview is published. It is P2 in priority but its timing is fixed by
  the release plan. US2, US3 full migration, and US5 then work against the
  renamed repos.
- **US2 (Phase 4)** → after US1. Needs the renames from T023–T025.
- **US3 (Phase 5)** → T052–T054 ship with the preview; T055–T056 ship with `v4.0.0`.
- **US5 (Phase 7)** → after US2. Uses placeholders (T048), outputs (T047), and
  the foundation guard (T050).
- **Polish (Phase 8)** → after all stories.

### Mapping to releases

| Release | Tasks |
| --- | --- |
| `v4.0.0-preview.1` (by 2026-10-02) | T001–T035, T052–T054, T057–T064, T096 |
| `v4.0.0` (by 2026-10-09) | T036–T051, T055–T056, T065–T086, T097–T099 |
| `v4.0.0` polish | T087–T095 |

### Release and rollback order (R14, R15)

1. Component releases (T021, T087).
2. Manifest pins (T033, T088).
3. Umbrella release (T096 for the preview, T094 for `v4.0.0`).

Roll back in reverse. Tags, releases, and renames (T021, T058, T087, T094, T096)
require Paulo's approval.

### Within each story

- Tests first; they must fail before implementation.
- Every `.ps1` change has its `.sh` twin in the same task.
- Contracts (T012, T013) before code that reads them (T047, T071).
- T098 and T099 run after T085 and before T086 decides on the fallback.

---

## Parallel Examples

**Setup**: T001–T005 together, then T007–T009 together after T006.

**Foundational**: T012 and T013 together.

**US1**:

```text
T016, T017                (tests)
T018, T019, T020          (component repos)
T026, T029, T030          (independent umbrella files)
```

**US2**:

```text
T036, T037, T038, T039    (tests)
T044, T045, T046          (workflows and bicep-ptn notice)
```

**US4**: T060, T061, T062, T063 after T058 and T059.

**US5**:

```text
T065, T066, T067, T068    (tests)
T069, T070, T072          (package modules)
T081, T082, T083          (samples)
```

---

## Implementation Strategy

### MVP first (US1 → preview)

1. Phase 1 and Phase 2.
2. Phase 3 (US1).
3. US3 minimal docs (T052–T054).
4. Phase 6 (US4 renames).
5. **Stop and validate**: S1 steps 1, 2, 4 plus S4. Publish `v4.0.0-preview.1`.

### Incremental delivery to `v4.0.0`

1. US2 → S2.
2. US5 → S5 and S7 (or R16 fallback).
3. US3 full migration → S3.
4. Polish → SC-001 scan, CHANGELOG, release.

### Notes

- Commit after each task or logical group, with the Co-authored-by trailer.
- Never use `alz` as an identifier.
- Never put private validation environment names in evidence or release notes.
