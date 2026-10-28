# ADR-0015: Incorporate the AI Landing Zone infrastructure into the repository

**Status:** Accepted<br>
**Date:** 2026-10-01<br>
**Owners:** Agent Landing Zone maintainers<br>
**Approver:** Paulo (maintainer)

**Partial supersession:** [ADR-0028](ADR-0028-integrated-terraform-composition.md)
supersedes the external Terraform location and synchronization requirement.
The Bicep incorporation and provenance decision remains in effect.

## Context

`infra/` is a read-only git submodule of `Azure/bicep-ptn-aiml-landing-zone`,
pinned by `ailz_tag` in `manifest.json` (last pinned tag `v2.7.3`). Operators
who clone without `--recursive` get an empty `infra/`, and every infrastructure
change requires a separate release in another repository. The consolidation
(ADR-0014) requires the infrastructure to be part of Agent Landing Zone and
released with a single version (spec FR-010a to FR-010e; research R4).

The infrastructure also has a Terraform counterpart,
`Azure/terraform-azurerm-avm-ptn-aiml-landing-zone`, kept in parity by a
workflow in the infra repository (R5).

Prioritized characteristics and measures:

1. Behavior preservation: the same parameters produce the same resources,
   apart from renamed identifiers (FR-010b).
2. Auditability: one provenance commit names the source repository, tag, and
   commit (FR-010a, R4).
3. Single version: `manifest.json` no longer pins a separate infra version
   (FR-010e).
4. Terraform parity with mandatory human review (FR-010c, R5).

## Alternatives considered

### Option A: Copy files at `v2.7.3` as tracked source (selected)

- Simple to review, no clone flags required, provenance recorded (R4).
- Earlier history stays in the source repository and is not imported.

### Option B: Keep the submodule

- No migration effort, but fails consolidation (FR-010a). Rejected.

### Option C: git subtree

- Imports history, but adds history noise and harder review (R4). Rejected.

### Option D: Bicep registry module

- No Bicep registry workflow is in place (R4). Rejected.

### Terraform sync options

- Bicep only: breaks Terraform users. Fully automatic sync: risk of silent
  drift. Both rejected (R5).

### AVM resource modules

- A hybrid AVM approach is still being evaluated for dependency and
  maintenance risk; adopting it now adds risk to a dated release (R6).
  Deferred.

## Decision

- Copy the files of the last pinned tag (`v2.7.3`, or a later tag if one is
  pinned before the copy) into `infra/` as regular tracked source in one
  provenance commit that names the source repository and tag (FR-010a).
- Record provenance in `manifest.json` under `infra.source` (repo, tag,
  commit). Remove `.gitmodules` and `ailz_tag` in the same change (R4,
  FR-010e).
- Bicep remains the source of truth. Move `infra-terraform-parity.yml` into
  this repository; it detects Bicep changes and opens a Terraform sync PR
  against `Azure/terraform-azurerm-avm-ptn-aiml-landing-zone` that requires
  human review. The Terraform module is not renamed (R5, FR-010c).

  **Maintenance update:** The automatic parity-PR workflow has since been
  retired before ADR-0028. ADR-0028 also retires the inherited external
  assessment/publication pipeline in favor of product-owned Terraform
  composition and local contract/parity review.

- Infrastructure validation workflows run from this repository (FR-010c).
- Keep current module usage; AVM adoption is out of scope (R6).
- `Azure/bicep-ptn-aiml-landing-zone` stays available with history and tags
  until frozen and archived. Before archival, open issues and PRs are
  triaged, and its README states exactly "This repository has moved to
  Azure/agent-landing-zone." with a link. It receives no new development;
  existing consumers keep their pinned tags (FR-010d).

## Consequences

- Infra changes are reviewed and released with the product version.
- Renamed identifiers inside `infra/` fall under the naming inventory and scan
  (FR-003, R17).
- The repository grows by the infra source; history before the copy must be
  consulted in the source repository.
- Maintainers own Terraform parity review.

## Adoption and migration

1. Provenance commit with the unchanged `v2.7.3` files.
2. Manifest, `.gitmodules`, and `ailz_tag` changes in the same change set.
3. Move validation and parity workflows; then apply renames in Phase 2.

Rollback: restore `.gitmodules` and `ailz_tag` pinned to `v2.7.3` and remove
the copied folder.

## Compliance verification

- Deployment with the same parameters is compared against the last pinned
  version (FR-010b).
- Tests assert `manifest.json` has `infra.source` and no `ailz_tag`, and that
  `.gitmodules` is absent.
- Parity workflow opens a reviewable PR; no auto-merge.

## Documentation impact

Constitution Principle I and Sources of Truth (`infra/` becomes repo-owned
source), AGENTS.md, contributor guidance, and the archive notice in the
source repository.

## Review trigger

Reassess when the hybrid AVM evaluation concludes, the Terraform module is
renamed or moved, or a Bicep registry workflow becomes available.
