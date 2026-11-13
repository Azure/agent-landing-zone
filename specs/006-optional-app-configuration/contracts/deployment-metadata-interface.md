# Deployment Metadata Interface

Both native providers, the shared loader and migrated setup consumers implement
this interface. It is not the runtime platform outputs contract.

## Wire contract and producer obligations

Both providers emit:

```text
DEPLOYMENT_METADATA
```

Its value conforms to the production
[deployment-metadata-v1.schema.json](../../../contracts/deployment-metadata-v1.schema.json).
The dedicated output exists in hosted, classic, custom and infrastructure-only
compositions. It is not a member of `HOSTED_AGENT_DEPLOYMENT`.
The accepted migration in
[ADR-0041](../../../docs/adr/ADR-0041-provider-owned-deployment-metadata.md)
replaces only `OBSERVABILITY_MIXED_WORKSPACES_ALLOWED`, preserving its typed
policy/checks, all other root outputs, hosted handoffs and runtime v1.
The manifest, component pins and runtime/sample implementations are unchanged.

Use evaluated provider resource outputs and approved resource-ID expressions
bound to declared parents. Do not copy model defaults or infer resources by
runtime naming conventions. Preserve the existing five Terraform PostgreSQL
adapter outputs and all module/provider pins.

The Terraform root `DEPLOYMENT_METADATA` declaration explicitly uses
`sensitive = false`. Its value must remain a reviewed non-secret output.
Do not declassify a tainted value with
`nonsensitive()`. Metadata contains only the closed selected fields, not source
commands, app settings, telemetry connection strings or secret references that
embed values.

The example is synthetic schema data, not a new application, deploy-ready
definition, source pin or approved Azure destination.

## Selection and provider requests

Resolve the actual provider using `config.deployment.provider.resolve_provider`.
Resolve the explicit environment using the existing validated selected snapshot
helper. Read the original typed parameter declaration and existing resource-group
binding. Do not use ambient CLI subscription, a provider environment override,
generated tfvars or store contents as selection authority.

| Provider | Approved metadata request | Required source binding |
| --- | --- | --- |
| Bicep | `az deployment group show`, query `properties.outputs.DEPLOYMENT_METADATA.value`, JSON output | Explicit subscription, bound Foundry/root group and validated saved `DEPLOYMENT_NAME`. Check deployment succeeded |
| Terraform | `terraform output -json DEPLOYMENT_METADATA`, consume the object directly | Native selected provider directory and existing initialized backend, matching `.azure/<env>/terraform-backend.json` |

For Bicep, check deployment status with a separate bounded projection rather
than printing all outputs. ARM read-only control-plane access may return a
deployment internally. Do not log, persist or display its full response.

For Terraform, parse the root declarations before invocation. Require exactly
one approved output, explicit literal false sensitivity, valid HCL and the
repository's reviewed producer path. Reject unknown or sensitive declarations
before requesting the value. Do not log subprocess stdout/stderr wholesale.
The CLI can reveal sensitive named outputs, so source approval is essential.
Terraform's own sensitivity checks and producer regression tests remain required.

Native staging follows the selected infrastructure path:
`.azure/<env>/<infra.path>/.terraform` and
`.azure/<env>/<infra.path>/<env>.conf.json`. After original binding/configuration
checks, bounded `terraform init -input=false -get=false -lockfile=readonly`
with that backend configuration rejects changed native bindings before the named
output request. No reconfiguration or state migration is authorized.

Forbidden operations include unnamed/bulk `terraform output -json`, `state
pull`, `show -json` as a state-discovery substitute, parsing state files, dumping
the whole azd environment, backend guessing and store fallback.

Provider CLI/backends legitimately read their own native persistence. This is
not permission for deployment code to read full state or grant itself broader
access. An unavailable backend/output fails closed.

## Shared loader and setup boundary

Implemented module:

```text
python -m config.deployment.metadata --check --environment <name>
  [--project-root <path>] [--input <declared-parameter-file>]
```

- Success exits 0 after schema, context and live verification for the selected
  setup/deploy operation. Log a concise success summary, no metadata dump.
- Failure exits nonzero and logs a typed, redacted error through the configured
  Python logging path. No dependent mutation is performed by this command.
- Python callers receive a typed verified context rather than mutate global
  environment variables or instantiate an App Configuration client.
- Service modules use the same loader and focused setup resolver. Existing
  direct CLI entry points must not become bypasses.
- An operation with explicitly deferred private setup remains deferred, not
  silently ready. Retain the current hook's visible deferral policy.

The setup resolver combines this context with typed declared inputs and approved
runtime preferences. It maps modern fields to legacy setup shapes such as
`MODEL_DEPLOYMENTS`, `CONTAINER_APPS` and canonical names where consumers still
expect them, without another output format. Metadata values override nothing
silently: conflicting declarations/aliases are errors.

Current operator guidance belongs in the central documentation:
[runtime configuration](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/configuration/#runtime-configuration-mode)
and [metadata recovery](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/deployment-operations/#verify-deployment-metadata).

## Freshness and conflict rules

Each invocation reads its selected provider output again and verifies the live
targets relevant to the operation. Native provider outputs persist across
processes, so no additional inventory file is required.

Compare overlapping azd flat aliases and any saved `DEPLOYMENT_METADATA` structurally
with the live candidate. Missing cache is not missing authoritative output.
An existing cache that conflicts is stale and must fail with refresh guidance.
Do not compare mutable hosted agent publication siblings as immutable metadata.

Normalize only supported ARM casing/endpoint representations. Reject mismatched
environment, provider, tenant/subscription, deployment name, groups, application,
mode, resource IDs, identity UUIDs, model/app mappings and Foundry binding.
Enabled-service data cannot be replaced with null, empty strings or guessed
names. A payload's `referenced` status never authorizes external ownership.

Older foundations without the dedicated output require same-provider reprovision.
Refreshing only the azd cache cannot repair a missing provider output.

## Runtime mode and secret boundary

App Configuration is not consulted for metadata in any mode.
In appConfig mode it remains the runtime sink and source of allowlisted
user-owned preferences, with exact store identity/endpoint verification.
Preserve `agent-lz`, setting ownership, feature flags, Key Vault references and
the original runtime outputs v1.

Store-free setup still configures selected services and legitimate Key Vault
operations. A true store-dependent selected feature fails before mutation.
ContainerEnv with an existing store does not silently select appConfig.
Mode `none` gains no runtime settings injection.

## Consumed-key ownership inventory (T002)

The inventory covers the actual Foundry, toolbox, Search setup and both Jinja
templates, governance, Container Apps, panel, shared deployment publication,
MCP/native access and their dynamic source-key construction.

Categories below are **I** original typed input or explicit declared operational
intent, **D** provider-derived deployment metadata, **P** an allowlisted
user-owned runtime preference, **S** a secret/reference, and **O** an existing
deployment operation's persisted binding. D values are never read from the
store. Read-only live verification may resolve properties of the exact bound
resource, not select a different resource.

| Consumers and exact key group | Category and authority | Resolution or preservation rule |
| --- | --- | --- |
| Shared context: `TENANT_ID`, `AZURE_TENANT_ID`, `SUBSCRIPTION_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_APP_RESOURCE_GROUP`, `AZURE_FOUNDRY_RESOURCE_GROUP`, `AZURE_NETWORK_RESOURCE_GROUP`, `ENVIRONMENT_NAME`, `AZURE_ENV_NAME`, `DEPLOYMENT_NAME`, `APPLICATION_ID`, `APP_RUNTIME_CONFIGURATION_MODE` | D context, independently bound to I selection | Map supported aliases explicitly, compare rather than overwrite conflicting cached aliases |
| `LOCATION`, `RESOURCE_TOKEN`, `USE_UAI`, `USE_CAPP_API_KEY`, `NETWORK_ISOLATION`, `DEPLOY_APP_CONFIG`, `DEPLOY_SOFTWARE`, `DEPLOY_KEY_VAULT`, `DEPLOY_LOG_ANALYTICS`, `DEPLOY_APP_INSIGHTS`, `DEPLOY_SEARCH_SERVICE`, `DEPLOY_SPEECH_SERVICE`, `DEPLOY_STORAGE_ACCOUNT`, `DEPLOY_COSMOS_DB`, `DEPLOY_CONTAINER_APPS`, `DEPLOY_CONTAINER_REGISTRY`, `DEPLOY_CONTAINER_ENV`, `DEPLOY_VM_KEY_VAULT` | I original typed parameters | Retain declared types/defaults and existing selection rules, do not infer ownership/readiness from an echoed flag |
| `RELEASE` | I repository-owned manifest tag | Preserve existing runtime publication, do not add release data to the resource schema |
| Foundry: `AI_FOUNDRY_ACCOUNT_NAME`, `AI_FOUNDRY_ACCOUNT_RESOURCE_ID`, `AI_FOUNDRY_PROJECT_ENDPOINT`, `AI_FOUNDRY_PROJECT_RESOURCE_ID`, `AZURE_AI_PROJECT_ENDPOINT`, `AZURE_AI_PROJECT_RESOURCE_ID`, `MODEL_DEPLOYMENTS` | D Foundry slots and model mappings | Adapt canonical model/name shapes in memory and verify the exact account/project, including RAI association |
| Vault: `KEY_VAULT_URI`, `KEY_VAULT_ENDPOINT`, `KEY_VAULT_NAME`, `KEY_VAULT_RESOURCE_ID` | D keyVault slot | Pass an explicit verified vault URI to the Foundry helper, no default store lookup |
| Runtime store: `APP_CONFIG_ENDPOINT` | D appConfig slot | A disabled slot cannot create a store client, present store in containerEnv does not authorize publication |
| Container Apps: `CONTAINER_REGISTRY_NAME`, `CONTAINER_REGISTRY_RESOURCE_ID`, `AZURE_CONTAINER_REGISTRY_RESOURCE_ID`, `AZURE_CONTAINER_REGISTRY_ENDPOINT`, `CONTAINER_APPS`, canonical app `*_NAME`/`*_ENDPOINT` values | D registry slot and app/identity mappings | Use exact mapped apps/identities and live registry binding, never reconstruct app selection from `RESOURCE_TOKEN` |
| Setup process controls: `LOG_LEVEL`, `CONTAINER_APP_MAX_WORKERS`, `CONTAINER_APP_POLL_TIMEOUT_SECONDS` | I local setup controls | Retain existing validation/defaults, not resource metadata or runtime store preferences |
| Search resources: `SEARCH_SERVICE_QUERY_ENDPOINT`, `STORAGE_ACCOUNT_RESOURCE_ID`, `DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID`, `SEARCH_SERVICE_UAI_RESOURCE_ID` | D Search/storage slots and children, exact bound Search live identity | Validate parent/group and identity association, never synthesize an identity name or choose arbitrarily between multiple identities |
| Cosmos/panel: `DATABASE_ACCOUNT_NAME`, `DATABASE_NAME`, `COSMOS_DB_ACCOUNT_RESOURCE_ID`, `COSMOS_DB_ENDPOINT`, `MCP_COSMOS_DATABASE`, `MCP_COSMOS_ENDPOINT` | D cosmos slot and database/container children | Remove panel/MCP store discovery fallback, use exact mapped parent/child IDs, retain container-scoped grants |
| `EMBEDDING_MODEL_INFO`, `GPT_MODEL_INFO`, `GPT_MODEL_DEPLOYMENT_NAME`, `GPT_MODEL_NAME`, `CHAT_DEPLOYMENT_NAME`, `EMBEDDING_DEPLOYMENT_NAME` | D model-derived adapters and canonical selectors | No missing-required-model substitution, preserve model format checks |
| `RETRIEVAL_BACKEND`, `ENABLE_AGENTIC_RETRIEVAL`, `FOUNDRY_IQ_PATTERN`, `FOUNDRY_IQ_API_VERSION`, `FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME`, `FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND`, `FOUNDRY_IQ_STORAGE_CONTAINER_NAME`, `FOUNDRY_IQ_STORAGE_FOLDER_PATH`, `FOUNDRY_IQ_IS_ADLS_GEN2`, `FOUNDRY_IQ_CONTENT_EXTRACTION_MODE`, `FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS`, `FOUNDRY_IQ_SECURITY_FIELD_NAME`, `FOUNDRY_IQ_MAX_OUTPUT_DOCUMENTS`, `FOUNDRY_IQ_FILTER_ADD_ON_ENABLED`, `FOUNDRY_IQ_KNOWLEDGE_RETRIEVAL_BILLING_PLAN`, `SEARCH_RAG_INDEX_NAME`, `KNOWLEDGE_BASE_NAME` | I corresponding typed foundation declarations | Preserve current template/default semantics, do not allow store preferences to change infrastructure intent |
| `KNOWLEDGE_BASE_ENDPOINT`, `KNOWLEDGE_BASE_CONNECTION_ID`, `TOOLBOX_ENDPOINT`, `FOUNDRY_IQ_AI_SERVICES_ENDPOINT` | D verified Search/Foundry bindings plus I declared connection/KB/endpoint inputs | Validate derived endpoints and project-child connection IDs, preserve an explicit compatible AI Services endpoint, never substitute a runtime-store destination |
| `SEARCH_API_VERSION`, `SEARCH_ANALYZER_NAME`, `EMBEDDINGS_VECTOR_DIMENSIONS`, `SEARCH_QUERIES_INDEX_NAME`, `SEARCH_TABLES_INDEX_NAME`, `SEARCH_MEASURES_INDEX_NAME` | Template-owned setup values, with D validated token/model context | Preserve current template-generated values and dimensional/model checks, no new metadata fields or unreviewed preference override |
| `FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED`, `FOUNDRY_IQ_CONVERSATION_KNOWLEDGE_SOURCE_NAME` | I explicit operational intent, P only where existing setting ownership permits | Preserve feature prerequisites, not proof of uploaded data or source readiness |
| `WORK_IQ_ENABLED`, `WORK_IQ_KNOWLEDGE_SOURCE_NAME`, `WORK_IQ_APPLICATION_ID`, `WORK_IQ_FEDERATED_CREDENTIAL_ID`, `WORK_IQ_TENANT_ID` | I explicit source declarations, P under existing ownership in appConfig mode | Validate complete source selection and UUIDs, never treat source tenant/application IDs as platform resource discovery |
| `FABRIC_IQ_ENABLED`, `FABRIC_IQ_KNOWLEDGE_SOURCE_NAME`, `FABRIC_IQ_WORKSPACE_ID`, `FABRIC_IQ_ONTOLOGY_ID`, `FABRIC_DATA_AGENT_ENABLED`, `FABRIC_DATA_AGENT_KNOWLEDGE_SOURCE_NAME`, `FABRIC_DATA_AGENT_WORKSPACE_ID`, `FABRIC_DATA_AGENT_DATA_AGENT_ID` | I explicit source declarations, P under existing ownership in appConfig mode | Preserve dynamic required-key validation for each selected source |
| `SHAREPOINT_INDEXED_ENABLED`, `SHAREPOINT_INDEXED_KNOWLEDGE_SOURCE_NAME`, `SHAREPOINT_INDEXED_INDEX_NAME`, `SHAREPOINT_INDEXED_SITE_URL`, `SHAREPOINT_INDEXED_TENANT_ID`, `SHAREPOINT_INDEXED_APPLICATION_ID`, `SHAREPOINT_INDEXED_FEDERATED_CREDENTIAL_APPLICATION_ID` | I explicit source declarations, P under existing ownership in appConfig mode | Preserve consent, OBO, source completeness and tenant/client validation |
| `WEB_GROUNDING_ENABLED`, `WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME`, `WEB_GROUNDING_ALLOWED_DOMAINS`, `WEB_GROUNDING_BLOCKED_DOMAINS` | I explicit source declarations, P under existing ownership in appConfig mode | Preserve template normalization and host restrictions |
| `FOUNDRY_IQ_MCP_ENABLED`, `FOUNDRY_IQ_MCP_SOURCES_JSON`, `FOUNDRY_IQ_MCP_REASONING_EFFORT`, `FOUNDRY_IQ_MCP_TRUSTED_HOSTS`, `FOUNDRY_IQ_MCP_LOG_TOOL_ARGUMENTS` | I/P curated operational source settings | Preserve the closed MCP source validator, tool limits, trust policy and nested credential-reference checks |
| `RETRIEVAL_AUTH_MODE`, `HOSTED_AGENT_AUTH_MODE`, `FOUNDRY_IQ_FORWARD_SOURCE_AUTH`, `ALLOW_ANONYMOUS` | I/P existing protected retrieval intent | Preserve `config/retrieval/settings.py` checks, do not change auth mode to make setup pass |
| Governance: `AUDIT_EVENTS_ENABLED`, `AUDIT_SENSITIVE_CONTENT_ENABLED`, `AUDIT_SENSITIVE_CONTENT_FIELDS`, `AUDIT_ACTOR_PSEUDONYM_ENABLED`, `AUDIT_SOURCE_EVENT_LIMIT`, `AUDIT_HMAC_KEY_ID`, `AUDIT_ADDITIONAL_REDACTED_KEYS`, `INGESTION_PROVENANCE_ENABLED`, `INGESTION_REQUIRE_GOVERNANCE_METADATA`, `INGESTION_DEFAULT_CLASSIFICATION`, `INGESTION_DEFAULT_RIGHT_TO_USE` | I explicit intent, otherwise P/defaults with existing governance ownership | Preserve existing store values/default seeding in appConfig mode, resolve store-free setup without creating a store client |
| `AUDIT_HMAC_KEY`, `MCP_API_KEY`, `CHAINLIT_AUTH_SECRET`, `OAUTH_AZURE_AD_CLIENT_SECRET`, `authClientSecret`, Foundry evaluation API key | S Key Vault operations/references | No resolved value in metadata or logs, preserve create/reuse, migration conflict and narrow RBAC checks |
| `NATIVE_TOOL_SECRET_NAMES`, `MCP_SQL_SECRET_NAMES` and MCP source `valueFrom.secretName` | I declared S reference names | Names/references only, validate against the exact verified vault, no raw secret-value transport |
| `APPLICATION_MODE`, `ORCHESTRATION_HOST`, `DEPLOY_INGESTION_CONTAINER_APP`, `DEPLOY_AGENT_APP_MCP`, `MCP_TOOLSETS`, `ENABLE_CHAT_HISTORY`, `ENABLE_USER_FEEDBACK`, `ENABLE_PRIVATE_ATTACHMENTS`, `NATIVE_UI_METADATA_CONTAINER` | I composition/feature selection | Preserve shared composition/ownership helpers and actual selected service prerequisites |
| `MCP_SOURCES_CONTAINER`, `MCP_METADATA_CONTAINER`, `MCP_EMBEDDING_DIMENSIONS`, `MCP_QUERY_TIMEOUT_SECONDS`, `MCP_METADATA_TOP_K`, `COSMOS_VECTOR_SEARCH_ENABLED`, `COSMOS_ACCOUNT_CAPABILITIES` | I catalog policy and D verified Cosmos capabilities/children | Preserve immutable retained-catalog policy and dimensions, do not use absent discovery as permission to default a live capability |
| `MCP_APP_NAME`, `MCP_APP_ENDPOINT`, `MCP_APP_CLIENT_ID`, `MCP_APP_PRINCIPAL_ID` | D selected app/identity, O publication where applicable | Verify actual binding before use, not a store discovery fallback |
| `MCP_AUTH_APP_OBJECT_ID`, `MCP_AUTH_AUDIENCE`, `MCP_AUTH_RESOURCE_SCOPE`, `MCP_AUTH_ROLE_ID`, `MCP_AUTH_SERVICE_PRINCIPAL_ID`, `MCP_AUTH_TENANT_ID`, `MCP_ALLOWED_CLIENT_IDS`, `MCP_ENABLED`, `MCP_SERVER_URL` | O feature-owned Entra state and runtime publication | Existing bundled MCP activation requires its store-backed state/publication, fail explicitly before mutations for an incompatible selection rather than invent a new persistence mechanism |
| `HOSTED_AGENT_DEPLOYMENT`, `HOSTED_AGENT_PREPARED`, `DEPLOY_HOSTED_AGENT`, `ACR_TASK_AGENT_POOL`, scheduler/egress/private-build handoff fields | Existing specialized foundation contracts plus I selection | Preserve durableTask, workloadEgress and privateBuild verification, compare any overlapping neutral resource bindings |

The rows enumerate consumed setting names, not permission to accept arbitrary
keys with those prefixes. Jinja locals such as `GPT_MODEL_INFO`, generated source
suffixes such as `WORKSPACE_ID`, HTTP methods and log-level constants are not
additional runtime input keys. Retired composition keys in
`appconfig_ownership.json` remain retired, not revived by this migration.

The resolver must map I keys through existing typed parameters or explicit
operational setting declarations. A missing required selected value is an error,
not an empty-string placeholder. A store-owned preference is readable only in
appConfig mode after exact store verification and only under its existing owner.
In containerEnv mode, resolve explicit declared operational values and existing
defaults without consulting even a present store. Do not copy all store values
into template context, override resource mappings, or persist a second inventory.

The current native secret-reference reader has an implicit store dependency.
Use explicit declared references and the verified vault for store-free grants,
retaining existing reference migration checks in appConfig mode. If a selected
feature genuinely needs store-owned state, validate that prerequisite before any
dependent mutation rather than skipping its setup. This does not make the pinned
bundled MCP/runtime or existing sample applications store-free.

## Error contract

| Error category | Examples | Recovery |
| --- | --- | --- |
| Missing foundation/output | No successful deployment or missing dedicated output | Provision/reprovision the selected provider from preserved declarations |
| Invalid/unsupported contract | Wrong type, extra field, unknown version | Use a compatible producer/consumer revision and reprovision |
| Context conflict/stale cache | Switched environment, stale endpoint/identity, different group | Restore intended binding, refresh saved outputs, revalidate |
| Unapproved/sensitive source | Nonliteral/true sensitivity, wrong output, secret-bearing field | Correct reviewed producer. Never dump candidate values |
| Live verification failure | Wrong ARM ID/type, project endpoint mismatch, principal mismatch | Correct intended resource/identity binding, then retry |
| Access/connectivity failure | Forbidden, DNS/TLS error, unavailable backend | Restore existing approved permissions/runner connectivity. No bypass grants |
| Feature prerequisite failure | Runtime requires store or selected audit requires vault | Correct explicit selection or provide prerequisite, no silent disable |

Errors name the affected field/category and corrective action, never an embedded
value, credentials, raw provider output or a connection string.

## Compatibility and adoption

Adopt both producers and shared consumers in one coordinated platform change
after acceptance of the concrete output/consumer migration in ADR-0041.
Update every affected consumer of reorganized outputs together and document
mixed-version restrictions, old-to-new mappings and recovery. No
runtime/component manifest update is assumed because
no runtime contract changes. Old foundations need reprovision before new hooks.
Old hooks remain store-dependent, so rollback for a store-free environment is a
reviewed roll-forward, not reintroducing a metadata fallback.

The implementation must prove dedicated-output serialization using pinned
tooling before migrating consumers. If that fails, revise the ADR explicitly.
Do not silently switch to a generated local-state substitute.
