# Feature Specification: Optional App Configuration in deployment flows

**Feature Branch**: `feature/optional-app-configuration`

**Created**: 2026-11-11

**Status**: Draft

**Input**: [Issue #875](https://github.com/Azure/agent-landing-zone/issues/875):
"Make Azure App Configuration optional in Bicep and Terraform deployment flows."

## Clarifications

### Session 2026-11-12

- Q: Does acceptance require only deployment decoupling, or also adapting bundled applications to run without App Configuration? → A: Correct deployment scripts and configuration modules without rewriting application runtimes. Demonstrate store-free deployment with a reference application that already supports `containerEnv`, completing all selected platform configuration steps.
- Q: Should a separate application be created to validate store-free deployment when the existing samples require App Configuration? → A: No. Do not create an additional application or require that reference-application validation. Keep application runtimes unchanged. This supersedes the reference-application demonstration in the preceding answer, not the required platform configuration or automated regression coverage.
- Q: Should generic deployment metadata reuse the hosted-agent output to preserve all existing root names? → A: No. Use a dedicated neutral `DEPLOYMENT_METADATA` output in both providers. Reorganize existing outputs through an explicit coordinated migration where needed to respect ARM's output limit. Identify affected consumers and approve the concrete migration before implementation, rather than nesting generic metadata under `HOSTED_AGENT_DEPLOYMENT`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Complete deployment without a configuration store (Priority: P1)

An operator whose application uses directly supplied runtime settings can
provision the platform and deploy that application without creating or accessing
Azure App Configuration. The deployment still completes all required service
configuration using metadata from the selected deployment.

**Why this priority**: Removing an unnecessary deployment dependency is the
primary outcome of the issue. Removing an endpoint check without supplying
metadata to downstream operations does not deliver that outcome.

**Independent Test**: Exercise both providers' outputs, lifecycle hooks and
selected configuration modules with `deployAppConfig=false` and
`APP_RUNTIME_CONFIGURATION_MODE=containerEnv`. Deny App Configuration access
in the automated boundary tests and verify that all selected platform setup
operations complete. Do not create a reference application or require a live
application deployment for this feature. Report simulation separately from
any future cloud evidence.

**Acceptance Scenarios**:

1. **Given** a fresh Bicep deployment with App Configuration disabled and an
   application compatible with `containerEnv`, **When** the operator provisions
   and deploys it, **Then** the required hooks and service configuration complete,
   the application receives its required non-secret runtime settings, and no
   App Configuration store is created, read, or written.
2. **Given** the same selection using Terraform, **When** the operator completes
   the equivalent deployment, **Then** the same observable outcome is achieved
   without requiring access to full Terraform state.
3. **Given** App Configuration is absent and another required service needs
   configuration, **When** that configuration runs, **Then** it obtains the
   necessary endpoints, resource identifiers and identities from deployment
   metadata rather than skipping the operation or inventing defaults.
4. **Given** provisioning completed successfully, **When** the operator runs
   application deployment separately or repeats it for the same selected
   environment, **Then** the deployment can recover its required metadata without
   a previous process's transient values or an App Configuration lookup.
5. **Given** an optional service is disabled, **When** required deployment
   metadata is validated, **Then** that service's absent metadata is accepted
   without skipping checks for enabled services or fabricating resource values.
6. **Given** a supported isolated or shared-resource topology, **When** its
   store-free deployment runs, **Then** existing ownership, network restrictions
   and connectivity requirements remain enforced.

---

### User Story 2 - Keep centralized runtime configuration working (Priority: P1)

An operator who chooses App Configuration for application settings and feature
flags retains the existing runtime behavior. Decoupling deployment metadata
does not remove centralized application configuration.

**Why this priority**: The default runtime mode must remain usable while the
unnecessary dependency is removed from deployment discovery.

**Independent Test**: Complete provision and deployment in `appConfig` mode
with each provider, then verify that the application reads its configured
settings and feature flags through the existing supported mechanism.

**Acceptance Scenarios**:

1. **Given** a valid `appConfig` deployment with either provider, **When**
   provisioning and deployment finish, **Then** the selected application retains
   its required configuration access, settings, feature flags and secret
   references.
2. **Given** App Configuration holds runtime settings, **When** deployment
   operations need resource metadata, **Then** the selected deployment's outputs
   supply that metadata instead of treating runtime settings as infrastructure
   inputs or an authoritative deployment inventory.
3. **Given** `appConfig` mode has no usable configuration store, **When** the
   requested operation is validated, **Then** it fails before dependent changes
   with an actionable explanation rather than silently switching runtime modes.
4. **Given** the operator explicitly provisions a store but selects
   `containerEnv`, **When** deployment runs, **Then** the presence of the store
   does not change the selected runtime mode or make it the deployment metadata
   source.
5. **Given** an existing supported metadata consumer, **When** the updated
   deployment publishes discovery information, **Then** that consumer retains
   its supported contract semantics or uses an explicitly versioned, documented
   coordinated transition.

---

### User Story 3 - Refuse an unsafe or incomplete deployment destination (Priority: P1)

An operator can rely on deployment operations to verify the intended subscription,
resource groups, resource identities and Foundry project before making changes.
Missing or conflicting discovery data produces a useful failure, not a change
to the wrong environment.

**Why this priority**: Replacing a metadata source must not weaken the existing
destination and identity safeguards.

**Independent Test**: Supply missing, malformed, stale and conflicting metadata
for both providers and runtime modes. Observe the error and verify that no
dependent mutation occurs.

**Acceptance Scenarios**:

1. **Given** required metadata is missing, malformed or uses an unsupported
   declared contract version, **When** a dependent operation starts, **Then**
   it fails with the affected field or contract and a recovery action, without
   guessing resource names or falling back to App Configuration.
2. **Given** metadata belongs to another selected environment, subscription,
   resource group, resource identity or Foundry project, **When** destinations
   are checked, **Then** the operation rejects the mismatch before mutation.
3. **Given** the deployment outputs and selected environment contain conflicting
   destination values, **When** metadata is resolved, **Then** the operation
   identifies the conflict instead of silently choosing a value.
4. **Given** a project endpoint does not belong to the verified Foundry account
   and project, or a required identity does not match the deployed resource,
   **When** the operation validates its targets, **Then** it rejects the binding.
5. **Given** the operator cannot read a resource needed for verification,
   **When** validation runs, **Then** the permission or connectivity failure is
   reported and the dependent change is not attempted.

---

### User Story 4 - Discover resources without exposing secrets (Priority: P1)

An operator can make deployment metadata available to the hooks without
exporting credentials or granting those hooks access to the full infrastructure
state. Secrets remain under the existing Key Vault access controls.

**Why this priority**: Removing one service dependency must not introduce a
broader disclosure path.

**Independent Test**: Include sensitive and unrelated outputs in a representative
deployment and observe which values the metadata consumer requests, persists
and reports.

**Acceptance Scenarios**:

1. **Given** Terraform exposes declared non-secret outputs alongside sensitive
   outputs, **When** deployment metadata is read, **Then** only explicitly
   declared, approved non-secret outputs are requested and full state is not read.
2. **Given** either provider supplies deployment metadata, **When** it is
   persisted or reported, **Then** it contains no secret values, credentials or
   tokens, and runtime secrets continue to use Key Vault.
3. **Given** a selected metadata output is marked sensitive or contains a
   prohibited secret-bearing value, **When** it is considered for discovery,
   **Then** it is rejected without echoing that value.
4. **Given** an identity lacks permission to configure a target resource or
   resolve a secret, **When** it uses the new discovery path, **Then** access
   remains denied without granting broader permissions to bypass the failure.

---

### User Story 5 - Understand and recover the deployment configuration (Priority: P2)

An operator can distinguish the values that request infrastructure, describe
provisioned resources, configure an application, and reference secrets. The
operator knows how those values reach deployment operations and how to recover
from missing or stale metadata.

**Why this priority**: Clear ownership and recovery instructions prevent operators
from reintroducing hidden dependencies or copying secrets into discovery data.

**Independent Test**: Follow the central deployment and configuration guidance
for each provider without using undocumented settings or manually copying
resource metadata into App Configuration.

**Acceptance Scenarios**:

1. **Given** the published operator guidance, **When** an operator selects a
   provider and runtime mode, **Then** it separately explains infrastructure
   inputs, deployment outputs and discovery, runtime settings, and secrets.
2. **Given** a separate deployment run or incomplete provisioning result,
   **When** the operator follows the recovery guidance, **Then** the selected
   environment's metadata can be restored or refreshed through a documented
   supported operation before retrying.
3. **Given** a setting or application feature genuinely requires App
   Configuration, **When** the operator considers disabling the store, **Then**
   the guidance identifies that prerequisite rather than promising unsupported
   store-free application behavior.

### Edge Cases

- An optional service is disabled. Its metadata may be absent without weakening
  checks for services required by the selected topology.
- `APP_CONFIG_ENDPOINT` is empty because the store is intentionally disabled.
  That absence alone must not mean the foundation is unprovisioned.
- The selected environment contains an obsolete App Configuration endpoint.
  A store-free deployment must not access it as a discovery fallback.
- A prior provision failed after creating only some resources. Outputs alone
  must not be accepted as evidence that required resources are ready.
- A selected environment is copied, switched, or paired with outputs from a
  different deployment. Binding checks must prevent cross-environment changes.
- Two sources agree on a resource name but disagree on its identifier, endpoint
  or identity. Agreement on the name must not suppress the conflict.
- Supported isolated and shared-resource deployments still require their existing
  network connectivity, ownership and permission checks.
- An application or explicitly selected feature cannot operate without App
  Configuration. It must fail with its actual prerequisite before dependent
  changes, not be silently disabled or reconfigured.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Both Bicep and Terraform flows MUST complete provisioning and
  application deployment with App Configuration creation disabled and
  `APP_RUNTIME_CONFIGURATION_MODE=containerEnv`, with zero App Configuration
  reads or writes. All selected platform configuration steps MUST complete.
  Creating an additional validation application, requiring a live reference-
  application demonstration, and rewriting application runtimes are out of scope.
- **FR-002**: Deployment metadata MUST originate from Bicep/ARM outputs or
  equivalent explicitly declared Terraform outputs associated with the selected
  `azd` environment. A versioned non-secret JSON output or deployment artifact
  MAY supplement that transport when needed. App Configuration MUST NOT be a
  required source or fallback for deployment metadata in either runtime mode.
- **FR-003**: Every affected lifecycle hook and service configuration consumer
  MUST receive the metadata needed to complete its selected operations. Removing
  an endpoint guard, skipping required configuration, or reporting readiness
  without that configuration MUST NOT count as success.
- **FR-004**: Required deployment metadata MUST remain available to a subsequent
  provision or deploy invocation for the same selected environment, without
  relying on transient values from a prior process. Missing or partial metadata
  MUST fail rather than be inferred from naming conventions.
- **FR-005**: Before dependent mutations, deployment operations MUST verify
  the target subscription, all relevant resource groups and resource identities,
  and the Foundry project and endpoint binding against the selected environment
  and actual provisioned resources.
- **FR-006**: Missing, invalid, stale or conflicting required metadata MUST stop
  the affected operation before mutation and report the invalid field or binding
  and a corrective action. Validation, permission and connectivity failures MUST
  remain visible through the configured diagnostic path.
- **FR-007**: Terraform metadata consumption MUST request only explicitly
  declared, approved non-secret outputs. It MUST NOT read full Terraform state,
  bulk-export sensitive outputs, or substitute state inspection for missing
  declared outputs.
- **FR-008**: Deployment outputs, artifacts and diagnostics MUST NOT expose
  secret values, credentials or tokens. Secrets MUST remain in Key Vault under
  the existing access model. Sensitive metadata candidates MUST be rejected
  without disclosing their values.
- **FR-009**: `appConfig` mode MUST preserve existing application settings,
  feature flags, configuration access, publication conventions and Key Vault
  references for both providers. This feature MUST NOT change the default
  runtime mode or implicitly select another mode.
- **FR-010**: App Configuration MUST remain an optional application-settings and
  feature-flag service, not an infrastructure-input authority or mandatory
  deployment inventory. Selecting a mode or feature that genuinely requires a
  store without providing one MUST produce an explicit prerequisite error.
- **FR-011**: Optional-resource absence MUST be distinguishable from missing
  metadata for a required resource. Disabled resources MUST NOT require
  invented endpoints, placeholder identities or unrelated configuration access.
- **FR-012**: The change MUST preserve authorization, least-privilege access,
  resource ownership, foundation/application separation, network isolation and
  supported shared-resource behavior. It MUST NOT broaden access to compensate
  for the metadata-source change.
- **FR-013**: PowerShell and shell lifecycle entry points MUST provide equivalent
  metadata consumption, validation, failure and retry behavior for both providers.
- **FR-014**: Automated acceptance coverage MUST exercise both providers and both
  runtime modes, including successful deployments, missing and malformed data,
  conflicting environment bindings, identity mismatches and prohibited sensitive
  outputs. It MUST distinguish store-free discovery from runtime store access.
- **FR-015**: Changes to a published metadata contract MUST identify affected
  consumers and preserve existing supported runtime consumers without requiring
  application runtime changes. A new metadata contract MUST use an explicitly
  versioned transition with documented adoption and recovery. Existing contract
  versions MUST NOT be silently redefined.
- **FR-016**: Central AI Landing Zones documentation MUST explain the four
  configuration categories, supported mode/store combinations, metadata
  provenance and delivery to scripts, required permissions, and recovery from
  missing or conflicting metadata for both providers.

### Key Entities *(include if feature involves data)*

- **Infrastructure input**: An operator-declared parameter defining requested
  topology and options. It is not a value discovered from runtime settings.
- **Deployment context**: The selected environment and provider, target
  subscription, resource-group ownership and deployment identity against which
  operations are checked.
- **Deployment metadata**: Non-secret descriptions of provisioned resources,
  including endpoints, resource identifiers, identities, feature availability
  and Foundry project binding, associated with one deployment context.
- **Runtime configuration selection**: The chosen application-settings delivery
  mode and whether the selected application or feature requires a store.
- **Secret reference**: A reference to a Key Vault-managed secret. Its resolved
  value is excluded from deployment discovery and non-secret artifacts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Automated acceptance exercises all four primary provider/mode
  combinations through their provision-output and deploy-hook boundaries.
  Both store-free combinations omit the configuration store and make zero
  requests to that service in the exercised flows.
- **SC-002**: Every selected platform configuration operation in the acceptance
  scenarios completes without manual metadata entry into a configuration store.
  No new application or live application-readiness demonstration is required.
- **SC-003**: Every invalid-destination case in the acceptance set is rejected
  before a dependent resource change. The set covers missing, malformed,
  conflicting and stale metadata, wrong subscriptions and resource groups,
  and mismatched resource identities and project endpoints.
- **SC-004**: Discovery requests and resulting non-secret artifacts contain zero
  secret values or unapproved outputs, and no acceptance journey requires
  access to full infrastructure state.
- **SC-005**: Each primary combination passes separate-invocation and two-run
  regression scenarios with unchanged inputs, without cross-environment
  changes or loss of required settings.
- **SC-006**: An operator following the central guidance can identify the source,
  purpose and secret-handling boundary of all four configuration categories and
  complete each documented provider/mode walkthrough without undocumented steps.
- **SC-007**: Both lifecycle entry points produce equivalent pass/fail outcomes
  for the full acceptance set. Recorded evidence distinguishes automated
  simulation from completed cloud deployments and identifies every unverified
  scenario.

## Assumptions

- Scope is issue #875's deployment-dependency removal, not a general application
  runtime rewrite. Application runtime changes are out of scope. No additional
  application is created and no live reference-application validation is required,
  while all selected platform configuration steps remain required. Existing
  applications retain their current runtime behavior. This feature does not
  claim that every bundled runtime supports store-free operation or silently
  remove features that require a store.
- The four primary acceptance combinations are Bicep and Terraform, each using
  `containerEnv` without a store and `appConfig` with a usable store. Keeping a
  store provisioned in `containerEnv` is an additional compatibility case.
- Existing defaults and the distinct behavior of runtime mode `none` remain
  unchanged. Expanding that mode or introducing a new runtime mode is out of
  scope.
- If live deployment evidence is gathered later with an already compatible
  application, use fresh environments. Automated coverage does not establish
  cloud parity or application readiness. This feature does not authorize deleting
  a store from an existing environment or promise an in-place runtime-mode
  migration. Adoption and recovery instructions must make these limitations explicit.
- Operators retain the permissions and network connectivity already required
  to verify and configure their selected resources. Store-free discovery does
  not remove Key Vault or other genuine service prerequisites.
- `Azure/agent-landing-zone` owns provider outputs, deployment contracts, hooks
  and configuration modules. `Azure/AI-Landing-Zones` owns the published operator
  documentation. Application runtime implementation remains in the component
  repositories identified by `manifest.json` and is not changed by this feature.
- Planning must inventory metadata consumers and contract compatibility, assess
  alternatives, and record the required architectural decision before
  implementation. This specification does not select a new artifact format,
  schema version or output adapter.
- Relevant central documentation includes configuration, Bicep and Terraform
  deployment, full-stack and infrastructure-only deployment, and operations
  guidance. Those pages must describe the shipped behavior when this feature is
  delivered, not claim store-free deployment is already available.
