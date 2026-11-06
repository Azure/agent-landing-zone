# Validation quickstart

Implementation/evidence guide for `feature/postgresql-opcional`, not a released
or Azure-validated feature. The requester authorized local implementation and
explicitly excluded Azure deployment/destructive validation. T039/T040 remain
**NOT EXECUTED / deferred**. No Azure resource deployment, cleanup, release or
manifest pin update was performed in this scope.

## Prerequisites

Python >=3.10, Azure CLI, azd, PowerShell7, pinned Bicep v0.42.1 and Terraform
1.13+ with the committed provider lock. Operator needs an explicit Entra admin
principal, foundation deployment and server-scope lock permissions.

Use fresh workload-profiles ACA, delegated subnet at least /27 (retain current
/24 seed), no conflicting forced default route. Legacy Consumption-only
environment is unsupported. Private cases require a connected host; Basic
bootstrap requires an explicitly allowed operator egress IPv4.
Use an approved custom test ACA consumer with managed identity and verified TLS,
not a bundled runtime change.

## Existing repository checks

Run from repo root with current dependencies; restore only after a missing
dependency failure. Commands are discovered from current repository/CI.
The ledger below distinguishes executed offline checks from the remaining
provider/live gates. Do not infer completion from this command catalogue.

```powershell
python -m pytest tests\test_deployment_inputs.py tests\test_platform_outputs.py tests\test_infra_provider_hooks.py tests\test_terraform_interface.py tests\test_private_network_hooks.py --quiet
python -m pytest tests\test_postgresql_deployment.py tests\test_postgresql_bootstrap.py --quiet
az bicep build --file infra\bicep\main.bicep --outfile "$env:TEMP\agentlz-postgresql-main.json"
az bicep lint --file infra\bicep\main.bicep
pwsh -NoProfile -File infra\tests\Invoke-OfflineContracts.ps1
terraform -chdir=infra\terraform fmt -check -recursive
terraform -chdir=infra\terraform init -backend=false -lockfile=readonly
terraform -chdir=infra\terraform validate
terraform -chdir=infra\terraform test
```

Add new PG cases to these runners; do not present selectors for nonexistent
tests as executable. Escalate to `python -m pytest tests --quiet` after focused
checks. Validate hook/CLI behavior on Windows and Linux, not syntax alone.

## Paired live matrix

Select Bicep/Terraform through existing documented flow; distinct fresh
environments per mode/provider. Do not retrofit Basic for fresh-only evidence.

| Case | Required observation |
| --- | --- |
| Default/disabled, both modes/providers | Zero feature resources/settings or changed ACA networking. |
| Basic enabled, both providers | External ingress; ACA VNet and dedicated NAT; observed SQL source IP equals NAT IP. |
| Basic unlisted source | Firewall rejects; identity alone cannot bypass network control. |
| Isolated enabled, both providers | Canonical FQDN resolves to PE IP; app SQL succeeds privately; public access disabled. |
| BYO/existing/policy DNS | Correct ownership/records, no duplicates, missing readiness fails. |
| Bootstrap/auth | Entra-only, no secret output/log, non-admin app OID mapping. |
| SQL permissions | Existing/future CRUD succeeds; app DDL/cross-schema/admin operations fail. |
| Rerun/conflict | Same grants/mapping after two runs; mismatched identity/privileged role rejected. |
| Invalid configuration | Bad Boolean/admin/SKU/HA, broad firewall or forced route rejected. |
| Existing Basic retrofit | Stops before environment recreation. |
| Partial lock failure | No ready publication; verified same-binding recovery succeeds. |
| Disable/replacement/down | Lifecycle stops before destruction and inserted row remains. |
| Direct deletion | Independent lock denies server deletion, including direct Terraform destroy. |
| Explicit cleanup | Approved exact-resource cleanup; shared DNS/RGs remain. |

## Setup on the implementation branch

For a newly selected environment, after deployment approval:

```powershell
azd env set DEPLOY_POSTGRESQL true
azd env set NETWORK_ISOLATION false
azd env set POSTGRESQL_ADMINISTRATOR_OBJECT_ID <administrator-object-id>
azd env set POSTGRESQL_ADMINISTRATOR_PRINCIPAL_NAME <administrator-principal-name>
azd env set POSTGRESQL_ADMINISTRATOR_PRINCIPAL_TYPE Group
```

Principal type must match the actual admin; Group is only an example.
Provide optional operator addresses through typed postgreSqlAllowedIpRanges.
For isolation choose NETWORK_ISOLATION=true before first provision and use
a VNet-connected host. Run the documented selected-provider provision flow
and verify lock/discovery. API-policy rejection or unavailable regional SKU
must remain explicit failures.

Initialize schema under actual DDL owner, then run the implemented bootstrap CLI in
[contracts/postgresql.md](contracts/postgresql.md) twice. Compare mapping and
grants; verify positive/negative cases from the test app. Operator access is
separate from app NAT. No automatic SQL bootstrap in deployment hooks.

## Evidence and cleanup

Record exact module/provider/component pins, parameters, resource/lock
ownership, observed SNAT/DNS and SQL outcomes in session artifacts. Scrub
tokens, personal IDs and private validation names before versioning/publishing.
Compilation/mock plans are not deployed parity; flag unrun scenarios.

Do not use azd down as an automatic cleanup shortcut. Review backup/PITR needs,
scope/state ownership and explicit owner approval, stop consumers, remove only
approved locks/resources and reconcile provider state. Preserve shared DNS/RGs.

## Executed offline evidence (2026-11-05/06 implementation session)

No evidence below is live Azure parity or a completed T039/T040 scenario.

| Check | Result |
| --- | --- |
| Initial `python -m pytest tests/test_postgresql_deployment.py --quiet` | Reproduced collection failure: missing `config.deployment.postgresql`. |
| `python -m pytest tests/test_postgresql_deployment.py tests/test_postgresql_bootstrap.py tests/test_deployment_inputs.py tests/test_platform_outputs.py --quiet` | **185 passed** after implementation, including native/env defaults and invalid types, matching Bicep/native transports, fail-closed intent/lock/rerun/publication, real SQL composition with injected cursor results and secret-safe failures. |
| `python -m pytest tests/test_infra_provider_hooks.py --quiet --maxfail=1` | **65 passed** in the full PowerShell/Bash preprovision harness, covering both providers, custom paths and short-circuiting. Subsequent early postprovision marker tests were separately included in the focused check below. |
| `python -m pytest tests/test_postgresql_deployment.py tests/test_postgresql_bootstrap.py tests/test_deployment_inputs.py tests/test_platform_outputs.py tests/test_resource_group_teardown.py tests/test_infra_provider_hooks.py -k 'not complete_hook' --quiet` | **259 passed, 32 deselected** before the final ten additional bootstrap/state regressions. Includes executed PowerShell/Bash protection blocks and Terraform guard ordering. |
| `python -m pytest tests/test_deploy_environment.py tests/test_private_network_hooks.py --quiet` with verified jq prerequisite in PATH | **28 passed, 82 subtests passed**. Earlier missing-jq failures were prerequisite failures, not weakened/skipped assertions. |
| `git diff --check`; `python -m compileall -q config/deployment/postgresql.py util/postgresql_bootstrap.py`; both modules' `--help` | Passed. CLI help only; no Azure call. |
| Develop ancestry and ignored binding | `git merge-base --is-ancestor develop HEAD` returned zero; `git check-ignore .azure/fixture/postgresql-binding.json` confirmed ignored state. No provider lock/pin edits in this scope. |
| Central documentation | All **55** Agent Landing Zone source pages searched through the GitHub API; **13** files updated on `Azure/AI-Landing-Zones:feature/postgresql-opcional`; navigation YAML/new-page links checked. Latest docs commit `66a23b441758223e36273fec653d39f039b5cfb9`. |
| Issue #864 | Read live body, then reconciled mode-aware/fresh-only scope and explicitly excluded live/destructive acceptance. Records requester direction, not independent review approval. |

### Dependency/environment limitations

Final consolidated own-scope/coupled check, with jq available:

```text
python -m pytest tests/test_postgresql_deployment.py tests/test_postgresql_bootstrap.py tests/test_deployment_inputs.py tests/test_platform_outputs.py tests/test_resource_group_teardown.py tests/test_infra_provider_hooks.py tests/test_deploy_environment.py tests/test_private_network_hooks.py -k 'not complete_hook' --quiet
```

Result: **297 passed, 32 deselected, 82 subtests passed**. The 32 complete-hook
cases are not missing evidence: they passed in the full 65-case hook run above.
After final GUID/database safety changes, the four-file focused command was
rerun: **185 passed**. Final whitespace and Python compilation checks passed.
Workflow YAML parsing verified both OS runners, utility requirements and the
bounded job timeout (now 60 minutes with the complete Windows/Linux CI matrix).

Final resource-readback review added seven regressions: generic ARM ACA
inventory is followed by actual resource reads; ownership/profile/subnet
mismatches fail; BYO default routes and competing DNS fail before intent;
and known pending intent can resume unfinished children without claiming ready.
The final command
`python -m pytest tests/test_postgresql_deployment.py tests/test_postgresql_bootstrap.py tests/test_deployment_inputs.py tests/test_platform_outputs.py tests/test_resource_group_teardown.py --quiet`
passed **239 tests**. Whitespace/compilation checks were repeated successfully.
Fresh test fixtures now distinguish a truly fresh environment without previous
PG outputs from a provisioned output context: missing records with retained
outputs are rejected, not silently adopted.

The selected utility requirement is exactly `psycopg[binary]==3.3.6`, matching
both installed driver/binary versions and the configured package index.
The initial 3.3.8 proposal was not retained: its official wheel endpoint failed
TLS via Python and Windows, and the configured index did not offer it.
No TLS bypass or fallback driver is used. Utility Azure Identity now matches
configuration's 1.27.0; the combined CI dependency command initially reproduced
`ResolutionImpossible` for 1.23.0 versus 1.27.0 and succeeds after alignment.
`python -m pip install --dry-run --disable-pip-version-check -r config/requirements.txt -r util/requirements.txt --quiet`
passed. A separate global `pip check` reports unrelated pre-existing
Conda/litellm/OpenTelemetry/uptrace conflicts in this shared host; these were not
modified. Live SQL execution remains explicitly deferred.

Git Bash and PowerShell were exercised on this Windows host; this is not a
claim of a completed native-Linux run. Existing CI now includes both runner OSes
and installs utility requirements. Local jq was initially missing; restored
official jq 1.8.1 in a temporary tool directory and verified its SHA256 against
the release checksum before running the affected shell tests.

### Integration findings and resolution

The first broader command
`python -m pytest tests --quiet -k 'not complete_hook' --maxfail=5`
returned **911 passed, 12 skipped, 32 deselected, 239 subtests passed,
3 failed, 2 errors** during concurrent infra work. Two Bash environment failures
were missing jq and subsequently passed with the prerequisite restored.
The remaining compiled-foundation failures/errors were Bicep **max-outputs**:
adding five native outputs produced **69** outputs, exceeding Azure's 64-output limit.
The root now retains all existing 64 Bicep outputs. ADR-0039 records the
shared post-provision adapter instead of a breaking output migration.
Immutable intent plus live server/database/auth/lock readback supplies the
four server fields; Basic egress follows the verified ACA subnet, dedicated
Standard NAT and its single Standard static public IPv4. Both providers
persist the same five azd metadata values. Explicit conflicting native fields,
wrong ownership/scope/allocation and azd persistence failure fail closed.
Fresh disabled deployments make no new metadata writes.

Parent integration reproduced and fixed three additional regressions before
delivery: CIDRs with host bits now normalize consistently with both providers;
isolated PostgreSQL does not require ACA; and missing Bicep transport fields
are derived from verified creation intent without accepting conflicting values.
Fresh Terraform groups skip non-existent ARM inventories after an explicit
group-existence read. An actual-helper regression also caught the publication
flag error: `--output none` must accept empty stdout while still rejecting any
nonzero CLI exit status. No success-shaped fallback or exception suppression
was introduced.
The deployment tenant is read from the explicitly selected subscription when
Bicep has not exported a tenant variable, with explicit tenant conflicts
rejected. Native isolation selection likewise does not require a duplicated
environment flag: immutable intent and actual server networking must match.

The transport-focused command at that integration checkpoint
`python -m pytest tests/test_postgresql_deployment.py tests/test_postgresql_bootstrap.py tests/test_deployment_inputs.py tests/test_platform_outputs.py tests/test_resource_group_teardown.py --quiet`
passed **254 tests** with the exact selected driver. Whitespace checks and
Python compilation passed. The central docs were reconciled at
`Azure/AI-Landing-Zones:feature/postgresql-opcional`,
commit `50b46aa68c63e6017a1ca979af0229a10dd790f0`; existing pages retain their
original line endings and the diff contains only the intended additions.

### Final combined offline evidence (2026-11-06)

| Boundary | Executed result |
| --- | --- |
| Full Python regression excluding the separately executed complete-hook cases: `python -m pytest tests --quiet -k 'not complete_hook'` | **1496 passed, 12 skipped, 32 deselected, 833 subtests passed**, 687.42 seconds. An earlier run exposed one stderr-capture regression from structured logging; the corrected test also executes the actual CLI and verifies the same actionable stderr/nonzero behavior. |
| `python -m pytest tests/test_infra_provider_hooks.py tests/test_deploy_environment.py tests/test_private_network_hooks.py --quiet` | **97 passed, 82 subtests passed**, 1490.46 seconds; includes all 32 complete-hook cases excluded above, PowerShell and Git Bash on Windows. |
| Final directly affected Python files and provider interfaces, including bootstrap administrative-group inheritance, shared-catalog naming and real CLI guard stderr | **283 passed** after the last code change. Group membership on later pages, unreadable membership, malformed/cross-scope/cyclic/over-limit paging fail before SQL/token work. |
| Terraform readonly init, recursive fmt, validate and complete mocked test runner | **142 passed, 0 failed**; committed provider lock and provider/module pins preserved. |
| Bicep v0.42.1 root compilation and `pwsh -NoProfile -File infra/tests/Invoke-OfflineContracts.ps1` | **19 suites, 0 failures**, 985.3 seconds. Original 64-output set and historical fingerprints preserved; disabled preexisting-graph AST equivalence covers both network modes. |
| Bicep lint | Passed with **14 non-error diagnostics**; no suppression of the output limit or removal of legacy outputs. |
| Independent graph mutation checks | 62 PostgreSQL delta mutations, 3 independent semantic mutations, 73 historical graph mutations and 110 subnet/Basic/native mutations rejected. |
| Provider Python interfaces | **7 passed** (`infra/tests/test_postgresql_interface.py` and `tests/test_terraform_interface.py`). |
| Dependency manifests, navigation and hygiene | Combined pip dry-run resolves; exact driver/binary 3.3.6 installed; central navigation YAML valid; whitespace and Python compilation pass. |

These are local evidence, not a native-Linux CI result or deployed Azure parity.
The existing CI now runs the same Python/hook contracts on Windows and Ubuntu.
Its 60-minute bound includes the measured combined local hook/full-suite cost
plus dependency/compiler setup. No Azure deployment/destructive validation ran.

The bootstrap additionally checks a Group administrator's complete transitive
Microsoft Graph membership before obtaining a SQL token. The API's documented
limited-information responses retain IDs, which is all this guard consumes;
directory permission failures or incomplete pagination fail closed.
Reference: [Graph transitive members](https://learn.microsoft.com/en-us/graph/api/group-list-transitivemembers?view=graph-rest-1.0).

Final focused command:

```powershell
python -m pytest tests\test_postgresql_bootstrap.py tests\test_postgresql_deployment.py tests\test_provision_only.py tests\test_platform_outputs.py tests\test_deployment_inputs.py tests\test_resource_group_teardown.py infra\tests\test_postgresql_interface.py tests\test_terraform_interface.py --quiet
```

Default PostgreSQL names use the existing
`infra/shared/abbreviations.json` `databases.postgreSQLDatabase` prefix plus
the deterministic deployment-context hash. Both providers receive that same
explicit name; user-supplied names remain verbatim. Missing/invalid catalog
entries fail explicitly rather than falling back to a duplicated prefix.

### Remaining live risks and recovery boundary

No actual SNAT source stability, private DNS convergence, regional SKU/API policy
acceptance, directory behavior, SQL engine permission outcome, independent-lock
deletion denial or partial-provision Azure recovery was executed. Review both
provider roots and run approved live scenarios separately before production.
The creation-to-lock interval remains a partial-provision risk; early
postprovision protection runs before private-host deferral and discovery, but
cannot protect a server before it exists. Privileged operators can remove a
lock or bypass lifecycle guards. Missing/corrupt local records require restoring
the original context; never erase intent or import the lock into Terraform to
make teardown/provisioning succeed.
