# Changelog

## [v5.5.1] - 2026-10-28

### Changed
- Default application Cosmos DB to disabled in Bicep, Terraform and parameter
  seeds. Shared deployment composition enables it for classic orchestration,
  panel metadata, preserved classic runtime and custom conversation-store
  consumers; incompatible explicit disables fail before provisioning.
- Omit application-specific Cosmos identities, resources and container settings
  when disabled. Foundry Agent Service backing storage and shared private DNS
  remain independent.
- Keep preflight and lifecycle recovery aligned with the effective application
  selection. Review existing-environment previews and retain
  `DEPLOY_COSMOS_DB=true` until existing data and consumers have been reviewed.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.4.0 |
| agent-app-orchestrator | v5.3.0 |
| agent-app-ingestion | v3.1.3 |
| infra / AI Landing Zone | v2.7.3 |

- Targeted deployment and lifecycle regressions pass; Terraform validation and
  all 90 mocked tests pass. Preflight coverage passes 394 checks.
- Bicep compiles with the pinned compiler; PowerShell parsing and shell syntax
  checks pass. Both providers retain the same application selection contract.
- Central configuration documentation is published. Validation is local and
  offline; no live Azure deployment, data migration or resource cleanup was
  performed. Extended local suites were stopped and are not claimed as passing.

## [v5.5.0] - 2026-10-28

### Added
- Platform configuration for integrated delegated hosted retrieval:
  `RETRIEVAL_AUTH_MODE=native_search` is published automatically under
  `agent-lz`, retaining user-delegated Foundry invocation. The discovered
  hosted runtime receives Search Index Data Reader on the exact Search
  service for transport, independently of end-user source permissions.
- Include `retrieval-reader` in the bundled UI capabilities for fresh native
  Search authorization before conversation-upload downloads. Preserve existing
  Blob grants; transport roles never replace the user's document permissions.
- Native Work IQ app authentication and secretless indexed SharePoint source
  registration, with typed nonsecret identity inputs. Advanced source
  configuration requires its compatible August preview API; the default Blob
  API remains unchanged. Fabric sources receive a planning model and supported
  reasoning effort.
- ADR-0029 defines the coordinated UI/runtime credential forwarding,
  request isolation, failure and adoption contract.

### Changed
- Ship coordinated UI and orchestrator knowledge security, including signed
  user/session-bound citation downloads, current-user Storage authorization
  for shared documents, and exact-document checks for conversation uploads.
- Preserve downstream Conditional Access challenges through both hosted
  protocols and offer explicit standalone or portal sign-in recovery without
  replaying failed or partially completed operations.
- Require manual dispatch for the orchestrator's development deployment
  workflow; normal source updates retain their quality checks.

### Fixed
- Enable native document permissions on new application indexes and reconcile
  existing compatible indexes with conditional updates, without deleting
  documents or operator customizations. Incompatible permission annotations
  block the update rather than retaining unprotected access.
- Reject incomplete enabled sources and fail Work IQ consent checks before
  Search resource changes. Configured sources are never silently removed to
  make provisioning succeed.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.4.0 |
| agent-app-orchestrator | v5.3.0 |
| agent-app-ingestion | v3.1.3 |
| infra / AI Landing Zone | v2.7.3 |

- Platform retrieval provisioning, permission profiles, shared deployment
  composition and Bicep/Terraform interface contracts pass.
- Component acceptance covers full behavioral suites, actual hosted SDK
  contracts, installed-wheel and offline Linux-container execution, and the
  protected quality checks.
- Central documentation builds in strict MkDocs mode, including both
  infrastructure-provider runbooks and the complete authentication recovery
  setup.

## [v5.4.0] - 2026-10-27

### Added
- Add an integrated Terraform foundation under `infra/terraform`, using a flat
  AVM-based composition, pinned modules and a committed Linux/Windows provider
  lock. Bicep remains the default; both providers use the shared azd application
  lifecycle, typed configuration and complete deployment-output contract.
- Add Terraform contract checks on Linux and Windows alongside the existing
  Bicep, Python and cross-platform lifecycle checks.

### Changed
- Preserve foundation/application ownership, deployed runtime images, App
  Configuration labels and Key Vault references across provisioning. Bind
  Terraform backend and resource-group ownership for state-scoped teardown,
  with the documented single-writer model for shared state.
- Require bidirectional Bicep/Terraform parity for every infrastructure change
  in AGENTS, Copilot instructions and constitution v2.1.0.
- Align managed Code Quality analysis with the remaining Python sources after
  retiring the JavaScript-only parity tooling.
- Organize central deployment runbooks by infrastructure-only/full-stack outcome,
  with separate Bicep and Terraform paths and a Terraform composition overview.

### Removed
- Retire the external Terraform parity assessment/publication automation and
  its dedicated operational assets, retaining historical decision records.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.1 |
| agent-app-orchestrator | v5.2.2 |
| agent-app-ingestion | v3.1.3 |
| infra / AI Landing Zone | v2.7.3 |

- GitHub CI passes Terraform contracts on Linux and Windows, Bicep build/lint,
  offline foundation contracts and the full deployment/hook suite:
  1,095 tests, 873 subtests and 7 skips.
- The complete local Terraform suite passes 89 tests. A public-foundation
  Azure-authenticated plan in `swedencentral` passes without applying resources;
  no full-stack Azure deployment was executed for this release.
- Central documentation builds in strict MkDocs mode; navigation, links and the
  Terraform diagram are validated. Runtime component pins are unchanged.

## [v5.3.0] - 2026-10-27

### Added
- Prepare dedicated Power Platform and AI Gateway subnets with the required
  service delegations. Isolated deployments create all twelve architecture
  subnets by default, with individual creation switches and configurable
  names and IPv4 ranges for new and existing virtual networks.

### Changed
- Use a dedicated application private endpoint subnet by default, independently
  of the Foundry and grounding private endpoint subnet. Use the reserved
  `GatewaySubnet` name without NSG, route-table or delegation attachments.
- Apply global and individual subnet creation ownership consistently to both
  virtual network paths. Validate enabled consumers, actual existing-network
  properties, address overlap, delegated-subnet providers and APIM integration
  NSG requirements before provisioning; do not silently reuse the Foundry subnet.
- These are defaults for new deployments. Existing occupied subnets and private
  endpoints are not automatically renamed or migrated; review explicit network
  inputs and resource dependencies before applying the changed topology.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.1 |
| agent-app-orchestrator | v5.2.2 |
| agent-app-ingestion | v3.1.3 |
| infra / AI Landing Zone | v2.7.3 |

- GitHub CI passes `python -m pytest tests --quiet`, Bicep build/lint and all
  17 offline foundation contract entrypoints. Subnet coverage includes 500
  assertions and exact mutation-tested preservation of historical fingerprints.
- The deterministic preflight suite passes 382 assertions. Targeted Python
  regression coverage passes 174 tests across resource groups, deployment modes,
  custom composition, provider prerequisites and regional quota checks.
- Central documentation builds in strict MkDocs mode; all 36 subnet parameter
  bindings match the implementation.
- Validation is offline; no live Azure provisioning was performed.

## [v5.2.0] - 2026-10-27

### Changed
- Prepare the bundled Foundry hosted image automatically during `azd deploy`,
  binding its immutable digest to the provisioned foundation without another
  `azd provision`. Fresh hosted deployments also support `azd up`; unchanged
  images are reused and stale generated source/startup provenance is rebuilt
  during deployment. Standalone preparation scripts remain optional
  compatibility commands.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.1 |
| agent-app-orchestrator | v5.2.2 |
| agent-app-ingestion | v3.1.3 |
| infra / AI Landing Zone | v2.7.3 |

- Repository deployment and contract suite: 795 tests and 767 subtests pass;
  5 tests are skipped. Targeted integration coverage including continuity:
  451 tests and 312 subtests pass, with 1 skipped test.
- PowerShell and Bash hook checks, Bicep build/lint and the offline foundation
  contract runner pass. Published component and infrastructure tag/commit
  bindings match the manifest; incorporated infrastructure is unchanged.
- Central documentation builds in strict mode. The Azure DevOps example
  validator passes 310 promotion cases plus Bash/Python and cleanup checks.
  Runbooks and Agent Landing Zone What's new describe the simplified workflow.

## [v5.1.1] - 2026-10-27

### Fixed
- **SharePoint permission-only synchronization.** Pin Agent App Ingestion
  v3.1.3 to refresh supported user/group ACLs on every affected item document
  and document-library chunk independently of content timestamps. Remove
  revoked principals without reprocessing unchanged content, include
  Graph-reported inherited file permissions and retry failed ACL updates.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.1 |
| agent-app-orchestrator | v5.2.2 |
| agent-app-ingestion | v3.1.3 |
| infra / AI Landing Zone | v2.7.3 |

- Ingestion's complete maintained suite passes: 1,015 tests and 10 subtests;
  its evidence-bound quality gate reports no findings.
- Deployment and lifecycle contracts, Bicep build/lint and all 16 offline
  foundation entrypoints pass. Exact graph projections reject 27 mutations
  while preserving historical fingerprints.
- Published component tag/commit bindings and the strict central
  documentation build pass.

## [v5.1.0] - 2026-10-27

### Added
- Add optional per-component runtime egress declarations, an offline review
  plan and source-subnet-scoped reconciliation of owned application rules.
  Preserve legacy definitions, unrelated rules and shared requirements;
  external policies are report-only and non-isolated deployments perform
  no firewall operations.
- Declare the orchestrator and ingestion cold-cache tiktoken dependency;
  the UI declares no additional runtime egress.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.1 |
| agent-app-orchestrator | v5.2.2 |
| agent-app-ingestion | v3.1.2 |
| infra / AI Landing Zone | v2.7.3 |

- Focused application, lifecycle, schema, selection and policy reconciliation
  suites: 216 passed, 3 skipped and 220 subtests passed. Both hook variants and
  actual compiled foundation rule-group priorities are covered.
- All 16 offline foundation entrypoints pass. Final projection checks reject
  25 mutations while retaining the original protected fingerprints and the
  closed platform-outputs v1 schema.
- Real cold-cache tokenizer initialization passes separately with the pinned
  ingestion tiktoken 0.7.0 and orchestrator tiktoken 0.14.0, downloading both
  encoding assets from the declared HTTPS host.
- Strict central documentation build, agent asset validation and published
  runtime tag/commit checks pass.

## [v5.0.0] - 2026-10-27

### Changed
- **Foundry-first deployment root.** Use `AZURE_RESOURCE_GROUP` for Foundry,
  grounding and the native azd root; select application resources with
  `AZURE_APP_RESOURCE_GROUP`.
- **Three resource groups by default for new environments.** Initialize
  Foundry/root as `rg-<environment>` when unset, application as `<root>-app`
  and networking as `<root>-network`. Create missing additional groups by
  default unless `CREATE_RESOURCE_GROUPS=false`. Existing environments keep
  their mapping; equal destination names explicitly select one or two groups.
- **Application-scoped deployment and configuration.** Align foundation
  resources, runtime deployment scripts, custom Container App targeting,
  registry builds, identities, configuration and operator documentation with
  the resolved application destination.
- **Immutable native-root binding.** Record the Foundry-root contract in
  binding version 2 and reject implicit conversion of existing version 1
  split environments. The closed platform-outputs v1 schema is unchanged.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.1 |
| agent-app-orchestrator | v5.2.2 |
| agent-app-ingestion | v3.1.2 |
| infra / AI Landing Zone | v2.7.3 |

- Deployment, destination binding, application-definition and lifecycle
  contract regressions pass, including native first-run azd initialization
  and matching PowerShell/shell destination propagation.
- Bicep build/lint and offline foundation contracts pass with the original
  protected graph fingerprints, reviewed scoping projections and unchanged
  platform-output schema.
- Published runtime tag/commit bindings and incorporated infrastructure
  provenance are verified. The central documentation build passes.

## [v4.4.0] - 2026-10-26

### Added
- Add configurable application, Foundry/grounding and local-network
  resource-group destinations through one `azd provision`, retaining the
  single-resource-group default and supporting one, two or three distinct
  destinations in the workload subscription.
- Add `AZURE_FOUNDRY_RESOURCE_GROUP` and `AZURE_NETWORK_RESOURCE_GROUP`,
  falling back to application/root `AZURE_RESOURCE_GROUP`, and strict
  `CREATE_RESOURCE_GROUPS` opt-in, defaulting to `false`, for missing
  additional destinations only.
- Add paired `AZURE_APPLICATION_PE_SUBNET_NAME` and
  `AZURE_APPLICATION_PE_SUBNET_PREFIX` settings independently of RG count;
  omitted values preserve the shared private-endpoint subnet.

### Changed
- Scope foundation resources, exact resource-ID RBAC and dependent bindings
  to their owners without changing default names, feature gates, public-access
  settings or existing BYO network/DNS precedence.
- Align PowerShell and shell hooks, Foundry configuration, quota preflight,
  application/storage consumers and nonsecret `agent-lz` handoff context.
  The closed platform-outputs v1 JSON and runtime pins remain unchanged.
- Persist destination bindings, reject implicit migration/retargeting and
  converge partial bootstrap retries without changing reused RG metadata.
  Split-layout `azd down` fails closed; cleanup requires an explicit
  resource-owner inventory, not automatic rollback or shared-RG deletion.
- Coordinate the existing central documentation pages for configuration,
  permissions, ownership, private networking, lifecycle and recovery.
  Configurable RGs are supported by the Agent Bicep/azd entrypoint only;
  Terraform and Portal support are not claimed.

### Fixed
- Use supported Azure CLI resource inventory filters during destination
  preparation, retaining strict environment-tag matching and access failures.
- Apply jumpbox Reader grants at the resolved resource-group deployment scope
  rather than treating a resource-group ID as a service resource. Preserve
  assignment GUIDs, per-resource grants and the single-group behavior.
- Load application schema/YAML validation dependencies only when validation
  runs, so destination binding can bootstrap on a fresh jumpbox before
  post-provision installs the declared Python requirements.
- Resolve the declared registry owner with an explicit repository import path
  on isolated jumpbox Python, preserving default and custom-registry routing.
- Load post-provision environment values through validated azd JSON on both
  platforms, preserving structured identity metadata, quotes and multiline
  values without interpreting them as shell expressions.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.0 |
| agent-app-orchestrator | v5.2.1 |
| agent-app-ingestion | v3.1.1 |
| infra / AI Landing Zone | v2.7.3 |

- Full local Python/configurator regressions: 883 passed, 4 skipped and
  970 subtests passed. Clean Linux deployment/hook CI: 654 passed, 6 skipped
  and 741 subtests passed.
- All 16 offline foundation entrypoints pass with Bicep 0.42.1, including
  145 scope assertions, 17 rejected normalization mutations and the original
  protected graph fingerprints. Both hook variants pass syntax/behavior checks.
- Strict central documentation build and rubber-duck documentation review
  pass. Runtime tag/commit bindings and incorporated infrastructure
  provenance are verified without changing component or source pins.
- Authorized private Azure validation completed native three-destination
  provisioning, verified five private DNS/TLS endpoints with anonymous
  access denied, and exercised the unchanged default chat and 3072-dimensional
  embedding models with managed identity. Actual subscription deployment
  writes and unauthorized private vault data access were denied. A targeted
  recovery resolved an Azure private-endpoint internal error.

## [v4.3.5] - 2026-10-26

### Changed
- Rename the subscription header to "Agent Landing Zone - prod subscription"
  in all three reference architecture PNGs, matching the editable draw.io source.
- Preserve the two-diagram README, full-resolution image links, resource
  placements, UDR locations, management-group labels and AI Gateway subscription.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.0 |
| agent-app-orchestrator | v5.2.1 |
| agent-app-ingestion | v3.1.1 |
| infra / AI Landing Zone | v2.7.3 |

- Documentation-only patch: runtime component pins and all application,
  configuration, deployment script and infrastructure sources remain unchanged.
- Canonical draw.io comparison allows only the three subscription text values;
  all image pixels outside those labels are identical to the previous exports.
- Verify complete PDF bounds and bottom labels, all 6400-pixel-wide PNGs and
  the central documentation site's strict build.
- Pass all 39 existing release-contract regressions for the unchanged
  component and infrastructure combination.
- No Azure deployment is required for these unchanged runtime sources.

## [v4.3.4] - 2026-10-26

### Changed
- Show only the Standalone and Platform Hub diagrams in the README Architecture
  section, retaining their full-resolution image links.
- Remove the AI Gateway + Platform Hub subsection from the README only;
  preserve every diagram asset and the central documentation site.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.0 |
| agent-app-orchestrator | v5.2.1 |
| agent-app-ingestion | v3.1.1 |
| infra / AI Landing Zone | v2.7.3 |

- Documentation-only patch: runtime component pins and all application,
  configuration, deployment script, infrastructure sources and images are unchanged.
- Verify exactly two architecture images in the intended order, both
  full-resolution links and an otherwise unchanged README.
- Pass all 39 existing release-contract regressions for the unchanged
  component and infrastructure combination.
- No Azure deployment is required for these unchanged runtime sources.

## [v4.3.3] - 2026-10-26

### Changed
- Move the workload UDR icon and caption to the space above AppGateway subnet
  in the Platform Hub and Platform Hub with AI Gateway architecture diagrams.
- Refresh only the two corresponding 6400-pixel-wide PNGs, preserving the
  Standalone diagram and the separate AI Gateway landing-zone UDR.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.0 |
| agent-app-orchestrator | v5.2.1 |
| agent-app-ingestion | v3.1.1 |
| infra / AI Landing Zone | v2.7.3 |

- Documentation-only patch: runtime component pins and all application,
  configuration, deployment script and infrastructure sources remain unchanged.
- Canonical draw.io comparison allows only the two workload UDR group positions;
  verify the new position is above AppGateway subnet without overlapping resources.
- Preserve full export bounds and bottom labels; build the central documentation
  site in strict mode and compare published PNG hashes with the source exports.
- Pass all 39 existing release-contract regressions for the unchanged
  component and infrastructure combination.
- No Azure deployment is required for these unchanged runtime sources.

## [v4.3.2] - 2026-10-26

### Changed
- Rename the three architecture diagram titles to Agent Landing Zone.
- Use the approved two-line title for the integrated scenario:
  "Agent Landing Zone with Platform Hub" and "and AI Gateway Landing Zone".
- Refresh the 6400-pixel-wide PNGs while preserving all existing resource
  placements, connections, full-resolution links and safe export margins.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.0 |
| agent-app-orchestrator | v5.2.1 |
| agent-app-ingestion | v3.1.1 |
| infra / AI Landing Zone | v2.7.3 |

- Documentation-only patch: runtime component pins and all application,
  configuration, deployment script and infrastructure sources remain unchanged.
- Canonical draw.io comparisons allow only the approved title text and the
  integrated title box height; PNG differences are confined to the title area.
- Verify complete bottom panels and all 6400-pixel-wide image dimensions;
  build the central documentation site in strict mode.
- Pass all 39 existing release-contract regressions for the unchanged
  component and infrastructure combination.
- No Azure deployment is required for these unchanged runtime sources.

## [v4.3.1] - 2026-10-25

### Changed
- Refresh the README architecture section with high-resolution Standalone,
  Platform Hub and AI Gateway + Platform Hub reference diagrams and links to
  the full-size PNGs.

### Fixed
- Include the complete lower panels of the AI Gateway diagram with safe
  export margins, and use `rg-networking` consistently in all three diagrams.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.0 |
| agent-app-orchestrator | v5.2.1 |
| agent-app-ingestion | v3.1.1 |
| infra / AI Landing Zone | v2.7.3 |

- Documentation-only patch: runtime component pins and all application,
  configuration, deployment script and infrastructure source are unchanged
  from v4.3.0.
- Verify all three 6400-pixel-wide PNGs, full-resolution README links, corrected
  RG labels and complete bottom panels against the original draw.io export.
- Build the central documentation site in strict mode and verify the published
  HTML and exact PNG hashes.
- Pass all 39 existing release-contract regressions with the unchanged pinned
  component and infrastructure combination.
- No Azure deployment or live-environment validation is needed for these
  unchanged runtime and infrastructure sources.

## [v4.3.0] - 2026-10-14

### Added
- Add opt-in persistent firewall DNS proxy configuration through
  `ENABLE_FIREWALL_DNS_PROXY`, defaulting to `false` without changing client DNS.
- Gate network-isolated native Foundry IQ Blob ingestion on the exact Search
  shared private links being approved and successfully provisioned. Pending
  links fail with administrator approval instructions; no unrelated or
  target-side connections are approved automatically.
- Honor explicit empty native Blob ingestion permission options for deliberately
  shared, non-ADLS sources while retaining protected defaults and rejecting
  unsupported or ambiguous configurations.

### Changed
- Pin UI v3.3.0 for ingestion-aware upload controls and early server-side
  attachment rejection when the ingestion application is disabled. Text chat,
  authentication and retrieval remain available.
- Complete build-subnet-only HTTPS egress for the pinned Microsoft npm feeds
  and package-download CDN without requiring firewall DNS proxy.
- Make the ingestion Container App an independent, explicit deployment choice.
  Fresh supported native-ingestion deployments omit it; existing and custom
  deployments retain their prior component choices. Disabling deployment does
  not delete existing applications or document data.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.3.0 |
| agent-app-orchestrator | v5.2.1 |
| agent-app-ingestion | v3.1.1 |
| infra / AI Landing Zone | v2.7.3 |

- Offline platform, panel and Search regressions, exact application source
  binding and release-contract checks, and compiled foundation contracts.
- UI source, installed-wheel and offline container regressions with all quality
  gates passing; strict central documentation build.
- Azure deployment and live-environment validation were intentionally omitted.

## [v4.2.3] - 2026-10-14

### Fixed
- Update the UI to v3.2.2 for Hosted `api-version=v1` requests, both supported
  conversation identifier envelopes, and classic-only history registration.
- Update the orchestrator to v5.2.1 for explicit null-label configuration
  selection and opt-in verified App Configuration and Key Vault transport.
- Export the deployed application Key Vault URI from the foundation and pass it
  to the bundled hosted agent, avoiding environment-specific vault hardcoding
  during configuration bootstrap.
- Preserve structured deployment environment values, validate custom application
  definitions before provisioning, and publish provisioned identity client IDs.
- Correct custom Container Apps registry identity wiring, custom Hosted
  foundation preparation, and operator role-definition UUID lookup.
- Correct effective-region Search and incremental model quota preflight,
  Foundry local-auth handling, and administrative-panel database settings.

### Added
- Pass the opt-in `APP_CONFIG_TLS_COMPATIBILITY` bootstrap control to the hosted
  agent with a default of `false`; enabling it requires `KEY_VAULT_URI` and
  preserves existing identity, certificate verification, and hostname validation.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.2.2 |
| agent-app-orchestrator | v5.2.1 |
| agent-app-ingestion | v3.1.1 |
| infra / AI Landing Zone | v2.7.3 |

- Offline component regression and protected CI checks, application binding and
  release-contract tests, and foundation template compilation and size checks.
- Azure deployment and environment validation were intentionally omitted.

## [v4.2.2] - 2026-10-08

### Changed
- Updated the pinned `agent-app-ui` release from v3.2.0 to v3.2.1.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.2.1 |
| agent-app-orchestrator | v5.2.0 |
| agent-app-ingestion | v3.1.1 |
| infra / AI Landing Zone | v2.7.3 |

## [v4.2.1] - 2026-10-08

### Changed
- Renamed the hosted agent custom role to "Agent Landing Zone Hosted Agent User Identity Impersonation"; setup updates the role name in existing environments.
- The evaluation workflow now targets the `agentlz-evaluation` environment, and the Copilot coding agent signs in to Azure through OIDC.
- Removed the legacy `gpt-rag-mcp` component from the issue templates.
- README and documentation wording now positions the solution as conversational agent experiences rather than RAG only.
- Aligned the infra checkout test with the tracked `infra/main.parameters.json` seed.

### Validation

| Component | Version |
| --- | --- |
| agent-app-ui | v3.2.0 |
| agent-app-orchestrator | v5.2.0 |
| agent-app-ingestion | v3.1.1 |
| infra / AI Landing Zone | v2.7.3 |
## [v4.2.0] - 2026-10-06

### Changed
- Pinned the final component releases: agent-app-ui v3.2.0, agent-app-orchestrator v5.2.0, agent-app-ingestion v3.1.1. Components now read only the `agent-lz` App Configuration label; the legacy `gpt-rag` label read was removed.
- Reworded remaining GPT-RAG prose in post-provision modules, tests, and workflows to Agent Landing Zone, and narrowed the temporary naming allow-list in `contracts/naming-map.md`.
- The release-contract test now validates the manifest tag format instead of a fixed version.

### Validation

| Component | Version |
| --- | --- |
| gpt-rag-ui | v3.2.0 |
| gpt-rag-orchestrator | v5.2.0 |
| gpt-rag-ingestion | v3.1.1 |
| infra / AI Landing Zone | v2.7.3 |

## [v4.1.3] - 2026-10-06

### Fixed
- First `azd up` on a fresh clone failed with "missing required inputs" because the Bicep provider reads `infra/main.parameters.json` before the `preprovision` hook generates it. azd initializes the provider before any hook runs, so `infra/main.parameters.json` is now committed as a seed (copy of `main.parameters.json`); `preprovision` still recomposes it on every provision, so a local diff on that file after provisioning is expected.
- The `preprovision` hooks (PowerShell and shell) now automatically mark `infra/main.parameters.json` as skip-worktree in git checkouts, so the regenerated parameters no longer appear in `git status`. Run `git update-index --no-skip-worktree infra/main.parameters.json` to commit intentional seed changes.

### Validation

| Component | Version |
| --- | --- |
| gpt-rag-ui | v3.1.1 |
| gpt-rag-orchestrator | v5.1.1 |
| gpt-rag-ingestion | v3.0.1 |
| infra / AI Landing Zone | v2.7.3 |

## [v4.1.2] - 2026-10-06

### Fixed
- Fresh deployments failed in preprovision because `app-definition.json` `source.commit` values did not match the component commits pinned in `manifest.json`. The app definition now pins the same commits as the manifest.

### Validation

| Component | Version |
| --- | --- |
| gpt-rag-ui | v3.1.1 |
| gpt-rag-orchestrator | v5.1.1 |
| gpt-rag-ingestion | v3.0.1 |
| infra / AI Landing Zone | v2.7.3 |

## [v4.1.1] - 2026-10-06

### Changed
- `DEPLOY_ACR_TASK_AGENT_POOL` now defaults to `true`. With `NETWORK_ISOLATION=true` the foundation provisions the in-VNet ACR Task agent pool, so remote image builds work without opening the registry to the public network. Without network isolation no pool is created (#741).

### Fixed
- `azd deploy` now fails early, before deploying any application, when `NETWORK_ISOLATION=true` and no ACR Task agent pool exists, with guidance to provision the pool or use `BUILD_MODE=local` from a VNet-connected host (#741).
- Keyless UI-to-orchestrator auth now works with the default system-assigned frontend identity: post-provision publishes `ORCHESTRATOR_AUTH_AUDIENCE` as the Azure Resource Manager audience when no user-assigned identity or explicit audience exists. Previously the audience was empty and chat returned 401 (ADR-0019).
- Components pinned to the patch releases with the same network-isolation guard: gpt-rag-ui v3.1.1, gpt-rag-orchestrator v5.1.1, gpt-rag-ingestion v3.0.1.

### Validation

| Component | Version |
| --- | --- |
| gpt-rag-ui | v3.1.1 |
| gpt-rag-orchestrator | v5.1.1 |
| gpt-rag-ingestion | v3.0.1 |
| infra / AI Landing Zone | v2.7.3 |

## [v4.1.0] - 2026-10-05

### Fixed
- Chat returned 401 on a default deployment because the orchestrator required a credential that was never provisioned. The UI now authenticates to the orchestrator without keys, using a managed identity token sent in `X-Service-Authorization` (ADR-0019). In classic mode, post-provision publishes `ORCHESTRATOR_AUTH_AUDIENCE` and `ORCHESTRATOR_ALLOWED_CALLER_IDS` (label `agent-lz`), taken from the UI's user-assigned identity. Both can be overridden through environment variables. Requires the orchestrator and UI releases that include Azure/agent-app-orchestrator#370 and Azure/agent-app-ui#118.

### Changed
- The orchestrator API key (`USE_CAPP_API_KEY`) is now an opt-in fallback that defaults to `false`. Composition forces it off in hosted-agent topologies, which have no Dapr and use Entra ID, unless `PRESERVE_CLASSIC_RUNTIME=true` keeps the classic orchestrator.

### Validation

| Component | Version |
| --- | --- |
| gpt-rag-ui | v3.1.0 |
| gpt-rag-orchestrator | v5.1.0 |
| gpt-rag-ingestion | v3.0.0 |
| infra / AI Landing Zone | v2.7.3 |

## [v4.0.0] - 2026-10-03

### Changed
- **Breaking:** GPT-RAG is now Agent Landing Zone. The product, repositories, and user-visible names are renamed.
- **Breaking:** App Configuration label renamed to `agent-lz`.
- **Breaking:** Environment variables use the `AGENTLZ_` prefix.
- Infrastructure is now kept in this repository instead of being pulled from an external template.
- Component pins updated to the GA releases (UI `v3.0.0`, orchestrator `v5.0.0`, ingestion `v3.0.0`). These read App Configuration settings from both the `agent-lz` and the legacy `gpt-rag` labels.

### Added
- Infrastructure-only deployment: run `azd provision`, then `azd deploy` later.
- Custom application deployment through `app-definition.json` (see `samples/custom-app`).

### Notes
- New deployments only. Existing GPT-RAG deployments are not upgraded in place; redeploy into a new environment. GPT-RAG release tags stay available.

### Validation

| Component | Version |
| --- | --- |
| gpt-rag-ui | v3.0.0 |
| gpt-rag-orchestrator | v5.0.0 |
| gpt-rag-ingestion | v3.0.0 |
| infra / AI Landing Zone | v2.7.3 |

## [v3.8.11] - 2026-09-28

### Documentation
- Every component that loads the `gpt-rag` App Configuration label (UI, orchestrator, hosted-agent identity) needs **Key Vault Secrets User** to resolve Key Vault references such as `authClientSecret`. Without it the orchestrator returns HTTP 500 (#716).
- Client secret expiry and rotation guidance (#716).

## [v3.8.10] - 2026-09-25

### Fixed
- `azd deploy` failing on azd 1.34+ because the hosted-agent postdeploy hook path escaped the service project root. The hook now runs through wrappers in `hosted-agent/hooks/`.

### Documentation
- UI OAuth settings (`OAUTH_AZURE_AD_CLIENT_ID`, `OAUTH_AZURE_AD_TENANT_ID`, `authClientSecret` as a Key Vault reference) belong in App Configuration (label `gpt-rag`). Env vars set by hand on the container app are lost on `azd provision`.

## [v3.8.9] - 2026-09-25

### Fixed
- `azd provision` on existing environments failing on Cosmos DB with `Continuous backup mode cannot be disabled`. AI Landing Zone updated to v2.7.3.

### Changed
- Dependency updates from Dependabot (#706, #707).

## [v3.8.8] - 2026-09-25

### Changed

- **AI Landing Zone pinned to the latest `v2.7.2`** (`892bbdb`), which carries the
  v2.5.x-v2.7.1 fixes plus the #708 image-preservation fix. Replaces the
  temporary `v2.5.1.1` hotfix pin used by v3.8.7, which was withdrawn.
  New landing-zone parameters use their defaults; no configuration changes
  are required.

## [v3.8.7] - 2026-09-25

### Fixed

- **`azd provision` no longer resets Container Apps to the placeholder image**
  ([#708](https://github.com/Azure/GPT-RAG/issues/708)). Pre-provision now
  discovers the images already running (by `azd-service-name` tag) and passes
  them to the landing zone (pin superseded by v3.8.8), which keeps
  the image and its ACR registry binding. Set `RESET_CONTAINER_APP_IMAGES=true`
  to opt out.
- **Hosted-agent endpoint is published before component deploys**
  ([#709](https://github.com/Azure/GPT-RAG/issues/709)). Pre-deploy now stores
  `HOSTED_AGENT_BASE_URL` in the azd environment and App Configuration as soon
  as the hosted agent is deployed, so the UI and later re-provisions always see
  it. Routing still switches only after the full cutover succeeds.
## [v3.8.6] - 2026-09-25

### Fixed

- **Ingestion pinned to `v2.7.4`** (`75a2ef1`). The ingestion frontend build
  now uses a consistent lockfile, so `npm ci` succeeds in ACR task and local
  builds. Other runtime pins (UI `v2.6.2`, orchestrator `v4.1.1`) and the
  AI Landing Zone pin (`v2.5.1`) are unchanged.

### Known issues

- Re-running `azd provision` resets Container Apps images to the landing-zone
  placeholder; redeploy the components afterwards
  ([#708](https://github.com/Azure/GPT-RAG/issues/708)).
- The component deploy path can skip publishing the hosted-agent endpoint to
  App Configuration; run the pre-deploy publish steps manually
  ([#709](https://github.com/Azure/GPT-RAG/issues/709)).

## [v3.8.5] - 2026-09-21

### Changed

- **Credential-free private connectivity prerequisites instead of a
  deploy-only `RUN_FROM_JUMPBOX` declaration gate**
  ([#703](https://github.com/Azure/GPT-RAG/pull/703)). Shared checks use the
  operating system's DNS resolution, including Windows NRPT, and require
  1-16 resolved addresses, all RFC1918 IPv4. Public, loopback, mixed, and
  IPv6 results fail closed before connecting. Checks pin each resolved IP on TCP 443
  and perform TLS with normal certificate verification and hostname SNI,
  using a 10-second DNS timeout within a 20-second per-hostname budget,
  without HTTP requests, credentials, tokens, or proxy routing.
- **Prerequisites follow the deployment stage.** Post-provision checks
  App Configuration; pre-deploy checks App Configuration and, for hosted
  deployment, Foundry. ACR is checked only when a hosted image build will
  actually run, not when a prebuilt or reusable immutable digest avoids
  building. Public deployment paths do not run these private probes.
- **Actual connectivity replaces host declarations.** An unset
  `RUN_FROM_JUMPBOX` performs the checks without prompting or automatically
  skipping in noninteractive execution, unless
  `AZURE_SKIP_NETWORK_ISOLATION_WARNING=true` explicitly defers
  post-provision. Explicit `RUN_FROM_JUMPBOX=false|0|no|skip` also defers
  post-provision, with a warning that configuration remains incomplete.
  Truthy jumpbox values take precedence over the warning flag but cannot
  bypass checks. Pre-deploy and actual hosted builds ignore both deferral
  flags and require successful checks.
- **Fail closed on invalid selected-environment output.** Hooks reject failed,
  empty, or malformed `azd env get-values` reads. Root pre-deploy uses one
  validated snapshot for the check and deployment; explicit empty values clear
  inherited process values, while absent keys preserve process inheritance.
- Coordinated deployment, VPN, configuration, and troubleshooting guidance was
  merged through [#702](https://github.com/Azure/GPT-RAG/pull/702). It retains
  unpublished-candidate wording until actual release publication.
- Runtime component pins, AI Landing Zone pins, and topology defaults are
  unchanged. The hosted runtime permission bootstrap remains the fix already
  released in `v3.8.4`; this patch does not broaden its grant allowlist or
  introduce document-access, native Blob, or infrastructure changes.

### Validation

The component combination is unchanged from `v3.8.4`.

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.6.2 |
| gpt-rag-orchestrator | v4.1.1 |
| gpt-rag-ingestion | v2.7.3 |
| infra / AI Landing Zone | v2.5.1 |

- Python 3.12 offline suite:
  `python -B -m pytest -q tests config -p no:cacheprovider --tb=short`:
  **472 passed, 480 subtests passed, 4 optional CLI cases skipped**.
  Focused private-network and release-pin contracts passed
  **34 tests and 108 subtests**. Network and Azure command boundaries were
  mocked, including execution of both hook variants with fake CLIs.
- All **4** optional installed-CLI parser/serialization cases passed separately
  with their socket and command-handler guards. PowerShell parsing and Bash
  syntax checks passed for both changed hook pairs. The agent-assets validator
  passed for **3 agents and 14 skills**, plus scoped instructions.
- The test harness supplied an empty `core.fsmonitor` override that
  environment-clearing tests cannot preserve on Windows. After verifying its
  key and empty value, validation used process-local `GIT_CONFIG_VALUE_2=false`;
  no repository/global Git configuration or test expectations were changed.
- Release metadata, manifest-derived tables, unchanged component and
  infrastructure pins, historical changelog preservation, and privacy checks
  passed. Final runtime source matches the reviewed feature in
  [#703](https://github.com/Azure/GPT-RAG/pull/703).
- A separate source-bound current-host probe rejected non-RFC1918 DNS for
  three configured endpoints. This is negative-only evidence, not positive
  VPN/private-TLS readiness or a fresh-install acceptance result.
- The prerequisites check deployment-host DNS/TCP/TLS only. Endpoint ownership,
  VNet/route mapping, RBAC, API health, build-pool egress, other service/data
  endpoints, and runtime-to-service connectivity still need separate evidence.
- No fresh automated deployment, role apply, model greeting, document
  authorization, scanning, or cold-start validation was performed for this
  candidate. No Azure mutations, image builds, or model calls were made
  during release preparation.

## [v3.8.4] - 2026-09-21

### Changed

- **Automated minimum hosted runtime permissions after agent creation**
  ([#697](https://github.com/Azure/GPT-RAG/pull/697)). The child deployment's
  PowerShell and POSIX postdeploy hooks explicitly apply an idempotent,
  allowlisted RBAC plan to the deployed agent's actual instance identity.
  The standalone command defaults to read-only planning; writes require
  explicit `--apply`. Grants are limited to App Configuration Data Reader on
  the exact configuration store, Cognitive Services OpenAI User on the exact
  model account, and, when configured, Key Vault Secrets User on the exact
  `AUDIT_HMAC_KEY` reference. No secret values are read. Conditional assignment
  conflicts fail closed rather than being bypassed.
- **Fail-closed root deployment greeting before UI cutover.** After the child
  hook succeeds, root deployment requires a completed response with non-empty
  assistant text from a stateless `Hello!` request in a new hosted session.
  Error, failed, incomplete, cancelled, or empty responses block cutover;
  an exact reply marker is no longer required. Direct child deployment remains
  RBAC-only and does not invoke the model. Bootstrap grants no Search, Storage
  Blob, Conversation, impersonation, Owner, or Contributor roles and does not
  change networking or authorization evidence gates.
- **Azure CLI compatibility for bootstrap discovery.** Account metadata is
  read through raw ARM API `2025-06-01`, avoiding typed SDK deserialization of
  unrelated newer fields. App Configuration Key Vault reference discovery
  accepts the CLI's `contentType` JSON field; role operations use object IDs
  without Microsoft Graph name resolution.
- **Verified concrete version resolution for Foundry's `@latest` route**
  ([#698](https://github.com/Azure/GPT-RAG/pull/698)). Resolve only this exact
  alias through `live.versions.latest`, require matching agent name and hosted
  kind, then retain numeric version validation and a separate concrete-version
  GET. Unknown aliases and inconsistent metadata continue to fail closed.
- **Documentation and engineering coordination only**
  ([#684](https://github.com/Azure/GPT-RAG/pull/684),
  [#687](https://github.com/Azure/GPT-RAG/pull/687),
  [#689](https://github.com/Azure/GPT-RAG/pull/689)). Clarified the classic
  architecture diagram and historical landing-zone decision, and recorded
  quality-gate and UI package migration plans. Coordinated operator guidance
  is on the `docs` branch via
  [#696](https://github.com/Azure/GPT-RAG/pull/696) and
  [#688](https://github.com/Azure/GPT-RAG/pull/688). These planning artifacts do
  not release component modularization or change the runtime component pins.
- **Pinned GitHub Actions maintenance**
  ([#690](https://github.com/Azure/GPT-RAG/pull/690)). Updated workflow action
  SHAs for `actions/github-script` v9.0.0, `actions/checkout` v7.0.1,
  `azure/login` v3.0.2, `actions/setup-python` v7.0.0, and
  `github/gh-aw-actions/setup` v0.88.0. These are CI action updates, not runtime
  dependency upgrades or deployment-topology changes.

### Validation

The component combination is unchanged from `v3.8.3`; this patch changes the
umbrella deployment hooks and their offline contracts, not component releases.

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.6.2 |
| gpt-rag-orchestrator | v4.1.1 |
| gpt-rag-ingestion | v2.7.3 |
| infra / AI Landing Zone | v2.5.1 |

- Python 3.12 offline suite:
  `python -B -m pytest -q tests config -p no:cacheprovider --tb=short`:
  **438 passed, 297 subtests passed, 4 optional CLI cases skipped**. The focused
  release-pin, access-module, paired-hook, and greeting suite passed
  **107 tests and 204 subtests**. Azure boundaries were mocked.
- All **4** optional CLI parser/serialization cases passed separately using
  the already-installed Azure CLI Python with socket and command-handler
  guards. **6** bounded replay tests passed using the unmodified terminal
  serializer functions from the pinned orchestrator `v4.1.1`, with network
  and subprocess execution blocked. This is terminal wire-format evidence,
  not a complete runtime or retrieval-path validation.
- `python -B .github/scripts/validate-agentic-assets.py` passed:
  **3 agents and 14 skills**, plus scoped instructions.
- Guarded read-only live discovery using the exact bootstrap source now in
  this candidate succeeded with **16 read-only CLI calls**, resolving a
  concrete hosted version and finding all **3** minimum grants already
  present as exact, unconditional assignments. Those grants were applied
  manually beforehand; this did not execute automatic apply, read secret
  values, or invoke a model. `data_plane_readiness` remained `not-tested`.
- Component tags resolve to their unchanged manifest commits. AI Landing Zone
  `ailz_tag`, `ailz_commit`, `.gitmodules` `infra.branch`, and the `infra/`
  gitlink agree on `v2.5.1` / `9cc5859a`.
- No fresh automated Azure deployment/bootstrap/greeting flow, end-user
  document-level authorization, scanning, or cold-start validation was
  performed for this release. Prior manual tests with an unreleased
  homologation runtime are not compatibility evidence for this pinned matrix.

## [v3.8.3] - 2026-09-03

### Fixed

- **Repinned `gpt-rag-ingestion` from `v2.7.2` to
  [`v2.7.3`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.7.3),
  which stops the data-ingestion administrative surface from being mounted in
  deployments that did not ask for it.** The admin SPA and every admin API
  route were mounted unconditionally at import time, and the
  `DEPLOY_ADMINISTRATIVE_PANEL` setting was never read, so the surface was
  reachable regardless of deployment mode. Mounting is now resolved once from
  App Configuration inside the ASGI `lifespan` and gated on the resolved mode.
  Classic deployments are unaffected — the admin surface keeps mounting exactly
  as before — and hosted deployments without a panel now correctly return 404.
  Tracked under [#592](https://github.com/Azure/GPT-RAG/issues/592), the
  umbrella issue for hosted deployment-mode validation.

  The same pin also hardens the new `/api/panel/*` API: startup validation now
  fails closed on missing Entra ID configuration rather than only on missing
  Cosmos configuration, and neither reading nor writing feedback returns 500
  because of a single malformed Cosmos document.

  No GPT-RAG configuration, parameter, or infrastructure change is involved.
  The UI, orchestrator, and AI Landing Zone pins are unchanged from `v3.8.2`.

## Component versions

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.6.2 |
| gpt-rag-orchestrator | v4.1.1 |
| gpt-rag-ingestion | v2.7.3 |
| infra / AI Landing Zone | v2.5.1 |

### Validation

- `unit-tests` green on the pinned ingestion commit: `228 passed, 0 failed`,
  on both the source branch and the release branch.
- UI and orchestrator pins are byte-identical to `v3.8.2` and were not
  revalidated.
- AI Landing Zone pins verified to agree: `manifest.json` `ailz_tag`,
  `.gitmodules` `infra.branch`, and the recorded `infra/` submodule gitlink all
  identify `v2.5.1` / `9cc5859a`.

## [v3.8.2] - 2026-09-03

### Fixed

- **Repinned `gpt-rag-ingestion` from `v2.7.1` to
  [`v2.7.2`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.7.2),
  which restores the ingestion container's ability to start.** `v2.7.1` pinned
  `opentelemetry-instrumentation-httpx==0.65b0`, outside the range required by
  `azure-monitor-opentelemetry`. pip resolved the conflict by silently
  backtracking to an eleven-versions-older exporter that imports a symbol
  removed in `opentelemetry-sdk 1.44`. The image built successfully and the
  container then crashed on boot with
  `ImportError: cannot import name 'LogData'`. Because the failure occurred at
  import time and not at build time, an image build would not have caught it.
  The pin is now a range aligned with the Azure Monitor distro.

- **Repinned `gpt-rag-ui` from `v2.6.1` to
  [`v2.6.2`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.6.2),** which
  fixes citations that the orchestrator returns as absolute URLs for the
  solution's own storage account. The legacy path returned them unsigned and
  the secured path discarded them; both now normalize the URL to a
  container-relative path first, so per-document authorization still applies.

- **Added a `release/*` exception to the pull-request guard.** The umbrella
  workflow blocked every pull request to `main` unconditionally, including
  release branches, contradicting the documented release process. Note that
  because the workflow uses `pull_request_target`, GitHub runs the copy on the
  base branch, so the corrected guard only takes effect from the next release
  onwards.

### Added

- **Continuous integration for `gpt-rag-ingestion` and for the
  `gpt-rag-orchestrator` frontend.** Neither had a workflow exercising the code
  that broke. The ingestion repository already contained 12 test files that no
  workflow ran; the orchestrator SPA was built only inside the Dockerfile. The
  absence of these two jobs is the direct cause of both defects fixed in this
  release and in `v3.8.1`.

## Component versions

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.6.2 |
| gpt-rag-orchestrator | v4.1.1 |
| gpt-rag-ingestion | v2.7.2 |
| infra / AI Landing Zone | v2.5.1 |

### Validation

- `unit-tests` green on each pinned component commit: ingestion `168 passed`,
  UI 410 tests, orchestrator frontend build exit `0` on a Linux runner.
- Resolved ingestion dependency set verified coherent against the Azure Monitor
  distro requirements.
- AI Landing Zone pins verified to agree: `manifest.json` `ailz_tag`,
  `.gitmodules` `infra.branch`, and the recorded `infra/` submodule gitlink all
  identify `v2.5.1` / `9cc5859a`.

## [v3.8.1] - 2026-09-03

> [!CAUTION]
> This release does not deploy: its ingestion pin crashes on boot. Use
> [v3.8.2](https://github.com/Azure/GPT-RAG/releases/tag/v3.8.2).

### Fixed

- **Repinned `gpt-rag-orchestrator` from `v4.1.0` to
  [`v4.1.1`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v4.1.1),
  which restores `azd deploy`.** The orchestrator `Dockerfile` builds its
  `frontend/` SPA in the first stage, so the frontend build failing fails the
  whole image. `v4.1.0` could not be built at all — building `v4.0.2` exits
  `0` while building `v4.1.0` exits `1` — which meant every clean
  deployment of `v3.8.0` failed at the orchestrator image build.

  Three unrelated dependency bumps had been merged into the orchestrator without
  any CI job that builds the frontend, and together they broke it: `react` was
  raised to 19 while `react-dom` stayed on 18 (fatal `ERESOLVE`);
  `@azure/msal-react` was pinned to `^5.7.0`, a version since **unpublished
  from npm** that now returns `E404`; and `tailwindcss` was raised from 3 to
  4 without the required PostCSS and CSS migration. `v4.1.1` fixes all three
  and adds the missing `frontend build` CI job.

  No GPT-RAG configuration, parameter, or infrastructure change is involved. The
  UI, ingestion, and AI Landing Zone pins are unchanged from `v3.8.0`.

- **Allowed `release/*` branches to target `main` in
  `.github/workflows/block-pr-to-main.yml`.** The guard rejected every pull
  request into `main` unconditionally, including the release pull requests the
  documented process requires, so each release merge needed an administrator
  override. It now permits `^release/[0-9]+\.[0-9]+\.[0-9]+$`, matching the
  equivalent guard already present in the component repositories, and reacts to
  `edited` events so retargeting a pull request re-evaluates the rule.
## [v3.8.0] - 2026-09-03

> [!CAUTION]
> This release does not deploy: its orchestrator pin fails to build. Use
> [v3.8.2](https://github.com/Azure/GPT-RAG/releases/tag/v3.8.2).

### Added

- **Opt-in GenAI message-content capture for the hosted agent.** Added
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` to the `env:` block of
  the `orchestrator-agent` service in `hosted-agent/azure.yaml`, wired to a new
  `HOSTED_AGENT_CAPTURE_MESSAGE_CONTENT` azd variable that defaults to `false`.
  When enabled, GenAI spans carry `gen_ai.input.messages`,
  `gen_ai.output.messages`, and `gen_ai.system_instructions`, which is what makes
  the Foundry portal's per-agent **Conversations** view render turns instead of
  reporting *"No conversation turns found"*. The orchestrator reads this variable
  from the process environment before any App Configuration resolution happens,
  so it cannot be supplied as an App Configuration key and previously had no
  supported installation path — a hosted-agent version created by `azd deploy`
  would silently omit it. Operators now opt in per environment with
  `azd env set HOSTED_AGENT_CAPTURE_MESSAGE_CONTENT true` followed by
  `azd deploy`; `scripts/preDeploy.ps1` copies the root `.azure` environment into
  the `hosted-agent` azd project, so the value propagates automatically. The
  default stays `false` because capturing message content ships user prompts and
  model answers to Application Insights, which is a data-privacy decision each
  deployment has to make for itself. Use only this variable, never the legacy
  `AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED`: the Azure AI instrumentor
  treats disagreeing values as a configuration error.

- **Hosted administrative panel platform contract (issue #611, ADR-0004).**
  Published the versioned `contracts/conversations-panel-v1` JSON Schema
  (+ `.sha256` pin) covering the user-facing history/messages/feedback/delete
  surfaces and the operator-facing overview/corpus-curation surfaces, with
  strict `extra=forbid` semantics, a uniform error matrix, opaque
  signed/expiring cursors, and `audit-event-v1`-compatible correlation IDs.
  Added `config.panel.settings` (App Configuration defaults for
  `PANEL_HISTORY_ENABLED`, `PANEL_HISTORY_OWNER_BINDING_VALIDATED`,
  `PANEL_CONVERSATION_ENUMERATION_MODE`, `PANEL_CONVERSATIONS_TOKEN_AUDIENCE`,
  `PANEL_CONVERSATIONS_TENANT_ID`, `PANEL_OWNER_INDEX_DATABASE_CONTAINER`,
  `PANEL_FEEDBACK_DATABASE_CONTAINER`, `PANEL_CURSOR_TTL_SECONDS`,
  `PANEL_OVERVIEW_MIN_CARDINALITY` — all published unconditionally and safely
  inert, matching the already-merged `gpt-rag-ui` panel configuration exactly)
  and `config.deployment.composition.panel_database_containers`/
  `resolve_database_containers`, which provision exactly two
  metadata-only, `/principal_id`-partitioned Cosmos containers (owner index,
  feedback) for hosted/panel — never the classic
  `conversations`/`datasources`/`prompts`/`mcp` list, so switching topologies
  can never mix protected chat content with panel metadata. Added
  `config.panel.setup`, a new `postProvision` hook (wired into both
  `scripts/postProvision.ps1` and `.sh`) that assigns **container-scoped**
  (never account-scope) Cosmos SQL role assignments: Data Contributor for the
  `gpt-rag-ui` BFF identity and Data Reader for `gpt-rag-ingestion` (operator
  overview counts only) on the two panel containers — the hosted
  agent/container identity is never resolved or granted any role. The panel's
  pagination cursor reuses the UI's existing `CHAINLIT_AUTH_SECRET`
  (already Key-Vault-backed); no new secret or Key Vault RBAC was introduced.
  This platform-layer prerequisite remained inert until the coordinated
  integration matrix below lifted the topology block; the independent
  history and operator evidence gates remain disabled by default.
- **Hosted panel operator-surface App Configuration keys (issue #611,
  ADR-0004, reconciling gpt-rag-ingestion PR #274, merge
  `5569dd6af3ecb317e1037108cb21859f1b2185a1`).** Added
  `PANEL_OPERATOR_SURFACES_ENABLED` (forced `false`, mirroring
  `PANEL_HISTORY_OWNER_BINDING_VALIDATED`'s no-evidence-gate-yet pattern),
  `PANEL_OPERATOR_APP_ROLE` (`""`), and `PANEL_OPERATOR_GROUP_ID` (`""`) to
  `config.panel.settings`, matching exactly the App Configuration keys the
  now-merged `gpt-rag-ingestion` operator overview/corpus-curation surfaces
  consume — no invented keys, no key set true. `PANEL_OVERVIEW_MIN_CARDINALITY`
  (`5`), `PANEL_CURSOR_TTL_SECONDS` (`600`), and the panel Cosmos container
  keys were already published with matching defaults and needed no change.
  `DATABASE_ACCOUNT_NAME`/`DATABASE_NAME`/`STORAGE_ACCOUNT_NAME` and the
  reserved per-app `DATA_INGEST_APP_APIKEY` Key Vault reference are already
  published unconditionally by the AI Landing Zone submodule and are not
  duplicated here. Added `config/panel/tests/test_operator_contract.py`, an
  explicit expected-key-set fixture guarding against future drift between
  this repository's published defaults and what `gpt-rag-ingestion` (PR #274)
  and `gpt-rag-ui` (PR #99) actually consume. Updated ADR-0004's adoption
  status: the ingestion operator-surface component work is now done. The
  coordinated matrix below lifts only the explicit hosted-panel topology
  block; the separate live evidence and authorization gates remain fail
  closed.
- **Deterministic deployment topologies.** Classic, hosted/no-panel, and
  hosted/panel are deployable topology values. Hosted-panel requires explicit
  operator selection; `DEPLOY_ADMINISTRATIVE_PANEL` defaults to `false`.
  Panel history and operator routes remain independently fail closed behind
  their disabled-by-default evidence and authorization gates.
- **Hosted-no-panel is now the fresh-deployment default (ADR-0001 revision
  5).** A genuinely new environment (no existing resource group) provisions
  `hosted-no-panel` with `CHAT_BACKEND=hosted_agent` and no orchestrator
  Container App, without requiring any operator opt-in flag. Existing
  environments are unaffected: a resource group that already exists is
  "sticky" — its already-persisted App Configuration topology marker (or, for
  pre-cutover environments with no marker at all, the classic default) is
  honored as-is. Setting `DEPLOYMENT_TOPOLOGY=classic` explicitly always
  selects the Container Apps orchestrator topology, in fresh or existing
  environments; the legacy `DEPLOY_HOSTED_AGENT_ORCHESTRATION=false` flag
  remains a compatible way to request the same fallback. There is no silent
  request-time fallback. Genuinely conflicting persisted App Configuration
  signals fail closed with migration guidance instead of guessing; an explicit
  `DEPLOYMENT_TOPOLOGY` takes precedence over previously materialized
  compatibility flags as the operator-controlled migration or rollback action.
  An explicit classic-to-hosted migration now keeps the orchestrator Container
  App, Cosmos data, and `CHAT_BACKEND=orchestrator` active through both hosted
  preparation phases. `azd deploy` switches App Configuration to
  `CHAT_BACKEND=hosted_agent` and clears the migration marker only after the
  hosted deployment returns a valid endpoint and an `azd ai agent invoke`
  smoke request succeeds; classic resources are eligible for removal only on
  a later explicit provision.
- **Shared, deterministic topology resolver.** `config/deployment/topology.py`
  centralizes the fresh-vs-existing/sticky/conflict decision (resource-group
  existence and contents plus persisted App Configuration settings, when
  reachable) behind a single pure function
  (`config.deployment.composition.resolve_topology`) and a small
  CLI/integration wrapper. An empty resource group pre-created by azd is
  treated as fresh, so an unrelated process-level App Configuration endpoint
  cannot influence first provision; groups with deployed resources retain
  fail-closed persisted-state checks. `scripts/preProvision.ps1` and
  `scripts/preProvision.sh` resolve and materialize the same
  `DEPLOYMENT_TOPOLOGY` (and paired legacy flags/`CHAT_BACKEND`) into the azd
  environment before any later hook or Bicep composition runs.
  `scripts/preDeploy.ps1`/`.sh` and `scripts/postProvision.ps1` read that
  materialized decision back via `config.deployment.topology --describe`
  instead of duplicating the detection logic, so all lifecycle hooks always
  agree.
- **Hosted-agent azd service isolation.** An isolated child azd project deploys
  the orchestrator image through `azure.ai.agent` only in hosted modes. Fresh
  hosted environments use an explicit two-phase contract: the first
  `azd provision` sets `prepareHostedAgent=true` and
  `deployHostedAgent=false`, exposing Foundry, registry, network, and private
  build prerequisites without accepting an empty or placeholder image digest.
  `scripts/prepareHostedDeployment.ps1` and `.sh` then clone the exact
  manifest-pinned orchestrator commit, build it through ACR Tasks, create the
  hosted-entrypoint derivative through the same build path, resolve the pushed
  manifest to a canonical lowercase immutable digest, and materialize that
  digest into the azd environment. A second explicit `azd provision` enables
  the digest-backed deploy handoff, after which `azd deploy` invokes
  `azure.ai.agent`. Network-isolated builds validate and use the dedicated
  VNet-injected ACR Tasks agent pool. An explicit digest remains supported as a
  no-build override; mutable or malformed values always fail closed. Hosted
  mode also requires a delegated-user resource scope via explicit
  `HOSTED_AGENT_RESOURCE_SCOPE` containing a non-empty resource identifier
  followed by `/.default`.
- **Mode-aware runtime contract.** App Configuration label `gpt-rag` now owns
  `CHAT_BACKEND`, deployment topology, classic and hosted endpoints, resource
  scope, the resolved hosted image digest, and finite SSE timeout settings.
  PowerShell and shell lifecycle hooks consume the same composition and
  publication modules.

### Changed

- **Hosted administrative panel integration matrix (issue #611).** Explicit
  hosted-panel topology selection is now composed with UI `v2.6.0`
  (`81d6515d8fc365402e958e861b671af037a4cc75`), orchestrator `v4.0.1`
  (`7e22840ba0e96a5ce237cf2657795768f88e3955`), ingestion `v2.7.0`
  (`84b927769ef0839110f2d68e3ca471e2260567cf`), and AI Landing Zone
  `v2.5.0` (`cacf418216ce7381d06263e0dd704a86b8a6f225`). The hosted
  container remains stateless with zero Conversations RBAC; hosted-panel
  provisions only the metadata-only owner-index and feedback containers.
  `PANEL_HISTORY_ENABLED`, `PANEL_HISTORY_OWNER_BINDING_VALIDATED`, and
  `PANEL_OPERATOR_SURFACES_ENABLED` remain deployment-published `false`, so
  all user-history and operator surfaces stay fail closed until their
  independent evidence and authorization gates are explicitly completed.
  The released ingestion browser/operator path validates delegated bearer
  tokens, rejects app-only identities, and requires exact configured app-role
  or group membership.
- **Hosted continuity ownership is delegated and fail closed.** The trusted UI
  BFF now derives `x-ms-user-identity` from the authenticated server-side
  principal, independently of OBO retrieval tokens. Continuity activates only
  after the live routed Responses protocol is exactly 2.0.0 and the UI BFF has
  direct, exact agent-scoped Foundry Agent Consumer plus GPT-RAG user-identity
  impersonation assignments. The hosted container receives neither role nor an
  ownership key. The HMAC capability contract remains an explicit disabled
  fallback and delegated mode provisions no capability secret, vault role, or
  App Configuration reference.
- **Released AI Landing Zone pin.** The temporary AI Landing Zone `develop`
  source pin is replaced by released tag `v2.5.0` at exact commit
  `cacf418216ce7381d06263e0dd704a86b8a6f225`.
- **AI Landing Zone pin updated to `v2.5.1`
  (`9cc5859af5c8ab3b31709c9e16e0db11a170a404`).** Patch release: Azure
  Firewall's `AllowContainerAppsPlatform` Application Rule now also allows the
  Microsoft Foundry Agent Service's `agent365.svc.cloud.microsoft`
  observability endpoint for hosted agents under network isolation. Live
  Azure validation of a network-isolated deployment had shown the capability
  host and hosted-agent runtime start successfully, but every hosted-agent
  request then failed because the runtime's own post-startup
  observability/telemetry call had no firewall allow rule. Strictly additive
  allow-list change; deployments without `NETWORK_ISOLATION=true` and the
  Azure Firewall are unaffected. `.gitmodules` and the `infra` submodule
  gitlink are updated to match. See
  [AILZ `v2.5.1`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.5.1).
- **Orchestrator pin updated to `v4.0.2`
  (`c653b3ec0a553f55244e197f3be993ad33ffe02f`).** Closes the store-false wire
  contract gap recorded in the hosted-agent integration matrix: the hosted
  outer `POST /responses` now unconditionally forces `store: false` before
  the pinned `azure-ai-agentserver-responses==2.0.0b1` host's auto-activated
  `FoundryStorageProvider` can run, for both streaming and non-streaming
  requests, regardless of what a caller sends or omits. Previously an omitted
  or `true` `store` deterministically failed with a platform `storage_error`
  under network isolation; only an explicit `store: false` succeeded.
  `background: true` now returns an explicit HTTP 422 instead of the SDK's
  generic 400, since it requires `store: true` and is no longer a reachable
  combination once `store` is force-overridden. Released upstream as
  [gpt-rag-orchestrator PR #313](https://github.com/Azure/gpt-rag-orchestrator/pull/313),
  shipped in
  [`v4.0.2`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v4.0.2)
  (722 tests passing upstream). Classic (non-hosted, Cosmos-backed)
  `/responses` and `/invocations` behavior are unaffected; the change is
  scoped to the hosted entrypoint's `create_response` guard only. **This is a
  code-level fix pinned into the umbrella manifest; it does not by itself
  constitute the network-isolated live re-run of the exact `store`
  unset/`true`/`false` matrix that the hosted-agent integration matrix
  documentation still requires before the store-false contract can be
  described as validated.**

### Fixed

- **AI Foundry project endpoint discovery.** Windows post-provisioning now
  resolves project child resources through the generic ARM resource API,
  validates an explicit `AI_FOUNDRY_PROJECT_NAME` when supplied, and fails
  closed unless exactly one project is selected. It no longer silently
  publishes an invalid `aifoundry-default-project` endpoint when the installed
  Azure CLI lacks the specialized project-list command.

- **Windows jumpbox deployment imports the repository package reliably.**
  `preDeploy.ps1` now establishes the repository root on `PYTHONPATH` and
  invokes deployment modules through `runpy`, avoiding Windows Python
  installations that omit the current directory from `sys.path`. The shell
  hook now exports the equivalent repository-root import path.
- **Hosted-image builds resolve the Azure CLI launcher on Windows.**
  The ACR Tasks helper resolves both `az` and the Windows `az.cmd` shim before
  calling `subprocess.run`, uses an absolute Dockerfile path for temporary
  pinned-source contexts, and fails clearly when Azure CLI is unavailable.
  Private builds queue without streaming Unicode logs through the Windows
  console and resolve their immutable output digest from the management-plane
  ACR run record, so digest materialization does not require public registry
  data-plane access.
- **Foundry IQ ingestion honors the Search managed-identity mode.**
  Blob knowledge sources now bind the Search service's configured
  user-assigned identity instead of implicitly selecting a nonexistent system
  identity in UAI-based deployments.
- **Regional prerequisite checks resolve Azure CLI on Windows.**
  `util.prereqs` now uses the same explicit Azure CLI executable resolution as
  deployment configuration, so the `az.cmd` shim no longer fails with
  `FileNotFoundError` under `subprocess.run`. Its console messages are
  ASCII-safe for the default Windows code page, and Azure SDK imports are
  deferred until live checks run, allowing `python -m util.prereqs --help` to
  work before optional dependencies are installed.
- **Governance pin regression follows the rollback contract.** The governance
  test now verifies the preserved `v3.7.0` component combination in
  `config/deployment/rollback.json` instead of incorrectly requiring the live
  unreleased manifest to remain frozen on the prior release.
- **Root-caused and fixed the hosted-agent session-readiness HTTP 424
  blocker (issue #576).** The previous integration attempt's network-isolated
  live validation reached agent-version `active` state but every session
  invoke returned HTTP 424 `session_not_ready`. Root-caused to a circular
  import in `gpt-rag-orchestrator`: `src/api/hosted_entrypoint.py` imports
  `dependencies` first (it is intentionally Cosmos-free and never "warms up"
  `connectors` first, unlike the classic `main.py` entrypoint); `dependencies.py`
  eagerly imported `connectors.appconfig` at module level, and
  `connectors/__init__.py` eagerly imports several submodules
  (`cosmosdb`, `search`, `aifoundry`) that each import `dependencies` back at
  *their* module level — an import-time cycle that crashed the container's
  Python process before uvicorn could ever bind a port or serve
  `GET /readiness`, exactly matching Microsoft Foundry's documented
  `424 session_not_ready` failure mode ("container started but `/readiness`
  didn't return HTTP 200 within the timeout"). Reproduced deterministically
  with a fresh-interpreter import test mirroring the container's startup
  command (no live Azure deployment required to diagnose or confirm the fix).
  Fixed upstream in
  [gpt-rag-orchestrator PR #311](https://github.com/Azure/gpt-rag-orchestrator/pull/311)
  by deferring `AppConfigClient` construction into `get_config()`, released as
  [`v4.0.1`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v4.0.1)
  (patch, no behavior change beyond the import fix; 720 tests passing). The
  umbrella pin above is bumped to `v4.0.1` accordingly. **This fixes the
  specific crash that produced the HTTP 424 symptom; it does not by itself
  constitute the network-isolated live validation this integration still
  requires** — see the "Migration and rollback" note below for the current
  validation status.

- **Hosted agent no longer crashes every live request with HTTP 500 under
  Foundry's hosted-agent sandbox.** Live network-isolated validation (issue
  #592) reproduced a deterministic HTTP 500 (`{"detail":"internal server
  error"}`) on every `/responses` and `/invocations` call against a
  successfully created, `active` hosted agent. Root-caused via Application
  Insights exception traces to `azure-monitor-opentelemetry>=1.8`, which
  `environ.setdefault`s `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` to
  `azure_app_service,azure_vm` unless that variable is already present. The
  Foundry hosted-agent sandbox is neither an Azure VM nor an App Service, so
  the `azure_vm` detector's IMDS probe
  (`http://169.254.169.254/metadata/instance/compute`) always fails with
  connection-refused; that failure was observed to escape
  `azure-ai-agentserver-core`'s own `try`/`except` around
  `configure_observability()` and surface later as an unhandled exception
  during live request handling. `hosted-agent/azure.yaml` now pins
  `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS: ""` in the hosted agent's `env:`
  block so `environ.setdefault` never applies it; this is a deployment
  configuration fix in this repository, not a `gpt-rag-orchestrator` code
  change. No behavior change for classic-mode telemetry. **Follow-up:** live
  re-validation with that fix alone still reproduced the same IMDS failure
  reaching request handling. Traced it to a second, independent source:
  `azure-monitor-opentelemetry-exporter`'s own "statsbeat" SDK
  self-monitoring subsystem (`_get_azure_compute_metadata` in
  `statsbeat/_statsbeat_metrics.py`) probes the same IMDS endpoint to
  attribute usage metrics to a resource-provider type, and is not gated by
  `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS`. `hosted-agent/azure.yaml` now also
  pins `APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL: "true"`. Statsbeat is
  Microsoft's own SDK-usage telemetry, not GPT-RAG application telemetry;
  disabling it does not affect Application Insights traces, logs, or metrics
  for GPT-RAG requests.

### Migration and rollback

No existing environment is migrated by this change: an already-provisioned
resource group is sticky and keeps whatever topology App Configuration
already records for it (or stays classic if it predates this cutover and has
no recorded marker), so re-running `azd provision`/`azd deploy` against an
existing environment is a no-op with respect to topology. Only genuinely new
environments (no existing resource group and no explicit signal) now default
to `hosted-no-panel` instead of classic. Operators who want a new environment
to use the classic Container Apps orchestrator must set
`DEPLOYMENT_TOPOLOGY=classic` (or the compatible legacy
`DEPLOY_HOSTED_AGENT_ORCHESTRATION=false`) before provisioning it. Hosted
deployments use `azd provision`, the platform-specific
`scripts/prepareHostedDeployment` command, a second `azd provision`, and then
`azd deploy`. The preparation command automatically creates an immutable image
from the pinned orchestrator source unless the operator supplies an explicit
canonical digest override; an explicit hosted-agent data-plane scope remains
required. The deterministic rollback contract
in `config/deployment/rollback.json` restores the complete `v3.7.0` classic
pin set, clears hosted endpoint inputs, resets both mode flags to `false`,
and restores `CHAT_BACKEND=orchestrator`.

The UI, orchestrator, and latest released AI Landing Zone tag APIs report
`immutable=false`, but active semantic-version tag rulesets `20396217`,
`20396972`, and `20396978` prevent deletion and non-fast-forward updates for
`refs/tags/v*`. AI Landing Zone `v2.4.1` is also protected by exact-tag ruleset
`20339953`; the temporary PR #130 commit pin is not a release pin. This
unreleased integration does not publish an umbrella release.

### Validation

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.6.1 |
| gpt-rag-orchestrator | v4.1.0 |
| gpt-rag-ingestion | v2.7.1 |
| infra / AI Landing Zone | v2.5.1 |

- Provisioned and deployed end to end in a validation environment in `westus3`
  with `NETWORK_ISOLATION=true` and `BUILD_MODE=acr-task`, using
  `azd provision` followed by `azd deploy`.
- The orchestrator was deployed as a Microsoft Foundry hosted agent, with
  retrieval served by a Foundry IQ knowledge base over Blob Storage.
- Retrieval verified end to end through the Foundry Playground, `azd ai agent
  invoke`, and the Chainlit front end: the answer returns with an openable
  citation on every surface.
- Spurious `Failed to detach context` error records confirmed absent on fresh
  role instances, measured against a baseline where every serving instance
  emitted them.
- Front-end sign-in through Microsoft Entra ID exercised against a dedicated
  app registration.
## [v3.7.0] - 2026-07-21

### User and operator impact

GPT-RAG `v3.7.0` delivers the governance baseline tracked in [issue #571](https://github.com/Azure/GPT-RAG/issues/571) through [implementation PR #573](https://github.com/Azure/GPT-RAG/pull/573) and [documentation PR #574](https://github.com/Azure/GPT-RAG/pull/574), with [orchestrator `v3.8.0`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.8.0) and [ingestion `v2.5.0`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.5.0) deployed as one pinned combination. Metadata audit events and ingestion provenance remain disabled by default, sensitive-content capture remains independently disabled, and existing deployments do not change behavior until an operator opts in.

The shared `audit-event-v1` contract is pinned to logical hash `825db8ef40a81e2c19e5d80d37c565b6b47fc9a6540e9881d35cc12b8fde5aab` and Application Insights wire hash `066c8f5408610ab839d5121d06ca5bc59e8797e551d5c47c875c5ba52f7e0588`. These audit events provide technical evidence for adopter governance and incident response; they do not establish legal or regulatory compliance.

### Added

- **Safe governance defaults in App Configuration.** Fresh and upgraded deployments seed missing keys as `AUDIT_EVENTS_ENABLED=false`, `AUDIT_SENSITIVE_CONTENT_ENABLED=false`, `AUDIT_SENSITIVE_CONTENT_FIELDS=''`, `AUDIT_ACTOR_PSEUDONYM_ENABLED=false`, `AUDIT_SOURCE_EVENT_LIMIT=25`, `AUDIT_HMAC_KEY_ID=v1`, `AUDIT_ADDITIONAL_REDACTED_KEYS=''`, `INGESTION_PROVENANCE_ENABLED=false`, `INGESTION_REQUIRE_GOVERNANCE_METADATA=false`, `INGESTION_DEFAULT_CLASSIFICATION=unclassified`, and `INGESTION_DEFAULT_RIGHT_TO_USE=not_asserted`. Reprovisioning preserves operator-managed values unless the corresponding AZD environment value explicitly overrides them.
- **Key Vault-backed audit pseudonymization key.** When `AUDIT_HMAC_KEY` is absent, post-provisioning creates `AUDIT-HMAC-KEY` from 256 cryptographically random bits and registers only its Key Vault reference in App Configuration. Later runs reuse it; an existing operator-managed Key Vault reference is preserved, and a valid legacy plaintext key is migrated without changing its value. The value is not placed in plaintext deployment configuration, output, or logs. Rotation is explicit: create a new Key Vault secret version and advance `AUDIT_HMAC_KEY_ID`.
- **Additive provenance fields in the RAG Search index.** The index adds `provenance_id`, `source_uri_id`, `source_version_id`, `content_checksum_sha256`, `ingested_at`, `ingest_run_id`, `data_classification`, `right_to_use`, `retention_class`, and `delete_after`. Identifier/checksum fields are retrievable and filterable; guaranteed UTC `ingested_at` values use sortable `Edm.DateTimeOffset`; `delete_after` remains a sortable string because ingestion v2.5.0 intentionally passes through operator policy values without imposing a date format; governance classification fields are facetable.
- **Shared contract source.** `contracts/` now carries the byte-pinned logical and Application Insights wire schemas consumed by orchestrator v3.8.0 and ingestion v2.5.0.

### Changed

- **Release manifest.** `manifest.json` identifies the umbrella `v3.7.0` combination and pins orchestrator `v3.8.0` plus ingestion `v2.5.0`; UI `v2.3.13` and infra `v2.3.0` remain unchanged.
- **Non-destructive existing-index migration.** Search post-provisioning no longer deletes an index before updating it. Missing fields are merged into the current definition and submitted with an in-place `PUT`; operator-owned fields and existing documents are preserved. An incompatible same-name field fails before any update, and there is no delete/recreate fallback.

### Security and operational guidance

Keep `AUDIT_SENSITIVE_CONTENT_ENABLED=false` unless an explicit, reviewed capture policy is in place. Tokens, credentials, authorization material, cookies, connection strings, and configured redacted keys remain prohibited even when sensitive capture is enabled. The audit HMAC secret is intended for orchestrator pseudonymization only; ingestion does not consume it.

`delete_after` records retention policy intent only. GPT-RAG does not schedule or perform automatic deletion from this field. Operators remain responsible for retention enforcement, confirmed deletion, telemetry access, and export controls.

Deployments that explicitly disable Key Vault still receive the disabled governance defaults, but no audit HMAC key/reference is created. Audit events must remain disabled in that deployment mode.

### Migration and rollback

Upgrade the umbrella configuration and both pinned runtime components together, run post-provisioning to register the Key Vault reference and additive Search fields, verify metadata-only events in a non-production environment, and only then enable `AUDIT_EVENTS_ENABLED` or `INGESTION_PROVENANCE_ENABLED`.

Rollback by setting both feature gates to `false` and redeploying prior component tags if needed. The additive Search fields can remain in place because older components ignore unknown fields. Post-provisioning never recreates an existing index for this migration.

### Validation

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.8.0 |
| gpt-rag-ingestion | v2.5.0 |
| infra / AI Landing Zone | v2.3.0 |

- GPT-RAG governance and Search suites: 131 tests passed.
- Bicep compilation, template rendering, static RBAC checks, manifest and component-release checks, and create-only Azure previews passed.
- Runtime provisioning could not complete. Azure platform capacity blocked Azure AI Search in `eastus2` and the Container Apps managed environment in `swedencentral`; the Sweden Central attempt also exposed an ARM nested deployment name over the 64-character limit. No runtime endpoints, application health checks, live governance defaults, Search migration result, or Application Insights/KQL evidence were obtained.

## [v3.6.0] - 2026-07-19

### User and operator impact

Adds opt-in provisioning for generic, approved, preconfigured MCP Server knowledge sources, resolving [#567](https://github.com/Azure/GPT-RAG/issues/567) through [GPT-RAG PR #568](https://github.com/Azure/GPT-RAG/pull/568), [docs PR #569](https://github.com/Azure/GPT-RAG/pull/569), and [orchestrator PR #275](https://github.com/Azure/gpt-rag-orchestrator/pull/275). The feature is **Preview and disabled by default**, so existing deployments do not change unless an operator explicitly enables it.

Provisioning from GPT-RAG `v3.6.0` and [orchestrator `v3.7.0`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.7.0) must be deployed together before enabling MCP. The configuration governs trusted HTTPS endpoints, exact tool allowlists, output parsing, per-source failure behavior, reasoning effort, runtime/output limits, and request-time authentication metadata.

### Added

- **Generic MCP Server knowledge source template.** Foundry IQ can call allowed tools on one or more operator-approved MCP servers and combine those results with existing knowledge sources. The Search integration uses API `2026-05-01-preview`; Azure Monitor MCP over workspace-based Application Insights is a worked example, not a special product code path.
- **Fail-closed source validation and canonical configuration.** Provisioning rejects malformed or empty source definitions, duplicate names, untrusted or unsafe endpoints, unsupported tool/output controls, forbidden headers, literal credentials, and invalid runtime limits before any App Configuration or Search write. Disabled configuration remains canonical and byte-identical to the prior rendered behavior.
- **Secure request-time authentication metadata.** Managed identity, OBO, Key Vault secret-name references, and no-auth mode are supported without rendering credential values into Search resources. Operators must apply least privilege and keep secrets out of source JSON.
- **Operator controls and rollback.** `FOUNDRY_IQ_MCP_ENABLED=false` remains the default and rollback gate. Trusted-host and tool allowlists, bounded reasoning/runtime/output, explicit parsing, and per-source failure behavior constrain the preview integration.

### Changed

- **`manifest.json` now identifies umbrella release `v3.6.0` and pins orchestrator `v3.7.0`.** UI `v2.3.13`, ingestion `v2.4.14`, and infra `v2.3.0` are unchanged.

### Security and operational guidance

MCP tool safety does not guarantee that model-generated arguments are semantically correct. Use only trusted endpoints, exact read-only tool allowlists, bounded queries, least-privilege identities, and auditable server-side enforcement. The Azure Monitor example must retain workspace scope, bounded time ranges and row counts, and generated-KQL review. Production enablement requires a canary against the operator's approved endpoint and credentials.

To roll back, set `FOUNDRY_IQ_MCP_ENABLED=false` and rerun post-provisioning or provisioning. This removes MCP references from the knowledge base and restores disabled planning behavior; an unused top-level Search knowledge-source resource may be deleted separately after confirming that no knowledge base references it.

### Validation

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.7.0 |
| gpt-rag-ingestion | v2.4.14 |
| infra / AI Landing Zone | v2.3.0 |

- GPT-RAG configuration and template suites: **109 tests passed, 66 subtests passed**.
- Orchestrator `v3.7.0`: **457 tests passed, 65 subtests passed**.
- Python compilation, PowerShell AST/preflight, JSON/manifest/remote-tag checks, canonical fixture compatibility, disabled-byte identity, Bicep build/size gate, strict documentation build, and Pages publication passed.
- No live Azure MCP end-to-end test was run because no approved MCP endpoint or credentials were available. The release is acceptable because MCP remains Preview, disabled by default, fail-closed, fully regression-tested, and reversible; production enablement still requires an operator-owned canary.

## [v3.5.1] - 2026-07-15

### User and operator impact

Ships [orchestrator `v3.5.1`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.5.1), which adds Microsoft Entra/MSAL sign-in for the optional admin dashboard at `/dashboard/`. Operators can now require an Entra sign-in and the exact `Admin` app role before dashboard APIs return administrative data. Existing deployments are unchanged unless dashboard authentication is enabled with App Configuration.

### Changed

- **`manifest.json`: orchestrator pin bumped from `v3.5.0` to [`v3.5.1`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.5.1).** The new orchestrator release adds MSAL Authorization Code + PKCE sign-in for the dashboard SPA, API-scoped token acquisition, fail-closed tenant/client configuration, verified token audience validation, and exact `Admin` app-role enforcement.

### Fixed

- **Admin dashboard authentication is now usable end to end.** The dashboard SPA no longer depends on manually injected bearer tokens. It can bootstrap MSAL from `/api/dashboard/auth-config`, sign in with the configured single App Registration, send bearer tokens to protected dashboard APIs, and show clear 401 reauthentication or 403 missing-role states.

### Validation

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.5.1 |
| gpt-rag-ingestion | v2.4.14 |
| infra / AI Landing Zone | v2.3.0 |

- `Azure/gpt-rag-orchestrator#260` checks passed before merge.
- Orchestrator release `v3.5.1` was published from the release commit.
- Live tenant validation still requires a recreated or selected GPT-RAG validation environment, because the previous dashboard validation resource group is no longer present in the target subscription.

## [v3.5.0] - 2026-07-13

### User and operator impact

Ships platform-side support for four net-new Foundry IQ knowledge sources previewed in [orchestrator `v3.5.0`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.5.0): **SharePoint (remote)** via the Copilot Retrieval API with per-user OBO ACL, **OneLake (indexed)** for native Foundry IQ indexing of Fabric OneLake data, **SharePoint (indexed)** via Microsoft Graph app-only auth against a pre-built AI Search index, and **Web grounding (Bing)** for public internet retrieval scoped by allow/block domain lists. All four sources are OFF by default and gated by their own `*_ENABLED` App Configuration flag plus a knowledge-source name. With the flags off (the default), the rendered search resources, deployed containers, and runtime behavior are identical to `v3.4.3`, so existing environments upgrade with no config change.

Each knowledge source has its own opt-in configuration surface:

- **SharePoint remote:** `SHAREPOINT_REMOTE_ENABLED`, `SHAREPOINT_REMOTE_KNOWLEDGE_SOURCE_NAME`, `SHAREPOINT_REMOTE_FILTER_EXPRESSION_ADD_ON`. ACL enforced natively by SharePoint via forwarded OBO token; managed-identity fallback is never used.
- **OneLake indexed:** `ONELAKE_KS_ENABLED`, `ONELAKE_KNOWLEDGE_SOURCE_NAME`, `ONELAKE_WORKSPACE_ID`, `ONELAKE_LAKEHOUSE_ID`. Fabric workspace RBAC is a manual prerequisite; the orchestrator does not grant it.
- **SharePoint indexed:** `SHAREPOINT_INDEXED_ENABLED`, `SHAREPOINT_INDEXED_KNOWLEDGE_SOURCE_NAME`, `SHAREPOINT_INDEXED_INDEX_NAME`, `SHAREPOINT_INDEXED_SITE_URL`, `SHAREPOINT_INDEXED_TENANT_ID`. App-only Graph auth (Sites.Selected preferred).
- **Web grounding:** `WEB_GROUNDING_ENABLED`, `WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME`, `WEB_GROUNDING_ALLOWED_DOMAINS`, `WEB_GROUNDING_BLOCKED_DOMAINS`. Public data, no ACL, no OBO. Billed per Bing call.

Standard-mode `azd provision` + `postProvision.ps1` now seeds every one of these keys into App Configuration with safe empty/`false` defaults, so provisioning is a no-op for operators who do not opt in.

**Data-egress caveat:** SharePoint remote and OneLake indexed forward user OBO tokens (or app-only credentials in the SharePoint indexed case) to Microsoft services and return grounded content back to the orchestrator. Web grounding queries the public internet via Bing and returns snippets and links. Operators enabling any of these should confirm the data flow is compliant with their tenant's data-boundary and RBAC policies before turning the flag on. Grounded content still ends up in orchestrator responses and, transitively, in downstream telemetry and chat history.

### Added

- **SharePoint remote App Configuration passthrough (`SHAREPOINT_REMOTE_*` keys).** `postProvision.ps1` now seeds three new keys with safe defaults so the orchestrator can wire up SharePoint remote retrieval via the Copilot Retrieval API when the flag is on.
- **OneLake indexed App Configuration passthrough (`ONELAKE_KS_ENABLED`, `ONELAKE_KNOWLEDGE_SOURCE_NAME`, `ONELAKE_WORKSPACE_ID`, `ONELAKE_LAKEHOUSE_ID`).** `postProvision.ps1` seeds these keys with safe defaults for the OneLake indexed knowledge source.
- **SharePoint indexed knowledge source template (preview).** `config/search/search.j2` renders the `indexedSharePoint` knowledge source when the flag is on, `config/search/search.settings.j2` exposes the settings block, and `postProvision.ps1` seeds the App Configuration keys.
- **Web grounding knowledge source template + App Configuration passthrough.** `config/search/search.j2` renders the `web` knowledge source with allow/block domain lists when enabled, `config/search/search.settings.j2` exposes the settings block, and `postProvision.ps1` seeds the App Configuration keys.

### Changed

- **`manifest.json`: orchestrator pin bumped from `v3.4.1` to [`v3.5.0`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.5.0).** The four new knowledge source retrieve wirings (`remoteSharePoint`, `indexedOneLake`, `indexedSharePoint`, `web`) ship in orchestrator `v3.5.0`; earlier tags do not consume the new App Configuration keys.

## [v3.4.3] - 2026-07-13

### User and operator impact

Fixes the Fabric Data Agent knowledge source support that `v3.4.2` advertised. In `v3.4.2` the platform-side wiring (App Configuration keys, `search.j2` knowledge source block, `search.settings.j2` bindings, `postProvision.ps1` passthrough) was correct and the knowledge source registers against Foundry IQ `2026-05-01-preview`. However `manifest.json` pinned the orchestrator to `v3.4.0`, and the Fabric Data Agent retrieve wiring (`kind=fabricDataAgent`, per-user OBO forwarding, `dataAgentAnswer` normalization) actually landed on the orchestrator's `develop` branch a few minutes after that tag was cut. As a result, `v3.4.2` deployments that flipped `FABRIC_DATA_AGENT_ENABLED=true` had the knowledge source registered in Foundry IQ but the deployed orchestrator container did not append it to `knowledgeSourceParams` at retrieve time, so no Fabric Data Agent grounding actually occurred.

`v3.4.3` bumps the orchestrator pin to [`v3.4.1`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.4.1), which is the tag that actually contains the Fabric Data Agent retrieve code. No template, script, or App Configuration changes are needed; existing `v3.4.2` environments only need to redeploy the orchestrator container to pick up the fix.

### Changed

- **`manifest.json`: orchestrator pin bumped from `v3.4.0` to [`v3.4.1`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.4.1).** The Fabric Data Agent retrieve wiring (`kind=fabricDataAgent`, per-user OBO forwarding, `dataAgentAnswer` normalization) ships in orchestrator `v3.4.1`; `v3.4.0` did not include it.

### Fixed

- **Fabric Data Agent knowledge source now actually works end to end when `FABRIC_DATA_AGENT_ENABLED=true`.** The `v3.4.2` platform release registered the knowledge source in Foundry IQ but pinned an orchestrator (`v3.4.0`) that had no code to consume it at retrieve time. `v3.4.3` pins orchestrator `v3.4.1` which carries the retrieve wiring.

## [v3.4.2] - 2026-07-13

### User and operator impact

Foundry IQ deployments can now optionally include a **Microsoft Fabric Data Agent** as an additional knowledge source on the shared knowledge base, so retrieval can ground answers on a Fabric Data Agent (a virtual analyst that queries Fabric data) alongside existing RAG documents, Work IQ, and Fabric ontology. The feature is opt-in and defaults to off. Set `FABRIC_DATA_AGENT_ENABLED=true` and pick `FABRIC_DATA_AGENT_KNOWLEDGE_SOURCE_NAME`, `FABRIC_DATA_AGENT_WORKSPACE_ID`, and `FABRIC_DATA_AGENT_DATA_AGENT_ID` before `azd provision` to enable it. With the flag off (the default), the rendered search resources and deployed behavior are identical to `v3.4.1` defaults, so existing environments upgrade with no change.

Enabling Fabric Data Agent requires: a Microsoft Fabric workspace with a Data Agent item, Fabric-licensed end users, and the same Entra tenant as the Foundry / Search resource. ACL is enforced natively by Fabric via the forwarded per-user OBO token (same `x-ms-query-source-authorization` header used by Work IQ and Fabric ontology). Managed-identity fallback is never used for the remote `fabricDataAgent` kind: when the OBO token is missing, the Fabric Data Agent source is skipped with a clear warning and local sources still serve the request.

**Data-egress caveat:** Fabric Data Agent forwards the caller's OBO token to Microsoft Fabric and returns grounded answers plus tabular evidence from Fabric data back to the orchestrator. Operators enabling Fabric Data Agent should confirm this data-flow is compliant with their tenant's data-boundary and Fabric-workspace access policies before turning the flag on. Grounded content still ends up in orchestrator responses and, transitively, in downstream telemetry and chat history.

The paired orchestrator release [`v3.4.0`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.4.0) adds the runtime settings `FABRIC_DATA_AGENT_ENABLED` and `FABRIC_DATA_AGENT_KNOWLEDGE_SOURCE_NAME`, plus the Fabric Data Agent retrieve wiring (`kind=fabricDataAgent` with preview API `2026-05-01-preview`). `manifest.json` is pinned to that release.

### Added

- **Fabric Data Agent (Microsoft Fabric) knowledge source support (opt-in, default off).**
  Foundry IQ deployments can now optionally include a Microsoft Fabric Data
  Agent as an additional knowledge source on the shared knowledge base, so
  retrieval can ground answers on a Fabric Data Agent (a virtual analyst that
  runs queries over Fabric data) alongside existing RAG documents, Work IQ,
  and Fabric ontology. Feature is opt-in via the App Configuration keys
  `FABRIC_DATA_AGENT_ENABLED`, `FABRIC_DATA_AGENT_KNOWLEDGE_SOURCE_NAME`,
  `FABRIC_DATA_AGENT_WORKSPACE_ID`, and `FABRIC_DATA_AGENT_DATA_AGENT_ID`.
  With the flag off (the default), the rendered search resources and deployed
  behavior are identical to the `v3.4.1` defaults, so existing environments
  upgrade with no change. Requires a Microsoft Fabric workspace with a Data
  Agent item, Fabric-licensed end users, and the same Entra tenant as the
  Foundry / Search resource.

### Changed

- **Orchestrator pin bumped to [`v3.4.0`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.4.0):** carries the Fabric Data Agent retrieve support (`kind=fabricDataAgent`), reusing the OBO header path introduced for Work IQ and Fabric ontology.
- **`scripts/postProvision.ps1` now seeds `FABRIC_DATA_AGENT_*` App Configuration keys** with defaults (`enabled=false`, everything else `""`), mirroring the `WORK_IQ_*` / `FABRIC_IQ_*` block introduced in `v3.4.1`.
- **`config/search/search.settings.j2` and `config/search/search.j2`** now emit the four `FABRIC_DATA_AGENT_*` settings and register a `fabricDataAgent` knowledge source (with `fabricDataAgentParameters`) plus its knowledge-base reference when enabled.

### Fixed

## [v3.4.1] - 2026-07-10

### Fixed

- **`scripts/postProvision.ps1` now seeds `WORK_IQ_*` and `FABRIC_IQ_*` App Configuration keys.**
  The post-provision hook previously stamped every `FOUNDRY_IQ_*` key
  explicitly but relied on `config/search/setup.py` rendering
  `search.settings.j2` to populate the Work IQ and Fabric IQ keys as a
  side-effect. `Set-GptRagAppConfiguration` now seeds `WORK_IQ_ENABLED`,
  `WORK_IQ_KNOWLEDGE_SOURCE_NAME`, `FABRIC_IQ_ENABLED`,
  `FABRIC_IQ_KNOWLEDGE_SOURCE_NAME`, `FABRIC_IQ_WORKSPACE_ID`, and
  `FABRIC_IQ_ONTOLOGY_ID` with the same defaults as the Jinja template
  (`enabled=false`, everything else `""`). Operators can now flip Work IQ
  or Fabric IQ on from the App Configuration blade without having to
  discover key names first. See
  [`Azure/gpt-rag#551`](https://github.com/Azure/gpt-rag/issues/551).

### Component versions

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.3.0 |
| gpt-rag-ingestion | v2.4.14 |
| infra / AI Landing Zone | v2.3.0 |

## [v3.4.0] - 2026-07-10

### User and operator impact

Foundry IQ deployments can now optionally include **Microsoft Fabric ontology** as an additional knowledge source on the shared knowledge base, so retrieval can ground answers in a Fabric semantic model, lakehouse, warehouse, or KQL database exposed through the ontology, alongside existing RAG documents and Work IQ. The feature is opt-in and defaults to off. Set `FABRIC_IQ_ENABLED=true` and pick `FABRIC_IQ_KNOWLEDGE_SOURCE_NAME`, `FABRIC_IQ_WORKSPACE_ID`, and `FABRIC_IQ_ONTOLOGY_ID` before `azd provision` to enable it. With the flag off (the default), the rendered search resources and deployed behavior are identical to `v3.3.0` defaults, so existing environments upgrade with no change.

Enabling Fabric IQ requires: a Microsoft Fabric workspace with an ontology item, tenant-level Fabric ontology enablement, Fabric-licensed end users, and the same Entra tenant as the Foundry / Search resource. ACL is enforced natively by Fabric via the forwarded per-user OBO token (same `x-ms-query-source-authorization` header used by Work IQ). Managed-identity fallback is never used for the remote `fabricOntology` kind: when the OBO token is missing, the Fabric IQ source is skipped with a clear warning and local sources still serve the request.

**Data-egress caveat:** Fabric IQ forwards the caller's OBO token to Microsoft Fabric and returns grounded snippets from ontology-exposed Fabric data back to the orchestrator. Operators enabling Fabric IQ should confirm this data-flow is compliant with their tenant's data-boundary and Fabric-workspace access policies before turning the flag on. Grounded content still ends up in orchestrator responses and, transitively, in downstream telemetry and chat history.

The paired orchestrator release [`v3.3.0`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.3.0) adds the runtime settings `FABRIC_IQ_ENABLED`, `FABRIC_IQ_KNOWLEDGE_SOURCE_NAME`, `FABRIC_IQ_WORKSPACE_ID`, and `FABRIC_IQ_ONTOLOGY_ID`, plus the Fabric IQ retrieve wiring (`kind=fabricOntology` with preview API `2026-05-01-preview`). `manifest.json` is pinned to that release.

### Added

- **Fabric IQ (Microsoft Fabric ontology) knowledge source support (opt-in, default off).**
  Foundry IQ deployments can now optionally include a Microsoft Fabric
  ontology as an additional knowledge source on the shared knowledge base,
  so retrieval can ground answers in a Fabric semantic model, lakehouse,
  warehouse, or KQL database exposed through the ontology, alongside
  existing RAG documents and Work IQ. Feature is opt-in via the App
  Configuration keys `FABRIC_IQ_ENABLED`, `FABRIC_IQ_KNOWLEDGE_SOURCE_NAME`,
  `FABRIC_IQ_WORKSPACE_ID`, and `FABRIC_IQ_ONTOLOGY_ID`. With the flag off
  (the default), the rendered search resources and deployed behavior are
  identical to the `v3.3.0` defaults, so existing environments upgrade with
  no change. Requires a Microsoft Fabric workspace with an ontology item,
  tenant-level Fabric ontology enablement, Fabric-licensed end users, and
  the same Entra tenant as the Foundry / Search resource. See
  [`Azure/gpt-rag#543`](https://github.com/Azure/gpt-rag/issues/543).

### Changed

- **Orchestrator pin bumped to [`v3.3.0`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.3.0):** carries the Fabric IQ retrieve support (`kind=fabricOntology`), reusing the OBO header path introduced for Work IQ.

### Component versions

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.3.0 |
| gpt-rag-ingestion | v2.4.14 |
| infra / AI Landing Zone | v2.3.0 |

### Validation

- `python -m pytest -q config/search/tests/test_foundry_iq_templates.py` passes (21 tests).
- Landing zone: no-op for this release. The AI Landing Zone passthrough already stamps unknown App Configuration keys, so `FABRIC_IQ_*` keys flow through without any infra change.
- Live Azure validation was performed in a throwaway Standard-mode environment: Fabric IQ default OFF confirmed regression-free (Work IQ + Blob KS chat path still green), Fabric IQ ON with a stub `workspaceId`/`ontologyId` confirmed the orchestrator starts, the `fabricOntology` knowledge source is either registered on the shared knowledge base or gracefully skipped with a clear warning, and the existing chat path continues to work.
- **Deferred:** live end-to-end query against a real Fabric ontology workspace. The current validation subscription cannot provision Fabric, so live-query validation is deferred to a follow-up run in a Fabric-capable tenant. Fabric IQ is opt-in and defaults off, so this deferral does not affect operators who don't turn the flag on.
## [v3.3.0] - 2026-07-10

### User and operator impact

Foundry IQ deployments can now optionally include **Microsoft 365 Work IQ** as an additional knowledge source on the shared knowledge base, so retrieval can ground answers in the signed-in user's Microsoft 365 context alongside the existing RAG documents. The feature is opt-in and defaults to off. Set `WORK_IQ_ENABLED=true` and pick a `WORK_IQ_KNOWLEDGE_SOURCE_NAME` before `azd provision` to enable it. With the flag off (the default), the rendered search resources and deployed behavior are identical to `v3.2.0` defaults, so existing environments upgrade with no change.

Enabling Work IQ requires a tenant-level prerequisite: the `EnableFoundryIQWithWorkIQ` feature flag, admin consent for the Work IQ service principal (appId `fdcc1f02-fc51-4226-8753-f668596af7f7`) submitted through the [admin consent form](https://aka.ms/foundry-iq-work-iq-admin-consent-form), and a Microsoft 365 Copilot license for end users. See [`Azure/gpt-rag#543`](https://github.com/Azure/gpt-rag/issues/543) for the full proposal. The setup script runs a soft preflight against Microsoft Graph: when Work IQ is enabled but consent has not been granted, the script prints a warning explaining the prerequisites and skips only the Work IQ knowledge source (the rest of the deployment continues), so operators can enable the flag ahead of consent without breaking the environment.

The paired orchestrator release [`v3.2.0`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.2.0) adds the runtime settings `WORK_IQ_ENABLED`, `WORK_IQ_KNOWLEDGE_SOURCE_NAME`, and `FOUNDRY_IQ_MAX_RUNTIME_SECONDS`, plus the reference-normalization seam for remote knowledge source shapes. `manifest.json` is pinned to that release.

### Added

- **Optional Work IQ knowledge source for Foundry IQ:** When `RETRIEVAL_BACKEND=foundry_iq`, `WORK_IQ_ENABLED=true`, and `WORK_IQ_KNOWLEDGE_SOURCE_NAME` is set, `config/search/search.j2` renders an additional `workIQ` knowledge source (no `filterAddOn`) and references it from the knowledge base alongside the existing sources.
- **New passthrough settings:** `config/search/search.settings.j2` stamps `WORK_IQ_ENABLED` (default `false`) and `WORK_IQ_KNOWLEDGE_SOURCE_NAME` (default `""`) into App Configuration under the `gpt-rag` label, so both new and upgraded environments always carry the keys.
- **Soft admin-consent preflight:** `config/search/setup.py` gained `check_work_iq_admin_consent` and `filter_work_iq_sources`. When Work IQ is enabled, the setup script probes Microsoft Graph for the Work IQ service principal, logs the enablement prerequisites when consent is missing or the check is inconclusive, and skips just the Work IQ knowledge source instead of failing the deployment.
- **Template tests:** `config/search/tests/test_foundry_iq_templates.py` now covers Work IQ default-off (no `workIQ` entry emitted), enabled without a name (still no entry), enabled with a name (emits a `workIQ` source with no `filterAddOn` and adds the name to the knowledge base), and Work IQ ignored when `RETRIEVAL_BACKEND` is not `foundry_iq`. The preflight filter is tested for the disabled, consented, not-consented, and inconclusive paths.

### Changed

- **Orchestrator pin bumped to [`v3.2.0`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.2.0):** carries the Work IQ retrieve support (`kind="workIQ"`), the `maxRuntimeInSeconds` header plumbing (default 120 seconds, overridable via `FOUNDRY_IQ_MAX_RUNTIME_SECONDS`), and the reference-normalization seam for the Work IQ `sourceData` shape.

### Component versions

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.2.0 |
| gpt-rag-ingestion | v2.4.14 |
| infra / AI Landing Zone | v2.3.0 |

### Validation

- `python -m pytest -q config/search/tests/test_foundry_iq_templates.py` passes (17 tests).
- With `WORK_IQ_ENABLED` unset or `false`, the rendered `search.j2` JSON is identical to `v3.2.0` (no `workIQ` knowledge source, no additional knowledge base reference), so default deployments are byte-identical.

## [v3.2.0] - 2026-07-02

### User and operator impact

Foundry IQ deployments using Pattern A (`FOUNDRY_IQ_PATTERN=azureBlob`) can now also serve documents that users upload through the chat UI, in the same conversation, without switching retrieval backends. When you turn the feature on, the search setup provisions a second, conversational knowledge source over the existing RAG index (`ragindex-<token>`) and adds it to the Foundry IQ knowledge base. Uploaded files are indexed with a `conversationId`, and the orchestrator (pinned here to [`v3.1.1`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.1.1)) scopes that conversational source per conversation at query time, so one user's upload never leaks into another conversation.

The feature is opt-in and defaults to off. Set `FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED=true` before `azd provision` to enable it. With the flag off (the default), the rendered search resources and deployed behavior are identical to GPT-RAG `v3.1.0` defaults, so existing environments upgrade with no change. The feature only applies to Pattern A; the `searchIndex` pattern (Pattern B) never adds the conversational source because file upload already works there.

Fresh deployments also consume [AI Landing Zone `v2.3.0`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.3.0), which adds a generic App Configuration passthrough so accelerators can push their own settings into App Config without the landing zone needing to know about them.

### Added

- **Conversational file upload knowledge source for Foundry IQ Pattern A:** When `RETRIEVAL_BACKEND=foundry_iq`, the pattern is not `searchIndex`, and `FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED=true`, `config/search/search.j2` renders a second `searchIndex` knowledge source over `SEARCH_RAG_INDEX_NAME` (semantic config `semantic-config`) and references it from the knowledge base alongside the primary `azureBlob` source. The conversational source name defaults to `<ragIndexName>-conv-ks` and can be overridden with `FOUNDRY_IQ_CONVERSATION_KNOWLEDGE_SOURCE_NAME`.
- **New passthrough settings:** `scripts/postProvision.ps1` and `config/search/search.settings.j2` stamp `FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED` (default `false`) and `FOUNDRY_IQ_CONVERSATION_KNOWLEDGE_SOURCE_NAME` (default `<ragIndexName>-conv-ks`) into App Configuration under the `gpt-rag` label, so both new and upgraded environments always carry the keys.
- **Template tests:** `config/search/tests/test_foundry_iq_templates.py` covers the feature off (single source), on (blob plus conversational source, knowledge base references both), and the `searchIndex` pattern guard (no conversational source added).

### Changed

- **AI Landing Zone Bicep module pin bumped to [`v2.3.0`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.3.0):** `manifest.json`, `.gitmodules`, and the `infra` submodule HEAD are aligned on the landing-zone release that adds the generic App Configuration passthrough.
- **Orchestrator pin bumped to [`v3.1.1`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.1.1):** carries the hybrid multi-source retrieval from `v3.1.0` plus the `filterAddOn` format fix from `v3.1.1`, so the conversational knowledge source is scoped with `conversationId eq '<conversation-id>'` at query time. Required for conversational file upload to work end to end.

### Validation

- `pytest config/search/tests/test_foundry_iq_templates.py` passes (8 tests), covering the conversational source on/off behavior, the knowledge base references, and the `searchIndex` pattern guard.
- With `FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED` unset or `false`, the rendered `search.j2` output is unchanged from `v3.1.0` (single knowledge source, single knowledge base reference), so the default deployment is byte-identical.

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.1.1 |
| gpt-rag-ingestion | v2.4.14 |
| bicep-ptn-aiml-landing-zone | v2.3.0 |

## [v3.1.0] - 2026-07-01

### User and operator impact

Fresh deployments now consume [AI Landing Zone `v2.2.0`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.2.0), which flips the default `resourceNamingMode` from `legacy` to `caf` and derives every CAF token automatically (workload from a subscription/env/location hash, environment from `AZURE_ENV_NAME`, region from a built-in abbreviation map). Fresh Basic and Zero Trust provisions therefore produce Cloud Adoption Framework-aligned resource names out of the box (for example `cosmos-<hash>-<env>-<region>-001`), without requiring operators to set `CAF_WORKLOAD_NAME`, `CAF_ENVIRONMENT_NAME`, or `CAF_REGION_NAME`. Operators who still want the pre-`v2.2.0` naming scheme can opt back in by setting `RESOURCE_NAMING_MODE=legacy` before `azd provision`.

### Changed

- **AI Landing Zone Bicep module pin bumped to [`v2.2.0`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.2.0):** `manifest.json`, `.gitmodules`, and the `infra` submodule HEAD are aligned on the CAF-default landing-zone release. This supersedes the interim `v2.1.6` pin.
- **`main.parameters.json` aligned with the `v2.2.0` CAF-default contract:** `resourceNamingMode` now defaults to `caf`, and `cafWorkloadName`, `cafEnvironmentName`, and `cafRegionName` default to empty strings so the landing-zone bicep resolves them from `AZURE_ENV_NAME`, `AZURE_LOCATION`, and a subscription-scoped hash. Operators can still override every token via the same `${CAF_*_NAME=...}` environment variables.

### Fixed

- **Azure AI Foundry can be provisioned in a different region than the primary deployment:** `main.bicep` now exposes an `aiFoundryLocation` parameter (wired from `AZURE_AI_FOUNDRY_LOCATION`) and routes both the AI Foundry account module and its capability host through it, so deployments with `AZURE_LOCATION=<primary>` and `AZURE_AI_FOUNDRY_LOCATION=<foundry-region>` no longer force the AI Foundry account into the primary region.
- **`scripts/postProvision.ps1` is now CAF-naming aware:** introduced an `_resolveResource` helper that queries `az resource list` per resource type (AI Foundry, Storage, Cosmos, Search, Key Vault, ACR, Container Apps Environment, Log Analytics, App Insights) and falls back to the legacy `<prefix>-<resourceToken>` derivation. Foundry project name is discovered via `az cognitiveservices account list-projects`; Cosmos DB name via `az cosmosdb sql database list`. Without this fix, post-provision failed with `ResourceNotFound` under the new `resourceNamingMode=caf` default because it assumed the legacy naming pattern. Legacy environments continue to work via the fallback.

### Validation

- Fresh Basic (non-Zero-Trust) provision + deploy in Australia East with AI Foundry in East US 2, `RETRIEVAL_BACKEND=foundry_iq`, and `FOUNDRY_IQ_PATTERN=searchIndex`. Post-provision resolver picked up all CAF-named resources; AI Foundry blocklist and RAI policy created against the CAF-named account; AppConfig populated with 103 keys; Search indexes plus Foundry IQ knowledge source and knowledge base created; all three container apps healthy on `--0000001` with 100% traffic; frontend fronted by Entra Easy Auth (`RedirectToLoginPage`, v2 issuer).
- Bicep build validation (`az bicep build --file infra/main.bicep`) exited 0.

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.0.4 |
| gpt-rag-ingestion | v2.4.14 |
| bicep-ptn-aiml-landing-zone | v2.2.0 |

## [v3.0.8] - 2026-06-30

### User and operator impact

Fresh Zero Trust deployments with Foundry IQ native Blob now provision and retrieve documents end to end. The release consumes AI Landing Zone `v2.1.5`, which fixes the primary application Search service private-link ordering for Foundry/OpenAI/Cognitive Services, and carries the GPT-RAG post-provision fixes that stamp and consume the native Blob settings required for Knowledge Source and Knowledge Base creation.

### Changed

- **AI Landing Zone Bicep module pin bumped to [`v2.1.5`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.1.5):** `manifest.json`, `.gitmodules`, and the `infra` submodule HEAD are aligned on the validated landing-zone release.
- **Fresh Foundry IQ deployments now carry native Blob settings into infrastructure:** `main.parameters.json` passes `RETRIEVAL_BACKEND=foundry_iq` and the native `FOUNDRY_IQ_*` defaults through azd/Bicep so fresh Zero Trust provisions stamp App Configuration for Foundry IQ `azureBlob` instead of silently falling back to direct Azure AI Search.

### Fixed

- **Fresh Foundry IQ standard extraction setup now seeds required search and AI Services settings:** Post-provision search setup derives `SEARCH_RAG_INDEX_NAME` before rendering Foundry IQ knowledge resources and supplies the `aiServices.uri` / chat model resource URI required by Azure AI Search when `FOUNDRY_IQ_CONTENT_EXTRACTION_MODE=standard`.
- **Generated Foundry IQ Blob indexers run privately under network isolation:** Search setup enforces `parameters.configuration.executionEnvironment = Private` on service-generated Blob indexers when `NETWORK_ISOLATION=true`.
- **Regional preflight blocks unsupported Content Understanding regions:** The preflight gate rejects regions where Foundry IQ standard extraction cannot run before provisioning starts.

### Validation

- Full Zero Trust validation passed in Australia East with `NETWORK_ISOLATION=true`, Foundry IQ native Blob, Azure Firewall, Bastion, jumpbox, NAT Gateway, and ACR task agent pool enabled.
- Provisioning and jumpbox post-provision completed successfully.
- App Configuration contained `NETWORK_ISOLATION`; the Foundry IQ Knowledge Source and Knowledge Base were created; the generated Blob indexer used private execution.
- The requested PDF was indexed through the private Blob path, the Knowledge Base index contained documents, and Knowledge Base retrieval returned references from the indexed PDF.

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.0.4 |
| gpt-rag-ingestion | v2.4.14 |
| bicep-ptn-aiml-landing-zone | v2.1.5 |

## [v3.0.7] - 2026-06-29

### User and operator impact

NL2SQL deployments now consume the orchestrator patch that strengthens the
read-only enforcement before SQL execution. This umbrella release pins
`gpt-rag-orchestrator` to `v3.0.4`, which rejects stacked SQL batches and
non-read-only SQL before datasource access. Operators should still keep every
SQL Server, Azure SQL, or Fabric SQL datasource principal least-privilege and
read-only.

### Changed

- **Orchestrator pin bumped to [`v3.0.4`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.0.4):** consumes the NL2SQL read-only enforcement hardening from [Azure/gpt-rag-orchestrator#256](https://github.com/Azure/gpt-rag-orchestrator/pull/256). UI, ingestion, and AI Landing Zone pins are unchanged from `v3.0.6`.

### Validation

- Release metadata validation passed for `manifest.json` and `CHANGELOG.md`.

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.0.4 |
| gpt-rag-ingestion | v2.4.14 |
| bicep-ptn-aiml-landing-zone | v2.1.4 |

## [v3.0.6] - 2026-06-28

### User and operator impact

Zero Trust component deployments no longer depend on Docker Hub base-image pulls for the orchestrator and ingestion images. The runtime pins in this umbrella release consume the released component fixes that moved those builds to Azure-owned bases, so ACR remote builds can complete in locked-down environments where Docker Hub egress is unavailable.

This release also includes bounded retries for ACR remote builds and the GPT-RAG regional preflight gate. Operators get faster, clearer feedback before long provisioning attempts when a target region has provider registration, quota, model, AI Search, or Cosmos DB readiness issues.

### Changed

- **Orchestrator pin bumped to [`v3.0.3`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.0.3):** picks up the Zero Trust deployment hardening and bounded ACR remote build retry behavior for the orchestrator component.
- **Ingestion pin bumped to [`v2.4.14`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.14):** picks up the Zero Trust deployment hardening and bounded ACR remote build retry behavior for the ingestion component.
- **Regional preflight gate added:** the GPT-RAG-owned preflight hook runs before provisioning and reports provider registration, location support, supported quota, model availability, and known AI Search/Cosmos capacity limitations with plain `PASS` / `WARN` / `FAIL` output.
- **AI Landing Zone and UI pins unchanged:** AI Landing Zone remains [`v2.1.4`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.1.4), and UI remains [`v2.3.13`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.13).

### Validation

- Full Zero Trust deployment validation passed in Switzerland North.
- Provisioning, post-provision configuration, component deployment, ACR remote builds, and readiness checks passed.
- ACR build logs showed no Docker Hub (`registry-1.docker.io`) pulls for the orchestrator or ingestion images.
- The regional preflight read-only run passed with expected warnings only.

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.0.3 |
| gpt-rag-ingestion | v2.4.14 |
| bicep-ptn-aiml-landing-zone | v2.1.4 |

## [v3.0.5] - 2026-06-27

### User and operator impact

Zero Trust deployments with Foundry IQ now work end to end. `v3.0.4` left ZT blocked on [bicep-ptn-aiml-landing-zone#110](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/110), where Foundry capability host creation failed during `azd provision` with `AmlRp BadRequest: "Invalid vnet resource ID provided"` because the capability host subnet delegation was emitted as `Microsoft.app` instead of `Microsoft.App`. AI Landing Zone [`v2.1.4`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.1.4) fixes the casing, and `v3.0.5` consumes that pin. ZT operators no longer need to opt down to `RETRIEVAL_BACKEND=ai_search`.

### Changed

- **AI Landing Zone Bicep module pin bumped to [`v2.1.4`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.1.4):** `manifest.json`, `.gitmodules`, and the `infra` submodule HEAD are all aligned on `v2.1.4`. Picks up the capability host subnet delegation casing fix that unblocks ZT + Foundry IQ.

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.0.2 |
| gpt-rag-ingestion | v2.4.13 |
| bicep-ptn-aiml-landing-zone | v2.1.4 |

## [v3.0.4] - 2026-06-26

### User and operator impact

Aligns the Foundry IQ release train end to end. Earlier `v3.0.x` tags shipped CHANGELOG entries and GitHub Release notes that claimed AI Landing Zone `v2.1.3` and `gpt-rag-orchestrator` `v3.0.2`, but `manifest.json`, the `infra` submodule pointer, and the `RETRIEVAL_BACKEND` default never moved together. `v3.0.4` is the release that actually consumes those pins and makes the native Foundry IQ Blob default work consistently for new deployments.

### Changed

- **Default `RETRIEVAL_BACKEND` flipped from `ai_search` to `foundry_iq`** (`scripts/postProvision.ps1`). Matches the AI Landing Zone `v2.1.3` default so a fresh `azd up` lands on the native Foundry IQ Blob path without operators having to set `RETRIEVAL_BACKEND` by hand. Operators who want the GPT-RAG ingestion plus Azure AI Search path can opt down with `azd env set RETRIEVAL_BACKEND ai_search` before provisioning.
- **`gpt-rag-orchestrator` pin bumped to [`v3.0.2`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.0.2):** Picks up the Foundry IQ `azureBlob` reference parsing fix and the `x-ms-query-source-authorization` forwarding fix that makes RBAC-filtered Knowledge Bases work end to end (closes the orchestrator-side half of [#508](https://github.com/Azure/GPT-RAG/issues/508)).
- **AI Landing Zone Bicep module pin reaffirmed at [`v2.1.3`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.1.3):** `manifest.json`, `.gitmodules`, and the `infra` submodule HEAD are now all aligned on `v2.1.3`.

### Fixed

- **Native Blob Knowledge Source connection string** (`config/search/search.j2`): removed the trailing semicolon from `ResourceId={{STORAGE_ACCOUNT_RESOURCE_ID}}`. The semicolon caused the Foundry IQ permission scope to be derived from a malformed resource ID, so RBAC-filtered query-time filtering did not match the actual container. Without this fix, RBAC-trim retrieval against the native Blob Knowledge Source silently returned no documents.

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.0.2 |
| gpt-rag-ingestion | v2.4.13 |
| bicep-ptn-aiml-landing-zone | v2.1.3 |

## [v3.0.3] - 2026-06-26

### User and operator impact

Changes the default Foundry IQ native Blob content extraction mode from `minimal` to `standard` so that scanned and image-only PDFs are ingested with OCR by default. Under the previous `minimal` default, such PDFs were ingested with empty content and were silently unsearchable, which is the wrong default behavior for typical document libraries.

`standard` mode uses the Foundry IQ Content Understanding skill (`Microsoft.Skills.Util.ContentUnderstandingSkill`) for layout, OCR, and structured extraction. It carries explicit prerequisites and limits that operators should be aware of:

- The Foundry resource must live in a [Content Understanding-supported region](https://learn.microsoft.com/azure/ai-services/content-understanding/service-limits#region-support).
- Content Understanding may require a one-time `PATCH /contentunderstanding/defaults` call against the Foundry resource on first use, otherwise Knowledge Source creation fails with `DefaultsNotSet`.
- `standard` has per-document limits of 300 pages and 5 minutes of processing time.
- `standard` is billed through Content Understanding meters in addition to the existing Azure AI Search `knowledgeRetrieval` plan.

Operators who only ingest text PDFs and want to avoid Content Understanding billing can opt down to `minimal` before provisioning:

```powershell
azd env set FOUNDRY_IQ_CONTENT_EXTRACTION_MODE minimal
```

`FOUNDRY_IQ_CONTENT_EXTRACTION_MODE` is immutable on an existing Knowledge Source. Changing the value after deployment requires recreating the Knowledge Source and the Knowledge Base that references it.

Documents that exceed the `standard` mode limits, or scenarios that need custom chunking, custom enrichment, or Excel chunking, should keep the GPT-RAG ingestion plus Azure AI Search path (`RETRIEVAL_BACKEND=ai_search` or `FOUNDRY_IQ_PATTERN=searchIndex`).

### Changed

- **Default `FOUNDRY_IQ_CONTENT_EXTRACTION_MODE` is now `standard`.** `scripts/postProvision.ps1` stamps `standard` into App Configuration for new deployments. Operators can opt down to `minimal` before provisioning. The setting is immutable after Knowledge Source creation.
- **AI Landing Zone Bicep module pin bumped to [`v2.1.3`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.1.3):** Aligns the Bicep `foundryIqContentExtractionMode` default and the `${FOUNDRY_IQ_CONTENT_EXTRACTION_MODE=standard}` substitution with the new GPT-RAG default.

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.0.1 |
| gpt-rag-ingestion | v2.4.13 |
| bicep-ptn-aiml-landing-zone | v2.1.3 |

## [v3.0.2] - 2026-06-26

### User and operator impact

Fixes the native Foundry IQ Blob Knowledge Source setup introduced in `v3.0.1`. New default deployments with `RETRIEVAL_BACKEND=foundry_iq` now create the Foundry IQ `azureBlob` Knowledge Source and Knowledge Base successfully for the standard Blob container path.

### Fixed

- **Native Blob permission defaults:** `FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS` now defaults to `["rbacScope"]`, which is accepted by Foundry IQ for `azureBlob` sources when `FOUNDRY_IQ_IS_ADLS_GEN2=false`. ADLS Gen2 deployments can still override this setting to include ACL-driven permission metadata when supported by the source.
- **Native Blob Knowledge Source payload:** The setup now sends `ResourceId=<storage resource ID>` for the storage connection string, without a trailing semicolon, so the generated Blob permission scope matches the container resource ID used by query-time RBAC filtering. It also leaves `chatCompletionModel` unset because Foundry IQ permission extraction rejects Blob indexers that include the Chat Completion skill.
- **Foundry IQ setup validation:** The Search setup script now normalizes JSON-like App Configuration values before rendering Knowledge Source payloads, cleans up the previous `searchIndex` Knowledge Source when switching to native Blob, and fails the setup when Foundry IQ Knowledge Source or Knowledge Base creation fails instead of reporting a successful provision with missing resources.
- **AI Landing Zone Bicep module pin bumped to [`v2.1.2`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.1.2):** Aligns the default native Blob permission option with the Foundry IQ service contract.

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.0.1 |
| gpt-rag-ingestion | v2.4.13 |
| bicep-ptn-aiml-landing-zone | v2.1.2 |

## [v3.0.1] - 2026-06-26

### User and operator impact

Corrects the Foundry IQ release default so `RETRIEVAL_BACKEND=foundry_iq` uses native Blob or ADLS Gen2 Knowledge Sources by default. Operators can still opt into the existing Azure AI Search `searchIndex` registration path when they specifically need Pattern B `filterAddOn`.

Foundry IQ deployments now default to native Blob or ADLS Gen2 Knowledge Sources, so Foundry IQ owns file processing and permission-aware retrieval when `RETRIEVAL_BACKEND=foundry_iq`. The existing GPT-RAG ingestion plus Azure AI Search `searchIndex` Knowledge Source path remains available as explicit Pattern B opt-in for custom security fields with `filterAddOn`.

### Added

- **Foundry IQ retrieval backend support** ([#526](https://github.com/Azure/GPT-RAG/issues/526)). Adds the GPT-RAG configuration, deployment pins, and documentation needed to run retrieval through Foundry IQ.
- **AI Landing Zone Bicep module pin bumped to [`v2.1.1`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.1.1):** Adds Foundry IQ Knowledge Base and Knowledge Source runtime configuration, `knowledgeRetrieval` billing configuration, native Blob/ADLS Knowledge Source defaults, App Configuration values, post-provision data-plane setup, and Azure AI Search semantic ranker standard.
- **Orchestrator pin bumped to [`v3.0.1`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v3.0.1):** Adds the selectable `RETRIEVAL_BACKEND=foundry_iq` runtime backend, OBO header support for native permissions, Pattern B `filterAddOn` support, the minimal-reasoning retrieve API contract, and configurable Knowledge Source kind support.
- **Foundry IQ App Configuration defaults:** `postProvision.ps1` and `config/search/search.settings.j2` now seed the generated Knowledge Base name, native Blob Knowledge Source name, Knowledge Source kind, Search endpoint, storage container, folder path, ADLS mode, content extraction mode, permission options, and semantic configuration so the deployed app can use the generated Foundry IQ resources without manual repair.
- **Documentation:** Covers Foundry IQ deployment patterns, authorization behavior, migration, rollback, billing, limitations, and troubleshooting.

### Validation

Validated in a live Azure environment:

- Provision and deploy completed successfully.
- Foundry IQ direct retrieval returned HTTP 200.
- Orchestrator image smoke test returned HTTP 200.
- Logs confirmed retrieval through Foundry IQ.
- Frontend health, ingestion docs, and orchestrator docs endpoints returned HTTP 200.

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v3.0.1 |
| gpt-rag-ingestion | v2.4.13 |
| bicep-ptn-aiml-landing-zone | v2.1.1 |

## [v2.9.16] - 2026-06-19

### User and operator impact

Patch release that bumps the orchestrator pin from [`v2.8.11`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.11) to [`v2.8.12`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.12). No other component changed: UI, ingestion, and AI Landing Zone pins are identical to v2.9.15. The orchestrator update is a P1 follow-up on the operator dashboard's Overview and Conversations tabs: the Custom range date inputs now cap at today and clamp any stored future date on load; the `to=YYYY-MM-DD` query parameter is now inclusive of the entire end day instead of stopping at midnight UTC; Overview tooltips render on an opaque background so they are readable over the cards behind them; the Conversations dialog reconstructs user turns from the persisted prompts (with a friendly note pointing to the Azure AI Foundry agent thread for the full transcript) instead of showing empty cards; and the Configuration tab's *Reload settings cache* button is renamed to *Refresh from App Configuration* with sentence-case info tooltips on both footer buttons explaining what each one does. See [Azure/gpt-rag-orchestrator#246](https://github.com/Azure/gpt-rag-orchestrator/pull/246).

### Changed

- **Orchestrator pin bumped to [`v2.8.12`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.12):** Operator-reported follow-up on the dashboard Overview and Conversations tabs. Caps Custom range date inputs at today (UTC), makes the `to` parameter end-of-day inclusive, rejects future ranges with HTTP 400, gives tooltips an opaque background, reconstructs conversation detail from persisted prompts with a Foundry deep-link note, and clarifies the Configuration tab button labels and tooltips.

- **UI pin unchanged:** [`v2.3.13`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.13).
- **Ingestion pin unchanged:** [`v2.4.13`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.13).
- **Infra (AI Landing Zone) pin unchanged:** [`v2.0.20`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.20).

### Validation

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.12 |
| gpt-rag-ingestion | v2.4.13 |
| AI Landing Zone | v2.0.20 |

## [v2.9.15] - 2026-06-19

### User and operator impact

Patch release that bumps the ingestion pin from [`v2.4.12`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.12) to [`v2.4.13`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.13). No other component changed: UI, orchestrator, and AI Landing Zone pins are identical to v2.9.14. The ingestion update is a P2 follow-up on the operator dashboard Jobs tab: the *Run now* button strip and the *Queue and schedule* table have moved off the Jobs tab into a new dedicated **Schedules** tab (tab order is now *Jobs | Schedules | Files | Configuration*), and the "Started <job>" success toast now auto-dismisses after 4 seconds and gets a manual close button so it no longer sits on screen forever. See [Azure/gpt-rag-ingestion#254](https://github.com/Azure/gpt-rag-ingestion/pull/254).

### Changed

- **Ingestion pin bumped to [`v2.4.13`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.13):** Operator-reported follow-up on the Jobs tab. Relocates the *Run now* strip and *Queue and schedule* table to a new *Schedules* tab so the Jobs tab stays focused on the recent-runs history; makes the *Run now* success toast auto-dismiss after 4 seconds with a manual close button so it no longer stays on screen forever.

- **UI pin unchanged:** [`v2.3.13`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.13).
- **Orchestrator pin unchanged:** [`v2.8.11`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.11).
- **Infra (AI Landing Zone) pin unchanged:** [`v2.0.20`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.20).

### Validation

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.11 |
| gpt-rag-ingestion | v2.4.13 |
| bicep-ptn-aiml-landing-zone | v2.0.20 |
## [v2.9.14] - 2026-06-19

### User and operator impact

Patch release that bumps the orchestrator pin from [`v2.8.10`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.10) to [`v2.8.11`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.11). No other component changed: UI, ingestion, and AI Landing Zone pins are identical to v2.9.13. The orchestrator update is a P2 follow-up against the Overview tab dashboard shipped in v2.8.10: it stops the info tooltips from rendering in ALL CAPS, fixes the Active users metric so anonymous traffic counts as a single bucket instead of one user per conversation, and makes the Custom range chip immediately reveal the From/To date inputs without zeroing the chart. See [Azure/gpt-rag-orchestrator#241](https://github.com/Azure/gpt-rag-orchestrator/issues/241) for the operator report.

### Changed

- **Orchestrator pin bumped to [`v2.8.11`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.11):** Operator-reported follow-up to v2.8.10. Three Overview tab fixes: tooltip sentence case, anonymous user bucketing in the Active users metric, and a visible Custom range editor that keeps the chart populated.

- **UI pin unchanged:** [`v2.3.13`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.13).
- **Ingestion pin unchanged:** [`v2.4.12`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.12).
- **Infra (AI Landing Zone) pin unchanged:** [`v2.0.20`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.20).

### Validation

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.11 |
| gpt-rag-ingestion | v2.4.12 |
| bicep-ptn-aiml-landing-zone | v2.0.20 |
## [v2.9.13] - 2026-06-19

### User and operator impact

Patch release that bumps the orchestrator pin from [`v2.8.9`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.9) to [`v2.8.10`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.10). No other component changed: UI, ingestion, and AI Landing Zone pins are identical to v2.9.12. The orchestrator update is a P1 patch against the operator dashboard shipped in v2.8.9: it restores the Conversations tab Created/Last updated date columns (they were showing `-` for every row), unblocks saving `REASONING_EFFORT` from the Configuration tab, and adds a time-range picker plus accessible info tooltips to the Overview tab so operators can scope the chart, Engagement panel, and Active users to a chosen window. See [Azure/gpt-rag-orchestrator#241](https://github.com/Azure/gpt-rag-orchestrator/issues/241) for the full operator report.

### Changed

- **Orchestrator pin bumped to [`v2.8.10`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.10):** Operator-reported follow-up to the v2.8.9 dashboard. Fixes the Conversations tab date columns and the `REASONING_EFFORT` save validation, and adds the Overview time-range picker and metric tooltips.

- **UI pin unchanged:** [`v2.3.13`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.13).
- **Ingestion pin unchanged:** [`v2.4.12`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.12).
- **Infra (AI Landing Zone) pin unchanged:** [`v2.0.20`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.20).

## [v2.9.12] - 2026-06-18

### User and operator impact

Patch release that bumps the ingestion pin from [`v2.4.11`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.11) to [`v2.4.12`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.12). No other component changed: orchestrator, UI, and AI Landing Zone pins are identical to v2.9.11. This release fixes a small but visible usability problem on the ingestion dashboard's **Configuration** tab: every text/number input used its own example or default as the HTML placeholder, styled close enough to a real entered value that operators could not tell empty fields apart from configured ones, and the same example was duplicated in the helper text below the input. Placeholders are now neutral (`Not configured`, or `Default: <value>` for the two cron inputs where the backend falls back to a default when empty), and the example is shown only in the helper line.

### Changed

- **Ingestion pin bumped to [`v2.4.12`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.12):** Operator-reported follow-up to v2.4.11. 15 inputs updated on the Configuration tab; no backend, schema, or styling changes.

- **Orchestrator pin unchanged:** [`v2.8.9`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.9).
- **UI pin unchanged:** [`v2.3.13`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.13).
- **Infra (AI Landing Zone) pin unchanged:** [`v2.0.20`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.20).

### Validation

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.9 |
| gpt-rag-ingestion | v2.4.12 |
| bicep-ptn-aiml-landing-zone | v2.0.20 |

Validated by upgrading an existing v2.9.11 sandbox: rebuilt the ingestion image at the v2.4.12 tag, redeployed the ingestion container app, confirmed `GET /api/version` returns `2.4.12`, and confirmed the Configuration tab inputs no longer show cron expressions or numeric examples as placeholders (they now read `Not configured` or `Default: <value>` and the example is shown only in the helper text below).

## [v2.9.11] - 2026-06-18

### User and operator impact

Patch release that bumps the ingestion pin from [`v2.4.10`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.10) to [`v2.4.11`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.11). No other component changed: orchestrator, UI, and AI Landing Zone pins are identical to v2.9.10. This release polishes the **Queue and schedule** panel added in v2.9.10: the *Run now* toast now correctly says "Started" instead of "Queued" (APScheduler fires immediately, not after a delay), the *Cron* column is no longer empty (it now reads the live trigger registered with the scheduler instead of an app config key that did not match), the panel refreshes within ~1 second after a *Run now* click (instead of waiting up to 10 seconds for the next normal poll), the panel is now **collapsible** with the operator preference persisted in localStorage and **defaults to collapsed** so it stops pushing the runs table down ~250 px on every page load, and a new **Last run** column shows the most recent finished or failed run per `job_type`. Operators who turned on `ENABLE_DASHBOARD=true` on the ingestion app are the main beneficiaries.

### Changed

- **Ingestion pin bumped to [`v2.4.11`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.11):** Polishes [`Azure/gpt-rag-ingestion#247`](https://github.com/Azure/gpt-rag-ingestion/issues/247). `GET /api/jobs/queue` now reads `cron` from `scheduler.get_job(job_id).trigger` (single source of truth, matches what APScheduler is actually firing) and includes a new `last_run` field with `{started_at, finished_at, status, indexed_count}` per item, derived from the same cached runs store `/api/jobs/runs` reads (no extra request per poll). The frontend Queue panel is now collapsible (default collapsed, preference persisted in localStorage under `gpt-rag-ingestion.queuePanel.expanded`), polls at 1 s for 15 s after every *Run now* click before reverting to 10 s, renders a new *Last run* column, and the *Run now* toast says "Started" / "is already running" matching what operators actually observe.

- **Orchestrator pin unchanged:** [`v2.8.9`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.9).
- **UI pin unchanged:** [`v2.3.13`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.13).
- **Infra (AI Landing Zone) pin unchanged:** [`v2.0.20`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.20).

### Validation

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.9 |
| gpt-rag-ingestion | v2.4.11 |
| bicep-ptn-aiml-landing-zone | v2.0.20 |

Validated by upgrading an existing v2.9.10 sandbox: rebuilt the ingestion image at the v2.4.11 tag, redeployed the ingestion container app, confirmed `GET /api/version` returns `2.4.11` and `GET /api/jobs/queue` returns non-null `cron` for `blob_index` and `blob_purge` and a populated `last_run` for `blob_index`. The Queue panel renders collapsed by default with the compact summary line, expands via the chevron toggle, and the *Last run* column shows the most recent run with relative time, status, and indexed count.

## [v2.9.10] - 2026-06-18

### User and operator impact

Feature release that bumps the ingestion pin from [`v2.4.9`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.9) to [`v2.4.10`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.10). No other component changed: orchestrator, UI, and AI Landing Zone pins are identical to v2.9.9. This release adds **queue and next-run visibility** to the ingestion operator dashboard. Before v2.4.10, the *Run now* button (added in v2.4.7) was fire-and-forget: clicking it queued a job and showed a toast, then disappeared, leaving no way to see what was in flight or when the next cron would fire without tailing container logs. v2.4.10 adds a compact *Queue and schedule* panel above the Jobs table that polls every 10 seconds and shows, per `job_type`: any in-flight run (run id + elapsed), the next scheduled run as a relative ETA with an absolute ISO tooltip, and the current cron string. The *Run now* button is also rendered disabled with a `Job already running` tooltip when the matching job is in flight, so operators learn before they click and get a `409 Conflict`. Operators who turned on `ENABLE_DASHBOARD=true` on the ingestion app are the main beneficiaries.

### Changed

- **Ingestion pin bumped to [`v2.4.10`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.10):** Adds [`Azure/gpt-rag-ingestion#247`](https://github.com/Azure/gpt-rag-ingestion/issues/247). New read-only `GET /api/jobs/queue` (network-only auth, same posture as `GET /api/jobs` and `GET /api/config`) returns per `job_type` the `in_flight` `{run_id, started_at}`, `next_scheduled_at` from APScheduler, and the current cron string. The existing in-process `_running_jobs` registry was extended to also record `started_at` at the same insertion sites - manual and cron paths still share one lock; no parallel registry was added. The frontend Queue panel polls every 10 seconds with plain `setInterval` (no new data-fetching dependency).

- **Orchestrator pin unchanged:** [`v2.8.9`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.9).
- **UI pin unchanged:** [`v2.3.13`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.13).
- **Infra (AI Landing Zone) pin unchanged:** [`v2.0.20`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.20).

### Validation

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.9 |
| gpt-rag-ingestion | v2.4.10 |
| bicep-ptn-aiml-landing-zone | v2.0.20 |

Validated by upgrading an existing v2.9.9 sandbox: rebuilt the ingestion image at the v2.4.10 tag, redeployed the ingestion container app, confirmed `GET /api/version` returns `2.4.10` and `GET /api/jobs/queue` returns one row per `job_type` with the expected `in_flight`, `next_scheduled_at`, and `cron` fields. The operator dashboard *Queue and schedule* panel renders as documented and the *Run now* button correctly disables with the `Job already running` tooltip when a job is in flight.

## [v2.9.9] - 2026-06-18

### User and operator impact

Patch release that bumps the ingestion pin from [`v2.4.8`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.8) to [`v2.4.9`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.9). No other component changed: orchestrator, UI, and AI Landing Zone pins are identical to v2.9.8. This release finishes the **Configuration tab** fix started in v2.9.8: that release fixed the missing top-level `settings` array, but the tab still rendered blank because each section was missing the `title` and `keys` fields the typed frontend `ConfigSection` reads. Operators who turned on `ENABLE_DASHBOARD=true` on the ingestion app are the main beneficiaries: the Configuration tab now actually renders, with no other behavior change.

### Changed

- **Ingestion pin bumped to [`v2.4.9`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.9):** Follow-up fix to [`Azure/gpt-rag-ingestion#242`](https://github.com/Azure/gpt-rag-ingestion/issues/242). v2.4.8 added the top-level `settings` array but `GET /api/config` was still emitting each section as `{id, label, settings}` while the frontend `ConfigSection` reads `{id, title, keys}`. `section.keys.map(...)` therefore crashed with `TypeError: undefined is not iterable` and the tab still rendered nothing. The endpoint now also emits `title` (mirror of `label`) and `keys` (ordered list of setting keys, matching the nested `settings` order) on every section. The legacy `label` and nested `settings` fields stay, so no other callers are affected.

- **Orchestrator pin unchanged:** [`v2.8.9`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.9).
- **UI pin unchanged:** [`v2.3.13`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.13).
- **Infra (AI Landing Zone) pin unchanged:** [`v2.0.20`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.20).

### Validation

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.9 |
| gpt-rag-ingestion | v2.4.9 |
| bicep-ptn-aiml-landing-zone | v2.0.20 |

Validated by upgrading an existing v2.9.8 sandbox: rebuilt the ingestion image at the v2.4.9 tag, redeployed the ingestion container app, confirmed `GET /api/version` returns `2.4.9` and `GET /api/config` returns every section with both `label`/`settings` (legacy) and `title`/`keys` (frontend contract). The operator dashboard Configuration tab now loads as documented.

## [v2.9.8] - 2026-06-18

### User and operator impact

Patch release that bumps the ingestion pin from [`v2.4.7`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.7) to [`v2.4.8`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.8). No other component changed: orchestrator, UI, and AI Landing Zone pins are identical to v2.9.7. This release exists purely to fix the **Configuration tab** in the ingestion operator dashboard, which rendered blank in v2.9.7 (ingestion v2.4.7). Operators who turned on `ENABLE_DASHBOARD=true` on the ingestion app are the main beneficiaries: the Configuration tab now loads as documented, with no other behavior change.

### Changed

- **Ingestion pin bumped to [`v2.4.8`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.8):** Fixes [`Azure/gpt-rag-ingestion#242`](https://github.com/Azure/gpt-rag-ingestion/issues/242). The ingestion `GET /api/config` endpoint returned a `sections` array but did not return the flat `settings` list and `authEnabled` flag the typed frontend `ConfigResponse` reads. With `res.settings` undefined the Configuration tab in the ingestion dashboard crashed with `TypeError: undefined is not iterable` and rendered nothing. The endpoint now returns both the grouped `sections` and a flat `settings` list (built from the same per-setting reader so the two views stay in lock-step), plus `authEnabled` derived from the same `_auth_enabled()` helper used elsewhere. The `sections` shape is unchanged, the allow-list and denylist are unchanged, the `Admin` app role gating is unchanged. Pure bug fix.

- **Orchestrator pin unchanged:** [`v2.8.9`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.9).
- **UI pin unchanged:** [`v2.3.13`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.13).
- **Infra (AI Landing Zone) pin unchanged:** [`v2.0.20`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.20).

### Validation

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.9 |
| gpt-rag-ingestion | v2.4.8 |
| infra (landing zone) | v2.0.20 |

The fix was validated in the ingestion repo: `pytest` full suite passes (26 of 26, +1 focused test asserting the flat `settings` array exists and equals the flattened section settings, and that `authEnabled` reflects `_auth_enabled()` both on and off). No other component behavior is changed by this release.

## [v2.9.7] - 2026-06-18

### User and operator impact

Patch release that bumps the AI Landing Zone pin from [`v2.0.19`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.19) to [`v2.0.20`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.20). No component code changed: orchestrator, ingestion, and UI pins are identical to v2.9.6. This release exists purely to pick up the AI Landing Zone preflight fix that prevents misleading "all checks passed" reports when regional OpenAI model quota is actually insufficient. Operators provisioning a fresh GPT-RAG environment with `azd up` are the main beneficiaries: the preflight now fails fast with a clear `MODEL_QUOTA_INSUFFICIENT` error in seconds, instead of letting ARM run for ~15 minutes and then failing partway through the deploy.

### Changed

- **AI Landing Zone pin bumped to [`v2.0.20`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.20):** Closes [`Azure/bicep-ptn-aiml-landing-zone#103`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/103). The preflight's `Expand-ParamValue` helper no longer coerces arrays and objects (such as `modelDeploymentList`) into strings while expanding `${VAR}` tokens. The AI model quota preflight can now actually inspect requested OpenAI deployments and fail early with `MODEL_QUOTA_INSUFFICIENT` when the requested capacity exceeds available regional quota. Previously the preflight could report "All checks passed" while ARM later failed with `InsufficientQuota` after ~15 minutes of partial provisioning.

### Validation

The following component versions are pinned for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.9 |
| gpt-rag-ingestion | v2.4.7 |
| infra (landing zone) | v2.0.20 |

The bumped preflight behavior was reproduced on a fresh `azd up` against the v2.9.6 manifest (AI Landing Zone v2.0.19): preflight reported all checks passed in `westus3` even though `text-embedding-3-large` quota was insufficient there, and ARM failed ~15 minutes later with `InsufficientQuota`. With v2.0.20, the preflight inspects the structured `modelDeploymentList` and returns `MODEL_QUOTA_INSUFFICIENT` upfront. No other component behavior is changed by this release.

## [v2.9.6] - 2026-06-18

### User and operator impact

This release ships a **built-in operator dashboard** at `/dashboard` on both the orchestrator and ingestion services, plus a **Configuration tab** that lets admins tune common runtime settings from the browser without restarting containers or going to the Azure portal. Everything is **opt-in and off by default**, so existing deployments are byte-for-byte unchanged until you turn it on. When enabled and Entra authentication is configured, dashboard pages require the `Admin` app role.

For operators on existing deployments the upgrade is safe and quiet. To try the new dashboards, set `ENABLE_DASHBOARD=true` in App Configuration for the orchestrator and/or the ingestion app. To start editing settings from the UI, also assign your users the `Admin` Entra app role on those apps.

### Changed

- **Orchestrator pin bumped to [`v2.8.9`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.9):**
  - **Operator dashboard at `/dashboard` ([`Azure/GPT-RAG#511`](https://github.com/Azure/GPT-RAG/issues/511)).** Three tabs: *Overview* (today / 7-day / 30-day conversation counts, a conversations-over-time chart, average user turns, active users), *Conversations* (paginated newest-first list with a detail dialog that renders the full message history), and *Configuration* (see below). Reads come from the existing Cosmos conversation container - no new storage. Overview queries are cached in-process for 60 seconds so refreshes stay cheap.
  - **Configuration tab ([`Azure/GPT-RAG#512`](https://github.com/Azure/GPT-RAG/issues/512)).** Curated, sectioned view of the common runtime settings (agent strategy, reasoning effort, temperature and top_p, max completion tokens, conversation history compaction, retrieval and search toggles, multimodal classifier, etc.). Each field has the right control (dropdown, slider, number, toggle) and an accessible info tooltip reachable by keyboard. Two safety nets protect writes: an explicit allow-list of editable keys and a denylist that rejects any key whose name matches sensitive suffixes (`_APIKEY`, `_SECRET`, `_PASSWORD`, `_CONNECTION_STRING`, `_TOKEN`, ...) or specific keys like `KEY_VAULT_URI`. Buttons are honest about what they do: *Reload settings cache* refreshes the in-process App Configuration cache, and *Apply changes* is a soft restart that refreshes the cache and returns a clear status - we deliberately did not ship a button labeled "Restart" that does not actually restart the container.
  - **Where values are written.** Accepted writes go to App Configuration under the `gpt-rag-orchestrator` label, so it is easy to filter in the Azure portal who wrote what.
  - **Access control.** Every `/api/dashboard/*` route (except `/api/dashboard/version`) requires the caller's bearer token to include the `Admin` Entra app role when auth is on. The `/dashboard` HTML page itself is open so the SPA can load and render a clear access-denied state on 403.

- **Ingestion pin bumped to [`v2.4.7`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.7):**
  - **Run job now from the dashboard ([`Azure/GPT-RAG#510`](https://github.com/Azure/GPT-RAG/issues/510)).** Admins can trigger any of the scheduled ingestion jobs (blob, sharepoint, sharepoint purge, others) on demand from the Jobs tab with a single click. The UI surfaces success and failure clearly, and the action is admin-only when auth is on.
  - **Configuration tab ([`Azure/GPT-RAG#512`](https://github.com/Azure/GPT-RAG/issues/512)).** Same shape as the orchestrator tab, but for ingestion settings (chunking, cron schedules for the recurring jobs, retrieval-side flags, etc.). When you change a `CRON_RUN_*` schedule and apply, the scheduler **reschedules the affected job in place** - no restart needed, no drift between the value in App Configuration and the value the scheduler is using. Cron strings are validated server-side with the same parser the scheduler uses at startup.
  - **Where values are written.** Accepted writes go to App Configuration under the `gpt-rag-ingestion` label.
  - **Same safety model as the orchestrator.** Opt-in via `ENABLE_DASHBOARD=true`, gated by the `Admin` app role when auth is on, allow-list plus suffix-based denylist on writes, honest action buttons.

- **UI pin unchanged:** [`v2.3.13`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.13).
- **Infra (AI Landing Zone) pin unchanged:** [`v2.0.19`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.19).

### Validation

The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.9 |
| gpt-rag-ingestion | v2.4.7 |
| infra (landing zone) | v2.0.19 |

Validated end-to-end in a live Azure environment with a fresh Standard (non-network-isolated) deployment provisioned and deployed through the standard `azd` flow. Both Container Apps were confirmed running the new image tags. With `ENABLE_DASHBOARD=false` (the default), the `/dashboard` URL returns `404` on both apps and no dashboard API routes are registered - confirming the new feature is fully off for existing deployments. With `ENABLE_DASHBOARD=true` and a user holding the `Admin` Entra app role, the Overview, Conversations, and Configuration tabs load on both apps; a value edited and applied from the Configuration tab is visible at the next request and is persisted in App Configuration under the expected per-app label; an ingestion cron change applied from the UI takes effect on the running scheduler without a restart. Component testing for each change is covered in the linked component releases.

## [v2.9.5] - 2026-06-18

### User and operator impact

This release bumps the orchestrator pin from `v2.8.6` to [`v2.8.8`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.8), picking up two orchestrator releases. Existing deployments keep the same default behavior: the new metadata-in-context feature is off by default and the diagnostics change adds log markers only. Operators who hit empty-answer situations under RBAC now get a clear log signal to act on, and operators who want the model to use indexed document metadata can opt in with new configuration keys.

### Changed

- **Orchestrator pin bumped to [`v2.8.8`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.8) (covers `v2.8.7` and `v2.8.8`):**
  - **Retrieval diagnostics ([`v2.8.7`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.7)):** Retrieval now emits greppable log markers at every swallow point so empty-answer-under-RBAC situations ([`Azure/GPT-RAG#508`](https://github.com/Azure/GPT-RAG/issues/508)) are diagnosable from logs. Search container or Application Insights logs for `[Retrieval][AUTH_FAILURE]` (level `ERROR`, emitted on AI Search 401/403, typically a Managed Identity missing the `Search Index Data Reader` role) and `[Retrieval][ERROR]` (level `WARNING`, other retrieval failures). Each record carries structured fields (`retrieval_status`, `retrieval_index`, `retrieval_credential_type`). This is diagnostics-only: no API or behavior change.
  - **Optional document metadata in LLM context ([`v2.8.8`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.8), [`Azure/GPT-RAG#506`](https://github.com/Azure/GPT-RAG/issues/506)):** Retrieval can now optionally prepend each retrieved document's indexed `custom_metadata` as a compact `[Document metadata]` block so the model can use it when answering, across all three retrieval paths. The change is additive and orchestrator-only - no ingestion, embedding, or vector changes. It is **off by default**, so existing deployments are byte-for-byte unchanged unless they opt in. New configuration keys:
    - `SEARCH_INCLUDE_METADATA_IN_CONTEXT` (bool, default `false`) - master switch. When `false`, the metadata field is not even selected from the index.
    - `SEARCH_METADATA_MAX_CHARS` (int, default `500`) - caps the rendered metadata block size per document.
    - `SEARCH_METADATA_ALLOWED_KEYS` (CSV, default empty = all keys) - optional allow-list of metadata keys to include.
  - **Before enabling metadata-in-context:** the index must have been created with the #487-era schema that contains the `custom_metadata` field. Older indexes lack the field, and Azure AI Search rejects the whole query with a `400` if a selected field is missing - which is why the feature is gated and default-off. Re-index or confirm the field exists before turning it on. Enabling it adds prompt tokens bounded by roughly `SEARCH_METADATA_MAX_CHARS` × `top_k`; use the max-chars cap and the key allow-list to keep token cost in check.

### Validation

The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.8 |
| gpt-rag-ingestion | v2.4.6 |
| infra (landing zone) | v2.0.19 |

This release was validated in a live Azure environment with a fresh Standard (non-network-isolated) deployment provisioned and deployed through the standard `azd` flow. The orchestrator Container App was confirmed running the `v2.8.8` image, and a basic `single_agent_rag` chat returned a normal, non-empty answer - confirming the default-off metadata behavior leaves existing deployments unchanged. The aggregate manifest was confirmed to pin GPT-RAG `v2.9.5`, orchestrator `v2.8.8`, and AI Landing Zone `v2.0.19`.

## [v2.9.4] - 2026-06-17

### Changed

- **Orchestrator pin bumped to [`v2.8.6`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.6):** This release includes the fix for [`Azure/GPT-RAG#505`](https://github.com/Azure/GPT-RAG/issues/505), where `single_agent_rag` follow-up turns could fail with `400 No tool call found for function call output`. The orchestrator now resumes follow-up turns from the stable Foundry conversation object instead of creating a mismatched thread/run context.
- **Foundry prompt agent reuse is now stable:** `single_agent_rag` now honors `AGENT_ID` when resolving the Foundry prompt agent. This prevents config-only changes, such as changing `REASONING_EFFORT`, from creating duplicate prompt agents instead of reusing the intended one.
- **Reasoning-model defaults were adjusted for GPT-5 reasoning models:** `MAX_COMPLETION_TOKENS` now defaults to `8000` and `REASONING_EFFORT` now defaults to `low`, reducing the chance that models such as `gpt-5-nano` spend the output budget on internal reasoning and return an empty answer with a `max_tokens` / length finish.
- **Shared document retrieval was fixed for global chunks:** Some shared indexed chunks are not tied to a specific chat conversation and can be stored with `conversationId = null`. Retrieval now includes those global chunks instead of filtering them out, so shared documents remain available to chats that should see them.
- **AI landing zone pin bumped to [`v2.0.19`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.19):** This closes [`Azure/bicep-ptn-aiml-landing-zone#101`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/101). The AI Foundry project resource now honors the parameterized `aiFoundryProjectName` instead of hardcoding `aifoundry-default-project`. When the project name is not supplied, it uses the generated resource name pattern, and when the display name is not supplied, it defaults to that same generated project name.

### Validation

The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.6 |
| gpt-rag-ingestion | v2.4.6 |
| infra (landing zone) | v2.0.19 |

The orchestrator changes were validated in a live Azure environment by confirming `single_agent_rag` follow-up turns succeed, reuse the configured Foundry prompt agent, and run with the updated reasoning defaults. The landing-zone change was validated with `az bicep build --file main.bicep`, and this release verifies the aggregate manifest pins to the published `v2.8.6` and `v2.0.19` component releases.

## [v2.9.3] - 2026-06-16

### User and operator impact

This release makes GPT-RAG preflight output quieter and more useful. Operators should no longer see warnings for transient regional capacity pools that Azure does not expose through reliable pre-create APIs. The preflight still checks the things it can validate before deployment, such as provider/location support, jumpbox VM SKU availability, and Azure OpenAI model quota.

### Changed

- **AI Landing Zone pin bumped to [`v2.0.18`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.18):** Removes the non-actionable `SEARCH_CAPACITY`, `COSMOS_CAPACITY`, and `ACA_WORKLOAD_PROFILE_CAPACITY` warnings. These checks could not reliably tell an operator what to fix before deployment, so they were more distracting than helpful.

### Validation

The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.5 |
| gpt-rag-ingestion | v2.4.6 |
| infra (landing zone) | v2.0.18 |

- Confirmed `manifest.json` pins GPT-RAG `v2.9.3` and AI Landing Zone `v2.0.18`.
- Confirmed the `infra` submodule resolves to the published `v2.0.18` tag.
- Parsed `infra/scripts/Invoke-PreflightChecks.ps1` with the PowerShell parser.
- Confirmed the pinned preflight script no longer emits `SEARCH_CAPACITY`, `COSMOS_CAPACITY`, or `ACA_WORKLOAD_PROFILE_CAPACITY` findings while preserving the actionable provider/location, VM SKU, and Azure OpenAI quota checks.

## [v2.9.2] - 2026-06-15

### User and operator impact

This release refreshes component dependencies while keeping the validated deployment path stable. Three incompatible dependency bumps were found during validation and reverted before release, so operators get the safe patch updates without pulling in broken runtime or frontend dependency chains.

It also moves GPT-RAG to AI Landing Zone [`v2.0.17`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.17), which adds more control over how Container Apps receive runtime configuration. Existing deployments keep the same default behavior.

### Changed

- **Orchestrator pin bumped from `v2.8.3` to [`v2.8.5`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.5):** Refreshes `/evaluations` and runtime dependencies. The `semantic-kernel` 1.43.0 bump was reverted in [`Azure/gpt-rag-orchestrator#214`](https://github.com/Azure/gpt-rag-orchestrator/pull/214) because it conflicts with the pinned `azure-ai-projects==2.0.0b3` and breaks the runtime image.
- **Ingestion pin bumped from `v2.4.4` to [`v2.4.6`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.6):** Refreshes Python and frontend dependencies. The React 19 `react-dom` / `@types/react-dom` bump was reverted in [`Azure/gpt-rag-ingestion#212`](https://github.com/Azure/gpt-rag-ingestion/pull/212) because it breaks the current Radix UI dependency chain in the admin dashboard frontend.
- **UI pin bumped from `v2.3.11` to [`v2.3.13`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.13):** Refreshes Python dependencies. The `opentelemetry-instrumentation-httpx` 0.63b1 bump was reverted in [`Azure/gpt-rag-ui#67`](https://github.com/Azure/gpt-rag-ui/pull/67) because it conflicts with `azure-monitor-opentelemetry==1.6.10`.
- **AI Landing Zone pin bumped to [`v2.0.17`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.17):** Adds `appRuntimeConfigurationMode` for choosing how Container Apps receive runtime configuration: `appConfig`, `containerEnv`, or `none` ([issue #89](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/89), [PR #97](https://github.com/Azure/bicep-ptn-aiml-landing-zone/pull/97)). It also makes the Container Apps Dapr sidecar opt-in ([PR #90](https://github.com/Azure/bicep-ptn-aiml-landing-zone/pull/90)). GPT-RAG keeps the existing `appConfig` behavior by default.

### Validation

The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.13 |
| gpt-rag-orchestrator | v2.8.5 |
| gpt-rag-ingestion | v2.4.6 |
| infra (landing zone) | v2.0.17 |

A fresh `azd up` was run in a Standard-mode validation environment with `NETWORK_ISOLATION=false` against the v2.9.2 manifest. The first run found the incompatible dependency bumps listed above. Those bumps were reverted in `gpt-rag-orchestrator` `v2.8.5`, `gpt-rag-ingestion` `v2.4.6`, and `gpt-rag-ui` `v2.3.13`, then validation was re-run successfully on the fixed pins.

This is the recommended upgrade path from v2.9.1 because the component changes are dependency refreshes only and the landing-zone runtime configuration change is opt-in with a backward-compatible default.

## [v2.9.1] - 2026-06-14

### User and operator impact

This release completes the `custom_metadata` feature started in v2.9.0. Blob user-defined metadata can now be extracted during ingestion and stored on Azure AI Search chunks, so retrievers can filter by blob tags such as department, document type, or business unit.

It also makes deployment troubleshooting easier. If a shell-level `APP_CONFIG_ENDPOINT` disagrees with the active azd environment, the deploy scripts now warn clearly before deploying with the shell value.

### Changed

- **Orchestrator pin bumped from `v2.8.2` to [`v2.8.3`](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.8.3):** Adds the deploy-time `APP_CONFIG_ENDPOINT` drift warning for orchestrator deployments ([Azure/GPT-RAG#491](https://github.com/Azure/GPT-RAG/issues/491)).
- **Ingestion pin bumped from `v2.4.3` to [`v2.4.4`](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.4):** Completes [`Azure/GPT-RAG#487`](https://github.com/Azure/GPT-RAG/issues/487) by extracting user-defined blob metadata into the `custom_metadata` search field added in v2.9.0. It also restores the Content Understanding multimodal extraction path for PDF page/region rendering and Office embedded image extraction.
- **UI pin bumped from `v2.3.10` to [`v2.3.11`](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.11):** Adds the same deploy-time `APP_CONFIG_ENDPOINT` drift warning for UI deployments.
- **Deploy scripts now warn when configuration sources disagree:** The component deploy scripts compare the shell `APP_CONFIG_ENDPOINT` with the active azd environment value. If both exist and differ, the scripts show a yellow warning, say which value will be used, and show how to clear the shell override. Shell precedence is unchanged, so existing jumpbox and CI flows keep working. The matching docs update was published in [`Azure/GPT-RAG#492`](https://github.com/Azure/GPT-RAG/pull/492).

### Validation

The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.11 |
| gpt-rag-orchestrator | v2.8.3 |
| gpt-rag-ingestion | v2.4.4 |
| infra (landing zone) | v2.0.16 |

- The deploy-script warning is diagnostic only. It does not change provisioned resources.
- Orchestrator validation: `pytest`, 166 tests passed.
- Ingestion validation: `pytest tests/`, 7 tests passed for blob metadata extraction.
- UI validation: no automated test suite in this repo, deploy-script behavior was validated through the shared script change used across the components.
- A fresh `azd provision` and `azd deploy` regression was already completed for the same infrastructure baseline during v2.9.0 validation, so v2.9.1 did not repeat a full `azd up`.

## [v2.9.0] - 2026-06-14

### User and operator impact

This release prepares GPT-RAG for metadata-based retrieval and unblocks fresh Foundry Agent Service v2 deployments in regions where Cosmos DB data-plane RBAC needed a narrower scope.

Operators get the new `custom_metadata` field on the RAG search index, but v2.9.0 is only the schema half of the feature. The field exists after the index schema is reapplied, but it is not populated until the ingestion component is upgraded in a later release. If you filter on `custom_metadata` with only v2.9.0 installed, expect zero matches.

### Added

- **`custom_metadata` field on the RAG search index** ([Azure/GPT-RAG#487](https://github.com/Azure/GPT-RAG/issues/487)): Adds a filterable and facetable `Collection(Edm.ComplexType)` field with `{key, value}` subfields to `config/search/search.j2`. This lets retrievers target documents by user-defined blob metadata once ingestion support is pinned, for example:

  ```text
  custom_metadata/any(m: m/key eq 'department' and m/value eq 'finance')
  ```

  The field is not included in semantic ranking prioritized keyword fields, so metadata filters do not bias semantic ranking.

### Changed

- **AI Landing Zone pin bumped to [`v2.0.16`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.16):**
  - Fixes Foundry Agent Service v2 Cosmos DB data-plane RBAC by scoping the role assignment at the database level instead of a fixed list of containers ([issue #94](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/94), [PR #95](https://github.com/Azure/bicep-ptn-aiml-landing-zone/pull/95)). This allows lazily-created Foundry Agent Service v2 containers to work without authorization failures.
  - Changes the Cosmos analytical storage regional check from a hard failure to a warning when `enableCosmosAnalyticalStorage=true` targets a region where account creation can reject analytical storage ([issue #93](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/93), [PR #96](https://github.com/Azure/bicep-ptn-aiml-landing-zone/pull/96)).

### Docs

- Backfilled mandatory component version tables in historical GitHub releases and matching changelog sections so operators can see the validated component combination for each umbrella release.

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.10 |
| gpt-rag-orchestrator | v2.8.2 |
| gpt-rag-ingestion | v2.4.3 |
| infra (landing zone) | v2.0.16 |

- Ran `azd provision --no-prompt` and `azd deploy --no-prompt` in a fresh Standard-mode validation environment.
- Confirmed the landing-zone [`#94`](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/94) fix by completing provision and deploy with the v2.0.16 infrastructure pin.
- Confirmed the deployed frontend, ingestion, and orchestrator Container Apps responded on their HTTPS ingress endpoints.

## [v2.8.3] - 2026-06-10

### Fixed
- **Foundry Agent Service v2 create-once regression on `single_agent_rag` (issue [#484](https://github.com/Azure/GPT-RAG/issues/484)):** Bumps `gpt-rag-orchestrator` from `v2.8.1` to `v2.8.2`, which restores the migration to declarative/versioned Foundry prompt agents (`AIProjectClient.agents.create_version()` with `PromptAgentDefinition`). The fix coexists with the conversation-scoped retrieval introduced in v2.8.2, so `single_agent_rag` and `maf_agent_service` now reuse definition-fingerprinted prompt agents end-to-end without regressing per-conversation document upload retrieval.

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.10 |
| gpt-rag-orchestrator | v2.8.2 |
| gpt-rag-ingestion | v2.4.3 |
| infra (landing zone) | v2.0.14 |

Validated by re-running the orchestrator suite (166 tests passed locally) and confirming the `single_agent_rag` agent path on a deployed Azure validation environment using the published `v2.8.2` orchestrator image.

## [v2.8.2] - 2026-06-04

### Fixed
- **Uploaded documents now work end-to-end in authenticated chat (issue #478):** GPT-RAG now pins updated UI, orchestrator, and ingestion components that preserve the uploader identity during ingestion and propagate the active conversation id during retrieval. This lets uploaded files be indexed with the correct ACL metadata and retrieved by the `single_agent_rag` strategy in the same chat conversation.

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.10 |
| gpt-rag-orchestrator | v2.8.1 |
| gpt-rag-ingestion | v2.4.3 |
| infra (landing zone) | v2.0.14 |

Validated the component pins and manifest update, then confirmed the document upload flow in a deployed Azure validation environment: authenticated upload is available in the UI, ingestion returns indexed chunks without warnings, and uploaded content is available to chat retrieval for the active conversation.

## [v2.8.1] - 2026-06-04

### Changed
- **Landing zone submodule bumped to `v2.0.14` and Dapr declared explicitly for GPT-RAG Container Apps.** `manifest.json` `ailz_tag`, `.gitmodules` `branch`, and the recorded `infra/` submodule gitlink now consume the upstream Dapr opt-in change from [Azure/bicep-ptn-aiml-landing-zone#86](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/86). Because GPT-RAG uses Dapr for inter-container service invocation, `main.parameters.json` now sets `dapr.enabled=true` for the orchestrator, frontend, and data ingestion Container Apps, preserving the current runtime behavior while allowing the landing zone default to remain Dapr-disabled for external apps.

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.9 |
| gpt-rag-orchestrator | v2.8.0 |
| gpt-rag-ingestion | v2.4.2 |
| infra (landing zone) | v2.0.14 |
Validated the updated parameters and landing zone integration with JSON parsing, `az bicep build --file infra\main.bicep`, and `azd provision --preview --no-prompt` in a validation environment, region `eastus2`. Confirmed `main.parameters.json` sets `dapr.enabled=true` for `orchestrator`, `frontend`, and `dataingest`.
Validated the updated parameters and landing zone integration with JSON parsing, `az bicep build --file infra\main.bicep`, and `azd provision --preview --no-prompt` in a validation environment, region `eastus2`. Confirmed `main.parameters.json` sets `dapr.enabled=true` for `orchestrator`, `frontend`, and `dataingest`.

## [v2.8.0] - 2026-06-02

### Changed
- **Orchestrator bumped to `v2.8.0` for Foundry Agent Service v2 reusable agents.** The `single_agent_rag` and `maf_agent_service` strategies now use declarative/versioned Foundry prompt agents through `AIProjectClient.agents.create_version()` and `PromptAgentDefinition`, creating a reusable agent once per deterministic definition fingerprint and reusing it on subsequent requests. This removes the old ephemeral per-request Agent Service creation pattern and fixes the per-run `reasoning` payload rejection by baking reasoning effort into the prompt-agent definition. Implements [Azure/GPT-RAG#477](https://github.com/Azure/GPT-RAG/issues/477).
- **Landing zone submodule bumped to `v2.0.13`.** `manifest.json` `ailz_tag`, `.gitmodules` `branch`, and the recorded `infra/` submodule gitlink now consume the Foundry Agent Service v2 Cosmos RBAC fix. The AI Foundry project managed identity receives data-plane access to the capability-host `agent-definitions-v1` and `run-state-v1` containers required by declarative/versioned agents, so fresh deployments do not require manual Cosmos role assignments.

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.9 |
| gpt-rag-orchestrator | v2.8.0 |
| gpt-rag-ingestion | v2.4.2 |
| infra (landing zone) | v2.0.13 |

End-to-end validated on Azure in a validation environment, region `swedencentral`, with `AGENT_STRATEGY=single_agent_rag`. The orchestrator image built from commit `b0b9ae1` was deployed to Container Apps revision `ca-m53sdv7aincme-orchestrator--0000002` and received 100% traffic. Azure logs confirmed the new Foundry path: `Prompt agent 'gptrag-single-agent-rag-b622680c09' not found; creating once via create_version`, then `Created prompt agent ... (version=1)`, followed by request-time `Index Empty Check Result: False`, `Routing to Azure AI Agents SDK`, and `Streaming from Foundry prompt agent (Responses)`. Two live `/orchestrator` POST requests returned HTTP 200 with no `invalid_payload` run-time reasoning error and no Cosmos DB 403.

## [v2.7.14] - 2026-06-01

### Changed
- **Landing zone submodule bumped to `v2.0.12`.** `manifest.json` `ailz_tag`, `.gitmodules` `branch`, and the recorded `infra/` submodule gitlink were updated to consume the upstream Windows jumpbox CSE timeout fix for Zero Trust deployments ([Azure/bicep-ptn-aiml-landing-zone#82](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/82)) plus the Windows PowerShell 5.1 parser, Git clone watchdog, and non-interactive `azd init` hotfixes discovered during GPT-RAG validation. The landing zone now self-limits `install.ps1` under the platform's fixed 90-minute Custom Script Extension window: Chocolatey installs are capped with `--execution-timeout=600`, downloads and `azd` calls are bounded, optional bootstrap steps are skipped when the wall-clock budget is low, win-acme staging is non-fatal, component clone/update loops run through the bounded watchdog path, and `AZD_SKIP_FIRST_RUN=true` prevents azd first-run tooling prompts from blocking the jumpbox CSE. No GPT-RAG parameter changes are required; this release only advances the pinned landing zone so new GPT-RAG deployments fetch the fixed bootstrap script.

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.9 |
| gpt-rag-orchestrator | v2.6.11 |
| gpt-rag-ingestion | v2.4.2 |
| infra (landing zone) | v2.0.12 |

End-to-end validated on Azure in two complementary topologies. The Zero-Trust path (a validation environment, `francecentral`, `NETWORK_ISOLATION=true`, `DEPLOY_JUMPBOX=true`) confirmed the v2.0.12 fix-set on its target surface: `az bicep build --file .\infra\main.bicep` succeeded with only pre-existing warnings, and `azd provision --no-prompt` completed with the Windows jumpbox Custom Script Extension running the bounded `install.ps1` from landing zone `v2.0.12` (no 90-minute CSE timeout, no PowerShell 5.1 parser error, no Git clone watchdog false-fail, no azd first-run prompt block) - exercising the entire landing-zone-side fix-set targeted by this bump. The standard path (a validation environment, `swedencentral`, `NETWORK_ISOLATION=false`) then covered the full GPT-RAG flow end-to-end: `azd provision --no-prompt` completed in 28m59s (preflight 0 fail / 3 warn, all resources Succeeded including AI Foundry, capability host, model deployments, AI Search, knowledge sources and knowledge bases) and `azd deploy --no-prompt` built each component image via ACR remote build and updated all three Container Apps to revision `0000001`. The Container Apps `ca-oubo4ovyeuhjo-frontend`, `ca-oubo4ovyeuhjo-orchestrator`, and `ca-oubo4ovyeuhjo-dataingest` all reported `runningStatus=Running` / `provisioningState=Succeeded` with 1 replica, and HTTP smoke checks returned 200 for the frontend root and dataingest root (the orchestrator returned 404 at `/` because it has no root route; the service is live).

## [v2.7.13] - 2026-05-31

### Changed
- **Landing zone submodule bumped to `v2.0.8`.** `manifest.json` `ailz_tag` and `.gitmodules` `branch` updated. The bump rolls up four upstream releases:
  - v2.0.5 added `acrTaskConfig` so consumers can opt into ACR Tasks remote builds at provision time, and added `packages.microsoft.com` to the default ACR Tasks OS package allow-list ([Azure/bicep-ptn-aiml-landing-zone#68](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/68)).
  - v2.0.6 flipped `deployVmKeyVault` default from `true` to `false` (the parameter never actually gated a resource - only the `DEPLOY_VM_KEY_VAULT` azd output, which is preserved for backward compatibility).
  - v2.0.7 ([Azure/bicep-ptn-aiml-landing-zone#78](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/78)) added a `dependsOn` between Container Apps and `firewallPolicyDefaultRuleCollectionGroup` as defence-in-depth so the placeholder MCR pull cannot race the firewall's `AllowMicrosoftContainerRegistry` rule.
  - v2.0.8 ([Azure/bicep-ptn-aiml-landing-zone#80](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/80) / [#81](https://github.com/Azure/bicep-ptn-aiml-landing-zone/pull/81)) is the actual ZTA fix: Azure Firewall rejects `ApplicationRule.targetFqdns: []` at the ARM request-validation layer with `BadRequest: "The request is invalid."`, so the whole `DefaultRuleCollectionGroup` failed in ~0.3s and the firewall stayed empty whenever an optional feature was disabled. With the GPT-RAG default `DEPLOY_ACR_TASK_AGENT_POOL=false`, three rules (`AllowAcrTasks`, `AllowAcrTaskDevRuntimes`, `AllowAcrTaskOsPackages`) shipped with empty targets, which blocked every ZTA `azd provision` on v2.0.4-v2.0.7. v2.0.8 wraps the rule list in `filter(..., r => !empty(r.targetFqdns))` so empty rules are omitted from the ARM payload. The downstream symptom - Container Apps failing to pull `mcr.microsoft.com/dotnet/samples:aspnetapp-9.0` because the `aca-environment-subnet` UDR forces egress through a firewall with zero rules - is fully resolved by this fix.
  No GPT-RAG parameters change; this is a passthrough bump that picks up the upstream fixes and unblocks ZTA deployments.

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.9 |
| gpt-rag-orchestrator | v2.6.11 |
| gpt-rag-ingestion | v2.4.2 |
| infra (landing zone) | v2.0.8 |

End-to-end validated on Azure with the Zero-Trust topology (`NETWORK_ISOLATION=true`).

## [v2.7.12] - 2026-05-29

### Changed
- **Landing zone submodule bumped to `v2.0.4`.** `manifest.json` `ailz_tag` and `.gitmodules` `branch` updated. v2.0.3 extended `infra/scripts/Invoke-PreflightChecks.ps1` with regional readiness checks (subscription drift, provider/location, AI Search & Cosmos capacity warnings, jumpbox VM SKU, OpenAI model quota) - all driven by `main.parameters.json`, so they are now available to every consumer of the landing zone. v2.0.4 is a same-day hotfix on top of v2.0.3 ([Azure/bicep-ptn-aiml-landing-zone#74](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/74) / [#75](https://github.com/Azure/bicep-ptn-aiml-landing-zone/pull/75)) for a PowerShell parser regression in the new regional block: `ConvertTo-Bool (if (...) { ... } else { $true })` is rejected by pwsh with `The term 'if' is not recognized` because `if` is not a valid expression inside `(...)` when passed as a command argument; the fix wraps each conditional with the subexpression operator `$(if ...)`. Without v2.0.4 every `azd provision` consuming v2.0.3 aborts immediately after the preflight banner.

### Removed
- **`scripts/Invoke-GptRagRegionalPreflight.ps1` deleted; invocation removed from `scripts/preProvision.{ps1,sh}`.** Every check the GPT-RAG-specific preflight performed (region match, jumpbox VM SKU, provider/location support for AI Search/Cosmos/Container Apps/AI Foundry, transient capacity warnings, OpenAI model quota) is now performed by the landing-zone preflight in v2.0.3+. The legacy `GPT_RAG_REGIONAL_PREFLIGHT_SKIP` env var is no longer recognized - use `PREFLIGHT_SKIP=true` to bypass everything, or `LZ_PREFLIGHT_REGIONAL_SKIP=true` to bypass only the regional block while keeping parameter/topology/CIDR/BYO checks. Closes the duplication tracked in [Azure/bicep-ptn-aiml-landing-zone#72](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/72).

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.9 |
| gpt-rag-orchestrator | v2.6.11 |
| gpt-rag-ingestion | v2.4.2 |
| gpt-rag-mcp | v0.3.8 |
| infra (landing zone) | v2.0.4 |

End-to-end validated in `francecentral` with `NETWORK_ISOLATION=false` (a validation environment): full `azd provision` (preflight emitted the regional readiness block from the landing zone v2.0.4 without the v2.0.3 parser error - 3 transient capacity warnings, 0 failures; provisioning completed in 27m05s) + `azd deploy` succeeded. Health endpoints returned HTTP 200: frontend `/`, orchestrator `/docs`, ingestion `/readyz`, and ingestion `/api/version`. Initial run in `swedencentral` proved the preflight fix worked (the script ran past the previously-failing line 950) but provisioning aborted at AI Foundry model deployment due to a regional `text-embedding-3-large` quota exhaustion (independent of this release); the validation was therefore completed in `francecentral`.


## [v2.7.11] - 2026-05-29

### Changed
- **Regional preflight: warn about Azure AI Search transient capacity.** `scripts/Invoke-GptRagRegionalPreflight.ps1` now adds a Warn next to the existing PASS for Azure AI Search, mirroring the Cosmos DB pattern. The PASS still confirms regional provider/SKU support, but operators are now explicitly told that pre-create capacity (`InsufficientResourcesAvailable`) is not exposed by a reliable quota API and provisioning may still fail on transient regional saturation. Closes [#470](https://github.com/Azure/GPT-RAG/issues/470).

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.9 |
| gpt-rag-orchestrator | v2.6.11 |
| gpt-rag-ingestion | v2.4.2 |
| gpt-rag-mcp | v0.3.8 |
| infra (landing zone) | v2.0.2 |



All notable changes to this project will be documented in this file.  
This format follows [Keep a Changelog](https://keepachangelog.com/) and adheres to [Semantic Versioning](https://semver.org/).

## [v2.7.10] - 2026-05-28

### Fixed
- **Ingestion Managed Identity client ID fallback in Azure Container Apps:** bumped `gpt-rag-ingestion` to [v2.4.2](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.2), preserving App Configuration precedence for `AZURE_CLIENT_ID` while falling back to the Container Apps-injected environment variable when the key is absent. This completes the fix for `/ingest-documents` returning HTTP 200 with `indexedChunks: 0` due to user-assigned Managed Identity token acquisition failures.

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.9 |
| gpt-rag-orchestrator | v2.6.11 |
| gpt-rag-ingestion | v2.4.2 |
| gpt-rag-mcp | v0.3.8 |
| infra (landing zone) | v2.0.2 |

## [v2.7.9] - 2026-05-28

### Fixed
- **Ingestion Managed Identity authentication in Azure Container Apps:** bumped `gpt-rag-ingestion` to [v2.4.1](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.1), updating `azure-identity` so `/ingest-documents` can authenticate sync Content Understanding, Blob Storage, and embedding paths with user-assigned Managed Identity.

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.9 |
| gpt-rag-orchestrator | v2.6.11 |
| gpt-rag-ingestion | v2.4.1 |
| gpt-rag-mcp | v0.3.8 |
| infra (landing zone) | v2.0.2 |

## [v2.7.8] - 2026-05-28

### Changed
- **Grouped dependency refresh across GPT-RAG components:** updated the service manifest to consume `gpt-rag-ui` [v2.3.9](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.9), `gpt-rag-orchestrator` [v2.6.11](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.6.11), and `gpt-rag-ingestion` [v2.4.0](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.4.0). `gpt-rag-mcp` [v0.3.8](https://github.com/Azure/gpt-rag-mcp/releases/tag/v0.3.8) was released in the same dependency refresh batch; the MCP server remains an optional component and is not listed in the default deployment manifest.

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.9 |
| gpt-rag-orchestrator | v2.6.11 |
| gpt-rag-ingestion | v2.4.0 |
| gpt-rag-mcp | v0.3.8 |
| infra (landing zone) | v2.0.2 |

## [v2.7.7] - 2026-05-27

### Changed
- **Grouped dependency refresh across GPT-RAG components:** bumped `requests` in the core configuration tooling to 2.33.0 and updated the service manifest to consume `gpt-rag-ui` [v2.3.8](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.8), `gpt-rag-orchestrator` [v2.6.10](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.6.10), and `gpt-rag-ingestion` [v2.3.8](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.3.8). `gpt-rag-mcp` [v0.3.7](https://github.com/Azure/gpt-rag-mcp/releases/tag/v0.3.7) was released in the same dependency refresh batch; the MCP server remains an optional component and is not listed in the default deployment manifest.

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.8 |
| gpt-rag-orchestrator | v2.6.10 |
| gpt-rag-ingestion | v2.3.8 |
| gpt-rag-mcp | v0.3.7 |
| infra (landing zone) | v2.0.2 |

## [v2.7.6] - 2026-05-27

### Changed
- **Bumped `gpt-rag-orchestrator` to [v2.6.9](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.6.9)** to consume long conversation history compaction and retrieval-needed triage improvements.

### Fixed
- **Long conversations no longer grow persisted Cosmos DB documents indefinitely:** the orchestrator now compacts persisted conversation documents by serialized size and message count while keeping recent messages and question metadata. It also skips unnecessary Azure AI Search calls for no-retrieval follow-ups such as formatting, translation, summarization, or rephrasing. Fixes [Azure/GPT-RAG#448](https://github.com/Azure/GPT-RAG/issues/448).

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.7 |
| gpt-rag-orchestrator | v2.6.9 |
| gpt-rag-ingestion | v2.3.7 |
| infra (landing zone) | v2.0.2 |
## [v2.7.5] - 2026-05-26

### Added
- **Existing-platform deployment parameters surfaced:** `main.parameters.json` now passes through AI Landing Zone v2.0.2 settings for BYO Private DNS zones, shared observability, hub integration, existing jumpbox/Bastion/NAT resources, Private Endpoint placement, ACR Task agent pools, speech resources, and policy-managed private DNS. This allows GPT-RAG deployments to integrate with existing enterprise landing zones without editing the infra submodule. Fixes [Azure/GPT-RAG#452](https://github.com/Azure/GPT-RAG/issues/452) and [Azure/GPT-RAG#453](https://github.com/Azure/GPT-RAG/issues/453).

### Changed
- **Bumped component releases for NL2SQL and conversation rename fixes:** `gpt-rag-ui` to [v2.3.7](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.7) and `gpt-rag-orchestrator` to [v2.6.8](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.6.8).

### Fixed
- **NL2SQL no longer depends on Semantic Kernel Agent Service creation:** the orchestrator release now uses Microsoft Agent Framework with direct model calls and local NL2SQL tool execution, eliminating the `AgentsOperations.create_agent` failure and reducing per-request setup latency. Fixes [Azure/GPT-RAG#461](https://github.com/Azure/GPT-RAG/issues/461) and [Azure/GPT-RAG#462](https://github.com/Azure/GPT-RAG/issues/462).
- **Conversation rename persists after refresh:** the UI release now sends Chainlit rename events to the orchestrator conversation update API. Fixes [Azure/GPT-RAG#435](https://github.com/Azure/GPT-RAG/issues/435).

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.7 |
| gpt-rag-orchestrator | v2.6.8 |
| gpt-rag-ingestion | v2.3.7 |
| infra (landing zone) | v2.0.2 |
## [v2.7.4] - 2026-05-26

### Changed
- **Bumped component releases for deploy image verification**: `gpt-rag-ui` to [v2.3.6](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.6), `gpt-rag-orchestrator` to [v2.6.7](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.6.7), and `gpt-rag-ingestion` to [v2.3.7](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.3.7).

### Fixed
- **Docker-free deploy no longer fails on revision restart race or Azure CLI warning output**: service deploy scripts now treat `az containerapp update --image` as the revision rollout, verify the configured image instead of immediately restarting the latest revision, and filter warning/progress output before consuming Azure CLI TSV values. Fixes [Azure/GPT-RAG#449](https://github.com/Azure/GPT-RAG/issues/449).

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.6 |
| gpt-rag-orchestrator | v2.6.7 |
| gpt-rag-ingestion | v2.3.7 |
| infra (landing zone) | v2.0.2 |
## [v2.7.3] - 2026-05-25

### Changed
- **Bumped component releases for Docker-free deploy reliability**: `gpt-rag-ui` to [v2.3.4](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.4), `gpt-rag-orchestrator` to [v2.6.5](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.6.5), and `gpt-rag-ingestion` to [v2.3.5](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.3.5).

### Fixed
- **Component deploy no longer requires local Docker Desktop**: service deploy scripts now select ACR remote builds before probing Docker, support explicit `BUILD_MODE=acr-task`/`USE_DOCKER=false`, configure Container App registry identity, and restart the latest revision after image updates. Fixes [Azure/GPT-RAG#449](https://github.com/Azure/GPT-RAG/issues/449).

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.4 |
| gpt-rag-orchestrator | v2.6.5 |
| gpt-rag-ingestion | v2.3.5 |
| infra (landing zone) | v2.0.2 |
## [v2.7.2] - 2026-05-25

### Changed
- **Bumped `gpt-rag-orchestrator` to [v2.6.4](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.6.4)** to consume the Agent Service startup warmup fix for default basic deployments.

### Fixed
- **Default `maf_lite` startup no longer creates Agent Service agents**: the orchestrator startup warmup is now strategy-aware, skips Agent Service entirely for the default `maf_lite` strategy, limits reusable startup agent creation to `single_agent_rag`, and reuses any existing `gpt-rag-agent-v2` by name before creating one. Fixes [Azure/GPT-RAG#456](https://github.com/Azure/GPT-RAG/issues/456).

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.3 |
| gpt-rag-orchestrator | v2.6.4 |
| gpt-rag-ingestion | v2.3.4 |
| infra (landing zone) | v2.0.2 |
## [v2.7.1] - 2026-05-25

### Changed
- **Bumped `gpt-rag-ui` to [v2.3.3](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.3)** to pick up the WSL/Linux Bash script line-ending fix for component deployment.

### Fixed
- **WSL/Linux UI component deploy failure**: `gpt-rag-ui` now ships repository line-ending attributes that keep `scripts/deploy.sh` and `scripts/preProvision.sh` checked out with LF endings, preventing `$'\r': command not found` and `set: pipefail` failures during `azd deploy`. Fixes [Azure/GPT-RAG#451](https://github.com/Azure/GPT-RAG/issues/451).

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.3 |
| gpt-rag-orchestrator | v2.6.3 |
| gpt-rag-ingestion | v2.3.4 |
| infra (landing zone) | v2.0.2 |
## [v2.7.0] - 2026-05-19

> v2.7.0 bumps the **AI Landing Zone** Bicep module submodule from **v1.0.7 → v2.0.2**. This is a major-version submodule upgrade that brings several new capabilities (IP allow-lists, BYO Private DNS zones, BYO Log Analytics + App Insights, hub-and-spoke composability, deployment-mode preset, pre-flight validation hook) and a handful of bug fixes (most notably the `${VAR=null}` string-default bug that affected route-table wiring, the hardcoded service-flag defaults that ignored `azd env set` overrides, and two v2.0.0-only template-validation regressions in the AI Foundry account Private Endpoint emission and the AI Foundry-bundled sub-modules' PE subnet propagation - fixed in v2.0.1 and v2.0.2 respectively). Default behavior is **unchanged** for existing GPT-RAG operators - all new landing-zone capabilities are opt-in. See the [v2-migration guide](https://github.com/Azure/bicep-ptn-aiml-landing-zone/blob/v2.0.0/docs/v2-migration.md) and the [parameterization reference](https://azure.github.io/AI-Landing-Zones/bicep/parameterization) for details.

### Changed
- **AI Landing Zone Bicep submodule bumped to [v2.0.2](https://github.com/Azure/bicep-ptn-aiml-landing-zone/releases/tag/v2.0.2) plus the merged ACR Tasks egress hotfix [PR #69](https://github.com/Azure/bicep-ptn-aiml-landing-zone/pull/69)** (`ailz_tag` in `manifest.json` remains `v2.0.2` for the jumpbox bootstrap script URL). v2.0.2 is a hotfix on top of v2.0.0 that resolves two ARM template-validation errors encountered while validating this very release: (a) a duplicate-name in the AI Foundry account Private Endpoint emission (v2.0.1, [PR #60](https://github.com/Azure/bicep-ptn-aiml-landing-zone/pull/60)), and (b) an unconditional `varPeSubnetId` propagation that caused the AI Foundry-bundled Cosmos DB, Key Vault, AI Search, and Storage Account modules to emit invalid private endpoint iterators under `_networkIsolation=false` (v2.0.2, [issue #63](https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/63) / [PR #64](https://github.com/Azure/bicep-ptn-aiml-landing-zone/pull/64)). PR #69 adds `packages.microsoft.com` to the network-isolated ACR Task build allow-list and adds `additionalAcrTaskBuildFqdns` for future solution-specific build dependencies. No GPT-RAG-component bumps in this release (`gpt-rag-ui` v2.3.2, `gpt-rag-orchestrator` v2.6.3, `gpt-rag-ingestion` v2.3.4 carry over from v2.6.7).
- **`scripts/preProvision.{ps1,sh}` now fail fast on GPT-RAG regional readiness before ARM deployment starts.** The new GPT-RAG preflight validates the selected region, jumpbox VM SKU restrictions, provider/location support for AI Search, Cosmos DB, Container Apps, and AI Foundry/Cognitive Services, plus Azure OpenAI model quota for the exact deployments in `modelDeploymentList`. If model quota is insufficient, it suggests candidate regions when possible. It is intentionally explicit that transient service-capacity failures (for example Cosmos DB high-demand `ServiceUnavailable`) are not exposed by a reliable pre-create quota API. Bypass only these checks with `GPT_RAG_REGIONAL_PREFLIGHT_SKIP=true`; bypass all preflight hooks with `PREFLIGHT_SKIP=true`.
- **`scripts/preProvision.{ps1,sh}` continue to invoke the landing-zone preflight check** (`infra/scripts/Invoke-PreflightChecks.ps1`). This catches parameter-contradiction errors (BYO ID mismatches, malformed CIDR entries, subnet prefixes outside the VNet, mutually-exclusive hub-integration flags, etc.) *before* `azd provision` reaches Azure Resource Manager. Bypass with `PREFLIGHT_SKIP=true` (CI/offline). The shell version now fails clearly if `pwsh` is missing for the GPT-RAG regional preflight instead of silently skipping regional checks.
- **`scripts/preDeploy.{ps1,sh}` now key Network Isolation behavior only from `NETWORK_ISOLATION`**. Workstation runs should stop after `azd provision`; when `NETWORK_ISOLATION=true`, `azd deploy` must be run from the jumpbox/VNet with `RUN_FROM_JUMPBOX=true`, and the legacy `AZURE_ZERO_TRUST` deploy prompt is no longer used.
- **`scripts/postProvision.{ps1,sh}` now honor `AZURE_SKIP_NETWORK_ISOLATION_WARNING=true` for automated network-isolated workstation provisions.** The local hook skips data-plane work without prompting, while the real data-plane setup still requires rerunning from the jumpbox/VNet with `RUN_FROM_JUMPBOX=true`.

### Added
- **`main.parameters.json` surfaces three v2.0.0 parameters as substitutable env vars** so operators can opt into them via `azd env set`:
  - `allowedIpRanges` (default `[]`) - array of CIDRs uniformly applied as an IP allow-list on Storage, Key Vault, App Configuration, Container Registry, Cosmos DB, AI Search, and the AI Foundry storage account. Works orthogonally to `networkIsolation`. **Note**: `azd` env substitution emits strings, so this parameter accepts an array literal - edit `main.parameters.json` directly to seed it, or use a parameter overlay file.
  - `deploymentMode` (default `standalone`) - `'standalone'` or `'ailz-integrated'`. Advisory in v2.0.0 (surfaced as a deployment tag `deploymentMode=<value>`); future v2.x releases may use it to drive defaults. `azd env set DEPLOYMENT_MODE ailz-integrated` switches it.
  - `enableCosmosAnalyticalStorage` (default `false`) - surfaced explicitly because Azure does not permit toggling this flag on an existing Cosmos DB account (it only takes effect at account creation), and several region / subscription combinations refuse the `true` setting at provision time. Default `false` matches the typical GPT-RAG topology (no Synapse Link / Fabric Mirroring consumer). Toggle via `azd env set ENABLE_COSMOS_ANALYTICAL_STORAGE true` *before* the first `azd provision`.
- **`vmSize` is now env-substitutable** in `main.parameters.json`: `${VM_SIZE=Standard_D2s_v3}`. Default lowered from the previously-hardcoded `Standard_D8s_v5` (8 vCPU / 32 GiB) to `Standard_D2s_v3` (2 vCPU / 8 GiB) for the jumpbox VM. The smaller D2s_v3 SKU is broadly available across Azure regions (the v5 D-family is restricted in several regions including `eastus2`), and the 2 vCPU / 8 GiB sizing is more than sufficient for the jumpbox admin/bootstrap role. Operators with heavier use cases can override with `azd env set VM_SIZE Standard_D8s_v5` (or any other size) before `azd provision`.

### Fixed (via the submodule upgrade)
- **`${VAR=null}` literal-string bug for nullable-string parameters** (landing-zone fix): `azd` passed the literal string `"null"` into `string?` parameters when the env var was unset, which broke every `!empty(...)` guard downstream. Symptom: subnet deployments failed with `LinkedInvalidPropertyId: Property id 'null' at path 'properties.routeTable.id' is invalid`. v2.0.0 changed `${VAR=null}` → `${VAR=}` (empty-string default) for every nullable-string parameter, so route-table wiring, BYO existing IDs, and the App Insights connection string now correctly evaluate as empty.
- **Hardcoded service flags now respect `azd env set`** (landing-zone fix): `deploySearchService`, `deployStorageAccount`, `deployKeyVault`, `deployLogAnalytics`, `deployMcp`, `deployGroundingWithBing`, `deploySoftware`, `deployPostgres`, `greenFieldDeployment`, and `speechServiceSku` are no longer pinned at compile time in the landing-zone parameter file. v2.0.0 switched them to `${ENV=default}` substitution so `azd env set DEPLOY_SEARCH_SERVICE false` (and similar) actually take effect. The umbrella's parameter file passes them through.
- **Cosmos `enableAnalyticalStorage=true` provisioning failures**: the landing-zone now defaults `enableAnalyticalStorage` to `false` and gates it on the new `enableCosmosAnalyticalStorage` parameter. v2.6.x deployments occasionally failed with role-assignment / region-permission errors when this was implicitly enabled - those failures stop in v2.7.0.
- **Jumpbox `SkuNotAvailable` failures in regions without v5 D-family** (umbrella-level fix, see `vmSize` entry under **Added**): `Standard_D8s_v5` was hardcoded in the umbrella `main.parameters.json` since the project's inception; in regions where Azure restricts the `Dsv5` family (notably `eastus2` as of release time), `azd provision` aborted at the AI Search service's internal VM-SKU preflight check with `SkuNotAvailable`. The new env-substitutable default (`Standard_D2s_v3`) provisions reliably across all GPT-RAG-supported regions.
- **PowerShell hooks on Windows jumpbox**: `scripts/preDeploy.ps1` and `scripts/postProvision.ps1` are now stored with a UTF-8 BOM so Windows PowerShell 5.1 reads the existing Unicode status messages correctly instead of parsing corrupted script text. `postProvision.ps1` also suppresses the Azure CLI dynamic-install warning without aborting when `$ErrorActionPreference='Stop'`.

### Opt-in landing-zone v2.0.0 features (not surfaced as umbrella env vars, but reachable via `azd env set <PARAM_NAME>` or by editing the umbrella `main.parameters.json` directly)
- 15 `existingPrivateDnsZone<Service>ResourceId` parameters for BYO Private DNS zones (ALZ-integrated hub-spoke topologies).
- `existingLogAnalyticsWorkspaceResourceId`, `existingApplicationInsightsResourceId`, `existingApplicationInsightsConnectionString` for observability reuse against a hub-managed workspace.
- `hubIntegrationHubVnetResourceId`, `hubIntegrationEgressNextHopIp`, `hubIntegrationExistingRouteTableResourceId`, `hubIntegrationCreateHubPeering`, `hubIntegrationPeeringAllowGatewayTransit`, `hubIntegrationPeeringUseRemoteGateways` for hub-and-spoke composability.
- `deployJumpbox`, `deployBastion`, `deployNatGateway` + matching `existing*ResourceId` BYO variants. The legacy `deployVM` parameter remains as a **deprecated** umbrella that gates all three when left unset - existing GPT-RAG deployments continue to work unchanged.
- `dnsZoneLinkSuffix` for unique VNet-link names when multiple spokes share the same hub DNS zones.

### Validation
The following component versions were validated together for this release:

| Component | Version |
| --- | --- |
| gpt-rag-ui | v2.3.2 |
| gpt-rag-orchestrator | v2.6.3 |
| gpt-rag-ingestion | v2.3.4 |
| infra (landing zone) | v2.0.2 |

End-to-end validation in `swedencentral` (subscription `mcaps-paulolacerda`), basic deployment (`NETWORK_ISOLATION=false`, `deploymentMode=standalone`):

| Aspect | Result |
| --- | --- |
| Preflight hook (`Invoke-PreflightChecks.ps1`) executes from `preProvision.{ps1,sh}` | ✅ |
| `azd provision` succeeds (~9m) | ✅ |
| All infra resources provisioned (VNet, Cosmos, Key Vault, ACR, AI Search, AI Foundry, Container Apps Environment, Container Apps) | ✅ |
| `azd deploy` succeeds (~14m, 3 container apps Running) | ✅ |
| Frontend smoke test (HTTP 200) | ✅ |
| New params (`allowedIpRanges`, `deploymentMode`, `enableCosmosAnalyticalStorage`) honored | ✅ |
| Backward compatibility - existing `azure.env` deploys with no changes | ✅ |

Network-isolated deployment (`NETWORK_ISOLATION=true`) reuses the same Bicep submodule and AILZ v2.0.2 fixes; operators with existing isolated deployments can upgrade in place. Hub-and-spoke topology (a separate v2.0.0 capability) is **not** exercised by this release - operators integrating with an existing ALZ hub should follow the [hub-spoke runbook](https://github.com/Azure/bicep-ptn-aiml-landing-zone/blob/v2.0.0/docs/runbook-hub-spoke.md).

## [v2.6.7] - 2026-05-19
### Added
- **Per-conversation file upload from the chat UI** ([#401](https://github.com/Azure/GPT-RAG/issues/401)): Users can now upload files directly through the GPT-RAG chat interface. Uploaded documents are persisted to the conversation-documents storage container (declared in v2.6.0) under conversations/<conversationId>/<recordId>/<filename>, chunked and indexed in Azure AI Search tagged with the per-chunk conversationId field (also declared in v2.6.0), and retrieved by the orchestrator with a conversationId eq '<cid>' or conversationId eq 'NaN' filter so retrieval mixes conversation-private documents with shared/global documents. Implemented across three coordinated component PRs:
  - gpt-rag-ingestion [v2.3.4](https://github.com/Azure/gpt-rag-ingestion/releases/tag/v2.3.4) ([#183](https://github.com/Azure/gpt-rag-ingestion/pull/183)): new POST /ingest-documents endpoint that authenticates via DATA_INGEST_APP_APIKEY, persists the original bytes, and indexes the chunks with camelCase conversationId.
  - gpt-rag-orchestrator [v2.6.3](https://github.com/Azure/gpt-rag-orchestrator/releases/tag/v2.6.3) ([#188](https://github.com/Azure/gpt-rag-orchestrator/pull/188)): conversation-scoped retrieval filter across all strategies.
  - gpt-rag-ui [v2.3.2](https://github.com/Azure/gpt-rag-ui/releases/tag/v2.3.2) ([#51](https://github.com/Azure/gpt-rag-ui/pull/51)): Chainlit spontaneous_file_upload paperclip wired to the new ingestion endpoint, surfaced only when authentication is configured.

### Changed
- Bumped gpt-rag-ui to 
2.3.2.
- Bumped gpt-rag-orchestrator to 
2.6.3.
- Bumped gpt-rag-ingestion to 
2.3.4.

## [v2.6.6] - 2026-04-20
### Added
- **Multimodal figure/image extraction for Content Understanding** ([Azure/GPT-RAG#446](https://github.com/Azure/GPT-RAG/issues/446)): When using Content Understanding as the document analysis backend (USE_DOCUMENT_INTELLIGENCE=false), the multimodal chunker now extracts figures from documents, uploads them to the documents-images blob container, generates captions using a vision-capable model, and populates 
elatedImages, imageCaptions, and captionVector fields in the search index ΓÇö achieving full multimodal parity with the Document Intelligence path. Supports PDF (PyMuPDF page rendering with bounding-box crop), DOCX (word/media/ ZIP extraction), and PPTX (ppt/media/ ZIP extraction). The ContentUnderstandingClient now parses and returns figure and page metadata from the API response instead of discarding it. New dependencies: PyMuPDF, python-docx, python-pptx.

### Changed
- Bumped gpt-rag-ingestion to 
2.3.3.

### Tested Service Versions

| Component | Version |
|---|---|
| gpt-rag-ui | v2.3.1 |
| gpt-rag-orchestrator | v2.6.2 |
| gpt-rag-ingestion | v2.3.3 |
| infra (landing zone) | v1.0.7 |

## [v2.6.5] - 2026-04-18
### Fixed
- **OpenTelemetry version pinning** (orchestrator): Pinned `azure-monitor-opentelemetry==1.8.7`, `azure-monitor-opentelemetry-exporter==1.0.0b49`, `opentelemetry-instrumentation-httpx==0.61b0`, and `opentelemetry-instrumentation-fastapi==0.61b0` in `requirements.txt`. Unpinned versions caused non-deterministic Docker builds where an older exporter (referencing the removed `LogData` class) could be paired with `opentelemetry-sdk>=1.39.0`, crashing the container on startup with `ImportError: cannot import name 'LogData' from 'opentelemetry.sdk._logs'`. ([#445](https://github.com/Azure/GPT-RAG/issues/445))
- **Permission trimming header format** (orchestrator): Removed erroneous `Bearer` prefix from the `x-ms-query-source-authorization` header value in both the REST API path (`search.py`) and the SDK path (`search_context_provider.py`). Azure AI Search expects the raw OBO token without the prefix; including it caused `400 Invalid header` errors when `permissionFilterOption` was enabled on the search index. ([#447](https://github.com/Azure/GPT-RAG/issues/447))

### Changed
- Bumped `gpt-rag-orchestrator` to `v2.6.2`.

## [v2.6.4] - 2026-04-14
### Fixed
- Restored missing `parent_id` field in the RAG search index template (`config/search/search.j2`), which was accidentally removed during the v2.6.0 merge. This caused `gpt-rag-ingestion` blob storage and SharePoint indexers to fail with `Could not find a property named 'parent_id'` errors.

### Changed
- Updated `infra` submodule to [bicep-ptn-aiml-landing-zone](https://github.com/Azure/bicep-ptn-aiml-landing-zone) tag `v1.0.7`, fixing Log Analytics provisioning failure in Sweden Central caused by `forceCmkForQuery` default.

## [v2.6.3] - 2026-04-08
### Changed
- Updated `infra` submodule to [bicep-ptn-aiml-landing-zone](https://github.com/Azure/bicep-ptn-aiml-landing-zone) tag `v1.0.6`.
- Parametrized Container App CPU and memory per app entry with fallback defaults (`0.5` CPU / `1.0Gi`).
- Increased `dataingest` Container App resources to `1.0` CPU and `3.0Gi` memory.
- Increased `text-embedding-3-large` deployment capacity from `40` to `100`.
- Bumped `gpt-rag-ingestion` to `v2.3.2`.

## [v2.6.2] - 2026-04-01
### Changed
- Bumped `gpt-rag-orchestrator` to `v2.6.1`.

## [v2.6.1] - 2026-04-01
### Fixed
- Fixed Zero Trust provisioning failure caused by jumpbox Custom Script Extension using incorrect release tag. Replaced `install_script` URL field with `ailz_tag` in `manifest.json`, allowing the install script URL and release parameter to be derived from the landing zone tag.

### Changed
- Updated `infra` submodule to [bicep-ptn-aiml-landing-zone](https://github.com/Azure/bicep-ptn-aiml-landing-zone) tag `v1.0.5`.
- Bumped `gpt-rag-ui` to `v2.3.1`.
- Bumped `gpt-rag-ingestion` to `v2.2.5`.

## [v2.6.0] - 2026-03-31
### Changed
- Updated `infra` submodule to [bicep-ptn-aiml-landing-zone](https://github.com/Azure/bicep-ptn-aiml-landing-zone) tag `v1.0.4`.
- Bumped `gpt-rag-ui` to `v2.3.0`.
- Bumped `gpt-rag-orchestrator` to `v2.6.0`.
- Bumped `gpt-rag-ingestion` to `v2.2.4`.
- Added explicit `partitionKey` to all Cosmos DB container definitions, including `/principal_id` for `conversations` container.
- Added `conversation-documents` storage container.
- Added `conversationId` filterable field to search index.
- Removed standalone MCP Container App from default deployment (consolidated into orchestrator).

## [v2.5.3] - 2026-03-24
### Changed
- Updated default chat model from `gpt-5-mini` to `gpt-5-nano` (`2025-08-07`), increased deployment capacity to `100`, and set API version to `2025-12-01-preview`.
- Updated `infra` submodule to [bicep-ptn-aiml-landing-zone](https://github.com/Azure/bicep-ptn-aiml-landing-zone) tag `v1.0.3`.
- Bumped `gpt-rag-ui` to `v2.2.3`.
- Bumped `gpt-rag-orchestrator` to `v2.5.0`.
### Added
- Added repository development and release instructions (`.github/copilot-instructions.md`).

## [v2.5.2] - 2026-03-16
### Changed
- Updated pre-deployment behavior to skip cloning a component repository when it already exists locally, improving repeat deployment workflows and avoiding unnecessary clone failures. Closes [#428](https://github.com/Azure/GPT-RAG/issues/428).
### Fixed
- Made virtual environment cleanup in `scripts/postProvision.sh` non-fatal so post-provisioning continues even if cleanup cannot complete. Closes [#426](https://github.com/Azure/GPT-RAG/issues/426).

## [v2.5.1] - 2026-03-06
### Changed
- Updated `infra` submodule to external [bicep-ptn-aiml-landing-zone](https://github.com/Azure/bicep-ptn-aiml-landing-zone) tag `v1.0.1`.
- Bumped `gpt-rag-orchestrator` to `v2.4.2`.
- Bumped `gpt-rag-ui` to `v2.2.2`.
- Improved runtime performance by upgrading the Orchestrator and UI components to `v2.4.2` and `v2.2.2`, respectively.
- Bumped `gpt-rag-ingestion` to `v2.2.3`.

## [v2.5.0] - 2026-03-02
### Changed
- Migrated `infra` folder to external submodule [bicep-ptn-aiml-landing-zone](https://github.com/Azure/bicep-ptn-aiml-landing-zone) pinned to v1.0.0.

## [v2.4.2] - 2026-02-04
### Fixed
- Updated the Docker image to install Microsoft's current public signing key, fixing build failures caused by SHA-1 signature rejection in newer Debian/apt verification policies (orchestrator).
- Fixed Docker builds on ARM-based machines by explicitly setting the target platform to `linux/amd64`, preventing Azure Container Apps deployment failures.
### Changed
- Updated the Docker base image.
- Standardized on the container best practice of using a non-privileged port (`8080`) instead of a privileged port (`80`), reducing the risk of runtime/permission friction and improving stability of long-running ingestion workloads.
- Bumped `aiohttp` to `3.13.3`.

## [v2.4.1] - 2026-01-20
### Changed
- Bumped ingestion component version to include reliability improvements for large spreadsheet ingestion.


## [v2.4.0] - 2026-01-15
### Added
- Document-level security enforcement for GPT-RAG using Azure AI Search native ACL/RBAC trimming with end-user identity propagation via `x-ms-query-source-authorization`.
	Includes permission-aware indexing metadata (userIds/groupIds/rbacScope), safe-by-default behavior for requests without a valid user token, and optional elevated-read debugging support.
### Changed
- Bumped chat model to gpt-5-mini.

## [v2.3.0] – 2025-12-15
### Added
- Support for **SharePoint Lists** in the ingestion component.
- Refactored **Single Agent Strategy** to simplify citation handling. [#161]
- Simplified **MCP Strategy**. [#159]
### Changed
- Improved robustness of **Blob Storage indexing** in the ingestion pipeline.
- Enhanced **data ingestion logging** for better observability and troubleshooting.
### Tested
- Compatibility with **Azure direct models for inference** in the orchestration layer.

## [v2.2.6] – 2025-12-05
### Fixed
- Fixed Issue [#409](https://github.com/Azure/GPT-RAG/issues/409) by updating the main Bicep template to ensure the `SEARCH_CONNECTION_ID` app setting points to the correct AI Search connection ID. It was previously pointing to the AI Foundry AI Search dependency.

## [v2.2.5] – 2025-12-02
### Fixed
- Fixed Issue [#406](https://github.com/Azure/GPT-RAG/issues/406) by updating networking and private endpoint configuration to prevent the `cosmos_vnet_blocked` error in Cosmos DB private-only setups.
### Changed
- Automated the creation and registration of the Azure AI Search connection, removing the need for the previous manual workaround.

## [v2.2.4] – 2025-11-26
### Fixed
- Fixed a bug in data ingestion component where the Blob storage ingestion process was re-indexing unchanged files when AI Search index had more than 1,000 chunks. Fixed in gpt-rag-ingestion v2.0.6.
### Changed
- Small update in `scripts/postProvision.sh` to make the Container Apps API Key check more robust by always converting the `USE_CAPP_API_KEY` variable to lowercase, even when it is unset.


## [v2.2.3] – 2025-11-15
### Fixed
- Intermittent AI Foundry post provisioning setup authentication timeout by increasing `AzureCliCredential` and `ManagedIdentityCredential` process timeout to 30 seconds in `config/aifoundry/setup.py`
- Compatibility with older AZD versions by removing string interpolation syntax from capability host connection arrays in AI Foundry project module (infra/modules/ai-foundry/modules/project/main.bicep lines 229-231)
### Changed
- Suppressed BCP081 warnings for future-dated API versions (2025-01-01, 2025-04-01, 2025-05-01, 2025-06-01) in AI Foundry project module by adding #disable-next-line directives
- Improved PR and Issue templates
- Moved documentation to https://aka.ms/gpt-rag-docs
- Bumped **gpt-rag-mcp** to **v0.2.3**

## [v2.2.2] – 2025-11-09
### Changed
- Updated infra templates to create the **data** private endpoint for Azure Container Registry when in network isolation mode.
- Updated Bastion configuration to retrieve credentials from Key Vault. Users can now simply reset the `testvmuser` password to access the VM for the first time.

## [v2.2.1] – 2025-10-21
### Added
- Added more troubleshooting logs.
### Fixed
- Citations [387](https://github.com/Azure/GPT-RAG/issues/387)

## [v2.2.0] – 2025-10-16
### Added
- Bring your own VNet. [#370](https://github.com/Azure/GPT-RAG/issues/370).
- Agentic Retrieval. [#359](https://github.com/Azure/GPT-RAG/issues/359).

### Fixed
- Citation links opens up new chat windows instead of rendering files [#387](https://github.com/Azure/GPT-RAG/issues/387)
## [v2.1.2] – 2025-10-02
### Changed
- Fixed a bug in data ingestion component where the SharePoint ingestion process was unnecessarily re-indexing unchanged files.

## [v2.1.1] – 2025-09-22
### Changed
- Limit `azd` environment variables to the script process (no longer persisted to the user profile) to reduce secret exposure. Resolves [#378](https://github.com/Azure/GPT-RAG/issues/378).
- Streamline AI Search provisioning: now creates **only** the AI Search index. Previously we also created indexers, skillsets, and data sources that are no longer used and caused confusion about expected runtime behavior. Indexing is performed by the `gpt-rag-ingestion` jobs - see the ingestion docs for how to run, schedule, or troubleshoot ingest jobs. Resolves [#377](https://github.com/Azure/GPT-RAG/issues/377).

## [v2.1.0] – 2025-08-31
### Added
- **User Feedback Loop**. [#358](https://github.com/Azure/GPT-RAG/issues/358). **[Documentation](https://github.com/Azure/GPT-RAG/blob/release/2.1.0/docs/GUIDE.md#configuring-user-feedback-loop)**.

### Changed
- Standardized resource group variable as `AZURE_RESOURCE_GROUP`. [#365](https://github.com/Azure/GPT-RAG/issues/365)

## [v2.0.5] - 2025-08-26
### Fixed
- Resolved VM deployment errors when using CustomScriptExtension under network isolation.

## [v2.0.4] - 2025-08-21
### Added
- Updated orchestrator to version 2.0.3, which includes NL2SQL docs and improved settings checks.

## [v2.0.3] - 2025-08-19
### Fixed
- Resolved issue with using Azure Container Apps under a private endpoint in AI Search as a custom web skill.
### Added 
- Blob Storage Data Source Ingestion.
- NL2SQL Metadata Ingestion from Blob Storage.

## [v2.0.2] - 2025-08-08
### Changed
- Updated deployment documentation.

## [v2.0.1]
### Changed
- Updated deployment documentation.

### Fixed
- Resolved deployment issues introduced in v2.0.0.

## [v2.0.0] - 2025-07-15
### Changed
- Major architecture refactor to support the vNext architecture.