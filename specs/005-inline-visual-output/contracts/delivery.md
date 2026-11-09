# Native delivery and reader contract

**Acceptance proof method — maintainer amendment, 2026-11-08:** Verify the
unchanged streaming/completed/history, authorization, lifecycle and deadline
requirements through controlled local public SDK/client boundaries and
Playwright. Preserve 20 distinct restored-history cases and 20 timing-varied
runs. Real-Azure host smoke/targets/deployed-provider validation are removed
from completion, not deferred. Azure persistence/ACL enforcement remain
unverified residual risks; mocks never prove deployment. Human/performance,
automated local provider/usability checks and repository-wide release/security rules remain.

**Status**: Selected Phase 1 design. The minimum Hosted carrier passed, not the product integrations below.

## Producer

An enabled native agent captures successfully authorized function results through public `function_middleware` and `FunctionInvocationContext.result`. The existing outcome/consent middleware remains authoritative. Failed, refused, cancelled, unavailable, or provider-managed results without a usable typed result are not registered as visual data.

Use public `agent_middleware` and `AgentContext.result` for orchestration. Keep the existing response narrative. After its tool/model work succeeds, make one bounded, tool-free structured selection request using the same public chat client and `response_format` for the selection schema. Supply the user's analytical intent and authorized source/row/field metadata. No model-authored measurement enters hydration.

The additional stage has one absolute monotonic 10-second deadline per enabled agent occurrence, starting when primary answer and authorized source results are available. Normalize, select, hydrate, validate and compact-serialize within the same budget; any SDK/network retries consume remaining time. Race completion against expiry rather than waiting indefinitely for cancellation. At the deadline, seal timeout, signal cancellation and observe cleanup/errors without delaying authorized text. Accept no late mutation, additional block or replacement envelope. Preserve other valid contributions. This deadline does not impose a total multi-agent workflow SLA or change native crash/replay guarantees.

This second selection call is intentionally simpler than changing the primary agent's text/tool contract or inventing a selection tool/event. Disabled agents add no selection request. Invalid selection is a diagnosed visual rejection with retained authorized text, not a successful visual result.

Capture and parse typed tool content without a float round trip. Preserve exact decimal tokens/strings and source row associations. Shared structural adapters described in [tool-results.md](tool-results.md) serve any eligible native/MCP/customer-defined tool without tool-name-specific enablement. This is not an unrestricted JSON-to-chart parser: ambiguous, unstructured, unavailable or lossy results receive a diagnosed authorized-text fallback. NL2SQL and all other named integrations are optional. Source owners may provide compatible typed formats independently, without becoming a feature release dependency.

Hydrate, validate and aggregate deterministically. Keep ordinary narrative output and append one canonical envelope as a standard assistant message `output_text`. Its `markdown` combines the existing authorized explanation with a deterministic accessible projection of accepted key values, indicators and authorized citations. Escape source labels/cells as markdown text, never interpolate active markup/links. Do not ask the model to recopy those values.

For streaming, use public `ResponseStream`/`AgentResponseUpdate`/`AgentResponse` composition and finalization so the exact appended message is in both live updates and the completed native result. Never edit private host builders or stream raw SSE bytes. Preserve tool-consent/failure/cancellation and lazy cleanup behavior. The finalization parity test is an implementation stop gate before opt-in.

The envelope is compact UTF-8 JSON, not a markdown code fence, tool result, refusal, custom event, citation metadata extension, HTML fragment, or separately fetched resource. A channel-facing projection removes the machine envelope and supplies its markdown before a text-only frontend receives it.

Reserve `agent_lz_presentation` for trusted hydrated output. The producer must buffer/recognize reserved-marker-shaped primary model text and preserve it only as inert quoted text with a safe diagnostic, never as a standalone presentation message in live or saved output. Otherwise a model could bypass source validation by imitating a valid envelope. Tool/user messages are not presentation carriers. This guard does not invent a protocol event or grant authority to a marker.

## Hosted native surface

Use the existing agent/workflow-scoped OpenAI protocol base. Emit only standard Responses message/text events. Envelope fragments are buffered as machine content by the new reader and are never streamed as raw JSON into the chat message. Ordinary preceding text can continue streaming.

Read saved completed messages using the existing authorized Responses retrieval/history client. The pinned UI uses `responses.retrieve(response_id)` and `responses.input_items.list(response_id, limit=100, order="asc")`. Native conversation-item listing additionally passed in the minimum standalone probe, but is not a replacement for product owner admission.

Project-wide 403/404 routing failures are not authorization evidence. The UI's authenticated admission, owner lookup, native call correlation and platform user partition remain unchanged. No browser-supplied header/reference establishes access.

## Durable native surface

Keep official `DurableAIAgentWorker`, the isolated v2 state policy and the existing agent/workflow SDK clients. Ordinary native agent response text can carry the same appended message.

The current research/review workflow places `answer.text` in `ReviewRequest.draft`, then `ResearchReviewResult.draft`, finally `WorkflowContext.yield_output(result)`. This flattening would lose message boundaries. The selected change is an optional typed `presentation` field on `ReviewRequest` and `ResearchReviewResult`, matched by the UI's strict business-result readers. Extract the accepted envelope from the actual `AgentResponse.messages`, keep `draft` as readable markdown, and carry the typed envelope in that native field. Omit the field when there is no accepted presentation.

Both Hosted workflows and Durable workflows use this business-result shape, with their existing host serialization. The stable marker and schema version remain inside the presentation field. Human review sees readable draft text, never machine JSON. Do not locate envelopes by substring regex within arbitrary prose, alter Durable state-version identity, invent a history/SSE API, or create a presentation side store.

Hosted and Durable use distinct admission/progress/history/result APIs. Both must restore accepted values from fresh authorized clients without source calls. Neither grants cross-version checkpoint migration or exactly-once external effects.

Saved presentations are originally authorized snapshots governed by the same access, retention and deletion policy as text history. Losing source access while retaining conversation access does not add a new visual-history source ACL lookup. Preserve existing citation resolution/admission behavior. A new query, suggestion or row follow-up always traverses the current tool/source authorization path.

## New reader behavior

| Input | Projection |
| --- | --- |
| Ordinary text-only native history | Existing markdown and citations, no visual parsing |
| Recognized v1 envelope | Markdown plus safely projected known blocks |
| Unknown optional fields | Ignore through explicit projection, never spread into UI props |
| Unknown block kind | Skip that block, retain recognized siblings and fallback |
| Malformed known block/contribution | Reject that unit with a safe diagnostic, preserve other valid units/text |
| Unsupported contract version | Stable `markdown` fallback only, no guessed block interpretation |
| Aggregate block/byte violation | Entire presentation rejected with diagnosed text fallback, no truncation |
| Incomplete/cancelled envelope | Never accepted as a visual or parsed via partial JSON |
| Visual-generation deadline expires | Authorized text and other valid contributions, safe timeout diagnostic, no late accepted output |
| Native owner/authorization error | Existing fail-closed error, expose neither fallback nor blocks |

Recognize only a complete standalone machine message with the marker/version shape. Use duplicate-key-rejecting bounded parsing and reject nonfinite values. Do not mistake arbitrary user/assistant JSON for an envelope.

Apply recognition only in the admitted native assistant/result presentation path, not arbitrary user/tool/progress content. Pair it with the trusted producer's reserved-marker guard; schema validity alone cannot establish that primary model text was hydrated.

Validate size/count before creating visual props. Producer budgets prevent legitimate saved output from exceeding limits, but readers independently reject oversized/malformed output. Bounded extraction of the stable markdown field may provide fallback for a malformed or unsupported envelope without interpreting its blocks. No raw envelope dump or success-shaped empty chart is permitted.

New supported UI/customer/server adapters must implement the marker/version/fallback reader even when they render no visual blocks. Text-only frontends consume the adapter's markdown projection. Unchanged older raw Responses consumers are explicitly outside acceptance. No unsupported claim is made that any unaware third-party caller automatically receives plain markdown.

## Interaction and observability

The build-free Chainlit element is `public/elements/Presentation.jsx`, using local SVG and existing component/theme imports. A valid visual projection accompanies the existing narrative, with fallback available without duplicating the narrative by default. On renderer failure, the adapter supplies the full escaped markdown projection. Its only follow-up operation is documented `sendUserMessage` with the saved suggestion or row prompt. No direct tool callback or privileged API is introduced.

Guard double keyboard/pointer activation while that action is in flight. A distinct later activation is a new ordinary turn. Use current server-side authorization for each turn. Copy exports only currently authorized accepted rows in their current displayed order.

Diagnostic reasons distinguish configuration/version/schema/source-binding/indicator/size/content rejection from native authorization or transport failures. Include correlation, component, contribution/block ID and counts, not raw source data, user credentials, rule guidance or hidden rows. Record rejected visual outcomes separately from successful text completion.

For the additional stage, record elapsed duration, accepted/rejected/timed-out outcome, and late-completion exclusion through existing structured telemetry. Observe cancellation/child-task failure safely without extending delivery or hiding a failed optional operation. Native completed output remains immutable; replay/history never restarts the stage.
