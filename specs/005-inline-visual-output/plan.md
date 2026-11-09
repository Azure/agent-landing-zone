# Implementation Plan: Native Inline Visual Output

**Branch**: `feature/inline-visual-output` | **Date**: 2026-11-07 | **Spec**: [spec.md](spec.md)

**Input**: `specs/005-inline-visual-output/spec.md`, based on issue #691 and its review comment.

**Status**: ADR-0040 is accepted for local implementation. On 2026-11-08 the
maintainer removed real-Azure validation from completion, not deferred it.
Controlled public SDK/history, authorization/lifecycle, Durable, UI and local
provider/hook checks remain required. Azure runtime/deployed parity is an
unverified residual risk, not a future mandatory gate. Acceptance comprises
automated functional/provider/usability checks and measured render performance;
no repository-wide rule is changed.

## Summary

Add per-agent opt-in inline cards, tables, charts, and follow-up prompts while preserving text fallback, source integrity, and authorization. The model selects presentation and source fields, not measurements. Runtime components assemble and validate data, render it, and restore it through native state.

Any user-selected native or MCP tool, including customer-defined tools, can supply eligible typed results. There is no fixed tool-name allowlist and no mandatory NL2SQL integration. Unsupported or lossy results retain authorized text. Historical snapshots follow existing text-history access rules without introducing source-permission revalidation; new queries and follow-ups enforce current permissions.

The issue predates ADR-0034's native-runtime transition. Do not extend the retired classic stream or element data layer. The maintainer explicitly selected keeping the current Hosted Responses protocol in this planning conversation. A switch to Invocations, custom SSE proxy, new transcript database, or SDK monkeypatch is not authorized.

Research found no documented custom presentation-event extension point. The minimum proof instead passed with deterministic application JSON in standard `output_text`, without changing Responses. Fresh clients recovered identical table/chart data through agent-scoped response retrieval and conversation history. [feasibility.md](feasibility.md) records the exact evidence and remaining product gates.

## Technical Context

**Language/Version**: Python >=3.12 in both component manifests, Python 3.12 in orchestrator CI, and build-free JSX in Chainlit. The minimal code-deployed fixture used Python 3.13, not a new product Python pin.

**Primary Dependencies**: Manifest-pinned UI v3.6.0 and orchestrator v7.1.0. Both use Core 1.24.0, the UI uses Chainlit 2.12.0/OpenAI 3.38.0, and the runtime uses Foundry client 1.16.0. Hosted uses Foundry Hosting 1.0.0b261030. Durable uses agent-framework-durabletask 1.0.0b261029 and durabletask/durabletask-azuremanaged 1.12.0. The minimal live fixture resolved Agent Server Core 2.3.0 and Responses 2.4.0. This plan changes no pins or approved release combination.

**Storage**: Foundry owns Hosted state, DTS owns durable Container Apps state. Standard Hosted message `output_text` retained the proof JSON in response and conversation history through the agent-scoped protocol API. No visual side store was used. Product owner/lifecycle and Durable restoration still require proof.

**Testing**: Seven local SDK checks and the minimum live Hosted stream/response/conversation comparison passed. No product BFF, Chainlit, Durable, or infrastructure parity acceptance was exercised. Existing component and provider/lifecycle regressions remain implementation obligations.

**Target Platform**: Native Foundry Hosted Responses and Durable Container Apps, with standalone and embedded Chainlit in both themes. Other channels receive text fallback.

**Project Type**: Multi-repository platform, runtime, and UI feature with a shared versioned presentation contract.

**Performance Goals**: Each enabled agent's additional visual-generation stage completes or times out within 10 seconds elapsed time, including retries, after its authorized source results and primary answer are available. Timeout preserves text and other valid contributions and rejects late results. This is a per-agent stage budget, not a total multi-agent workflow SLA. Separately, SC-007 requires readable output within 1 second in 95% of 30 representative turns after complete content is available. SC-008 uses controlled browser reading/follow-up assertions. Record the reference device and dataset during validation.

**Constraints**: Default off per agent. Tool-result measurements only. Source or approved deterministic rules for indicators. No remote scripts, active HTML, executable expressions, CSP relaxation, extra chart bundle, or duplicated native checkpoints. Limits: 10 blocks/turn, 500 rows/table, 8 series/chart, 1,000 points/chart, and 262,144 UTF-8 bytes of presentation content/turn, with exact-boundary acceptance and no silent truncation.

**Scale/Scope**: Four block families, three chart variants, table sort/filter/copy and optional row action, suggestions, multi-agent ordering, native history, two web views/themes, both infrastructure providers. No new connectors, dashboard engine, relationship graphs, or native Teams/Microsoft 365 visuals.

## Constitution Check

*GATE: Check before research and again after Phase 1 design.*

| Principle or gate | Pre-research assessment | Post-design assessment |
| --- | --- | --- |
| I. Repository/provisioning boundaries | Pass: runtime stays in component repositories | Pass for planning: no runtime added here |
| II. Compatible explicit contracts | Verify native carrier and history before selecting wire shape | Pass for design: three draft schemas, tool-independent normalization, native message/result mapping, reader-first rollout and rollback |
| III. Identity/confidentiality | Preserve owner checks and invocation-scoped tool authorization | Local controlled denial/lifecycle tests required; Azure enforcement unverified |
| IV. Observable failure | Reject invalid visuals with text and safe diagnostic reasons | Pass for design: 10-second stage deadline, diagnosed timeout/unsupported data, late-result exclusion; implementation evidence required |
| V. Verifiable evidence | Source research can begin, no deployed claim | Local and live Hosted evidence recorded, remaining product gates unrun |
| VI. Infrastructure parity | Assess providers and hooks for configuration changes | Both local adapters/provider/hook regressions required; mocks are not deployed parity |
| Architectural decision | Record new contract/state decision before implementation | ADR-0040 accepted locally with explicit maintainer proof-method amendment |
| Product documentation | Central current-source impact must be assessed | Current-main navigation inventory recorded, update shipped pages during delivery |

The maintainer-approved amendment changes feature-level proof method only.
Implemented runtime/UI behavioral and security tests remain gates, using
controlled local SDK/history boundaries. No protocol/store/host-scope change,
global parity waiver or production/release authorization is implied.

## Project Structure

### Documentation (this feature)

```text
specs\005-inline-visual-output\
  spec.md
  checklists\requirements.md
  plan.md
  research.md
  feasibility.md
  data-model.md
  contracts\
    turn-presentation-v1.schema.json
    presentation-selection-v1.schema.json
    agent-presentation-settings-v1.schema.json
    delivery.md
    configuration.md
    tool-results.md
    examples\
  quickstart.md
```

Schemas, examples and integrity metadata are draft feature artifacts, not published root contracts. `tasks.md` belongs to the subsequent `/speckit-tasks` phase and is intentionally not generated here.

### Source Code (repository root)

```text
contracts\                                  Shared schemas and integrity metadata
config\deployment\native.py                  Public host/mode and feature resolution
config\deployment\composition.py             Application settings and dependencies
config\deployment\appconfig_intent.py         Runtime intent/publication validation
config\deployment\appconfig_ownership.json    Setting authority and content-type rules
main.parameters.json                        Provider-neutral declaration
infra\bicep\main.bicep                       Foundation provider
infra\terraform\                            Foundation counterpart
scripts\                                    PowerShell/shell azd lifecycle
tests\                                      Platform and hook regressions
infra\tests\                                Offline foundation contract checks
docs\adr\ADR-0040-native-inline-presentation.md
```

**Structure Decision**: Keep umbrella runtime-free. Actual ORCH owners are
`src/native/config.py`, `agent.py`, `contracts.py`, `workflow.py`,
`presentation.py` and public `presentation_middleware.py`; no `knowledge.py`
exists in this baseline. UI owners are `src/gpt_rag_ui/api/native_chat.py`,
`api/native.py`, `services/native.py`, `services/native_presentation.py` and
`public/elements/Presentation.jsx`. Do not modify retired classic transport.

## Phase 0 Research Result

- The classic orchestrator is retired. The legacy UI stream is unframed text, and its element data-layer no-ops are not the new persistence target.
- Ignoring unknown events in the Hosted UI client does not prove the hosting SDK or Foundry can emit, persist, or restore custom events.
- Official Responses hosting uses typed output/event builders. Research found no documented application-defined presentation event. Do not invent `TurnPresentationEvent` as a wire API.
- A deterministic standard `output_text` envelope passed the exact-SDK local probe and live Hosted streaming, response retrieval, and conversation-history comparisons. Correct reads use the agent-scoped protocol base, not the project-wide OpenAI base.
- Pinned Durable UI reads `read_agent_state(...).to_dict()["data"]["conversationHistory"]` for agent history and official completed workflow output for workflows. Existing native result validation/projection is explicit, not a new storage mechanism.
- The native human-review sample does not establish general multi-agent contribution ordering. Define explicit stable contribution ordinals, not completion-time order or a new scheduler.
- Chainlit custom-element messaging is documented. Local SVG and embedded rendering remain small smoke-test obligations.

**Research exit**: The carrier, native extension seams, draft shape, configuration ownership and current CI commands are resolved. Unrun product owner/lifecycle, middleware-finalization, Durable and UI tests have concrete acceptance scenarios in [quickstart.md](quickstart.md). Their eventual failure blocks opt-in/full delivery. It does not require a finished product before its design.

## Phase 1 Design

### Contracts, data model, and validation

Define separate model-selection, hydrated-presentation, approved-rule, and delivery contracts. Selection contains source handles/field mappings, not measurements. Scope source handles to the authorized invocation and contributor. Never persist credentials or re-fetch data using a source reference as authorization.

Normalize captured successful results through shared typed structural adapters, not a registry of eligible tool names or an NL2SQL-specific path. Existing and customer-defined tools use the same normalization/hydration interface. [tool-results.md](contracts/tool-results.md) defines eligibility, runtime-assigned provenance, precision and row identity. Tool names remain attribution and approved-rule scope, not enablement. This does not relax existing tool admission, MCP endpoint allowlists or authorization.

Preserve exact numeric precision through serialization and browser copying. Reject missing/incompatible columns, ambiguous series/units, nonfinite numbers, and conflicting rules. Missing values remain null/gaps. Guidance never substitutes for validation.

The three [draft schemas](contracts/README.md) separate selection, hydrated turn data and agent settings. [data-model.md](data-model.md) defines immutable source/contribution identities, typed exact values, rules and state transitions. Producer schemas are strict, while new readers safely project known blocks and ignore unknown optional fields. Unsupported versions retain the stable fallback.

Numeric rules are owner-approved disjoint cases, each a conjunction of at most two fixed comparisons on the same typed source field. Missing/no-match indicators are omitted. No model rule or expression evaluation exists. Aggregate limits count all accepted contributions, non-null plotted chart values, and the full compact UTF-8 envelope including fallback/provenance, excluding native framing. Exact limits are accepted.

### Per-agent configuration and ordering

Prefer one versioned per-agent settings object over a global enable flag or another deployment selector. Default to an empty map with no enabled agents. Include enablement, guidance, and approved declarative rules, not secrets or authorization inputs.

Publish `AGENT_PRESENTATION_SETTINGS` as compact JSON in `text/plain`, label `agent-lz`, through existing provider-neutral `additionalAppConfigurationSettings`. Add it as typed `ordinary` ownership with an explicit `json_object` validator. Do not classify it as generated `controlled` authority or bypass validation as an unknown setting. [configuration.md](contracts/configuration.md) specifies default/disable/reconciliation behavior.

Add the key to `src/native/config.py`'s selected `BASE_KEYS` and functional snapshot. Use a request-owned selected refresh for this functional key at the next turn, rather than silently relying on the 30-second provider refresh throttle. Freeze it for the workflow and keep authorization/MCP capability settings live as today.

The current stable conversation agent ID is `agent-lz-conversation`. The current research executor calls that same agent, not a separate configurable analytical agent. When adding the required multi-agent fixture, assign distinct stable native definition IDs and explicit deterministic workflow ordinals. Repeated node occurrences get definition-assigned occurrence ordering. Demonstrate two enabled and one disabled agent with varied completion timing, not merely the existing human-review sample.

### Native delivery and history

Use public function middleware to capture authorized supported results and public agent middleware to compose output. Preserve ordinary narration. For enabled agents, perform one bounded tool-free structured selection call with the public chat client, then deterministically hydrate/validate and append a canonical envelope in ordinary native assistant text. Disabled agents add no call. Public `ResponseStream`/response finalization must preserve the exact same appended message in live output and saved completed state.

Start one absolute monotonic 10-second deadline for the additional stage, including normalization, selection, hydration, validation and compact serialization. Any SDK/network retries consume the remaining budget, never start another 10-second window. Keep bounded processing responsive to the deadline. Race the stage against that deadline, seal its acceptance/timeout decision once, signal cancellation on expiry, and observe cleanup/errors without delaying text to await an uncooperative selection request. A late completion cannot mutate output or reopen the sealed contribution. Existing native replay uses recorded completed outcomes rather than repeating selection for a saved answer. Deadline/cancellation/finalization behavior on both hosts is an implementation stop gate, not an already verified SDK guarantee.

For workflows, the existing `answer.text` flattening is insufficient. Extend `ReviewRequest`/`ResearchReviewResult` with an optional typed `presentation`, mirrored by UI strict readers. Extract from real response messages, leave `draft` readable, omit the field for nonvisual output, and carry the accepted object through native human-review/result state on both hosts. This changes business payloads, not DTS state-version identity.

Do not use UI Cosmos, browser/process memory, a new transcript service, or tool re-execution as authoritative restoration. Current UI owner admission binds UUID sessions to principal, host/application and publication before native reads. Preserve it. New text-only frontends receive markdown from the supported envelope-aware server/customer adapter. Unaware old raw Responses clients are not acceptance targets.

If source permissions change while conversation access remains valid, saved visuals follow the same historical snapshot rules as saved text. Do not add a source ACL lookup solely to restore visuals. Preserve existing citation handling, native access, retention and deletion; a new row action or query still uses current source permissions.

Accept only complete immutable envelopes, never selection/partial JSON. Preceding ordinary text remains available after interruption. Deduplicate by native message/turn identity plus generated presentation ID. See [delivery.md](contracts/delivery.md) for exact host mapping, projection and failure behavior.

### UI

Use one build-free Chainlit custom element, supported shadcn/Tailwind/lucide imports, and local SVG charts. Render labels/values as text, never executable markup or remote-resource attributes. Handle citations separately through approved existing paths.

Table sorting/filtering is local display state, not mutation of saved results. Copy headings and visible rows in displayed order with source precision. Bind row actions to stable authorized row identifiers and use normal `sendUserMessage`. Prevent duplicate activation while a message is in flight, with server-side authorization on the resulting request.

### Infrastructure and lifecycle parity

The intended feature adds no foundation resource, identity, secret, role, endpoint, or network egress. Assess generic App Configuration publication in both providers and update affected shared configuration/composition consumers together.

If templates do not change, document concrete non-impact and run both adapter/provider regressions. If they change, update both together. Preserve Terraform lock/module pins and Bicep provenance. Compare defaults, encoding, label, ownership, provision/deploy/reprovision/disable/teardown, and both hook implementations. Compilation/mocks are not deployed parity.

### Evidence and documentation

Map all 22 functional requirements and 10 outcomes to contract/runtime/UI/compatibility/authorization/parity/user exercises, including both native hosts.

Observed umbrella commands include targeted pytest, offline foundation contracts and Terraform fmt/init/validate/test. Orchestrator PR CI uses Python 3.12, host-specific requirement files and `pytest -q --junitxml=.artifacts/pytest.xml`. UI uses its tracked `run-unittest.py` with a resolvable base ref and `QUALITY_RUN_ID` for local evidence. [quickstart.md](quickstart.md) separates those existing runnable commands from future feature acceptance scenarios.

### Minimum-work validation policy

The default development loop is local and change-scoped, with no Azure provisioning or mandatory full Landing Zone deployment. Use synthetic authorized results and deterministic selection/clock fixtures to exercise changed contracts, normalization, limits, timeout and reader behavior without remote tools or model calls. Run the smallest relevant existing selectors, combine related cases in one runner, and reuse prepared dependency environments. Retain repository-required CI checks; a broad CI suite need not also be repeated manually for the same source.

Escalate only at a changed boundary or failed check. Runtime/UI changes do not by themselves require rerunning unchanged foundation suites. Configuration publication, provider or hook changes require the affected Bicep/Terraform/shared and PowerShell/shell checks, with explicit counterpart impact. Use offline parity checks during iteration, not full provisioning; they do not establish deployed parity.

Complete acceptance locally using public SDK streaming/completed output,
controlled Hosted/Durable state/history client interfaces, owner/action denial,
deadline races and Playwright. No dedicated Azure target, live smoke or deployed
provider exercise belongs to this execution backlog. Retired T054-T056 are
historical IDs, not completed runs or work to schedule.

All Azure and demo operations remain unauthorized, including inspection,
traffic, configuration, deployments, data access, restarts and cleanup.
Record Azure persistence/ACL/deployed-parity uncertainty as residual risk,
not a missing-target completion blocker or future required gate.

Run the complete mapped local matrix once for the candidate, not every edit.
Reuse unchanged source-sealed evidence with recorded hashes/dependencies and
impact assessment. Changed boundaries invalidate corresponding evidence.
Keep both host shapes, 20 distinct controlled histories, 20 timing-varied runs,
30 measured renders and automated local provider/publication/hook checks.

The actual central page inventory was searched. The user-approved candidate
placement is Agent Application → Chat & channels → **Inline visuals**, source
`docs/agent-landing-zone/inline-visuals.md`, with only an Agents crosslink to
per-agent enablement. Preserve existing nav names/order; no duplicated manual.
Keep the unreleased notice and text-only/unverified-channel limits. Placement
approval is not issue screenshot publication approval or shipped availability.

## Adoption, Compatibility, and Recovery

1. Review Proposed [ADR-0040](../../docs/adr/ADR-0040-native-inline-presentation.md) and these draft contracts before implementation approval.
2. Promote schemas/integrity fixtures and implement accepting UI/customer readers, shared projections and matched optional business-result fields with production off.
3. Implement shared typed structural result adapters, exact-value/rule enforcement, the 10-second deadline and public middleware producers on both hosts. No unsupported/lossy result is silently treated as supported and no named integration is a prerequisite.
4. Implement umbrella typed ordinary publication and native settings snapshots. Run provider/hook/configuration checks with all agents initially disabled.
5. Pass controlled local finalization, authorization/lifecycle, Hosted/Durable
   history, UI, limits/performance and automated provider/publication/hook
   checks.
6. Record the exact compatible commits/images/packages and evidence, update central shipped documentation, then bind only the actually validated combination in a separately authorized release. No future tags are invented here.

Rollback disables new visual production first and retains new readers and matched result contracts for saved turns. Do not roll readers back to binaries unable to understand persisted envelopes/result fields. The minimum proof marker was `inline_visual_proof`, not the draft product marker `agent_lz_presentation`. Its carrier result is not a full product-schema acceptance result. Never delete/convert native sessions, checkpoints or saved visuals. Incompatible graph/runtime changes follow ADR-0034's isolated publication/task-hub policy.

The original planning invocation authorized no resource creation. On 2026-11-07 the maintainer separately authorized a minimal low-cost proof in a new resource group in the requested subscription. This does not authorize production operations, full Landing Zone provisioning, tags, or releases.

## Completion and Hooks

The setup script found the feature through `.specify/feature.json`. Its JSON `BRANCH` field returned the directory identifier `005-inline-visual-output`, not the actual Git branch recorded above.

No `.specify/extensions.yml` exists, so before/after planning hooks are skipped. Phase 0 decisions and Phase 1 design incorporate all three accepted clarifications. Prior pinned-source/SDK research is reused because no host, library or protocol choice changed; no new research-agent or Azure operation is needed. Draft schemas/examples are validated separately from unrun product acceptance. No runtime implementation, `tasks.md`, manifest change, commit, release, product-doc publication or additional Azure operation belongs to this planning step.
