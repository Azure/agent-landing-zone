---
applyTo: "scripts/**/*.ps1,scripts/**/*.sh,azure.yaml"
---

# azd lifecycle hooks

- Keep PowerShell and shell hooks behaviorally equivalent.
- Treat hook ordering and environment-variable propagation as public
  deployment behavior.
- Preserve `azd` environment reuse when component repositories are cloned and
  deployed.
- `infra/` is repository-owned, foundation-only source; change it through
  reviewed edits and keep `manifest.json` `infra.source` accurate. Read
  configuration under App Configuration label `agent-lz`.
- Validate every shared lifecycle change against both Bicep and Terraform.
  Respect provider selection, typed input/output adapters, original resource
  ownership and backend bindings; do not assume Bicep parameter envelopes or
  group-wide teardown apply to Terraform. Update affected counterparts together
  or document and test why the other provider is unchanged.
- Quote paths and external input safely. Do not echo secrets or private Azure
  validation environment names.
- Surface failed prerequisites and provisioning steps; do not continue with a
  success-shaped fallback.
- Validate both platform variants when changing shared hook behavior.
- Load `documentation-consistency` when the deployment flow or operator steps
  change.
