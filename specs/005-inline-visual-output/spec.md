# Feature Specification: Native Inline Visual Output

**Feature Branch**: `feature/inline-visual-output`

**Created**: 2026-11-07

**Status**: Draft

**Input**: User description: "https://github.com/Azure/agent-landing-zone/issues/691"

**Source Context**: Issue #691 and its October 2 review comment. This specification includes the proposed clickable table rows, deterministic status indicators, combined multi-agent presentations, and per-agent guidance. It describes desired behavior, not capabilities already shipped.

## Clarifications

### Session 2026-11-07

- Q: If a user loses access to the original source but remains authorized to open the conversation, should saved values remain visible? → A: Apply the existing text-history rules to originally authorized snapshots, without introducing independent source-permission revalidation for visuals. New requests continue to enforce current source permissions.
- Q: How long may the additional visual-generation stage take per agent before abandoning it and preserving text? → A: At most 10 seconds per enabled agent, including retries. On timeout, retain authorized text and other valid contributions, record the reason, and ignore late visual results.
- Q: Which data integration must work for the first visual-output release to be ready? → A: Tool-agnostic authorized structured results. No named tool, including NL2SQL, is a prerequisite. Any user-selected tool may supply eligible data, and unsupported or lossy results retain the authorized text fallback.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read Trustworthy Analytical Answers Inline (Priority: P1)

As an analyst working in audit, finance, or operations, I want an analytical answer to include metric cards, a table, or a chart inside the conversation so that I can identify trends and exceptions without exporting data or using a separate charting bot.

**Why this priority**: Inline visual output is the central benefit. It must be as trustworthy as the underlying authorized data.

**Independent Test**: Ask an enabled agent for an analysis of a known, authorized dataset. Compare every displayed value and indicator with the source data and approved rules, without requiring follow-up interactions or conversation reopening.

**Acceptance Scenarios**:

1. **Given** an enabled agent and a tool result containing monthly revenue, **When** the user requests a revenue comparison, **Then** the answer contains an inline supported chart with labeled categories, values, and a readable text alternative, and every plotted value matches the tool result.
2. **Given** tool results containing metrics, units, and status fields, **When** the agent produces metric cards, **Then** their labels, values, units, trends, and status indicators reflect those results without model-invented values.
3. **Given** an approved rule that marks values below a threshold as critical, **When** a result includes values below, equal to, and above that threshold, **Then** card statuses and table highlights match the rule exactly, including its boundary behavior.
4. **Given** a tool result without status or trend information and no applicable approved rule, **When** a presentation is produced, **Then** it omits those indicators instead of inferring them from the model's judgment.
5. **Given** no usable tool result or an unsupported chart request, **When** the agent answers, **Then** the user receives a text answer without fabricated visual data.
6. **Given** a user-selected tool that returns identifiable, authorized, typed data with preserved precision, **When** an enabled agent produces a presentation, **Then** eligibility depends on the result's data and provenance, not the tool's name or a fixed tool allowlist.

---

### User Story 2 - Enable Visuals Without Disrupting Existing Channels (Priority: P1)

As an agent owner, I want to opt individual analytical agents into visual output while other agents retain their text experience and supported new clients receive a readable answer.

**Why this priority**: Supported new text-only clients need readable answers without requiring native visuals in every channel. Unchanged older client binaries are outside acceptance.

**Independent Test**: Submit equivalent requests to enabled and disabled agents and to supported new clients with and without visual support. Verify that only enabled agents produce visual presentations and that those clients retain a readable answer.

**Acceptance Scenarios**:

1. **Given** an existing agent with no visual-output setting, **When** the user asks an analytical question, **Then** the agent keeps its existing text and citation behavior and does not deliver visual blocks.
2. **Given** two agents with different opt-in settings, **When** each handles an equivalent analytical request, **Then** enabling one does not enable the other.
3. **Given** an enabled agent, **When** its answer is viewed through a supported new text-only client for Microsoft Teams, Microsoft 365 Copilot, or a customer-owned frontend, **Then** the client receives a readable markdown fallback without needing to render visual blocks.
4. **Given** an agent owner disables visual output, **When** a new turn starts, **Then** that turn contains no new visual blocks, while authorized previously saved presentations remain available in history.
5. **Given** the operator uses either supported infrastructure provider, **When** the operator configures the same agent opt-in choices, **Then** the effective defaults and enabled-agent behavior are equivalent.

---

### User Story 3 - Explore Tables and Ask Contextual Follow-Ups (Priority: P2)

As an analyst, I want to sort, filter, and copy tabular results, inspect chart values, and ask for details about a row without manually reconstructing a prompt.

**Why this priority**: These interactions make the displayed data actionable rather than merely decorative.

**Independent Test**: Open a response containing a known table, chart, and follow-up suggestions. Exercise each interaction and verify the selected data and resulting message.

**Acceptance Scenarios**:

1. **Given** a table with numeric and text columns, **When** the user sorts or filters it, **Then** numeric values sort numerically, text values sort consistently, and filtering changes only the visible rows, not the underlying answer.
2. **Given** a sorted and filtered table, **When** the user copies it, **Then** the copied content includes column headings and only the visible rows in their current order.
3. **Given** an interactive chart, **When** the user inspects a plotted value, **Then** its tooltip identifies the category, series when applicable, value, and unit when supplied.
4. **Given** an optional row-details action and a table whose visible order has changed, **When** the user activates a row, **Then** exactly one follow-up message referring to that row's authorized identifier is sent through the normal conversation flow.
5. **Given** a table without a row-details action, **When** the user reads or selects a row, **Then** no follow-up message is sent.
6. **Given** a follow-up suggestion, **When** the user activates it, **Then** exactly one message containing the displayed prompt is sent under the user's current permissions.

---

### User Story 4 - Reopen Answers in Any Supported Web View (Priority: P2)

As a returning user, I want saved visual answers to remain readable when I reopen a conversation, in both the standalone web app and the embedded Copilot widget.

**Why this priority**: Analytical answers are useful beyond the live turn and must not disappear or change meaning after reopening.

**Independent Test**: Save a conversation containing each supported block and reopen it in both web views and both themes, without re-running the original tools.

**Acceptance Scenarios**:

1. **Given** a saved visual answer, **When** an authorized user reopens the conversation, **Then** its values, titles, citations, agent attribution, and block order match the saved answer without re-querying the source.
2. **Given** a supported presentation, **When** it is viewed in light and dark themes in the standalone app and embedded widget, **Then** text, status indicators, chart labels, and controls remain readable and usable.
3. **Given** a saved conversation predating visual output, **When** it is reopened, **Then** its text and citations remain readable without requiring a presentation.
4. **Given** a saved answer contains an unknown block type, **When** it is reopened in a supported new visual client, **Then** the client skips that block, displays recognized blocks, and preserves the text fallback.
5. **Given** the user no longer has permission to view the conversation, **When** the user attempts to reopen it, **Then** neither its text nor its saved visuals are exposed.
6. **Given** the user loses access to an original source but retains access to the conversation, **When** the user reopens an originally authorized answer, **Then** text and visuals follow the existing text-history access rules without new source-permission revalidation, and any new follow-up uses current source permissions.

---

### User Story 5 - Read a Coherent Multi-Agent Answer (Priority: P2)

As a user of a multi-agent workflow, I want visuals from specialized agents to form one coherent turn, with clear ownership and predictable ordering.

**Why this priority**: Multiple visual producers must not mix datasets, override another agent's settings, or produce an unstable answer.

**Independent Test**: Run a turn with two enabled agents using different datasets and guidance, plus one disabled agent. Repeat with different completion timing and verify contribution attribution, data isolation, and ordering.

**Acceptance Scenarios**:

1. **Given** enabled specialized agents with different visual guidance, **When** they contribute to one turn, **Then** each selects from supported block types using its own guidance and its blocks retain their agent and source attribution.
2. **Given** the same workflow contribution order but different agent completion timing, **When** the combined presentation is displayed, **Then** contributions follow workflow order and each contribution preserves its own block order.
3. **Given** enabled and disabled agents in one workflow, **When** the turn completes, **Then** only enabled agents contribute visual blocks and all agents can still contribute their normal text answers.
4. **Given** two agents refer to different results with similarly named fields, **When** their visuals are assembled, **Then** each block uses only its explicitly associated authorized source.
5. **Given** one contribution is invalid, **When** the turn completes, **Then** valid contributions remain visible and the text answer is not lost.

---

### User Story 6 - Receive Safe Answers When Visual Output Fails (Priority: P1)

As a user and operator, I want unsafe, unsupported, or oversized visual content to be rejected without losing a usable answer or hiding the reason from operations.

**Why this priority**: Tool and model output are untrusted. Visual rendering must not add execution paths or weaken existing authorization.

**Independent Test**: Supply malformed, oversized, unauthorized, and executable-content examples. Verify rejection, a readable text answer, and diagnostic evidence without rendering unsafe content.

**Acceptance Scenarios**:

1. **Given** a block contains executable content or an actionable external address, **When** the answer is processed, **Then** that block is rejected, no content is executed or fetched, and an authorized text answer is still delivered.
2. **Given** a presentation reaches a published limit, **When** it is processed, **Then** it is accepted if otherwise valid. **Given** it exceeds that limit, **When** it is processed, **Then** it is rejected without silent truncation.
3. **Given** a malformed known block, **When** the answer is processed, **Then** that block is rejected with a diagnosable reason and other valid blocks remain available.
4. **Given** a visual fails to display, **When** the user reads the response, **Then** the user can still access its readable text alternative.
5. **Given** a source includes rows or documents the user cannot access, **When** the presentation and fallback are assembled, **Then** neither exposes the unauthorized values, identifiers, citations, or derived indicators.
6. **Given** an enabled agent's additional visual-generation stage has not completed within 10 seconds, **When** its time budget expires, **Then** its visual stage times out with a diagnostic, authorized text and other valid contributions remain available, and late results cannot add blocks to the answer.

### Edge Cases

- Empty results produce an explicit no-data answer, not a zero-valued metric or an empty chart suggesting a measurement.
- A tool name does not determine visual eligibility. Unstructured, lossy, or otherwise unsupported results from any tool retain the authorized text fallback rather than creating fabricated visual data.
- Missing source references, missing columns, incompatible column types, or ambiguous rule inputs invalidate the affected block and preserve the text answer.
- Missing values remain distinguishable from zero. Missing chart points are represented as gaps rather than fabricated values.
- Large, negative, fractional, and zero values preserve their meaning. Formatting may round displayed values only when the precision is stated and copied table data preserves the source precision.
- Different units must not be combined into a misleading series or comparison. Unsupported combinations fall back to text.
- Long labels and wide tables remain readable without obscuring neighboring messages or controls.
- Status meaning is conveyed by text or icons as well as color. Reading and follow-up controls must be usable with a keyboard.
- Rule boundaries, missing operands, and overlapping rules must have a single documented outcome. Ambiguous rules cannot supply indicators.
- A row action without its required identifier is unavailable for that row. Row data is treated as data, not as instructions or an executable expression.
- An interrupted turn must not persist an incomplete block as valid. Already accepted blocks and available text retain their association with that turn.
- A combined answer exceeding the turn-level limit is rejected as a presentation, not silently reduced according to agent completion timing.
- Unknown future block types are skipped by clients without suppressing recognized blocks or the fallback. Unsupported contract versions use the fallback rather than guessing their meaning.
- Deleted conversations follow existing deletion behavior for their saved visual content as well as their text.
- Source-access changes do not introduce a separate visual-history permission check. Originally authorized saved values follow existing text-history access, retention, and deletion rules. New requests and follow-ups enforce current source permissions.
- Visual generation has a 10-second elapsed-time budget per enabled agent, including retries, starting when its authorized source results and primary answer are available. A timeout rejects only that agent's pending visual contribution, preserves text and other valid contributions, and ignores late results.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Visual output MUST be explicitly enabled per agent and disabled by default. It MUST NOT replace the default text experience for unconfigured agents.
- **FR-002**: An enabled agent MUST be able to choose supported visual blocks according to the user request and its per-agent presentation guidance. Guidance MUST NOT override source integrity, authorization, supported types, or size limits.
- **FR-003**: Version 1 MUST support metric cards, typed tables, bar charts, grouped bar charts, line charts, and follow-up suggestions. Each block MUST allow an optional title and existing authorized citation references.
- **FR-004**: Visual values MUST come directly from identified, authorized tool results. Eligibility MUST depend on usable typed data, preserved precision, and verifiable provenance, not a fixed tool-name allowlist or dependency on a named integration. Any user-selected tool MAY supply eligible results, including customer-defined tools. The model MAY select a presentation and source fields but MUST NOT supply or reconstruct the underlying numbers. Unsupported, lossy, or unavailable data MUST retain an authorized text fallback without invented measurements.
- **FR-005**: Status, trend, and row highlights MUST originate from source fields or deterministic, agent-owner-approved rules applied to those fields. Supported statuses MUST be `ok`, `warning`, and `critical`. Indicators without valid provenance MUST be omitted.
- **FR-006**: Cards MUST support labels, values, units, trends, and status when available. Tables MUST expose column types, rows, and status indicators. Charts MUST expose category labels, series labels where applicable, and value tooltips.
- **FR-007**: Tables MUST support sorting, filtering, and copying. Copying MUST preserve source precision and include headings and visible rows in the displayed order.
- **FR-008**: Tables MAY carry an optional row-details action. Activating it MUST send one normal follow-up message bound to the selected row's authorized identifier, independent of sorting and filtering.
- **FR-009**: Follow-up suggestion chips MUST send exactly one normal user message per activation. Suggestions and row actions MUST NOT execute a tool directly or elevate permissions.
- **FR-010**: Every visual response MUST include a readable markdown fallback conveying the same key values, units, conclusions, and citations. Supported new web clients MUST expose that fallback when visual rendering fails. Unchanged older clients are outside the delivery acceptance scope.
- **FR-011**: Supported blocks MUST render inline in both the standalone Agent App Web UI and embedded Copilot widget, in light and dark themes. They MUST preserve keyboard access, legible labels, and non-color-only status meaning.
- **FR-012**: Accepted presentations MUST be saved with their conversation turn and restored without re-running the source query. Saved values, citations, contribution ownership, and block order MUST remain stable. Existing text-history access, retention, and deletion rules MUST also apply to originally authorized presentation snapshots. Visual history MUST NOT introduce independent source-permission revalidation. New requests and follow-ups MUST enforce current source permissions.
- **FR-013**: A multi-agent turn MUST combine enabled-agent contributions into one logical presentation. It MUST preserve contribution ownership and source binding and order contributions by workflow order, then by the producing agent's block order, not completion timing.
- **FR-014**: Invalid contributions MUST NOT prevent valid contributions or the authorized text answer from being delivered. A turn-level limit violation MUST reject the combined presentation rather than silently select contributions.
- **FR-015**: The published version 1 presentation contract MUST define supported blocks, required and optional content, source attribution, indicator provenance, limits, and compatibility behavior. Its versioned JSON Schema and valid and invalid examples MUST be published for customer-owned frontends.
- **FR-016**: Before delivery, presentations MUST be checked for supported types, required content, source validity, indicator rules, size limits, and prohibited executable content. Invalid known blocks MUST be rejected and their reasons recorded through the configured diagnostic path without exposing sensitive source data.
  Each enabled agent's additional visual-generation stage MUST complete or time out within 10 seconds elapsed time after its authorized source results and primary answer are available, including retries. A timeout MUST preserve authorized text and other valid contributions, record a safe diagnostic reason, and prevent late results from adding visual blocks to that answer.
- **FR-017**: Version 1 MUST accept at most 10 blocks per turn, 500 rows per table, 8 series per chart, 1,000 non-null plotted measurements across all series per chart, and 256 KiB (262,144 UTF-8 bytes) of complete presentation content per turn. The byte limit includes the markdown fallback and provenance, but excludes transport framing. Content exactly at each limit MUST be accepted when otherwise valid. Content exceeding a limit MUST be rejected without silent truncation.
- **FR-018**: Visual content MUST NOT introduce active HTML, scripts, executable expressions, actionable URLs, remote content loading, third-party script delivery, or relaxed browser security controls. Existing approved citation handling MUST remain separate from visual content.
- **FR-019**: Visual content, text fallbacks, copied values, saved history, and follow-up actions MUST preserve existing authentication, document-level and row-level authorization, and user-delegated access controls.
- **FR-020**: Supported new clients MUST skip unknown block types while retaining known blocks and the fallback. They MUST use the fallback when they cannot understand the contract version. Existing text-only conversations MUST remain readable in those new clients without migration. Backward compatibility with older client binaries is not required.
- **FR-021**: Agent opt-in configuration MUST have equivalent effective defaults and behavior across both supported infrastructure providers and supported lifecycle paths. Any necessary provider difference MUST be explicitly documented and approved before delivery.
- **FR-022**: Operator and customer documentation MUST cover enabling and disabling the feature, per-agent guidance, supported channels and interactions, limits, source and indicator provenance, the contract reference, and a complete sample. It MUST describe shipped behavior rather than imply this draft is already available.

### Key Entities *(include if feature involves data)*

- **Agent Presentation Settings**: An agent's opt-in choice and presentation guidance. These apply only to that agent and cannot weaken shared safety rules.
- **Authorized Tool Result**: An identified result already restricted to the user's accessible data, with typed fields, values, units, and optional source-provided indicators.
- **Presentation Rule**: An approved, deterministic mapping from result fields to status, trend, or highlight, including explicit boundaries and missing-value behavior.
- **Turn Presentation**: The versioned visual content associated with one conversation turn, its ordered contributions, and its readable text fallback.
- **Agent Contribution**: An identified agent's ordered blocks and their source associations within a turn presentation.
- **Visual Block**: A metric-card group, table, chart, or suggestion group, with optional title and authorized citations and block-specific content.
- **Follow-Up Action**: A displayed suggestion or optional row-details action that creates a normal user message without bypassing authorization.
- **Saved Conversation Turn**: The existing history record extended to preserve accepted presentation content under the same access and lifecycle rules.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a controlled set covering all supported blocks and three analytical domains, 100% of visual values match their authorized source, and 100% of displayed statuses, trends, and highlights match source fields or approved rules. Eligibility checks MUST additionally show that equivalent eligible results from differently named tools, including a customer-defined tool, produce equivalent supported visuals without tool-name-specific enablement, and that unsupported results retain text fallback. No specific tool integration is a release prerequisite.
- **SC-002**: All supported blocks and interactions pass the same acceptance scenarios in all four combinations of standalone or embedded view and light or dark theme, including keyboard operation and readable status meaning without color.
- **SC-003**: In 100% of disabled-agent, supported new text-only-client, unknown-block, malformed-block, oversized-content, and visual-generation-timeout scenarios, the user retains a readable authorized text answer without a broken conversation. Unchanged older client binaries are not acceptance targets.
- **SC-004**: Reopening 20 distinct controlled local saved-history cases spanning single-agent, multi-agent, interrupted, and legacy turns through fresh SDK/client interfaces restores 100% of accepted visual values, attribution, citations, and ordering without re-querying data. Real Azure conversations are not required acceptance proof.
- **SC-005**: Across 20 repeated multi-agent runs with varied completion timing, contribution ordering and source binding remain identical for equivalent workflow contributions, with zero blocks contributed by disabled agents.
- **SC-006**: All boundary checks at and immediately above the published limits produce the specified acceptance or rejection outcome, with no silent truncation or invented data.
- **SC-007**: Once complete answer content is available, supported presentations become readable within 1 second in at least 95% of 30 representative turns on the documented reference device, including examples at the allowed content limits. Model and source-query waiting time are excluded from this rendering target. Separately, each enabled agent's additional visual-generation stage MUST complete or time out within 10 seconds elapsed time, including retries. Deadline tests MUST verify timely text delivery, preservation of other valid contributions, timeout diagnostics, and rejection of late visual results.
- **SC-008**: Controlled browser checks expose readable trend and critical-row meaning, locate the expected row using sort/filter, and send exactly one contextual follow-up with its source business ID through the ordinary message path.
- **SC-009**: All adversarial content and unauthorized-data acceptance cases result in zero executable-content execution, zero visual-triggered external requests, and zero unauthorized disclosure. Every rejected presentation case has a diagnosable reason.
- **SC-010**: Automated local checks for both infrastructure providers and hook implementations exercise the documented declaration: empty/default-off, enable one agent, disable/remove it and repeated publication without changing other agents or authentication.

## Assumptions

### Maintainer-approved acceptance scope amendment — 2026-11-08

The maintainer explicitly removed real-Azure validation from implementation
completion, rather than postponing it. Acceptance uses local controlled public
SDK/client/history boundaries and Playwright, including Hosted/Durable agent
and workflow shapes, owner/action denial and lifecycle semantics. SC-004 still
requires 20 distinct controlled saved-history cases; SC-005 still requires
20 timing-varied runs. SC-007 requires 30 render measurements; SC-008 and
SC-010 use automated browser and local provider/publication/hook checks.
This is the maintainer-approved technical acceptance scope.

Azure runtime persistence, authorization enforcement and deployed provider
parity remain **unverified residual risks**, not deferred mandatory gates.
No behavioral/security requirement, default, schema, pin or repository-wide
constitution/release policy is waived. Compilation/mocks do not prove deployment.
No Azure operation, provisioning or issue publication is authorized.

- The October 2 review comment is treated as an in-scope refinement, including optional clickable rows and the recommendation to combine model selection with per-agent guidance.
- Existing tool integrations already provide authorized results. This feature consumes them and does not add a new data connector or change source authorization.
- Visual output is tool-agnostic. Users may choose existing or customer-defined tools. Results must retain the types, precision, identity, and authorization needed for faithful presentation, but no named tool is mandatory.
- Indicators may be derived from source data through approved deterministic rules. Such derivations are distinct from allowing the model to invent measurements or judge status.
- Workflow contribution order is the default ordering policy. Planning must define how existing workflows expose a stable order without changing this user-visible requirement.
- The limits and rendering targets in FR-017 and SC-007 require a reproducible reference device, representative datasets and measured evidence.
- Table filtering searches displayed cell values. Column-specific analytics, editable data, dashboards, exports beyond copying, and independent visual refresh are not included.
- Previously saved authorized presentations remain readable after an agent is disabled. Disabling affects new turns and does not itself delete history.
- Version 1 excludes relationship graphs, pie charts, scatter plots, heatmaps, customer-specific visual templates, model-authored executable visuals, and native visual rendering in Microsoft Teams or Microsoft 365 Copilot.

### Dependencies and Delivery Boundaries

- `Azure/agent-app-orchestrator` owns runtime presentation assembly, validation, source binding, fallback delivery, multi-agent combination, and its conversation-history integration.
- `Azure/agent-app-ui` owns web rendering, interactions, and visual history restoration. Runtime application behavior remains in those component repositories rather than being duplicated here.
- `Azure/agent-landing-zone` owns shared contract governance, deployment opt-in configuration, infrastructure parity, and the manifest that binds the validated component combination.
- Existing native and MCP tools may supply eligible results. Agent App MCP and its NL2SQL toolset are examples, not mandatory dependencies. No ingestion or connector changes are assumed.
- Product documentation must be delivered through the central AI Landing Zones documentation source. This specification is a development artifact, not a replacement for shipped product documentation.
- Before implementation, planning must record the architectural decision for the new cross-component presentation and persistence contract, exact repository ownership, trust boundaries, migration and recovery behavior, compatible component revisions, integration order, rollback order, and required evidence.
- The coordinated implementation must assess both infrastructure providers and both lifecycle-hook implementations. It must distinguish deployed evidence from compilation or mocked checks and identify any unverified scenarios.
- This invocation produces a specification and quality checklist only. It does not publish a schema, change runtime behavior, update component pins, or claim implementation acceptance criteria have passed.
