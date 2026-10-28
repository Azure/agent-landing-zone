# Quickstart: Validate Terraform Parity Coordination

> **Retired:** Do not run these historical commands against the current checkout.
> [ADR-0028](../../../docs/adr/ADR-0028-integrated-terraform-composition.md)
> supersedes this coordination pipeline. Use the current
> [offline test harness](../../tests/README.md) instead.

This guide validates coordination assets. It does not deploy Azure resources or prove Terraform
parity. Commands under `scripts/parity/` become available during implementation.

## Prerequisites

- PowerShell 7
- Node.js 20 or later and npm
- Git
- Repository checkout at the feature implementation commit
- No Azure credentials are required for deterministic validation

Install the exact-pinned local JSON Schema validator:

```powershell
npm ci --ignore-scripts
```

## 1. Validate contracts and records

```powershell
pwsh ./scripts/parity/Test-ParityAssets.ps1
```

Expected result:

- all JSON records pass their schemas;
- source baseline is Bicep `v2.6.1` at `64195c01b70974fa7256c2f54a0035fb06804139`;
- target baseline is Terraform `v0.5.1` at `abe337894f93de3ddda525ea44898b33e1484070`;
- every capability has exactly the standard and network-isolated scenario entries;
- no duplicate capability, assessment, handoff, or evidence IDs exist;
- pending baseline drafts match the active baseline and exact inventory-byte digest but have no
  inventory commit or review claim;
- only approved handoffs with verified provenance and complete authorization are proposal-eligible;
- no parity declaration lacks scenario-specific deployment and reviewed comparison evidence.

Run the foundational malformed-record and cross-record fixture suite:

```powershell
npm run test:parity
```

## 2. Check generated documentation

```powershell
pwsh ./scripts/parity/Export-ParityMarkdown.ps1 -Check
```

Expected result: `docs/terraform-parity.md` is byte-identical to deterministic output from
`parity/inventory.json`.

## 3. Exercise assessment and workflow fixtures

```powershell
pwsh ./tests/parity/Test-AlignmentAssessment.Tests.ps1
pwsh ./tests/parity/Test-ParityWorkflowYaml.Tests.ps1
pwsh ./tests/parity/Test-LedgerAppendOnly.Tests.ps1
pwsh ./tests/parity/Test-WorkflowEventContract.Tests.ps1
pwsh ./tests/parity/Test-WorkflowSecurity.Tests.ps1
pwsh ./tests/parity/Invoke-ParityWorkflow.Tests.ps1
```

Fixtures must cover:

- no Terraform impact;
- standard-scenario impact;
- network-isolated impact;
- unsupported provider capability recorded as blocked;
- breaking Terraform contract requiring migration;
- duplicate merged-PR delivery.

Expected result: each unique merged PR creates one assessment, duplicate delivery creates none,
concurrent events serialize append-only writes to `terraform-parity-assessments`, and no assessment
workflow writes to `develop`.

Prove ledger coverage against the fetched integration branch. Always validate against
`origin/develop`; a local `develop` ref is a stale snapshot:

```powershell
git fetch --no-tags origin '+refs/heads/develop:refs/remotes/origin/develop'
pwsh ./scripts/parity/Test-AssessmentCoverage.ps1 -Branch origin/develop
```

Expected result: every merge after the adoption commit recorded in
`parity/assessments/adoption-marker.json` has exactly one assessment, every assessment
references a merge commit that is on the integration branch, and no first-parent commit
after the adoption commit lacks a pull request reference. Use `-Branch HEAD` only to
validate the merge commit currently checked out, and `-AllowUnattributedCommits` only
for an integration branch that is not yet protected against direct pushes.

## 4. Exercise approval and handoff fixtures

```powershell
pwsh ./tests/parity/Test-TerraformHandoff.Tests.ps1
pwsh ./tests/parity/Test-NewTerraformHandoff.Tests.ps1
pwsh ./scripts/parity/Test-ParityAssets.ps1
```

Expected result:

- pending, rejected, or superseded handoffs cannot dispatch, authorize T033, or satisfy proposal
  eligibility;
- an approved proposal-required assessment covering every capability produces one schema-valid
  alignment handoff;
- a pending baseline draft needs only baseline ID and exact-byte digest;
- approved baseline provenance requires a commit containing the digest-matching inventory and an
  auditable inventory review URL, separately from handoff approval metadata;
- the pinned Bicep source SHA fails as inventory provenance because that commit has no
  `parity/inventory.json`;
- each handoff contains exactly one provenance form;
- repository, branch, baseline, and capability mismatches fail explicitly;
- duplicate dispatch returns the existing proposal reference;
- the handoff contains no Terraform source, credential, tenant ID, or subscription ID.

Issue #136 supplies design context only; it is not inventory review or handoff approval evidence.
The five checked-in baseline handoffs are approved against the reviewed inventory commit, carry
separate T033 authorization, and link their upstream draft Terraform proposals. Proposal status
does not claim deployment or functional parity.

## 5. Validate repository assets

```powershell
pwsh ./.github/scripts/Validate-CopilotAssets.ps1
pwsh ./tests/scripts/Validate-CopilotAssets.Tests.ps1
```

Expected result: existing Copilot assets remain valid after adding parity agent instructions.

## 6. Check publication safety and performance

```powershell
pwsh ./tests/parity/Test-ParityPublication.Tests.ps1
pwsh ./tests/parity/Test-ParityPerformance.Tests.ps1
```

Expected result:

- only an approved handoff with fresh baselines, an allow-listed target repository and branch, and
  an open inventory gap produces a bounded identifier-only dispatch payload;
- a recorded Terraform proposal is reconciled instead of dispatched twice, and target rejection
  fails explicitly while leaving the gap open;
- complete inventory validation plus deterministic Markdown generation finish within 60 seconds.

Publication itself is never run locally. It requires the protected
`terraform-parity-publication` environment and an ephemeral GitHub App token, as described in
`docs/terraform-parity-ownership.md`.

## Follow-up deployment evidence

Actual `terraform apply` runs occur only in an approved test subscription from the Terraform
repository. Standard and network-isolated scenarios run separately. The sanitized run URL and
reviewed capability comparison are then recorded through a reviewed inventory update. `terraform
validate`, `terraform plan`, Bicep compilation, preflight, and What-If do not count as deployment
or parity evidence.
