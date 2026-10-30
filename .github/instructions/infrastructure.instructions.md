---
applyTo: "infra/**,scripts/infra/**"
---

# Infrastructure source and helpers

- Follow root `AGENTS.md` and ADR-0032. Keep Bicep in `infra/bicep`, Terraform
  in `infra/terraform`, shared JSON catalogs in `infra/shared`, and operational
  helpers in root `scripts/infra`. Do not restore standalone repository metadata,
  workflows, manifests, release tooling or the retired manual hub laboratory.
- Keep Bicep's orchestrator, symbolic module names, feature gates, dependencies
  and typed interfaces stable during source moves. Use the shared naming and
  role catalogs instead of duplicating identifiers.
- Preserve Terraform's committed provider lock, explicit module pins and backend
  bindings. Do not use Bicep deployments as Terraform implementations.
- Root `manifest.json` and `main.parameters.json` are authoritative. Never commit
  generated environment-specific inputs, diagnostics, state, plans or credentials.
- Keep the Bicep tracked seed usable in a clean clone. Preserve the native azd
  provider/path/module selection and both PowerShell and shell hook behavior.
- Resolve helper paths from the script/project root, not the caller's directory.
  Fail explicitly for missing required inputs.
- Validate both providers, compiled resource contracts and relevant hooks. Local
  compilation and mocked tests do not establish deployed Azure parity.
