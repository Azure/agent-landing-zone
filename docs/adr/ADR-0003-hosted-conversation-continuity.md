# ADR-0003: Multi-turn continuity for the hosted-agent Responses path across compute/version replacement

**Status:** Accepted (decision and live evidence sufficient; the orchestrator
container boundary that makes the hosted agent stateless and rejects the
top-level `conversation` / `previous_response_id` continuity params is merged in
gpt-rag-orchestrator **PR #308**, merge
`a828253b85c6ed7a63f6085c1666f75a9ca2b7d8`; the gpt-rag-ui BFF continuity
implementation and the App Configuration/contract wiring in this repo remain
pending as adoption work — see "Adoption and migration")<br>
**Date:** 2026-08-07<br>
**Owners:** GPT-RAG maintainer (Paulo), architecture analysis, with gpt-rag-ui and gpt-rag-orchestrator component owners (revised after independent security review)

> Native-runtime revision: [ADR-0034](ADR-0034-native-agent-and-workflow-hosting.md)
> supersedes mandatory stateless generation and manual BFF transcript replay
> for the new native MAF runtime. It does not invalidate the identity-boundary
> findings or promise checkpoint portability across hosts or agent versions.
> The historical evidence below is retained for the original deployment model.

> **Revision note (2026-08-07, superseded in part by ADR-0004).** Three points
> in this ADR are tightened after security review and after live OQ-OWN
> evidence, and this ADR is updated to match:
>
> 1. **Persistence/replay location.** ADR-0004's approved invariant is that the
>    hosted **container holds zero managed-Conversations data-plane RBAC (neither
>    read nor write)**, because the Foundry gateway strips the user token so the
>    container has no authenticated identity and could only act on forgeable
>    caller metadata. Therefore the container is **purely stateless** — it
>    receives a complete ordered input set and returns output — and **all**
>    managed-Conversation read/append/persist plus continuity move to the
>    **authenticated UI BFF**. Where this ADR says "inside the hosted agent the
>    application retrieves/replays/persists," read "**the UI BFF** retrieves,
>    replays, and persists."
> 2. **How the logical ID is carried.** The stable logical conversation
>    identifier is **not** carried as a raw resource ID in request metadata that
>    a service could act on. It is carried as a **BFF-issued, signed, opaque
>    locator handle** referencing `conversation_resource_id`, so no
>    caller-selected ID drives a read and a direct caller cannot forge
>    ownership. In `capability` mode (the fallback/pre-gate mechanism) that
>    handle additionally embeds an `oid` claim
>    (`{oid, conversation_resource_id, issued_at, expiry, key_id}`) that the BFF
>    re-checks against the live token before any read; in `delegated` mode (the
>    chosen/default mechanism — see point 3) the handle omits the `oid` claim
>    and the BFF-side re-check, because the Foundry platform itself enforces
>    per-user authorization on the read. Either way the handle requires **no
>    persistent store**, so continuity holds in **hosted/no-panel with zero
>    Cosmos**. See ADR-0004 for the capability design, key rotation,
>    replay/theft handling, and the panel-only owner index used solely for
>    cross-conversation enumeration.
> 3. **OQ-OWN resolved for the hosted-continuity call path (2026-08-07).** A
>    live, end-to-end, disposable-environment experiment
>    ([`gpt-rag#591` evidence comment](https://github.com/Azure/GPT-RAG/issues/591#issuecomment-5212288245),
>    [cleanup proof](https://github.com/Azure/GPT-RAG/issues/591#issuecomment-5212334345))
>    proved that Foundry hosted agents on container protocol **`responses`
>    2.0.0** enforce **per-user isolation of the platform-managed response
>    chain and `get_history`** from a trusted middle-tier identity asserting
>    `x-ms-user-identity`, gated by a **custom `UserIdentityImpersonation`
>    data action at agent scope** (present in no built-in role) plus a
>    **narrow `Foundry Agent Consumer`** role for the interact action. This
>    **supersedes `capability` as the default** owner-binding mechanism: the
>    **native delegated-header mechanism becomes the chosen/default** binding
>    once an **environment evidence gate** confirms the deployed protocol
>    version and RBAC shape; `capability` becomes an **optional,
>    disabled-by-default fallback** an operator may **explicitly** select
>    (never auto-engaged, never the required primary). Until the gate passes,
>    hosted multi-turn continuity stays **off** and the continuity path
>    **fails closed with 503** (mirroring the `POST /retrieve` disabled-gate
>    idiom) rather than silently running any mechanism. This changes only *which
>    mechanism authorizes a read*; it does **not** change the BFF-mediated,
>    stateless, cross-version replay mechanism below (Option C) — the
>    top-level `conversation` parameter and `previous_response_id` remain
>    version-bound and are still never used for continuity. See the
>    "Delegated header mechanism" subsection under the Decision.


## Context

ADR-0001 chose Option 1: package GPT-RAG orchestration as a Microsoft Foundry
hosted agent, with the Chainlit UI as a thin BFF speaking Responses, and made
the orchestrator Container Apps optional. ADR-0001 froze two relevant
contracts: hosted modes use **Foundry managed Conversations** as chat history
system of record (no Cosmos in hosted/no-panel), and hosted versions are
**immutable, one version serves 100% of traffic, update = publish new version +
switch, rollback = revert version**.

The canonical Foundry Responses v2 path is implemented in
`Azure/gpt-rag-orchestrator` `develop` (through PR #304). The hosted agent
container originally persisted user and assistant items into Foundry managed
Conversations. That in-container persistence is now **superseded**:
gpt-rag-orchestrator **PR #308** (merge
`a828253b85c6ed7a63f6085c1666f75a9ca2b7d8`) implements the stateless container
boundary — the container holds zero Conversations RBAC and **rejects** the
top-level `conversation` / `previous_response_id` continuity params — matching
the decision below.

### Observed blocker (evidence)

In a real `NETWORK_ISOLATION=true` deployment using an immutable image digest:

- Turn 1 works. The managed Conversation Items remain readable through the
  Conversations data API after the hosted compute/version is replaced.
- When the same **top-level Responses `conversation` ID** is reused on the
  replacement version, the Foundry hosted `/responses` gateway returns
  **HTTP 404**. It also 404s after routing back to the original version.
- A fresh request (no reuse of the prior top-level `conversation`) succeeds.

Conclusion supported by the evidence: the 404 is **platform pre-routing /
session-affinity behavior that executes before the application runs**. It is
not missing persisted data — the managed Conversation Items (the system of
record) are intact and readable. Two distinct Foundry constructs are being
conflated:

1. **Managed Conversations** — a durable data-plane store of items. Survives
   compute/version replacement. Readable. System of record (ADR-0001).
2. **The `/responses` gateway session binding keyed by the top-level
   `conversation` parameter** — a control-plane routing/session construct
   coupled to the serving version/compute session. Does **not** survive
   immutable-version or compute replacement.

Because ADR-0001's supported update model *is* version replacement, any
continuity mechanism that depends on construct (2) is structurally broken by
the platform's own update path.

### Security correction (why this ADR was revised)

A previous revision of this ADR chose an application-managed mechanism that
carried a **stable logical managed-Conversation ID in request metadata** and
then had the **hosted agent container** read prior items from managed
Conversations, replay them, run the turn, and append the new items — all inside
the container. An independent security review found this **SECURITY-INVALID**
and it is **withdrawn**:

- The Foundry gateway strips the `Authorization` header, so the **user token
  never reaches the container** (ADR-0001, "User identity and document-level
  security"). Any container-side managed-Conversations read is therefore a
  **service-identity** read.
- Letting a **caller-supplied logical conversation ID** drive a
  **service-identity** read is a textbook **confused-deputy / BOLA (IDOR)**:
  caller A can pass caller B's conversation ID and the hosted service credential
  would read and replay B's history. Per-user isolation is lost.
- It also requires granting the container a managed-Conversations data-plane
  **read** role, breaking the history-blindness invariant reaffirmed in
  ADR-0004.

The corrected model, decided below, moves **all** authorized managed-Conversation
create/read/append/delete into the **authenticated UI BFF** (which holds the end
user's Entra identity and can bind ownership), and reduces the hosted container
to a **stateless, history-blind** compute that receives complete bounded ordered
Responses input and returns output. This is consistent with ADR-0004's
owner-bound, fail-closed contract and its OQ-OWN read-mechanism selector.

### Acceptance criteria (from the task)

- Stable logical multi-turn continuity **across compute/version replacement**.
- Canonical Responses interoperability (stateless caller-supplies-input mode).
- **Fail-closed security**: no service-identity read driven by a caller-selected
  ID; no unauthorized cross-user read; no silent success-shaped fallback; a
  read/append failure must **not** silently start a fresh thread.
- **Owner-bound history**: the BFF authenticates the end user and binds
  conversation ownership before any read; non-owner and missing return
  **indistinguishable 404**.
- **History-blind, stateless container**: the hosted container holds **zero**
  managed-Conversations data-plane RBAC (no create/read/append/delete) and
  cannot select server-side history; direct hosted-agent calls stay stateless.
- No Cosmos chat content in hosted/no-panel; if an owner index is needed (Option
  A), only owner-binding **metadata** is stored, never content.
- Delegated OBO / Toolbox retrieval authorization preserved **separately** from
  history ownership (ADR-0001 INV-002, `POST /retrieve` boundary unchanged).
- Managed Conversation items remain the system of record; the BFF reads/appends,
  the container only generates output.

### Affected repositories

- `Azure/gpt-rag-ui` — thin **BFF** (`orchestrator_client.py`, `hosted_agent`
  path). **Owner of continuity**: authenticates the end user, binds conversation
  ownership (via the `delegated` asserted header once the environment evidence
  gate is met, or `capability` as fallback), reads managed-Conversation
  history, builds the complete bounded ordered stateless Responses input, calls
  the hosted agent, and appends the new turns to managed Conversations. Holds
  the only end-user token in the hosted path; owns the BFF endpoint-call
  identity that carries `Foundry Agent Consumer` + (in `delegated` mode) the
  custom `UserIdentityImpersonation` action, both at agent scope.
- `Azure/gpt-rag-orchestrator` — hosted-agent Responses v2 adapter. Reduced to
  **stateless generation**: consume the caller-supplied input items, run the
  turn, return output. **Removes** container-side managed-Conversations
  read/replay/append. Preserves the Toolbox/OBO retrieval path and the
  `POST /retrieve` fail-closed boundary unchanged. Never holds Conversations
  RBAC, a capability signing key, or the `UserIdentityImpersonation` action —
  those belong solely to the BFF's endpoint-call identity.
- `Azure/GPT-RAG` (this repo) — App Configuration contract (label `gpt-rag`),
  ADR record, and the `contracts/` continuity/owner-binding schema. Holds all
  **GPT-RAG-specific** history policy.
- `Azure/bicep-ptn-aiml-landing-zone` (**AILZ**) — generic landing-zone infra
  (consumed via the `infra/` submodule). Stays generic: it must **not** encode
  GPT-RAG history policy. Its only obligation here is to ensure the hosted-agent
  **container** identity carries **no** managed-Conversations data-plane role at
  all — no create, read, append, or delete, and no append-only or write-only
  variant either. Zero role, full stop; nothing is assumed or carved out. AILZ
  also provisions the custom `UserIdentityImpersonation` role definition as a
  generic, reusable Azure role artifact (no GPT-RAG-specific meaning encoded in
  the role itself) and assigns it, together with `Foundry Agent Consumer`, only
  to the **BFF's** endpoint-call identity, scoped narrowly at agent scope —
  never to the container. GPT-RAG-specific policy (which mode is active, when
  the gate flips) stays in GPT-RAG's App Configuration.

### Prioritized characteristics (measures)

1. **Security fail-closedness / authorization correctness** — no caller-ID-driven
   service read; no cross-user read; non-owner and missing return an
   indistinguishable 404; read/append failure fails closed (no fresh-thread
   masquerade). (Two-user negative tests.)
2. **Continuity durability** — a turn on logical conversation `C` returns prior
   context after the serving version/compute is replaced, with no gateway 404.
   (Binary pass/fail in the isolated topology.)
3. **Container history-blindness** — the hosted-agent identity holds no
   Conversations data-plane read role and cannot select server history. (RBAC
   assertion / infra review; stateless-input contract test.)
4. **Content confinement** — no Cosmos chat content in hosted/no-panel; any owner
   index stores metadata only. (Store-inspection tests.)
5. **Protocol interoperability & operability** — request/response conform to the
   Responses stateless input-items schema; continuity is independent of which
   version is serving and is rollback-safe behind one config switch.
   (Schema conformance + version-swap matrix.)

## Alternatives considered

### Option A: Keep top-level `conversation`; declare a platform blocker

Continue passing the top-level Responses `conversation` ID and document that
cross-version continuity is unsupported until Foundry changes gateway session
behavior.

- Benefits: zero code change; strictly uses the platform's canonical
  server-side threading; honest about the limitation.
- Costs and risks: **fails acceptance**. In the ADR-0001 model, update = new
  version, so every routine update breaks continuity with a raw 404. Users lose
  their thread on ordinary operations, not just incidents.
- Security and identity: unchanged.
- Operational consequences: hosted/no-panel is effectively single-version-only
  for continuity; incompatible with the supported update/rollback path.
- Component compatibility: no change.
- Reversibility: n/a (no change).

### Option B: Container-side replay keyed by a caller-supplied logical Conversation ID (WITHDRAWN — security-invalid)

Carry a stable logical managed-Conversation ID in Responses **request metadata**
and have the **hosted agent container** validate it, read prior items from
managed Conversations, replay them as input, run the turn, and append the new
items — all inside the container using the container/service identity.

- **Rejected on security grounds (confused-deputy / BOLA / IDOR).** The gateway
  strips `Authorization`, so the container has no user token; its
  managed-Conversations read is necessarily a **service-identity** read. Driving
  that read from a **caller-selected** conversation ID lets any caller replay any
  other caller's history. This is the exact anti-pattern ADR-0004 Option C
  rejects.
- It also requires granting the container a managed-Conversations **read** role,
  breaking history-blindness.
- No append-only-that-cannot-read role is assumed to exist; even if it did, it
  would not make the caller-ID-driven **read** safe.
- **Explicit rejection of container replay:** the hosted container must never
  read or select server-side history. Withdrawn; retained here only to record the
  correction.

### Option C: BFF-mediated stateless replay with owner-bound history (chosen)

Move all authorized managed-Conversation **create/read/append/delete** into the
authenticated **gpt-rag-ui BFF**, and make the hosted container **stateless and
history-blind**. Each turn:

1. The BFF **authenticates the end user** (it holds the Entra token) and
   **binds conversation ownership** for the logical conversation **before any
   read**. Ownership is enforced by the mechanism selected under OQ-OWN:
   **`delegated`** (**chosen/default** once the environment evidence gate
   confirms protocol + RBAC — native, per-user platform enforcement via a
   BFF-asserted `x-ms-user-identity` header derived server-side from the
   validated `oid`; see "Delegated header mechanism" below). Until that gate
   passes, hosted continuity stays **off** and this path **fails closed with
   503** — the BFF auto-engages **no** mechanism. As an **optional,
   disabled-by-default** alternative an operator may **explicitly** select
   **`capability`** (never auto-engaged, never the required primary —
   **store-free**: a server-issued, signed, opaque, owner-bound capability
   whose embedded `oid` the BFF re-checks against the live token before any
   read; works in **hosted/no-panel with zero Cosmos**). A raw caller-selected
   ID is never accepted under either mechanism. Non-owner, forged/expired capability, bad/missing header, and
   missing all return an **indistinguishable 404**. (The panel-only **owner
   index** in Cosmos is used solely for cross-conversation *enumeration* when
   the panel is deployed; it is **not** the continuity binding.)
2. On an owner hit, the BFF **reads** the ordered managed-Conversation items and
   builds the **complete, bounded, ordered, stateless Responses input** (bounded
   by an explicit history policy). A read failure **fails closed** (error to the
   user) and must **not** silently start a fresh thread.
3. The BFF calls the hosted agent with a **fresh `/responses` request** carrying
   the full input items — **no** top-level `conversation` param and **no**
   `previous_response_id`. The gateway performs no version-bound pre-routing and
   cannot 404 on a stale session.
4. The **container generates output statelessly** and returns it. It performs
   **no** read, replay, or persist.
5. The BFF **appends** the new user and assistant turns to managed Conversations
   (the SoR), using an **idempotent client turn ID**, under a **one-in-flight-turn
   per conversation** constraint initially. An append failure **fails closed**;
   the turn is not reported as durably persisted.

- Benefits: eliminates the confused-deputy path (no caller-ID-driven service
  read; ownership bound where the user token exists); continuity depends only on
  the durable store, which survives version/compute replacement (proven); keeps
  managed Conversations as SoR; no Cosmos chat content; container stays
  history-blind and stateless; consistent with ADR-0004.
- Costs and risks: the BFF owns threading mechanics (owner-binding, read, bounded
  replay, append), concurrency/idempotency, and a bounded-history policy. Full
  input per turn costs tokens/latency and needs explicit truncation or
  summarization. In `delegated` mode the BFF must derive `x-ms-user-identity`
  **server-side only** from the validated `oid` and never accept it from the
  client; the asserted identity is middle-tier-asserted, not cryptographically
  proven by the platform, so the BFF remains the trust boundary. **Both modes
  require the same signing-key infrastructure** (key in Key Vault, rotation via
  key version, short TTL with rolling re-mint; no fine-grained per-handle
  revocation in no-panel): in `capability` mode the BFF signs/verifies the full
  owner-bound capability (locator + `oid` claim, `oid` re-checked against the
  live token); in `delegated` mode the BFF signs/verifies the same locator
  shape **without** the `oid` claim/re-check, relying on the Foundry platform's
  own per-request identity enforcement for authorization instead. The
  panel-only owner index, when present, is metadata-only and must stay
  consistent with the SoR (worst case: a 404 or a stale list row, never content
  disclosure).
- Security and identity: **three concerns kept separate** — (a) **history
  ownership** enforced by the BFF before any read (via `delegated` header or
  `capability`); (b) **delegated OBO/Toolbox retrieval authorization**
  (document-level trimming) carried to Search via the existing passthrough,
  unchanged and independent of history ownership; (c) the **identity
  authenticating the Foundry `/responses` endpoint call** — the BFF's own
  narrowly-scoped service identity (`Foundry Agent Consumer` +, in `delegated`
  mode, the custom `UserIdentityImpersonation` action, both at agent scope).
  Carried user context (b) is never conflated with the endpoint-call identity
  (c); the endpoint-call identity (c) is never itself treated as a
  history-ownership claim (a) — ownership is the *asserted* `x-ms-user-identity`
  value, which the BFF derives solely from (1) the validated `oid`, never from
  the client.
- **Residual risk (platform session-join, live-tested):** the platform allows
  a request asserting a *different* `x-ms-user-identity` to **enter** (join) a
  session the BFF's identity created for another user, even though it still
  **fences** that session's response chain and `get_history` per asserted
  identity. Session **membership** is therefore not a security boundary. The
  container is unaffected (it is stateless and holds no data), but this ADR's
  invariant is stated explicitly: **never store unpartitioned container/session
  -keyed data** — any future container- or downstream-side state must be
  partitioned per user, never keyed by session/agent-thread ID alone.
- Operational consequences: continuity is independent of the serving version;
  rollback-safe; matches the immutable-version model; **no new always-on compute
  and no store in hosted/no-panel** (continuity uses the store-free capability;
  the owner index exists only when the panel/Cosmos is deployed, for enumeration).
- Component compatibility: coordinated change across gpt-rag-ui (BFF owner) and
  gpt-rag-orchestrator (adapter reduced to stateless generation); one App
  Configuration selector and one `contracts/` schema in Azure/GPT-RAG; AILZ stays
  generic.
- Reversibility: single App Configuration switch; when continuity is off, the
  path degrades to safe **single-turn stateless** behavior, never to an
  unauthorized read.

#### Delegated header mechanism (native, chosen/default post-gate)

Live evidence
([`gpt-rag#591` evidence comment](https://github.com/Azure/GPT-RAG/issues/591#issuecomment-5212288245),
[cleanup proof](https://github.com/Azure/GPT-RAG/issues/591#issuecomment-5212334345))
resolves OQ-OWN for the hosted-continuity call path. The mechanism:

- **Protocol requirement:** the hosted agent must run container protocol
  **`responses` 2.0.0**. Per-user response-chain/`get_history` fencing was
  proven only on this protocol version; no other version is assumed to carry
  the same guarantee.
- **Header:** the BFF asserts `x-ms-user-identity` on its call to the Foundry
  `/responses`/Conversations endpoints, derived **server-side only** from the
  end user's Entra token `oid` **after** the BFF validates that token. The BFF
  **never** accepts this header, or the `oid` it is derived from, as a
  client-supplied value; a client-supplied `x-ms-user-identity`-shaped header
  is stripped/ignored before the BFF's own value is set.
- **Conversation locator (unchanged shape across mechanisms):** the header
  authorizes the *read*; it does not tell the BFF *which* managed Conversation
  to read. The client-held reference to `conversation_resource_id` is still a
  **BFF-issued opaque locator handle** in both modes — never the raw resource
  ID, never self-authorizing, never client-constructed. In `capability` mode
  this handle **is** the signed capability (locator + `oid`-bound authorization
  combined, per the Decision above). In `delegated` mode the BFF mints a
  **structurally identical signed, opaque locator** (same signing-key
  infrastructure and `{conversation_resource_id, issued_at, expiry, key_id}`
  shape as the capability) but **omits the `oid` claim and the BFF-side `oid`
  equality re-check** — the signature exists only to make the locator
  tamper-evident and non-guessable (a client cannot construct or mutate one),
  not to authorize the read. Authorization of *who* may resolve that locator is
  performed once, per request, by the Foundry platform itself: it evaluates
  the presented `conversation_resource_id` together with the live-derived
  `x-ms-user-identity` header and returns the **platform's own 404** if they
  don't match the identity that owns the target conversation, rather than a
  BFF-side signature/`oid` mismatch. The handle is stored client-side
  identically in both modes (see ADR-0004's `OQ-611-CAP` for the
  persistence-surface question), and switching between modes at the
  environment evidence gate does not change how or where the client holds it
  — only whether the BFF also re-checks `oid` before trusting it.
- **RBAC:** the BFF's own service identity (or a dedicated middle-tier
  identity it controls) authenticates the endpoint call and must hold **only**
  `Foundry Agent Consumer` (interact data action) plus the custom
  **`UserIdentityImpersonation`** data action, both scoped **narrowly at agent
  scope** — no broader project/account-scope Foundry role. No built-in role
  includes `UserIdentityImpersonation`; it is a custom role definition
  provisioned by infra/AILZ. `Foundry Agent Consumer` alone (without the
  impersonation action) can still invoke the endpoint but is confirmed
  **narrow**: it cannot read, enumerate, or delete another identity's sessions
  or responses.
- **Enforcement observed:** a request asserting one `x-ms-user-identity`
  cannot continue another identity's response chain via `previous_response_id`
  (404), cannot read another identity's stored response (404), and — even from
  **inside** a session another identity's request created and this identity
  was allowed to **enter** — still cannot continue that session's response
  chain (404). See the residual-risk bullet above for the session-join
  implication.
- **Environment evidence gate:** `delegated` is the **chosen/default** owner-
  binding mechanism, but it only actually engages once **environment evidence**
  confirms, for the specific deployment: (1) the target hosted agent runs
  protocol `responses` >= 2.0.0, and (2) the BFF's endpoint-call identity holds
  exactly the narrow RBAC shape above (`Foundry Agent Consumer` + custom
  `UserIdentityImpersonation` at agent scope, no broader Foundry role). Until
  **both** are confirmed, hosted multi-turn continuity stays **off** and the
  continuity path **fails closed with 503** — the BFF auto-engages **no**
  mechanism and **never** fails open to an unbound/unauthenticated read.
  `capability` is available only if an operator **explicitly** selects it
  (disabled by default; never auto-engaged; not the required primary). This
  gate is an environment/deploy-time confirmation, not a requirement to repeat
  the full live two-identity experiment per deployment.
- **Unaffected invariants:** the container remains **stateless with zero
  Conversations RBAC** — the impersonation/consumer RBAC belongs to the BFF's
  endpoint-call identity, never the container/hosted-agent identity, which has
  no visibility into the header. Downstream OBO/Toolbox retrieval authorization
  (document-level trimming, INV-002) is **unchanged and independent** of this
  mechanism. **Cross-version stateless replay is unchanged**: `delegated`
  changes only how the per-turn **read is authorized**; it does **not**
  reintroduce reliance on the top-level `conversation` param or
  `previous_response_id` for continuity across version/compute replacement,
  because that routing **remains version-bound** (unaffected by this
  evidence) — the BFF still assembles a fresh, complete, bounded, stateless
  input every turn per steps 2–3 above.
- **Scope of this evidence:** this resolves the owner-binding mechanism for
  the hosted-continuity call path only. It does not resolve issue #591's
  separate, still-open document-level-authorization question (retrieval/Toolbox
  trimming), and it does not, by itself, resolve ADR-0004's independent panel
  enumeration/read gate (`PANEL_HISTORY_OWNER_BINDING_VALIDATED`), which
  requires its own live evidence for its own exact call path.

### Option D: BFF/gateway detects version change and mints a new platform conversation, linking/replaying managed history

Keep the top-level `conversation` for within-version continuity; on detecting a
version change (or a 404), the BFF creates a **new** platform conversation,
replays managed history into it, and maintains a logical→(version, platform
conversation) mapping.

- Benefits: retains the platform's server-side auto-threading within a version.
- Costs and risks: highest complexity. The BFF must reliably detect version
  changes, own extra mapping state, and recover from 404 mid-conversation.
  Still depends on the fragile version-bound session for the common path.
  Concurrent turns during a version swap create races and duplicate/interleaved
  platform conversations. More moving parts on a preview control-plane behavior.
- Security and identity: unchanged, but the added BFF state widens surface.
- Operational consequences: 404-driven recovery is user-visible latency/retry;
  hard to test deterministically against a preview platform.
- Component compatibility: heavier BFF change; adds durable mapping state to a
  component ADR-0001 wants thin.
- Reversibility: moderate; the mapping/recovery logic is not a single switch.

### Option E: `previous_response_id` (or another official lifecycle pointer)

Chain turns with `previous_response_id` referencing the prior `resp_...`.

- Benefits: canonical chaining primitive.
- Costs and risks: same class of failure as Option A. `previous_response_id`
  points to a response object served by a version/session; it is expected to be
  version/compute-bound and does not reference the managed Conversation SoR.
  Does not solve cross-version continuity and arguably worsens SoR alignment.
- Security/operational/compatibility/reversibility: no advantage over A/C.

### Do not change (Option F)

- Benefits: none beyond deferral.
- Costs and risks: ships a hosted/no-panel experience that loses the thread on
  every routine version update; fails acceptance; erodes trust in the mode.

## Decision

Adopt **Option C**. Hosted-mode multi-turn continuity is **BFF-mediated,
owner-bound, and stateless at the container**. The authenticated **gpt-rag-ui
BFF** owns authorized managed-Conversation **create/read/append/delete**: it
authenticates the end user, binds conversation ownership before any read, reads
the ordered items from **Foundry managed Conversations (system of record)**,
builds the **complete, bounded, ordered, stateless Responses input**, calls the
hosted agent with a fresh `/responses` request (no top-level `conversation`, no
`previous_response_id`), and appends the new turns back to managed Conversations.
The **hosted container is history-blind and stateless**: it holds **zero**
managed-Conversations data-plane RBAC and only generates output from the input it
is given. **Container-side replay and any caller-ID-driven service read are
prohibited (Option B withdrawn).**

The **owner-binding mechanism is a selector** consistent with ADR-0004. Live
OQ-OWN evidence (issue #591) resolves the hosted-continuity call path, so the
selector defaults to the **native, chosen** `delegated` mechanism, which
engages only once an environment evidence gate confirms protocol + RBAC. Until
that gate passes, continuity stays **off** and the path **fails closed with
503**; the store-free `capability` mechanism is retained as an **optional,
disabled-by-default** fallback an operator may **explicitly** select (never
auto-engaged, never the required primary):

- `delegated` (**chosen/default, post-gate**): native per-user enforcement via
  a BFF-asserted `x-ms-user-identity` header, derived server-side from the
  validated `oid`, on a hosted agent running container protocol `responses`
  2.0.0, with the BFF's endpoint-call identity holding narrowly-scoped RBAC
  (`Foundry Agent Consumer` + the custom `UserIdentityImpersonation` action, at
  agent scope). Live evidence
  ([`gpt-rag#591`](https://github.com/Azure/GPT-RAG/issues/591#issuecomment-5212288245))
  proves per-user response-chain/`get_history` enforcement for this exact call
  path. Engages automatically once the environment evidence gate (protocol +
  RBAC confirmed) is `true` for the deployment; see "Delegated header
  mechanism" above for the full mechanism, residual-trust caveats, and scope
  limits.
- `capability` (**optional, disabled-by-default fallback**): a server-issued,
  signed, opaque, owner-bound capability minted by the BFF from the validated
  user `oid` (`{oid, conversation_resource_id, issued_at, expiry, key_id}`).
  The BFF re-checks the capability `oid` against the live token before any
  read. Requires **no store** (signing key in Key Vault, provisioned like
  `AUDIT-HMAC-KEY`), so it works in **hosted/no-panel with zero Cosmos**.
  **Disabled by default and never auto-engaged**; an operator must
  **explicitly** select it. It remains fully specified and available as an
  optional rollback/defense-in-depth option even after `delegated` is chosen,
  but pre-gate the default behavior is a fail-closed **503**, not silent
  capability activation.

A raw caller-selected conversation ID is **never** accepted as a read key. The
panel-only **owner index** (Cosmos) exists solely for cross-conversation
**enumeration** when the panel is deployed and stores **only** owner-binding
metadata (principal ID, conversation ID, title, timestamps) — **never** message
content. No Cosmos chat content exists in hosted/no-panel.

### Identity separation (non-negotiable)

Three distinct identities/authorizations must not be conflated:

1. **History ownership** — enforced by the BFF against the authenticated end user
   before any read; non-owner and missing both return **404**. Under
   `delegated`, the ownership *signal* is the `x-ms-user-identity` value, which
   the BFF derives **solely** from this validated identity, never from the
   client.
2. **Delegated OBO/Toolbox retrieval authorization** — the user context carried
   to Foundry IQ/Search for native document-level trimming (ADR-0001 target
   path). Unchanged by this ADR and independent of history ownership.
3. **Foundry `/responses` endpoint-call identity** — the credential that
   authenticates the BFF→gateway call. In `delegated` mode this is the BFF's
   own narrowly-scoped service identity (`Foundry Agent Consumer` + the custom
   `UserIdentityImpersonation` action, at agent scope). It is never treated as,
   or derived from, the carried user context (2), and is never itself a
   history-ownership claim (1) — it only carries the asserted identity that (1)
   supplies.

**Never store unpartitioned container/session-keyed data.** Live evidence
shows the platform fences the response chain/`get_history` per asserted
identity but does **not** fence session **membership** itself (a differently
asserted identity can enter a session another identity's request created). The
container is stateless today and holds no data, so this is a forward-looking
invariant: any future container- or downstream-side state must be partitioned
per user, never keyed by session/agent-thread ID alone.

### App Configuration contract (label `gpt-rag`, owned by Azure/GPT-RAG)

Defaults preserve safe behavior; enabling requires explicit evidence gates.
These align with ADR-0004's panel keys and the `POST /retrieve` idiom.

- `HOSTED_CONTINUITY_ENABLED` (default `false`) — when `false`, the hosted path
  is **single-turn stateless** (no server history, safe). When `true`, the BFF
  performs owner-bound read + bounded replay + append **only** if the selected
  binding is active (`delegated` with its gate met, or an explicit `capability`
  opt-in); otherwise the continuity path fails closed with **503** (no
  auto-fallback).
- `HOSTED_CONVERSATION_OWNER_BINDING` (default `delegated`; explicit opt-in alt
  `capability`) — selects the owner-binding mechanism. `delegated` only
  actually engages once the environment evidence gate is `true` for the
  deployment; until then, the continuity path **fails closed with 503** and the
  BFF auto-engages **nothing**. `capability` is used **only** when an operator
  explicitly sets this key to `capability` (disabled by default; never
  auto-selected). Same key as ADR-0004.
- `HOSTED_CONVERSATION_CAPABILITY_KEY` / `HOSTED_CONVERSATION_CAPABILITY_KEY_ID` /
  `HOSTED_CONVERSATION_CAPABILITY_TTL_SECONDS` — Key Vault-referenced signing key
  (provisioned like `AUDIT-HMAC-KEY`), active key version for rotation, and
  capability lifetime with rolling re-mint. Present in **all** modes (fallback
  and defense-in-depth); no store.
- `HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED` (default `false`) — the
  **environment evidence gate**: confirms, for this deployment, that (1) the
  target hosted agent runs container protocol `responses` 2.0.0, and (2) the
  BFF's endpoint-call identity holds exactly `Foundry Agent Consumer` + the
  custom `UserIdentityImpersonation` action at agent scope (no broader Foundry
  role). This mirrors `HOSTED_RETRIEVAL_INV_002_VALIDATED`'s pattern but checks
  protocol/RBAC shape rather than repeating the live two-identity experiment
  per deployment (that experiment is recorded once, in `gpt-rag#591`).
  Continuity stays **off** and the continuity path **returns 503** unless this
  is `true` (with `delegated` selected); it does **not** silently fall back to
  `capability`. An operator wanting pre-gate continuity must **explicitly** set
  `HOSTED_CONVERSATION_OWNER_BINDING=capability`.
- `HOSTED_CONVERSATION_PROTOCOL_VERSION` (expected `responses/2.0.0`) —
  records/asserts the hosted agent's container protocol version; part of the
  environment evidence gate check in (1) above.
- `HOSTED_CONVERSATIONS_TOKEN_AUDIENCE` — managed-Conversations query-token
  audience for `delegated` mode (analogous to `HOSTED_RETRIEVAL_TOKEN_AUDIENCE`);
  required only when `delegated`.
- `HOSTED_HISTORY_MAX_ITEMS` / `HOSTED_HISTORY_MAX_TOKENS` — explicit bounded
  history policy for the replayed input.
- `HOSTED_HISTORY_TRUNCATION` (default `drop_oldest`; alt `summarize`) — bound
  strategy when the policy limit is exceeded.

If a typed field is warranted (the continuity/capability envelope), it is added
under `contracts/` and byte-pinned like `audit-event-v1`. **AILZ carries no
GPT-RAG history policy**; it only guarantees the container identity holds no
Conversations read/write role and no capability signing key, and that the
custom `UserIdentityImpersonation` role definition (when provisioned) is
assignable only at agent scope, never to the container/hosted-agent identity.

### Honest scope statement (protocol vs. continuity)

We do **not** invent a platform contract. In the current Foundry preview you
cannot simultaneously have (a) reliance on the platform's server-side
`conversation` / `previous_response_id` session threading and (b) stable
continuity across the platform's own immutable-version replacement. Therefore:

- **Preserved and canonical:** the Responses **request/response wire contract**,
  specifically the stateless "caller supplies input items" mode, which is a
  supported canonical usage of Responses. Interoperability of the message shape
  is intact.
- **Explicitly out of supported scope (preview / platform-limited):** durable
  cross-version continuity via the platform's server-side stateful
  `conversation` auto-loading and `previous_response_id` chaining. These are
  documented as **not durable across immutable-version replacement** and are not
  the GPT-RAG continuity mechanism.
- **Explicitly rejected:** container-side history read/replay of any kind, and
  any service-identity read driven by a caller-selected conversation ID.

## Consequences

### Positive

- No confused-deputy/BOLA path: the container never reads history, and no
  caller-selected ID ever drives a service-identity read.
- Continuity survives compute/version replacement and rollback, matching the
  ADR-0001 update model, because it depends only on the durable SoR.
- Managed Conversations stays the single system of record; the BFF reads/appends,
  the container only generates; no Cosmos chat content in hosted/no-panel.
- History ownership, delegated retrieval authorization, and endpoint-call
  identity remain cleanly separated; INV-002 / `POST /retrieve` untouched.
- **OQ-OWN resolved for this call path**: live evidence (`gpt-rag#591`) proves
  native per-user enforcement via the delegated header on protocol `responses`
  2.0.0. `delegated` ships as the **chosen/default** mechanism, engaging once
  the environment evidence gate confirms protocol + RBAC; until then continuity
  **fails closed with 503**. **Store-free `capability`** remains fully specified
  as an **optional, disabled-by-default** rollback/opt-in fallback (never
  auto-engaged). Reversible behind one App Configuration switch either way.

### Negative or accepted

- The BFF owns threading mechanics (owner-binding, read, bounded replay, append),
  concurrency/idempotency, and the bounded-history policy — more logic in a
  component ADR-0001 wants thin.
- Per-turn token/latency cost of sending full bounded input; requires the
  explicit truncation/summarization bound.
- In `delegated` mode, the asserted `x-ms-user-identity` is middle-tier-asserted,
  not cryptographically proven by the platform — the BFF must derive it
  server-side only, never from the client, and remains the trust boundary. The
  platform's session-**membership** fencing is weaker than its response-chain
  fencing (live-tested); this ADR's invariant against storing unpartitioned
  container/session-keyed data addresses that gap.
- In `capability` mode (fallback) the BFF signs/verifies a store-free capability
  (Key Vault-backed key, rotation via key version, short TTL + rolling re-mint);
  no fine-grained per-capability revocation in no-panel (bounded by TTL +
  rotation). The panel-only owner index, when present, is metadata-only and
  must stay consistent with the SoR (at worst a 404 or stale list row, never
  content disclosure).
- Gives up the platform's server-side auto-threading convenience while the
  preview limitation stands; cross-version stateless replay is required
  regardless of owner-binding mechanism, because `previous_response_id`/session
  routing remains version-bound.
- Reconciled with ADR-0004: managed-Conversation create/read/append/delete and
  ownership belong to the **BFF**, not the container; the container is stateless
  with zero Conversations RBAC and no signing key — unaffected by the
  delegated-header mechanism, whose RBAC belongs solely to the BFF's
  endpoint-call identity.

## Adoption and migration

Coordinated, ordered change (compatible-commit discipline per AGENTS.md):

1. **Azure/GPT-RAG** — freeze the App Configuration contract (label `gpt-rag`):
   add `HOSTED_CONTINUITY_ENABLED`, `HOSTED_CONVERSATION_OWNER_BINDING`,
   `HOSTED_CONVERSATION_CAPABILITY_KEY` (Key Vault ref, provisioned like
   `AUDIT-HMAC-KEY`), `HOSTED_CONVERSATION_CAPABILITY_KEY_ID`,
   `HOSTED_CONVERSATION_CAPABILITY_TTL_SECONDS`,
   `HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED`,
   `HOSTED_CONVERSATION_PROTOCOL_VERSION`,
   `HOSTED_CONVERSATIONS_TOKEN_AUDIENCE`, `HOSTED_HISTORY_MAX_ITEMS`,
   `HOSTED_HISTORY_MAX_TOKENS`, `HOSTED_HISTORY_TRUNCATION`, all defaulting to the
   safe pre-gate state (continuity off; `delegated` selector present but
   inactive until its validation gate is `true`; **no auto-fallback** — the
   continuity path returns **503** until the gate passes or an operator
   **explicitly** opts into `capability`). Add the `contracts/`
   continuity/capability envelope schema
   + `.sha256` if a typed field is warranted. Publish this ADR. No runtime
   behavior change yet.
2. **gpt-rag-orchestrator** — reduce the hosted-agent Responses v2 adapter to
   **stateless generation**: consume the caller-supplied bounded ordered input
   items and return output. **Remove** any container-side managed-Conversations
   read/replay/append and any dependency on the top-level `conversation` /
   `previous_response_id` for continuity. Emit `audit-event-v1` for
   turn-generated and legacy-404-detected (metadata only). No Conversations
   read/write role, no capability signing key, and no `UserIdentityImpersonation`
   RBAC on the container identity — that RBAC belongs only to the BFF's
   endpoint-call identity.
3. **gpt-rag-ui** — in the `hosted_agent` BFF path: authenticate the end user;
   bind conversation ownership before any read via the selected mechanism
   (`delegated` — assert `x-ms-user-identity` derived server-side from the
   validated `oid`, never from the client; or `capability` fallback — mint on
   create, verify signature + expiry + `oid` equality); read ordered items from
   managed Conversations; build the complete bounded ordered stateless Responses
   input; call the hosted agent with a fresh `/responses` request (no top-level
   `conversation`, no `previous_response_id`); append the new user/assistant turns
   to managed Conversations with an idempotent client turn ID; enforce one
   in-flight turn per conversation; re-mint a fresh capability on success when in
   `capability` mode; fail closed on read or append failure (no fresh-thread
   masquerade). Non-owner, forged/expired capability, bad/missing header, and
   missing → 404.
4. **AILZ (`bicep-ptn-aiml-landing-zone`)** — no GPT-RAG history policy. Confirm
   (infra/RBAC review) the hosted-agent/container identity carries **no**
   managed-Conversations data-plane read/write role, **no** capability signing
   key, and **no** `UserIdentityImpersonation` action; provision the custom
   `UserIdentityImpersonation` role definition and assign it, together with
   `Foundry Agent Consumer`, only to the **BFF's endpoint-call identity**, scoped
   narrowly at **agent scope**.
5. Revalidate in both topology classes (Basic and network-isolated with private
   endpoints/private ACR), run the negative security suite (below) **including
   no-panel/zero-Cosmos continuity and the delegated-header tests**, then update
   `manifest.json` pins for gpt-rag-orchestrator and gpt-rag-ui together.

Migration boundaries: no backfill required. Existing managed-Conversation items
are read by the BFF via owner-bound lookup; only the read/append **owner** and
the routing mechanism change. Classic mode is unaffected. Before the
environment evidence gate is met, hosted continuity is **off** (the path
returns **503**) unless an operator has **explicitly** opted into `capability`;
in `capability` mode a conversation without a live capability (e.g.,
browser/session loss in no-panel) starts fresh — an accepted, safe default (no
content disclosure); the optional panel adds enumeration-based recovery.
Backfill of panel owner-index rows, if desired, is a separate metadata-only
migration.

Rollback: flip `HOSTED_CONTINUITY_ENABLED` off (path degrades to safe single-turn
stateless), or flip `HOSTED_CONVERSATION_OWNER_BINDING` back to `capability`,
and revert the coordinated manifest pin. Because managed Conversations is SoR,
the capability is stateless, and any owner index is metadata only, no
chat-content migration is needed either direction; rotating
`HOSTED_CONVERSATION_CAPABILITY_KEY_ID` invalidates outstanding capabilities and
owner-index rows can be dropped.

## Negative security tests (must pass before enable)

- **NST-1 Cross-user read (BOLA/IDOR):** user B requests continuity/history on
  user A's conversation ID → **404**, indistinguishable from a missing ID; no
  managed-Conversations read is issued on A's items. (Reuses the INV-002 two-user
  harness.)
- **NST-2 No container read path:** infra/RBAC assertion that the hosted-agent
  identity has **no** Conversations data-plane read/list/append role; a wire test
  asserts the container receives only caller-supplied input and issues no
  Conversations read.
- **NST-3 No caller-ID-driven service read:** any code path where a caller-supplied
  conversation ID reaches a service-identity Conversations read without a prior
  owner hit is a failing test (static + integration).
- **NST-4 Fail-closed on read/append failure:** injected read failure and injected
  append failure each return an error and do **not** start a fresh thread or
  stream a success-shaped completion.
- **NST-5 Fail-closed when gate unmet (no auto-fallback):** with
  `HOSTED_CONVERSATION_OWNER_BINDING=delegated` but
  `HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED=false`, the continuity path
  **fails closed with 503** — it does **not** perform a native delegated read,
  does **not** auto-engage `capability`, never fails open, and never issues a
  bare service read. `capability` runs **only** when an operator explicitly
  sets `HOSTED_CONVERSATION_OWNER_BINDING=capability`, and even then never a
  bare service read.
- **NST-6 No content leakage to Cosmos/telemetry:** after turns, assert no message
  body or document content in Cosmos (owner index metadata only) or in
  `audit-event-v1`.
- **NST-7 Capability forgery/theft/replay:** a capability with a bad signature,
  expired TTL, retired `key_id`, or `oid` not matching the live token → **404**
  (uniform with missing); a stolen capability presented without the matching
  authenticated `oid` token is rejected; rotating `..._KEY_ID` invalidates all
  outstanding capabilities.
- **NST-8 No-panel/zero-Cosmos continuity:** with the panel undeployed and no
  Cosmos, a multi-turn conversation stays continuous within TTL using the
  active owner-binding mechanism alone; no owner index or Cosmos client is
  instantiated.
- **NST-9 Header spoofing rejected:** a client-supplied `x-ms-user-identity`
  value is stripped/ignored by the BFF; only the server-derived value (from the
  validated `oid`) is ever forwarded — a wire/contract test asserts the BFF
  never forwards a client-controlled header value verbatim.
- **NST-10 Cross-user response-chain/read 404 in `delegated` mode:** user B's
  `previous_response_id` continuation or stored-response read against user A's
  response/session → **404**, indistinguishable from missing (reuses the
  `gpt-rag#591` two-identity harness for this exact call path).
- **NST-11 Session-join does not leak response chain/history:** an asserted
  identity that is allowed to enter/join a session created by a different
  asserted identity's request still receives **404** on that session's
  response chain and `get_history` — session **membership** is not a
  substitute for response-chain ownership.
- **NST-12 RBAC narrowness / impersonation required:** `Foundry Agent Consumer`
  alone (without the custom `UserIdentityImpersonation` action) is insufficient
  for the BFF's endpoint-call identity to assert `x-ms-user-identity`; a call
  that omits the impersonation grant, or omits the asserted-identity header on a
  delegated session, is rejected with **403** (live evidence: no-impersonation
  header → 403; a non-delegated request into a delegated session → 403). An
  infra/RBAC assertion confirms no built-in Foundry role includes the
  impersonation action and that it is assigned only at agent scope.

## Operational behaviors

- **Concurrency:** one in-flight turn per conversation initially; concurrent turns
  are serialized or rejected deterministically.
- **Idempotency:** client turn IDs deduplicate retried appends; a retry never
  double-appends.
- **Bounded history:** replay is bounded by `HOSTED_HISTORY_MAX_ITEMS` /
  `HOSTED_HISTORY_MAX_TOKENS` with `HOSTED_HISTORY_TRUNCATION`; policy is explicit
  and observable.
- **Failure semantics:** read failure and append failure both fail closed;
  gateway 404 on a stale session cannot occur (no top-level `conversation`).
- **Telemetry:** `audit-event-v1` records owner-bind result, read, append,
  turn-generated, and legacy-404-detected — **metadata only**, correlation IDs
  only, no conversation body or document content.

## Compliance verification (fitness functions)

- **FF-1 Continuity across replacement:** turn on version A, replace with a new
  immutable digest (version B), then a turn on the same logical conversation
  returns prior context with **no gateway 404**; repeat after rolling back to A.
  Automated integration test in the isolated topology.
- **FF-2 No version-bound session dependency:** contract/wire test asserts the BFF
  sends the full stateless input and **never** the top-level `conversation`
  parameter or `previous_response_id` for continuity — unaffected by owner-binding
  mechanism, preserving cross-version stateless replay in both `delegated` and
  `capability` modes.
- **FF-3 History-blind stateless container:** RBAC assertion that the hosted-agent
  identity holds no Conversations data-plane role; wire test asserts the container
  issues no read/append and only generates from supplied input.
- **FF-4 Owner gate before read:** a `(caller, conversation_id)` with no valid
  owner binding (no capability match / signature / `oid` equality / valid
  asserted header) returns **404**; a caller ID never reaches a
  managed-Conversations read without a prior owner-binding validation.
- **FF-5 Managed Conversations is SoR / no Cosmos chat:** after a turn, items are
  readable via the Conversations data API; hosted/no-panel constructs history
  solely from it; assert no Cosmos chat client is instantiated and any owner index
  holds metadata only.
- **FF-6 Fail-closed read/append:** read or append failure returns an error and
  does **not** start a fresh thread or stream a success-shaped completion.
- **FF-7 Concurrency & idempotency:** concurrent turns on one conversation yield
  deterministic ordering; a retried turn with the same client turn ID does not
  double-append.
- **FF-8 Retrieval identity preserved & separate:** reuse ADR-0001 INV-002
  two-user negative retrieval test; per-user/group trimming via Toolbox
  passthrough unchanged and independent of history ownership.
- **FF-9 Canonical wire conformance:** requests/responses validate against the
  Responses schema/SDK types (stateless input-items mode).
- **FF-10 Environment evidence gate is protocol+RBAC, not per-deploy pentest:**
  `HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED` flips to `true` only via an
  automatable check of (a) `HOSTED_CONVERSATION_PROTOCOL_VERSION` equals
  `responses/2.0.0` and (b) the BFF's endpoint-call identity's role
  assignments equal exactly `Foundry Agent Consumer` +
  `UserIdentityImpersonation` at agent scope — never a manual/undocumented
  toggle.
- **FF-11 Header derivation only:** static/contract test asserts every code
  path that sets `x-ms-user-identity` sources it from the BFF's own validated
  `oid`, never from a request header, query parameter, or body field supplied
  by the client.
- **FF-12 No session-keyed unpartitioned state (forward-looking):** static/code
  review gate — any new container-side or downstream cache/store introduced
  after this ADR must key exclusively by validated `oid` (or an
  `oid`-partitioned derivative), never by session/agent-thread ID alone; a
  lint/review checklist item blocks merging a session-ID-only cache key,
  consistent with the observed platform behavior that session **membership**
  is not fenced even though the response chain/history is.

## Documentation impact

Update the hosted-agent operator page on the `docs` branch: describe BFF-mediated
owner-bound continuity, the container's stateless/history-blind role, the
`delegated` (native header, chosen/default post-gate) vs `capability`
(store-free fallback) selector and its environment evidence gate, the
delegated-header derivation rule (server-side only, never from client) and its
RBAC requirement (`Foundry Agent Consumer` + custom `UserIdentityImpersonation`
at agent scope), the capability lifecycle (mint/verify/rotate/TTL), the
bounded-history policy and its App Configuration keys, the fail-closed
404/error semantics, and an explicit preview note that platform server-side
`conversation` / `previous_response_id` threading is not durable across version
replacement. Explicitly document that container-side history read/replay is
prohibited, and that session **membership** is not fenced by the platform even
though the response chain/history is — so no unpartitioned container/session
state may ever be stored.

## Review trigger

Reassess when any of the following occurs:

- **OQ-OWN resolved for this call path:** live evidence
  ([`gpt-rag#591`](https://github.com/Azure/GPT-RAG/issues/591#issuecomment-5212288245),
  cleanup:
  [comment](https://github.com/Azure/GPT-RAG/issues/591#issuecomment-5212334345))
  proves native per-user response-chain/`get_history` enforcement for the
  exact BFF/hosted-agent call path, on protocol `responses` 2.0.0, with the
  narrow `Foundry Agent Consumer` + custom `UserIdentityImpersonation` RBAC at
  agent scope. `delegated` is now the chosen/default mechanism once the
  environment evidence gate (protocol + RBAC confirmation) is met; `capability`
  remains the fallback. **Not automatically inherited by ADR-0004's panel-path
  gate** (`PANEL_HISTORY_OWNER_BINDING_VALIDATED`) — that gate requires its own
  independent confirmation for the panel's call shape, per the discipline that
  each call path needs its own live evidence.
- Foundry changes `/responses` gateway session/pre-routing so a top-level
  `conversation` survives immutable-version/compute replacement, or provides an
  official rebind/continuation lifecycle.
- Foundry changes managed-Conversations identity/RBAC, header propagation, ordering,
  optimistic concurrency, or `store` semantics affecting read/append design.
- Foundry changes the platform's session-membership fencing behavior (currently
  weaker than response-chain fencing per live evidence) — reassess the
  unpartitioned-storage prohibition if membership becomes fenced too.
- Hosted agents leave preview.
- Any NST or FF regresses in validation or production, or a security review reports
  a cross-user or service-identity read path.

## Open questions

- **OQ-OWN (RESOLVED for hosted-continuity call path):** does managed
  Conversations accept a delegated/asserted user identity and enforce
  per-user/owner authorization for the exact BFF↔hosted-agent call path?
  **Yes** — live two-identity experiment
  ([`gpt-rag#591`](https://github.com/Azure/GPT-RAG/issues/591#issuecomment-5212288245))
  confirms cross-user 404 on `previous_response_id` continuation and stored-response
  read, on protocol `responses` 2.0.0, with narrow `Foundry Agent Consumer` +
  custom `UserIdentityImpersonation` RBAC at agent scope. `delegated` is the
  chosen/default and engages once the environment evidence gate (protocol +
  RBAC) is met for the deployment; until then continuity **fails closed with
  503** (no auto-fallback). `capability` remains a fully-specified **optional,
  disabled-by-default** fallback an operator may explicitly select (zero Cosmos
  in no-panel either way). **Residual/still
  open:** (a) the asserted header is middle-tier-trusted, not
  cryptographically proven by the platform — treat as a residual-trust
  invariant, not a closed risk; (b) session **membership** is not fenced by the
  platform (a differently asserted identity can enter a session), motivating
  the new "never store unpartitioned container/session-keyed data" invariant;
  (c) this does **not** resolve issue #591's separate document-level-authorization
  question, and does **not** automatically resolve ADR-0004's independently-tracked
  panel enumeration/read gate.
- **OQ-1 (ordered read + concurrency):** confirm the managed-Conversations data
  API (used by the BFF, not the container) supports ordered read and an
  optimistic-concurrency / turn-sequence primitive sufficient for FF-7. If not,
  the single-active-turn constraint is the contract.
- **OQ-2 (double-store):** confirm the container's stateless generation with
  `store=false` on the response does not itself persist items, so the BFF is the
  sole append path and no double-store occurs.
- **OQ-3 (bounded-history policy):** finalize `HOSTED_HISTORY_MAX_ITEMS` /
  `HOSTED_HISTORY_MAX_TOKENS` defaults and truncation-vs-summarization ownership.
- **OQ-4 (owner stamp durability):** confirm the create path durably records the
  owner principal (and that it survives version replacement) so ownership is
  attributable without content inspection — shared with ADR-0004 OQ-611-OWNERSTAMP.
- **OQ-CAP (capability sufficiency):** confirm the signed capability envelope
  (`{oid, conversation_resource_id, issued_at, expiry, key_id}`) plus live-token
  `oid` equality is sufficient owner binding for reads/appends with no store, and
  finalize TTL/rotation defaults — shared with ADR-0004 OQ-611-CAP. Remains
  relevant as the fallback mechanism even after OQ-OWN resolution.
- **OQ-REVOKE (revocation granularity):** in no-panel there is no per-capability
  revocation (only TTL expiry + key rotation as bulk revocation); confirm this is
  acceptable or require the panel/owner-index for fine-grained revocation —
  shared with ADR-0004 OQ-611-REVOKE. Also applies to `delegated` mode: confirm
  whether the platform offers any session/response revocation primitive beyond
  the environment evidence gate flip.
- **OQ-7 (cancel/background lifecycle):** define cancel/partial-turn behavior;
  recommend synchronous streaming with completed-turn-only append for the first
  release, so a cancelled turn appends nothing.
