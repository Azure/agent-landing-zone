# Research: Optional application PostgreSQL

User decisions are recorded in [spec.md](spec.md). Technical research used
tagged AVM sources, Registry metadata, Microsoft Learn and PostgreSQL docs.
This is design evidence, not deployment validation.

## 1. Module and provider selection

**Decision**: Propose Bicep
`br/public:avm/res/db-for-postgre-sql/flexible-server:0.16.1` and Terraform
`Azure/avm-res-dbforpostgresql-flexibleserver/azurerm` version `0.2.3`.
Retain current exact provider constraints: AzureRM 4.81.0, AzAPI 2.13.0,
Random 3.9.1, ModTM 0.4.0, Time 0.14.2. Root Terraform >=1.13 satisfies
the module's >=1.9 requirement.

**Rationale**: Published pins expose Entra-only authentication with nullable
admin login/password, administrator assignments, databases, SKU/storage/backup/
HA and public/Private Link inputs. No dummy credentials are required.
The Terraform module requires AzureRM ~>4.12, AzAPI ~>2.12 and Random ~>3.6,
compatible with current root constraints; confirm init with lockfile readonly.

**Alternatives considered**: Raw resources violate the requested AVM approach.
Bicep 0.15.3 was examined as an older stable-API candidate, but its actual server
resource uses `2025-06-01-preview`; 0.16.1 uses `2026-01-01-preview`.
The apparent stable API bump in child-module history is not a GA server API.
Prefer the newer fix-bearing pin and explicitly assess subscription governance.
If policy rejects this API, stop and obtain a reviewed compatible-pin decision;
do not hide a raw-resource fallback.

Sources:
- [Bicep tagged server](https://github.com/Azure/bicep-registry-modules/blob/avm/res/db-for-postgre-sql/flexible-server/0.16.1/avm/res/db-for-postgre-sql/flexible-server/main.bicep)
- [Older tagged server](https://github.com/Azure/bicep-registry-modules/blob/avm/res/db-for-postgre-sql/flexible-server/0.15.3/avm/res/db-for-postgre-sql/flexible-server/main.bicep)
- [Terraform module source](https://github.com/Azure/terraform-azurerm-avm-res-dbforpostgresql-flexibleserver/tree/v0.2.3)
- [Terraform published versions](https://registry.terraform.io/v1/modules/Azure/avm-res-dbforpostgresql-flexibleserver/azurerm/versions)

## 2. Equivalent economical defaults

**Decision**: Engine 16, Burstable Standard_B1ms, 32 GiB storage, seven-day
backup, HA disabled, geo-backup disabled and storage auto-grow disabled.
These are development defaults, configurable subject to service compatibility.

**Rationale**: User selected low initial cost. AVM defaults are not equivalent:
Bicep defaults to Entra-only but Terraform authentication must be explicit;
both default HA on, and Bicep defaults geo-backup on. Terraform SKU combines
the tier prefix (`B_Standard_B1ms`), while Bicep splits tier/SKU.
HA off is `Disabled` in Bicep and a null object in Terraform.
Storage maps from 32 GiB to 32768 MiB. Set all values explicitly.

**Alternatives considered**: General Purpose/HA as default increases cost.
Inheriting module defaults violates parity. Silent regional fallback is rejected.
Validate SKU/HA/region through current preflight patterns; capture live capacity
and billing risks. Do not claim Standard_B1ms exists in every region.

## 3. Basic application egress and isolated access

**Decision**: Fresh Basic ACA uses custom VNet integration, external ingress
and a dedicated Standard NAT Gateway/static public IPv4. Allow that exact
egress IP in PostgreSQL, plus explicit operator IPv4/CIDR inputs.
Isolation uses PE/private DNS with public database access disabled.

**Rationale**: User selected predictable public egress instead of changing
platform IP lists. Current roots only integrate ACA with VNet when isolated;
enabling PostgreSQL must extend the effective condition, not the default.
Workload-profiles ACA requires a delegated subnet of at least /27; existing
/24 seed remains suitable. Legacy Consumption-only environments do not
support NAT/UDR. A Consumption workload profile inside a workload-profiles
environment is not the same as the legacy environment type.
NAT IP is outbound, not ACA ingress IP. Use Standard, not unsupported
StandardV2. Do not change/reuse jumpbox NAT.

A `0.0.0.0/0` route to an NVA/firewall bypasses subnet NAT SNAT; reject it for
this Basic path rather than editing corporate routing. Private Link is distinct
from injecting PostgreSQL into a delegated server subnet; do not mix them.
Server-side networking remains managed under PE, not injected into ACA's subnet.
Clients still require token acquisition and existing approved identity egress.
Do not copy delegated-server Entra egress exceptions into the PE subnet.
Verify Entra/private operations live; this distinction is not live evidence.

**Alternatives considered**: Dynamic IP synchronization risks disconnection.
Broad Azure-services rule weakens network scoping. Always-private behavior
conflicts with the user-selected mode semantics. Existing Basic retrofit is
explicitly deferred; same-binding fresh-deployment recovery remains supported.

Sources:
- [ACA custom VNet/NAT requirements](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks)
- [NAT and UDR precedence](https://learn.microsoft.com/en-us/azure/nat-gateway/nat-gateway-design)
- [PostgreSQL Private Link](https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private-link)

## 4. Entra identity and manual SQL utility

**Decision**: Explicit Entra administrator; a manual Python CLI using existing
AzureCliCredential and proposed `psycopg[binary]==3.3.8`, verified published
on PyPI with Python >=3.10. App role is mapped by service-principal object ID,
not ambiguous display name, with no DDL/admin grants.

**Rationale**: Azure RBAC does not grant SQL permissions. Run
`pgaadauth_create_principal_with_oid(..., 'service', false, false)` in `postgres`;
grant CONNECT/schema USAGE/table CRUD/sequence access in application DB.
Default privileges must target the actual future DDL owner, not merely a
schema owner or inherited role. Operator owns migrations/schema initialization.
The CLI quotes identifiers, binds values and verifies tenant/OID/type/privileges.
Tokens stay in memory and connection parameters with verified TLS, never
command arguments or logs.

Rerun behavior of principal creation is not assumed: inspect existing mappings
through `pgaadauth_list_principals`, reuse exact matches and reject mismatches.
No broad duplicate-role catch. Cross-database role/grant setup is not atomic;
reruns complete verified partial operations.

**Alternatives considered**: Documentation-only copy/paste is error-prone.
Automatic post-provision SQL grants enlarge privilege/connectivity scope.
A new ORM or token-pooling package is unnecessary for manual administration.

Sources:
- [Managed identity PostgreSQL access](https://learn.microsoft.com/en-us/azure/postgresql/security/security-connect-with-managed-identity)
- [Entra role functions](https://learn.microsoft.com/en-us/azure/postgresql/security/security-manage-entra-users)
- [Default privilege semantics](https://www.postgresql.org/docs/16/sql-alterdefaultprivileges.html)
- [Schema privileges](https://www.postgresql.org/docs/16/ddl-schemas.html)
- [Published driver metadata](https://pypi.org/pypi/psycopg/json)

## 5. Independent data protection

**Decision**: Lifecycle creates/verifies server-scoped `CanNotDelete` lock
outside Terraform state and the Bicep graph, before ready output publication.
Guard disable, unsafe replacement and pre-down using verified live/local binding.
Explicit removal requires backup review and owner approval.

**Rationale**: A Terraform-owned lock can be destroyed before the server.
`prevent_destroy` cannot be injected into an AVM module at the caller and
does not universally protect configuration removal. Never claim it provides
the required independent protection. User approved separate lock ownership.
Existing teardown code has an early successful Terraform ownership return;
the new PostgreSQL guard must not be bypassed by that return.

**Alternatives considered**: IaC-owned locks alone fail this threat model.
Hook-only protection can be bypassed by direct provider execution.
Independent locks still permit privileged removal and leave a brief pre-lock
provisioning window; fail on missing lock/readiness, document recovery and test.
Resource data content survives a denial, but universal atomic teardown or
privileged deletion prevention is not promised.

Sources:
- [AVM resource-lock interface](https://azure.github.io/Azure-Verified-Modules/specs/tf/interfaces/#resource-locks)
- [Terraform lifecycle limits](https://developer.hashicorp.com/terraform/language/meta-arguments/lifecycle)

## 6. Discovery, documentation and evidence

**Decision**: Add only flat non-secret PostgreSQL keys under `agent-lz`;
preserve closed platform outputs v1. Central docs live in
Azure/AI-Landing-Zones. No bundled runtime is a new consumer and no runtime
manifest pin change follows from this feature.

**Rationale**: `contracts/platform-outputs-v1.schema.json` disallows extra
properties. Current output publisher and CI establish clear integration/test
points. Central source search found configuration/network/custom-app impact;
cost-planning is a redirect, so update consolidated sizing/cost guidance.

**Alternatives considered**: A new v2 output contract is unnecessary here.
Duplicating product docs or putting application schemas in this repo violates
ownership. Compilation and mock plans cannot substitute for live authorization,
source-IP, DNS and lock tests.

## Research exit

All design clarifications have selected behavior. Subscription policy/API
acceptance, regional SKU capacity, live DNS convergence, identity operations,
destructive-transition denial and partial-provision recovery are implementation
verification gates, not claims of already working infrastructure.

## Implementation verification notes

The requester authorized implementation and issue reconciliation on 2026-11-05,
but excluded Azure deployment/destructive acceptance. T039/T040 remain deferred.
CLI help checks corrected the real Azure boundary to `lock create --resource`,
`lock show --ids` and `postgres flexible-server microsoft-entra-admin list`.
No Azure command requiring a resource mutation was executed for validation.
The originally proposed PostgreSQL driver 3.3.8 could not be restored from the
configured package index; the official wheel endpoint also failed TLS through
both Python and Windows TLS. No TLS bypass or runtime fallback was introduced.
The selected explicit dependency is `psycopg[binary]==3.3.6`, available from the
configured index and matching both driver/binary versions used by the tests.
The utility Azure Identity pin is aligned with configuration's 1.27.0: the
combined CI requirements otherwise fail with incompatible exact pins. Combined
requirements resolve successfully after alignment. Live SQL remains deferred.

The broader compiled-foundation check caught ARM's native 64-output budget.
ADR-0039 records the selected shared post-provision transport: preserve every
old Bicep output, closed platform outputs v1 and existing consumers, while
verifying and persisting additive PostgreSQL azd metadata for both providers.
Terraform's extra native outputs are checked by the same adapter. See
`quickstart.md` for commands, evidence and the coordinated central-docs branch.
