"""Provider-neutral PostgreSQL input, binding and protection regressions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.deployment import postgresql as pg

SUB = "11111111-1111-1111-1111-111111111111"
TENANT = "22222222-2222-2222-2222-222222222222"
ADMIN = "33333333-3333-3333-3333-333333333333"
ID = f"/subscriptions/{SUB}/resourceGroups/rg-fixture/providers/Microsoft.DBforPostgreSQL/flexibleServers/pg-fixture"
ENV = {
    "AZURE_ENV_NAME": "fixture", "AZURE_SUBSCRIPTION_ID": SUB,
    "AZURE_TENANT_ID": TENANT, "AZURE_RESOURCE_GROUP": "rg-fixture",
    "NETWORK_ISOLATION": "false", "POSTGRESQL_SERVER_RESOURCE_ID": ID,
    "POSTGRESQL_HOST": "pg-fixture.postgres.database.azure.com",
    "POSTGRESQL_DATABASE_NAME": "agentlz", "POSTGRESQL_PORT": "5432",
}
INPUTS = {
    "deployPostgreSql": True, "networkIsolation": False, "deployContainerEnv": True,
    "postgreSqlServerName": "pg-fixture",
    "postgreSqlAdministratorObjectId": ADMIN,
    "postgreSqlAdministratorPrincipalName": "fixture-admin",
    "postgreSqlAdministratorPrincipalType": "Group",
}
FRESH_ENV = {key: value for key, value in ENV.items() if not key.startswith("POSTGRESQL_")}


def test_disabled_defaults_and_unrelated_settings_do_not_enable():
    assert pg.resolve_inputs({}, {})["deployPostgreSql"] is False
    assert pg.resolve_inputs({"postgreSqlVersion": "16"}, {})["deployPostgreSql"] is False
    result = pg.resolve_inputs({}, {})
    result["postgreSqlAllowedIpRanges"].append("203.0.113.1")
    assert pg.resolve_inputs({}, {})["postgreSqlAllowedIpRanges"] == []


@pytest.mark.parametrize("selection", ["yes", "1", "", "invalid"])
def test_enablement_is_strict(selection):
    with pytest.raises(ValueError, match="deployPostgreSql"):
        pg.resolve_inputs({}, {"DEPLOY_POSTGRESQL": selection})


def test_inputs_resolve_env_and_defaults_once():
    result = pg.resolve_inputs(INPUTS, {"POSTGRESQL_STORAGE_SIZE_GB": "64"})
    assert result["postgreSqlStorageSizeGb"] == 64
    assert result["postgreSqlHighAvailability"] == "Disabled"
    assert result["postgreSqlVersion"] == "16"
    assert result["postgreSqlGeoRedundantBackup"] is False
    assert result["postgreSqlStorageAutoGrow"] is False


def test_generated_server_name_uses_shared_catalog_and_explicit_names_bypass_it(tmp_path, monkeypatch):
    catalog = tmp_path / "infra" / "shared" / "abbreviations.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(json.dumps({"databases": {"postgreSQLDatabase": "rel-"}}), encoding="utf-8")
    monkeypatch.setattr(pg, "find_repo_root", lambda: tmp_path)
    source = {key: value for key, value in INPUTS.items() if key != "postgreSqlServerName"}
    generated = pg.resolve_inputs(source, FRESH_ENV)["postgreSqlServerName"]
    assert generated.startswith("rel-")
    assert pg.resolve_inputs(source, FRESH_ENV)["postgreSqlServerName"] == generated
    catalog.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="shared naming catalog"):
        pg.resolve_inputs(source, FRESH_ENV)
    assert pg.resolve_inputs(INPUTS, FRESH_ENV)["postgreSqlServerName"] == INPUTS["postgreSqlServerName"]


@pytest.mark.parametrize("changes,match", [
    ({"postgreSqlHighAvailability": "ZoneRedundant"}, "Burstable"),
    ({"postgreSqlBackupRetentionDays": 6}, "backup"),
    ({"postgreSqlStorageSizeGb": 31}, "storage"),
    ({"postgreSqlVersion": "11"}, "version"),
    ({"postgreSqlAdministratorObjectId": ""}, "Administrator"),
    ({"deployContainerEnv": False}, "Container"),
    ({"postgreSqlAllowedIpRanges": ["0.0.0.0/0"]}, "range"),
    ({"postgreSqlAllowedIpRanges": ["0.0.0.0"]}, "range"),
    ({"postgreSqlAllowedIpRanges": ["::1"]}, "IPv4"),
])
def test_invalid_enabled_inputs(changes, match):
    with pytest.raises(ValueError, match=match):
        pg.resolve_inputs({**INPUTS, **changes}, {})


def test_firewall_normalizes_explicit_ranges():
    assert pg.firewall_ranges(["203.0.113.8", "198.51.100.17/24"]) == [
        ("203.0.113.8", "203.0.113.8"), ("198.51.100.0", "198.51.100.255"),
    ]


def test_isolated_postgresql_does_not_require_container_apps():
    result = pg.resolve_inputs({**INPUTS, "networkIsolation": True, "deployContainerEnv": False}, {})
    assert result["deployPostgreSql"] is True


def test_protection_hydrates_missing_bicep_outputs_from_verified_intent(tmp_path):
    client = Client()
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)
    settings = pg.protect(FRESH_ENV, tmp_path, run_az=client)
    assert settings["AGENTLZ_POSTGRESQL_HOST"] == ENV["POSTGRESQL_HOST"]
    assert pg.discovery_settings(FRESH_ENV, tmp_path, run_az=client) == settings
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)


def test_fresh_resource_group_does_not_require_existing_arm_inventory(tmp_path):
    client = Client()

    def missing_group(args, **kwargs):
        if args[:2] == ["group", "exists"]:
            return "false"
        if args[:2] == ["resource", "list"]:
            raise AssertionError("A fresh Terraform resource group does not exist yet.")
        return client(args, **kwargs)

    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "terraform", run_az=missing_group)
    assert pg.binding_path(tmp_path, ENV).exists()


def test_bicep_tenant_is_resolved_from_selected_subscription_when_not_exported(tmp_path):
    client = Client()
    env = {key: value for key, value in FRESH_ENV.items() if key != "AZURE_TENANT_ID"}
    pg.preflight(INPUTS, env, tmp_path, "bicep", run_az=client)
    record = json.loads(pg.binding_path(tmp_path, env).read_text())
    assert record["binding"]["tenant"] == TENANT
    assert pg.protect(env, tmp_path, run_az=client)["AGENTLZ_POSTGRESQL_AUTH_MODE"] == "entra"


def test_explicit_tenant_must_match_selected_subscription_before_intent(tmp_path):
    with pytest.raises(ValueError, match="tenant"):
        pg.preflight(INPUTS, {**FRESH_ENV, "AZURE_TENANT_ID": ADMIN}, tmp_path, "bicep", run_az=Client())
    assert not pg.binding_path(tmp_path, ENV).exists()


def test_native_isolation_selection_does_not_require_a_duplicate_env_flag(tmp_path):
    client = Client()
    env = {key: value for key, value in FRESH_ENV.items() if key != "NETWORK_ISOLATION"}
    client.server["properties"]["network"]["publicNetworkAccess"] = "Disabled"
    pg.preflight({**INPUTS, "networkIsolation": True}, env, tmp_path, "bicep", run_az=client)
    pg.protect(env, tmp_path, run_az=client)
    assert pg.environment_outputs(env, tmp_path, run_az=client)["CONTAINER_APPS_POSTGRESQL_EGRESS_IP"] == ""


@pytest.mark.parametrize("isolated", [False, True])
def test_verified_metadata_persists_without_bicep_root_outputs(tmp_path, isolated):
    client = Client()
    env = {**FRESH_ENV, "NETWORK_ISOLATION": str(isolated).lower()}
    client.server["properties"]["network"]["publicNetworkAccess"] = "Disabled" if isolated else "Enabled"
    pg.preflight({**INPUTS, "networkIsolation": isolated}, env, tmp_path, "bicep", run_az=client)
    pg.protect(env, tmp_path, run_az=client)
    client.exists = True
    prefix = f"/subscriptions/{SUB}/resourceGroups/rg-fixture/providers/Microsoft.Network/"
    subnet_id = client.aca["properties"]["vnetConfiguration"]["infrastructureSubnetId"]
    nat_id = prefix + "natGateways/ng-aca-postgresql-fixture"
    address_id = prefix + "publicIPAddresses/pip-aca-postgresql-fixture"
    resources = {
        subnet_id: {"id": subnet_id, "properties": {"natGateway": {"id": nat_id}}},
        nat_id: {"id": nat_id, "sku": {"name": "Standard"}, "tags": {"azd-env-name": "fixture"},
                 "properties": {"publicIpAddresses": [{"id": address_id}]}},
        address_id: {"id": address_id, "sku": {"name": "Standard"}, "tags": {"azd-env-name": "fixture"},
                     "properties": {"publicIPAllocationMethod": "Static", "ipAddress": "203.0.113.8"}},
    }

    def metadata(args, **kwargs):
        if args[:2] == ["resource", "show"]:
            resource_id = args[args.index("--ids") + 1]
            if resource_id in resources:
                return json.dumps(resources[resource_id])
        return client(args, **kwargs)

    values = pg.environment_outputs(env, tmp_path, run_az=metadata)
    assert values == {**{key: ENV[key] for key in ENV if key.startswith("POSTGRESQL_")},
                      "CONTAINER_APPS_POSTGRESQL_EGRESS_IP": "" if isolated else "203.0.113.8"}
    calls = []
    pg.persist_outputs(env, tmp_path, values, run_azd=lambda root, args: calls.append((root, args)))
    assert len(calls) == 5
    assert all(root == tmp_path and args[-3:] == ["--environment", "fixture", "--no-prompt"] for root, args in calls)
    if not isolated:
        for value in ("ReadOnly", "Dynamic"):
            resources[address_id]["properties"]["publicIPAllocationMethod"] = value
            with pytest.raises(ValueError, match="allocation"):
                pg.environment_outputs(env, tmp_path, run_az=metadata)
        resources[address_id]["properties"]["publicIPAllocationMethod"] = "Static"
        with pytest.raises(ValueError, match="egress output"):
            pg.environment_outputs({**env, "CONTAINER_APPS_POSTGRESQL_EGRESS_IP": "203.0.113.9"},
                                   tmp_path, run_az=metadata)
        resources[nat_id]["tags"]["azd-env-name"] = "other"
        with pytest.raises(ValueError, match="ownership"):
            pg.environment_outputs(env, tmp_path, run_az=metadata)


def test_metadata_persistence_failure_is_explicit(tmp_path):
    from config.deployment.resource_groups import ResourceGroupError

    def failure(root, args):
        raise ResourceGroupError("azd unavailable")

    with pytest.raises(RuntimeError, match="persist verified PostgreSQL"):
        pg.persist_outputs(ENV, tmp_path, {"POSTGRESQL_HOST": ENV["POSTGRESQL_HOST"]}, run_azd=failure)


@pytest.mark.parametrize("enabled", [False, True])
def test_protection_cli_persists_only_verified_enabled_metadata(tmp_path, monkeypatch, enabled):
    events = []
    values = {"POSTGRESQL_HOST": ENV["POSTGRESQL_HOST"]}

    def protect(env, root):
        assert root == tmp_path
        events.append("protect")
        return {"AGENTLZ_POSTGRESQL_HOST": ENV["POSTGRESQL_HOST"]} if enabled else {}

    def metadata(env, root):
        assert root == tmp_path
        events.append("verify")
        return values

    def persist(env, root, result):
        assert root == tmp_path and result == values
        events.append("persist")

    monkeypatch.setattr(pg, "protect", protect)
    monkeypatch.setattr(pg, "environment_outputs", metadata)
    monkeypatch.setattr(pg, "persist_outputs", persist)
    assert pg.main(["protect", "--azure-dir", str(tmp_path)]) == 0
    assert events == (["protect", "verify", "persist"] if enabled else ["protect"])


def test_protection_cli_never_persists_failed_readback(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(pg, "protect", lambda env, root: {"AGENTLZ_POSTGRESQL_PORT": "5432"})

    def fail(env, root):
        raise ValueError("NAT ownership mismatch")

    monkeypatch.setattr(pg, "environment_outputs", fail)
    monkeypatch.setattr(pg, "persist_outputs", lambda *args: pytest.fail("No metadata may be persisted"))
    assert pg.main(["protect", "--azure-dir", str(tmp_path)]) == 1
    assert "NAT ownership mismatch" in caplog.text


class Client:
    def __init__(self):
        self.calls = []
        self.exists = False
        self.aca = {
            "id": f"/subscriptions/{SUB}/resourceGroups/rg-fixture/providers/Microsoft.App/managedEnvironments/aca-fixture",
            "name": "aca-fixture", "tags": {"azd-env-name": "fixture"},
            "properties": {"workloadProfiles": [{"name": "Consumption", "workloadProfileType": "Consumption"}],
                           "vnetConfiguration": {"infrastructureSubnetId":
                               f"/subscriptions/{SUB}/resourceGroups/rg-fixture/providers/Microsoft.Network/virtualNetworks/vnet/subnets/aca"}},
        }
        self.server = {
            "id": ID, "name": "pg-fixture",
            "tags": {"azd-env-name": "fixture"},
            "properties": {
                "state": "Ready",
                "fullyQualifiedDomainName": ENV["POSTGRESQL_HOST"],
                "authConfig": {"activeDirectoryAuth": "Enabled", "passwordAuth": "Disabled", "tenantId": TENANT},
                "network": {"publicNetworkAccess": "Enabled"},
            },
        }

    def __call__(self, args, *, required=True):
        self.calls.append(args)
        if args[:2] == ["account", "show"]:
            return json.dumps({"id": SUB, "tenantId": TENANT})
        if args[:3] == ["ad", "group", "show"]:
            return json.dumps({"id": ADMIN, "displayName": "fixture-admin"})
        if args[:3] == ["postgres", "flexible-server", "microsoft-entra-admin"]:
            return json.dumps([{"objectId": ADMIN, "tenantId": TENANT,
                                "principalName": "fixture-admin", "principalType": "Group"}])
        if args[:2] == ["group", "exists"]:
            return "true"
        if args[:2] == ["resource", "list"]:
            kind = args[args.index("--resource-type") + 1]
            if not self.exists:
                return "[]"
            return json.dumps([self.server] if kind.endswith("flexibleServers")
                              else [{"id": self.aca["id"], "name": self.aca["name"]}])
        if args[:2] == ["resource", "show"]:
            if args[args.index("--ids") + 1].endswith("/databases/agentlz"):
                return json.dumps({"id": ID + "/databases/agentlz", "name": "agentlz"})
            if args[args.index("--ids") + 1] == self.aca["id"]:
                return json.dumps(self.aca)
            return json.dumps(self.server)
        if args[:2] in (["lock", "create"], ["lock", "show"]):
            return json.dumps({"id": ID + "/providers/Microsoft.Authorization/locks/" + pg.LOCK_NAME,
                               "properties": {"level": "CanNotDelete"}})
        raise AssertionError(args)


def test_disabled_preflight_is_no_cloud_no_state(tmp_path):
    client = Client()
    disabled = {key: value for key, value in ENV.items() if not key.startswith("POSTGRESQL_")}
    pg.preflight({"deployPostgreSql": False}, disabled, tmp_path, "bicep", run_az=client)
    assert client.calls == []
    assert not list(tmp_path.rglob("*.json"))


def test_fresh_intent_protection_and_rerun(tmp_path):
    client = Client()
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "terraform", run_az=client)
    client.exists = True
    settings = pg.protect(ENV, tmp_path, run_az=client)
    assert settings["AGENTLZ_POSTGRESQL_HOST"] == ENV["POSTGRESQL_HOST"]
    pg.preflight(INPUTS, ENV, tmp_path, "terraform", run_az=client)
    pg.protect(ENV, tmp_path, run_az=client)
    assert pg.binding_path(tmp_path, ENV).is_file()


def test_disable_and_mode_replacement_are_blocked(tmp_path):
    client = Client()
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)
    with pytest.raises(ValueError, match="disable"):
        pg.preflight({"deployPostgreSql": False}, ENV, tmp_path, "bicep", run_az=client)
    with pytest.raises(ValueError, match="binding"):
        pg.preflight({**INPUTS, "networkIsolation": True}, ENV, tmp_path, "bicep", run_az=client)
    with pytest.raises(ValueError, match="teardown"):
        pg.require_safe_teardown(ENV, tmp_path)


def test_existing_server_without_intent_is_not_adopted(tmp_path):
    client = Client()
    client.exists = True
    with pytest.raises(ValueError, match="existing"):
        pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)


def test_corrupt_binding_fails_closed(tmp_path):
    path = pg.binding_path(tmp_path, ENV)
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="binding"):
        pg.require_safe_teardown(ENV, tmp_path)


def test_wrong_host_or_auth_cannot_be_published(tmp_path):
    client = Client()
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)
    with pytest.raises(ValueError, match="host"):
        pg.protect({**ENV, "POSTGRESQL_HOST": "evil.example.org"}, tmp_path, run_az=client)
    client.server["properties"]["authConfig"]["passwordAuth"] = "Enabled"
    with pytest.raises(ValueError, match="Entra"):
        pg.protect(ENV, tmp_path, run_az=client)


def test_lock_failure_is_not_ready(tmp_path):
    client = Client()
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)

    def failure(args, **kwargs):
        if args[:2] == ["lock", "create"]:
            raise RuntimeError("access denied")
        return client(args, **kwargs)

    with pytest.raises(RuntimeError, match="access denied"):
        pg.protect(ENV, tmp_path, run_az=failure)
    record = json.loads(pg.binding_path(tmp_path, ENV).read_text())
    assert record["ready"] is False


def test_discovery_requires_verified_lock(tmp_path):
    client = Client()
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)
    with pytest.raises(ValueError, match="protection"):
        pg.discovery_settings(ENV, tmp_path, run_az=client)
    pg.protect(ENV, tmp_path, run_az=client)
    assert pg.discovery_settings(ENV, tmp_path, run_az=client)["AGENTLZ_POSTGRESQL_AUTH_MODE"] == "entra"


@pytest.mark.parametrize("name,value", [
    ("DEPLOY_POSTGRESQL", 1), ("POSTGRESQL_STORAGE_SIZE_GB", True),
    ("POSTGRESQL_STORAGE_SIZE_GB", "32.0"), ("POSTGRESQL_STORAGE_SIZE_GB", "-32"),
    ("POSTGRESQL_BACKUP_RETENTION_DAYS", "7.0"), ("POSTGRESQL_GEO_REDUNDANT_BACKUP", "1"),
    ("POSTGRESQL_STORAGE_AUTO_GROW", "yes"),
])
def test_native_env_types_are_strict(name, value):
    with pytest.raises(ValueError):
        pg.resolve_inputs(INPUTS, {name: value})


def test_whole_source_placeholders_resolve_once_and_env_contract_is_explicit():
    source = {**INPUTS, "deployPostgreSql": "${DEPLOY_POSTGRESQL=false}",
              "postgreSqlStorageSizeGb": "${POSTGRESQL_STORAGE_SIZE_GB=32}"}
    result = pg.resolve_inputs(source, {"DEPLOY_POSTGRESQL": "true", "POSTGRESQL_STORAGE_SIZE_GB": "128"})
    assert result["deployPostgreSql"] is True and result["postgreSqlStorageSizeGb"] == 128
    with pytest.raises(ValueError, match="deployPostgreSql"):
        pg.resolve_inputs(source, {"DEPLOY_POSTGRESQL": "${UNEXPANDED}"})
    assert set(pg.ENVIRONMENT_KEYS.values()) == {
        "DEPLOY_POSTGRESQL", "POSTGRESQL_SERVER_NAME", "POSTGRESQL_DATABASE_NAME", "POSTGRESQL_VERSION",
        "POSTGRESQL_TIER", "POSTGRESQL_SKU_NAME", "POSTGRESQL_STORAGE_SIZE_GB",
        "POSTGRESQL_BACKUP_RETENTION_DAYS", "POSTGRESQL_HIGH_AVAILABILITY",
        "POSTGRESQL_GEO_REDUNDANT_BACKUP", "POSTGRESQL_STORAGE_AUTO_GROW",
        "POSTGRESQL_ADMINISTRATOR_OBJECT_ID", "POSTGRESQL_ADMINISTRATOR_PRINCIPAL_NAME",
        "POSTGRESQL_ADMINISTRATOR_PRINCIPAL_TYPE",
    }


@pytest.mark.parametrize("change", [
    {"postgreSqlTier": "GeneralPurpose"},
    {"postgreSqlVersion": 16}, {"postgreSqlDatabaseName": "azure_sys"},
    {"postgreSqlServerName": "unsafe.name"}, {"postgreSqlStorageSizeGb": 48},
    {"postgreSqlBackupRetentionDays": 36}, {"postgreSqlAdministratorObjectId": "not-guid"},
    {"postgreSqlAdministratorPrincipalType": "service"}, {"postgreSqlAdministratorPrincipalName": ""},
])
def test_invalid_native_contract_values(change):
    with pytest.raises(ValueError):
        pg.resolve_inputs({**INPUTS, **change}, {})


@pytest.mark.parametrize("property,value", [
    ("id", ID.replace("rg-fixture", "wrong-group")),
    ("tags", {"azd-env-name": "different"}),
])
def test_live_resource_identity_and_ownership_are_required(tmp_path, property, value):
    client = Client()
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)
    client.server[property] = value
    with pytest.raises(ValueError):
        pg.protect(ENV, tmp_path, run_az=client)
    assert not any(args[:2] == ["lock", "create"] for args in client.calls)


@pytest.mark.parametrize("key,value", [
    ("AZURE_SUBSCRIPTION_ID", ADMIN), ("AZURE_TENANT_ID", ADMIN),
    ("TENANT_ID", ADMIN),
    ("POSTGRESQL_DATABASE_NAME", "other"), ("POSTGRESQL_PORT", "6432"),
    ("AZURE_ENV_NAME", "other"), ("DEPLOY_POSTGRESQL", "false"),
])
def test_output_context_cannot_replace_the_recorded_binding(tmp_path, key, value):
    client = Client()
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)
    with pytest.raises(ValueError):
        pg.protect({**ENV, key: value}, tmp_path, run_az=client)


def test_missing_intent_with_prior_outputs_is_not_adopted_or_disabled(tmp_path):
    with pytest.raises(ValueError, match="binding"):
        pg.protect(ENV, tmp_path, run_az=Client())
    with pytest.raises(ValueError, match="disable"):
        pg.preflight({"deployPostgreSql": False}, ENV, tmp_path, "terraform", run_az=Client())


@pytest.mark.parametrize("level", ["ReadOnly", "", None])
def test_lock_readback_failure_never_advances_ready_and_rerun_recovers(tmp_path, level):
    client = Client()
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)

    def wrong_lock(args, **kwargs):
        if args[:2] == ["lock", "show"]:
            return json.dumps({"id": ID + "/providers/Microsoft.Authorization/locks/" + pg.LOCK_NAME,
                               "properties": {"level": level}})
        return client(args, **kwargs)

    with pytest.raises(ValueError, match="protection"):
        pg.protect(ENV, tmp_path, run_az=wrong_lock)
    assert json.loads(pg.binding_path(tmp_path, ENV).read_text())["ready"] is False
    pg.protect(ENV, tmp_path, run_az=client)
    # Discovery only reads. It cannot repair the removed/changed lock.
    before = len(client.calls)
    pg.discovery_settings(ENV, tmp_path, run_az=client)
    assert not any(args[:2] == ["lock", "create"] for args in client.calls[before:])
    with pytest.raises(ValueError, match="protection"):
        pg.discovery_settings(ENV, tmp_path, run_az=wrong_lock)


def test_wrong_lock_scope_is_rejected(tmp_path):
    client = Client()
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)

    def wrong_scope(args, **kwargs):
        if args[:2] == ["lock", "show"]:
            return json.dumps({"id": "/subscriptions/" + SUB + "/providers/Microsoft.Authorization/locks/" + pg.LOCK_NAME,
                               "properties": {"level": "CanNotDelete"}})
        return client(args, **kwargs)

    with pytest.raises(ValueError, match="protection"):
        pg.protect(ENV, tmp_path, run_az=wrong_scope)


def test_terraform_teardown_guard_precedes_ownership_early_return(tmp_path):
    from config.deployment import teardown
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "terraform", run_az=Client())
    with pytest.raises(ValueError, match="PostgreSQL teardown"):
        teardown.require_safe_teardown(ENV, tmp_path, "fixture", provider="terraform")


def test_teardown_reads_pg_environment_despite_normal_scope_filter(monkeypatch):
    from config.deployment import teardown
    from types import SimpleNamespace
    monkeypatch.setattr(teardown.shutil, "which", lambda name: name)
    monkeypatch.setattr(teardown.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=json.dumps({**ENV, "DEPLOY_POSTGRESQL": "true"})))
    result = teardown.read_environment("fixture")
    assert result["DEPLOY_POSTGRESQL"] == "true" and result["POSTGRESQL_SERVER_RESOURCE_ID"] == ID


def test_subnet_and_dns_boundaries(tmp_path):
    with pytest.raises(ValueError, match="subnet"):
        pg.preflight({**INPUTS, "acaEnvironmentSubnetPrefix": "10.0.0.0/28"}, FRESH_ENV,
                     tmp_path, "bicep", run_az=Client())


def test_unverified_pg_settings_cannot_be_supplied_to_foundation():
    from config.deployment.app_settings import merge_app_configuration_settings
    for key in ("HOST", "PORT", "DATABASE", "SSLMODE", "AUTH_MODE"):
        with pytest.raises(ValueError, match="protected"):
            merge_app_configuration_settings(
                [{"name": "AGENTLZ_POSTGRESQL_" + key, "value": "unverified", "label": "agent-lz"}], [])


def test_retained_env_metadata_blocks_teardown_even_after_caller_filtering(tmp_path):
    path = pg.binding_path(tmp_path, FRESH_ENV)
    path.parent.mkdir(parents=True)
    (path.parent / ".env").write_text(f'POSTGRESQL_SERVER_RESOURCE_ID="{ID}"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="teardown"):
        pg.require_safe_teardown(FRESH_ENV, tmp_path)
    with pytest.raises(ValueError, match="binding"):
        pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=Client())


def test_missing_record_rejects_even_when_live_inventory_is_empty(tmp_path):
    with pytest.raises(ValueError, match="binding"):
        pg.preflight(INPUTS, ENV, tmp_path, "bicep", run_az=Client())


def test_partial_recovery_verifies_server_ownership_before_iac(tmp_path):
    client = Client()
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)
    client.exists = True
    client.server["tags"] = {"azd-env-name": "other"}
    with pytest.raises(ValueError, match="ownership"):
        pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)


def test_location_and_admin_changes_cannot_replace_existing_binding(tmp_path):
    client = Client()
    source = {**INPUTS, "location": "westus"}
    pg.preflight(source, FRESH_ENV, tmp_path, "bicep", run_az=client)
    for changed in ({**source, "location": "eastus"}, {**source, "postgreSqlAdministratorObjectId": TENANT},
                    {**source, "postgreSqlServerName": "pg-replacement"}):
        with pytest.raises(ValueError, match="binding"):
            pg.preflight(changed, FRESH_ENV, tmp_path, "bicep", run_az=client)


def test_known_creation_intent_can_resume_unfinished_children_but_never_publish(tmp_path):
    client = Client()
    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=client)
    client.exists = True
    client.server["properties"]["state"] = "Updating"

    def incomplete(args, **kwargs):
        if args[:3] == ["postgres", "flexible-server", "microsoft-entra-admin"]:
            return "[]"
        if args[:2] == ["resource", "show"] and args[args.index("--ids") + 1].endswith("/databases/agentlz"):
            raise AssertionError("Preflight must allow IaC to resume the intended missing database")
        return client(args, **kwargs)

    pg.preflight(INPUTS, FRESH_ENV, tmp_path, "bicep", run_az=incomplete)
    with pytest.raises(ValueError, match="Ready"):
        pg.protect(ENV, tmp_path, run_az=incomplete)
    client.server["properties"]["state"] = "Ready"
    with pytest.raises(ValueError, match="Administrator"):
        pg.protect(ENV, tmp_path, run_az=incomplete)
    assert not json.loads(pg.binding_path(tmp_path, ENV).read_text())["ready"]


@pytest.mark.parametrize("kind", ["owner", "profile", "subnet"])
def test_existing_aca_is_read_back_not_trusted_from_generic_inventory(tmp_path, kind):
    client = Client()
    source = {**INPUTS, "acaEnvironmentSubnetName": "aca"}
    pg.preflight(source, FRESH_ENV, tmp_path, "bicep", run_az=client)
    client.exists = True
    if kind == "owner":
        client.aca["tags"]["azd-env-name"] = "other"
    elif kind == "profile":
        client.aca["properties"]["workloadProfiles"] = []
    else:
        client.aca["properties"]["vnetConfiguration"]["infrastructureSubnetId"] = "/wrong/subnets/other"
    with pytest.raises(ValueError, match="Container Apps"):
        pg.preflight(source, FRESH_ENV, tmp_path, "bicep", run_az=client)


@pytest.mark.parametrize("forced", [False, True])
def test_byo_aca_route_table_is_verified_without_changing_corporate_routes(tmp_path, forced):
    client = Client()
    vnet_id = f"/subscriptions/{SUB}/resourceGroups/rg-network/providers/Microsoft.Network/virtualNetworks/existing"
    table_id = f"/subscriptions/{SUB}/resourceGroups/rg-network/providers/Microsoft.Network/routeTables/existing"
    source = {**INPUTS, "useExistingVNet": True, "existingVnetResourceId": vnet_id,
              "acaEnvironmentSubnetName": "aca"}

    def network(args, **kwargs):
        if args[:2] == ["resource", "show"]:
            resource_id = args[args.index("--ids") + 1]
            if resource_id == vnet_id:
                return json.dumps({"id": vnet_id, "properties": {"subnets": [{
                    "name": "aca", "properties": {"addressPrefix": "10.0.8.0/24",
                        "delegations": [{"properties": {"serviceName": "Microsoft.App/environments"}}],
                        "routeTable": {"id": table_id}}}]}})
            if resource_id == table_id:
                return json.dumps({"id": table_id, "properties": {"routes": [
                    {"properties": {"addressPrefix": "0.0.0.0/0" if forced else "10.100.0.0/16"}}]}})
        return client(args, **kwargs)

    if forced:
        with pytest.raises(ValueError, match="forced"):
            pg.preflight(source, FRESH_ENV, tmp_path, "bicep", run_az=network)
        assert not pg.binding_path(tmp_path, ENV).exists()
    else:
        pg.preflight(source, FRESH_ENV, tmp_path, "bicep", run_az=network)
        assert pg.binding_path(tmp_path, ENV).exists()


def test_competing_private_dns_modes_fail_before_intent(tmp_path):
    source = {**INPUTS, "networkIsolation": True, "policyManagedPrivateDns": True,
              "existingPrivateDnsZonePostgreSqlResourceId":
                  f"/subscriptions/{SUB}/resourceGroups/rg-network/providers/Microsoft.Network/privateDnsZones/privatelink.postgres.database.azure.com"}
    with pytest.raises(ValueError, match="Competing"):
        pg.preflight(source, FRESH_ENV, tmp_path, "bicep", run_az=Client())
    assert not pg.binding_path(tmp_path, ENV).exists()
