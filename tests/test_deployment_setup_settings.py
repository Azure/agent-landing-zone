import json
from pathlib import Path

import pytest

from config.deployment import setup_settings
from config.deployment.metadata import MetadataError, VerifiedMetadata


@pytest.fixture
def verified():
    root = Path(__file__).resolve().parents[1]
    document = json.loads((
        root / "tests" / "fixtures" / "deployment-metadata-v1.json"
    ).read_text(encoding="utf-8"))
    return VerifiedMetadata(document, {"AZURE_ENV_NAME": "example"}, {
        "networkIsolation": False, "deployAgentAppMcp": False,
        "additionalAppConfigurationSettings": [],
    }, {})


def test_store_free_resolution_maps_evaluated_resources_and_models(verified):
    settings = setup_settings.resolve_setup_settings(verified)
    assert settings["APP_RUNTIME_CONFIGURATION_MODE"] == "containerEnv"
    assert "APP_CONFIG_ENDPOINT" not in settings
    assert settings["AI_FOUNDRY_ACCOUNT_NAME"] == "example-foundry"
    assert settings["MODEL_DEPLOYMENTS"][0]["model"]["name"] == "example-model"
    assert settings["CONTAINER_APPS"][0]["identity"]["principalId"].startswith("33333333")
    assert settings["NETWORK_ISOLATION"] == "false"


def test_store_presence_does_not_select_publication(verified):
    verified.document["resources"]["appConfig"] = {
        "status": "managed", "resource": {
            "resourceId": "/subscriptions/22222222-2222-2222-2222-222222222222/resourceGroups/rg-example-app/providers/Microsoft.AppConfiguration/configurationStores/example",
            "name": "example", "endpoint": "https://example.azconfig.io",
        },
    }
    settings = setup_settings.resolve_setup_settings(verified)
    assert "APP_CONFIG_ENDPOINT" not in settings
    assert settings["APP_RUNTIME_CONFIGURATION_MODE"] == "containerEnv"


@pytest.mark.parametrize("selected", [True, False])
def test_foundry_selection_controls_reach_hooks_as_typed_strings(verified, selected):
    verified.parameters.update(deployAiFoundry=selected, deployAfProject=selected)
    settings = setup_settings.resolve_setup_settings(verified)
    assert settings["DEPLOY_AI_FOUNDRY"] == str(selected).lower()
    assert settings["DEPLOY_AF_PROJECT"] == str(selected).lower()


def test_verified_service_selections_supply_omitted_hook_controls(verified):
    settings = setup_settings.resolve_setup_settings(verified)
    assert settings["DEPLOY_AI_FOUNDRY"] == "true"
    assert settings["DEPLOY_AF_PROJECT"] == "true"
    assert settings["DEPLOY_SEARCH_SERVICE"] == "false"


def test_resource_preferences_cannot_override_destinations(verified):
    verified.parameters["additionalAppConfigurationSettings"] = [
        {"name": "AI_FOUNDRY_ACCOUNT_NAME", "value": "another", "label": "agent-lz"},
    ]
    with pytest.raises(MetadataError, match="conflict"):
        setup_settings.resolve_setup_settings(verified)


def test_only_explicit_allowlisted_preferences_enter_setup(verified):
    verified.parameters["additionalAppConfigurationSettings"] = [
        {"name": "AUDIT_EVENTS_ENABLED", "value": "true", "label": "agent-lz"},
        {"name": "PRIVATE_RUNTIME_SETTING", "value": "runtime-only", "label": "agent-lz"},
        {"name": "AUDIT_SOURCE_EVENT_LIMIT", "value": "9", "label": "another-app"},
    ]
    settings = setup_settings.resolve_setup_settings(verified)
    assert settings["AUDIT_EVENTS_ENABLED"] == "true"
    assert "PRIVATE_RUNTIME_SETTING" not in settings
    assert "AUDIT_SOURCE_EVENT_LIMIT" not in settings
    assert "AUDIT_SENSITIVE_CONTENT_ENABLED" not in settings


def test_preferences_cannot_supply_key_vault_reference_content(verified):
    verified.parameters["additionalAppConfigurationSettings"] = [{
        "name": "AUDIT_EVENTS_ENABLED", "value": '{"uri":"https://example.vault.azure.net/secrets/value"}',
        "label": "agent-lz", "contentType": "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8",
    }]
    with pytest.raises(MetadataError, match="secret references"):
        setup_settings.resolve_setup_settings(verified)


def test_store_required_selection_is_not_silently_disabled(verified):
    verified.parameters["deployAgentAppMcp"] = True
    with pytest.raises(MetadataError, match="prerequisite"):
        setup_settings.resolve_setup_settings(verified)


def test_missing_store_in_appconfig_mode_fails(verified):
    verified.document["context"]["runtimeConfigurationMode"] = "appConfig"
    with pytest.raises(MetadataError, match="appConfig"):
        setup_settings.resolve_setup_settings(verified)


def test_none_preserves_no_injection_selection(verified):
    verified.document["context"]["runtimeConfigurationMode"] = "none"
    settings = setup_settings.resolve_setup_settings(verified)
    assert settings["APP_RUNTIME_CONFIGURATION_MODE"] == "none"
    assert "APP_CONFIG_ENDPOINT" not in settings


def test_toolbox_bindings_come_from_declared_names_and_verified_destinations(verified):
    verified.document["resources"]["search"] = {"status": "managed", "resource": {
        "resourceId": "/subscriptions/22222222-2222-2222-2222-222222222222/resourceGroups/rg-example/providers/Microsoft.Search/searchServices/example",
        "name": "example", "endpoint": "https://example.search.windows.net",
    }}
    verified.parameters.update(
        retrievalBackend="foundry_iq", knowledgeBaseName="selected-kb",
        knowledgeBaseConnectionName="selected-connection", foundryIqApiVersion="2026-05-01-preview",
    )
    settings = setup_settings.resolve_setup_settings(verified)
    project = verified.document["resources"]["foundryProject"]["resource"]
    assert settings["KNOWLEDGE_BASE_ENDPOINT"] == "https://example.search.windows.net"
    assert settings["KNOWLEDGE_BASE_CONNECTION_ID"] == project["resourceId"] + "/connections/selected-connection"
    assert settings["TOOLBOX_ENDPOINT"] == project["endpoint"] + "/toolboxes/selected-kb/mcp?api-version=v1"
    assert settings["FOUNDRY_IQ_API_VERSION"] == "2026-05-01-preview"


def test_audit_adapter_contains_only_selected_vault_reference(verified):
    verified.document["resources"]["keyVault"] = {"status": "managed", "resource": {
        "resourceId": "/subscriptions/22222222-2222-2222-2222-222222222222/resourceGroups/rg-example-app/providers/Microsoft.KeyVault/vaults/example",
        "name": "example", "endpoint": "https://example.vault.azure.net",
    }}
    settings = setup_settings.resolve_setup_settings(verified)
    assert settings["AUDIT_HMAC_KEY_URI"] == "https://example.vault.azure.net/secrets/AUDIT-HMAC-KEY"
    assert "AUDIT_HMAC_KEY" not in settings


def test_unselected_toolbox_does_not_require_disabled_search(verified):
    verified.parameters["retrievalBackend"] = "foundry_iq"
    settings = setup_settings.resolve_setup_settings(verified)
    assert settings["RETRIEVAL_BACKEND"] == "foundry_iq"
    assert "TOOLBOX_ENDPOINT" not in settings
    assert "KNOWLEDGE_BASE_CONNECTION_ID" not in settings
