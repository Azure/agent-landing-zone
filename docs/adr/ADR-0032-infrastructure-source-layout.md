# ADR-0032: Separate infrastructure providers and centralize automation

**Status:** Accepted<br>
**Date:** 2026-10-30<br>
**Owners:** Agent Landing Zone maintainers<br>
**Decision basis:** Maintainer-approved infrastructure reorganization plan

## Context

The incorporated Bicep repository left standalone repository metadata, agents,
workflows, specifications, runbooks and a manual hub laboratory inside `infra/`.
Bicep occupies that directory's root, while the product-owned Terraform
composition already has a dedicated directory. These mixed responsibilities make
the current product entry points and sources of authority difficult to identify.

Prioritized characteristics and measures:

1. Discoverability: each provider has one entry point and every retained asset
   has a current product or validation consumer.
2. Behavioral compatibility: the same inputs produce equivalent compiled Bicep
   resources, dependencies and outputs, with no intentional Azure resource change.
3. Reproducibility: Terraform's provider lock, module pins and backend bindings
   remain unchanged.
4. Operational clarity: lifecycle hooks and infrastructure helpers share one
   automation root, with no compatibility wrappers at retired paths.
5. Evidence: existing local contracts continue to cover both providers and shells.

## Alternatives considered

### Separate providers and centralize automation (selected)

Use `infra/bicep/`, retain `infra/terraform/`, and share naming and role catalogs
under `infra/shared/`. Keep lifecycle hooks under root `scripts/`, moving their
infrastructure helpers to `scripts/infra/`.

This makes ownership explicit without introducing another provisioning layer.
It requires coordinated path changes in azd, hooks, tests, CI and documentation.
Identity, network isolation, runtime component compatibility and resource cost
are unchanged. The source change is reversible without migrating Azure state.

### Remove copied metadata but retain Bicep at the infrastructure root

This minimizes path changes, but retains an asymmetric layout and leaves the
distinction between provider-specific and shared assets implicit.

### Do not change

This avoids migration work but preserves obsolete repository automation and
multiple apparent sources of authority.

## Decision

- Move the Bicep entry point, tracked parameter seed, modules and Bicep-specific
  constants to `infra/bicep/`. Retain symbolic module names and deployment names.
- Keep Terraform under `infra/terraform/`, with its existing lock and pins.
- Move the shared abbreviation and RBAC role JSON catalogs to `infra/shared/`.
  Both providers consume these single copies.
- Keep root `manifest.json` and `main.parameters.json` authoritative. Preserve
  `infra.source` as Bicep provenance, not a local layout or Terraform version.
- Generate Bicep's parameter composition at its selected entry point. Keep
  Terraform's diagnostic-only parameter envelope separate under
  `infra/shared/main.parameters.json`, ignored by Git.
- Keep root azd hooks in place. Move retained infrastructure helper scripts to
  root `scripts/infra/` and resolve paths relative to their script or project
  root, never the caller's working directory.
- Remove obsolete incorporated repository metadata and the manual hub test
  laboratory, including its exclusive helpers. Do not create an archive
  directory. Preserve license attribution and current regression fixtures.
- Convert incorporated manifest data required by historical resource-graph
  regression checks into an explicitly named test fixture, not an active manifest.
- Keep support for existing hub-and-spoke infrastructure. Removing its synthetic
  test hub does not remove product peering, routing or existing-resource inputs.
- Do not change the remotely pinned bootstrap installer URL or its version.

This supersedes only ADR-0028's requirement to leave the Bicep entry-point path
unchanged. Its provider-selection, ownership, state and lifecycle decisions
remain in effect. ADR-0015's source incorporation and provenance remain in effect.

## Consequences

Operators using the checked-in `azure.yaml` retain the same root azd workflow.
Consumers with custom Bicep paths must update them to `infra/bicep/`. Consumers
must not use a standalone azd project inside `infra/`.

There is no state migration, provider switch, resource replacement, identity
change or new runtime dependency. Source consumers and validation tooling must
adopt the new paths together. Historical files remain recoverable in Git rather
than being retained as inactive product assets.

## Adoption and migration

Capture a local compiled baseline before moving files. Update both provider
imports, lifecycle hooks, validation consumers and active CI in the same change.
Keep upstream baseline checkouts at their original upstream layout.

Before updating an existing checkout, clear only the old parameter seed's
skip-worktree flag and preserve any private local input outside tracked source.
Bicep uses `infra/bicep/main.parameters.json` after the update. Terraform's native
input, state backend address, resource ownership and private bindings do not move.
Regenerate diagnostic parameters through the normal preprovision lifecycle.

Coordinate the matching `Azure/AI-Landing-Zones` documentation update with the
availability of this layout. Do not publish unreleased paths as current guidance.

Rollback is a coordinated source/path revert, not a provider conversion or Azure
resource recreation. Restore the matching azd configuration and helper paths
without altering state, backend bindings or deployed resources.

## Compliance verification

- Compare before/after compiled ARM semantically with the same compiler, ignoring
  only known compiler-generated metadata, not resource/deployment properties.
- Run Bicep build/lint, compiled foundation contracts and deterministic script
  tests against the reorganized source.
- Run Terraform formatting, backend-disabled read-only-lock initialization,
  validation and native mocked tests without changing dependency pins.
- Exercise input resolution and both lifecycle hook variants, including
  nondefault provider paths/modules, clean seeds and diagnostic-only artifacts.
- Guard against retired assets, broken active references and tracked generated
  parameters, plans, credentials or state.

No Azure evaluation, what-if, provisioning, apply or destruction is authorized
for this source-layout task. Local evidence is not deployed Azure parity.

## Documentation impact

Update the infrastructure README and engineering instructions to describe the
two providers, shared catalogs and single automation root. Update current product
deployment and Azure DevOps pages/examples in `Azure/AI-Landing-Zones`. Do not
rewrite historical ADRs or changelogs as if they had used the new layout.

## Review trigger

Reassess if providers become independently distributed products, azd changes its
entry-point contract, shared configuration ownership changes, or a retained
infrastructure asset loses its current product or validation consumer.
