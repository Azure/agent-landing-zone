# Data Model: Provider-owned Deployment Metadata

**Status**: Proposed interface, not a shipped runtime contract

## Entities and relationships

| Entity | Fields | Relationships and validation |
| --- | --- | --- |
| Deployment metadata | `schemaVersion`, `context`, `resources`, `modelDeployments`, `containerApps`, `dataResources` | Exactly v1, closed object. Only selected non-secret resource descriptions |
| Context | Environment/provider, tenant/subscription UUIDs, deployment name, three destination groups, application ID, runtime mode | Must agree with independently selected azd/provider/declared input/group binding |
| Resource slot | `status`, `resource` | Fixed service names. `disabled` requires null, `managed`/`referenced` requires exact resource descriptor |
| Resource descriptor | `resourceId`, `name`, nullable `endpoint` | ARM type/parent/scope derived and checked by service slot, not trusted from a type field |
| Model deployment | Canonical name, resource ID, deployment name, model format/name/version, API version, endpoint | Exact Foundry account child, no duplicate canonical names or IDs, declared/evaluated model agreement |
| Container App | Canonical name, service name, resource ID/name, nullable FQDN, identity | Exact declared app, Container App environment and registry bindings verified live |
| Identity | Kind, principal UUID, nullable client UUID/resource ID | System-assigned has no user-assigned resource ID/client ID. User-assigned requires both and exact live principal/client binding |
| Data resources | Storage containers, Cosmos databases/containers | Typed named children belonging to verified parent accounts. No connection strings or keys |
| Setup settings | Typed declared parameters plus approved runtime preferences and verified metadata | In-memory input to existing service modules, not a second output contract |
| Runtime publication | Existing v1 JSON, flat keys, settings, flags and secret references | Existing owners and `agent-lz` semantics. No new keys required in pinned runtimes |

The schema is [deployment-metadata-v1.schema.json](contracts/deployment-metadata-v1.schema.json).
The example is synthetic and cannot select a real Azure destination.

## Fixed resource slots

Every slot is present, even when disabled:

| Slot | Expected resource type or relationship |
| --- | --- |
| `foundryAccount` | `Microsoft.CognitiveServices/accounts` in bound Foundry group |
| `foundryProject` | Exact project child of that account |
| `registry` | `Microsoft.ContainerRegistry/registries`, including explicitly approved external registry ownership |
| `appConfig` | `Microsoft.AppConfiguration/configurationStores` when provisioned, exact application-group binding |
| `keyVault` | `Microsoft.KeyVault/vaults` |
| `storage` | Selected application `Microsoft.Storage/storageAccounts`, not an unrelated Foundry backing account |
| `search` | `Microsoft.Search/searchServices` |
| `cosmos` | `Microsoft.DocumentDB/databaseAccounts` |
| `containerEnvironment` | `Microsoft.App/managedEnvironments` |
| `network` | Workload VNet, with explicitly declared shared ownership where supported |
| `speech` | Selected Speech Cognitive Services account |
| `logAnalytics` | Selected `Microsoft.OperationalInsights/workspaces` |
| `appInsights` | Selected `Microsoft.Insights/components`, no instrumentation/connection-string values |

The closed metadata object is the value of the dedicated `DEPLOYMENT_METADATA`
root output, not a hosted handoff member.
Existing specialized `durableTask`, `workloadEgress` and `privateBuild` handoff
members retain their contracts. The new output does not replace them or accept
conflicting overlapping bindings. Specialized validation still runs.

## Validation beyond JSON Schema

Schema validation is necessary, not authorization or readiness evidence.

1. UUIDs, ARM paths and endpoints are parsed, not compared as unconstrained
   strings. Use existing resource-ID and endpoint helpers. HTTPS endpoints must
   have no userinfo, query, fragment or unexpected port.
2. Resource IDs must have the expected provider/type/parent and independently
   approved subscription/group. Shared/external ownership requires matching
   declared IDs and existing service-specific policy, never a self-asserted
   `referenced` status.
3. Names must match the IDs. Foundry endpoint must match the live account
   domain and exact project. Registry/Search/storage/vault endpoints must match
   live service metadata. A name match alone never resolves an ID conflict.
4. `disabled` must match typed selected inputs. Missing enabled-service data is
   an error. App/model/data child arrays must match selected resources and
   canonical declarations, including duplicates and required children.
5. Live resource identities must match the intended principals and user-assigned
   client/resource IDs. Keep document authorization, OBO and owner RBAC unchanged.
6. Normalize ARM ID casing and service endpoint trailing slashes only using
   existing validated helpers. Do not lowercase arbitrary path or settings
   values. Compare parsed JSON structurally, never by key order.
7. Intersecting saved flat aliases and cached `DEPLOYMENT_METADATA` must agree
   with the live provider result. Ignore unrelated saved inputs, not conflicting
   destination values. Compare only the dedicated output, not the mutable hosted
   agent publication overlay.
8. Secret-bearing extra fields, credentialed URLs, prohibited values and
   unapproved outputs are rejected without logging candidate values.

## Authority and state transitions

```text
Selected environment + provider + declared inputs + bound destinations
  -> Approved provider output read
  -> Schema-valid candidate
  -> Consistent with declared context and cached aliases
  -> Live resource/project/identity and network verified
  -> Ready for this selected operation
  -> Required setup succeeds
  -> Optional runtime publication
```

Any invalid transition ends in a visible failure before dependent mutation.
There is no transition from invalid metadata to store hydration, guessed values,
raw state or a different provider. A partially successful provision is not a
ready foundation merely because a previous output still exists.

Keep verification scoped to the current operation and revalidate on subsequent
invocations. No durable "verified" flag or local timestamp bypasses live checks.
Setup failure remains failure even if some earlier independent operations
succeeded. Retries reuse normal idempotent module behavior and original ownership.

## Configuration categories

| Category | Authority | Persistence/use |
| --- | --- | --- |
| Infrastructure inputs | Root parameter declaration and shared typed resolver | Native provider inputs, never reconstructed from runtime store contents |
| Deployment metadata | Approved evaluated provider output | Native provider persistence, consumed by setup after binding/verification |
| Runtime settings/flags | Existing owners, declared intent and permitted operational overrides | Store label `agent-lz` or existing curated `containerEnv` path according to selection |
| Secrets | Key Vault and existing access controls | Resolved values stay inside the legitimate secret operation, never discovery/artifacts/logs |

The setup resolver must enumerate consumed operational keys and classify each
as declared input, resource-derived value, runtime preference or secret reference.
Existing store-owned operational preferences remain readable only for their
runtime purpose. They may not replace provider resource metadata.

No general-purpose settings dictionary is accepted in the deployment schema.
Audit HMAC and evaluation keys remain Key Vault values. Configuration paths pass
references or use the existing secret operation, not metadata value transport.

## Compatibility, retention and recovery

- `schemaVersion: 1` is independent of runtime platform outputs v1.
  Unsupported versions fail rather than assume compatibility.
- Existing hosted handoff contracts and runtime v1 bytes/semantics remain
  unchanged. Root output names may change only through the approved
  old-to-new output/consumer migration within ARM's output limit.
  Closed deployment v1 changes require a new version.
- No local metadata database or generated state substitute is introduced.
  Native outputs survive independent process invocations.
- Missing old metadata requires same-provider reprovision. Stale saved aliases
  require supported refresh and revalidation. Backend identity, declared inputs
  and resource-group binding are preserved.
- No runtime conversion or store deletion is promised. Old store-dependent
  hooks cannot be the recovery path for a new store-free environment.
