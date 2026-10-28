# External Terraform parity automation retirement

[ADR-0028](../../docs/adr/ADR-0028-integrated-terraform-composition.md)
retires the inherited external assessment, ledger, approved-handoff and
publication pipeline. It does not declare the new Terraform composition
deployment-validated.

The three inherited `terraform-parity-{assess,publish,validate}.yml` workflows,
exclusive engineering agent/skill, `scripts/parity/`, `tests/parity/`,
`parity/` records/schemas, generated status and operator runbooks, and the
parity-only npm manifest/lockfile are removed. Do not run the former npm suite
or recreate its source pins, approvals or dispatch payloads. Prior content
remains available in Git history. Historical ADRs and specifications remain
explicitly superseded.

The root `infra-terraform-parity.yml` workflow was already removed in
`017fd93`; this retirement does not remove or recreate it. All existing root
workflows remain in place. Foundation, architecture, release-metadata and
Copilot-asset validation continue independently of external synchronization.
The strict workflow YAML reader now lives at `scripts/WorkflowYaml.ps1` with
generic tests under `tests/scripts/`.

Run the [offline harness](../tests/README.md) for foundation validation. Its
retirement contract rejects external target/dispatch, environment, credential,
ledger and legacy entrypoint references in operational workflows and
engineering assets, while allowing local Terraform validation. Historical
ADRs, specifications and changelogs are intentionally outside that scan.

## Coordinator-owned remote cleanup

Source cleanup does **not** remove any remote GitHub configuration. On
2026-10-27 the coordinator reported completing the remote consumer check and
cleanup:

- No active Actions workflow or workflow file on `main` consumed the dedicated
  environment; no dedicated repository/environment secrets were listed.
- The `terraform-parity-publication` environment was deleted and its absence
  verified with HTTP 404.
- Shared GitHub Apps and workflow run/deployment history were unchanged.

This is coordinator-provided evidence, not a remote operation performed by the
source cleanup. Remote ownership remains with the coordinator. Do not delete
shared GitHub Apps, historical workflow runs/deployments, or remote
repositories. No publication or Azure deployment is part of this cleanup.

No runtime component, manifest pin, Bicep deployment interface or hook changes
are required by this retirement. New Terraform implementation and public
deployment documentation are coordinated separately under ADR-0028.
