---
description: "Story-organized implementation tasks for native inline visual output"
---

# Tasks: Native Inline Visual Output

**Input**: Design artifacts in `specs\005-inline-visual-output\`.
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts](contracts/README.md), [quickstart.md](quickstart.md).
**Status**: Working local native-middleware-to-UI increment. Full local
quality/acceptance remains incomplete. Maintainer-approved scope amendment
(2026-11-08) removes Azure LIVE validation from completion, not defers it.
**Implementation gate**: T001 local approval remains. T054-T056 are retired,
not executed. T057-T058 retain controlled SDK/history/Playwright counts and
automated usability/provider checks and measured performance. Azure persistence,
authorization enforcement and deployed parity remain unverified residual risks.
No Azure operation, production enablement, deployment or release is authorized.
**Tests**: Required by the specification's explicit acceptance scenarios and SC-001 through SC-010, and by the constitution. Add focused failing behavioral tests before the corresponding implementation. Do not run product suites merely to generate this backlog.
**Organization**: Setup, shared foundations, P1 stories US1/US2/US6, P2 stories US3/US4/US5, then final acceptance and documentation.

## Format and path conventions

- Every task uses `- [ ] Tnnn [P?] [USn?] description with path`.
- `[P]` means eligible for parallel execution only after its stated prerequisites are complete and its files are not being edited by another task.
- `ALZ\` means this repository, `Azure/agent-landing-zone`.
- `ORCH\` means the component repository `Azure/agent-app-orchestrator`.
- `UI\` means the component repository `Azure/agent-app-ui`.
- `DOCS\` means central documentation repository `Azure/AI-Landing-Zones`.
- All paths below are repository-relative Windows paths. Component repositories are not subdirectories of this umbrella checkout.
- Confirmed local files include `ORCH\src\native\presentation.py`, `ORCH\src\native\presentation_middleware.py`, `UI\src\gpt_rag_ui\services\native_presentation.py`, `UI\src\gpt_rag_ui\api\native.py`, `UI\src\gpt_rag_ui\api\native_chat.py` and `UI\public\elements\Presentation.jsx`. UI tests are collected under `UI\tests\`, not root `api\`. T002's exact inventory is in quickstart. Do not invent a new test runner or schema distribution package.
- Exact wire shapes and semantics are defined by the three schemas and delivery/configuration/tool-results documents, not by task prose.

## Execution boundaries

Default to local, change-scoped validation with synthetic authorized results, a deterministic chat client and controllable clocks. Reuse prepared environments. Do not repeat full infrastructure/component suites manually when unchanged evidence and required CI already cover the same source.

Azure and demo operations are off-limits. No target selection or target-approval
task remains in this local-only backlog. Keep private identities out of artifacts.

No task authorizes Azure provisioning/traffic, proof restart, releases/tags/images
or production deployment. Run the full local matrix once, then repeat invalidated
cases. Preserve counts, both host SDK/history shapes and local provider/hook parity.

## Phase 1: Setup

**Purpose**: Establish implementation authority, repository boundaries and executable validation entrypoints without Azure operations.

- [X] T001 Record explicit user authorization of `ALZ\docs\adr\ADR-0040-native-inline-presentation.md` for local implementation (2026-11-07); preserve native ownership, source trust and rollback. The 2026-11-08 proof-method amendment removes Azure live gates, not security requirements or residual risk. No production acceptance is claimed.
- [X] T002 Inventory the manifest-pinned baselines and actual `develop`-based feature checkouts, applicable instructions, native imports, test collection, schema packaging and existing CI entrypoints for `ALZ\manifest.json`, `ORCH\src\native\agent.py`, `UI\src\gpt_rag_ui\api\native_chat.py` and `DOCS\mkdocs.yml`; record exact source/test/doc paths and commands in `ALZ\specs\005-inline-visual-output\quickstart.md`. Obtain missing repository access rather than cloning or switching shared checkouts automatically.
- [X] T003 Extend the evidence inventory in `ALZ\specs\005-inline-visual-output\quickstart.md` with change-to-test mapping, fixture domains, hashes/revisions, local/final lanes and historical deployed-proof limits. Inventory central native-agent/configuration/workflow/history/embed/customer references through `DOCS\mkdocs.yml`. Target selection was removed by the maintainer amendment, not deferred.

**Checkpoint**: ADR approved, paths/commands grounded in actual checkouts, no demo/environment operations performed.

## Phase 2: Foundational

**Purpose**: Shared producer/reader/configuration primitives required by all stories. All of T004-T010 must complete before story implementation.

- [X] T004 Add focused contract regressions in `ALZ\tests\test_presentation_contracts.py` for duplicate keys, three Draft 2020-12 schemas, format checking, valid/invalid examples and exact LF/SHA-256 metadata from `ALZ\specs\005-inline-visual-output\contracts\`. Assert strict producer shapes, measurement-free selection and unchanged settings default. Evidence: five tests pass; four missing-root-schema failures observed before promotion.
 `ALZ\contracts\turn-presentation-v1.schema.json`, `ALZ\contracts\presentation-selection-v1.schema.json` and `ALZ\contracts\agent-presentation-settings-v1.schema.json`, sibling integrity metadata and synthetic examples using existing governance, preserving the three current hashes. Establish matched component consumption/packaging identified in T002 and reject divergent schema copies; do not change manifest pins or create a separate runtime contract service.
- [X] T005 Promote the reviewed `ALZ\contracts\turn-presentation-v1.schema.json`, `ALZ\contracts\presentation-selection-v1.schema.json` and `ALZ\contracts\agent-presentation-settings-v1.schema.json`, sibling integrity metadata and synthetic examples using existing governance, preserving the three current hashes. Establish matched component consumption/packaging identified in T002 and reject divergent schema copies; do not change manifest pins or create a separate runtime contract service.
- [X] T006 [P] Add typed settings, source, selection, contribution and envelope primitives in `ORCH\src\native\presentation.py`, consuming the reviewed contracts. Implement duplicate-key/nonfinite rejection, exact decimal/integer handling, unique identifiers and disjoint fixed-comparison rule validation; reject invalid present configuration explicitly.
- [X] T007 [P] Add bounded presentation recognition and safe typed projection in `UI\src\gpt_rag_ui\services\native_presentation.py`, preserving decimal strings and nulls. Distinguish strict known producer validation from forward-compatible readers that skip unknown block kinds/optional fields, reject malformed known units and retain stable fallback without spreading unknown props.
- [X] T008 Implement deterministic escaped markdown projection and reserved-marker primary-text handling in `ORCH\src\native\presentation.py`. Only trusted hydrated output may use the standalone `agent_lz_presentation` carrier; quote model imitations inertly, retain ordinary narration and authorized opaque citations, and avoid fabricated no-data values.
- [X] T009 [P] Add optional typed `presentation` to `ORCH\src\native\contracts.py`'s `ReviewRequest`/`ResearchReviewResult` and matching UI business models in `UI\src\gpt_rag_ui\services\native.py`, reached through `UI\src\gpt_rag_ui\api\native.py` and `UI\src\gpt_rag_ui\api\native_chat.py`. Omit it for nonvisual results and keep readable `draft`, native state-version identity and existing admission unchanged.
- [X] T010 Add empty/off settings resolution and immutable functional snapshot primitives in `ORCH\src\native\config.py` and `ORCH\src\native\presentation.py`, keyed by stable native agent IDs. Missing key/entry disables production, invalid present values error explicitly, guidance cannot override safety, and no timeout/tool-eligibility allowlist setting is introduced.

**Checkpoint**: Local contract primitives pass. These foundations do not prove product streaming, native persistence, Azure parity or production readiness.

## Phase 3: US1 - Read Trustworthy Analytical Answers Inline (P1, local MVP)

**Goal**: An enabled agent produces faithful cards, tables and supported charts from authorized typed results, with accessible text.
**Independent test**: Compare every value/unit/indicator with sales, operations and finance fixtures, including differently named/customer-defined tools. No interactions or history reopening are required.

### Tests

- [X] T011 [P] [US1] Add source/selection/hydration regressions in `ORCH\tests\test_native_presentation.py` covering exact decimals and large integers, null gaps, source-derived/disjoint-rule indicators and boundaries, units, ambiguous/lossy/no-data rejection and semantically identical results from differently named native/MCP/customer tools.
- [X] T012 [P] [US1] Add reader/display fixtures in `UI\tests\test_inline_presentation.py` and `UI\tests\test_native_presentation.py` for cards, typed tables, bar/grouped-bar/line charts and suggestions, exact accessible values, authorized citation separation and non-color-only indicators. Use the existing collected UI harness confirmed in T002.

### Implementation

- [X] T013 [US1] Capture only successfully authorized supported function results for an enabled snapshot through public middleware in `ORCH\src\native\presentation_middleware.py` and normalize them in `ORCH\src\native\presentation.py` within the optional stage budget. Disabled agents perform no additional presentation capture/normalization. Preserve existing tool results/consent/outcomes, assign invocation-associated provenance, dispatch by typed structure rather than tool name, and bind generated row IDs to captured positions without inventing business identifiers.
- [X] T014 [US1] Hydrate supported block selections and approved indicators deterministically in `ORCH\src\native\presentation.py`, resolving only contribution-scoped source/row/field bindings. Verify source equality, types, units, dimensions and indicator provenance; preserve exact strings/nulls and omit missing/no-match indicators.
- [X] T015 [US1] Implement one optional tool-free structured selection call in `ORCH\src\native\presentation.py` using the public chat client/`response_format`, user intent and authorized metadata. Accept layout/bindings/wording only, not measurements, rules, identity authority or additional tool calls.
- [X] T016 [US1] Wire public function/agent middleware and `ResponseStream`/`AgentResponse` composition in `ORCH\src\native\agent.py` and `ORCH\src\native\presentation_middleware.py`, retaining normal text and appending one complete canonical assistant envelope. Preserve consent/cancellation/lazy cleanup and guard marker-shaped primary output before live/saved delivery; never modify private host builders or raw SSE.
- [X] T017 [P] [US1] Build the initial static renderer in `UI\public\elements\Presentation.jsx` for all four block families and local SVG chart variants with bounded geometry, exact value text, labels/units and status meaning. Use approved existing imports/theme tokens, no chart dependency, remote resource or active HTML.
- [X] T018 [US1] Integrate the shared projection into `UI\src\gpt_rag_ui\api\native_chat.py`'s `text_output`/`display_output`/`render_progress` and `UI\src\gpt_rag_ui\api\native.py`'s REST path, showing readable narration plus trusted known blocks. Buffer machine fragments, preserve authorized citations and expose full escaped fallback on renderer failure.
- [X] T019 [US1] Run collected local source/renderer and exact-SDK stream/completed-result tests through `ALZ\specs\005-inline-visual-output\quickstart.md`; compare envelope bytes, source counts and disabled-call absence. Record revisions and carry final controlled owner/history/host-shape cases into T057, not an actual-Azure gate.

**Checkpoint**: Local US1 MVP works with deterministic sources and client. It is not a public opt-in/release or a demo-environment deployment.

## Phase 4: US2 - Enable Visuals Without Disrupting Existing Channels (P1)

**Goal**: Per-agent explicit opt-in with no extra operator work, resources or selection calls when absent/off, and readable supported new text-only clients.
**Independent test**: Compare two differently configured stable agent IDs, absent/off/default cases and new visual/nonvisual readers. Verify fresh-turn disablement and equivalent provider handoff.

### Tests

- [X] T020 [P] [US2] Extend `ALZ\tests\test_app_settings_resolution.py` and `ALZ\tests\test_appconfig_intent.py` for compact `AGENT_PRESENTATION_SETTINGS`, label `agent-lz`, `text/plain`, ordinary `json_object` validation, defaults/removal/reconciliation and both generic provider adapters.
- [X] T021 [P] [US2] Add per-agent and snapshot regressions in `ORCH\tests\test_native_presentation_config.py`, proving no selection/extra source call when unconfigured/off, actionable invalid-present errors, one-agent isolation, turn-start refresh despite the 30-second normal throttle and a frozen workflow snapshot with live authorization settings.

### Implementation

- [X] T022 [US2] Register the setting as owner-edited `ordinary` with explicit `json_object` validation in `ALZ\config\deployment\appconfig_ownership.json` and `ALZ\config\deployment\appconfig_intent.py`. Reject duplicate/version/rule/metadata errors through configured logging; do not classify it as generated `controlled` authority or bypass ordinary validation.
- [X] T023 [US2] Wire shared typed resolution/publication in `ALZ\config\deployment\native.py` and `ALZ\config\deployment\composition.py` through existing `additionalAppConfigurationSettings` in `ALZ\main.parameters.json`. Keep absent/off deployments unchanged, add no mandatory input/resource/host selector, and document Bicep/Terraform non-impact or coordinated counterpart edits.
- [X] T024 [US2] Add the key to selected `BASE_KEYS` and request-owned fresh reads in `ORCH\src\native\config.py`, integrating immutable per-turn/workflow functional settings into `ORCH\src\native\agent.py` and `ORCH\src\native\workflow.py`. Keep dynamic MCP capability/authorization settings live and disabled agents on their existing path.
- [X] T025 [US2] Exercise and complete envelope-aware text-only projections in `UI\src\gpt_rag_ui\api\native.py` and `UI\src\gpt_rag_ui\api\native_chat.py`, with readable markdown for supported new customer/Teams/Microsoft 365 frontends. Do not add native visuals to those channels or promise compatibility with unaware older raw Responses binaries.
- [X] T026 [US2] Implement or verify stale-value removal/empty-map convergence in `ALZ\config\deployment\appconfig_intent.py` and regressions in `ALZ\tests\test_infra_provider_hooks.py`; trace actual callers in `ALZ\scripts\preDeploy.ps1` and `ALZ\scripts\preDeploy.sh`. Change affected hooks together, or document why shared reconciliation leaves both unchanged.
- [X] T027 [US2] Run affected shared/provider/offline checks from `ALZ\specs\005-inline-visual-output\quickstart.md`, covering Bicep, Terraform and both hook implementations. Preserve locks/module pins/provenance and exact non-impact. Automated provider instruction checks are mapped in T058; deployed parity is unverified risk, not deferred work.

**Checkpoint**: Local opt-in/default/configuration parity passes. No extra default
operator step; deployed parity is unverified residual risk, not pending execution.

**Local US2 evidence — 2026-11-08**: T020/T021/T025/T026 meet their local
criteria; see the dated quickstart receipt for exact commands and source hashes.
The missing-declaration publisher regression failed before the surgical
`prepare_publication` fix; it now converges enabled → removed/empty/off and is
idempotent without deleting auth or other labels. Both generic adapters preserve
absent inputs; both real pre-deploy lifecycle blocks call the unchanged shared
publisher and stop on failure. Public-SDK source/selection counts, agent-ID
isolation, fresh-turn removal despite throttled refresh, frozen workflow
settings with live auth/MCP and JSON checkpoint restoration pass. Text-only
reader/handler cases cover both Hosted message forms, future-version fallback
and pending/completed/nonvisual workflow results, not actual external clients.

**T027 completed — authorized local dependency restoration, 2026-11-08**:
The user subsequently authorized exact local tools/dependencies. One secure
download installed Bicep 0.42.1 into the session temporary directory, without
replacing shared 0.37.4. Standalone pinned build/lint of `infra/bicep/main.bicep`
pass. Terraform 1.13.0 `init -backend=false -lockfile=readonly`, validation and
the existing Windows-native `tests\services.tftest.hcl` selector pass:
26 mocked plan contracts, 0 failures. Formatting and shared/provider adapter
and pwsh/bash pre-deploy evidence remain valid. The initial forward-slash
Terraform filter selected zero tests and is not passing evidence; use the
native selector. Lock bytes, module pins, manifest, provenance, foundation
source and production hooks remain unchanged. No Azure command/API/resource,
authentication or deployed parity was exercised. The former T056 Azure exercise
is now retired, not an outstanding gate.

The exact existing full Terraform/PowerShell mock case was further bounded:
at 30s it reached every expected trace event; at a final 45s cap it completed
successfully in 28.56s (1 test passed in 28.81s). Earlier 15s/30s timeouts remain
historical diagnostic results, not evidence of a persistent deadlock or reason
to change production hooks. No full lifecycle was executed against Azure.

**T002/T003 inventory completed**: Known local files establish exact
manifest-pinned versus actual feature baselines, applicable instructions,
native imports, source/test paths, collection, schema package locations and
ALZ/ORCH/UI/DOCS CI/doc commands; see quickstart. Confirmed UI and middleware
path aliases in this backlog were corrected without changing acceptance
criteria or unrelated task markers. T003's prior inventory remains valid.
Full shipped-page updates, declared-pin component qualification and live
acceptance remain separate delivery obligations. No shared checkout switch,
new planning file, vendor investigation or target selection was performed.

## Phase 5: US6 - Receive Safe Answers When Visual Output Fails (P1)

**Goal**: Unsafe/invalid/oversized/timed-out visual work preserves authorized text and valid siblings, with safe diagnostics and no late native mutation.
**Independent test**: Malformed, unauthorized, executable and boundary inputs plus deterministic deadline races produce precise rejection/fallback outcomes.

### Tests

- [X] T028 [P] [US6] Add adversarial/boundary/deadline regressions in `ORCH\tests\test_native_presentation_safety.py` for duplicate/nonfinite values, cross-contribution binding, invalid units/rules, source disclosure, aggregate rejection and exact/above 10/11 blocks, 500/501 rows, 8/9 series, 1,000/1,001 non-null values and 262,144/262,145 compact UTF-8 envelope bytes.
- [X] T029 [P] [US6] Add bounded reader/fallback and reserved-marker spoof cases in the collected `UI\tests\test_inline_presentation.py` and `UI\tests\test_native_presentation.py` for primary/user/tool/progress imitations, unknown versions/blocks/optional fields, malformed known units, oversized/incomplete output and renderer failure with zero unauthorized display or unknown-prop propagation.

### Implementation

- [X] T030 [US6] Complete semantic/content/aggregate validation in `ORCH\src\native\presentation.py`, rejecting invalid known units independently, preserving valid siblings and rejecting the entire over-budget combined presentation without truncation. Count full compact UTF-8 fallback/provenance bytes and non-null measurements exactly; emit ordinary text when no valid block remains.
- [X] T031 [US6] Implement the absolute monotonic 10-second stage supervisor in `ORCH\src\native\presentation.py` and integrate it in `ORCH\src\native\agent.py`. Include normalization/selection/hydration/validation/serialization and retries, keep processing deadline-responsive, seal accepted/timed-out once, signal cancellation without awaiting an uncooperative child and exclude all late completion from native output.
- [X] T032 [US6] Route optional-stage rejection/timeout/late-completion/cleanup failures through existing structured telemetry in `ORCH\src\native\presentation.py`, recording safe reasons, elapsed time, correlation and counts only. Preserve explicit native authorization/transport errors and never log raw values, guidance, credentials or hidden rows.
- [X] T033 [US6] Complete independent size/count/known-unit validation and fallback extraction in `UI\src\gpt_rag_ui\services\native_presentation.py`, restricted to admitted native assistant/result paths. Skip future unknown block kinds without rejecting valid siblings, ignore unknown optional fields safely and never display raw/partial JSON as accepted visuals.
- [X] T034 [US6] Harden `UI\public\elements\Presentation.jsx` and its integration in `UI\src\gpt_rag_ui\api\native_chat.py` against HTML evaluation, executable URLs, remote SVG references, automatic linkification and unknown object props. Preserve browser security controls and keep approved citations outside visual attributes/actions.
- [X] T035 [US6] Run deterministic retry/before-expiry/at-expiry/late-result/slow-processing/uncooperative-cancellation tests through `ALZ\specs\005-inline-visual-output\quickstart.md`. Assert timely text, immutable completed results, sibling preservation, safe diagnostics and all exact boundaries; carry controlled public SDK host-shape cases into T057 without treating mocks as deployed proof.

**Checkpoint**: Local safety/deadline gate passes. Controlled finalization and
authorization failures still block local acceptance; Azure enforcement remains
unverified residual risk, not a mandatory gate.

## Phase 6: US3 - Explore Tables and Ask Contextual Follow-Ups (P2)

**Goal**: Exact-value sort/filter/copy, accessible chart inspection and one normal user turn for an eligible row/suggestion action.
**Independent test**: Reorder/filter a known table, compare copied visible rows and activate actions under current authorization without source re-query for display.

### Tests

- [X] T036 [P] [US3] Add row/action hydration regressions in `ORCH\tests\test_native_presentation_actions.py`, proving generated row-position IDs support binding but not business actions, missing entity IDs disable actions, and prefix plus authorized identifier produces an inert plain prompt without templates/tool execution.
- [X] T037 [P] [US3] Add collected API/action fixtures in `UI\tests\test_native_presentation.py` and browser cases in `UI\tests\test_inline_presentation_browser.py` with commands in `ALZ\specs\005-inline-visual-output\quickstart.md` for exact numeric ordering, filter/copy precision and headers, stable selected row after reorder, keyboard inspection and duplicate activation.

### Implementation

- [X] T038 [US3] Implement stable exact-value numeric/text/date sorting, displayed-text filtering and headings/visible-row-order copy in `UI\public\elements\Presentation.jsx`. Never convert authoritative large integer/decimal strings to binary floats or mutate persisted values; define null ordering and preserve copied scale.
- [X] T039 [US3] Add accessible category/series/value/unit chart inspection and keyboard equivalents in `UI\public\elements\Presentation.jsx`, retaining exact text separately from approximate bounded SVG coordinates.
- [X] T040 [US3] Hydrate optional row-details prompts in `ORCH\src\native\presentation.py` using captured authorized business IDs, not current display indices. Omit actions without those IDs and preserve plain suggestion wording and source association.
- [X] T041 [US3] Wire row/suggestion controls in `UI\public\elements\Presentation.jsx` through documented `sendUserMessage`, using the saved prompt and an in-flight pointer/keyboard guard. Verify one normal message per activation, no implicit action on ordinary rows, no direct privileged tool call and current server authorization on the new turn; record browser outcomes in `ALZ\specs\005-inline-visual-output\quickstart.md`.

**Checkpoint**: Local/browser interactions are verified against accepted output.
Controlled current-permission denial remains required; Azure permission
enforcement is unverified residual risk, not a completion requirement.

## Phase 7: US4 - Reopen Answers in Any Supported Web View (P2)

**Goal**: Native restored presentations retain values/ownership/order/citations, work in both views/themes and follow existing text-history lifecycle.
**Independent test**: Reopen complete accepted fixture histories from fresh clients with generation/source access disabled, checking four view/theme combinations and admission negatives.

### Tests

- [X] T042 [P] [US4] Add native agent/workflow persistence and business-result regressions in `ORCH\tests\test_native_presentation_history.py` for complete versus interrupted output, readable review draft, optional presentation preservation and no repeated selection/source work for recorded completed outcomes.
- [X] T043 [P] [US4] Add Hosted/Durable/legacy/future-block history and owner denial fixtures in `UI\tests\test_native_presentation_history.py`, using real client interfaces with controlled boundaries rather than browser/process caches. Preserve existing citation behavior and no independent visual-history source ACL query.

### Implementation

- [X] T044 [US4] Reuse existing owner-admitted native history paths reached from `UI\src\gpt_rag_ui\api\native.py` and `UI\src\gpt_rag_ui\api\native_chat.py`, projecting Hosted response/input items and Durable `conversationHistory` with `UI\src\gpt_rag_ui\services\native_presentation.py`. Deduplicate by native turn/message plus presentation identity and expose neither text nor visuals on admission failure; do not add a transcript store/API.
- [X] T045 [US4] Preserve the accepted optional envelope through research/review/completed workflow results in `ORCH\src\native\workflow.py` and matched UI business readers reached by `UI\src\gpt_rag_ui\api\native_chat.py`'s `render_progress`. Extract actual response messages, not substring regex over flattened `answer.text`; keep human review readable and preserve both host serializers/state identities.
- [X] T046 [US4] Verify and complete standalone/embedded light/dark rendering, wide-table/long-label handling, keyboard focus, non-color status and fallback controls in `UI\public\elements\Presentation.jsx` and `UI\src\gpt_rag_ui\api\native_chat.py`, using the same projected native history as live output.
- [X] T047 [US4] Run local fresh-history/lifecycle fixtures and prepare the 20-case controlled SDK/history matrix in `ALZ\specs\005-inline-visual-output\quickstart.md`, including legacy, single/multi-agent/interrupted turns, disablement, retained snapshot access, new-action denial and conversation deletion/access revocation. Complete all 20 distinct local cases in T057; no actual-Azure reads or target approval is required. Never modify native history to retrofit compatibility.

**Checkpoint**: Local restoration and four-view projection work without source
calls. The 20-case fresh controlled SDK/history matrix remains T057; real-Azure
restoration/lifecycle is unverified risk, not a pending gate.

## Phase 8: US5 - Read a Coherent Multi-Agent Answer (P2)

**Goal**: One logical presentation retains enabled contributions in deterministic workflow/occurrence/block order with isolated sources and guidance.
**Independent test**: Two distinct enabled stable agents plus one disabled agent contribute separate datasets under varied completion timing with identical accepted ownership/order.

### Tests

- [X] T048 [P] [US5] Add isolation/ordering/aggregate/timeout-sibling regressions in `ORCH\tests\test_native_presentation_multi_agent.py`, including repeated node occurrences, same field names across sources, different guidance, one invalid contribution and an over-limit combined envelope.
- [X] T049 [P] [US5] Add ordered contribution/agent-attribution and replay-dedup fixtures in `UI\tests\test_inline_presentation_multi_agent.py`, preserving recognized siblings and readable text independently of completion order.

### Implementation

- [X] T050 [US5] Add a bounded synthetic multi-agent workflow fixture in `ORCH\tests\test_native_presentation_multi_agent.py` with distinct stable native definition IDs, explicit workflow/occurrence ordinals and separate sources. Integrate ordinal propagation through `ORCH\src\native\workflow.py`; do not treat current research executor names as independently configurable agents or introduce a new scheduler.
- [X] T051 [US5] Aggregate accepted contribution envelopes deterministically in `ORCH\src\native\presentation.py` and `ORCH\src\native\workflow.py`, preserving per-agent snapshots/source registries/local order and rejecting over-limit aggregate output atomically. Retain other contributions after one invalid/timed-out producer and prevent disabled producers from adding blocks.
- [X] T052 [US5] Render agent/source attribution and stable contribution order with shared projection in `UI\src\gpt_rag_ui\services\native_presentation.py` and `UI\public\elements\Presentation.jsx`, preserving existing normal text and replay deduplication without timing-based order.
- [X] T053 [US5] Run 20 timing-varied local native workflow fixture executions and verify exact ownership/order/disabled/source-call outcomes through `ALZ\specs\005-inline-visual-output\quickstart.md`. Record fixture versus real-host evidence separately and include required native-host cases in T057's final matrix rather than repeating the matrix after every edit.

**Checkpoint**: Local deterministic multi-agent increment passes. No independent agent or workflow publication has been deployed by this task list.

## Phase 9: Polish, Final Acceptance and Documentation

**Purpose**: Validate the complete candidate once, finish operator/customer delivery and hand off the exact compatible combination without publishing a release.

**Maintainer scope amendment — 2026-11-08:** Actual-Azure validation is removed
from implementation completion, not deferred. Behavioral/security requirements,
default-off, automated local provider/hook/usability checks and performance remain.
Azure persistence/ACL/deployed parity are unverified residual risks, not future
required gates. No global policy or release/publication approval is changed.

**Retired IDs (historical, never marked executed):** T054 dedicated Azure target
approval; T055 actual Hosted/Durable Azure smoke; T056 LIVE provider lifecycle
exercise. These IDs have no execution checkbox or active dependency.
SC-010 is covered by automated local provider/publication/hook checks.

 in `ALZ\specs\005-inline-visual-output\quickstart.md`: 20 distinct fresh controlled SDK/history cases, 20 timing-varied local multi-agent runs, Hosted/Durable agent/workflow shapes, four Playwright view/theme combinations, exact limits, unsupported/new text readers, reserved-marker attacks, zero visual external requests and controlled lifecycle/owner/new-action denial. Retain functional counts and actual public interfaces; no Azure target, actual-Azure 20-conversation matrix or live smoke is required. Reuse valid changed-boundary evidence without claiming deployed proof.
- [X] T057 Complete the final local FR/SC matrix in `ALZ\specs\005-inline-visual-output\quickstart.md`: 20 distinct fresh controlled SDK/history cases, 20 timing-varied local multi-agent runs, Hosted/Durable agent/workflow shapes, four Playwright view/theme combinations, exact limits, unsupported/new text readers, reserved-marker attacks, zero visual external requests and controlled lifecycle/owner/new-action denial. Retain functional counts and actual public interfaces; no Azure target, actual-Azure 20-conversation matrix or live smoke is required. Reuse valid changed-boundary evidence without claiming deployed proof.
- [X] T058 Measure at least 95% of 30 complete-content renders within 1 second on a documented device, including allowed content limits and excluding model/source waits. Record individual sanitized outcomes in `ALZ\specs\005-inline-visual-output\quickstart.md`. SC-008 uses controlled browser interaction checks; SC-010 uses both local provider/publication/hook implementations, including one-agent enable/disable without changing others.
- [X] T059 Prepare the user-approved central candidate page `DOCS\docs\agent-landing-zone\inline-visuals.md` at Agent Application → Chat & channels → Inline visuals in `DOCS\mkdocs.yml`. Agents contains only a per-agent enablement crosslink; add the subsequently approved upcoming What's new and relevant overview/configuration discoverability links. Preserve existing names/order and use the relevant Teams/Microsoft 365 and Copilot Studio runbook section order, numbered steps, admonitions and polished diagram style. Reuse the approved actual Chainlit 2.12 light/dark captures byte-for-byte with synthetic-data/local-mock captions; do not capture more chat screenshots. Include opt-in copyexample/default-off/no extra resources, guidance, Chainlit-only supported cards/typed tables/bar-grouped-bar-line charts/suggestions/identified row follow-ups, sort/filter/copy/native hover tooltip, no zoom/pan/chart drill-down, limits/text fallback, source/rule provenance reference and disable/reader-retaining rollback. Search T003's actual references, avoid duplicate manuals and shipped-availability claims, and keep private identities out. Placement and docs/PR image reuse approval are not issue publication approval.
- [X] T060 Complete customer-facing promoted schema/hash/valid-invalid/source examples under `ALZ\contracts\` and the central contract/sample documentation referenced by `DOCS\mkdocs.yml`, including a new text-only adapter example, safe future-block/version projection, exact precision and ordinary follow-up semantics. Verify component fixtures/packaging consume the same published contract identified in T005.
- [X] T061 Seal sanitized local acceptance evidence and integration/rollback handoff in `ALZ\specs\005-inline-visual-output\quickstart.md`: actual HEADs plus dirty-source hashes, tested packages/wheel hashes, doc revisions and passed/failed/blocked local checks. Record unbuilt image digests as unavailable, never invent them. Azure runtime is unverified residual risk, not a future required gate. Describe future `ALZ\manifest.json` binding under separately authorized release rules: matched readers/contracts before opt-in; rollback disables production but retains saved-data readers. No manifest pin/release/tag/image or issue publication is authorized by this task.

### Final integrated documentation and technical qualification (2026-11-08)

T059/T060 local artifacts are prepared in the existing DOCS feature worktree:
approved Chat & channels placement, incumbent-style runbook/diagram, unchanged
actual Chainlit 2.12 light/dark captures, upcoming discoverability and central
contract/text-reader reference. Final integrated customer adapter/contracts:
10 passed (1.36s); exact wheels/package-only schema/readers: one passed (1.999s).
DOCS strict build passed (187.06s); focused existing runbook/navigation/source/
SVG checks passed at desktop/390/320, as did diagram controls, keyboard/focus,
zoom/pan, no-JS fallback and unrelated Home/Gateway isolation. No new captures.
Fresh H01-H20 SDK/history cases passed on final UI HEAD (24 tests, 2.453s),
including two ordered multi-agent workflow snapshots. Thirty complete-content
renders passed the one-second criterion (maximum 692.8ms), including six allowed-
limit samples. Final protected UI visual suite: 19 passed (19.034s).
Final ORCH native Toolbox/runtime/tools/hosted/presentation/config/history/
multi-agent/safety selection: 194 passed, one skipped (120.16s).

The final technical dependency chain comprises T057's complete local counts,
T058's measured performance and T059-T061's documentation/contract/handoff work.
T061's sanitized revision/source/wheel/report seal and rollback handoff are in
quickstart; relevant full-quality failures are recorded rather than waived.
Docs/PR capture reuse is authorized; issue comments, release/pin binding and
publication remain separately gated. Component targets were integrated without
changing global policy pins; exact remaining quality findings are in quickstart.

### Local execution evidence (2026-11-07; historical)

This receipt supersedes earlier foundation-only/54-test/7-handler status.
T005 now has exact schema/hash/LF checks against both actual wheels and
package-only reader imports. UI's wheel used available setuptools 75.8.0;
it is schema-inclusion evidence, not qualification of declared setuptools
84.1.0. T022/T023 are implemented through shared generic settings paths;
Bicep/Terraform resources, selectors, pins and both deployment hooks are
unchanged. The earlier 218-test foundation receipt remains reusable.
At this earlier checkpoint T020/T026/T027 were unchecked; the later US2
receipt above completes their local reconciliation/provider evidence.
No live deployed lifecycle is claimed.

Backlog proposed paths are resolved by the actual inventory: UI production
modules are under `src/gpt_rag_ui/{api,services}`, collected cases under
`tests/`. Capture resides in public `presentation_middleware.py`, not
duplicated tool-specific knowledge code. Source/config/safety/action cases
reuse ORCH `test_native_presentation.py` and `test_native_runtime.py`;
history/application cases reuse UI `test_native_presentation.py`.
No wrapper test modules or new test runner were introduced.

Checked tasks indicate individually evidenced local behavior, not completion
of every broader story prerequisite or final acceptance gate. The latest
focused receipt below closes citation/fallback, adversarial/deadline,
safe diagnostics and browser/action criteria. Complete native lifecycle,
provider/channel matrices and T059-T061 publication-compatible delivery remain open.
T002/T003 inventory is now complete in quickstart; declared-pin full-environment
qualification remains a separate unresolved delivery gate.
Historical T054-T056 Azure tasks are retired; current T057-T058 local matrix
and measured performance criteria are superseded by the current final receipt.

**Checkpoint**: Mark each technical task complete only against actual evidence.

### Updated local component evidence

#### Final focused hardening receipt

The preceding receipts below are historical. Latest ORCH four-module receipt:
**102 passed in 13.62s**. Subsequent source-status/business-ID action cases
passed with all safety cases: **21 passed in 2.67s** (four added cases; unchanged
other modules are not claimed rerun). Exact expiry rejects; cancellation does
not await an uncooperative child; late failure retains correlation without
logging values. Native citation annotations survive enabled/off stream/final
guarding. Source-only table status and plain business-ID prompts retain exact
measurements and suppress missing/mismatched/non-string identifier actions.

UI actual native handlers: **11 passed in 2.343s**, readers/helpers **15 passed**,
replay **1 passed**. Fixes preserve assistant-admitted citations through native
`items`, retain readable text on optional element-construction failure and
reject all-null/repeated-category charts. Controlled native metadata revocation
denies restored history and new actions before native execution; this is not
actual host deletion or deployed source-permission acceptance.

Final Playwright: **1 passed in 21.939s**, eleven payload scenarios across
four standalone/iframe × light/dark views. The added long-label/wide-table
regression first failed in all four views; grid-card minimum sizing and local
exact-table scrolling fixed page overflow without clipping the whole page.
Keyboard, clipboard, source precision/nulls, spoof rejection, fallback and
duplicate-action guard pass with actual JSX/React and production API projection.
Authentication/API/data are mocked only at the local test boundary.
Eight screenshots and four trace ZIPs are ignored local synthetic artifacts.
Rebuilt current wheels passed exact-schema/package-only imports:
**1 passed in 3.991s**. Scoped Ruff passes; declared-pin TLS/backend and
full-quality import blockers remain unchanged, with no install retry.

Actual component code now exists in isolated ORCH/UI `inline-visual-output`
worktrees. ORCH implements opt-in capture, bounded structural normalization,
exact hydration, supervised deadline, native stream/final composition and
optional workflow fields. UI implements the admitted reader, shared REST/text
projection, native chat/history integration and build-free local SVG element.
These are local component behaviors, not completed live acceptance.

- ORCH: **85 passed** across runtime, presentation and multi-agent modules
  with prepared Core 1.24.0 and UI `src` available. After adding fresh
  checkpoint-resume assertions, the affected multi-agent module separately
  passed **22 tests**, including 20 timing-varied native graph executions.
- Actual public OpenAI function invocation returns a single text Content list;
  capture now admits that structural result without concatenating multimodal
  content. Selection stays tool-free. Disabled production does not capture
  or select; ordinary authorized tools still run normally.
- Explicit definition IDs/occurrence ordinals flow through the existing native
  research executor. Merge sorts ordinals, isolates guidance/sources, rejects
  aggregate overflow atomically and retains valid siblings after invalid or
  timed-out producers. Invalid first-producer revisions cannot poison siblings.
  Fresh native checkpoint resume preserves the reviewed envelope without
  repeated source calls. This is bounded sequential composition, no scheduler.
- UI reader/actual JS helpers: **14 passed**; native handlers: **8 passed**,
  including actual middleware-to-native-handler enabled/off/deadline/spoof
  cases. Public Durable state constructors serialize generated carriers with
  native `$type`/`messageId` history shape; fresh owner-admitted reads restore
  without generation/source access and wrong owners fail before state reads.
  Controlled native state I/O is not real host persistence/finalization.
- UI ordering/attribution/replay: **1 passed**. Actual JSX browser smoke:
  **1 passed**, covering four standalone/iframe × light/dark views, three chart
  variants, exact `9.750` clipboard text, pending duplicate-action suppression,
  zero external requests and zero runner errors. Installed Chainlit 2.9.4
  smoke is not declared 2.12.0 or secure production-embed acceptance.
- Current ORCH/UI wheels built; package-only schema integrity test:
  **1 passed** after rebuilding current sources. Scoped Ruff and four-worktree
  whitespace checks passed. Scoped mypy fails on three missing JSONSchema stub
  imports and one unavailable provider import; full quality is not passed.
- One secure truststore-based alternate declared-pin install failed TLS at
  `files.pythonhosted.org`. Declared UI wheel build fails because
  `setuptools==84.1.0` is unavailable. No certificate bypass or further install
  attempt was used.

Central documentation remains an unshipped coordination draft in isolated
`ai-landing-zones/inline-visual-output`, outside published navigation. No Azure
operation, deployment, commit, push, pin change or release was performed.

## Dependencies and execution order

### Latest explicit Playwright request

The user's unauthenticated/mocked-test authorization was applied only to the
local test harness. Production authentication was not changed. The expanded
actual JSX/installed React runner browser test passes in **19.650s**, using
real production REST/text projection through a mocked local API boundary.
Four view/theme combinations each cover ten payload scenarios: valid,
future block, malformed known table, future version, user/tool/progress spoof,
guarded primary marker, incomplete carrier and ordinary text. Decimal scale,
null geometry gaps, status filtering/copy headings, stable sorted-row action,
keyboard chart values, pointer/keyboard follow-ups and pending dedup are
asserted. No external request or runner error occurred. Eight screenshots and
four Playwright traces are under UI `.artifacts/inline-presentation-playwright/`
(ignored, synthetic data only). Commands/artifact scope are in quickstart.
T037-T039 are now individually complete locally. T041's complete current
authorization matrix and T046's wide-table/long-label/focus matrix remain open;
mocked browser delivery does not replace actual host/permission acceptance.

### Phase and story graph

```text
Setup T001-T003
        |
Foundation T004-T010
        |
        +---- US1 (P1) ----+---- US6 (P1)
        |                 +---- US3 (P2)
        |                 +---- US4 (P2)
        |
        +---- US2 (P1) ----+
                          |
                     US5 (P2, also needs US1)
                          |
All local story checkpoints
                          |
Controlled SDK/history/Playwright matrix -> measured renders/automated usability
                          |
Central docs + customer contracts + exact-combination handoff
```

US2 configuration work can begin after foundations independently of US1. Its final text-client integration needs US1's projection. US6, US3 and US4 integrate US1 but do not depend on one another for local implementation. US5 needs US1 production primitives and US2 workflow snapshots. They can be tested with accepted fixtures independently of higher-level interactions. None may bypass the final safety/history gates to publish an MVP.

### Task prerequisites

The following table is the execution dependency list, not merely a suggested ordering. A phase gate still applies even where a row lists a narrower dependency.

| Task or group | Prerequisites |
| --- | --- |
| T001, T002 | None |
| T003 | T002 |
| T004 | T001-T003 |
| T005 | T004 |
| T006, T007 | T005 |
| T008 | T006 |
| T009 | T006, T007 |
| T010 | T006 |
| T011, T012, T020, T021, T028, T029 | All T004-T010 |
| T013 | T011 |
| T014 | T013 |
| T015 | T014 |
| T016 | T015 |
| T017 | T012 |
| T018 | T016, T017 |
| T019 | T011-T018 |
| T022 | T020 |
| T023 | T022 |
| T024 | T021, T023 |
| T025 | T018, T024 |
| T026 | T023, T024 |
| T027 | T025, T026 |
| T030 | T014, T028 |
| T031 | T016, T030 |
| T032 | T031 |
| T033 | T018, T029 |
| T034 | T017, T033 |
| T035 | T028-T034 |
| T036, T042 | T016 |
| T037, T043 | T018 |
| T038 | T037 |
| T039 | T038 |
| T040 | T014, T036 |
| T041 | T039, T040 |
| T044 | T018, T043 |
| T045 | T009, T016, T042 |
| T046 | T017, T044 |
| T047 | T044-T046 |
| T048 | T019, T027 |
| T049 | T018 |
| T050 | T024, T048 |
| T051 | T016, T050 |
| T052 | T018, T051 |
| T053 | T049-T052 |
| T057 | Local story checkpoints T019, T027, T035, T041, T047, T053 |
| T058 | T041, T046, T057 |
| T059 | T003, T057, T058 |
| T060 | T005, T059 |
| T061 | T057-T060 |

Shared-file edits must be serialized even when the graph allows concurrency: `presentation.py`, `config.py`, `workflow.py`, `native_presentation.py`, `native_chat.py`, `Presentation.jsx` and `quickstart.md` are not independent worktrees inside a repository. Use coherent sequential batches rather than simultaneous writes.

### Parallel examples per story

These are scheduling examples, not requests to spawn agents or workflows:

- **US1**: T011 runtime fidelity tests and T012 UI fixtures after foundations. After T012, T017's JSX renderer can progress alongside T013-T016 runtime work in distinct files.
- **US2**: T020 umbrella publication tests and T021 runtime snapshot tests after foundations.
- **US6**: T028 runtime safety tests and T029 UI adversarial fixtures after foundations.
- **US3**: T036 runtime row-binding tests and T037 UI action fixtures after their respective producer/projection prerequisites.
- **US4**: T042 runtime persistence tests and T043 UI history fixtures after their respective prerequisites.
- **US5**: T048 runtime ordering/isolation tests and T049 UI attribution fixtures once T019/T027/T018 are complete.

## Requirement traceability

| Requirement | Primary tasks |
| --- | --- |
| FR-001 | T010, T021, T024 |
| FR-002 | T015, T024, T048-T051 |
| FR-003 | T014, T017, T040-T041 |
| FR-004 | T011, T013-T015 |
| FR-005 | T006, T011, T014 |
| FR-006 | T012, T014, T017, T039 |
| FR-007 | T037-T038 |
| FR-008 | T036, T040-T041 |
| FR-009 | T037, T041 |
| FR-010 | T008, T018, T025, T033 |
| FR-011 | T017, T039, T046, T057 |
| FR-012 | T042-T047, T057 |
| FR-013 | T048-T053 |
| FR-014 | T028, T030, T048, T051 |
| FR-015 | T004-T005, T060 |
| FR-016 | T028-T035, T057 |
| FR-017 | T028, T030, T035 |
| FR-018 | T008, T029, T033-T034, T057 |
| FR-019 | T013, T040-T047, T057 |
| FR-020 | T007, T025, T029, T033, T043 |
| FR-021 | T020, T022-T027, T057, T058 |
| FR-022 | T003, T059-T060 |
| SC-001 | T011-T019, T057 |
| SC-002 | T037-T041, T046, T057 |
| SC-003 | T021, T025, T028-T035, T057 |
| SC-004 | T047, T057 |
| SC-005 | T048-T053, T057 |
| SC-006 | T028, T030, T035, T057 |
| SC-007 | T031, T035, T058 |
| SC-008 | T058 |
| SC-009 | T029, T034, T043, T057 |
| SC-010 | T058, T059 |

## Implementation strategy

1. Complete setup/foundations and use US1 as a local synthetic MVP: faithful single-agent output with readable fallback. No demo or production deployment is part of that milestone.
2. Complete P1 opt-in and safety, then P2 interactions/history/multi-agent increments. Run only affected local tests and retain valid evidence for unchanged boundaries.
3. After local checkpoints, complete T057's controlled public SDK/history and
   Playwright matrix. Azure live tasks are removed, not scheduled later.
4. Complete functional counts, measured performance and automated browser/provider
   checks once. Respect source-sealed reports and invalidate changed boundaries.
5. Coordinate candidate docs and exact reader/runtime/contracts handoff. Keep
   production off; release binding/publication needs separate authorization.

## Summary

58 active task IDs and three retired IDs (T054-T056), retained historically
without executed checkboxes. Final cross-cutting delivery is T057-T061.
No named tool prerequisite, default resource or default operator step is added.
