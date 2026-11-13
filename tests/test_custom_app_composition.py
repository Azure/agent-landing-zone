"""Declared custom-only consumers remain valid under either canonical host."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from config.deployment import appconfig, native_deploy, private_network
from config.deployment.composition import (
    DeploymentTopologyError, compose_parameters, custom_container_apps, describe_application,
)
from config.deployment.app_settings import substitute_values
from config.deployment.resolution import resolve_parameters

ROOT = Path(__file__).resolve().parents[1]


def source():
    return json.loads((ROOT / "main.parameters.json").read_text())


def environment(host, mode, selection):
    return {
        "ORCHESTRATION_HOST": host, "APPLICATION_MODE": mode,
        "AGENTLZ_APP_DEFINITION": selection,
        "AZURE_RESOURCE_GROUP": "rg-test", "RESOURCE_TOKEN": "test",
    }


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
@pytest.mark.parametrize("mode", ["conversational", "workflow", "both"])
@pytest.mark.parametrize("selection,services,hosted", [
    ("samples/custom-app/containerapp", ["web"], False),
    ("samples/custom-app/hosted", [], True),
])
def test_actual_declared_apps_and_foundation_are_identical_in_both_providers(host, mode, selection, services, hosted):
    env = environment(host, mode, selection)
    document = source()
    bicep = compose_parameters(document, env)["parameters"]
    plain = substitute_values({key: value["value"] for key, value in document["parameters"].items()}, env)
    terraform = resolve_parameters(plain, env)
    for key in ("containerAppsList", "deployCosmosDb", "databaseContainersList", "prepareHostedAgent", "deployHostedAgent", "deployDurableTaskScheduler"):
        assert bicep[key]["value"] == terraform[key]
    assert [item["service_name"] for item in terraform["containerAppsList"]] == services
    assert terraform["prepareHostedAgent"] is hosted
    assert terraform["deployHostedAgent"] is False
    assert terraform["deployDurableTaskScheduler"] is False
    assert not terraform["deployCosmosDb"] and not terraform["databaseContainersList"]
    if hosted:
        assert terraform["grantHostedAgentProjectManager"] is False
    description = describe_application(env)
    assert not description["bundled_application"] and not description["ui_included"]
    assert not description["metadata_required"] and not description["components"] and not description["publications"]


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
def test_custom_container_preserves_explicit_resources_roles_and_selection_path(host):
    folder = environment(host, "conversational", "samples/custom-app/containerapp")
    file = {**folder, "AGENTLZ_APP_DEFINITION": folder["AGENTLZ_APP_DEFINITION"] + "/app-definition.json"}
    first = compose_parameters(source(), folder)
    assert first == compose_parameters(source(), file)
    web, = first["parameters"]["containerAppsList"]["value"]
    assert web["external"] and web["cpu"] == "0.5" and web["memory"] == "1.0Gi"
    assert web["canonical_name"] == "WEB_APP" and web["name"] is None
    assert web["roles"] == ["AcrPull"]
    assert "image" not in web


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
@pytest.mark.parametrize("mode", ["conversational", "workflow", "both"])
def test_custom_runtime_publication_discovers_only_declared_services(host, mode):
    env = environment(host, mode, "samples/custom-app/containerapp")
    with patch.object(appconfig, "_container_app", return_value={"fqdn": "web.example.test", "principalId": "web-principal"}) as discovery:
        settings = appconfig.build_settings(env, require_hosted_endpoint=True)
    assert [call.args[1] for call in discovery.call_args_list] == ["ca-test-web"]
    assert settings["WEB_APP_NAME"] == "ca-test-web"
    assert settings["WEB_APP_ENDPOINT"] == "https://web.example.test"
    assert json.loads(settings["CONTAINER_APPS"])[0]["serviceName"] == "web"
    assert "DURABLE_TASK_SCHEDULER_CONNECTION_STRING" not in settings
    assert "FRONTEND_APP_NAME" not in settings
    assert "ORCHESTRATOR_APP_NAME" not in settings
    assert settings["ORCHESTRATION_HOST"] == host and settings["APPLICATION_MODE"] == mode


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
def test_custom_hosted_requires_no_missing_bundled_runtime_or_client(host):
    env = environment(host, "both", "samples/custom-app/hosted")
    with patch.object(appconfig, "_container_app", side_effect=AssertionError("No undeclared Container Apps")):
        settings = appconfig.build_settings(env, require_hosted_endpoint=True)
    assert json.loads(settings["CONTAINER_APPS"]) == []
    assert "DURABLE_TASK_SCHEDULER_CONNECTION_STRING" not in settings
    assert native_deploy.runtime_settings(env) == {
        "ORCHESTRATION_HOST": host, "APPLICATION_MODE": "both",
        "ENABLE_CHAT_HISTORY": "false", "ENABLE_USER_FEEDBACK": "false",
        "ENABLE_PRIVATE_ATTACHMENTS": "false",
    }


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
def test_infrastructure_only_and_mixed_definitions_are_not_injected_with_defaults(tmp_path, host):
    container = json.loads((ROOT / "samples/custom-app/containerapp/app-definition.json").read_text())["components"][0]
    agent = json.loads((ROOT / "samples/custom-app/hosted/app-definition.json").read_text())["components"][0]
    path = tmp_path / "app-definition.json"
    for components, expected_hosted in (([], False), ([container], False), ([container, agent], True)):
        path.write_text(json.dumps({"components": components}), encoding="utf-8")
        result = compose_parameters(source(), environment(host, "both", str(path)))["parameters"]
        assert result["prepareHostedAgent"]["value"] is expected_hosted
        assert result["deployHostedAgent"]["value"] is False
        assert len(result["containerAppsList"]["value"]) == int(container in components)


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
def test_custom_network_preflight_probes_only_declared_dependencies(host):
    env = {**environment(host, "both", "samples/custom-app/containerapp"),
           "NETWORK_ISOLATION": "true", "APP_CONFIG_ENDPOINT": "https://config.azconfig.io"}
    with patch.object(private_network, "check_endpoint") as probe:
        assert private_network.check_stage(env, "pre-deploy") == 0
    probe.assert_called_once_with("APP_CONFIG_ENDPOINT", env["APP_CONFIG_ENDPOINT"])


@pytest.mark.parametrize("profiles,expected_profile", [
    (
        [
            {"name": "Consumption", "workloadProfileType": "Consumption"},
            {"name": "main", "workloadProfileType": "D4", "minimumCount": 0, "maximumCount": 1},
        ],
        "main",
    ),
    ([{"name": "Consumption", "workloadProfileType": "Consumption"}], "Consumption"),
    ([], "Consumption"),
    (
        [{"name": "dedicated", "workloadProfileType": "D4", "minimumCount": 1, "maximumCount": 3}],
        "dedicated",
    ),
])
@pytest.mark.parametrize("via_env", [False, True])
def test_custom_container_apps_resolve_effective_workload_profile_in_both_providers(
    profiles, expected_profile, via_env,
):
    document = source()
    env = {
        **environment("hosted", "conversational", "samples/custom-app/containerapp"),
        "HOSTED_AGENT_RESOURCE_SCOPE": "https://ai.azure.com/.default",
    }
    if via_env:
        env["WORKLOAD_PROFILES"] = json.dumps(profiles)
    else:
        document["parameters"]["workloadProfiles"]["value"] = profiles
    bicep = compose_parameters(document, env)["parameters"]
    plain = substitute_values({key: entry["value"] for key, entry in document["parameters"].items()}, env)
    terraform = resolve_parameters(plain, env)
    assert bicep["workloadProfiles"]["value"] == terraform["workloadProfiles"] == profiles
    assert bicep["containerAppsList"]["value"] == terraform["containerAppsList"]
    web, = terraform["containerAppsList"]
    assert web["service_name"] == "web"
    assert web["profile_name"] == expected_profile
    if via_env:
        direct, = custom_container_apps(env, [], hosted_orchestration=True)
        assert direct["profile_name"] == expected_profile


def test_custom_container_apps_reject_ambiguous_multi_dedicated_profiles_without_main_or_consumption():
    ambiguous = [
        {"name": "dedicated-d4", "workloadProfileType": "D4", "minimumCount": 1, "maximumCount": 2},
        {"name": "dedicated-d8", "workloadProfileType": "D8", "minimumCount": 1, "maximumCount": 2},
    ]
    document = source()
    document["parameters"]["workloadProfiles"]["value"] = ambiguous
    env = {
        **environment("container_apps", "conversational", "samples/custom-app/containerapp"),
    }
    with pytest.raises(DeploymentTopologyError, match="workloadProfiles"):
        compose_parameters(document, env)
    plain = substitute_values({key: entry["value"] for key, entry in document["parameters"].items()}, env)
    with pytest.raises(DeploymentTopologyError, match="workloadProfiles"):
        resolve_parameters(plain, env)
    # Hosted-only custom definitions have no Container Apps and remain unaffected.
    hosted_env = {
        **environment("hosted", "conversational", "samples/custom-app/hosted"),
        "HOSTED_AGENT_RESOURCE_SCOPE": "https://ai.azure.com/.default",
    }
    assert compose_parameters(document, hosted_env)["parameters"]["containerAppsList"]["value"] == []

