# Draft presentation contracts

**Current proof method:** the 2026-11-08 maintainer amendment selects local
controlled SDK/history/Playwright acceptance and local provider/hook checks.
Azure LIVE target/smoke/parity tasks are retired, not deferred; deployment
behavior remains unverified residual risk. Human/performance/operator criteria
and schemas/hashes are unchanged. See [the specification](../spec.md).

These are Phase 1 design artifacts, not published customer contracts or a new runtime API. The shared schema names and IDs designate their intended umbrella `contracts/` locations after review. No root contract or component pin changes in this planning step.

| File | Producer and consumer |
| --- | --- |
| [turn-presentation-v1.schema.json](turn-presentation-v1.schema.json) | Runtime hydrator/aggregator to native state and new UI/customer readers |
| [presentation-selection-v1.schema.json](presentation-selection-v1.schema.json) | Untrusted model selection to runtime hydrator, never measurements |
| [agent-presentation-settings-v1.schema.json](agent-presentation-settings-v1.schema.json) | Owner configuration through umbrella publication to the orchestrator's immutable turn snapshot |
| [delivery.md](delivery.md) | Standard Responses/Durable delivery, reader compatibility, fallback and failure semantics |
| [configuration.md](configuration.md) | Key, label, ownership, defaults, validation and provider/lifecycle parity |
| [tool-results.md](tool-results.md) | Tool-independent eligibility and shared typed result normalization, not a named integration dependency |
| [examples](examples/) | Valid hydrated/selection/settings fixtures and invalid shape fixtures |

All schemas use JSON Schema Draft 2020-12 and strict known producer shapes. Schema validation is not source authorization or semantic validation. Required semantic checks are in [data-model.md](../data-model.md). Sibling SHA-256 files pin exact schema bytes.

**Producer**: Validate the full known v1 shape and semantic constraints before accepting native output. A change to required fields or interpretation needs a new schema version.

**Reader**: First recognize the marker, version and fallback, then validate/project only recognized block types. Do not apply the strict producer union to an entire future-containing payload and reject every known block. Skip unknown blocks, tolerate unknown optional fields by explicit safe projection, reject malformed known blocks, and keep markdown available. Never pass unknown properties into React/SVG props. Unknown versions use the stable fallback only.

The full design is in [data-model.md](../data-model.md). Promotion must add source-integrity, limits, security and consumer fixtures in the owning repositories, not merely copy schemas.

The fixed 10-second generation deadline, timeout/late-result behavior and existing text-history access policy are delivery semantics, not new payload/configuration fields. The three schemas and their integrity hashes remain unchanged by these clarifications.
