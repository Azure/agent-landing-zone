# Research: Native Inline Visual Output

**Date**: 2026-11-07
**Status**: Phase 0 design research complete. Minimum local/live Hosted carrier/history proof passed. Remaining product and deployed acceptance evidence is explicitly unrun.

## Evidence Baseline and Limits

Component research used the manifest-pinned sources:

| Component | Tag | Commit |
| --- | --- | --- |
| agent-app-ui | v3.6.0 | `8a45595aa321d8841e7a4555d542b890beebf1b0` |
| agent-app-orchestrator | v7.1.0 | `666d39862590cfb165097ee55737a1ef66fd2afc` |

These are research baselines, not a validated future release combination.

Initial vendor research used package metadata, documentation, and upstream source. The subsequent proof inspected released SDK archives, resolved an isolated local environment, and exercised the official host locally and in a minimal live Foundry deployment. Standard text deltas, completed output, fresh response retrieval, and conversation history preserved identical synthetic table/chart JSON. Product authorization/lifecycle, Durable, and UI smoke were not exercised. See [feasibility.md](feasibility.md) for exact scope, dependencies, routing, packaging, and stopped-compute evidence.

Current-main documentation navigation was inventoried from `mkdocs.yml`. Page-content searches/updates remain implementation work. Do not treat develop-page prose or this draft as shipped behavior.

## 1. Hosting Boundary

**Decision**: Retain native Hosted Responses and durable Container Apps integrations. Do not extend retired classic execution.

**Rationale**: ADR-0034 requires official native host integrations and host-owned state. Pinned orchestrator research found `src/orchestration/orchestrator.py` raises the retirement error, while current entrypoints are `src/native/hosted.py` and `src/native/durable.py`.

**Alternatives considered**: Extend classic HTTP streaming, switch Hosted to Invocations, or implement a custom proxy. Classic is retired, and the maintainer selected keeping the protocol. A proxy or monkeypatch would hide incompatible host behavior.

**Evidence**:

- [ADR-0034](../../docs/adr/ADR-0034-native-agent-and-workflow-hosting.md).
- [Pinned hosted entrypoint](https://github.com/Azure/agent-app-orchestrator/blob/666d39862590cfb165097ee55737a1ef66fd2afc/src/native/hosted.py).
- [Pinned durable entrypoint](https://github.com/Azure/agent-app-orchestrator/blob/666d39862590cfb165097ee55737a1ef66fd2afc/src/native/durable.py).
- [Pinned retired execution module](https://github.com/Azure/agent-app-orchestrator/blob/666d39862590cfb165097ee55737a1ef66fd2afc/src/orchestration/orchestrator.py).

## 2. Hosted Presentation Carrier

**Decision**: Use standard `output_text` for a deterministic versioned application envelope. The minimum carrier passed. The draft product schema is separately defined, not claimed live-tested by this fixture.

**Rationale**: Existing client unknown-event tolerance proves only local client compatibility. Research found standard typed Responses builders and no documented general-purpose custom SSE emission hook. A made-up event name cannot establish platform pass-through or persistence.

**Alternatives considered**: Arbitrary SSE event, standard output metadata, a native structured output, Invocations, or side-channel storage. The proof used a normal message/text output through official `Agent`, public `BaseChatClient`, and `ResponsesHostServer` APIs. Invocations is outside the maintainer's chosen direction. Misusing refusal/citation/tool events or introducing a side-channel transcript store is rejected.

**Evidence**:

- [Foundry hosting package metadata at researched compatible version](https://pypi.org/pypi/agent-framework-foundry-hosting/1.0.0b261030/json).
- [Upstream Responses implementation, unpinned investigation reference](https://github.com/microsoft/agent-framework/blob/main/python/packages/foundry_hosting/agent_framework_foundry_hosting/_responses.py).

**Proven minimum**: Core 1.24.0, Foundry Hosting 1.0.0b261030, Agent Server Core 2.3.0, and Responses 2.4.0 support the fixture. Live retrieval uses the deployed agent-scoped OpenAI protocol base for both responses and conversation items. Decimal strings retain trailing zeros. Reads issue no generation request. The local fresh-host test additionally disables fixture execution and verifies one source call total.

**Unrun acceptance**: Public middleware stream/final-result parity, product owner/deletion/retention, Durable restoration and Chainlit behavior. Concrete implementation scenarios are in [quickstart.md](quickstart.md). These do not require the finished feature before design.

## 3. State and History

**Decision**: Keep presentation content with Foundry/DTS native output/state. UI Cosmos remains owner/product metadata, not a second transcript/checkpoint store.

**Rationale**: ADR-0034 explicitly separates native state from UI metadata. Restoring visuals must preserve values without re-querying tools or persisting invocation credentials.

**Alternatives considered**: UI element records, a new transcript container, browser-only data, or data re-fetch. They respectively widen storage boundaries, duplicate content/lifecycle obligations, lose reopening, or violate stable historical values and authorization assumptions.

**Evidence**:

- [ADR-0034 state/identity decision](../../docs/adr/ADR-0034-native-agent-and-workflow-hosting.md).
- [Durable extension package metadata/documentation](https://pypi.org/pypi/agent-framework-durabletask/1.0.0b261029/json).
- [Official durable extension source](https://github.com/microsoft/agent-framework-durable-extension).

Pinned product inspection establishes official Durable agent state reads via `read_agent_state(metadata.get_state()).to_dict()["data"]["conversationHistory"]`, and completed workflow output via the official workflow client. UI `NativeService` strictly validates current review requests/results before rendering. Schema markers do not authorize reads. Fresh real restoration remains unrun, and cross-version checkpoint replay is not presumed supported.

**Workflow decision**: Do not flatten appended native envelopes into `answer.text`. Add optional typed `presentation` to existing `ReviewRequest` and `ResearchReviewResult`, mirrored by strict UI business models. Keep `draft` as readable markdown and omit presentation for nonvisual results. Both host serializers retain that native business payload. A separate store or guessed custom Durable event is unnecessary.

**Clarified access policy**: Originally authorized saved snapshots follow existing text-history access/retention/deletion rules. Source-access revocation does not introduce a new visual-history ACL lookup. Existing conversation admission and citation behavior stay authoritative. New queries and follow-ups always use current source permissions. Revalidating every original source on restoration was considered and rejected by the maintainer.

## 4. Source Integrity and Indicators

**Decision**: Separate untrusted model selection from hydrated data. Capture authorized tool results within the invocation, bind them to contributor/source handles, and apply only source-derived or owner-approved deterministic indicators.

**Rationale**: The pinned native tool path already keeps invocation identity separate from persistent state. Model-provided IDs, partition labels, or row actions are not authorization. Neither values nor status judgments may be reconstructed from model prose.

**Alternatives considered**: Ask the model to copy numbers, re-fetch later with stored credentials, or infer status from narrative. All weaken fidelity or access boundaries.

**Evidence**:

- [Pinned tool identity and tool composition](https://github.com/Azure/agent-app-orchestrator/blob/666d39862590cfb165097ee55737a1ef66fd2afc/src/native/tools.py).
- [Pinned agent invocation boundary](https://github.com/Azure/agent-app-orchestrator/blob/666d39862590cfb165097ee55737a1ef66fd2afc/src/native/agent.py).

## 5. Multi-Agent Ordering

**Decision**: Introduce explicit stable contribution ordinals and deterministic occurrence ordering in native workflow definitions, preserving local block order. Do not sort by completion timing.

**Rationale**: Research found a research/human-review workflow, not an existing generalized multi-agent presentation aggregator. Current sample behavior cannot be claimed as proof of FR-013.

**Alternatives considered**: Completion order, alphabetic agent IDs, inferred edge traversal, or an additional workflow scheduler. None establishes the declared workflow contribution order as reliably as explicit ordinals.

**Evidence**: [Pinned workflow definitions](https://github.com/Azure/agent-app-orchestrator/blob/666d39862590cfb165097ee55737a1ef66fd2afc/src/native/workflow.py).

Pinned `contracts.py` defines `AGENT_NAME="agent-lz-conversation"` and `WORKFLOW_NAME="agent-lz-research-review"`. Current executor IDs are `research`, `human-review` and `complete`; research invokes the same conversation agent. A multi-agent fixture must add distinct stable native agent IDs, not pretend existing executor labels are independent agents. Freeze functional settings for a run while reevaluating authorization for new actions.

## 6. Chainlit Renderer and Follow-Ups

**Decision**: Use a build-free custom element with approved imports, theme tokens, and normal user-message follow-ups. Validate local SVG and embedded behavior rather than adding a chart library.

**Rationale**: Official documentation supplies `sendUserMessage(message, command?)` and a restricted React/shadcn/lucide import surface. Existing custom elements provide local precedent. Plain SVG JSX is a candidate with no external dependency, but browser smoke remains required.

**Alternatives considered**: PNG bot, remote chart/CDN library, arbitrary model-authored HTML, or direct tool execution from controls. These conflict with native interaction, isolation, output safety, or normal authorization.

**Verified UI integration**: The native path is Chainlit `api/native_chat.py`, sharing `NativeService` with REST `api/native.py`, not the retired/legacy streaming service. `text_output` already narrowly recognizes approved/rejected `draft` results. `display_output` handles both live/history output plus authorized citations, while `render_progress` handles workflow/human-review output. These are the shared new-reader/renderer seams. `NativeService.owned` validates canonical session UUID, principal, host/application and publication binding before resume/history.

**Evidence**:

- [Official custom-element documentation](https://docs.chainlit.io/api-reference/elements/custom).
- [Chainlit 2.12.0 package metadata](https://pypi.org/pypi/chainlit/2.12.0/json).
- [Pinned UI custom-element directory](https://github.com/Azure/agent-app-ui/tree/8a45595aa321d8841e7a4555d542b890beebf1b0/public/elements).

Documentation existence is not a tested guarantee for inline SVG or embedded interactions.

## 7. Configuration and Provider Parity

**Decision**: Use a shared versioned per-agent settings object through existing App Configuration publication, default empty/off, without a new public host selector or resource dependency.

**Rationale**: `native.py` and `composition.py` already share application selection. `appconfig_intent.py` and `appconfig_ownership.json` govern runtime publication. Both adapters already accept explicit named settings with label/content type, as exercised by `tests/test_app_settings_resolution.py`.

**Alternatives considered**: One global enable flag, unrelated Bicep/Terraform parameters, or runtime settings loaded from browser input. They lose per-agent control, duplicate platform behavior, or cross the trust boundary.

**Evidence**:

- `config/deployment/native.py`.
- `config/deployment/composition.py`.
- `config/deployment/appconfig_intent.py`.
- `config/deployment/appconfig_ownership.json`.
- `tests/test_app_settings_resolution.py`.
- `.github/workflows/infra-validate.yml`.

**Selected contract**: `AGENT_PRESENTATION_SETTINGS`, compact JSON in `text/plain`, label `agent-lz`, absent/empty-map default off. This is owner-edited ordinary configuration with explicit `json_object` validation, not generated `controlled` authority. Current merge/publisher protections would reject arbitrary controlled opt-in values. [configuration.md](contracts/configuration.md) defines the shared validation/metadata/reconciliation path.

Add the selected key to native `BASE_KEYS` and functional snapshots. Use the existing request-owned selected-provider pattern to read it fresh at turn start, avoiding the normal 30-second refresh throttle. Snapshot it for a workflow, but do not freeze current authorization/dynamic MCP keys. No new foundation parameter/resource is required beyond existing generic setting input. Counterpart non-impact still requires regression and live evidence.

## 8. Dependency and Validation Discipline

**Decision**: Verify isolated compatible dependencies and distinguish a narrow fixture from the actual component dependency set before choosing new pins.

**Rationale**: The researched newer Foundry hosting release `1.0.0b261106` requires Core >=1.25.0, while the baseline is Core 1.24.0. Picking latest packages independently is unsafe. Compatible direct version bounds do not prove a complete install or runtime behavior.

**Alternatives considered**: Upgrade all packages during planning, install into the shared environment, or label metadata inspection as a resolver pass. These introduce unrelated changes or false evidence.

**Evidence**:

- [Core 1.24.0 metadata](https://pypi.org/pypi/agent-framework-core/1.24.0/json).
- [Foundry hosting b261106 metadata](https://pypi.org/pypi/agent-framework-foundry-hosting/1.0.0b261106/json).
- [Foundry hosting b261030 metadata](https://pypi.org/pypi/agent-framework-foundry-hosting/1.0.0b261030/json).

Both component `pyproject.toml` files require Python >=3.12. Orchestrator `pr_pipeline.yaml` installs host-specific requirements plus tools/test prerequisites under Python 3.12 and runs `pytest -q --junitxml=.artifacts/pytest.xml`. UI `tests.yml` invokes tracked `run-unittest.py`; local runs require `QUALITY_RUN_ID`, a resolvable base commit/ref and the co-located tracked quality helper. [quickstart.md](quickstart.md) records exact commands rather than invented feature selectors.

The local proof resolved the baseline dependency set. For the user's explicitly simplified live proof, direct dependencies were reduced to Core and Foundry Hosting with pinned transitive requirements. Removing model/configuration/monitoring packages does not establish full component dependency parity. The remote build succeeded after replacing an index-bound lock in the deployment package with portable exported requirements. No vendor SDK change or infrastructure expansion was needed.

## Phase 0 Exit

The maintainer resolved the protocol choice: keep Responses. They separately authorized a minimum-cost synthetic Hosted proof without private networking and removed unchanged older-client compatibility from acceptance. That narrows the proof, not the full feature's host/UI scope.

The maintainer subsequently explicitly authorized proceeding with `/speckit-plan`. The minimum carrier uncertainty is resolved, native source/reader seams and configuration ownership are verified, and concrete product schemas/lifecycle semantics are designed. Phase 1 can complete while the unrun tests remain mandatory before enablement/full delivery. ADR-0040 remains Proposed. No shipped runtime, manifest pin, setting or product documentation behavior changed.

## 9. Public extension and selection design

**Decision**: Public function middleware captures supported successful tool results, public agent middleware preserves narrative and appends an accepted native message, and one bounded tool-free structured selection call runs only for enabled agents.

**Rationale**: The installed Core 1.24.0 documents writable `AgentContext.result` for both `AgentResponse` and `ResponseStream`, `FunctionInvocationContext.result` for supported tool result content, and public chat `response_format`. Pinned runtime already uses `agent_middleware` in `agent.py` and `function_middleware` in `knowledge.py`. These are verified extension seams, not private host overrides.

**Alternatives considered**: Change the primary agent to emit only a structured selection, add a fake selection/tool transport event, or introspect private hosting builders. A separate bounded selection call retains existing primary narrative/consent/tool behavior and adds no overhead for disabled agents. It incurs one optional model request per enabled agent. Public stream/final-result composition still requires an explicit integration test before opt-in.

Some provider-managed tools do not expose typed local results. Do not assume middleware can capture them or recover precision discarded upstream. Shared typed structural adapters must demonstrate exact source tokens/row identity, or diagnose unsupported-result fallback. A source owner may independently provide a compatible result format, but no named source integration or source-owner change is a release prerequisite.

## 10. Tool-independent eligibility and bounded operation

**Decision**: Eligibility depends on authorized typed result structure, precision and provenance, not tool name. Existing native/MCP and customer-defined tools enter the same normalization path. NL2SQL is an example, never a mandatory integration. [tool-results.md](contracts/tool-results.md) defines the boundary.

**Rationale**: The maintainer explicitly rejected a named-tool prerequisite during clarification. Current public middleware captures function outcomes rather than providing an NL2SQL-only visual API. The synthetic registry already separates field/row data from tool attribution. Structural normalization preserves that boundary without promising faithful charts from arbitrary prose or lossy values.

**Alternatives considered**: Mandatory NL2SQL acceptance, all named analytical tools as a release gate, or unrestricted model-authored JSON conversion. The first two unnecessarily couple the feature to tool choices. The third violates source fidelity. Existing tool/endpoint admission remains enforced separately.

**Decision**: Each enabled agent's additional stage has one 10-second elapsed budget, including retries, starting after primary answer/source availability. A monotonic deadline covers normalization through serialized validated contribution. Expiry seals a diagnosed timeout, preserves text/other contributions, signals cancellation, and excludes late results.

**Rationale**: The maintainer chose 10 seconds over the offered 5/30-second alternatives. A renderer-only latency target does not bound an optional model request. Awaiting cancellation before returning text could violate this budget if the client is uncooperative.

**Alternatives considered**: Unbounded optional generation, resetting the timeout for each retry, or dropping the entire multi-agent answer. They respectively violate bounded operation, exceed the agreed budget, or lose valid contributions. The runtime must race completion against an absolute deadline and supervise cancellation without reopening acceptance. The deadline is per agent occurrence, not a total workflow SLA.

**Evidence scope**: These policies are accepted clarification decisions applied to the existing verified extension seams. Deadline, cleanup, renamed/customer-tool normalization and revoked-source-history tests remain implementation evidence. No new package pin, SDK timer API, source-specific integration or deployed proof is claimed.

## Pinned source and documentation inventory

- Orchestrator [configuration/snapshot](https://github.com/Azure/agent-app-orchestrator/blob/666d39862590cfb165097ee55737a1ef66fd2afc/src/native/config.py), [public agent middleware](https://github.com/Azure/agent-app-orchestrator/blob/666d39862590cfb165097ee55737a1ef66fd2afc/src/native/agent.py), [tool outcome middleware](https://github.com/Azure/agent-app-orchestrator/blob/666d39862590cfb165097ee55737a1ef66fd2afc/src/native/knowledge.py), [business contracts](https://github.com/Azure/agent-app-orchestrator/blob/666d39862590cfb165097ee55737a1ef66fd2afc/src/native/contracts.py), [dependencies](https://github.com/Azure/agent-app-orchestrator/blob/666d39862590cfb165097ee55737a1ef66fd2afc/pyproject.toml), [PR checks](https://github.com/Azure/agent-app-orchestrator/blob/666d39862590cfb165097ee55737a1ef66fd2afc/.github/workflows/pr_pipeline.yaml).
- UI [native Chainlit](https://github.com/Azure/agent-app-ui/blob/8a45595aa321d8841e7a4555d542b890beebf1b0/src/gpt_rag_ui/api/native_chat.py), [owner/service boundary](https://github.com/Azure/agent-app-ui/blob/8a45595aa321d8841e7a4555d542b890beebf1b0/src/gpt_rag_ui/services/native.py), [Durable client](https://github.com/Azure/agent-app-ui/blob/8a45595aa321d8841e7a4555d542b890beebf1b0/src/gpt_rag_ui/clients/native_durable.py), [test runner](https://github.com/Azure/agent-app-ui/blob/8a45595aa321d8841e7a4555d542b890beebf1b0/.github/scripts/run-unittest.py), [quality helper](https://github.com/Azure/agent-app-ui/blob/8a45595aa321d8841e7a4555d542b890beebf1b0/.github/scripts/check-quality.py).
- Current central [navigation](https://github.com/Azure/AI-Landing-Zones/blob/main/mkdocs.yml) registers `application.md`, `hosted-agents.md`, `agent-strategies.md`, `workflows.md`, `conversations.md`, `embed-chat.md`, `application-settings.md`, `configuration.md`, `application-api.md`, `application-testing.md`, `operations.md`, `application-monitoring.md`, `agentops.md`, `publish-to-teams.md` and `connect-copilot-studio.md` under `agent-landing-zone`. Search/update their actual content at delivery, not draft-publication time.
