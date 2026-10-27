# Shared Agent Landing Zone contracts

## Audit event v2 (current)

`audit-event-v2.schema.json` and
`audit-event-v2.application-insights.schema.json` are the current audit
contract. Version 2 renames the Application Insights event prefix from
`gptrag.audit.*` to `agentlz.audit.*`, sets `schema_version` to `2`, and expects
`service_name` values from the renamed `agent-app-*` components (see
[naming-map.md](naming-map.md)). Field names, enums, and semantics are
otherwise unchanged from v1.

`audit-event-v2.sha256` pins the exact LF-encoded bytes:

- Logical schema: `884dfa2441d3313c8ec46a099f60ce86e7abb6cdf88bb5b5da720463edbf5e97`
- Application Insights wire schema: `48416073768c0710b9a1f58640d4e822745f28b3a17b3712a2fe4cd9326c9c07`

During the R14 transition, readers accept both v1 and v2 events (both
prefixes, dispatched on `schema_version`); producers switch to v2 when they
ship their renamed releases.

## Audit event v1 (deprecated)

Deprecated by v2; retained unchanged as history. Removal follows the R14
transition in [naming-map.md](naming-map.md), once all pinned components emit
v2 only.

These schemas are the shared Agent Landing Zone audit contract consumed by orchestrator
v3.8.0 and ingestion v2.5.0.

`audit-event-v1.sha256` pins the exact LF-encoded bytes:

- Logical schema: `825db8ef40a81e2c19e5d80d37c565b6b47fc9a6540e9881d35cc12b8fde5aab`
- Application Insights wire schema: `066c8f5408610ab839d5121d06ca5bc59e8797e551d5c47c875c5ba52f7e0588`

Consumers must use `schema_version` when interpreting events and ignore unknown
optional fields. Technical audit evidence supports operator governance work but
does not establish legal or regulatory compliance.

## Hosted conversation ownership

The preferred binding is `HOSTED_CONVERSATION_OWNER_BINDING=delegated`. The
trusted UI BFF derives the opaque `x-ms-user-identity` value only from its
authenticated server-side user principal and sends it to the hosted Responses
2.0.0 endpoint. Browser input is never an ownership source. This identity value
is also separate from OBO access tokens: OBO remains authorization for retrieval
and downstream data, while the delegated header partitions Foundry-managed
response chains.

The UI BFF receives exactly two direct assignments at the individual hosted
agent scope:

- Foundry Agent Consumer
  (`eed3b665-ab3a-47b6-8f48-c9382fb1dad6`).
- Agent Landing Zone Hosted Agent User Identity Impersonation (formerly "GPT-RAG Hosted Agent User Identity Impersonation"; setup renames existing definitions in place)
  (`bef66abe-a495-530a-be1d-5d882fecff03`), a custom role with no `Actions`
  and exactly
  `Microsoft.CognitiveServices/accounts/AIServices/agents/endpoints/UserIdentityImpersonation/action`
  in `DataActions`.

Inherited, group-derived, custom-equivalent, or broader assignments do not
satisfy this contract. Foundry User and Project Runtime User are prohibited.
The hosted container receives neither role and no ownership key. Before
continuity is enabled, setup verifies the live routed Responses protocol is
exactly 2.0.0 and both assignments are direct and exact. Until then,
`HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED=false`,
`HOSTED_CONTINUITY_ENABLED=false`, and the runtime contract is HTTP 503.

## Hosted conversation capability v1 (disabled fallback)

`hosted-conversation-capability-v1.schema.json` is retained only for an explicit
`HOSTED_CONVERSATION_OWNER_BINDING=capability` fallback. Delegated deployments
do not provision or require its Key Vault, secret, secret role, or App
Configuration Key Vault reference. Switching to delegated removes active
fallback access and indirection while retaining historical secret versions.

In capability mode, the UI BFF derives `oid` from the authenticated server-side
principal, signs and verifies the canonical framing, and keeps the envelope at
the UI boundary. The hosted container receives neither the envelope nor the
HMAC key. The key must be in a dedicated UI BFF vault selected with
`HOSTED_CONTINUITY_KEY_VAULT_URI` or
`HOSTED_CONTINUITY_KEY_VAULT_NAME`; the shared workload vault is rejected.

`hosted-conversation-capability-v1.sha256` pins the exact LF-encoded schema
bytes. Capability consumers must reject unknown schema versions, invalid or
expired signatures, mismatched owners, and non-canonical framing.

## Conversations panel v1 (issue #611, ADR-0004)

`conversations-panel-v1.schema.json` is the shared wire contract for the
optional hosted administrative panel: user-facing history/feedback/deletion
(consumed by `agent-app-ui`) and operator-facing overview/corpus-curation
(consumed by `agent-app-ingestion`). It has no single top-level instance;
every shape lives under `$defs` and is referenced by a JSON Pointer fragment
(for example `#/$defs/ConversationsListResponse`). Every object shape is
strict (`additionalProperties: false`); an unknown field is a schema
violation, mapped to HTTP 422, never silently ignored.

`conversations-panel-v1.sha256` pins the exact LF-encoded schema bytes.

Non-negotiables carried over from ADR-0001/0003/0004 and reflected directly
in the schema:

- The hosted agent/container never implements or consumes any shape here.
  It is stateless and holds **zero** managed-Conversations RBAC; only the
  `agent-app-ui` BFF (user surfaces) and `agent-app-ingestion` admin app
  (operator surfaces) ever produce or consume these payloads.
- `MessageItem.content` is read live from Foundry managed Conversations
  (the system of record) after the owner gate passes — it is never
  persisted to Cosmos. Cosmos-backed shapes (`ConversationSummary`,
  `FeedbackRecord`, `CorpusCurationItem`, the overview counts) carry
  metadata only: identifiers, titles, timestamps, ratings, category codes,
  and counts — never message bodies, citations, or document content.
- `correlation_id` reuses the exact `audit-event-v1` pattern
  (`^req_[0-9a-f]{32}$`) so panel requests join the same operator audit
  trail; it is always server-generated, never accepted from client input.
- `Cursor` is opaque, signed, expiring, and bound to the authenticated
  caller's principal — never a raw offset or caller-supplied identifier. A
  tampered, expired, or cross-principal cursor is a 422, not a 401/403/404.
- Panel `{id}` path segments (`/panel/conversations/{id}/...`) are accepted
  only as a lookup key: every per-conversation endpoint re-checks ownership
  (the owner-index row or an equivalent delegated per-user authorization)
  before ever reading the managed-Conversations store. A failed owner check
  and a missing conversation return the identical `404` — never a
  distinguishable `403` — so there is no existence oracle.
- `OperatorOverviewMetricsResponse` counts are aggregate-only and each
  bucket is suppressed (`null`) below `PANEL_OVERVIEW_MIN_CARDINALITY`
  rather than disclosing a small exact count. `CorpusCurationItem` never
  carries or is derived from conversation content.
- Error matrix (`ErrorResponse`, `{detail, correlation_id?}`): 401
  missing/invalid bearer; 403 wrong token type/audience (app-only token on a
  user surface, or a missing operator role); 404 not-owner or missing; 422
  schema/bounds violation (including a bad cursor); 502 the
  managed-Conversations or panel-metadata store actually failing; 503 the
  surface itself is undeployed. 503 is never used for an unmet
  owner-binding evidence gate — that falls back to `owner_index`
  transparently with no error at all.

Panel Cosmos containers (provisioned only when
`DEPLOY_ADMINISTRATIVE_PANEL=true`, via
`config.deployment.composition.panel_database_containers`):

| Container | Canonical App Configuration key | Partition key | Purpose |
| --- | --- | --- | --- |
| `panel-conversation-owner-index` | `PANEL_OWNER_INDEX_DATABASE_CONTAINER` | `/principal_id` | `principal_id -> {conversation_id, title, timestamps}`; the sole authorization check before any per-conversation read/feedback/delete. |
| `panel-feedback` | `PANEL_FEEDBACK_DATABASE_CONTAINER` | `/principal_id` | Feedback metadata (rating/category/comment/message reference). |

Both containers use the AI Landing Zone's generic `defaultTtl: -1` (no
automatic item expiration) — Agent Landing Zone performs no automatic scheduled
deletion; retention is operator/owner-initiated hard delete only
(`DELETE /panel/conversations/{id}`). Hosted/panel provisions *only* these
two containers, never the classic `conversations`/`datasources`/`prompts`/
`mcp` list, so switching topologies can never mix protected chat content
with panel metadata in the shared Cosmos account/database. Reversal is a
config flip (`DEPLOY_ADMINISTRATIVE_PANEL=false`) plus re-provisioning; no
destructive migration of classic conversation content is ever performed.

RBAC is intentionally **not** granted through the generic, account-scope
`containerAppsList` role loop (which would also reach any other container
in the shared account, including a still-present classic `conversations`
chat-content container after a topology migration). Instead,
`config.panel.setup` assigns exactly two **container-scoped** Cosmos SQL
role assignments per container (`/dbs/{database}/colls/{container}`, never
the account root):

| Identity | Role | Scope |
| --- | --- | --- |
| `agent-app-ui` (frontend, the only component holding the user token) | Cosmos DB Built-in Data Contributor | Both panel containers |
| `agent-app-ingestion` (dataingest, operator overview counts only) | Cosmos DB Built-in Data Reader | Both panel containers |
| `agent-app-orchestrator` (hosted agent/container) | *(none)* | *(none — never resolved or assigned by this script)* |

The panel's opaque pagination cursor is signed with the UI's existing
`CHAINLIT_AUTH_SECRET` (already Key-Vault-backed, with `frontend` already
holding `KeyVaultSecretsUser`) — no new Key Vault secret, reference, or RBAC
is introduced for cursor signing.

App Configuration keys (label `agent-lz`, published unconditionally and
safely inert by `config.panel.settings.public_settings`; matches the merged
`agent-app-ui` `panel_config.py` exactly — no invented duplicates):

| Key | Default | Notes |
| --- | --- | --- |
| `DEPLOY_ADMINISTRATIVE_PANEL` | `false` | Existing key; provisions panel Cosmos containers and enables panel routers, including cross-conversation enumeration. |
| `PANEL_HISTORY_ENABLED` | `false` | User-facing history/feedback/deletion gate. |
| `PANEL_HISTORY_OWNER_BINDING_VALIDATED` | `false` (forced) | This ADR's own environment-evidence gate for the panel's list/read call path; independent of ADR-0003's `HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED`. Forced `false` here because no live verification procedure ships in this change — flipping it is future work once such a procedure exists. |
| `PANEL_CONVERSATION_ENUMERATION_MODE` | `owner_index` | Panel-only listing backend selector (`owner_index` pre-gate/fallback vs. `delegated`). |
| `PANEL_CONVERSATIONS_TOKEN_AUDIENCE` | `""` | Expected `aud` claim on the delegated user bearer; required once `PANEL_HISTORY_ENABLED=true`. |
| `PANEL_CONVERSATIONS_TENANT_ID` | `""` | Falls back to `OAUTH_AZURE_AD_TENANT_ID` when unset. |
| `PANEL_OWNER_INDEX_DATABASE_CONTAINER` | `panel-conversation-owner-index` | Published by the generic AILZ database-container-list mechanism. |
| `PANEL_FEEDBACK_DATABASE_CONTAINER` | `panel-feedback` | Published by the generic AILZ database-container-list mechanism. |
| `PANEL_CURSOR_TTL_SECONDS` | `600` | Pagination cursor lifetime (bounded 30–3600 by the UI). |
| `PANEL_OVERVIEW_MIN_CARDINALITY` | `5` | Operator overview metric bucket-suppression threshold. |

Operator-role authorization for the ingestion admin surfaces reuses
ingestion's existing admin-dashboard bearer/role pattern (the same
`OAUTH_AZURE_AD_TENANT_ID`/`OAUTH_AZURE_AD_CLIENT_ID` pair `require_admin`
validates); this repository does not introduce a separate audience/config
key for token validation. `agent-app-ingestion` PR #274 (merge
`5569dd6af3ecb317e1037108cb21859f1b2185a1`) does define the operator
authorization *inputs* below (`PANEL_OPERATOR_SURFACES_ENABLED`,
`PANEL_OPERATOR_APP_ROLE`, `PANEL_OPERATOR_GROUP_ID`), which this repository
now publishes with matching names and safe defaults -- no invented
duplicates.

| Key | Default | Notes |
| --- | --- | --- |
| `PANEL_OPERATOR_SURFACES_ENABLED` | `false` (forced) | Gates the ingestion operator overview/corpus-curation endpoints (fail-closed 503). Forced `false` here the same way `PANEL_HISTORY_OWNER_BINDING_VALIDATED` is: no dedicated evidence-gate verification procedure ships in this change, even though the ingestion component work itself (PR #274) has landed. |
| `PANEL_OPERATOR_APP_ROLE` | `""` | Operator Entra app role name (`roles` claim); a plain operator input, published empty and safely overridable once an operator is ready to name a real role. |
| `PANEL_OPERATOR_GROUP_ID` | `""` | Operator Entra group object id (`groups` claim); same as above. At least one of role/group must be set (in addition to `PANEL_OPERATOR_SURFACES_ENABLED=true`) before ingestion's operator surfaces stop returning 503. |

As of this change, hosted-panel topology selection
(`DEPLOY_ADMINISTRATIVE_PANEL=true`) still fails closed at
`config.deployment.topology`/`composition`
(`HostedPanelUnsupportedError`); this is now a **deliberate, separate**
decision distinct from component readiness -- the `agent-app-ingestion`
operator-surface component work this platform contract was blocking on has
landed (PR #274). Lifting the topology gate and repinning `manifest.json`
for all changed components together remain their own coordinated follow-up,
gated on the still-pending live evidence procedures for
`PANEL_HISTORY_OWNER_BINDING_VALIDATED` and `PANEL_OPERATOR_SURFACES_ENABLED`
(see ADR-0004's "Adoption and migration" and "Review trigger" sections),
not on any further platform-repository platform-contract change.


## App definition v1 (feature 002, Agent Landing Zone)

`app-definition-v1.schema.json` is the structural contract for an
application's `app-definition.json`. Owner: this repository (umbrella);
consumed by the umbrella validator and by component repositories that ship an
app definition. Semantic rules (unique component names, settings key
collisions, path existence) live outside the schema.

The additive component `egress` contract retains `schemaVersion: 1`.
Each entry contains `fqdn`, `protocol`, `port` and `purpose`; semantic
validation and actual workload selection use `config.appdefinition.egress`
and `config.deployment.egress_plan`. An explicit empty array revokes only
that component's additional owned requirements; absence preserves legacy
compatibility. Ownership, reconciliation and the generic infrastructure
handoff are specified in [ADR-0025](../docs/adr/ADR-0025-component-runtime-egress.md).
The closed platform-outputs v1 schema below is unchanged.

## Platform outputs v1 (feature 002, Agent Landing Zone)

`platform-outputs-v1.schema.json` describes the non-secret platform endpoints
published after `azd provision`. Owner: this repository (umbrella, producer);
consumers are the application components that read the published outputs.

Both schemas pin their exact LF-encoded bytes in a sibling
`<name>.schema.json.sha256` file (`<sha256>  <file name>`). Versioning rules:
additive optional fields keep v1 and require regenerating the `.sha256` file;
any change in interpretation, a new required field, or a removed field
publishes a new `-v2` file alongside v1. Consumers must check `schemaVersion`
and ignore unknown optional fields only where the schema permits them (both v1
schemas set `additionalProperties: false` at the top level). Rename rules for
labels, prefixes, indexes (`agent-lz-*`), and images (`agent-app-*`) live in
`naming-map.md`.
