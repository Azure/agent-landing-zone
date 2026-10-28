# ADR-0004: Separate the handoff artifact commit from the comparison baselines in the parity dispatch

- Status: superseded by [ADR-0028](../../../docs/adr/ADR-0028-integrated-terraform-composition.md)
- Date: 2026-08-22
- Owners: AI Landing Zone maintainers and Terraform pattern-module maintainers
- Related context: issue #136 and Terraform pull request #170 (context, not review or approval evidence)
- Refines: [ADR-0003](./0003-repository-native-terraform-parity-coordination.md)

## Context

> Historical decision: external Terraform publication and its dispatch contract
> are retired. The original proposal below is retained for audit, not operator use.

ADR-0003 established a repository-native parity ledger and a bounded, identifier-only
`repository_dispatch` from this repository to the Terraform pattern-module repository. The consumer
retrieves the reviewed handoff record and its schema from this repository instead of receiving
content in the payload. That indirection only works when the payload names the commit that actually
contains those files.

The current contract does not name it, so no dispatch can succeed:

- `scripts/parity/Publish-TerraformHandoff.ps1` emits `sourceCommitSha` from `handoff.source.commitSha`,
  which `parity/config.json` pins to the released Bicep baseline `v2.6.1`
  (`64195c01b70974fa7256c2f54a0035fb06804139`). That commit predates the `parity/` tree and contains
  neither `parity/handoffs/**` nor `parity/schemas/terraform-handoff.schema.json`.
- The receiver in Terraform pull request #170 fetches `handoffPath` and
  `parity/schemas/terraform-handoff.schema.json` at `sourceCommitSha`, so every dispatch returns
  404 and the gap stays open. The failure is structural, not transient.
- Baseline provenance already carries `provenance.inventoryCommitSha`, proving the reviewed
  `parity/inventory.json` bytes. It is not a handoff artifact location: the inventory commit need not
  contain the handoff record, whose `approval` block is written later. Alignment-assessment
  provenance has no equivalent field at all, and its assessment record lives on the
  `terraform-parity-assessments` ledger branch rather than on `develop`.
- A handoff record cannot store the SHA of the commit that contains it, so the artifact location is
  necessarily discovered at publication time and can only live in the payload.
- The receiver additionally requires `targetCommitSha` to equal the current Terraform `main` head.
  The producer correctly sends the pinned comparison baseline `v0.5.1`
  (`abe337894f93de3ddda525ea44898b33e1484070`) while `main` has advanced to `5082af...`, so the
  check would keep failing even after the artifact-location defect is fixed. The two repositories
  disagree about what `targetCommitSha` means.

Affected contracts are the `repository_dispatch` payload, `scripts/parity/Publish-TerraformHandoff.ps1`,
`.github/workflows/terraform-parity-publish.yml`, the parity publication tests, and the receiving
workflow in the Terraform repository. No Azure resource, Bicep parameter, output, identity, RBAC,
network, or deployment behavior is involved.

## Prioritized characteristics

| Characteristic | Priority | Measure |
| --- | --- | --- |
| Traceability | 1 | Every dispatch names one artifact commit and two baseline commits, each resolvable without inferring one role from another |
| Evidence integrity | 2 | The consumer proves the fetched handoff bytes match the approved digest at the named commit; no silent fallback exists |
| Compatibility | 3 | `terraform-handoff.schema.json` and all five approved handoff records dispatch unchanged; payload version is negotiated explicitly, never guessed |
| Authorization | 4 | The artifact commit must be contained in an allow-listed source branch; unreachable, unreviewed, or out-of-tree paths are rejected |
| Recoverability | 5 | Reverting or disabling either side returns to a fail-closed state with the gap open and no Azure or consumer impact |

## Alternatives considered

### Option A: distinct `handoffCommitSha` artifact field with immutable baselines

Add artifact-location fields to the dispatch payload (`handoffCommitSha`, `handoffRef`,
`handoffDigest`, `handoffSchemaPath`) under an explicit `payloadVersion`. Keep `sourceCommitSha` and
`targetCommitSha` as immutable comparison baselines. The consumer fetches the handoff record and the
schema at `handoffCommitSha`, verifies the digest, verifies that the commit is contained in an
allow-listed source branch, and requires only that `targetCommitSha` resolves and is an ancestor of
the current target base-branch head before branching from that current head.

Benefits: each commit keeps exactly one meaning; the artifact commit is discovered from the trusted
publication checkout, so it is always a reviewed commit that contains both files; baselines stay
immutable, so the comparison evidence recorded in the inventory remains valid; the handoff record
schema is unchanged, so no approved record needs re-approval; the ancestor rule removes the
current-head coupling without pretending target drift does not exist.

Costs: five additional payload fields, a producer change with git verification, a receiver change,
and one coordinated adoption window in which explicit rejection replaces today's 404. Identity and
networking are unaffected. Reversal is a revert on either side; both directions fail closed.

### Option B: overload `inventoryCommitSha` or `sourceCommitSha`

Reuse an existing field as the fetch location.

Overloading `sourceCommitSha` destroys the comparison baseline: the payload would carry a moving
commit while the inventory, capability evidence paths, and every scenario assessment remain measured
at `v2.6.1`. Parity claims would no longer be reproducible.

Overloading `inventoryCommitSha` fails on availability and coverage. It exists only for
baseline-inventory provenance, so alignment-assessment handoffs — the entire ongoing workflow — would
still have no artifact location. It also asserts inventory-byte provenance; a commit that contains
the exact inventory bytes is not guaranteed to contain the later handoff record with its approval
block, so the receiver would 404 intermittently instead of deterministically. This option directly
contradicts the ADR-0003 rule that implementation and artifact commits are never inferred from one
another.

Cheaper in payload size only. Rejected on traceability and evidence integrity.

### Option C: auto-advance baselines or require current-head equality

Advance `parity/config.json` and the inventory to a commit that contains the parity assets, or keep
the receiver's `targetCommitSha == main` rule and have the producer send the current head.

Auto-advancing the source baseline invalidates every capability evidence path, scenario assessment,
and inventory digest at once, and turns a reviewed release-pinning decision into an automatic side
effect of a dispatch defect. Requiring target-head equality makes every dispatch a race against
unrelated merges in the Terraform repository: any merge between approval and dispatch fails the
publication, and re-approval loops would follow. Neither option restores a meaning for the artifact
commit; both weaken the immutability that makes parity claims auditable.

### Option E: send the full handoff record in the payload

Embedding the reviewed handoff JSON removes the fetch entirely. It also removes the immutable,
reviewed source of the instruction set: the consumer would trust dispatch-time content instead of
committed, reviewed bytes, the bounded identifier-only payload rule from ADR-0003 would be replaced
by a size limit that grows with every handoff, and the sensitive-content scan would become the only
boundary between a coding agent and arbitrary text. Rejected on evidence integrity and authorization.

### Do not change

Every dispatch continues to 404 in the consumer. No proposal is ever raised through the approved,
audited path, so either the gaps stay open indefinitely or maintainers work around the automation
with manual, unaudited pull requests. The mismatch is structural and does not resolve with time.

## Decision

Adopt Option A.

1. The dispatch payload gains an explicit `payloadVersion` of `2.0.0` and four artifact-location
   fields: `handoffCommitSha`, `handoffRef`, `handoffDigest`, and `handoffSchemaPath`.
2. Three commit roles are named and never inferred from one another:
   - *comparison baselines*: `sourceCommitSha` and `targetCommitSha`, immutable released commits
     from `parity/config.json`, used for comparison and evidence, allowed to predate `parity/`;
   - *artifact locations*: `handoffCommitSha` in this repository, plus the existing
     `inventoryCommitSha` for baseline provenance, which always contain the referenced bytes;
   - *current heads*: the target base-branch head, observed by the consumer at execution time and
     never carried in the payload.
3. The producer sets `handoffCommitSha` from the trusted publication checkout commit, verifies that
   the committed blob at that commit matches the validated handoff bytes, verifies that the schema
   file exists at that commit, and fails explicitly rather than falling back to any other commit.
4. The consumer fetches the handoff record and the handoff schema at `handoffCommitSha` only,
   verifies `handoffDigest`, verifies that `handoffCommitSha` is contained in the configured source
   integration branch (`develop`), and validates the record against the schema retrieved from the
   same commit. Adding another source branch requires a reviewed contract change.
5. `targetCommitSha` is a comparison baseline. The consumer requires only that it resolves in the
   target repository and is an ancestor of, or equal to, the current base-branch head. The consumer
   then branches from the current head and records that head in the proposal for drift traceability.
6. A payload without `payloadVersion` major version `2`, or missing any required version 2 field, is
   rejected with a named error. The consumer never infers an artifact location from a baseline
   commit, never falls back to a branch head, and never guesses.

Evidence for the choice: the pinned baseline commit `64195c0` provably predates the `parity/` tree;
`provenance.inventoryCommitSha` is defined only for `baseline-inventory` in
`parity/schemas/terraform-handoff.schema.json`; assessment records live on a separate ledger branch;
and a file cannot contain its own commit SHA, so no in-record field can carry this value.

## Consequences

Positive: every dispatch becomes deterministic and auditable; baselines stay immutable, so inventory
and evidence remain reproducible; the handoff record schema and all approved records are untouched;
target-repository drift is recorded rather than raced; failures name a single cause.

Negative: two repositories must adopt in a defined order; the producer takes a dependency on git
metadata in the publication job; four payload fields and one version field must be maintained on both
sides; the consumer performs two extra read-only GitHub API calls per dispatch (containment check and
ancestor check) and is subject to their rate limits.

Neutral: no Azure cost, no new identity, and no change to Actions minutes beyond those calls.
Operational ownership stays as ADR-0003 defines it: this repository owns the payload contract and the
approved records; the Terraform repository owns the receiver, branches, proposals, and evidence.

## Compatibility and migration

No Bicep parameter, output, default, naming, manifest, module, or runtime contract changes. No change
to `parity/schemas/terraform-handoff.schema.json`, `parity/config.json`, `parity/inventory.json`, or
any approved handoff record; `schemaVersion` stays `1.0.0` and no handoff needs re-approval.

The dispatch payload is versioned separately from the handoff schema and moves from an implicit
version 1 to `2.0.0`. This is a breaking payload change, and it is safe to make in one step because
version 1 has never been consumed successfully: every dispatch under it 404s. Compatibility behavior
is explicit rejection, not tolerance. The consumer rejects a version 1 payload, or any version 2
payload missing a required field, with a named error and no proposal, so an operator sees a contract
mismatch instead of a silent or guessed fetch. The event type stays `parity-proposal-requested` so
that rejection happens inside the receiving workflow, where it is visible, rather than as a silently
unrouted event.

Migration for records is not required. Migration for automation is the adoption order below.

## Security and identity

Azure managed identities, RBAC scopes, public access, private endpoints, DNS, routes, and subnets are
unchanged. No Azure credential, tenant ID, subscription ID, or environment-specific name enters the
payload; the existing sensitive-content scan and the identifier-only allow-list continue to apply to
the new fields, all of which are identifiers, paths, or digests.

The artifact-commit rule tightens authorization. Because the consumer fetches instructions that a
coding agent will act on, the fetch location must be reviewed content: the consumer verifies that
`handoffCommitSha` is contained in an allow-listed branch of the allow-listed source repository, so a
mistaken or manipulated dispatch cannot point the agent at an arbitrary, unreviewed, or forked
commit. `handoffPath` and `handoffSchemaPath` are validated against path allow-list patterns rooted at
`parity/handoffs/` and `parity/schemas/`, with no traversal segments, before any fetch. Fetched
content is treated as data only and is never executed.

Publication authorization is unchanged: protected-environment approval, an ephemeral GitHub App token
scoped to the target repository only, no write access back to this repository, and no merge or deploy
permission. The App gains no permission from this decision; the containment and ancestor checks use
read-only access to public repository history.

## Adoption and rollback

Adoption order:

1. This ADR and the updated contract documents merge in this repository. No behavior changes yet, and
   dispatch stays broken in exactly the way it is broken today.
2. The Terraform receiver pull request (#170) adopts version 2 first: require `payloadVersion` major
   `2` and every required field, fetch the handoff and schema at `handoffCommitSha`, verify the digest
   and branch containment, replace the `targetCommitSha == main` rule with resolve-and-ancestor, and
   reject anything else with a named error. Receiver-first is deliberate and fail-closed: until the
   producer catches up, dispatches fail with an explicit contract-version error instead of a 404, and
   nothing regresses because no dispatch succeeds today.
3. This repository's producer pull request adds the fields, the git verification, and the fitness
   functions below.
4. An end-to-end rehearsal uses one approved handoff through the protected environment. The rehearsal
   proves the fetch, digest, containment, ancestor, and duplicate paths.
5. Remaining approved handoffs are published one at a time, each reconciled against its recorded
   `terraformPullRequestUrl`.

Rollback and roll-forward: reverting the producer change leaves version 1 payloads that the consumer
rejects by name; reverting the consumer change leaves version 2 payloads that the old consumer 404s.
Both directions fail closed, raise no proposal, and leave the gap open, so neither creates a partial
or ambiguous proposal. Disabling `.github/workflows/terraform-parity-publish.yml` or the receiving
workflow pauses coordination with no Azure, consumer, or record impact. Roll-forward is preferred:
fix the failing side and re-run the manual publication, which is idempotent.

Cleanup: no data or Azure resource cleanup. A proposal opened from a wrong artifact commit is closed
in the target repository, and its handoff is superseded by a reviewed record here; records are never
deleted or rewritten.

## Compliance verification

Producer fitness functions in this repository:

- Prove the payload contains `payloadVersion` `2.0.0` and every required version 2 field, and that the
  identifier allow-list still rejects any unlisted property.
- Prove `handoffCommitSha` is a 40-character lower-case hex commit and is never derived from
  `source.commitSha`, `target.commitSha`, or `provenance.inventoryCommitSha`.
- Prove publication fails explicitly when the handoff bytes in the working tree differ from the blob
  at `handoffCommitSha`, when that commit does not contain the handoff path, and when it does not
  contain the handoff schema path.
- Prove `handoffDigest` is computed over the same LF-normalized bytes as `inventoryDigest` and is
  identical on Windows and Linux.
- Prove baseline fields still fail on a stale baseline, and that the artifact fields do not relax the
  existing approval, provenance, allow-list, gap, and duplicate checks.
- Prove the payload stays within the bounded size limit and passes the sensitive-content scan with the
  new fields present.
- Keep publication tests deterministic by initializing a temporary git repository, as the existing
  workflow-event tests do, rather than adding an opt-out switch to the verification.

Consumer fitness functions in the Terraform repository:

- Reject a version 1 or field-incomplete payload with a named error, no branch, and no proposal.
- Fail explicitly and name `handoffCommitSha` when the handoff or schema is not found at that commit.
- Reject an artifact commit that is not contained in an allow-listed source branch.
- Reject a digest mismatch and a handoff record that fails schema validation.
- Reject `handoffPath` or `handoffSchemaPath` outside their allow-list patterns.
- Prove that a `targetCommitSha` that is an ancestor of the current head succeeds, that the current
  head at branch time is recorded in the proposal, and that a non-ancestor or unresolvable baseline
  fails explicitly.
- Prove a repeated dispatch for the same handoff ID returns the existing proposal and never opens a
  second one, and that a changed `handoffCommitSha` for the same handoff ID reports artifact drift on
  the existing proposal instead of creating another.

Static checks, plans, and this rehearsal remain non-parity evidence. Only an approved
test-subscription deployment plus a reviewed capability comparison can advance a scenario.

## Documentation impact

This decision updates `specs/001-terraform-foundry-parity/contracts/workflow-events.md`,
`specs/001-terraform-foundry-parity/contracts/terraform-repository-interface.md`, and the handoff
section of `specs/001-terraform-foundry-parity/data-model.md`.

Implementation additionally updates `docs/terraform-parity-ownership.md` operator commands with the
new publication parameter, `CHANGELOG.md`, and the receiving workflow's documentation in the Terraform
repository. `README.md`, deployment runbooks, and the public AI Landing Zones documentation are
unaffected because no consumer-visible infrastructure behavior changes.

## Review trigger

Review this decision when either release baseline advances, when the handoff schema takes a breaking
change, when the assessment ledger or allow-listed source branches change, when this repository or the
target repository changes visibility or branch protection so that anonymous commit-containment checks
stop working, when GitHub changes `repository_dispatch`, compare, or rate-limit behavior, when the
receiving workflow's ownership or contract changes, after any authorization incident or wrongly
targeted proposal, or when a third consumer repository needs the same payload.
