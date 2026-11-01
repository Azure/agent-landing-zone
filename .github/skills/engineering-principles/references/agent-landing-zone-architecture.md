# Agent Landing Zone architecture

## Purpose and boundaries

Agent Landing Zone is an Azure solution accelerator, not a monolithic application. This
repository owns platform configuration, deployment composition, shared
contracts, and release pins. Runtime behavior belongs to the component
repositories referenced by `manifest.json`.

Preserve these boundaries:

- `config/` configures provisioned Azure services.
- `scripts/` coordinates `azd` lifecycle operations.
- `main.parameters.json` expresses deployment topology.
- `manifest.json` binds a validated multi-repository release.
- `manifest.json` `infra.source` records the incorporated Bicep provenance,
  not the local Terraform composition.
- `contracts/` contains shared versioned schemas.
- `infra/` is repository-owned foundation source, changed only through reviewed edits;
  `infra/bicep/main.parameters.json` is a tracked seed regenerated locally by
  `preProvision`; generated private values must not be committed.
- `infra/bicep/main.bicep` and `infra/terraform` implement the same platform contract.
  Assess every infrastructure change in both directions and update affected
  counterparts in the same coordinated change.
- `infra/shared/` contains catalogs used by both providers. Keep lifecycle hooks
  in root `scripts/` and infrastructure helpers in `scripts/infra/` (ADR-0032).

## Design questions

Before changing a boundary, ask:

1. Which repository owns the behavior?
2. Is the change configuration, provisioning, runtime behavior, or a shared
   contract?
3. Which identities and trust boundaries are crossed?
4. Does it preserve Basic, network-isolated, and supported upgrade paths?
5. Which component versions must be validated together?
6. What is the rollback or roll-forward path?

Prefer a focused module or adapter over adding conditionals to an unrelated
setup path. Prefer explicit, typed contracts over implicit dictionaries or
duplicated environment-variable knowledge.

## Sources of truth

- Read release and component versions from `manifest.json`.
- Read deployment defaults and topology from `main.parameters.json`, the shared
  typed resolver and both executable infrastructure implementations.
- Read runtime behavior from the pinned component repository and tag.
- Read product documentation from `Azure/AI-Landing-Zones` main and the
  published central site, not a local documentation branch.
- Record significant platform decisions in `docs/adr/`.
