"""Shared explicit App Configuration settings survive both input adapters."""

import copy

import pytest

from config.deployment.composition import compose_parameters
from config.deployment.terraform_inputs import compose_inputs, render_template
from tests.test_deployment_inputs import ENVIRONMENT, source


@pytest.fixture(params=["bicep", "terraform"])
def compose(request):
    def resolve(entries, environment=None):
        document = source()
        document["parameters"]["additionalAppConfigurationSettings"]["value"] = entries
        before = copy.deepcopy(document)
        context = {**ENVIRONMENT, **(environment or {})}
        if request.param == "bicep":
            settings = compose_parameters(document, context)["parameters"]["additionalAppConfigurationSettings"]["value"]
        else:
            values = {name: entry["value"] for name, entry in document["parameters"].items()}
            settings = compose_inputs(values, context)["additionalAppConfigurationSettings"]
        assert document == before
        return settings

    return resolve


def test_explicit_name_label_and_content_type_override_generated_defaults(compose):
    explicit = {
        "name": "HOSTED_AGENT_SSE_IDLE_TIMEOUT_SECONDS",
        "value": "120", "contentType": "application/custom",
    }
    other_label = {**explicit, "value": "240", "label": "other"}
    custom = {"name": "CUSTOM", "value": "custom", "label": ""}
    settings = compose([explicit, other_label, custom])
    assert {**explicit, "label": "agent-lz"} in settings
    assert other_label in settings
    assert {**custom, "contentType": "text/plain"} in settings
    assert len({(item["name"], item["label"]) for item in settings}) == len(settings)
    assert not any(item["name"] == "CHAT_BACKEND" for item in settings)


def test_presentation_settings_both_adapters_compact_and_default_off(compose):
    assert not any(item["name"] == "AGENT_PRESENTATION_SETTINGS" for item in compose([]))
    settings = compose([{
        "name": "AGENT_PRESENTATION_SETTINGS", "value": '{ "schemaVersion": 1, "agents": {} }',
    }])
    assert next(item for item in settings if item["name"] == "AGENT_PRESENTATION_SETTINGS") == {
        "name": "AGENT_PRESENTATION_SETTINGS", "value": '{"schemaVersion":1,"agents":{}}',
        "label": "agent-lz", "contentType": "text/plain",
    }


def test_presentation_settings_both_adapters_enable_disable_remove_are_request_owned(compose):
    key = "AGENT_PRESENTATION_SETTINGS"
    enabled = {"name": key, "value": '{"schemaVersion":1,"agents":{"a":{"enabled":true},"b":{"enabled":false}}}'}
    first = compose([enabled])
    disabled = compose([{**enabled, "value": '{"schemaVersion":1,"agents":{"a":{"enabled":false}}}'}])
    removed = compose([])
    assert next(s for s in first if s["name"] == key)["value"] == enabled["value"]
    assert next(s for s in disabled if s["name"] == key)["value"].endswith('"enabled":false}}}')
    assert not any(s["name"] == key for s in removed)
    assert next(s for s in first if s["name"] == key)["value"] == enabled["value"]


@pytest.mark.parametrize("override", [
    {"value": '{"schemaVersion":2,"agents":{}}'},
    {"label": "other"},
    {"contentType": "application/json"},
])
def test_presentation_settings_both_adapters_reject_invalid_present(compose, override):
    with pytest.raises(ValueError, match="AGENT_PRESENTATION_SETTINGS"):
        compose([{
            "name": "AGENT_PRESENTATION_SETTINGS",
            "value": '{"schemaVersion":1,"agents":{}}', **override,
        }])


def test_additional_settings_resolve_once_and_retain_literal_native_json(compose):
    text = 'literal ${DO_NOT_EXPAND}; "quote"; \\slash\ncafé $HOME'
    settings = compose(
        [{"name": "HOSTED_AGENT_SSE_IDLE_TIMEOUT_SECONDS", "value": "${CUSTOM_LIMIT=100}"}],
        {"CUSTOM_LIMIT": text, "DO_NOT_EXPAND": "must-not-appear"},
    )
    entry = next(item for item in settings if item["name"] == "HOSTED_AGENT_SSE_IDLE_TIMEOUT_SECONDS")
    assert entry["value"] == text
    assert "$" not in render_template({"settings": settings})


@pytest.mark.parametrize("name", [
    "COSMOS_DB_ENDPOINT", "COSMOS_DB_ACCOUNT_RESOURCE_ID",
    "ORCHESTRATOR_APP_APIKEY", "CUSTOM_APP_APIKEY",
])
@pytest.mark.parametrize("label", ["agent-lz", "other"])
def test_reserved_infrastructure_settings_reject_instead_of_disappearing(compose, name, label):
    with pytest.raises(ValueError, match="reserved"):
        compose([{"name": name, "value": "unsafe", "label": label}])


@pytest.mark.parametrize("name,value", [
    ("CHAT_BACKEND", "hosted_agent"),
    ("DEPLOYMENT_TOPOLOGY", "hosted-no-panel"),
    ("DEPLOY_INGESTION_CONTAINER_APP", "true"),
    ("DEPLOY_HOSTED_AGENT", "true"),
    ("HOSTED_AGENT_BASE_URL", "https://unverified.invalid"),
    ("HOSTED_AGENT_IMAGE_VERSION", "unverified"),
    ("HOSTED_CONTINUITY_ENABLED", "true"),
    ("HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED", "true"),
    ("PANEL_HISTORY_OWNER_BINDING_VALIDATED", "true"),
    ("PANEL_OPERATOR_SURFACES_ENABLED", "true"),
    ("PANEL_OWNER_INDEX_DATABASE_CONTAINER", "chat-content"),
    ("ORCHESTRATOR_BASE_URL", "https://unverified.invalid"),
    ("AGENTLZ_PLATFORM_OUTPUTS", "{}"),
    ("AGENTLZ_IDENTITY_WEB_CLIENT_ID", "unverified"),
    ("AUDIT_HMAC_KEY", "unsafe"),
    ("HOSTED_CONVERSATION_CAPABILITY_KEY", "unsafe"),
])
def test_protected_fields_cannot_bypass_authoritative_resolution(compose, name, value):
    with pytest.raises(ValueError, match="protected|obsolete"):
        compose([{"name": name, "value": value}])


def test_matching_current_protected_defaults_remain_compatible(compose):
    settings = compose([
        {"name": "ENABLE_CHAT_HISTORY", "value": "false"},
        {"name": "ENABLE_USER_FEEDBACK", "value": "false"},
    ])
    assert next(item for item in settings if item["name"] == "ENABLE_CHAT_HISTORY")["value"] == "false"


def test_non_runtime_labels_are_distinct_even_for_controlled_names(compose):
    entries = [
        {"name": "HOSTED_AGENT_BASE_URL", "value": "staging", "label": "staging"},
        {"name": "HOSTED_AGENT_BASE_URL", "value": "unlabeled", "label": ""},
    ]
    settings = compose(entries)
    for entry in entries:
        assert {**entry, "contentType": "text/plain"} in settings
    assert next(
        entry for entry in settings if entry["name"] == "HOSTED_AGENT_BASE_URL" and entry["label"] == "agent-lz"
    )["value"] == ""


def test_custom_app_derived_endpoint_uses_the_same_ownership_inventory(compose):
    with pytest.raises(ValueError, match="protected"):
        compose(
            [{"name": "WEB_APP_ENDPOINT", "value": "https://unverified.invalid"}],
            {"AGENTLZ_APP_DEFINITION": "samples/custom-app/containerapp"},
        )


def test_duplicate_explicit_name_and_effective_label_are_rejected(compose):
    with pytest.raises(ValueError, match="Duplicate"):
        compose([
            {"name": "CUSTOM", "value": "first", "label": None},
            {"name": "CUSTOM", "value": "second", "label": "agent-lz"},
        ])
