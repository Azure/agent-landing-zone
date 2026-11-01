# ADR-0035: Preserve protected quality checks during native runtime adoption

**Status:** Proposed, no policy activation authorized by this record<br>
**Date:** 2026-10-31<br>
**Owners:** Agent Landing Zone and runtime repository maintainers

## Context

[ADR-0034](ADR-0034-native-agent-and-workflow-hosting.md) changes the runtime
architecture, public module surfaces and supported execution paths. Passing
native behavior tests does not authorize changes to contributor quality controls.

The frozen runtime candidate `076d477c5c4ca51490e93fe48287242931c959af` in
[Azure/agent-app-orchestrator#427](https://github.com/Azure/agent-app-orchestrator/pull/427)
passed the actual tests and frontend checks. Its required quality checks did
not pass. The artifact-bound
[handoff](https://github.com/Azure/agent-app-orchestrator/pull/427#issuecomment-6551271598)
identifies source/evidence findings, missing protected-base SDK dependencies,
undeclared module consumers and protected-control modifications separately.

The existing evaluator executes from the protected base. Its `policy_changes`
function unconditionally rejects protected-control modifications, apart from
typing-debt removal and typing-scope expansion. Its diagnostic requests explicit
maintainer authorization, but it does not implement an authorization channel.
The initial policy records administrative adoption, not permission for a
candidate to approve its own subsequent changes.

The UI also demonstrates an independent prerequisite: green develop checks do
not prove release-to-main readiness when main's protected dependency manifest
lacks the adopted SDKs.

Affected repositories are `Azure/agent-app-orchestrator` and `Azure/agent-app-ui`.
The umbrella manifest and central product documentation must not describe a
blocked candidate as the validated released combination.

Priorities are unchanged enforcement, authenticated authorization, exact
source/evidence provenance, compatible prerequisite sequencing and bounded
validation. Required quality failures and unapproved allowances must be zero
before publication.

## Alternatives considered

### Option A: Formal, separately reviewed protected-policy adoption

- Benefits: explicitly reviews new surfaces, retired records and dependency
  contracts instead of disguising an architectural change as existing approval.
- Costs and risks: requires a legitimate maintainer-controlled adoption path,
  which the current evaluator does not provide.
- Security and identity: candidate code, comments and generated reports cannot
  authorize themselves. Any future authorization must authenticate the
  maintainer and bind approval to exact source, scope and policy revision.
- Operational consequences: stage source cleanup and prerequisites separately.
  A normal PR or a chat approval alone does not make the current gate pass.
- Component compatibility: evaluate develop and main independently. Preserve
  existing behavior while promoting dependency-only prerequisites.
- Reversibility: no production change occurs while adoption is only proposed.

### Option B: Source-only corrections within existing policy

- Benefits: resolve genuine bugs and missing failure evidence without changing
  protected controls. Independently compatible maintenance can proceed.
- Costs and risks: cannot by itself authorize the remaining protected surface,
  workflow and retirement changes required by the native major.
- Security and identity: retain exact approvals only for unchanged, proven
  handlers. Changed handlers need precise handling or legitimate new adoption.
- Operational consequences: use targeted checks and keep residual policy
  findings distinct from source defects.
- Component compatibility: retain the current released combination while the
  coordinated native release remains blocked.
- Reversibility: ordinary reviewed source corrections remain reversible.

### Do not change

- Benefits: preserve existing contributor enforcement and released behavior.
- Costs and risks: the requested native major cannot be published as ready.

## Decision

Prepare formal adoption evidence and continue source-only corrections, but keep
the coordinated native release blocked until every required check passes through
a legitimate, verifiable process.

This proposal does not add an authorization channel, approve exception records,
change required statuses or prescribe an administrative bypass. If no compliant
activation path exists, report that limitation rather than manufacturing a
passing result. Governance is contributor infrastructure, not a new application
or provisioning dependency.

## Consequences

### Positive

- Preserve protected-base execution, source-bound evidence and failure controls.
- Distinguish functional SDK proof from merge and release acceptance.
- Avoid inheriting historical approvals for changed or retired handlers.

### Negative or accepted

- Passing behavior tests alone cannot satisfy the release commitment.
- Explicit adoption and dependency sequencing can block publication.

## Adoption and migration

First resolve removable source/evidence findings under existing rules. Promote
compatible SDK prerequisites through normal protected PRs before their consumers
reach develop or main. Preserve unrelated main documentation during reconciliation.

Maintain a reviewed inventory of exact surface changes and handler dispositions.
Establish a compliant adoption path before attempting protected-policy activation.
No candidate-supplied policy or substitute dependency environment may replace the
trusted base to force a passing check.

After all required checks pass, validate the exact frozen component combination,
publish components, bind umbrella tags and commits, and publish matching product
documentation. Rollback before adoption is to retain existing released pins.
Any later policy rollback must preserve or strengthen enforcement and be reviewed.

No Azure resource, runtime identity, networking or product-data migration is
introduced by this proposal. Validation cost is limited to existing CI and local
checks.

## Compliance verification

- Reject unauthorized control edits, mismatched source hashes and replayed
  approval/evidence. Fail closed when authority cannot be verified.
- Preserve negative tests for source substitution, approval inheritance,
  retired handlers and broadened suppressions.
- Verify any future adoption against exact reviewed modules, handlers and SDK
  manifests, not blanket path exclusions or an expanded debt baseline.
- Require the real quality, behavior and frontend statuses on the final head.
  Final component binding tests must use the commits selected for release.

## Documentation impact

Keep this contributor decision local. Central product documentation stays
aligned with the shipped combination and must not advertise a blocked candidate
as released. Functional local tests do not establish deployed durability, private
network behavior or live model file understanding.

## Review trigger

Reassess when a compliant maintainer-controlled adoption path is demonstrated,
the protected evaluator changes, or the final native candidate has no remaining
source/evidence or policy failures.
