"""Manually bind one managed identity to dedicated application-schema CRUD.

The operator initializes the schema and owns migrations. This utility neither
creates schemas nor changes their owners. Cross-database work is deliberately
restartable, not atomic: the principal transaction in postgres commits first.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import logging
import re
import subprocess
from typing import Callable
from urllib.parse import urlsplit

from azure.identity import AzureCliCredential
from azure.core.exceptions import AzureError
import psycopg
from psycopg import sql

from config.deployment import postgresql as pg

LOGGER = logging.getLogger(__name__)
TOKEN_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


def _reject_administrator_membership(run_az: Callable, group_id: str, application_id: str) -> None:
    path = f"/v1.0/groups/{group_id}/transitiveMembers"
    url = f"https://graph.microsoft.com{path}?$select=id&$top=999"
    seen = set()
    # Check every page: absence from one page does not establish non-membership.
    for _ in range(100):
        if url in seen:
            raise ValueError("Administrator membership pagination repeated; identity safety is unverified.")
        seen.add(url)
        document = pg._json(run_az, ["rest", "--method", "GET", "--url", url])
        rows = document.get("value") if isinstance(document, dict) else None
        if not isinstance(rows, list) or any(not isinstance(row, dict) or not row.get("id") for row in rows):
            raise ValueError("Administrator group membership could not be verified.")
        if any(pg.guid(row["id"], "directory member") == application_id.lower() for row in rows):
            raise ValueError("Application identity is a transitive member of the Entra administrator group.")
        next_url = document.get("@odata.nextLink")
        if next_url is None:
            return
        if not isinstance(next_url, str):
            raise ValueError("Invalid administrator membership continuation.")
        parsed = urlsplit(next_url)
        if (parsed.scheme != "https" or parsed.netloc.lower() != "graph.microsoft.com"
            or parsed.path != path or parsed.fragment):
            raise ValueError("Administrator membership continuation changed directory scope.")
        url = next_url
    raise ValueError("Administrator membership pagination limit exceeded; identity safety is unverified.")


@dataclass(frozen=True)
class Inputs:
    server_resource_id: str
    host: str
    database: str
    administrator_role: str
    application_object_id: str
    application_role: str
    schema: str
    ddl_owner_role: str

    def validate(self) -> tuple[str, str, str]:
        match = pg.SERVER_PATH.fullmatch(self.server_resource_id)
        if not match:
            raise ValueError("Invalid PostgreSQL server resource ID.")
        subscription = pg.guid(match[1], "subscription")
        if self.host != match[3].lower() + ".postgres.database.azure.com":
            raise ValueError("PostgreSQL host must match the canonical server hostname.")
        pg.guid(self.application_object_id, "application object ID")
        for name in ("database", "administrator_role", "application_role", "schema", "ddl_owner_role"):
            value = getattr(self, name)
            if not value or len(value.encode("utf-8")) > 63 or any(ord(char) < 32 for char in value):
                raise ValueError(f"{name} requires a PostgreSQL identifier of 1..63 bytes.")
        if self.database.lower() in {"postgres", "template0", "template1", "azure_maintenance", "azure_sys"}:
            raise ValueError("Bootstrap requires a dedicated application database.")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,62}", self.database):
            raise ValueError("Application database must match the native ARM/SQL identifier contract.")
        if self.schema.lower() in {"public", "information_schema"} or self.schema.lower().startswith("pg_"):
            raise ValueError("Bootstrap requires a dedicated application schema, not a shared/system schema.")
        if self.application_role in {self.administrator_role, self.ddl_owner_role} or self.application_role.lower().startswith(("pg_", "azure_")):
            raise ValueError("Application role cannot be an administrator/DDL owner/system role.")
        return subscription, match[2], match[3]


def verify_resources(inputs: Inputs, run_az: Callable) -> str:
    subscription, group, server_name = inputs.validate()
    account = pg._json(run_az, ["account", "show", "--subscription", subscription])
    if not isinstance(account, dict):
        raise ValueError("Invalid Azure account metadata.")
    tenant = pg.guid(account.get("tenantId"), "tenant")
    pg.verify_account(run_az, subscription, tenant)
    server = pg._json(run_az, ["resource", "show", "--ids", inputs.server_resource_id])
    if not isinstance(server, dict) or str(server.get("id", "")).lower() != inputs.server_resource_id.lower():
        raise ValueError("Server resource identity mismatch.")
    properties = server.get("properties") or {}
    auth = properties.get("authConfig") or {}
    if (properties.get("fullyQualifiedDomainName") != inputs.host or auth.get("activeDirectoryAuth") != "Enabled"
        or auth.get("passwordAuth") != "Disabled" or str(auth.get("tenantId", "")).lower() != tenant):
        raise ValueError("Server hostname/tenant/Entra-only authentication mismatch.")
    if properties.get("state") != "Ready":
        raise ValueError("Server is not Ready for manual bootstrap.")
    admins = pg._json(run_az, ["postgres", "flexible-server", "microsoft-entra-admin", "list", "--resource-group", group,
                              "--server-name", server_name, "--subscription", subscription])
    if not isinstance(admins, list) or len(admins) != 1:
        raise ValueError("Expected one configured Entra administrator.")
    admin = admins[0].get("properties", admins[0])
    if admin.get("principalName") != inputs.administrator_role or str(admin.get("tenantId", "")).lower() != tenant:
        raise ValueError("Configured administrator role/tenant mismatch.")
    admin_oid = pg.guid(admin.get("objectId"), "administrator object ID")
    if admin.get("principalType") not in {"User", "Group", "ServicePrincipal"} or admin_oid == inputs.application_object_id.lower():
        raise ValueError("Application identity cannot be the administrator.")
    pg.verify_principal(run_az, admin_oid, admin["principalType"], inputs.administrator_role)
    identity = pg.verify_principal(run_az, inputs.application_object_id, "ServicePrincipal")
    if identity.get("servicePrincipalType") != "ManagedIdentity":
        raise ValueError("Application object ID must identify a managed identity service principal.")
    if admin["principalType"] == "Group":
        _reject_administrator_membership(run_az, admin_oid, inputs.application_object_id)
    database_id = inputs.server_resource_id + "/databases/" + inputs.database
    database = pg._json(run_az, ["resource", "show", "--ids", database_id])
    if not isinstance(database, dict) or str(database.get("id", "")).lower() != database_id.lower():
        raise ValueError("Application database resource identity mismatch.")
    pg._lock(run_az, {"server": inputs.server_resource_id})
    return tenant


def _mapping(cursor, inputs: Inputs, tenant: str, *, create: bool) -> None:
    cursor.execute("SELECT rolename, principaltype, objectid::text, tenantid::text, isadmin FROM pgaadauth_list_principals(false)")
    rows = cursor.fetchall()
    matches = [row for row in rows if row[0] == inputs.application_role or str(row[2]).lower() == inputs.application_object_id.lower()]
    expected = (inputs.application_role, "service", inputs.application_object_id.lower(), tenant.lower(), False)
    if matches:
        if len(matches) != 1 or (matches[0][0], str(matches[0][1]).lower(), str(matches[0][2]).lower(), str(matches[0][3]).lower(), matches[0][4]) != expected:
            raise ValueError("Existing Entra principal tenant/OID/type/admin mapping mismatch.")
        return
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (inputs.application_role,))
    if cursor.fetchone():
        raise ValueError("Existing SQL role has no matching Entra principal; remapping is prohibited.")
    if not create:
        raise ValueError("Created Entra principal mapping was not read back.")
    cursor.execute("SELECT pgaadauth_create_principal_with_oid(%s, %s, 'service', false, false)",
                   (inputs.application_role, inputs.application_object_id))
    cursor.fetchone()
    _mapping(cursor, inputs, tenant, create=False)


def _role_safety(cursor, inputs: Inputs) -> None:
    cursor.execute(
        "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls "
        "FROM pg_roles WHERE rolname = %s", (inputs.application_role,))
    row = cursor.fetchone()
    if row is None or any(row):
        raise ValueError("Application SQL role is missing or privileged.")
    # Reject all role memberships, including NOINHERIT roles usable with SET ROLE.
    cursor.execute(
        "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=%s",
        (inputs.application_role,))
    if cursor.fetchone():
        raise ValueError("Application SQL role has inherited/SET ROLE privilege bypass.")
    cursor.execute(
        "SELECT 1 FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba WHERE r.rolname=%s "
        "UNION ALL SELECT 1 FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE r.rolname=%s "
        "UNION ALL SELECT 1 FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner WHERE r.rolname=%s "
        "UNION ALL SELECT 1 FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE r.rolname=%s "
        "UNION ALL SELECT 1 FROM pg_type t JOIN pg_roles r ON r.oid=t.typowner WHERE r.rolname=%s "
        "UNION ALL SELECT 1 FROM pg_extension e JOIN pg_roles r ON r.oid=e.extowner WHERE r.rolname=%s",
        (inputs.application_role,) * 6)
    if cursor.fetchone():
        raise ValueError("Application role owns a database/schema/object.")


def _grant(cursor, inputs: Inputs) -> None:
    _role_safety(cursor, inputs)
    cursor.execute("SELECT current_database(), current_user")
    database, current_user = cursor.fetchone()
    if database != inputs.database or current_user != inputs.administrator_role:
        raise ValueError("Connected database/administrator role mismatch.")
    cursor.execute(
        "SELECT r.rolname, pg_has_role(current_user, r.oid, 'MEMBER') "
        "FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname=%s", (inputs.schema,))
    row = cursor.fetchone()
    if row is None or row[0] != inputs.ddl_owner_role or not row[1]:
        raise ValueError("Operator must initialize schema under the actual authorized DDL owner; no reassignment.")
    cursor.execute(
        "SELECT 1 FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE r.rolname=%s",
        (inputs.application_role,))
    if cursor.fetchone():
        raise ValueError("Application role owns a schema.")
    cursor.execute(
        "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname=%s "
        "AND (r.rolname<>%s OR c.relkind IN ('v','m','f'))",
        (inputs.schema, inputs.ddl_owner_role))
    if cursor.fetchone():
        raise ValueError("Application objects require the actual DDL owner and base tables/sequences, not view/foreign wrappers.")
    # This is a dedicated fresh app DB. Do not silently modify unrelated/shared schemas.
    cursor.execute(
        "SELECT 1 FROM pg_namespace n WHERE n.nspname NOT IN (%s, 'public', 'information_schema') "
        "AND n.nspname NOT LIKE 'pg\\_%' ESCAPE '\\'", (inputs.schema,))
    if cursor.fetchone():
        raise ValueError("Shared/cross-schema database is not a bootstrap target.")
    cursor.execute(
        "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f')")
    if cursor.fetchone():
        raise ValueError("Shared public objects are not a bootstrap target.")
    cursor.execute(
        "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND p.prosecdef")
    if cursor.fetchone():
        raise ValueError("User SECURITY DEFINER functions/triggers are unsupported privilege bypasses.")
    app, schema, owner, db = map(sql.Identifier, (
        inputs.application_role, inputs.schema, inputs.ddl_owner_role, inputs.database))
    cursor.execute(sql.SQL("REVOKE CREATE, TEMPORARY ON DATABASE {} FROM PUBLIC").format(db))
    cursor.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    cursor.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(db, app))
    cursor.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(schema, app))
    cursor.execute(sql.SQL("REVOKE CREATE ON SCHEMA {} FROM PUBLIC").format(schema))
    cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(db, app))
    cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema, app))
    cursor.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM {}").format(schema, app))
    cursor.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA {} FROM {}").format(schema, app))
    cursor.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}").format(schema, app))
    cursor.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(schema, app))
    for kind, privileges in (("TABLES", "SELECT, INSERT, UPDATE, DELETE"), ("SEQUENCES", "USAGE, SELECT")):
        cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} REVOKE ALL ON " + kind + " FROM {}").format(owner, schema, app))
        cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT " + privileges + " ON " + kind + " TO {}").format(owner, schema, app))
    # Effective rights include PUBLIC/defaults, not just explicit ACLs.
    cursor.execute(
        "SELECT has_database_privilege(%s,%s,'CONNECT'), has_database_privilege(%s,%s,'CREATE'), "
        "has_database_privilege(%s,%s,'TEMP'), has_schema_privilege(%s,%s,'USAGE'), "
        "has_schema_privilege(%s,%s,'CREATE'), has_schema_privilege(%s,'public','CREATE')",
        (inputs.application_role, inputs.database) * 3 + (inputs.application_role, inputs.schema) * 2 + (inputs.application_role,))
    if cursor.fetchone() != (True, False, False, True, False, False):
        raise ValueError("Effective database/schema grants violate CRUD-only policy.")
    cursor.execute(
        "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=%s AND c.relkind IN ('r','p','v','m','f') AND "
        "(NOT (has_table_privilege(%s,c.oid,'SELECT') AND has_table_privilege(%s,c.oid,'INSERT') "
        "AND has_table_privilege(%s,c.oid,'UPDATE') AND has_table_privilege(%s,c.oid,'DELETE')) "
        "OR has_table_privilege(%s,c.oid,'TRUNCATE,REFERENCES,TRIGGER'))",
        (inputs.schema,) + (inputs.application_role,) * 5)
    if cursor.fetchone():
        raise ValueError("Effective table privileges violate CRUD-only policy.")
    cursor.execute(
        "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=%s AND c.relkind='S' AND "
        "(NOT (has_sequence_privilege(%s,c.oid,'USAGE') AND has_sequence_privilege(%s,c.oid,'SELECT')) "
        "OR has_sequence_privilege(%s,c.oid,'UPDATE'))",
        (inputs.schema,) + (inputs.application_role,) * 3)
    if cursor.fetchone():
        raise ValueError("Effective sequence privileges violate CRUD-only policy.")
    # Global default ACLs can add rights even when schema-specific defaults are
    # correct. Inspect effective owner defaults including PUBLIC, not only app ACLs.
    cursor.execute(
        "SELECT 1 FROM pg_default_acl d JOIN pg_roles owner ON owner.oid=d.defaclrole "
        "LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace "
        "CROSS JOIN LATERAL aclexplode(d.defaclacl) a "
        "WHERE owner.rolname=%s AND (d.defaclnamespace=0 OR n.nspname=%s) "
        "AND (a.grantee=0 OR a.grantee=(SELECT oid FROM pg_roles WHERE rolname=%s)) "
        "AND ((d.defaclobjtype='r' AND a.privilege_type NOT IN ('SELECT','INSERT','UPDATE','DELETE')) "
        "OR (d.defaclobjtype='S' AND a.privilege_type NOT IN ('USAGE','SELECT')) OR a.is_grantable)",
        (inputs.ddl_owner_role, inputs.schema, inputs.application_role))
    if cursor.fetchone():
        raise ValueError("DDL owner's global/PUBLIC future defaults permit a privilege bypass.")


def bootstrap(inputs: Inputs, *, run_az: Callable = pg._run_az,
              credential_factory: Callable = AzureCliCredential,
              connect: Callable = psycopg.connect) -> None:
    tenant = verify_resources(inputs, run_az)
    credential = credential_factory(tenant_id=tenant, process_timeout=30)
    try:
        # Never pass a DSN containing this token; never persist or log parameters.
        token = credential.get_token(TOKEN_SCOPE).token
        parameters = dict(host=inputs.host, port=5432, user=inputs.administrator_role,
                          password=token, sslmode="verify-full", connect_timeout=15,
                          options="-c search_path=pg_catalog,public -c statement_timeout=30000 -c lock_timeout=10000")
        with connect(dbname="postgres", **parameters) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user")
                if cursor.fetchone() != ("postgres", inputs.administrator_role):
                    raise ValueError("Connected administrator/postgres database mismatch.")
                _mapping(cursor, inputs, tenant, create=True)
                _role_safety(cursor, inputs)
        with connect(dbname=inputs.database, **parameters) as connection:
            with connection.cursor() as cursor:
                _mapping(cursor, inputs, tenant, create=False)
                _grant(cursor, inputs)
    finally:
        credential.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in Inputs.__dataclass_fields__:
        parser.add_argument("--" + name.replace("_", "-"), required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        bootstrap(Inputs(**vars(args)))
    except ValueError as exc:
        LOGGER.error("PostgreSQL bootstrap rejected: %s", exc)
        return 1
    except (psycopg.Error, AzureError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        # Driver/credential exceptions may embed connection data: log only kind.
        LOGGER.error("PostgreSQL bootstrap failed (%s); inspect permissions/network and rerun the same binding.", type(exc).__name__)
        return 1
    LOGGER.info("PostgreSQL managed-identity CRUD binding verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
