# Offline infrastructure contracts

Run from the repository root with PowerShell 7 and Azure CLI Bicep **0.42.1**
(the historical fixture compiler, not a runtime dependency pin):

```pwsh
pwsh -NoProfile -File infra/tests/Invoke-OfflineContracts.ps1

# Narrow selections before running the full suite:
pwsh -NoProfile -File infra/tests/contracts/Test-ScopedGraphNormalizationContract.ps1
pwsh -NoProfile -File infra/tests/contracts/Test-SolutionStorageAccessContract.ps1
pwsh -NoProfile -File infra/tests/scripts/Invoke-PreflightChecks.Tests.ps1
pwsh -NoProfile -File infra/tests/contracts/Test-PostgreSqlContract.ps1
pwsh -NoProfile -File infra/tests/scripts/Test-PostgreSqlPreflight.Tests.ps1
python -m pytest infra/tests/test_postgresql_interface.py tests/test_terraform_interface.py -q
```

The runner executes every `contracts/Test-*Contract.ps1` and
`scripts/*.Tests.ps1`, reports exit codes and elapsed time, and fails if any
check fails. Unique compiler/runtime scratch directories are cleaned in
`finally`. No Azure credentials, evaluation, what-if, deployment or writes are
required. Bicep registry dependencies must already be available for offline
compilation. Active CI is root
[`infra-validate.yml`](../../.github/workflows/infra-validate.yml).

## What remains covered

- The actual `infra/bicep/main.bicep` compiled resource graph: feature flags,
  hosted agents, Storage ACL forwarding and typed rejection, resource-group
  ownership/RBAC, subnet creation and reserved subnet rules, private endpoints,
  naming, firewall policy and maintenance wrappers.
- Deterministic preflight and operator-access tests using mocks, plus size-gate
  defaults and all warning/failure paths in root `scripts/infra/`.
- The external Terraform automation retirement guard, scanning current
  operational source and rejecting retired dispatch and credential references.

Terraform's native mocked contracts remain under
[`infra/terraform/tests/`](../terraform/tests/); shared lifecycle and input
contracts remain under root [`tests/`](../../tests/). These offline checks do
not demonstrate deployed provider parity, live DNS, RBAC or resource persistence.

PostgreSQL counterpart plans are in `infra/terraform/tests/postgresql.tftest.hcl`.
Use `terraform -chdir=infra/terraform init -backend=false -lockfile=readonly`,
then `validate` and `test`. On Windows the narrow native filter is
`-filter=tests\postgresql.tftest.hcl`; on Unix use
`-filter=tests/postgresql.tftest.hcl`. Always check the executed test count:
a mismatched path can execute zero tests.
The new cases distinguish a Consumption profile in a workload-profiles
environment from legacy Consumption-only ACA, and check explicit server
settings, dedicated NAT, exact firewall ranges and all three DNS owners.

## Historical graph fixtures

`contracts/fixtures/` records reviewed exact before/after graph deltas.
`ScopedResourceGroupNormalization.ps1` checks those deltas before projecting
the compiled graph to its historical representation; it never mutates the
actual deployment graph. Mutation tests reject unrelated resource, scope,
security, subnet, output and manifest drift. **Do not reset fingerprints just
to make tests pass.**

`SubnetConditionalReferencesNormalization.ps1` checks the bounded deterministic
subnet `resourceId(...)` and explicit network-module `dependsOn` delta at the
front of the normalization pipeline before restoring the pre-change inlined
subnet representation, leaving `PostgreSqlNormalization.ps1` digests and all
historical fixtures untouched. `Test-SubnetConditionalReferencesContract.ps1`
proves why conditional cross-resource-group 1-argument `reference(...)` inside
`map(...)` fails ARM validation, asserts zero `reference(` calls in compiled
subnet expressions, verifies exact scopes across single-RG, split network RG,
cross-subscription `useExistingVNet`, and BYO route table / NAT gateway
passthroughs, and rejects missing `dependsOn` edges.

`PostgreSqlNormalization.ps1` is the bounded optional-PostgreSQL delta against
the pre-feature graph, using Bicep 0.42.1. Both sides of changed fields are
pinned; complete added AVM modules are protected by canonical digests instead
of copied templates. Every accepted path has a rejection mutation. This runs
before the original projections and leaves all historical fingerprints intact.
`postgresql_disabled_ast.py` separately proves that the actual compiled graph
with PostgreSQL disabled is equivalent to that exact pre-feature graph in
**both** network modes: only Boolean gates/if, identity filters and empty-array
concat are reduced; unknown ARM functions/references remain opaque. It also
rejects independent semantic mutations, without relying on the digest guard.
This is bounded static evidence, not an ARM evaluator. Enabled security,
ownership, DNS, NAT and the deliberate Bicep/Terraform native output difference
are tested separately in `Test-PostgreSqlContract.ps1` and Terraform mock plans.

`embedding-default-normalization.json` permits only the intentional embedding
fallback SKU change from `Standard` to `GlobalStandard`. It checks the complete
native list-selection expression, preserving the explicit-list passthrough,
model/version and fallback capacity 10 before restoring the historical SKU.
The scoped graph contract rejects SKU/model/version/capacity and custom-list
mutations. Existing baseline fixtures and fingerprints remain unchanged.

`native-platform-normalization.json` records the exact ADR-0034 delta from
pre-native `951a1df` to `86a19f0`, compiled with the same Bicep 0.42.1. It
validates the complete native scheduler/hub and hub-scoped client/worker grants,
default-off inputs, returned-endpoint handoff, worker ingress forwarding, and
the complete PE/DNS expressions before the existing adapters run. The single
DTS endpoint and zone are prepended without rewriting any legacy branch.
Mutation checks cover isolation, public access, PE placement/group, DNS reuse
and policy ownership, grant scope/consumers, resource injection, and every
deploying native delta. No endpoint array is ignored and no historical
fingerprint is regenerated. This is offline compiled-contract evidence, not
live DTS, private DNS, RBAC or provider-parity validation.

`historical-foundation-manifest.json` contains exactly the four fields from
the retired incorporated manifest at `v2.7.3`. It is only a regression fixture,
not deployment or release configuration. The normalizer first checks the
compiled manifest against the actual repository-root manifest and verifies
`infra.source.tag` against the historical fixture. Existing incorporation
allowlists continue to protect source/component pins and shape. The Storage
contract checks the projected manifest against the exact fixture, including
negative mutations, then normalizes only `tag` and `ailz_tag` to `v2.6.1` for
the original variable fingerprint. No copied changelog or release helper is
needed. The original hosted-agent and Storage fingerprints remain unchanged.

Contracts accepting `-MainFile` expect the same `infra/bicep/` layout and
corresponding root manifest and parameters in isolated regression checkouts.
The maintenance fixture imports the real moved Bicep wrapper.

The copied engineering-agent/release-workflow tests and synthetic manual hub
lab have been removed with their obsolete assets. Existing hub-and-spoke
product capabilities remain supported; operational guidance belongs in the
[central documentation](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/),
not a second deployment project here.
