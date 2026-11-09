# ADR-0040: Keep inline presentation within native protocol and state boundaries

**Status:** Accepted for local implementation; Azure live proof removed from completion by maintainer amendment, production/release not authorized<br>
**Date:** 2026-11-07<br>
**Owners:** Agent Landing Zone maintainers and runtime component owners

## Context

Issue #691 requests opt-in inline analytical cards, tables, charts, and suggestions. Review adds optional row actions, deterministic source-derived indicators, and multi-agent output ordering. The feature must not replace text defaults or weaken tool/data authorization.

The issue's transport/history assumptions predate ADR-0034. Current native execution uses official Hosted Responses and durable Container Apps integrations. Foundry/DTS own state. UI metadata is not a second transcript store. A minimum local/live proof established deterministic application JSON in standard `output_text` as a carrier with identical native response/conversation retrieval. Product authorization/lifecycle, Durable, and Chainlit feasibility remain unverified.

Affected repositories are `Azure/agent-landing-zone`, `Azure/agent-app-orchestrator`, `Azure/agent-app-ui`, and central documentation `Azure/AI-Landing-Zones`. Existing native/MCP and customer-defined tools may supply eligible results. MCP/NL2SQL is an example, not a required integration or code change. Ingestion is not an intended consumer.

Prioritized characteristics:

1. Fidelity: every measurement and indicator traces to authorized tool data or an approved deterministic rule.
2. Protocol continuity: keep Responses, default-off text behavior, and readable fallback in new supported clients. The maintainer removed backward compatibility with unchanged older clients from acceptance on 2026-11-07.
3. Confidentiality: negative owner/read/action tests expose neither text nor presentation and never persist invocation credentials.
4. Native persistence: reopened visuals preserve original values without re-querying or a duplicate transcript/checkpoint database.
5. Bounded operation: current browser security/network isolation remain intact, content limits reject oversized output observably, and each enabled agent's additional generation completes or times out within 10 seconds including retries.

## Alternatives considered

### Option A: Supported native carrier and native state, with an evidence gate

- Benefits: preserves Responses compatibility, host ownership, existing identity/lifecycle boundaries, and no new storage or network dependency.
- Costs and risks: Minimum Hosted carrier/history passed. Product middleware-finalization, owner/lifecycle, Durable and renderer acceptance remains unrun.
- Security and identity: hydrate inside the authorized tool invocation, use existing text-history admission for saved snapshots, and current source permissions for new queries/follow-ups. No new source ACL lookup on visual restoration.
- Operational consequences: use existing App Configuration and host storage, record exact package compatibility and diagnostic reason codes.
- Component compatibility: coordinated readers/producers/configuration, compatible text fallback, and preserved old conversations.
- Reversibility: disable new production first and retain saved-turn readers. No state conversion or deletion.

### Option B: App-owned side-channel presentation storage/API

- Benefits: application-controlled JSON transport independent of Responses extension points.
- Costs and risks: duplicates content and lifecycle ownership, adds consistency/deletion/retention complexity, potentially new resource/RBAC/cost.
- Security and identity: a new owner-gated content API/store requires separate negative tests and least-privilege grants.
- Operational consequences: introduces synchronization/recovery work and another authoritative content surface.
- Component compatibility: new UI/API/state contract, not a simple optional event.
- Reversibility: needs explicit data lifecycle and rollback for side-channel records.

### Option C: Switch Hosted to Invocations for custom output

- Benefits: a different host surface may expose application-controlled output.
- Costs and risks: loses the current Responses wire choice and still requires a separate continuity/persistence proof.
- Security and identity: re-prove trusted platform invocation, owner partitioning, history/actions, and delegation.
- Operational consequences: changes client and publication contracts rather than adding only an optional presentation.
- Component compatibility: coordinated transport change, no assertion that old clients remain untouched.
- Reversibility: retain separate publications/state, no assumed native-state portability.

### Do not change

- Benefits: no new contract, dependency, migration, or output-handling risk.
- Costs and risks: analytical users remain limited to markdown or external charting workarounds, failing the feature outcome.

## Decision

Adopt Option A for local implementation with a deterministic versioned envelope
in native assistant text and an optional typed workflow review/result field.
The 2026-11-07 T001 approval remains valid. On 2026-11-08 the maintainer explicitly
removed actual-Azure validation from implementation completion, not postponed
it. T054-T056 are retired, never marked executed. T057 proves behavior through
controlled public SDK/history/client interfaces and Playwright, preserving
20 histories and 20 timing-varied runs. T058 retains 30 render measurements,
automated browser usability and both local provider/publication/hook checks.
Azure persistence, ACL enforcement and deployed parity are unverified residual
risks, not future mandatory gates. No behavioral/security/global parity rule,
production enablement, Azure operation or release authorization is changed.

Do not invent a custom Responses SSE event, misuse refusal/citation/tool messages, patch SDK internals, add a generalized state SDK, switch to Invocations, or store transcripts in UI Cosmos. Absence of a supported carrier must be reported rather than silently worked around.

The presentation contract is versioned and separate from untrusted model selection. Selection supplies source handles and field mappings, never measurements. Runtime validators hydrate authorized data and accept only approved block/chart types, source/rule indicators, and bounded content.

Use existing public function/agent middleware and public response/stream finalization. Enabled agents add one bounded tool-free structured selection call after ordinary tool/model work. Disabled agents add no selection call. Shared structural result adapters preserve exact typed values and captured row associations without tool-name-specific enablement, model reconstruction or a named-tool dependency. Existing tool/endpoint admission remains authoritative.

The additional stage has one absolute monotonic 10-second budget per enabled agent occurrence, starting after authorized source/primary-answer availability and including normalization, selection, hydration, validation, serialization and retries. Expiry seals timeout, retains text and other valid contributions, signals cancellation, and rejects late mutation. Do not delay text awaiting uncooperative cancellation. This is not a total workflow SLA or a new native replay/clock API guarantee.

Saved originally authorized values follow existing text-history access, retention and deletion rules without independent source-permission revalidation. Existing citation handling remains intact. New queries and follow-ups enforce current permissions. The maintainer explicitly selected this policy during clarification.

The selected key is `AGENT_PRESENTATION_SETTINGS`, typed owner-edited `ordinary` configuration containing JSON as `text/plain` under `agent-lz`, through existing generic settings input. Generated `controlled` authority is the wrong ownership category. Snapshot at each turn/workflow, preserve live authorization, and reconcile disablement on both provider paths.

Draft schemas, exact source bindings, disjoint numeric indicator cases, full-envelope byte accounting, strict producer/safe-reader behavior and native result mapping are defined in [the Phase 1 contracts](../../specs/005-inline-visual-output/contracts/README.md). Draft promotion and compatible consumer changes are coordinated implementation work.

Use explicit stable native workflow contribution ordinals rather than completion timing. This does not add a workflow scheduler or pretend both host protocols are identical.

## Consequences

### Positive

- Existing deployment, authentication, host persistence, and private-network boundaries remain authoritative.
- No new chart/CDN bundle, content database, secret, or broad role grant is intended.
- Compatible text output remains independently usable.
- Source integrity and deterministic indicators have a testable enforcement boundary outside model instructions.

### Negative or accepted

- Local delivery requires public finalization, controlled authorization/lifecycle,
  Durable/history and UI evidence. Real-Azure proof is not a completion gate;
  deployment enforcement/persistence remain unverified residual risks.
- Enabled agents incur one bounded extra selection-model call within the 10-second stage budget. Unsupported or lossy results use diagnosed authorized-text fallback; source owners may optionally expose compatible types without becoming release prerequisites.
- Hosts retain distinct client/state APIs and compatible-package constraints.
- Saved presentations contain authorized data and must obey native access/retention/deletion rules. A reference ID alone is not authorization.
- Package metadata and source inspection are not a live Hosted persistence or authorization result.

## Adoption and migration

The [bounded feasibility investigation](../../specs/005-inline-visual-output/feasibility.md)
is historical evidence, not an instruction to repeat its Azure publication.
The current acceptance guide is local-only by maintainer amendment.

The minimum proof used official `Agent`/`BaseChatClient` with `ResponsesHostServer(..., history_source="agent_server")`, Core 1.24.0 and Foundry Hosting 1.0.0b261030. Streaming, fresh-client agent-scoped response retrieval, and conversation history preserved the same table/chart values. The local source-disabled restoration check passed. No model, external tool, new transcript store, or private network was involved. The Hosted compute session was stopped after reads. This does not prove product authorization, durable parity, rendered UI, or infrastructure provider parity.

The Phase 1 schemas/configuration are now drafted. Review this proposed ADR, promote shared contracts, implement accepting readers and matched optional review/result fields with production disabled, then add both native producers and typed settings publication. Pass the [acceptance guide](../../specs/005-inline-visual-output/quickstart.md) on the exact compatible component combination before opt-in. Update the manifest only in a separately authorized release with the actually validated combination.

Rollback disables new visual production first and retains readers plus compatible business-result models for saved turns. Do not roll back to binaries unable to read stored envelopes/result fields. Restore only compatible configuration/images. Never migrate, convert or delete native state automatically. Graph/protocol incompatibility follows ADR-0034's isolated publication/task-hub policy.

No resource creation, deployment, release, or production publication is authorized by this ADR.

## Compliance verification

- Public streaming and completed native results contain the same accepted message. Hosted/Durable fresh histories restore identical accepted values with zero source queries or duplicate content storage.
- Wrong-owner/arbitrary-ID read and action tests fail closed. Credentials and invocation identity never enter presentation state/logs.
- Differently named native/MCP/customer-defined tools with equivalent typed data use the same structural normalization/hydration path and yield equivalent supported values/shapes with correct attribution. No NL2SQL or named-tool acceptance prerequisite exists.
- Source revocation with retained conversation access preserves existing text-history snapshot rules and introduces no new visual-history source lookup. New follow-ups use current permissions; conversation access revocation exposes neither text nor visuals.
- Deadline tests cover retries, completion before/at/after the 10-second deadline, slow processing and uncooperative cancellation. Text/other valid contributions remain available, timeout is diagnosed, and late output cannot mutate accepted native state.
- New supported clients expose text fallback and citations. Unknown blocks and unsupported versions follow explicit fallback rules. Unchanged older clients are not an acceptance gate.
- Exact-boundary and above-limit tests cover 10 blocks, 500 table rows, 8 series, 1,000 non-null plotted points and 262,144 compact UTF-8 envelope bytes without silent truncation.
- Twenty timing-varied local multi-agent runs and twenty distinct controlled
  reopened SDK/history cases preserve ownership/order with zero disabled contributions.
- UI smoke covers both themes/views, local SVG, normal follow-up messages, no external fetch/CSP change, and precision-preserving copy.
- Provider/configuration/hook regression checks establish counterpart changes or concrete non-impact. Mocks/compilation are not deployed parity.
- At least 95% of 30 complete-content renders are readable within 1 second.
  Automated browser checks cover trend/critical-row/contextual-follow-up
  usability; both local provider/publication/hook implementations cover
  documented one-agent enable/disable without changing others or authentication.

## Documentation impact

Review current `Azure/AI-Landing-Zones` main for configuration, native architecture, analytical tools/agents/workflows, conversation history, and embedded UI. Publish enablement, supported channels, contract/sample, limits, source/rule provenance, and recovery only when shipped. Register a new page if required.

Current-main navigation inventory is in [research.md](../../specs/005-inline-visual-output/research.md). Actual page-content searches and coordinated shipped updates remain delivery work. Explain tool-independent eligibility, typed-result limitations, the fixed deadline and unchanged historical snapshot policy when shipped. Do not use the legacy docs branch, duplicate product docs in component READMEs, or present this draft as current behavior.

## Review trigger

Review before implementation approval, within one working day of a blocked public finalization/Durable integration investigation, or immediately if supported APIs, owner/deletion checks or source precision cannot meet acceptance. A failed gate requests a human boundary decision, not a workaround. Revisit on native SDK/state schema changes, new host capabilities or proposed storage/protocol expansion.
