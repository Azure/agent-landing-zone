# ADR-0003: Coordinate Terraform parity with a repository-native ledger

- Status: superseded by [ADR-0028](../../../docs/adr/ADR-0028-integrated-terraform-composition.md)
- Date: 2026-08-21
- Owners: AI Landing Zone maintainers and Terraform pattern-module maintainers
- Related context: issue #136 (not review or approval evidence)
- Refined by: [ADR-0004](./0004-parity-dispatch-artifact-commit-contract.md), which defines the
  dispatch payload's commit roles and artifact-location contract

## Context

> Historical decision: the external ledger, assessment and handoff automation is
> retired. The original proposal below is retained for audit, not operator use.

The Bicep repository is the functional reference for the Foundry AI Landing Zone, while Terraform
source and release ownership remain in a separate AVM pattern-module repository. Maintainers need
an auditable way to inventory gaps, assess every merged reference change, and create reviewable
Terraform proposals without moving Terraform source here or weakening human review.

Affected contracts are repository automation, a machine-readable inventory, generated
documentation, assessment and handoff records, GitHub permissions, and ownership. Azure resources,
Bicep parameters, outputs, identity, RBAC, networking, and deployment topology are not changed.

## Prioritized characteristics

| Characteristic | Priority | Measure |
| --- | --- | --- |
| Traceability | 1 | Exactly one assessment per PR merged into `develop` |
| Evidence integrity | 2 | No parity declaration without scenario-specific deployment and review |
| Compatibility | 3 | Every consumer input, output, and default difference is explicit |
| Authorization | 4 | No cross-repository proposal without recorded human approval |
| Reversibility | 5 | Disable workflows and revoke App access without Azure or consumer impact |

## Alternatives considered

### Repository-native structured ledger and gated handoff

Store versioned JSON inventory and append-only records here, persist per-merge assessments on a
serialized dedicated ledger branch, generate Markdown deterministically, and send approved
structured handoffs to the Terraform repository using an ephemeral, least-privilege GitHub App
token.

This option adds no Azure identity, resource, networking, or recurring Azure cost. It is
reviewable, reversible, and preserves repository ownership, but adds Actions usage and reviewer
work.

### GitHub Issues or Projects as the system of record

Issues offer assignment and discussion but weak schema enforcement, deterministic generation,
immutable baseline pinning, and complete coverage checks. API availability would become necessary
to answer basic parity questions.

### One assessment pull request per merged source pull request

Reviewing every assessment through `develop` would preserve familiar branch protection, but merging
an assessment-only pull request would itself require another assessment and create a recursive loop.
It would also create avoidable merge contention and delay durable recording of no-impact decisions.

### Dedicated coordination service

A hosted service and database could provide queueing and reporting, but would add Azure cost,
identity and RBAC, availability, monitoring, data lifecycle, and network ownership for a workflow
that can be represented safely in version control.

### Do not change

Manual comparison leaves gaps, no-impact decisions, and cross-repository proposals untraceable.
Parity would decay after subsequent Bicep changes.

## Decision

Use a repository-native JSON parity ledger with deterministic Markdown generation. Pin the initial
comparison to Bicep `v2.6.1` (`64195c01b70974fa7256c2f54a0035fb06804139`) and Terraform `v0.5.1`
(`abe337894f93de3ddda525ea44898b33e1484070`).

Create one idempotent assessment per PR merged into `develop`. Serialize append-only assessment
commits on a dedicated `terraform-parity-assessments` ledger branch so assessment persistence never
pushes to `develop` or recursively assesses itself. Initial catch-up handoffs use a reviewed,
immutable inventory baseline; ongoing handoffs use approved alignment assessments. Initial catch-up
uses two stages: pending drafts identify the baseline and SHA-256 digest of the exact inventory bytes
without claiming a commit or review; approval adds the commit containing that exact inventory and
its auditable review URL. The Bicep implementation commit, Terraform implementation commit, and
inventory artifact commit are distinct roles and are never inferred from one another. Require
protected-environment human approval before dispatching a bounded handoff to the Terraform
repository. Terraform source, validation, deployment, merge, and release remain owned there. Keep
support classification separate from evidence level, and require independent successful deployment
and reviewed comparison for standard and network-isolated parity claims.

## Consequences

Parity decisions become reproducible and auditable. Coding agents receive structured context
without credentials or Azure permissions. Maintainers incur schema maintenance, Actions minutes,
GitHub App key rotation, ledger-branch retention, and review backlog. Test-subscription deployments
remain follow-up cost owned by the Terraform workflow.

## Compatibility and migration

No Bicep parameter, output, default, naming, manifest, module, or runtime contract changes. Existing
Terraform contracts are inventoried, not modified here. Baseline and schema changes use reviewed
PRs; breaking schema changes require a major schema version and migration.

Adoption starts with the pinned inventory, then validation-only workflows, bounded backfill,
per-merge assessments, protected publication, and finally Terraform proposals.

## Security and identity

Azure managed identities, RBAC scopes, public access, private endpoints, DNS, routes, and subnets
remain unchanged. The assessment workflow can append only to the dedicated ledger branch and cannot
push to `develop`; its job-level repository token receives only the contents permission needed for
that branch. Cross-repository dispatch uses an ephemeral token from a GitHub App installed only on
the Terraform repository and only after protected-environment approval.

Privileged workflows do not execute untrusted PR-head code. Records and logs exclude credentials,
tenant and subscription IDs, private addresses, and environment-specific resource names. Target
test deployments use workload identity federation under Terraform-repository ownership.

## Adoption and rollback

Implement schemas and tests, publish the initial inventory and generated view, create reviewed
baseline-origin handoffs and initial proposals, enable the dedicated assessment ledger, backfill
recent merges, then enable assessment-origin publication gates.

Rollback by disabling the workflows and revoking the GitHub App installation or key. Retain the
ledger branch and mark obsolete records superseded; do not rewrite its history. Closing or rejecting
a Terraform PR never closes its gap automatically.

## Compliance verification

- Validate all JSON records against their schemas.
- Prove generated Markdown is byte-for-byte reproducible.
- Prove every capability has exactly two scenario assessments.
- Prove merged-PR event handling and dispatch are idempotent.
- Prove concurrent assessment events serialize append-only ledger commits without writing to
  `develop` or recursively triggering assessment.
- Prove every handoff has exactly one valid provenance form; pending baseline drafts carry only the
  baseline ID and digest, while approved baseline handoffs also prove the committed inventory blob
  and review.
- Prove publication is blocked without platform-recorded approval.
- Prove no parity declaration exists without matching deployment and reviewed comparison evidence.
- Run secret scanning over records, fixtures, and workflow logs.
- Treat build, lint, preflight, What-If, and Terraform plan only as their respective static evidence.

## Documentation impact

Implementation adds generated parity status, ownership guidance, and workflow operation guidance.
No current parameter, topology, or deployment runbook changes. Public AI Landing Zones
documentation needs review when Terraform proposals merge and alter consumer-visible parity.

## Review trigger

Review this decision when the integration branch changes, either release baseline advances, the
schema needs a breaking change, GitHub permission or App behavior changes, an authorization
incident occurs, the assessment backlog exceeds its agreed service level, or a hosted coordination
service becomes justified by scale.
