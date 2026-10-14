# ADR-0020: Validate exception registry updates technically, without mandatory independent approval

**Status:** Accepted for implementation; protected-policy adoption pending<br>
**Date:** 2026-10-09<br>
**Owners:** Agent Landing Zone maintainers

## Context

Q5 currently blocks Azure/agent-app-ui#144 solely for changing exception
records and requires independent latest-head approval. The user's explicit
decision removes that administrative requirement, not technical quality gates.
Affected repositories are Azure/agent-landing-zone (Q5 and this decision),
Azure/agent-app-ui (evaluator, tests, records and contributor guidance), and the
central AI Landing Zones documentation source (checked for affected guidance).
No runtime, identity, deployment, component pin or data contract changes.

Priorities, in order: fail-closed evaluation (all negative fixtures fail);
exact-source evidence (stale, skipped or failed receipts never authorize);
protected-tool integrity (candidate checker/settings cannot relax policy);
bounded exceptions (expiry, stage and exact caught types remain enforced);
low administrative overhead (registry-only changes need no approval string).

## Alternatives considered

### Option A: Technical validation policy

- Benefits: source-bound, tested registry updates can pass without human
  approval metadata; CI still evaluates real results.
- Costs and risks: tests and written rationale cannot prove every runtime
  semantic property. Maintain negative fixtures and review on regressions.
- Security and identity: preserve read-only CI, isolated protected evaluator,
  exact handler identity, bounded catch resolution and fail-closed aggregation.
- Operation and compatibility: ordinary registry updates use candidate records;
  checker, workflow, toolchain and other policy changes remain protected.
- Reversibility: revert evaluator adoption; revised records may then block.

### Option B: Administrative override

- Benefits: can unblock this one policy-change PR without a checker change.
- Costs and risks: repeats bureaucracy, leaves ordinary registry changes blocked,
  and relies on a privileged bypass rather than technical acceptance.
- Security and identity: auditable but adds administrator intervention.
- Operation and compatibility: no runtime change; old policy remains.
- Reversibility: simple, but recurring overrides are not a policy solution.

### Do not change

- Benefits: preserves current approval controls.
- Costs and risks: contradicts the user's resolved decision and continues
  blocking technically valid exception corrections.

## Decision

Choose Option A. Evaluate the candidate exception registry under protected
technical rules. Only `active` records can be consumed; this means eligible
for technical validation, not independently approved. `review` remains required
nonempty provenance for schema compatibility, not authority. Proposed, retired,
expired, stale, unresolved, wrong-type or unevidenced records fail. Registry
edits alone are not policy-change violations. All other protected checks remain.
Do not introduce migration flags, blanket BLE001 suppression, fake approval
strings, fabricated CI results or privileged PR execution.

## Consequences

### Positive

- Evidence-based registry updates no longer require independent review.
- Ordinary checker/tool/workflow tampering remains a blocking finding.

### Negative or accepted

- A protected checker change still needs authorized adoption. The old checker
  cannot authorize this new policy, so this PR is not expected to turn green
  remotely before adoption.
- Existing repository review rules, if configured separately, are not changed
  by these files. No claim is made about live merge eligibility.

## Adoption and migration

Deliver the UI implementation and documentation first, with this platform
decision and Q5 update kept separate from unrelated root PR #774. Incorporate
the new evaluator through the repository's authorized protected-policy path.
Then validate a genuine reference PR with the adopted protected checker and
actual required jobs; configure required checks separately if absent.
No manifest, runtime, Azure resource, cost or network migration is needed.
Rollback by reverting the protected evaluator and restoring the previous
records; never weaken aggregation to hide the resulting failures. Roll forward
by correcting source/test evidence rather than adding bypasses.

## Compliance verification

- Registry-only addition/update/retirement passes policy checking.
- Only exact active, unexpired records with passing bound behavior tests can
  exempt that exact BLE001 site; unrelated lint errors still fail.
- Missing, stale, failed, skipped, unsupported and wrong-source evidence fails.
- Protected checker/runner/aggregator/workflow/CODEOWNERS/tool tampering fails.
- Aggregate rejects missing, cancelled, skipped or mismatched real job results.
- Run targeted policy tests and lint/type/architecture/exception evaluation
  against the genuine protected base; disclose protected-adoption findings.

## Documentation impact

Update Q5, UI Python development/agent guidance and technical assessment
statuses. The central AI Landing Zones source has no Python quality/exception
governance page; its existing runtime diagnostic guidance is unaffected.
Clearly distinguish local
technical validation from protected-policy adoption and remote CI.

## Review trigger

Reassess on an exception-related security regression, evidence-integrity
failure, checker/tool/workflow trust-boundary change, or by 2027-01-06 (current
exception expiry).
