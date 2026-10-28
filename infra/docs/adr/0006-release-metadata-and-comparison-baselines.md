# ADR-0006: Separate release metadata from historical parity comparisons

> The external parity ledger and publication portions are superseded by
> [ADR-0028](../../../docs/adr/ADR-0028-integrated-terraform-composition.md).
> The release metadata guard remains in use; the comparison and handoff details
> below are historical and do not require restoring the retired tooling.

- Status: accepted for implementation; integrated into develop by #165
- Date: 2026-09-18
- Owners: AI Landing Zone maintainers and parity reviewers
- Related issues or pull requests: #159, #160, feature PR #164, candidate PR #165

## Context

Prepare a reviewable `v2.7.0` candidate without rewriting parity history.
The feature adds backward-compatible Storage inputs, making the combined
release minor. `develop` includes released `main` through #161. Candidate
implementation starts at `ff6b7589022ca79d5b74f07e8f865b04ca22d7f3`.
The candidate subsequently includes the parent's documentation-only
`803e20f72660c9e856880fcf2f578fc6b298fe04` and the normal #164 integration
merge `3d88122ae53d873d68a3d8469525e7cab98b89a1`. Integrating that history
into the candidate branch did not change its validated file tree.

`Test-BaselineContract.Tests.ps1` originally required both manifest tags and the
configuration/inventory source tag to equal `v2.6.1`. The inventory collector
reads pinned Git content, not the candidate working tree. Config and inventory
remain the Bicep `v2.6.1` / `64195c01b70974fa7256c2f54a0035fb06804139`
versus Terraform `v0.5.1` / `abe337894f93de3ddda525ea44898b33e1484070`
comparison. Assessments reference that inventory, and handoff provenance can
include its exact digest. A release bump is not authorization to replace any
of those records or evidence.

The Storage regression test also fingerprints every root variable. Bicep
0.42.1 emits `_manifest` as `[variables('$fxv#0')]`, with the loaded JSON in
`$fxv#0`. Changing only the two manifest versions changes those two compiled
values and the top-level compiler `templateHash`; the remaining parsed
template is identical. Both original guards reject this version-only change.
The manifest is used by bootstrap URLs/commands, runtime `RELEASE` keys and
the `RELEASE` output. It is not merely documentation.

## Prioritized characteristics

| Characteristic | Priority | Measure |
| --- | --- | --- |
| Historical integrity | 1 | No config/inventory/record/digest changes; all four comparison tag/SHA pairs remain pinned. |
| Narrow compatibility | 2 | Only the two verified release fields are normalized; original graph fingerprints remain unchanged. |
| Release consistency | 3 | Equal exact semantic tags match the latest unique versioned changelog heading. |
| Reviewability | 4 | Proposed status, explicit blockers and rollback; no inferred waiver or publication. |
| CI coverage | 5 | Manifest/changelog/shared-guard-only changes run both validation workflows. |

## Alternatives considered

### Option A: Independent release and comparison guards

Validate manifest/changelog consistency separately from pinned historical
comparisons. Before graph hashing, prove the exact compiled manifest binding
and equality with the actual manifest; clone root variables and normalize only
the loaded object's `tag` and `ailz_tag` to the original fingerprint's
`v2.6.1`. No hash is regenerated. Preserve repo, components, additional fields,
all other variables, resources and outputs. Negative mutations must fail for
the intended reason. No product modules, RBAC, topology or resource cost change.

### Option B: Review a new comparison baseline for every release

Coordinate a new inventory, reviewed comparison evidence and explicit
supersession of affected records with each release. This can provide a current
snapshot, but needs a separately designed history/migration contract; the
current validator accepts one active inventory and existing records reference
it. Updating only pins or approved-record references would invalidate evidence,
not complete that migration. This remains a viable separately approved project,
not work implicitly authorized by preparing this candidate.

### Do not change

Keep `v2.6.1` metadata and stop candidate preparation. This avoids a governance
change but cannot produce a consistent `v2.7.0` candidate with existing guards.
Skipping tests or silently changing their fingerprints is not an alternative.

## Decision

**Select Option A for the requested autonomous release workflow.** The
implementation was integrated through #165 after all normal CI gates passed.
This decision does not approve an Azure deployment or a Terraform handoff.
Historical comparison pins and
all approval, digest, provenance, ledger coverage and publication gates remain
enforced. Baseline advancement still requires a separate reviewed change.

The shared release assertion permits a versioned changelog section marked
`Unreleased`, so preparation does not invent a publication date. It does not
prove that a tag exists or authorize creating one. At publication, maintainers
must separately verify the approved commit, release date, Git tag and GitHub
Release title, all using exactly `v2.7.0`.

## Consequences

Releases can be prepared without presenting historical comparison evidence as
current runtime parity. The inventory can lag the current product release;
ongoing reviewed assessments and handoffs describe intervening impact. Owners
must not confuse independent versioning with permission to skip minor-release
Portal and Terraform review. Additional CI runs consume runner time only.

## Compatibility and migration

No Bicep source, parameter, output name, AVM pin, naming mode, bootstrap schema
or component pin changes. This proposal changes repository guard semantics.
Candidate versions intentionally affect bootstrap and runtime release metadata.
Do not deploy the unpublished candidate: its release URL/tag is not available.
Consumer overlays remain supported; the upstream graph test intentionally
rejects unrelated overlay changes as a different comparison, not as proof
that those consumer manifests are invalid.

No inventory-history migration is included. Do not rewrite config, inventory,
assessments, approvals, handoffs or digests. Collector expectations stay
188 inputs and 61 outputs against the historical source.

## Security and identity

No Azure operation, identity, RBAC, private endpoint, DNS, network-isolation,
permission, environment protection or GitHub App change. Workflow permissions
and dispatch gates are unchanged. New negative cases prevent manifest content
from being hidden behind the release normalization, including a manifest
`_generator` field that is data rather than compiler metadata.

## Adoption and rollback

1. Preserve normal feature and candidate integration through #164 and #165,
   with successful exact-head CI and no policy bypass.
2. Retain the Portal/Terraform source-impact review in ADR-0005 and coordinate
   the separately validated public documentation. Source review does not
   certify runtime parity or approve a handoff.
3. Record the unexecuted Azure scenarios explicitly in the release notes.
   Operators must obtain approved preview/test-scope evidence before production
   adoption; publication does not authorize those Azure operations.
4. Under the user's release request and delegated autonomous execution, set the
   publication date, verify the exact release commit and aligned versions,
   promote through the normal release PR and publish the matching tag/release.

The initial candidate was prepared as a review-only proposal. The subsequent
instruction to finish the release autonomously selected this bounded change;
it did not authorize ledger rewriting, approval fabrication, Azure deployment
or Terraform dispatch.
Rollback the proposal by reverting its guard/docs/metadata change together.
Do not reset historical records or rebaseline hashes. Azure rollback of the
feature is a separate operator decision described in ADR-0005.

## Compliance verification

- Release contract: actual metadata, valid versions, invalid/mismatched tags,
  duplicate/stale changelog sections, YAML parsing and both event path filters.
- Baseline contract: actual comparison pins plus mutation of every tag/SHA in
  both configuration and inventory; `Test-ParityAssets.ps1` stays untouched.
- Storage contract: actual compiled manifest binding/equality, original graph
  hashes, targeted manifest/variable/resource/output mutations and existing
  typed fixtures/profile matrix.
- Exact version-only before/after template comparison: only two loaded manifest
  fields and top-level compiler hash change. Build/lint with Azure CLI Bicep
  0.42.1, unchanged size gate, deterministic preflight and Copilot checks.
- Live Azure evidence remains outstanding and is disclosed as such. Compilation
  is not evidence of successful deployment or runtime parity; deployment and
  handoff approvals remain separate.

Current guidance: [Azure Well-Architected safe deployment practices](https://learn.microsoft.com/azure/well-architected/operational-excellence/safe-deployments)
requires quality gates, explicit recovery and controlled deployment. Azure
best-practice MCP calls timed out; current first-party guidance was retrieved
read-only through Microsoft Learn instead.

## Documentation impact

Update README, candidate changelog, test documentation, parity ownership and
the parity-view generator/footer. Inventory content and evidence remain
unchanged. Public feature documentation is coordinated separately in
[Azure/AI-Landing-Zones#139](https://github.com/Azure/AI-Landing-Zones/pull/139);
this repository-guard proposal does not change public
deployment defaults or constitute publication of that documentation.

## Review trigger

Revisit when Bicep changes the compiled manifest representation, manifest
fields or bootstrap behavior change, comparison baselines need advancement,
historical inventory retention is designed, or a release gate permits drift.
