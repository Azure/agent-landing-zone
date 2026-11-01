"""T038: platform outputs contract (R13, FR-015f)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from jsonschema import Draft202012Validator

from config import find_repo_root
from config.deployment import outputs

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "contracts" / "platform-outputs-v1.schema.json"
UI_CLIENT_ID = "11111111-2222-3333-4444-555555555555"

ENVIRONMENT = {
    "AZURE_RESOURCE_GROUP": "rg-test",
    "AZURE_AI_PROJECT_ENDPOINT": "https://aif.services.ai.azure.com/api/projects/p1",
    "AI_FOUNDRY_ACCOUNT_NAME": "aif-test",
    "AZURE_CONTAINER_REGISTRY_ENDPOINT": "crtest.azurecr.io",
    "APP_CONFIG_ENDPOINT": "https://appcs-test.azconfig.io",
    "SEARCH_SERVICE_ENDPOINT": "https://srch-test.search.windows.net",
    "STORAGE_BLOB_ENDPOINT": "https://sttest.blob.core.windows.net/",
    "KEY_VAULT_URI": "https://kv-test.vault.azure.net/",
    "NETWORK_ISOLATION": "true",
    "AGENTLZ_COMPONENT_IDENTITIES": json.dumps({"ui": UI_CLIENT_ID}),
}


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_document_validates_against_published_schema():
    document = outputs.build_platform_outputs(ENVIRONMENT)
    Draft202012Validator(_schema()).validate(document)
    outputs.validate_platform_outputs(document)
    assert document["schemaVersion"] == 1
    assert document["network"] == {"isolated": True}
    assert "cosmos" not in document  # optional section omitted when absent
    assert document["identities"] == [{"component": "ui", "clientId": UI_CLIENT_ID}]


def test_flat_keys_match_json_document_under_agent_lz_label():
    document = outputs.build_platform_outputs(ENVIRONMENT)
    settings = outputs.platform_settings(document)
    assert json.loads(settings["AGENTLZ_PLATFORM_OUTPUTS"]) == document
    assert settings["AGENTLZ_FOUNDRY_PROJECT_ENDPOINT"] == document["foundry"]["projectEndpoint"]
    assert settings["AGENTLZ_FOUNDRY_ACCOUNT_NAME"] == document["foundry"]["accountName"]
    assert settings["AGENTLZ_ACR_LOGIN_SERVER"] == document["registry"]["loginServer"]
    assert settings["AGENTLZ_APPCONFIG_ENDPOINT"] == ENVIRONMENT["APP_CONFIG_ENDPOINT"]
    assert settings["AGENTLZ_SEARCH_ENDPOINT"] == document["search"]["endpoint"]
    assert settings["AGENTLZ_STORAGE_BLOB_ENDPOINT"] == document["storage"]["blobEndpoint"]
    assert settings["AGENTLZ_KEYVAULT_URI"] == document["keyVault"]["uri"]
    assert settings["AGENTLZ_IDENTITY_UI_CLIENT_ID"] == UI_CLIENT_ID
    assert settings["AGENTLZ_NETWORK_ISOLATED"] == "true"
    assert "AGENTLZ_COSMOS_ENDPOINT" not in settings
    assert all(key.startswith("AGENTLZ_") for key in settings)

    calls: list[list[str]] = []
    with mock.patch(
        "config.deployment.appconfig._run_az",
        side_effect=lambda args, required=True: calls.append(args) or "",
    ):
        outputs.publish(ENVIRONMENT["APP_CONFIG_ENDPOINT"], settings)
    assert len(calls) == len(settings)
    for call in calls:
        assert call[call.index("--label") + 1] == "agent-lz"
    assert [c[c.index("--key") + 1] for c in calls][0] == "AGENTLZ_PLATFORM_OUTPUTS"


def test_missing_required_value_fails_with_actionable_message():
    environment = {k: v for k, v in ENVIRONMENT.items() if k != "KEY_VAULT_URI"}
    with pytest.raises(outputs.PlatformOutputsError, match="AGENTLZ_KEYVAULT_URI"):
        outputs.build_platform_outputs(environment)


def test_schema_violation_is_rejected():
    document = outputs.build_platform_outputs(ENVIRONMENT)
    document["identities"] = [{"component": "ui", "clientId": "not-a-guid"}]
    with pytest.raises(outputs.PlatformOutputsError, match="/identities/0/clientId"):
        outputs.validate_platform_outputs(document)
    document = outputs.build_platform_outputs(ENVIRONMENT)
    document["secret"] = "x"
    with pytest.raises(outputs.PlatformOutputsError):
        outputs.validate_platform_outputs(document)


def test_cli_dry_run_writes_nothing(monkeypatch, capsys):
    for key, value in ENVIRONMENT.items():
        monkeypatch.setenv(key, value)
    with mock.patch("config.deployment.appconfig._run_az") as run_az:
        assert outputs.main(["--dry-run"]) == 0
    run_az.assert_not_called()
    assert "AGENTLZ_PLATFORM_OUTPUTS" in json.loads(capsys.readouterr().out)


def test_cli_discovers_and_publishes_container_identity_when_map_is_absent(monkeypatch, capsys):
    for key, value in ENVIRONMENT.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(outputs.IDENTITIES_ENV)
    monkeypatch.setenv("AGENTLZ_APP_DEFINITION", str(REPO_ROOT / "samples" / "custom-app" / "containerapp"))
    with mock.patch("config.appdefinition.roles.discover_component_identities",
                    return_value={"web": UI_CLIENT_ID}) as discover, mock.patch.object(outputs, "publish") as publish:
        assert outputs.main([]) == 0
    discover.assert_called_once()
    settings = publish.call_args.args[1]
    assert json.loads(settings[outputs.PLATFORM_OUTPUTS_KEY])["identities"] == [
        {"component": "web", "clientId": UI_CLIENT_ID}
    ]
    assert settings["AGENTLZ_IDENTITY_WEB_CLIENT_ID"] == UI_CLIENT_ID


def test_cli_rejects_identity_discovery_failure_before_publication(monkeypatch, capsys):
    from config.appdefinition.roles import RoleAssignmentError

    for key, value in ENVIRONMENT.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(outputs.IDENTITIES_ENV)
    monkeypatch.setenv("AGENTLZ_APP_DEFINITION", str(REPO_ROOT / "samples" / "custom-app" / "containerapp"))
    with mock.patch("config.appdefinition.roles.discover_component_identities",
                    side_effect=RoleAssignmentError("Expected exactly one identity")), \
            mock.patch.object(outputs, "publish") as publish:
        assert outputs.main([]) == 1
    publish.assert_not_called()
    assert "Expected exactly one identity" in capsys.readouterr().err


def test_repo_root_detected_by_markers_not_folder_name(tmp_path):
    root = tmp_path / "any-folder-name"
    nested = root / "config" / "deployment"
    nested.mkdir(parents=True)
    (root / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileNotFoundError):  # azure.yaml missing
        find_repo_root(nested, environment={})
    (root / "azure.yaml").write_text("name: x\n", encoding="utf-8")
    assert find_repo_root(nested, environment={}) == root.resolve()
    assert find_repo_root(environment={}) == REPO_ROOT
    assert find_repo_root(tmp_path, environment={"AGENTLZ_REPO_ROOT": str(root)}) == root.resolve()
    with pytest.raises(FileNotFoundError, match="AGENTLZ_REPO_ROOT"):
        find_repo_root(environment={"AGENTLZ_REPO_ROOT": str(tmp_path)})
