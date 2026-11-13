# Research: Optional App Configuration

**Date**: 2026-11-12 | **Status**: Design research, not implementation evidence

## 1. Metadata transport under the output limit

**Decision**: Add a dedicated `DEPLOYMENT_METADATA` root output in Bicep and
Terraform. Give it its own closed schema/version. Read it
from the selected provider for every independent invocation.

**Rationale**: `infra/bicep/main.bicep` already has exactly 64 outputs, enforced
by `tests/test_terraform_interface.py`. ARM supports at most 64 root outputs.
The existing hosted object is present beyond hosted deployments and already carries
Durable Task, workload egress and private-build context. Its readers inspect
specific members rather than reject an unknown sibling:
`egress._context`, `hosted_prepare.deployment_handoff`,
`hosted_access.discover_instance`, `native.scheduler_settings`,
the `native_deploy` publication overlay and private-network scheduler probing.
Keep regression coverage for these readers and native publication overlays,
but do not add generic deployment metadata to that object.

**Alternatives considered**:

| Alternative | Assessment |
| --- | --- |
| Dedicated neutral root output with coordinated output migration | Selected by the maintainer. Accurately scoped contract, requires an inventory and explicit approved transition to fit within 64 outputs |
| Add a generic member to the hosted output | Rejected by the maintainer. Preserves root names but mixes unrelated responsibilities |
| Provider-produced local artifact | Viable with explicit freshness and binding, but adds synchronization, recovery and another persistent inventory |
| Keep metadata in App Configuration | No migration, but cannot satisfy store-free discovery |
| Recover values from naming rules or Terraform state | Rejected. Violates explicit output, ownership and confidentiality requirements |

The maintainer selected the neutral output on 2026-11-12. The previous nested
carrier proposal is superseded. No specific output removal is approved yet.
Before Phase 2, inventory outputs and consumers, propose old-to-new mappings,
document compatibility and recovery, and obtain acceptance in ADR-0041.
Do not treat preserving all current root names as a constraint or retire an
arbitrary output to free a slot.

## 2. Source freshness and environment binding

**Decision**: Use live named provider outputs, not saved azd values alone.
Reuse the validated selected-environment helper, provider resolver and
resource-group binding. Compare overlapping saved metadata/aliases with the
provider result, then verify resource identities and endpoints live.

**Rationale**: `azd env get-values` returns saved environment values, not proof
that a resource still exists. `azd env refresh` refreshes prior provisioned
values. `config/deployment/provider.py` already resolves root `azure.yaml`
without a provider environment override. `egress.selected_environment` validates
an explicit selected snapshot. `resource_groups.py` and `context.py` preserve
destination ownership and exact ARM identities.

Bicep's authoritative locator is the selected subscription, bound root group
and validated `DEPLOYMENT_NAME`. Terraform uses the selected provider directory
and preserved backend binding. Neither locator is taken from the payload being
verified. No timestamp or hash is treated as proof of resource readiness.

**Alternatives considered**: Trusting `.azure/<env>/.env` alone misses stale
resource bindings. A signed inventory adds unrelated key management and still
requires live readiness checks. Name-based discovery is not exact identity.

## 3. Terraform non-secret output safety

**Decision**: Request only `DEPLOYMENT_METADATA` using named JSON output.
Before invocation, parse the root output declaration and require a unique,
literal `sensitive = false` declaration. Reject sensitive, nonliteral, missing
or malformed declarations. Add `python-hcl2` for this source preflight.
Producer tests prohibit `nonsensitive()` declassification in the metadata
derivation and validate the approved object fields.

**Rationale**: HashiCorp documents that `-json`, `-raw` and named output can
expose sensitive values. Named CLI JSON does not give a sensitivity envelope.
The state/plan JSON envelope is not the named-output format. Terraform rejects
an output that exposes sensitive dependencies without declaring sensitivity,
unless its author deliberately declassifies them, which this producer forbids.

This assurance combines reviewed non-secret producers, declaration preflight,
Terraform sensitivity propagation, closed schema and semantic validation.
It does not claim that a schema can recognize every secret disguised as an
otherwise valid resource name or that locally modified IaC is trusted merely
because it includes `false`.

**Alternatives considered**: Bulk `terraform output -json` exposes unrelated
and sensitive values before filtering. Raw/full-state inspection is prohibited.
Human-formatted output is not a parsing contract. A self-reported sensitivity
boolean inside the payload is not evidence.

Terraform internally accesses its selected backend to implement `output`.
Deployment code does not request, copy or parse raw state. A backend read
failure is a visible failure, never an invitation to select a different state.

## 4. Runtime contract and setting ownership

**Decision**: Keep `contracts/platform-outputs-v1.schema.json` unchanged.
Use deployment metadata directly for setup. Publish runtime v1 and existing
flat settings only when the selected runtime consumer requires them.

**Rationale**: Runtime v1 is closed and requires `appConfig.endpoint`.
`config/deployment/outputs.py` currently combines a mandatory store guard,
App Configuration hydration, identity discovery and publication. Reusing v1
for store-free setup would redefine an existing contract or fabricate a store.
`appconfig_intent.py`, `app_settings.py` and `appconfig_seed.py` already encode
declaration, authority and user-setting preservation rules.

**Alternatives considered**: Making v1's store optional changes interpretation
for existing consumers. Exporting all App Configuration keys as metadata
confuses runtime ownership, includes arbitrary values and retains the dependency.

Allowlisted runtime preferences remain runtime-owned in appConfig mode.
They cannot supply infrastructure destinations or override provider metadata.
Setup settings combine typed declared intent with verified resource/model
mappings. Derived Search settings may remain in memory for setup before an
optional publication step.

## 5. Real consumers, authorization and network behavior

**Decision**: Migrate the service consumers together and preserve selected
operations. Gate publication and genuine runtime prerequisites, not setup
completion, on the selected runtime mode.

**Rationale**:

- Foundry setup reads account/model/vault metadata through `AppConfigClient`.
  Toolbox setup also reads project/Search/connection metadata.
- Search bulk-loads settings, derives model/template context and writes settings
  before provisioning. Both discovery and publication must be separated.
- Container Apps reads registry, apps and identities from the store.
- Governance couples audit secret creation to store publication. Key Vault work
  must remain selected and secret values must not enter metadata.
- Panel and MCP have resource-discovery fallbacks as well as genuine runtime
  or registration-state uses. Only discovery is replaced.
- `profiles.py` grants AppConfigurationDataReader implicitly through base.
  Remove that implicit dependency where not required, without removing explicit
  feature prerequisites or broadening other grants.
- `private_network.check_stage` always probes the store today. Required-service
  probe selection must preserve all other DNS/TLS and private-runner safeguards.

PowerShell postProvision includes large flat seeding/discovery behavior absent
from shell. Shared Python setup-input resolution is necessary for parity.
Do not copy the PowerShell model-name/version defaults into a second discovery
implementation. Use evaluated provider values.

**Alternatives considered**: Removing endpoint guards only leaves real consumers
broken. Skipping Foundry/Search/governance/roles reports false success.
Rewriting runtimes exceeds the user's confirmed scope.

## 6. Validation scope clarification

**Decision**: Do not create another application and do not require a live
reference-application demonstration. Cover providers, contracts, hook behavior,
setup calls, safety and repeated invocations with automated tests.

**Rationale**: Both existing samples explicitly read `APP_CONFIG_ENDPOINT` and
`AGENTLZ_PLATFORM_OUTPUTS`. The Container App returns 503 at `/` without the
store. The hosted sample can return a superficially healthy greeting with an
unavailable project. Neither is evidence of compatible store-free application
behavior, and both definitions contain placeholder source commits.
The user explicitly declined the proposed extra validation application.

**Alternatives considered**: Rewriting samples/runtimes violates scope.
Using only health endpoints would be a false proxy for application readiness.
An external unverified image/commit is not a reproducible approved reference.

Four provider/mode combinations remain automated coverage targets. Compilation,
mocks and contract checks are not cloud parity, and live store-free application
readiness remains unverified. No acceptance fixture application is introduced.

## 7. Documentation and adoption

**Decision**: Update central product documentation with implementation, not now.
Fail explicitly when an old foundation lacks deployment metadata. Reprovision
the same provider with declared inputs instead of restoring store discovery.

**Rationale**: Central `configuration.md` describes App Configuration in
generated metadata, runtime mode and post-provision publication.
`build-your-own-app.md` documents both samples' store-backed runtime v1 reads.
`deployment-operations.md` delegates recovery to the provider-specific guides.
These are concrete affected areas, not evidence that store-free setup ships.

**Alternatives considered**: Publishing planned support now creates drift.
Changing only a README misses the operator source. Silent old-output fallback
would keep App Configuration authoritative.

Implementation must search the full central docs source, including configuration,
application settings, both full-stack/infra-only guides, operations, private
access and troubleshooting. Keep current runtime/sample prerequisites accurate.

## External evidence

Official references consulted for tool behavior:

- [Terraform output](https://developer.hashicorp.com/terraform/cli/commands/output)
- [Terraform sensitive data](https://developer.hashicorp.com/terraform/language/manage-sensitive-data)
- [Terraform JSON format](https://developer.hashicorp.com/terraform/internals/json-format)
- [azd command reference](https://learn.microsoft.com/azure/developer/azure-developer-cli/reference)
- [azd environments](https://learn.microsoft.com/azure/developer/azure-developer-cli/work-with-environments)
- [azd environment variables](https://learn.microsoft.com/azure/developer/azure-developer-cli/manage-environment-variables)
- [Terraform with azd](https://learn.microsoft.com/azure/developer/azure-developer-cli/use-terraform-for-azd)
- [ARM template limits and outputs](https://learn.microsoft.com/azure/azure-resource-manager/templates/best-practices)

Not established by those sources: azd Terraform import filtering, preservation
of sensitivity metadata in saved values, or a built-in approved-output filter.
The design does not depend on these behaviors. Implementation must test native
object serialization and output-size compatibility using the pinned toolchain
before consumer migration. If the dedicated output cannot round-trip, stop and
revise the ADR rather than invent a silent alternative transport.
