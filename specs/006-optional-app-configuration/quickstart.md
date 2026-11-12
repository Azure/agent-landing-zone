# Validation Guide: Optional App Configuration

## Status and scope

Implementation and integration checks are in progress. The metadata loader,
setup adapters and service migrations exist. Completed observations are recorded
below, and remaining acceptance work is tracked in [tasks.md](tasks.md).

Do not create a validation application, rewrite samples/runtimes or run a live
reference-app deployment for this feature. Both current samples require a store.
Use synthetic metadata and mocked Azure/service boundaries in existing tests.
Automated results do not prove deployed Azure parity or application readiness.

## Prerequisites

- Use `feature/optional-app-configuration`, based on `develop`, with the original
  declared parameter source and manifest.
- Maintainer acceptance is recorded in
  [ADR-0041](../../docs/adr/ADR-0041-provider-owned-deployment-metadata.md)
  including the concrete migration replacing only the policy echo
  `OBSERVABILITY_MIXED_WORKSPACES_ALLOWED` with `DEPLOYMENT_METADATA`.
  The typed mixed-workspace policy and all other outputs remain supported.
- Use the repository's Python environment, PowerShell/Bash and pinned Bicep,
  Terraform and provider/module versions.
- Install/restore dependencies only after the implementation changes the
  dependency manifest or a selected command reports a missing dependency.
  CI's existing dependency command is:

```powershell
python -m pip install --disable-pip-version-check pytest click tabulate -r config\requirements.txt -r util\requirements.txt
```

For module/hook tests, supply an explicit synthetic selected environment,
declared inputs, group/backend bindings and read-only provider/Azure responses.
Do not use a developer's real `.azure` values or credentials as fixtures.
The [JSON example](contracts/containerenv.example.json) is schema data only,
not an application or provisionable Azure configuration.

## 1. Producer and contract checks

Assert both providers emit the same closed `DEPLOYMENT_METADATA` root output
for selected configurations, including disabled states. Verify at most 64
Bicep root outputs, the approved old-to-new output/consumer migration, the five
Terraform PostgreSQL adapter contracts and legacy hosted handoff semantics.
Include hosted, classic,
custom and software-disabled cases. Preserve unchanged runtime v1 schema bytes
and integrity metadata.

From the repository root, use the existing focused suites:

```powershell
python -m pytest tests\test_terraform_interface.py tests\test_platform_outputs.py tests\test_custom_foundation_outputs.py tests\test_native_foundation.py --quiet
```

Add focused coverage for the new loader/schema in `tests/` during implementation,
then include those files in the same pytest invocation. Test output declarations
marked sensitive before value retrieval. A named Terraform output command alone
is not a sensitivity check.

Compile and validate the actual providers after implementation:

```powershell
$bicepOutput = Join-Path $env:TEMP ("agentlz-875-" + [guid]::NewGuid().ToString("N") + ".json")
az bicep build --file infra\bicep\main.bicep --outfile $bicepOutput
az bicep lint --file infra\bicep\main.bicep --diagnostics-format sarif
Remove-Item -LiteralPath $bicepOutput
pwsh -NoProfile -File infra\tests\Invoke-OfflineContracts.ps1
```

Run the Terraform checks from its provider directory, preserving the lock:

```powershell
Push-Location infra\terraform
terraform fmt -check -recursive
terraform init -backend=false -lockfile=readonly
terraform validate
terraform test
Pop-Location
```

These are compilation/offline/mocked checks. Do not initialize a real remote
backend or mutate Azure as part of this guide.

## 2. Automated provider/mode matrix

| Provider | Mode | Store | Expected exercised behavior |
| --- | --- | --- | --- |
| Bicep | `containerEnv` | Disabled | No store resource, no store CLI/SDK calls, all selected setup calls succeed |
| Terraform | `containerEnv` | Disabled | Same outcome, exactly approved named output and no raw-state requests |
| Bicep | `appConfig` | Present | Output-only discovery, exact store verified, existing settings/flags/references preserved |
| Terraform | `appConfig` | Present | Same semantics, selected backend/output only |
| Both | `containerEnv` | Present | No mode switch or store-discovery/publication fallback |
| Both | `none` | As declared | Existing no-injection semantics and feature prerequisites preserved |

For each primary row, run post-provision and pre-deploy in independent test
processes, then repeat deploy twice with unchanged inputs. Supply only persisted
selected environment, declarations and native output fixtures between processes.
Assert no reliance on a prior process or store hydration.

Instrument CLI and Azure SDK call boundaries. Fail immediately if a store-free
case constructs a store client or invokes a store endpoint, including checks,
roles, seeding or connectivity probes. Merely asserting an empty endpoint is
insufficient. In appConfig cases, distinguish permitted runtime preference/
publication calls from forbidden metadata reads.

Use the existing hook, ownership and safety suites:

```powershell
python -m pytest tests\test_infra_provider_hooks.py tests\test_private_network_hooks.py tests\test_resource_group_consumers.py tests\test_appconfig_intent.py tests\test_appconfig_seed.py tests\test_app_definition_roles.py --quiet
```

Exercise both actual PowerShell and Bash wrappers on their supported CI runners.
String assertions alone do not prove parity. Observe delegated commands,
nonzero propagation and ordering before mutating operations.

## 3. Selected service setup

Cover each metadata-using service with a store client that fails if accessed for
discovery. Assert the real selected SDK/CLI calls, rendered payloads and IDs:

| Service | Required observations |
| --- | --- |
| Foundry | Correct account/project/model, RAI blocklist/policy association and legitimate Key Vault evaluation-secret operation |
| Search/toolbox | StrictUndefined rendered payloads, correct model/connection/KB binding, selected Search/Foundry IQ setup, no missing-required-model fallback |
| Container Apps | Correct app/registry/identity configuration, no broadened roles |
| Governance | Audit HMAC secret create/reuse in Key Vault when selected, reference delivery, unchanged appConfig migration and no HMAC value in metadata/logs |
| Panel | Correct selected Cosmos account/database without store fallback |
| MCP/native | Resource discovery uses metadata, genuine selected store/Entra-state prerequisites remain explicit |

Extend and run the existing focused service tests:

```powershell
python -m pytest tests\test_aifoundry_setup.py tests\test_knowledge_toolbox.py tests\test_panel_setup.py config\search\tests config\governance\tests --quiet
```

Include affected Container Apps/deployment tests selected from the existing
suite when implementing those migrations. Never count "skipped because no
endpoint" as a completed selected operation.

## 4. Negative and safety matrix

For both providers and modes, assert a visible error and zero dependent
mutations for:

- Missing dedicated output, malformed JSON, unsupported version, unexpected secret field
  and enabled-service null descriptor.
- Wrong environment/provider/application/mode, tenant/subscription/group,
  deployment name, stale cached output/aliases or changed backend binding.
- Matching resource name with mismatched ID/type/parent/endpoint, wrong Foundry
  account/project binding, wrong principal/client ID or undeclared external scope.
- Missing, true, nonliteral or malformed Terraform output sensitivity declaration,
  unapproved output command and producer declassification.
- Credentialed/query-bearing endpoints, forbidden/timeout/DNS/TLS resource checks
  and unavailable Terraform backend.
- Selected appConfig without a usable store, or a genuine selected feature
  lacking its required store/vault.

Also prove disabled resources do not trigger probes/RBAC/publication, required
private resources still do, explicit deferral is not readiness, and existing
appConfig runtime preferences cannot override infrastructure metadata.
Diagnostics identify field/category and recovery without echoing candidate
values, provider responses, tokens or secrets.

## 5. Recovery and documentation checks

Read-only metadata check:

```text
python -m config.deployment.metadata --check --environment <selected-environment>
```

Old output: explain same-provider reprovision with original declarations.
Stale cache: use the supported refresh, then rerun the guard:

```text
azd env refresh --environment <selected-environment>
```

Do not hand-copy metadata into the store, switch providers, inspect state or
guess a Terraform backend. Old store-dependent hooks are not a store-free
rollback. No live command in this section is required during planning.

Search/update the central docs source with implementation. Verify all examples
distinguish inputs, deployment outputs, runtime settings and secrets.
Keep current samples' store requirement and no-in-place-conversion limitation.
Capture the actual documentation revision in the implementation handoff.

## Evidence record

### T002 compatibility baseline

Source: `823109be4aafe2870972941ac3cec34f880d6153`.
The original Bicep root set has exactly these 64 names:

```text
TENANT_ID
SUBSCRIPTION_ID
AZURE_RESOURCE_GROUP
AZURE_APP_RESOURCE_GROUP
AZURE_NETWORK_RESOURCE_GROUP
LOCATION
ENVIRONMENT_NAME
DEPLOYMENT_NAME
RESOURCE_TOKEN
NETWORK_ISOLATION
USE_UAI
USE_CAPP_API_KEY
RELEASE
APP_RUNTIME_CONFIGURATION_MODE
DEPLOY_APP_CONFIG
DEPLOY_SOFTWARE
DEPLOY_KEY_VAULT
DEPLOY_LOG_ANALYTICS
DEPLOY_APP_INSIGHTS
DEPLOY_SEARCH_SERVICE
DEPLOY_SPEECH_SERVICE
DEPLOY_STORAGE_ACCOUNT
DEPLOY_COSMOS_DB
DEPLOY_CONTAINER_APPS
DEPLOY_CONTAINER_REGISTRY
DEPLOY_CONTAINER_ENV
DEPLOY_VM_KEY_VAULT
ACR_TASK_AGENT_POOL
APP_CONFIG_ENDPOINT
KEY_VAULT_URI
RETRIEVAL_BACKEND
FOUNDRY_IQ_PATTERN
KNOWLEDGE_BASE_NAME
KNOWLEDGE_BASE_ENDPOINT
KNOWLEDGE_BASE_CONNECTION_ID
FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME
FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND
AZURE_SPEECH_RESOURCE_ID
AZURE_SPEECH_ENDPOINT
AZURE_SPEECH_REGION
AZURE_SPEECH_RESOURCE_NAME
PUBLIC_INGRESS_ENABLED
PUBLIC_INGRESS_PUBLIC_IP
PUBLIC_INGRESS_PUBLIC_IP_RESOURCE_ID
PUBLIC_INGRESS_GATEWAY_RESOURCE_ID
PUBLIC_INGRESS_NSG_RESOURCE_ID
PUBLIC_INGRESS_WAF_POLICY_RESOURCE_ID
PUBLIC_INGRESS_IDENTITY_PRINCIPAL_ID
PUBLIC_INGRESS_LIVE
APP_GATEWAY_SUBNET_RESOURCE_ID
VNET_RESOURCE_ID
KEY_VAULT_RESOURCE_ID
KEY_VAULT_NAME
LOG_ANALYTICS_RESOURCE_ID
APP_INSIGHTS_RESOURCE_ID
OBSERVABILITY_MIXED_WORKSPACES_ALLOWED
CONTAINER_APP_INTERNAL_FQDN
DEPLOY_HOSTED_AGENT
HOSTED_AGENT_PREPARED
AZURE_AI_PROJECT_RESOURCE_ID
AZURE_AI_PROJECT_ENDPOINT
AZURE_CONTAINER_REGISTRY_RESOURCE_ID
AZURE_CONTAINER_REGISTRY_ENDPOINT
HOSTED_AGENT_DEPLOYMENT
```

The proposed Bicep set is exactly this set minus
`OBSERVABILITY_MIXED_WORKSPACES_ALLOWED` plus `DEPLOYMENT_METADATA`, still 64.
Both original and proposed Terraform sets are their respective Bicep set plus
these five names, exactly 69:

```text
POSTGRESQL_SERVER_RESOURCE_ID
POSTGRESQL_HOST
POSTGRESQL_PORT
POSTGRESQL_DATABASE_NAME
CONTAINER_APPS_POSTGRESQL_EGRESS_IP
```

All other root names retain their contracts. The full old-to-new mapping,
historical normalization treatment and compatibility/recovery window are in
ADR-0041. Root consumer groups audited include context/group/backend and quota
helpers, post-provision runtime publication, pre-deploy guards/builds, Foundry
and registry/service setup, retrieval/source configuration, ingress/egress,
PostgreSQL, hosted handoff, samples and central documentation.

Preserve these exact SHA256 values:

| File | SHA256 |
| --- | --- |
| `contracts/platform-outputs-v1.schema.json` | `7217acf4ab374fd2f6426f849d013756f911ae297ab99c13aed78bc976aecd3d` |
| `contracts/platform-outputs-v1.schema.json.sha256` | `79af31eeb9e87ba03216b2f825b900f9b251801ce2b9213137d58405e45362b2` |
| `manifest.json` | `b12c51d9863013d9e047b8a39d7020faf3291ccb71b3d6ae75d875186b090f3d` |
| `infra/terraform/.terraform.lock.hcl` | `43c0975f87920c17d301968a28b4563524929e3ab7d8602b49211d1b938a2421` |

The runtime schema requires its existing `v1` interpretation and unchanged
integrity file, independent of the new deployment schema version.

| Manifest entry | Tag | Commit |
| --- | --- | --- |
| Umbrella | `v7.3.0` | Platform source above |
| infra / AI Landing Zone | `v2.7.3` | `97e2375b89dcda4900d75aac9e7ffb7b20cce165` |
| agent-app-mcp | `v2.0.0` | `e462d929ce02a74813feff9288d155098295691c` |
| agent-app-ui | `v3.7.0` | `b5e2462adb047c4e91110a87580d2c97a0d94b84` |
| agent-app-orchestrator | `v7.2.0` | `72909db145ca41b954e18261d89e50318bed592a` |
| agent-app-ingestion | `v3.1.3` | `d7f34eb040cc308ce18d0d95ee9c9cb0f07028b1` |

The retired output name has no occurrence in any regular file of those four
runtime archives at the exact pinned commits (78 MCP, 268 UI, 285 orchestrator,
245 ingestion files). Central documentation was searched across 204 text source
files at `964a1f65e1100eaa2c0c19e6274bde3e61bcd945`, also without an occurrence
of that name. This is a bounded compatibility audit, not a claim about
customer-owned automation.

Central source references to the broader configuration/discovery boundary were
found in application-settings, build-your-own-app, configuration, full-stack/
infra-only deployment guides, get-started, ingestion, local-development, NL2SQL,
PostgreSQL, private-access, SharePoint and troubleshooting pages. Also inspect
deployment-operations, both provider guides and the affected examples when
implementing. Do not publish the proposal as shipped behavior.

| Tool boundary | Repository baseline | Available during T002 |
| --- | --- | --- |
| Python | Python 3.11+ | 3.12.9 |
| PowerShell | PowerShell 7 | 7.6.10 |
| Bicep | `v0.42.1` in infra CI | 0.42.1 |
| Terraform | 1.13.0 in CI, root constraint `>= 1.13.0, < 2.0.0` | 1.13.0 |
| azd transport | Native Terraform 1.37.1 behavior documented by existing producer | 1.37.3, transport-specific feature assertions remain implementation work |

Provider pins remain Azure/azapi 2.13.0, hashicorp/azurerm 4.81.0,
Azure/modtm 0.4.0, hashicorp/random 3.9.1 and hashicorp/time 0.14.2.
All module versions remain the explicit versions in `infra/terraform/main*.tf`,
including VNet/subnet 0.22.3 and PostgreSQL 0.2.3. No init or dependency
installation was needed for the baseline run.

Baseline command:

```powershell
python -m pytest tests\test_terraform_interface.py tests\test_platform_outputs.py tests\test_custom_foundation_outputs.py tests\test_native_foundation.py --quiet
```

Result: **24 passed**. This verifies the pre-change root/runtime contracts,
not the unimplemented metadata producer or loader.

Setup inspection found existing Python/Terraform ignore coverage and explicit
lock-file retention. Dockerfiles exist only in the two excluded sample source
contexts, not in the metadata tool. No Node publishing, ESLint, Prettier or Helm
configuration was found for this work. Do not add unrelated sample/build-tool
ignore files while completing the metadata inventory.

Record source revision and unchanged manifest combination, tools, fixture
selection, commands/results, both hook runners and unverified scenarios.
Use the narrow suites first. Broaden to CI's `python -m pytest tests --quiet`
only when needed, with CI's manifest-matched UI checkout/PYTHONPATH prerequisite.
Do not fabricate full-suite success on a checkout lacking that prerequisite.

Report automated contract/setup/hook coverage separately from live evidence.
No new validation application or live reference-app run is required. Until
separately exercised, cloud parity, private-topology operation and store-free
application readiness remain unverified.

## Implementation evidence

The approved migration is implemented in both providers. Bicep retains 64 root
outputs and Terraform 69, including all five PostgreSQL adapters. Only the
mixed-workspace policy echo was replaced. Its input and checks remain. No runtime
or sample was rewritten, no application was added, and no component/provenance
pin or provider lock was changed.

### Source and binding observations

- Both producers emit the six-section production contract with all thirteen
  resource slots and managed/referenced/disabled states. The typed
  `applicationId` input defaults to `agent-lz-default` and root parameters bind
  `${AGENTLZ_APP_ID=agent-lz-default}` for custom selected definitions.
- The native Bicep adapter makes a bounded deployment-success request and one
  approved metadata-value request. Failed/running/accepted provisioning cannot
  retrieve an old metadata value.
- Native Terraform behavior was checked against azd 1.37.3 source commit
  `c791087c9a8626cdc57ece00bd8ec3568e95225c`. The initialized data directory and
  backend configuration are under `.azure/<env>/<infra.path>`, including custom
  provider paths. Source approval precedes native init and the single named
  output request. Original-backend success, changed-backend rejection and
  restoration were exercised without deployment-code state parsing.
- Live verification binds original selection, explicit names, groups, ARM
  types/parents, endpoints and app identity associations. Solution storage is
  in the Foundry group. PostgreSQL selects networking even without isolation.
  Existing monitoring IDs and hosted registry references retain their exact
  declared ownership.
- Speech uses the returned service endpoint. All model formats preserve the
  existing provider-produced `<account>.openai.azure.com` endpoint. Cosmos
  requires exactly one `DATABASE_NAME` row when selected, validates explicit
  database-name overrides and binds children to the verified account/database.
- Shared settings carry typed Search/project selection controls, including
  evaluated defaults when those controls were omitted. Disabled/unselected
  Search does not prevent unrelated setup. Selected Search/toolbox operations
  still reject missing prerequisites.
- Default `appConfig` preserves runtime-v1 publication, `agent-lz`, owner-only
  operational preferences, feature flags and Key Vault-reference behavior.
  Store presence does not select publication in `containerEnv` or `none`.
- The read-only guard verifies the selected foundation and all its enabled
  resource bindings, not resources from other deployments. Disabled slots
  require no live read. A provisioned store is not live-read outside `appConfig`.
  Direct setup entry points repeat this boundary rather than trusting an
  earlier process's verified flag.
- Legacy monitoring and Speech output aliases participate in stale-cache
  rejection. The deployment application identifier uses `AGENTLZ_APP_ID` and
  does not take ownership of an unrelated runtime `APPLICATION_ID`.

### Executed checks

| Check | Observation |
| --- | --- |
| Producer/interface/composition/compatibility suites | 211 passed and 138 subtests |
| Full native Terraform test suite before the final application-ID addition | 142 passed |
| Final Terraform root suite, including custom application ID | 23 passed |
| Final full native Terraform suite, including application ID and runtime RBAC | 144 passed, zero failures |
| Terraform fmt, readonly backend-disabled init and validate | Passed |
| Pinned Bicep 0.42.1 build | Passed with 64 outputs |
| `az bicep lint --file infra\bicep\main.bicep --diagnostics-format sarif` | Exit 0 |
| Offline contract runner, parallel throttle 3 | 19 scripts, zero failures |
| Final integrated metadata/service/runtime/consumer Python run | 842 passed and 372 subtests |
| Final metadata/setup and independent-process regressions | 103 passed |
| Final executed PowerShell/Bash hooks, role and private-network regressions | 242 passed and 195 subtests |
| Remaining context/group/binding/backend/input suites | 244 passed and 201 subtests |
| Final producer integration and new endpoint/database/custom-path regressions | 179 passed |
| `python -m config.deployment.metadata --help` | All documented flags present |
| Protected baseline SHA256 checks | All four files unchanged |
| `git diff --check` | Passed |

The integrated command was:

```powershell
python -m pytest tests\test_deployment_metadata.py tests\test_deployment_setup_settings.py tests\test_aifoundry_setup.py tests\test_knowledge_toolbox.py tests\test_containerapps_setup.py tests\test_panel_setup.py tests\test_custom_registry.py tests\test_governance_setup.py tests\test_search_setup.py config\search\tests config\governance\tests tests\test_native_application.py tests\test_mcp_component.py tests\test_hosted_access.py tests\test_hosted_prepare.py tests\test_platform_outputs.py tests\test_appconfig_intent.py tests\test_appconfig_seed.py tests\test_app_settings_resolution.py tests\test_deployment_modes.py tests\test_optional_ingestion.py tests\test_resource_group_consumers.py --quiet --tb=short
```

The additional binding command was:

```powershell
python -m pytest tests\test_deployment_metadata.py tests\test_deployment_setup_settings.py tests\test_resource_groups.py tests\test_app_definition_binding.py tests\test_native_knowledge_connection.py tests\test_terraform_backend.py tests\test_deployment_inputs.py --quiet --tb=short
```

The final producer-integration command was:

```powershell
python -m pytest tests\test_deployment_metadata.py tests\test_deployment_setup_settings.py tests\test_terraform_interface.py tests\test_custom_foundation_outputs.py tests\test_native_foundation.py tests\test_deployment_inputs.py --quiet --tb=short
```

The final both-shell command was:

```powershell
python -m pytest tests\test_infra_provider_hooks.py tests\test_deploy_environment.py tests\test_provision_rerun.py tests\test_app_definition_roles.py tests\test_private_network.py tests\test_private_network_hooks.py --quiet --tb=short
```

Both PowerShell and Bash cases executed with jq 1.8.1 available to the runners.
The run completed with 242 passing tests and 195 passing subtests, without
missing-tool skips. The final full `terraform test -no-color` run completed
with 144 passing tests and no failures, including the mode-aware RBAC assertions.

Counts describe their individual runs and overlap. Do not sum them as unique
coverage. Later final integration results supersede earlier counts.

### Acceptance observations

| Selected boundary | Observed behavior |
| --- | --- |
| Bicep / `containerEnv`, store omitted | Executed post-provision and pre-deploy guards revalidate each invocation. Shared setup tests forbid store discovery while exercising selected service operations. |
| Terraform / `containerEnv`, store omitted | The same hook contract and service adapters apply, with separate named-output/source/backend checks for native Terraform. |
| Bicep / default `appConfig` | Runtime publication uses the verified store, preserves `agent-lz`, v1/flat keys, setting ownership, feature flags and secret references. |
| Terraform / default `appConfig` | The same runtime compatibility suite applies after Terraform-specific source/backend verification. |
| Store present with `containerEnv`, and `none` | Store presence does not enable discovery/publication. `none` retains no new runtime injection. |

These are synthetic provider-boundary and executed-hook observations, not live
deployments. The guard matrix runs post-provision and pre-deploy for both
providers and all three modes, twice in independent subprocesses with unchanged
inputs. Its failing guard prevents the following mutation stage. The selected
Search/toolbox block also executes in both shells and propagates selected-step
failures.

Selected-service suites observe RAI/evaluation-vault and connection/toolbox
operations, StrictUndefined Search template rendering and writes, Container App
registry/auth/identity configuration, HMAC Key Vault creation/reuse/reference
delivery, and Cosmos database selection. Required-service failures remain
visible rather than becoming successful skips. MCP's genuine store-dependent
registration remains an explicit prerequisite outside `appConfig`.

The destination matrix rejects independent context fields, overlapping cached
aliases/documents, wrong ARM types/parents/names, undeclared external ownership,
missing/duplicate selected mappings, incorrect principals/client IDs and exact
Foundry endpoint mismatches. Existing shared-group normalization, exact declared
external resources and disabled-resource cases remain accepted where appropriate.
Direct-entry and binding suites preserve the same failure propagation.

The persisted-selection integration matrix starts two fresh Python processes
for each provider with store-free `containerEnv`, default `appConfig`,
`containerEnv` with a store, and `none`. Each process runs the actual declared
input resolver, provider adapter, live verification and setup-settings boundary
against synthetic external responses. All eight cases passed, with exactly one
named metadata-value request per process, identical repeated request traces and
no App Configuration CLI discovery. The fixture explicitly selects
`ORCHESTRATION_HOST=container_apps` and `APPLICATION_MODE=conversational`, so
unrelated default hosted-agent prerequisites are not silently bypassed.

Both infrastructure providers already restrict runtime
`AppConfigurationDataReader` grants to selected `appConfig` mode.
`infra\bicep\main.bicep` requires the store, runtime mode and requested role
together. `infra\terraform\main.identity.tf` maps that role only in `appConfig`
mode. These matching template conditions need no production change. New native
Terraform assertions cover default Reader retention, omission in `containerEnv`
with a store, and preservation of ACR/Key Vault grants without a store.

Source-preflight failures never request the Terraform value. Captured requests
use only the approved named output and bounded Bicep projections. Provider
failure canaries and invalid candidate values do not enter diagnostics.
Unrelated sensitive Terraform outputs remain irrelevant, while direct and
transitive `nonsensitive()` dependencies are rejected. The native backend
probe uses Terraform commands, not deployment-code state inspection. Existing
Key Vault failures remain failures without granting broader roles.

### Central documentation

Complete-source discovery used `Azure/AI-Landing-Zones` main at
`964a1f65e1100eaa2c0c19e6274bde3e61bcd945`. Twelve existing pages were updated
without adding pages or changing navigation:

| Under `docs\agent-landing-zone\` | Change |
| --- | --- |
| `configuration.md` | Four authorities, mode/store matrix, native output provenance and permissions |
| `application-settings.md` | Runtime dependency distinguished from platform discovery |
| `build-your-own-app.md` | Custom ownership and explicitly unchanged store-dependent samples |
| `deploy-bicep.md`, `deploy-terraform.md` | Shared verified discovery and configuration/recovery links |
| `deploy-full-stack.md`, `deploy-terraform-full-stack.md` | Native provenance with unchanged bundled runtime prerequisites |
| `deploy-infra-only.md`, `deploy-terraform-infra-only.md` | Independent metadata versus mode-gated runtime publication |
| `deployment-operations.md` | Check/refresh, same-provider reprovision and original backend recovery |
| `private-access.md` | Required-service probes without an implicit store dependency |
| `troubleshooting.md` | Typed metadata failures and supported corrective actions |

Other matches in `get-started.md`, `ingestion.md`, `local-development.md`,
`nl2sql.md`, `postgresql.md` and `sharepoint.md` describe unchanged bundled
runtime/component behavior, not platform discovery. Generic upstream
`docs\bicep\deployed-resources.md` and `parameterization.md` describe the
foundation rather than Agent Landing Zone's wrapper contract. Those pages
required no change. The retired policy-output name had no central source match.

The actual docs workflow is `.github\workflows\docs-build-check.yml`.
Its relevant text/link check, `python -m mkdocs build --strict`, passed.
The reviewed twelve-page update is persisted in
`Azure/AI-Landing-Zones` branch `feature/optional-app-configuration`, commit
`54458d3bcf40e4b0233d2324c2bbb73ff0b803bd`. Its parent is the reviewed main
revision above. Existing line-ending conventions were preserved when creating
the Git tree. Main was not changed, so the public site does not advertise
support ahead of the matching implementation. Deliver this coordinated
documentation revision with the platform feature.

### Feature handoff

The feature targets `develop` from `feature/optional-app-configuration` and
implements issue #875. All planned implementation tasks are complete. The
final integrity checks preserve the four protected baseline files, the new
schema matches its integrity file, and the changed-file privacy scan and
`git diff --check` pass. The coordinated documentation revision above is ready
for delivery with this feature, not independently ahead of it.

Existing deployments need same-provider provisioning to obtain the new output
before adopting the migrated hooks. Do not mix the new hooks with old
foundations or use the old store-dependent hooks as a store-free rollback.
Runtime components, samples, application count, component/provenance pins and
the provider lock are unchanged. The observations above remain automated
contract, mocked provider, executed-hook and compilation evidence.
