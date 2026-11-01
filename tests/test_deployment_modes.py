"""Current public selection and shared provider composition, not migration modes."""

import json
from pathlib import Path

import pytest

from config.deployment.composition import (
    compose_parameters, describe_application, materialized_settings, resolve_mode,
)
from config.deployment.native import OBSOLETE_SELECTION_KEYS, OrchestrationHost
from config.deployment.resolution import resolve_parameters
from config.deployment.app_settings import substitute_values

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    return json.loads((ROOT / "main.parameters.json").read_text(encoding="utf-8"))


def environment(host, mode, **features):
    return {
        "ORCHESTRATION_HOST": host, "APPLICATION_MODE": mode,
        "HOSTED_AGENT_RESOURCE_SCOPE": "https://ai.azure.com/.default", **features,
    }


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
@pytest.mark.parametrize("mode", ["conversational", "workflow", "both"])
@pytest.mark.parametrize("feature", [None, "ENABLE_CHAT_HISTORY", "ENABLE_USER_FEEDBACK"])
def test_provider_neutral_matrix_includes_ui_and_independent_features(host, mode, feature):
    env = environment(host, mode, **({feature: "true"} if feature else {}))
    source = inputs()
    plain = substitute_values({key: entry["value"] for key, entry in source["parameters"].items()}, env)
    # Both adapters use the same real resolver; no provider mocks select a host.
    bicep = compose_parameters(source, env)["parameters"]
    terraform = resolve_parameters(plain, env)
    for key in (
        "containerAppsList", "databaseContainersList", "deployCosmosDb",
        "prepareHostedAgent", "deployHostedAgent", "deployDurableTaskScheduler",
        "additionalAppConfigurationSettings", "useCAppAPIKey",
    ):
        assert bicep[key]["value"] == terraform[key]
    description = describe_application(env)
    assert description["ui_included"]
    assert "agent-app-ui" in description["components"]
    assert description["metadata_required"] is (mode != "conversational" or feature is not None)
    assert bicep["deployCosmosDb"]["value"] == description["metadata_required"]
    assert bicep["prepareHostedAgent"]["value"] is (host == "hosted")
    assert bicep["deployDurableTaskScheduler"]["value"] is (host == "container_apps")
    assert bicep["deployHostedAgent"]["value"] is False
    settings = materialized_settings(env)
    assert not set(settings).intersection(OBSOLETE_SELECTION_KEYS)
    assert not set(description).intersection(OBSOLETE_SELECTION_KEYS)
    for key in ("ENABLE_CHAT_HISTORY", "ENABLE_USER_FEEDBACK", "ENABLE_PRIVATE_ATTACHMENTS"):
        assert settings[key] == ("true" if key == feature else "false")


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
@pytest.mark.parametrize("mode", ["conversational", "both"])
def test_private_files_select_only_frontend_metadata_not_ingestion(host, mode):
    env = environment(host, mode, ENABLE_PRIVATE_ATTACHMENTS="true")
    composed = compose_parameters(inputs(), env)["parameters"]
    assert composed["deployCosmosDb"]["value"]
    assert [item["name"] for item in composed["databaseContainersList"]["value"]] == ["native-ui-metadata"]
    assert not any(item["service_name"] == "dataingest" for item in composed["containerAppsList"]["value"])
    assert materialized_settings(env)["ENABLE_CHAT_HISTORY"] == "false"


def test_unset_defaults_are_native_and_obsolete_booleans_are_rejected():
    assert resolve_mode({}) is OrchestrationHost.HOSTED
    with pytest.raises(ValueError, match="Obsolete.*DEPLOY_HOSTED_AGENT"):
        resolve_mode({"DEPLOY_HOSTED_AGENT": "false"})
    assert resolve_mode({"ORCHESTRATION_HOST": "container_apps"}) is OrchestrationHost.CONTAINER_APPS


@pytest.mark.parametrize("key", sorted(OBSOLETE_SELECTION_KEYS))
def test_old_declaration_cannot_be_republished_under_any_label(key):
    source = inputs()
    source["parameters"]["additionalAppConfigurationSettings"]["value"].append({
        "name": key, "value": "false", "label": "private-label",
    })
    with pytest.raises(ValueError, match="obsolete deployment setting"):
        compose_parameters(source, environment("hosted", "conversational"))


def test_shipped_template_exposes_canonical_bindings_not_foundation_host_controls():
    source = inputs()["parameters"]
    for key in ("prepareHostedAgent", "deployHostedAgent", "deployDurableTaskScheduler", "useCAppAPIKey"):
        assert source[key]["value"] is False
    settings = {item["name"]: item["value"] for item in source["additionalAppConfigurationSettings"]["value"]}
    assert settings == {
        "ORCHESTRATION_HOST": "${ORCHESTRATION_HOST=hosted}",
        "APPLICATION_MODE": "${APPLICATION_MODE=conversational}",
    }
