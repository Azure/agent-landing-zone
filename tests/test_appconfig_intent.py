"""Declared runtime intent and ownership, with no Azure boundary calls."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from config.deployment import appconfig
from config.deployment import appconfig_intent as intent

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = {
    "AZURE_ENV_NAME": "fixture",
    "AZURE_SUBSCRIPTION_ID": "11111111-1111-1111-1111-111111111111",
    "AZURE_TENANT_ID": "22222222-2222-2222-2222-222222222222",
    "AZURE_RESOURCE_GROUP": "rg-fixture",
    "AZURE_LOCATION": "swedencentral",
    "AZURE_COSMOS_LOCATION": "swedencentral",
    "AZURE_PRINCIPAL_ID": "33333333-3333-3333-3333-333333333333",
    "NETWORK_ISOLATION": "false",
    "USE_UAI": "true",
    "USE_EXISTING_VNET": "false",
    "ENABLE_AGENTIC_RETRIEVAL": "false",
    "SIDE_BY_SIDE": "true",
    "DEPLOYMENT_TOPOLOGY": "classic",
    "APP_CONFIG_ENDPOINT": "https://fixture.azconfig.io",
    "RESOURCE_TOKEN": "fixture",
}
AUTHORITY = {
    "CHAT_BACKEND": "orchestrator",
    "DEPLOYMENT_TOPOLOGY": "classic",
    "HOSTED_AGENT_BASE_URL": "",
    "HOSTED_AGENT_IMAGE_VERSION": "",
    "AZURE_RESOURCE_GROUP": "rg-fixture",
    "SEARCH_RAG_INDEX_NAME": "must-not-republish-foundation",
}


def declaration(tmp_path, settings, **overrides):
    document = json.loads((ROOT / "main.parameters.json").read_text(encoding="utf-8-sig"))
    document["parameters"]["additionalAppConfigurationSettings"] = {"value": settings}
    for name, value in overrides.items():
        document["parameters"][name] = {"value": value}
    path = tmp_path / "declared.parameters.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def resolved(tmp_path, settings):
    return intent.resolve_intent(declaration(tmp_path, settings), ENVIRONMENT)


def by_name(entries):
    return {entry["name"]: entry for entry in entries}


def test_ordinary_override_is_consumed_from_declared_source_on_fresh_runner(tmp_path):
    loaded = resolved(tmp_path, [{"name": "HOSTED_HISTORY_MAX_ITEMS", "value": "50"}])
    published = by_name(intent.prepare_publication(loaded, AUTHORITY))
    assert published["HOSTED_HISTORY_MAX_ITEMS"] == {
        "name": "HOSTED_HISTORY_MAX_ITEMS", "value": "50",
        "label": "agent-lz", "contentType": "text/plain",
    }
    assert "AZURE_RESOURCE_GROUP" not in published
    assert "SEARCH_RAG_INDEX_NAME" not in published


def test_substitution_is_once_only_and_literals_metadata_survive(tmp_path):
    literal = 'role "$HOME" ${NOT_EXPANDED} \\ Unicode café\nnext'
    source = declaration(tmp_path, [{
        "name": "PANEL_OPERATOR_APP_ROLE", "value": "${DECLARED_ROLE}",
        "contentType": "application/x-role",
    }])
    loaded = intent.resolve_intent(source, {**ENVIRONMENT, "DECLARED_ROLE": literal})
    record = by_name(intent.prepare_publication(loaded, AUTHORITY))["PANEL_OPERATOR_APP_ROLE"]
    assert record["value"] == literal
    assert record["contentType"] == "application/x-role"


@pytest.mark.parametrize("name,value", [
    ("CHAT_BACKEND", "hosted_agent"),
    ("DEPLOYMENT_TOPOLOGY", "hosted-panel"),
    ("HOSTED_AGENT_BASE_URL", "https://unverified.example.test"),
    ("HOSTED_AGENT_IMAGE_VERSION", "sha256:" + "a" * 64),
    ("HOSTED_CONTINUITY_ENABLED", "true"),
    ("HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED", "true"),
    ("PANEL_HISTORY_OWNER_BINDING_VALIDATED", "true"),
    ("PANEL_OPERATOR_SURFACES_ENABLED", "true"),
])
def test_explicit_cutover_and_evidence_conflicts_fail_before_writes(tmp_path, name, value):
    with pytest.raises(ValueError, match="authority|protected"):
        loaded = resolved(tmp_path, [{"name": name, "value": value}])
        intent.prepare_publication(loaded, AUTHORITY)


def test_platform_identity_override_is_routed_to_existing_owner_or_rejected(tmp_path):
    for name in ("AGENTLZ_PLATFORM_OUTPUTS", "AGENTLZ_IDENTITY_FRONTEND_CLIENT_ID"):
        with pytest.raises(ValueError, match="existing runtime/platform owner|protected"):
            loaded = resolved(tmp_path, [{"name": name, "value": "unverified"}])
            intent.prepare_publication(loaded, AUTHORITY)


@pytest.mark.parametrize("setting,match", [
    ({"name": "CHAT_BACKEND", "value": "orchestrator", "contentType": "application/json"}, "contentType|protected"),
    ({"name": "HOSTED_HISTORY_MAX_ITEMS", "value": "bad", "contentType": "application/json"}, "valid JSON"),
    ({"name": "HOSTED_HISTORY_MAX_ITEMS", "value": "0"}, "between"),
    ({"name": "HOSTED_AGENT_SSE_IDLE_TIMEOUT_SECONDS", "value": "nonnumeric"}, "positive integer"),
    ({"name": "PANEL_HISTORY_ENABLED", "value": "yes"}, "true or false"),
])
def test_invalid_metadata_and_ordinary_values_fail(tmp_path, setting, match):
    with pytest.raises(ValueError, match=match):
        intent.prepare_publication(resolved(tmp_path, [setting]), AUTHORITY)


@pytest.mark.parametrize("name", ["AUDIT_HMAC_KEY", "HOSTED_CONVERSATION_CAPABILITY_KEY", "HOSTED_HISTORY_MAX_ITEMS"])
def test_runtime_key_vault_references_are_never_flattened(tmp_path, name):
    with pytest.raises(ValueError, match="owner|protected"):
        loaded = resolved(tmp_path, [{
            "name": name,
            "value": '{"uri":"https://fixture.vault.azure.net/secrets/reference"}',
            "contentType": "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8",
        }])
        intent.prepare_publication(loaded, AUTHORITY)


def test_label_identity_case_and_unknown_extensions_remain_foundation_owned(tmp_path):
    loaded = resolved(tmp_path, [
        {"name": "HOSTED_AGENT_BASE_URL", "value": "staging", "label": "staging"},
        {"name": "HOSTED_AGENT_BASE_URL", "value": "unlabeled", "label": ""},
        {"name": "hosted_agent_base_url", "value": "lowercase"},
        {"name": "HOSTED_CUSTOM_EXTENSION", "value": "custom"},
    ])
    assert not any(intent.is_runtime(setting, loaded) for setting in loaded.explicit)
    assert [setting["label"] for setting in loaded.explicit] == ["staging", "", "agent-lz", "agent-lz"]
    intent.prepare_publication(loaded, AUTHORITY)


def test_canonical_panel_database_key_stays_foundation_owned():
    setting = intent.Setting(name="PANEL_FEEDBACK_DATABASE_CONTAINER", value="custom", label="agent-lz", contentType="text/plain")
    loaded = intent.RuntimeIntent([setting], [setting], frozenset([setting["name"]]), frozenset())
    assert not intent.is_runtime(setting, loaded)
    assert setting["name"] not in by_name(intent.prepare_publication(loaded, AUTHORITY))


def test_empty_label_is_distinct_from_default_and_duplicate_pairs_fail():
    records = intent.normalize_settings([
        {"name": "CUSTOM", "value": "one", "label": ""},
        {"name": "CUSTOM", "value": "two"},
    ])
    assert [entry["label"] for entry in records] == ["", "agent-lz"]
    with pytest.raises(ValueError, match="Duplicate"):
        intent.normalize_settings([{"name": "CUSTOM", "value": "one"}, {"name": "CUSTOM", "value": "two", "label": "agent-lz"}])


def test_missing_private_source_does_not_fall_back_to_defaults(tmp_path):
    with pytest.raises(ValueError, match="clean runner"):
        intent.resolve_intent(tmp_path / "missing-private.parameters.json", ENVIRONMENT)


def test_wrong_environment_binding_and_malformed_source_fail(tmp_path):
    path = declaration(tmp_path, [], environmentName="another")
    with pytest.raises(ValueError, match="selected environment"):
        intent.resolve_intent(path, ENVIRONMENT)
    path = declaration(tmp_path, [], applicationResourceGroupName="rg-foreign")
    with pytest.raises(ValueError, match="resource-group binding"):
        intent.resolve_intent(path, ENVIRONMENT)
    path.write_text('{"parameters":{"additionalAppConfigurationSettings":null}}', encoding="utf-8")
    with pytest.raises(ValueError, match="value entries"):
        intent.resolve_intent(path, ENVIRONMENT)


def test_single_inventory_is_consumed_by_terraform_and_python():
    source = (ROOT / "infra/terraform/main.data.tf").read_text(encoding="utf-8")
    assert "config/deployment/appconfig_ownership.json" in source
    assert "local.services_appconfig_ownership.controlled" in source
    assert "HOSTED_HISTORY_MAX_ITEMS" not in source
    policy = intent.ownership()
    groups = [set(policy["controlled"]), set(policy["evidence"]), set(policy["ordinary"]), set(policy["ownerReferences"])]
    assert sum(map(len, groups)) == len(set.union(*groups))


def main_context(monkeypatch, path):
    monkeypatch.setenv("AZURE_ENV_NAME", "fixture")
    monkeypatch.setattr(appconfig, "find_repo_root", lambda: ROOT)
    monkeypatch.setattr(appconfig, "selected_environment", lambda root, name: dict(ENVIRONMENT))
    monkeypatch.setattr(appconfig, "build_settings", lambda environment, **kwargs: dict(AUTHORITY))
    return ["--input", str(path)]


def test_cli_validates_everything_before_any_publication(tmp_path, monkeypatch):
    args = main_context(monkeypatch, declaration(tmp_path, [
        {"name": "HOSTED_HISTORY_MAX_ITEMS", "value": "50"},
        {"name": "CHAT_BACKEND", "value": "hosted_agent"},
    ]))
    calls = []
    monkeypatch.setattr(appconfig, "_run_az", lambda *args, **kwargs: calls.append(args))
    assert appconfig.main(args) == 1
    assert calls == []


def test_cli_uses_selected_environment_preserves_ephemeral_gate_and_writes_metadata(tmp_path, monkeypatch):
    args = main_context(monkeypatch, declaration(tmp_path, [
        {"name": "HOSTED_HISTORY_MAX_ITEMS", "value": "50", "contentType": "application/json"},
    ]))
    seen = []
    monkeypatch.setenv("AZURE_APP_RESOURCE_GROUP", "ambient-wrong-group")
    monkeypatch.setenv("HOSTED_CUTOVER_COMPLETE", "false")
    def build(environment, **kwargs):
        assert "AZURE_APP_RESOURCE_GROUP" not in environment
        assert environment["HOSTED_CUTOVER_COMPLETE"] == "false"
        return dict(AUTHORITY)
    monkeypatch.setattr(appconfig, "build_settings", build)
    monkeypatch.setattr(appconfig, "_run_az", lambda args, **kwargs: seen.append(args))
    assert appconfig.main(args) == 0
    record = next(args for args in seen if args[args.index("--key") + 1] == "HOSTED_HISTORY_MAX_ITEMS")
    assert record[record.index("--content-type") + 1] == "application/json"
    assert record[record.index("--value") + 1] == "50"
    assert seen[-1][seen[-1].index("--key") + 1] == "CHAT_BACKEND"
    assert not any("SEARCH_RAG_INDEX_NAME" in args for args in seen)


def test_missing_source_cli_fails_without_read_or_write(tmp_path, monkeypatch):
    args = main_context(monkeypatch, tmp_path / "missing-private.json")
    monkeypatch.setattr(appconfig, "build_settings", lambda *args, **kwargs: pytest.fail("No runtime discovery before missing-source failure"))
    monkeypatch.setattr(appconfig, "_run_az", lambda *args, **kwargs: pytest.fail("No Azure calls"))
    assert appconfig.main(args) == 1


def test_publication_failure_short_circuits_before_selector(tmp_path, monkeypatch):
    args = main_context(monkeypatch, declaration(tmp_path, []))
    calls = []
    def fail(arguments, **kwargs):
        calls.append(arguments)
        raise RuntimeError("Publication failed")
    monkeypatch.setattr(appconfig, "_run_az", fail)
    assert appconfig.main(args) == 1
    assert len(calls) == 1
    assert "CHAT_BACKEND" not in calls[0]


def test_cli_errors_do_not_echo_private_values(monkeypatch):
    secret_fixture = "private-value-must-not-be-logged"
    monkeypatch.setattr(appconfig.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=1, stdout=secret_fixture, stderr=secret_fixture,
    ))
    with pytest.raises(RuntimeError) as error:
        appconfig._run_az(["appconfig", "kv", "set", "--value", secret_fixture])
    assert secret_fixture not in str(error.value)
