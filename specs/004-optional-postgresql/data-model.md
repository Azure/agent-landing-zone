# Data model and lifecycle

This models infrastructure/configuration, not a bundled runtime schema.
See [contracts/postgresql.md](contracts/postgresql.md).

## Selection and immutable binding

Fields: enabled Boolean, provider, subscription, application RG, server ID/name,
database, network mode, ACA environment/subnet, administrator OID/tenant and
independent lock ID. Derive Basic NAT from enabled && !isolation and PE from
enabled && isolation. Basic requires fresh workload-profiles ACA.

Record non-secret binding under selected `.azure/<environment>/`, following
existing binding conventions. Verify live identity/ownership; do not trust an
environment variable containing an ARM ID alone. Reject malformed Booleans,
incompatible existing ACA, unsafe adoption, network-mode switch, immutable
replacement or disabling a provisioned binding. Missing/corrupt records
require explicit recovery, not silent adoption or destruction permission.
The implementation uses `postgresql-binding.json` schemaVersion1 with the
immutable binding, SHA256 fingerprint and ready Boolean. Intent is atomically
written before IaC; readiness is false until live server/database/admin checks
and independent lock readback succeed. Retained `.env` PG outputs are also
teardown/missing-state evidence, even when a caller filters its environment.
Location is part of the immutable network context.
Generic ARM resource inventories are only inventory, not authoritative ACA
profile/subnet metadata: existing ACA entries are read back individually.
Known non-ready creation intent can resume missing admin/database children;
conflicting existing principals/ownership still fail, and complete protection/
discovery always require Ready server, exact administrator and application DB.

## Server/database

Fields: name, region, tier/SKU, engine, storage GiB, backup days, HA,
geo-backup, auto-grow, Entra auth/admin, database name, tags and canonical FQDN.
Defaults: engine16, Burstable/Standard_B1ms, 32 GiB, backup7, HA/geo/auto-grow
off. Validate names, supported sizing/HA/region, backup7..35, versions and
ownership. No database/admin resources when disabled.

## Connectivity

Basic: ACA -> delegated subnet -> dedicated Standard NAT/public IPv4 ->
PostgreSQL exact-IP firewall. Additional operator IPv4/CIDR becomes inclusive
start/end ranges. Prohibit all-address ranges and Azure-services 0.0.0.0 rules.
Never use ingress IP as outbound IP. Forced NVA/firewall default routing
invalidates NAT SNAT assumptions and fails preflight.

NAT/IP is produced before server/firewall consumption; associated subnet before
ACA environment. No graph dependency on application runtime or SQL bootstrap.

Isolated: server -> application PE/subnet -> private DNS resolution.
Zone is `privatelink.postgres.database.azure.com`; ownership is managed,
explicit existing-zone ID, or policy-managed, with no competing owners.
No delegated PostgreSQL server subnet.

## SQL binding

Fields: service-principal object ID, SQL role, database, app schema, actual
DDL owner, tenant and non-admin effective grants.
Operator initializes the schema with the declared owner; bootstrap verifies
rather than reassigning an existing owner. Role creation runs in `postgres`;
grants/default privileges run in the application DB.

Reuse exact role/OID/type/tenant matches; reject conflicts and excessive
inherited privileges. Grant CONNECT, schema USAGE, table CRUD and sequence
USAGE/SELECT; defaults apply to objects created by the declared DDL owner.
App cannot own database/schema, create objects/roles, administer the server
or inherit a privilege bypass. Check PUBLIC privileges on the fresh database,
not unrelated/shared databases.
The conservative utility accepts dedicated base-table/sequence schemas, not
view/materialized-view/foreign wrappers or user SECURITY DEFINER functions/
triggers. It rejects ownership of objects and role memberships/SET ROLE paths
in both connected databases, rather than reassigning or silently adopting them.

Identifiers use driver quoting; values are bound. Grant updates can be
transactional within one DB; two-database bootstrap is not advertised as atomic.

## Protection/readiness

```text
absent -> fresh selection verified -> provisioned/unprotected
       -> independent lock verified -> discovery published/ready
       -> manual bootstrap verified -> app usable
```

Failure never advances readiness. Enabled same-binding recovery reruns are
supported. Disable/replacement/down transition to blocked, not deleted.
Lock has deterministic name, exact server scope, CanNotDelete level and
lifecycle owner; neither provider owns/removes it. Intentional deletion is
approved operator work. A privileged operator can still bypass protection.

## Discovery

Host, port, database, TLS and auth mode are flat agent-lz keys only after
resource/lock verification. No credentials, SQL grants or global application
username are published. Platform outputs v1 remains unchanged.
