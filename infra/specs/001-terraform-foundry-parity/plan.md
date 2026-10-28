# Implementation Plan: Terraform Parity for the Foundry AI Landing Zone

> **Historical plan:** Superseded by
> [ADR-0028](../../../docs/adr/ADR-0028-integrated-terraform-composition.md).
> The external assessment/publication pipeline is retired; the plan and its
> sibling records are not active implementation instructions.

**Branch**: `001-terraform-foundry-parity` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-terraform-foundry-parity/spec.md`

## Summary

Create repository-owned coordination assets that compare the released Bicep reference implementation
with the released Terraform AVM pattern module, produce one alignment assessment for every pull
request merged into `develop`, and hand approved gaps to a coding agent in the Terraform repository.
The design uses versioned JSON records validated by JSON Schema, a deterministic generated Markdown
view, PowerShell 7 validation and generation scripts, and human-gated GitHub Actions. Terraform
source, target-repository validation, deployment, and parity evidence remain owned by
`Azure/terraform-azurerm-avm-ptn-aiml-landing-zone`.

## Technical Context

**Language/Version**: PowerShell 7; JSON Schema draft 2020-12; GitHub Actions YAML

**Primary Dependencies**: Native PowerShell JSON support, a pinned JSON Schema validator,
GitHub Actions, GitHub App installation token for cross-repository dispatch

**Storage**: Version-controlled inventory and handoffs under `parity/` on the integration branch;
append-only alignment assessments under `parity/assessments/` on a dedicated
`terraform-parity-assessments` ledger branch; generated Markdown under `docs/`

**Testing**: Existing PowerShell test conventions; schema validation, deterministic generation,
fixture-based workflow tests, idempotency tests, and secret scanning

**Target Platform**: GitHub-hosted Windows and Ubuntu runners; GitHub.com repositories in the
`Azure` organization

**Project Type**: Repository automation and documentation

**Performance Goals**: Validate the complete inventory and generate its Markdown view in under
60 seconds in CI; process a merged-PR fixture deterministically without network access

**Constraints**: No Terraform source in this repository; no Azure mutation during coordination;
no long-lived personal token; no generated proposal without human approval; plan/What-If output is
not deployment evidence; standard and network-isolated evidence remain independent

**Scale/Scope**: All consumer-visible capabilities in Bicep `v2.6.1`; exactly two scenarios;
one append-only assessment per PR merged into `develop`; one active proposal or reviewed deferral
per actionable gap

**Pinned baselines**:

- Bicep: `v2.6.1` at `64195c01b70974fa7256c2f54a0035fb06804139`
- Terraform: `v0.5.1` at `abe337894f93de3ddda525ea44898b33e1484070`

These are implementation commits. The inventory artifact has its own exact-byte SHA-256 digest and,
only after review, a separate repository commit containing `parity/inventory.json`. Pending drafts
carry the baseline ID and digest only; inventory review and T033 handoff authorization are separate
approved-state records.

## Constitution Check

*GATE: Passed before Phase 0 and re-checked after Phase 1.*

| Gate | Design response | Status |
| --- | --- | --- |
| Orchestrator and module boundaries | No Bicep resource or module changes | Pass |
| Compatibility and parameterization | Inputs, defaults, outputs, runtime keys, and manifest fields are inventory data; no contract changes | Pass |
| Deployment-mode integrity | Standard and network-isolated scenario records and evidence are separate | Pass |
| Managed identity and secure networking | Azure identity, RBAC, endpoints, DNS, routes, and public access are unchanged; their invariants are compared | Pass |
| Evidence-based authorized change | Static evidence is typed separately from deployment evidence; publication and deployment require human approval | Pass |
| PowerShell and automation | PowerShell 7, explicit failures, quoted input, idempotent generation, and no secret logging | Pass |
| Release constraints | Baselines are pinned; advancing them is a reviewed PR; this feature does not publish a release | Pass |

Post-design re-check: all gates still pass. The schemas prohibit a parity declaration without
scenario-specific successful deployment evidence and reviewed comparison. Cross-repository write
access is isolated to a protected publication job using an ephemeral, narrowly scoped GitHub App
token. No constitutional exception is required.

## Architecture Characteristics

| Priority | Characteristic | Fitness measure |
| --- | --- | --- |
| 1 | Traceability | Exactly one assessment links each merged PR number and merge SHA to inventory gaps and proposals |
| 2 | Evidence integrity | No scenario is declared at parity without its own successful deployment and reviewed comparison |
| 3 | Compatibility | Every public input, output, default, and runtime contract is classified; breaking changes require migration and version impact |
| 4 | Authorization | Pending drafts are ineligible; no T033 proposal, cross-repository dispatch, or generated PR occurs without complete inventory provenance and separate recorded handoff approval |
| 5 | Recoverability | Workflows can be disabled and App access revoked without changing Azure or deleting audit records |

## Project Structure

### Documentation (this feature)

```text
specs/001-terraform-foundry-parity/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── inventory.schema.json
│   ├── assessment.schema.json
│   ├── terraform-handoff.schema.json
│   ├── parity-evidence.schema.json
│   ├── generated-markdown.md
│   ├── workflow-events.md
│   └── terraform-repository-interface.md
├── validation.md
└── tasks.md
```

### Source Code (repository root)

```text
parity/
├── config.json
├── inventory.json
├── assessments/  # append-only records on terraform-parity-assessments
└── handoffs/

scripts/parity/
├── Test-ParityAssets.ps1
├── Export-ParityMarkdown.ps1
├── New-AlignmentAssessment.ps1
└── New-TerraformHandoff.ps1

tests/parity/
├── fixtures/
└── *.Tests.ps1

docs/
├── terraform-parity.md
├── terraform-parity-ownership.md
└── adr/0003-repository-native-terraform-parity-coordination.md

.github/workflows/
├── terraform-parity-validate.yml
├── terraform-parity-assess.yml
└── terraform-parity-publish.yml
```

**Structure Decision**: `parity/` contains the machine-readable product records; `docs/` contains
generated and ownership views; `scripts/parity/` and `tests/parity/` contain deterministic
automation. The feature contracts stay beside the plan until implementation promotes matching
schemas into `parity/schemas/`.

## Delivery Sequence

1. Implement schemas, configuration, validators, and fixture tests.
2. Inventory the pinned Bicep and Terraform releases and generate the Markdown view.
3. Add drift validation and coverage checks to CI.
4. Create approved initial handoffs directly from the pinned inventory baseline.
5. Raise the initial Terraform proposals through the target repository's existing contribution path.
6. Enable per-merge assessments on `develop`, writing append-only records to a serialized dedicated
   ledger branch without direct pushes to `develop`.
7. Backfill a bounded set of recent merges and confirm idempotency.
8. Configure ownership, protected environment reviewers, and a least-privilege GitHub App.
9. Enable approved structured handoffs for ongoing changes.
10. Track Terraform merge, deployment, and reviewed parity evidence as follow-up work.

## Complexity Tracking

No constitution violations require justification.
