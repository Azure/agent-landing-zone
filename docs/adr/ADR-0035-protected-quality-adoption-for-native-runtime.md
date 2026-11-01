# ADR-0035: Retire the frozen-base quality policy self-lock

**Status:** Accepted, runtime control maintenance activated<br>
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

The maintainer subsequently requested removal of this blocking policy and
authorized administrative adoption and PR integration. The authenticated acting
account's administration permission was verified for the runtime, UI and umbrella
repositories. This decision supersedes the earlier hold pending a new formal
authorization channel; it does not waive actual source or behavior failures.

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

### Option B: Current-revision quality checks without a permanent self-lock

- Benefits: analyze source, dependency manifests and contributor controls from
  the revision actually being reviewed. Control maintenance no longer requires
  pretending that new contracts are unchanged historical ones.
- Costs and risks: maintainers must review control changes through the repository
  process instead of relying on an immutable-policy prohibition.
- Security and identity: preserve actual failure evidence, source/report binding,
  typing coverage and suppression protections. No blanket approval inheritance
  or debt-baseline reset is permitted.
- Operational consequences: retire the automatic control-edit prohibition and
  frozen-base authority, not lint, typing, architecture or behavior checks.
- Component compatibility: preserve host-specific production dependencies and
  validate the real published SDK groups used by each component.
- Reversibility: contributor control changes remain versioned and reversible;
  reintroducing a permanent self-lock would require a new explicit decision.

### Do not change

- Benefits: preserve existing contributor enforcement and released behavior.
- Costs and risks: the requested native major cannot be published as ready.

## Decision

Choose Option B, as explicitly requested by the maintainer. Remove the
frozen-base/self-amendment policy rather than adding another authorization
channel. Retain required quality checks and their useful regression protections.

Use a small, isolated maintenance PR for the transition. The maintainer-authorized
administrative override is limited to adopting that maintenance change when the
old self-lock is its remaining blocker and other checks pass. Do not disable
branch protection, fabricate statuses or extend this override to unresolved
native source failures. Native integration and publication still require genuine
passing checks under the maintained current-revision model.

Governance remains contributor infrastructure, not an application or provisioning
dependency. Activation of contributor controls does not establish native release
readiness.

### Activation evidence

The isolated maintenance change was normally squash-merged through
[Azure/agent-app-orchestrator#429](https://github.com/Azure/agent-app-orchestrator/pull/429)
on 2026-11-01. Its reviewed head was
`7c91b60c7968a44964ecc4dd5427313dc404878c`, and the resulting develop commit is
`9e45626f38de36e8faa595734ccd8fa378b27dbc`.

Every actual required check passed before integration, including tests, frontend,
lint, typing, architecture, exceptions, policy and the aggregate quality gate.
No administrative override, fabricated approval or branch-protection change was
needed. Native code and its main-targeted release retain their own required checks.

## Consequences

### Positive

- Preserve source-bound evidence and actual failure controls without freezing
  contributor policy and dependencies permanently at the previous architecture.
- Distinguish functional SDK proof from merge and release acceptance.
- Avoid inheriting historical approvals for changed or retired handlers.

### Negative or accepted

- Passing behavior tests alone cannot satisfy the release commitment.
- The isolated administrative transition needs exact scope and recorded evidence.

## Adoption and migration

First prepare and validate the isolated control-maintenance PR. Record its exact
head, the old self-lock finding, passing independent checks and the maintainer
authorization before administrative integration.

Then retire unused classic execution source coherently, preserve active shared
helpers and maintain exact active/retired surface and handler inventories. Do not
delete history or retain dead execution code solely to satisfy obsolete checks.
Preserve unrelated main changes during reconciliation.

CI must state explicitly that it evaluates the actual reviewed revision and its
dependency contracts. Do not disguise source substitution as protected-base
execution or claim that local prospective-policy validation is a passing hosted
CI result.

After all required checks pass, validate the exact frozen component combination,
publish components, bind umbrella tags and commits, and publish matching product
documentation. Rollback before adoption is to retain existing released pins.
Any later policy rollback must preserve or strengthen enforcement and be reviewed.

No Azure resource, runtime identity, networking or product-data migration is
introduced by this proposal. Validation cost is limited to existing CI and local
checks.

## Compliance verification

- Bind reports to the exact source being checked. Reject mismatched hashes,
  replayed evidence and forged statuses.
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

Reassess after the maintenance PR is activated, when the final native candidate
passes every required check, or if current-revision evaluation permits weakened
coverage, invalid retirement or unproven failure handling.
