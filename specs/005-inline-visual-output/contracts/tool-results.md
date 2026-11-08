# Tool-independent result normalization

**Status**: Phase 1 design. This defines the runtime normalization boundary, not a new tool execution API or mandatory source integration.

## Eligibility

Any user-selected native or MCP tool, including a customer-defined tool, may provide visual data after its existing authorization and outcome checks succeed. Eligibility depends on a captured result's usable structure, exact types/precision and verifiable invocation association. There is no presentation tool-name allowlist, NL2SQL prerequisite or requirement to qualify every existing tool before release.

Tool and endpoint admission, network host allowlists, consent and user-delegated access remain separate and unchanged. A payload that declares itself authorized is not authority. Failed, refused, cancelled or inaccessible results are not eligible.

## Shared typed view

Public function middleware captures successful supported content and its real invocation association without replacing the ordinary tool result. Trusted structural normalizers produce one internal view for hydration:

| Content | Invariant |
| --- | --- |
| Runtime source/result identity and actual tool name | Assigned or associated from the current authorized invocation, not model/browser/payload authority |
| Ordered field declarations | Unique field IDs, explicit supported types, optional source units and typed indicator metadata |
| Ordered rows and original field values | Exact numeric tokens/strings and nulls, no model conversion, rounded float reconstruction or silent row filtering |
| Source-row association | Unique captured row binding within the invocation; a generated row-position identity is sufficient for saved visual binding |
| Optional business identifier | Needed for an authorized row-details prompt, never inferred from a display index |
| Authorized citation handles | Resolved through the existing citation path, never arbitrary links or fetch targets |

[source-fixture.json](examples/source-fixture.json) illustrates this internal `fields` plus `rows[].data` view. Its `sourceId`, `resultId`, tool attribution and domain labels are fixture metadata, not a public source API. A tool may expose compatible typed fields/rows directly, or a trusted format adapter may normalize its existing result. Dispatch by validated structural format/types, not by tool name.

The presentation engine receives this same view for all producers. Values conform to the exact scalar representations in [data-model.md](../data-model.md). String IDs are not guessed to be numbers. Missing/ambiguous type or unit metadata is not invented from prose. Adapters preserve source row/field associations and cannot treat a result from another contributor as local data.

A generated invocation-scoped row ID does not grant a future query or row action. Without an authorized business identifier, the row remains readable/sortable/copyable but its details action is unavailable.

## Failure and operation

Unstructured, lossy, ambiguous, unavailable or unsupported results retain the authorized primary text with a safe unsupported-result reason. Do not extract model-authored measurements, guess precision discarded upstream, add a source query, or silently treat unsupported data as an empty successful chart.

The optional normalization/selection/hydration/validation/serialization stage shares the per-agent 10-second budget in [delivery.md](delivery.md). Bounded processing must remain responsive to expiry. No format adapter or retry starts a fresh budget. A timed-out attempt cannot accept later results.

Do not let synchronous parsing/normalization monopolize the deadline-watching execution loop. Use bounded processing units with deadline checks or supervised offloaded work, and reject its late completion through the same sealed-attempt guard.

Source owners may independently expose a compatible typed format. That is an optional way to qualify their results, not a release dependency on the owner or a named connector. Existing approved rules may match the real `toolName` as a deliberate rule-scope constraint, not a visual eligibility gate.

## Acceptance

Use equivalent typed results from differently named native/MCP/customer-defined tools through public capture and the same normalizer/hydrator. Hold layout/guidance constant and compare accepted values, units, block shapes and available interactions, allowing generated IDs and actual provenance attribution to differ. No name-specific enablement or engine branch is required.

Use source-provided indicators or no rules for this comparison. Separately verify that explicitly tool-scoped approved rules match only their configured tool and cannot cross source ownership. Test malformed/lossy results from every tool category for diagnosed text fallback. No specific remote tool integration is a release prerequisite, and these future cases are not claimed as executed by the minimum Hosted proof.
