"""Exercise real psycopg SQL composition with injected ARM/token/cursor outcomes."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from psycopg import sql

from util import postgresql_bootstrap as boot
from tests.test_postgresql_deployment import Client, ID, ENV, TENANT, ADMIN

OID = "44444444-4444-4444-4444-444444444444"
INPUT = boot.Inputs(ID, ENV["POSTGRESQL_HOST"], "agentlz", "fixture-admin",
                    OID, 'app"role', 'app"schema', "ddl-owner")


class Azure(Client):
    def __call__(self, args, **kwargs):
        if args[:2] == ["rest", "--method"]:
            self.calls.append(args)
            return '{"value":[]}'
        if args[:3] == ["ad", "sp", "show"]:
            self.calls.append(args)
            import json
            return json.dumps({"id": OID, "servicePrincipalType": "ManagedIdentity"})
        return super().__call__(args, **kwargs)


def test_administrator_group_membership_is_checked_transitively_across_pages():
    import json
    calls = []
    path = f"https://graph.microsoft.com/v1.0/groups/{ADMIN}/transitiveMembers"

    def graph(args):
        calls.append(args)
        return json.dumps({"value": [{"id": ADMIN}], "@odata.nextLink": path + "?$skiptoken=next"} if len(calls) == 1
                          else {"value": [{"id": OID}]})

    with pytest.raises(ValueError, match="transitive member"):
        boot.verify_resources(INPUT, lambda args, **kwargs: graph(args) if args[0] == "rest" else Azure()(args, **kwargs))
    assert len(calls) == 2
    assert all(call[:3] == ["rest", "--method", "GET"] for call in calls)


@pytest.mark.parametrize("response", [
    {}, {"value": "invalid"}, {"value": [{}]},
    {"value": [], "@odata.nextLink": "https://evil.example/next"},
    {"value": [], "@odata.nextLink": f"https://graph.microsoft.com/v1.0/groups/{OID}/transitiveMembers"},
])
def test_unverified_administrator_membership_fails_closed(response):
    import json
    with pytest.raises(ValueError, match="membership"):
        boot._reject_administrator_membership(lambda args: json.dumps(response), ADMIN, OID)


def test_administrator_membership_continuation_cycle_fails_closed():
    import json
    url = f"https://graph.microsoft.com/v1.0/groups/{ADMIN}/transitiveMembers?$select=id&$top=999"
    with pytest.raises(ValueError, match="pagination repeated"):
        boot._reject_administrator_membership(
            lambda args: json.dumps({"value": [], "@odata.nextLink": url}), ADMIN, OID)


def test_incomplete_administrator_membership_is_bounded_and_never_accepted():
    import json
    calls = []

    def graph(args):
        calls.append(args)
        url = f"https://graph.microsoft.com/v1.0/groups/{ADMIN}/transitiveMembers?$skiptoken={len(calls)}"
        return json.dumps({"value": [], "@odata.nextLink": url})

    with pytest.raises(ValueError, match="pagination limit"):
        boot._reject_administrator_membership(graph, ADMIN, OID)
    assert len(calls) == 100


def test_unreadable_administrator_membership_stops_before_token_or_sql():
    def directory(args, **kwargs):
        if args[0] == "rest":
            raise RuntimeError("Membership read denied")
        return Azure()(args, **kwargs)

    with pytest.raises(RuntimeError, match="Membership read denied"):
        boot.bootstrap(INPUT, run_az=directory,
                       credential_factory=lambda **kwargs: pytest.fail("No token may be requested"),
                       connect=lambda **kwargs: pytest.fail("No SQL may run"))


class Cursor:
    """Each result is a real query outcome; unexpected extra queries fail."""
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, values=None):
        rendered = query.as_string() if isinstance(query, sql.Composable) else query
        self.calls.append((rendered, values))
        if rendered.startswith(("SELECT", "WITH")):
            assert self.outcomes, rendered
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            self.result = outcome

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


class Connection:
    def __init__(self, cursor):
        self.value = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, kind, *args):
        self.committed = kind is None

    def cursor(self):
        return self.value


class Credential:
    def __init__(self):
        self.closed = False
        self.scopes = []

    def get_token(self, scope):
        self.scopes.append(scope)
        return SimpleNamespace(token="memory-only-token")

    def close(self):
        self.closed = True


def mapping():
    return [(INPUT.application_role, "service", OID, TENANT, False)]


def role_results():
    return [(False,) * 5, None, None]


def grant_results():
    return [*role_results(), ("agentlz", "fixture-admin"), ("ddl-owner", True),
            None, None, None, None, None,
            (True, False, False, True, False, False), None, None, None]


@pytest.mark.parametrize("field,value", [
    ("host", "evil.example"), ("database", "postgres"), ("schema", "public"),
    ("application_object_id", "not-guid"), ("application_role", "ddl-owner"),
    ("application_role", "fixture-admin"), ("schema", "a" * 64),
    ("schema", "null\0name"), ("server_resource_id", ID + "/bad"),
])
def test_invalid_arguments_reject_before_azure(field, value):
    with pytest.raises(ValueError):
        replace(INPUT, **{field: value}).validate()


def test_create_readback_and_repeat_use_exact_mapping():
    cursor = Cursor([[], None, ("created",), mapping()])
    boot._mapping(cursor, INPUT, TENANT, create=True)
    creation = next(call for call in cursor.calls if "create_principal" in call[0])
    assert creation[1] == (INPUT.application_role, OID)
    assert "'service', false, false" in creation[0]
    rerun = Cursor([mapping()])
    boot._mapping(rerun, INPUT, TENANT, create=True)
    assert len(rerun.calls) == 1


@pytest.mark.parametrize("row", [
    ("other-role", "service", OID, TENANT, False),
    (INPUT.application_role, "service", ADMIN, TENANT, False),
    (INPUT.application_role, "user", OID, TENANT, False),
    (INPUT.application_role, "service", OID, ADMIN, False),
    (INPUT.application_role, "service", OID, TENANT, True),
])
def test_mapping_conflicts_never_remap(row):
    cursor = Cursor([[row]])
    with pytest.raises(ValueError, match="mapping"):
        boot._mapping(cursor, INPUT, TENANT, create=True)
    assert len(cursor.calls) == 1


def test_unmapped_existing_sql_role_rejected():
    with pytest.raises(ValueError, match="remapping"):
        boot._mapping(Cursor([[], (1,)]), INPUT, TENANT, create=True)


@pytest.mark.parametrize("outcomes,match", [
    ([(True, False, False, False, False)], "privileged"),
    ([(False,) * 5, (1,)], "inherited"),
    ([(False,) * 5, None, (1,)], "owns a database"),
])
def test_role_privilege_bypass_is_rejected(outcomes, match):
    with pytest.raises(ValueError, match=match):
        boot._role_safety(Cursor(outcomes), INPUT)


def test_grants_quote_identifiers_and_target_actual_owner_defaults():
    cursor = Cursor(grant_results())
    boot._grant(cursor, INPUT)
    assert not cursor.outcomes
    statements = "\n".join(query for query, _ in cursor.calls)
    assert '"app""schema"' in statements and '"app""role"' in statements
    assert 'FOR ROLE "ddl-owner" IN SCHEMA "app""schema"' in statements
    assert "REVOKE CREATE, TEMPORARY" in statements
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in statements
    assert "GRANT USAGE, SELECT ON ALL SEQUENCES" in statements
    assert "REASSIGN" not in statements and "GRANT CREATE" not in statements


@pytest.mark.parametrize("index,outcome,match", [
    (4, ("wrong-owner", True), "DDL owner"),
    (5, (1,), "owns a schema"),
    (6, (1,), "objects"),
    (7, (1,), "cross-schema"),
    (8, (1,), "public objects"),
    (9, (1,), "SECURITY DEFINER"),
    (10, (True, True, False, True, False, False), "grants"),
    (11, (1,), "table privileges"),
    (12, (1,), "sequence privileges"),
    (13, (1,), "future defaults"),
])
def test_effective_grant_failures_roll_back(index, outcome, match):
    results = grant_results()
    results[index] = outcome
    with pytest.raises(ValueError, match=match):
        boot._grant(Cursor(results), INPUT)


def test_bootstrap_token_only_in_connect_parameters_and_two_transactions():
    cred = Credential()
    cursors = [Cursor([("postgres", "fixture-admin"), mapping(), *role_results()]),
               Cursor([mapping(), *grant_results()])]
    connections = [Connection(c) for c in cursors]
    calls = []

    def connect(**kwargs):
        calls.append(kwargs)
        return connections[len(calls) - 1]

    factory_calls = []
    boot.bootstrap(INPUT, run_az=Azure(),
                   credential_factory=lambda **kwargs: factory_calls.append(kwargs) or cred, connect=connect)
    assert factory_calls == [{"tenant_id": TENANT, "process_timeout": 30}]
    assert cred.scopes == [boot.TOKEN_SCOPE] and cred.closed
    assert [call["dbname"] for call in calls] == ["postgres", "agentlz"]
    assert all(call["password"] == "memory-only-token" and call["sslmode"] == "verify-full"
               and call["connect_timeout"] == 15 for call in calls)
    assert all(connection.committed for connection in connections)
    assert "memory-only-token" not in repr([c.calls for c in cursors])


def test_partial_cross_database_failure_preserves_verified_role_for_rerun():
    first = Connection(Cursor([("postgres", "fixture-admin"), [], None, ("created",), mapping(), *role_results()]))
    second = Connection(Cursor([mapping(), *role_results(), ("wrong", "fixture-admin")]))
    calls = []
    cred = Credential()

    def connect(**kwargs):
        calls.append(kwargs)
        return first if len(calls) == 1 else second

    with pytest.raises(ValueError, match="database"):
        boot.bootstrap(INPUT, run_az=Azure(), credential_factory=lambda **kwargs: cred, connect=connect)
    assert first.committed and not second.committed and cred.closed
    rerun = Cursor([mapping()])
    boot._mapping(rerun, INPUT, TENANT, create=True)
    assert all("create_principal" not in query for query, _ in rerun.calls)


def test_application_oid_must_be_managed_identity():
    azure = Azure()

    def mismatch(args, **kwargs):
        if args[:3] == ["ad", "sp", "show"]:
            return '{"id":"' + OID + '","servicePrincipalType":"Application"}'
        return azure(args, **kwargs)

    with pytest.raises(ValueError, match="managed identity"):
        boot.verify_resources(INPUT, mismatch)


@pytest.mark.parametrize("kind", ["account", "server", "administrator", "database", "directory"])
def test_resource_and_directory_identity_mismatches_reject_before_token(kind):
    import json
    azure = Azure()

    def mismatch(args, **kwargs):
        response = json.loads(azure(args, **kwargs))
        if kind == "account" and args[:2] == ["account", "show"]:
            response["id"] = ADMIN
        if kind == "server" and args[:2] == ["resource", "show"] and not args[args.index("--ids") + 1].endswith("/databases/agentlz"):
            response["properties"]["authConfig"]["tenantId"] = ADMIN
        if kind == "administrator" and args[:3] == ["postgres", "flexible-server", "microsoft-entra-admin"]:
            response[0]["principalName"] = "wrong-admin"
        if kind == "database" and args[:2] == ["resource", "show"] and args[args.index("--ids") + 1].endswith("/databases/agentlz"):
            response["id"] = ID + "/databases/wrong"
        if kind == "directory" and args[:3] == ["ad", "sp", "show"]:
            response["id"] = ADMIN
        return json.dumps(response)

    with pytest.raises(ValueError):
        boot.verify_resources(INPUT, mismatch)


def test_statement_and_connection_timeouts_and_secret_safe_auth_failure(monkeypatch, caplog):
    from azure.core.exceptions import ClientAuthenticationError
    args = [part for name in INPUT.__dataclass_fields__ for part in ("--" + name.replace("_", "-"), getattr(INPUT, name))]
    monkeypatch.setattr(boot, "bootstrap", lambda inputs: (_ for _ in ()).throw(ClientAuthenticationError("memory-only-token")))
    assert boot.main(args) == 1
    assert "memory-only-token" not in caplog.text
    assert "ClientAuthenticationError" in caplog.text


def test_cli_driver_error_does_not_log_token(monkeypatch, caplog):
    import psycopg
    monkeypatch.setattr(boot, "bootstrap", lambda inputs: (_ for _ in ()).throw(psycopg.OperationalError("memory-only-token")))
    args = [part for name in INPUT.__dataclass_fields__ for part in ("--" + name.replace("_", "-"), getattr(INPUT, name))]
    assert boot.main(args) == 1
    assert "memory-only-token" not in caplog.text
    assert "OperationalError" in caplog.text
