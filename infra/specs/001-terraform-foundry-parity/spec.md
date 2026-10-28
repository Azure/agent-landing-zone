# Feature Specification: Terraform Parity for the Foundry AI Landing Zone

**Feature Branch**: `001-terraform-foundry-parity`

**Created**: 2026-08-21

**Status**: Historical — superseded by [ADR-0028](../../../docs/adr/ADR-0028-integrated-terraform-composition.md)

> This specification and its sibling contracts, plans, tasks and validation
> records describe retired external coordination. They are retained for audit,
> not as active instructions or a requirement to restore the removed pipeline.

**Input**: User description: "let's specify https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/136 — Establish Terraform parity for the Foundry AI Landing Zone"

## Clarifications

### Session 2026-08-21

- Q: Which specific deployment scenarios must Terraform reach parity on for this feature to be considered done? → A: Standalone standard (`networkIsolation=false`) and standalone network-isolated (`networkIsolation=true`). Hub-spoke and optional-feature combinations are out of scope for the parity claim.
- Q: Does this feature's definition of done include the actual Terraform code that closes the gaps, or does it stop at the coordination assets? → A: Coordination assets ship here and every identified gap has a raised, reviewable proposal in the Terraform repository. Merging that code and producing deployment evidence is tracked as follow-up outside this feature's completion.
- Q: What triggers the alignment workflow that turns a reference-implementation change into a Terraform proposal? → A: Per pull request merged into this repository's integration branch; each merge produces an assessment record while the change context is still available.
- Q: Where should the gap inventory live and in what format? → A: A machine-readable structured data file in this repository is the source of truth, with a human-readable view generated from it.
- Q: Which version of the reference implementation should the gap inventory be measured against? → A: The released version recorded in this repository's release manifest, pinned in the inventory file and advanced deliberately.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Understand the parity gap (Priority: P1)

A platform engineer evaluating the AI Landing Zone needs to know, before committing to an
infrastructure language, exactly which landing-zone capabilities the Terraform implementation
supports today and which ones only the reference implementation supports. Today that comparison
does not exist, so the decision is made by reading two codebases side by side.

**Why this priority**: Without an agreed, published gap inventory, every later parity decision is
guesswork and no one can tell when parity has been achieved. This is the smallest slice that
delivers standalone value: it is useful even if no code is written afterwards.

**Independent Test**: Give the gap inventory to an engineer who has not read either codebase and
ask them to answer "can Terraform do X today?" for a sample of landing-zone capabilities. It
passes when they can answer correctly from the document alone, without opening source code.

**Acceptance Scenarios**:

1. **Given** the published gap inventory, **When** an engineer looks up a landing-zone capability
   supported by the reference implementation, **Then** the inventory states whether Terraform
   supports it fully, partially, or not at all, and links to the corresponding consumer input.
2. **Given** a capability marked as a gap, **When** an engineer reads its entry, **Then** the entry
   records the consumer-visible impact and whether closing it is expected to break existing
   consumers.
3. **Given** the reference implementation gains a new capability after the inventory is published,
   **When** the alignment workflow runs, **Then** the inventory is updated to include the new
   capability rather than silently going stale.

---

### User Story 2 - Prepare Terraform parity proposals (Priority: P2)

A platform team that standardises on Terraform needs a reviewable implementation proposal for every
gap that prevents it from deploying the same standard and network-isolated Foundry AI Landing Zone
scenarios as Bicep consumers, without moving Terraform source into this repository.

**Why this priority**: This is the core outcome of the request, but it depends on User Story 1 to
know what to build. The proposals are independently valuable and testable before the Terraform
repository merges, releases, and deploys them.

**Independent Test**: For every actionable inventory gap, validate an approved structured handoff
and confirm a corresponding draft Terraform pull request or reviewed deferral exists. It passes
when proposal coverage is complete and no Terraform source exists in this repository.

Pending baseline handoffs are draft gap coverage only. They identify the active baseline and the
SHA-256 digest of the exact inventory bytes, but cannot be consumed or satisfy proposal eligibility.
Approval separately records the commit containing that inventory, its review URL, and handoff
authorization. Issue #136 is context, not either form of approval.

**Acceptance Scenarios**:

1. **Given** an actionable inventory gap, **When** its approved handoff is processed, **Then** a
   reviewable Terraform proposal or reviewed deferral is linked to that gap.
2. **Given** a gap that may change an existing Terraform contract, **When** its handoff is created,
   **Then** the proposal requires a migration path, deprecation transition, and semantic-version
   assessment.
3. **Given** a gap affecting the network-isolated scenario, **When** its handoff is created, **Then**
   its isolation invariants and deployment evidence requirements are stated independently from the
   standard scenario.
4. **Given** an actionable implementation gap, **When** its Terraform proposal is prepared, **Then**
   the handoff identifies the Azure Verified Modules checks the target repository must pass.
5. **Given** a scenario that compiles and produces a clean plan, **When** someone proposes
   declaring it at parity, **Then** the claim is rejected until a successful test-subscription
   deployment of that scenario exists.
6. **Given** a pending initial-baseline draft, **When** proposal eligibility is evaluated, **Then**
   it remains ineligible until inventory provenance and handoff approval are complete and verified.

---

### User Story 3 - Keep both implementations aligned over time (Priority: P3)

A maintainer who lands a change in the reference implementation needs a defined, repeatable path
for that change to reach the Terraform implementation, so parity does not decay after the initial
catch-up effort.

**Why this priority**: Parity achieved once but not maintained returns the project to the starting
position within a few releases. It is deliberately lower priority than achieving parity, because
there is nothing to keep aligned until User Story 2 lands.

**Independent Test**: Take a recent reference-implementation change and run it through the
alignment workflow end to end. It passes when the workflow produces a reviewable Terraform change
proposal in the Terraform repository and a recorded review decision, with no undocumented manual
steps.

**Acceptance Scenarios**:

1. **Given** a change that alters consumer-visible behaviour in the reference implementation,
   **When** the alignment workflow runs, **Then** a corresponding Terraform change proposal is
   raised for review in the Terraform repository.
2. **Given** a machine-generated Terraform change proposal, **When** it is ready to publish,
   **Then** publication is blocked until a human reviewer has approved it.
3. **Given** a reference-implementation change with no Terraform impact, **When** the alignment
   workflow runs, **Then** the change is recorded as assessed and requiring no action.
4. **Given** any parity question or review request, **When** someone needs a decision, **Then**
   documented ownership identifies who is accountable for the reference implementation, the
   Terraform implementation, and cross-implementation review.
5. **Given** a change being implemented here through the specification-driven workflow, **When**
   that change reaches implementation, **Then** the workflow supplies the coding agent with the
   change context it needs to draft the Terraform proposal, without the maintainer re-describing
   the change by hand.

---

### Edge Cases

- What happens when a capability cannot be reproduced in Terraform because the underlying provider
  does not yet support it? The inventory must record it as a blocked gap with its cause, rather
  than leaving it indistinguishable from unimplemented work.
- What happens when closing a gap unavoidably breaks an existing consumer contract? The change must
  carry a documented migration path and an explicit version-impact decision before publication.
- How is a partially implemented capability represented? Partial support must be distinguishable
  from full support and from absence, so consumers are not misled by a binary yes/no.
- What happens when the reference implementation changes while Terraform parity work is in flight?
  The parity baseline must be explicit so "parity" is a claim against a known reference point, not
  a moving target.
- What happens when a machine-generated proposal is wrong or unsafe? Review must be able to reject
  it, and rejection must not silently drop the underlying gap.
- How are the two implementations kept from diverging on defaults? Differences in default values
  are consumer-visible and must be treated as parity gaps, not cosmetic differences.
- What happens when a Terraform deployment fails only in the network-isolated scenario? The
  standard scenario's evidence cannot cover it, so the isolated scenario stays outside the parity
  claim until it deploys successfully on its own.
- What happens when a test subscription is unavailable or a deployment cannot be funded? The
  scenario remains undeclared rather than being declared on weaker evidence.
- What happens when a reference-implementation change touches only internals with no consumer
  impact? The workflow must be able to close it as assessed-and-no-action without generating noise
  in the Terraform repository.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The project MUST publish a gap inventory that compares the Terraform implementation
  against the reference implementation across all consumer-visible landing-zone capabilities.
- **FR-001a**: The gap inventory MUST be maintained as a machine-readable structured data file in
  this repository, which is the single source of truth. A human-readable view MUST be generated
  from that file rather than authored independently, so the two can never disagree.
- **FR-002**: Each inventory entry MUST classify support as full, partial, absent, or blocked, and
  MUST state the consumer-visible impact of the gap.
- **FR-003**: Each inventory entry MUST state whether closing the gap is expected to preserve or
  break existing Terraform consumer contracts.
- **FR-004**: The gap inventory MUST be stated against an explicitly identified reference-
  implementation baseline version, so parity claims are verifiable at a fixed point in time. The
  baseline MUST be the released version recorded in this repository's release manifest, pinned
  inside the inventory file itself, and advanced only as a deliberate act when the inventory is
  re-run. "Latest integration branch" MUST NOT be used as a baseline.
- **FR-005**: The Terraform implementation MUST support exactly two supported scenarios — the
  standalone standard scenario and the standalone network-isolated scenario — at the capability
  level recorded in the inventory. The hub-spoke scenario and arbitrary optional-feature
  combinations are outside the parity claim for this feature.
- **FR-006**: The Terraform implementation MUST remain compliant with Azure Verified Modules
  pattern-module requirements.
- **FR-007**: Existing Terraform consumer inputs and outputs MUST be preserved wherever possible;
  where a contract must change, the change MUST ship with a documented migration path and a
  deprecation transition rather than an immediate removal.
- **FR-008**: Parity claims MUST be supported by automated tests covering the supported scenarios,
  and the tests MUST run as part of the Terraform implementation's own validation.
- **FR-009**: The project MUST define a repeatable workflow that identifies reference-
  implementation changes with Terraform impact and turns them into reviewable Terraform change
  proposals.
- **FR-009a**: The alignment workflow MUST be triggered per pull request merged into this
  repository's integration branch, so that each merge produces an assessment record at the moment
  the change context is still available. Release-time or on-demand batching MUST NOT be the primary
  trigger.
- **FR-010**: The alignment workflow MUST record an explicit assessment outcome for every evaluated
  reference-implementation change, including "no Terraform impact". The assessment record MUST
  identify the merged pull request it corresponds to.
- **FR-011**: Machine-generated Terraform changes MUST NOT be published without recorded human
  review and approval.
- **FR-012**: The project MUST document ownership and review responsibilities for the reference
  implementation, the Terraform implementation, and cross-implementation parity decisions.
- **FR-013**: Parity work MUST NOT alter the behaviour, contracts, or defaults of the reference
  implementation in order to make Terraform easier to write; the reference implementation stays the
  functional reference.
- **FR-014**: Differences in default values between the two implementations MUST be treated as
  consumer-visible gaps and recorded in the inventory.
- **FR-015**: This repository MUST own the parity coordination assets: the gap inventory, the
  alignment workflow definition, the ownership documentation, and the agent-facing instructions and
  tooling that turn a reference-implementation change into a Terraform change proposal.
- **FR-016**: This repository MUST NOT contain Terraform implementation source. Generated Terraform
  changes MUST be delivered as pull requests against the Terraform repository, which remains the
  owner of Terraform code, its validation, and its release process.
- **FR-017**: The specification-driven workflow used to implement a change in the reference
  implementation MUST be able to emit, from the same change context, the input a coding agent needs
  to produce the corresponding Terraform change proposal.
- **FR-018**: A scenario MUST NOT be declared at parity until it has been deployed successfully
  into a test subscription from the Terraform implementation. Static validation and plan-level
  output MUST NOT be accepted as parity evidence.
- **FR-019**: Parity evidence MUST be produced independently for each supported scenario, including
  the standard and network-isolated scenarios; evidence from one scenario MUST NOT be used to claim
  parity for another.
- **FR-020**: Once a scenario is deployed successfully, its capability comparison against the
  reference implementation MUST be recorded as a reviewed assessment against the gap inventory.
- **FR-021**: This feature is complete when the coordination assets are published here and every
  gap recorded in the inventory has a corresponding reviewable change proposal raised in the
  Terraform repository. Merging those proposals, deploying the resulting scenarios, and recording
  parity evidence are tracked as follow-up work outside this feature's completion.
- **FR-022**: FR-005 through FR-008 define the parity target that raised proposals and their
  follow-up work MUST satisfy. They are acceptance criteria for the parity outcome, not gates on
  this feature's completion, because the Terraform repository owns their merge and release.

### Key Entities

- **Landing-zone capability**: A consumer-visible behaviour of the landing zone — a configurable
  option, an included component, a security or connectivity characteristic, or a published output.
  It is the unit the gap inventory compares.
- **Gap inventory entry**: One capability's parity record — its support classification, consumer
  impact, contract-compatibility expectation, and, when blocked, the reason it cannot be closed.
  Entries are structured records in the machine-readable inventory file, not free prose.
- **Supported scenario**: A named deployment shape that both implementations are expected to
  deliver. For this feature the set is fixed at two: the standalone standard scenario and the
  standalone network-isolated scenario.
- **Consumer contract**: The stable surface Terraform consumers depend on — input names, defaults,
  allowed values, and outputs — governed by preservation, deprecation, and migration rules.
- **Alignment assessment**: The recorded outcome of evaluating one reference-implementation change
  for Terraform impact, including its decision, resulting proposal if any, and reviewer.
- **Parity baseline**: The identified reference-implementation version a parity claim is measured
  against — the released version recorded in the release manifest, pinned inside the inventory
  file and advanced only as a deliberate act.
- **Parity evidence record**: The proof that one supported scenario deployed successfully from the
  Terraform implementation into a test subscription, together with the reviewed capability
  comparison against the gap inventory.

## Success Criteria *(mandatory)*

### Measurable Outcomes

Outcomes marked *(follow-up)* describe the parity target and are verified after the Terraform
repository merges and deploys the raised proposals; they are not gates on this feature's
completion (see FR-021, FR-022).

- **SC-001**: 100% of consumer-visible landing-zone capabilities in the reference implementation
  have a classified entry in the gap inventory, with no capability left unassessed.
- **SC-002**: An engineer unfamiliar with both codebases can determine Terraform's support for any
  given capability from the inventory alone, without reading source code.
- **SC-003**: *(follow-up)* Every supported scenario has been deployed successfully from the
  Terraform implementation into a test subscription, and the deployed capability set matches the
  inventory's parity claims.
- **SC-004**: *(follow-up)* 100% of Terraform consumer inputs and outputs that existed before the
  parity work either continue to function unchanged or have a published migration path and
  deprecation notice.
- **SC-005**: *(follow-up)* The Terraform implementation passes the Azure Verified Modules
  pattern-module compliance checks required for publication.
- **SC-006**: *(follow-up)* Automated tests cover every supported scenario and run on every change
  to the Terraform implementation.
- **SC-007**: Every pull request merged into the integration branch after the workflow is adopted
  has a recorded alignment assessment traceable to that pull request, with zero silently unassessed
  merges.
- **SC-008**: Zero machine-generated Terraform changes reach publication without a recorded human
  approval.
- **SC-009**: For any parity question, the accountable owner can be identified from documentation
  in under five minutes.
- **SC-010**: Zero scenarios are declared at parity on the basis of static validation or plan
  output alone.
- **SC-011**: A maintainer implementing a change here can trigger the Terraform proposal from the
  same change context, without manually restating what changed.
- **SC-012**: 100% of gaps recorded in the inventory have a corresponding reviewable change
  proposal raised in the Terraform repository, with zero gaps left without a proposal or a recorded
  reason for deferral.

## Assumptions

- The reference implementation is the functional source of truth; the Terraform implementation
  adapts to it, not the other way round.
- Terraform work is delivered in the existing `Azure/terraform-azurerm-avm-ptn-aiml-landing-zone`
  repository through short-lived branches and pull requests. A new repository is created only if
  the work becomes a distinct pattern with a different consumer contract, which is assumed not to
  be the case.
- The Terraform implementation implements resources directly rather than composing other Terraform
  AVM resource modules, to keep the pattern module agile when the reference implementation changes.
- "Parity" means equivalent consumer-visible capability and behaviour, not identical internal
  structure, naming, or resource composition.
- Both implementations target the same Azure services; where an Azure capability is unavailable to
  one language's provider, that is recorded as a blocked gap rather than treated as a defect.
- Parity is assessed at the scenario level. Arbitrary combinations of every optional feature are
  out of scope for the parity claim unless they are part of a named supported scenario.
- The hub-spoke scenario depends on pre-existing customer connectivity that cannot be reproduced
  cheaply in a test subscription, so it is deferred to follow-up work rather than included in this
  feature's parity claim.
- Existing Terraform consumers are assumed to be on a published version of the module and able to
  follow a documented migration path within a normal upgrade cycle.
- Machine assistance may draft translations, but accountability for correctness stays with the
  human reviewer.
- Maintainers implement reference-implementation changes here using a specification-driven
  workflow, and the parity automation hooks into that workflow rather than running as a separate,
  disconnected process.
- A test subscription with capacity for both the standard and network-isolated scenarios is
  available for parity evidence.
- Portal-based landing-zone experiences are out of scope for this feature except where release
  policy already requires parity review.
