# Data Model: Native Inline Visual Output

**Status**: Phase 1 design for implementation, not a shipped model.

## Ownership and persistence

The orchestrator owns selection, invocation-scoped source capture, hydration, validation, and aggregation. The UI owns projections and interaction state. The umbrella owns the shared contracts and opt-in publication.

Foundry and Durable Task Scheduler retain the accepted envelope in native assistant output. A native response/message or durable result associates it with its existing turn. Do not add conversation IDs, user identity, bearer tokens, or self-authorizing source handles to the envelope. Do not add a Cosmos transcript, separate presentation API/store, or cached authoritative tool results.

The final schemas are proposed under [contracts](contracts/README.md). Promotion to the umbrella's published `contracts/` and matched consumer fixtures happens during coordinated implementation.

## Entities

| Entity | Fields and relationships | Lifetime |
| --- | --- | --- |
| Agent presentation settings | `schemaVersion`, map of stable native agent IDs to `enabled`, optional plain-text `guidance`, and approved rules | Operator configuration, snapshotted at turn/workflow start |
| Settings snapshot | Parsed immutable settings plus `settingsRevision`, the SHA-256 of canonical functional configuration | Invocation-local, only the revision enters accepted presentation |
| Authorized tool result | Captured typed rows, units, authorized citation handles, `toolName`, result ID, and generated source handle | Existing authorized invocation/native state, never a new transcript store |
| Source reference | `sourceId`, `toolName`, `resultId`, scoped to one contribution | Accepted provenance metadata, not permission to query a source |
| Model selection | Supported block kind, source/field/row mappings, labels, optional approved rule IDs, and suggestion/action wording | Untrusted invocation-local proposal, never authoritative measurements |
| Presentation rule | `id`, `toolName`, numeric `field`, indicator `kind`, comparison cases and `missing=omit` | Agent-owner-approved configuration |
| Agent contribution | `contributionId`, stable `agentId`, `workflowOrdinal`, source references and ordered accepted blocks | Native accepted output |
| Turn presentation | `kind=agent_lz_presentation`, `schemaVersion=1`, generated `presentationId`, revision, markdown fallback and ordered contributions | Immutable native accepted output |
| Visual block | Generated `blockId`, discriminated `type`, optional title/citation handles, and typed hydrated content | Native accepted output |
| Follow-up action | Plain prompt attached to a suggestion or to an authorized source-row identifier | Native output, creates a new ordinary user turn |
| UI display state | Sort column/direction, filter query, expanded fallback, focus, and in-flight activation guard | Browser-only, never changes the saved values |

## Source capture and binding

Capture results only after the existing tool authorization path succeeds. A source handle is resolved from the current contribution's authorized result registry, never from browser input, a stored token, a different contributor, or a new source query.

The result normalization boundary is shared across native, MCP and customer-defined tools. Select adapters by validated structural format and types, never by a fixed tool-name allowlist. Names remain attribution and optional approved-rule scope. [tool-results.md](contracts/tool-results.md) defines the internal typed view and unsupported-result behavior; it is not a requirement to install NL2SQL or any other named integration.

Tables preserve source-row IDs and column-to-field bindings. Cards identify their source row and value field. Chart categories identify source rows and labels, and series identify value fields. Producer validation compares every hydrated value to the captured typed source. Selection schemas have no measurement-value fields.

If a tool supplies no business row identifier, the runtime may assign an invocation-scoped row ID bound to the original captured row position. That is sufficient for stable presentation binding, not for a row-details action or future source query. Actions require an authorized business identifier, otherwise they remain unavailable.

For different agents with identically named sources/fields, `(contributionId, sourceId)` is the binding key. Neither source labels nor `agentId` supplied by the model establishes ownership. The runtime supplies all identities and ordinals.

Null remains null, not zero. Decimal and integer values are strings in their original exact scale, with no binary-float round trip. Exponent notation is expanded deterministically to an exact decimal representation before serialization. Typed source dates and timestamps use ISO date/date-time strings. Units come from the source or approved source metadata, not a model-invented conversion.

## Block shapes

**Cards**: An ordered `cards` array. Each card contains `label`, typed `value`, a source binding, optional unit/display precision, and optional status/trend with provenance. A card group is one block.

**Table**: One source, ordered typed columns, and ordered rows with stable generated row IDs and authorized source-row IDs. `values` keys must equal declared column IDs. Optional row statuses have provenance. Sorting compares exact numeric values, not display strings or JavaScript numbers. Filtering searches displayed cell text. Copy emits headings and visible rows in their display order, with source precision.

A table-wide `rowAction.label` exposes the action. Only rows with an authorized `entityId` may carry `followUp.prompt`. The model supplies a plain `promptPrefix`, not a template/expression. Hydration constructs the final prompt from that prefix and the selected authorized identifier. Rows lacking an identifier have no action. The browser uses the saved prompt for that stable row, never its current display index.

**Chart**: One source, category field, ordered `{label, sourceRowId}` categories, and ordered series with source fields and exact decimal values or null gaps. Each series length equals the category count. `bar` has one series, `grouped_bar` has at least two, and `line` supports one or more. Mixed units and ambiguous categories/field bindings invalidate the block. Null entries are gaps. The 1,000 plotted-point limit counts non-null measurements across all series. SVG coordinate normalization is separate from authoritative values: use bounded normalized geometry, retain exact strings for accessible values/tooltips, and never replace values with rounded coordinates.

**Suggestions**: Ordered plain-text prompts. Activating a chip sends exactly the displayed prompt as one normal user message. No URL, tool name, command, executable template, or privileged payload is an action target.

## Indicators and approved rules

Statuses are `ok`, `warning`, or `critical`. Trends are `up`, `down`, or `flat`. Source indicators must already have those typed meanings. A rule maps an authorized numeric field, such as a source-provided growth value, using only `lt`, `lte`, `eq`, `gte`, or `gt` against exact decimal thresholds. Each case is a conjunction of one or two comparisons on that same field, allowing closed/open ranges without an expression language.

Rule scope must match the agent, tool name, and field. No arithmetic language, model-authored rule, remote lookup, dynamic code, or inferred business status is supported. A trend rule may map a numeric source change field, but does not infer a change from narrative.

`missing=omit` is mandatory. No matching case yields no indicator. Empty/contradictory intervals and overlapping cases that can match the same value are rejected as invalid configuration before enablement. Invalid/mismatched source or rule provenance rejects the affected indicator and records a safe reason. It must never be replaced by a model judgment.

A persisted indicator contains its value and either source provenance or the approved `ruleId` plus source field. Saved rendering uses this accepted value, not the current rule configuration.

## Validation boundaries

JSON Schema checks shape, discriminators, numeric-string syntax, and per-block bounds. Semantic validation additionally checks authorization/source equality, row/column consistency, source ownership, unique IDs, stable ordinals, indicator provenance/rule overlap, chart dimensions/units, prohibited active content, aggregate counts, and encoded size.

The hard limits are 10 accepted blocks across all contributions, 500 rows per table, 8 series per chart, 1,000 non-null plotted measurements per chart, and 262,144 bytes for the complete compact UTF-8 application envelope, including fallback and provenance but excluding Responses/SSE framing. Bytes, not characters, determine the size boundary.

Malformed known blocks are rejected independently, leaving valid blocks and authorized text. A proposed aggregate exceeding a turn-level block or byte limit rejects the entire presentation. Do not drop the fastest/slowest contribution or silently truncate. With no accepted block, send ordinary authorized markdown, not an empty visual envelope. Empty/all-null results use the existing explicit no-data text path.

Visual fields remain plain text. Reject active markup, executable expressions, URL action/remote-resource fields, and unsupported executable content. Renderer safety remains independent: no HTML evaluation, URL linkification, object-to-prop spreading, remote imports, or external SVG references. Approved citations are opaque references resolved through existing authorized citation handling outside the visual data.

## State transitions and replay

1. `capturing`: authorized tool results are registered within the invocation.
2. `selected`: the model proposes bindings and layout only.
3. `hydrated`: runtime fills exact typed values and approved indicators.
4. `validated`: invalid blocks are removed with diagnostics, then aggregate limits are checked.
5. `accepted`: the complete immutable envelope is delivered through native assistant output and committed with that output.
6. `restored`: an authorized native history/result read projects the same accepted values, with no tool query.

Selection and partial JSON are never saved as accepted blocks. If native completion is interrupted, do not promote an incomplete envelope. Previously committed native messages and ordinary available text keep their existing lifecycle. This design adds no crash-recovery guarantee beyond the native host.

The optional generation attempt has one absolute monotonic deadline, 10 seconds after authorized source results and primary answer become available. Normalization, model selection, hydration, validation, serialization and retries consume that same budget. `accepted` and `timed_out` are mutually exclusive terminal decisions. At expiry, seal the pending contribution, retain authorized text and other accepted contributions, record a safe timeout reason, and signal cancellation. Late completion cannot modify native output or become an accepted contribution. Do not await an uncooperative child request before delivering text. Native replay of a recorded completed outcome does not re-run its selection; no monotonic timestamp or credential becomes part of the presentation schema.

`presentationId` is generated once for the accepted turn. A replay deduplicates using existing native turn/message identity plus `presentationId`, not array position or browser state. Contributions use definition-assigned `workflowOrdinal` plus deterministic occurrence ordering for repeated workflow nodes, independent of completion time. Blocks preserve producer order. Invalid contributions cannot reorder valid ones.

Disabling production affects subsequent turn snapshots only. Existing history remains readable using persisted values and provenance under the same access, retention and deletion rules as text history. Do not introduce independent source-permission revalidation during restoration if the user still has conversation access. Preserve existing citation handling. New queries and follow-ups enforce current source permissions; a saved row ID or prompt grants no data access.
