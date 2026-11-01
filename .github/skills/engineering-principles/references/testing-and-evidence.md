# Testing and evidence

Choose validation according to the changed boundary:

- Local logic: focused unit tests.
- Rendered Azure payloads or schemas: contract and fixture tests.
- Setup modules and adapters: integration-style tests with mocked Azure
  boundaries.
- PowerShell or shell hooks: syntax plus behavioral parity checks.
- Infrastructure: assess Bicep-to-Terraform and Terraform-to-Bicep parity for
  every change. Run the relevant checks for both implementations and their
  shared lifecycle; preserve Terraform's committed lock and module pins.
  Report counterpart changes or justified non-impact, approved differences
  and unverified scenarios. Compare behavior/contracts rather than generated
  names, and never describe compilation, mocks or a plan as deployed parity.
- Multi-repository changes: validate the exact commit or tag combination that
  will be pinned in `manifest.json`.
- Identity and document authorization: negative tests proving an unauthorized
  principal cannot access protected content.

For every change, capture:

1. Acceptance criterion and observable result.
2. Commands run and their results.
3. Configuration and component versions used.
4. Compatibility, migration, and rollback impact.
5. Validation that could not run and the resulting risk.

Do not treat a successful deployment as sufficient evidence when the change
affects authorization, data correctness, retrieval quality, or upgrade
behavior.
