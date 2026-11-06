# PostgreSQL implementation interfaces

Feature-branch contracts; not a released or Azure-validated capability.
See the quickstart evidence/blocker ledger before integrated delivery.

## Native inputs

Both roots, parameter seeds and typed resolver expose the same types/defaults.
Environment mappings are explicit additions, not inferred aliases.

| Native input | Type / default | Environment mapping |
| --- | --- | --- |
| `deployPostgreSql` | bool / false | `DEPLOY_POSTGRESQL` |
| `postgreSqlServerName` | string / shared naming derivation | `POSTGRESQL_SERVER_NAME` |
| `postgreSqlDatabaseName` | string / agentlz | `POSTGRESQL_DATABASE_NAME` |
| `postgreSqlVersion` | string / 16 | `POSTGRESQL_VERSION` |
| `postgreSqlTier` | string / Burstable | `POSTGRESQL_TIER` |
| `postgreSqlSkuName` | string / Standard_B1ms | `POSTGRESQL_SKU_NAME` |
| `postgreSqlStorageSizeGb` | int / 32 | `POSTGRESQL_STORAGE_SIZE_GB` |
| `postgreSqlBackupRetentionDays` | int / 7 | `POSTGRESQL_BACKUP_RETENTION_DAYS` |
| `postgreSqlHighAvailability` | string / Disabled | `POSTGRESQL_HIGH_AVAILABILITY` |
| `postgreSqlGeoRedundantBackup` | bool / false | `POSTGRESQL_GEO_REDUNDANT_BACKUP` |
| `postgreSqlStorageAutoGrow` | bool / false | `POSTGRESQL_STORAGE_AUTO_GROW` |
| `postgreSqlAdministratorObjectId` | GUID / required enabled | `POSTGRESQL_ADMINISTRATOR_OBJECT_ID` |
| `postgreSqlAdministratorPrincipalName` | string / required enabled | `POSTGRESQL_ADMINISTRATOR_PRINCIPAL_NAME` |
| `postgreSqlAdministratorPrincipalType` | User, Group, ServicePrincipal / required enabled | `POSTGRESQL_ADMINISTRATOR_PRINCIPAL_TYPE` |
| `postgreSqlAllowedIpRanges` | IPv4/CIDR array / empty | Typed root JSON, no string alias |
| `existingPrivateDnsZonePostgreSqlResourceId` | string / empty | Typed native parameter |

Admin tenant derives from the resolved deployment directory; verify supplied
principal belongs to it. No default to app identity. Disabled inputs never
implicitly enable resources or require admin lookup.
Port5432, Entra-only, verified TLS and protection are fixed requirements.
Location follows foundation location. HA enum Disabled/SameZone/ZoneRedundant;
reject enabled HA for Burstable. Validate supported engine/storage/SKU/region;
never fallback silently.

Basic requires a fresh deployed workload-profiles ACA environment, valid
delegation/capacity and no conflicting forced route. NAT naming derives from
shared conventions with a distinct ACA purpose. Isolated reuses app PE/DNS
inputs and policy-managed ownership; no delegated PostgreSQL subnet.

## Provider mapping

| Behavior | Bicep | Terraform |
| --- | --- | --- |
| Tier/SKU | tier and skuName | B_, GP_ or MO_ prefix plus SKU |
| Storage | GiB | GiB * 1024 MiB |
| Auth | Explicit AD Enabled/password Disabled | Explicit AD true/password false/tenant |
| HA off | Disabled | null HA object |
| Geo off | Disabled | false |
| Password | Omit nullable login/password | Omit nullable login/password |
| Public | Enabled only Basic | Enabled only Basic |
| Lock | No AVM ownership | lock=null; no Terraform ownership |

Map auto-grow/databases using exact tagged module schemas; Bicep `autoGrow`
uses Enabled/Disabled, Terraform uses its Boolean auto-grow input.
Current provider pins/lock remain intact.

## Outputs/publication

Both provider lifecycles expose azd metadata `POSTGRESQL_SERVER_RESOURCE_ID`, `POSTGRESQL_HOST`,
`POSTGRESQL_PORT`, `POSTGRESQL_DATABASE_NAME` and
`CONTAINER_APPS_POSTGRESQL_EGRESS_IP`. Fresh disabled deployments add no
metadata; Terraform's corresponding native outputs are empty strings.
Egress IP is empty in isolation. Required enabled metadata must not be empty.
The Bicep root retains all 64 existing outputs: ARM does not allow additional
outputs. The shared post-provision adapter instead derives the server identity
from immutable creation intent, verifies the live server/database/auth/lock,
and persists these five values through `azd env set` for either provider.
Basic egress is read from the verified ACA subnet/NAT/static-IP association,
never ACA ingress or an arbitrary public IP. Terraform's additive native
outputs are checked against the same authoritative readback. This is a
documented transport difference, not a change to the closed v1 JSON contract.

Flat App Configuration keys under `agent-lz`:

| Key | Enabled value |
| --- | --- |
| AGENTLZ_POSTGRESQL_HOST | Canonical FQDN |
| AGENTLZ_POSTGRESQL_PORT | 5432 |
| AGENTLZ_POSTGRESQL_DATABASE | Application database |
| AGENTLZ_POSTGRESQL_SSLMODE | verify-full |
| AGENTLZ_POSTGRESQL_AUTH_MODE | entra |

Publish only after binding/independent-lock verification. Fresh disabled
deployments omit keys. Enabled-to-disabled is rejected before publication,
not implemented as silently clearing a live consumer's settings.
AGENTLZ_PLATFORM_OUTPUTS v1/schema and bundled consumers remain unchanged.
Custom apps own SQL username selection, drivers, TLS, token refresh and pooling.

## Manual bootstrap CLI

Implemented manual interface:

```text
python -m util.postgresql_bootstrap
  --server-resource-id <verified-server-arm-id>
  --host <fqdn> --database <database>
  --administrator-role <configured-entra-admin-role>
  --application-object-id <service-principal-object-id>
  --application-role <sql-role> --schema <app-schema>
  --ddl-owner-role <actual-object-creator-role>
```

Verify directory/subscription, server/auth/database binding and principal
mapping; use AzureCliCredential with token only in memory. Verified TLS and
bounded timeouts are mandatory. No password/token argument, firewall edits,
remapping, DDL grant or lock removal.
Operator explicitly arranges network access and initializes the app schema.
For a Group administrator, enumerate all transitive Graph members before
SQL/token work and reject administrative group membership by the application
identity. Directory-read permissions must cover that membership, including
hidden members where applicable. Permission failures and malformed, scoped-out,
cyclic or over-limit continuations fail closed; never infer non-membership
from an incomplete page.

Zero exit only after mapping/effective-grant verification; failures are nonzero
with repository-standard logging and no secrets. Reuse exact mapping on rerun,
reject conflicts/privilege bypass; quote identifiers and bind values.
Tests cover wrong tenant/OID/type, existing role conflicts, inherited privileges,
identifier injection, partial failure and actual DDL-owner default grants.
The dedicated-schema boundary is conservative: base tables/sequences owned by
the actual declared DDL owner only; view/materialized-view/foreign wrappers and
user SECURITY DEFINER functions/triggers are rejected. PUBLIC CREATE/TEMP on
the target DB and PUBLIC CREATE on public/app schemas cannot bypass CRUD-only
rights. App ownership, global/PUBLIC default ACLs and SET ROLE paths are checked.

## Protection lifecycle

Lifecycle owns server-scoped CanNotDelete lock
`agentlz-postgresql-data-protection`, outside both provider graphs/state.
Verify exact scope/level and persist only non-secret binding.
Never import/adopt that lock into Terraform.

Pre-provision rejects disable, retrofit and destructive binding changes;
pre-down rejects while PG binding exists. Do not let the current Terraform
teardown ownership early return bypass the guard. Post-provision creates/
readbacks the independent lock before publishing readiness.
The record is `.azure/<environment>/postgresql-binding.json`, with immutable
binding/fingerprint/schemaVersion1 and ready Boolean. It is not secret state
and remains ignored with `.azure`; it is still mandatory recovery evidence.
Readback uses supported Azure CLI `lock create --resource <server-id>` and
`lock show --ids <server-id>/providers/Microsoft.Authorization/locks/<name>`;
administrator verification uses `postgres flexible-server microsoft-entra-admin
list`, not a fictitious `--scope`/`ad-admin` boundary. Calls are bounded/injectable.

Removal is separately approved operator work: backup/restore review, exact
inventory, consumer shutdown, owner approval, lock removal and provider-specific
resource/state reconciliation. It is not a deployment escape-hatch Boolean.
Never delete shared zones or resource groups implicitly.
