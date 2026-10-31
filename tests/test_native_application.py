"""Native composition contracts; no credentials or Azure writes."""
import json
from pathlib import Path

import pytest
from unittest.mock import patch
import subprocess
import shutil
import os
import yaml

from config.deployment.native import resolve_application, scheduler_settings
from config.deployment import native_deploy, native_access
from config.deployment import appconfig, private_network
from config.deployment import hosted_image
from config.deployment.composition import compose_parameters


ROOT = Path(__file__).resolve().parents[1]
SUB = "11111111-1111-4111-8111-111111111111"
HUB = {
    "resourceId": f"/subscriptions/{SUB}/resourceGroups/rg-test/providers/Microsoft.DurableTask/schedulers/test",
    "endpoint": "https://returned.eastus.durabletask.io",
    "taskHubName": "agent-lz",
}


def environment(host="hosted", mode="conversational"):
    return {
        "ORCHESTRATION_HOST": host, "APPLICATION_MODE": mode,
        "AZURE_ENV_NAME": "test", "AZURE_SUBSCRIPTION_ID": SUB,
        "AZURE_RESOURCE_GROUP": "rg-test", "RESOURCE_TOKEN": "test",
        "HOSTED_AGENT_RESOURCE_SCOPE": "https://ai.azure.com/.default",
        "AZURE_AI_PROJECT_ENDPOINT": "https://test.services.ai.azure.com/api/projects/test",
        "AZURE_AI_PROJECT_RESOURCE_ID": f"/subscriptions/{SUB}/resourceGroups/rg-test/providers/Microsoft.CognitiveServices/accounts/test/projects/test",
        "AZURE_CONTAINER_REGISTRY_ENDPOINT": "test.azurecr.io",
        "HOSTED_AGENT_PREPARED": "true", "APP_CONFIG_ENDPOINT": "https://test.azconfig.io",
        "HOSTED_AGENT_DEPLOYMENT": json.dumps({"durableTask": HUB}),
    }


def test_native_defaults_do_not_require_metadata_or_ingestion():
    app = resolve_application({})
    assert app.mode == "conversational"
    assert app.host == "hosted"
    assert app.publications == ("conversational",)
    assert not app.metadata
    assert not app.ingestion


@pytest.mark.parametrize("topology,host", [
    ("classic", "container_apps"),
    ("hosted-no-panel", "hosted"),
    ("hosted-panel", "hosted"),
])
def test_topology_maps_only_at_composition_boundary(topology, host):
    assert resolve_application({"DEPLOYMENT_TOPOLOGY": topology}).host == host


@pytest.mark.parametrize("values", [
    {"APPLICATION_MODE": "agent"},
    {"ORCHESTRATION_HOST": "functions"},
    {"ORCHESTRATION_HOST": "hosted", "DEPLOYMENT_TOPOLOGY": "classic"},
    {"ORCHESTRATION_HOST": "container_apps", "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true"},
    {"DEPLOYMENT_TOPOLOGY": "hosted-panel", "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false"},
    {"PRESERVE_CLASSIC_RUNTIME": "true"},
    {"CHAT_BACKEND": "orchestrator"},
    {"DEPLOY_INGESTION_CONTAINER_APP": "perhaps"},
])
def test_contradictions_and_unknown_values_fail(values):
    with pytest.raises(ValueError):
        resolve_application(values)


def test_both_publishes_separate_modes_not_a_universal_endpoint():
    assert resolve_application({"APPLICATION_MODE": "both"}).publications == (
        "conversational", "workflow",
    )


def test_scheduler_binding_uses_returned_endpoint_and_is_nonsecret():
    handoff = {
        "durableTask": {
            "resourceId": "/subscriptions/s/resourceGroups/g/providers/Microsoft.DurableTask/schedulers/test",
            "endpoint": "https://returned-suffix.eastus.durabletask.io",
            "taskHubName": "agent-lz",
        },
    }
    settings = scheduler_settings({"HOSTED_AGENT_DEPLOYMENT": json.dumps(handoff)})
    assert settings["DURABLE_TASK_SCHEDULER_CONNECTION_STRING"] == (
        "Endpoint=https://returned-suffix.eastus.durabletask.io;"
        "TaskHub=agent-lz;Authentication=DefaultAzure"
    )
    assert settings["DURABLE_TASK_HUB_NAME"] == "agent-lz"


@pytest.mark.parametrize("handoff", [{}, {"durableTask": None}, {
    "durableTask": {"endpoint": "http://guessed", "taskHubName": "agent-lz"},
}])
def test_missing_or_invalid_backend_never_guesses(handoff):
    with pytest.raises(ValueError):
        scheduler_settings({"HOSTED_AGENT_DEPLOYMENT": json.dumps(handoff)})


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
@pytest.mark.parametrize("mode,cosmos", [("conversational", False), ("workflow", True), ("both", True)])
def test_native_foundation_consumers_and_no_blanket_grants(host, mode, cosmos):
    result = compose_parameters(json.loads((ROOT / "main.parameters.json").read_text()), environment(host, mode))
    values = {k: v["value"] for k, v in result["parameters"].items()}
    assert values["deployCosmosDb"] is cosmos
    assert values["deployDurableTaskScheduler"] is (host == "container_apps")
    assert values["deployHostedAgent"] is False  # application publication is not infra ownership
    assert not any(a["service_name"] == "dataingest" for a in values["containerAppsList"])
    assert all("KeyVaultSecretsUser" not in a["roles"] and "CosmosDBBuiltInDataContributor" not in a["roles"]
               for a in values["containerAppsList"])
    assert [c["name"] for c in values["databaseContainersList"]] == (["native-ui-metadata"] if cosmos else [])
    settings = {s["name"]: s["value"] for s in values["additionalAppConfigurationSettings"]}
    assert settings["CHAT_BACKEND"] == ""
    assert all(s["label"] == "agent-lz" for s in values["additionalAppConfigurationSettings"])
    if host == "container_apps":
        worker = next(a for a in values["containerAppsList"] if a["service_name"] == "orchestrator")
        assert worker["disable_ingress"] and not worker["dapr"]["enabled"]
        assert worker["min_replicas"] >= 1


def test_nl2sql_is_an_explicit_catalog_not_a_global_checkpoint_database():
    source = json.loads((ROOT / "main.parameters.json").read_text())
    with pytest.raises(ValueError, match="NL2SQL_SOURCE_REGISTRY"):
        compose_parameters(source, {**environment(), "NL2SQL_ENABLED": "true"})
    result = compose_parameters(source, {
        **environment(), "NL2SQL_ENABLED": "true", "NL2SQL_SOURCE_REGISTRY": "cosmos",
    })["parameters"]
    assert result["deployCosmosDb"]["value"]
    assert [c["name"] for c in result["databaseContainersList"]["value"]] == ["datasources"]
    with pytest.raises(ValueError):
        resolve_application({**environment(), "ENABLE_PRIVATE_ATTACHMENTS": "true"})


def test_native_metadata_is_ui_owned_and_optional_for_conversation():
    assert resolve_application({**environment(), "ENABLE_CHAT_HISTORY": "true"}).metadata
    assert resolve_application({**environment(), "ENABLE_USER_FEEDBACK": "true"}).metadata
    assert resolve_application(environment(mode="workflow")).metadata


def test_worker_client_settings_use_real_output_and_actual_registration_names():
    settings = native_deploy.runtime_settings(environment("container_apps", "both"))
    assert settings["DURABLE_AGENT_NAME"] == "alz-conversation"
    assert settings["DURABLE_WORKFLOW_NAME"] == "alz-research-review"
    assert "Endpoint=https://returned.eastus.durabletask.io;" in settings["DURABLE_TASK_SCHEDULER_CONNECTION_STRING"]
    assert settings["HOSTED_AGENT_BASE_URL"] == settings["HOSTED_WORKFLOW_BASE_URL"] == ""
    with pytest.raises(ValueError, match="published runtime registration"):
        native_deploy.runtime_settings({**environment("container_apps"), "DURABLE_AGENT_NAME": "unregistered"})


def test_native_appconfig_requires_every_selected_endpoint_and_has_no_legacy_route():
    env = {
        **environment(mode="both"), "HOSTED_AGENT_BASE_URL": "https://test.example/agent",
        "HOSTED_WORKFLOW_BASE_URL": "https://test.example/workflow",
    }
    with patch.object(appconfig, "_container_app", return_value={"fqdn": "ui.example", "principalId": "principal"}):
        settings = appconfig.build_settings(env, require_hosted_endpoint=True)
        assert settings["CHAT_BACKEND"] == ""
        assert settings["HOSTED_WORKFLOW_BASE_URL"] == env["HOSTED_WORKFLOW_BASE_URL"]
        assert "HOSTED_CONTINUITY_ENABLED" not in settings
        with pytest.raises(ValueError, match="HOSTED_WORKFLOW_BASE_URL"):
            appconfig.build_settings({**env, "HOSTED_WORKFLOW_BASE_URL": ""}, require_hosted_endpoint=True)


def test_private_ca_hook_uses_provisioned_scheduler_without_network_calls():
    seen = []
    with patch.object(private_network, "check_endpoint", side_effect=lambda k, v: seen.append((k, v))):
        assert private_network.check_stage({**environment("container_apps"), "NETWORK_ISOLATION": "true"}, "pre-deploy") == 0
    assert seen == [
        ("APP_CONFIG_ENDPOINT", "https://test.azconfig.io"),
        ("DURABLE_TASK_SCHEDULER_ENDPOINT", HUB["endpoint"]),
    ]


@pytest.mark.parametrize("failure", [False, True])
def test_hosted_both_renders_separate_native_publications_then_publishes_outputs(tmp_path, failure):
    (tmp_path / ".azure/test").mkdir(parents=True)
    (tmp_path / ".azure/test/.env").write_text("AZURE_ENV_NAME=test\n")
    (tmp_path / "config/deployment/templates").mkdir(parents=True)
    shutil.copy(ROOT / "config/deployment/templates/native-hosted.yaml", tmp_path / "config/deployment/templates")
    shutil.copy(ROOT / "manifest.json", tmp_path)
    calls, publications, grants = [], [], []
    def run(args, **kwargs):
        calls.append((args, kwargs["cwd"]))
        if args[:2] == ["azd", "deploy"]:
            publications.append(yaml.safe_load((kwargs["cwd"] / "azure.yaml").read_text())["services"]["publication"])
            if failure and len(publications) == 2:
                return subprocess.CompletedProcess(args, 1, "", "omitted")
        output = json.dumps({"AGENT_PUBLICATION_RESPONSES_ENDPOINT": f"https://test.example/{len(publications)}/responses"})
        return subprocess.CompletedProcess(args, 0, output, "")
    with patch.object(native_deploy, "prepare_environment", return_value=("sha256:" + "a" * 64, "b" * 40)), \
         patch.object(native_deploy, "discover", side_effect=lambda env: type("Plan", (), {"principal_id": env["HOSTED_AGENT_NAME"]})()), \
         patch.object(native_deploy, "apply", side_effect=lambda p: grants.append(p.principal_id)), \
         patch.object(native_deploy, "grant_runtime_features"):
        if failure:
            with pytest.raises(RuntimeError):
                native_deploy.deploy_hosted(tmp_path, environment(mode="both"), run=run)
        else:
            result = native_deploy.deploy_hosted(tmp_path, environment(mode="both"), run=run)
            assert result == {"HOSTED_AGENT_BASE_URL": "https://test.example/1", "HOSTED_WORKFLOW_BASE_URL": "https://test.example/2"}
    assert [p["env"]["APPLICATION_MODE"] for p in publications] == ["conversational", "workflow"]
    assert all(p["startupCommand"] == "python -m src.native.hosted" for p in publications)
    assert all(p["protocols"] == [{"protocol": "responses", "version": "2.0.0"}] for p in publications)
    assert all("hooks" not in p for p in publications)  # never the stateless legacy postdeploy adapter
    assert grants == (["agent-app-orchestrator"] if failure else ["agent-app-orchestrator", "agent-app-orchestrator-workflow"])
    advertised = [a for a, cwd in calls if cwd == tmp_path and a[:3] == ["azd", "env", "set"] and a[3].endswith("BASE_URL")]
    assert bool(advertised) is not failure


def test_ca_preparation_preserves_container_environment_and_sets_official_command(tmp_path):
    updates = []
    def run(args, **kwargs):
        if "show" in args:
            service = args[args.index("--name") + 1].rsplit("-", 1)[1]
            doc = {"properties": {"template": {"containers": [{
                "name": service, "env": [{"name": "UNRELATED", "value": "kept"}],
            }]}}}
            return subprocess.CompletedProcess(args, 0, json.dumps(doc), "")
        if "--yaml" in args:
            updates.append(yaml.safe_load(Path(args[args.index("--yaml") + 1]).read_text()))
        return subprocess.CompletedProcess(args, 0, "", "")
    native_deploy.prepare_container_apps(tmp_path, environment("container_apps", "both"), run=run)
    assert len(updates) == 2
    worker = updates[1]["properties"]["template"]["containers"][0]
    assert worker["command"] == ["python", "-m", "src.native.durable"]
    assert worker["args"] == []
    assert {"name": "UNRELATED", "value": "kept"} in worker["env"]
    assert any(e["name"] == "DURABLE_TASK_SCHEDULER_CONNECTION_STRING" for e in worker["env"])


def test_actual_secret_consumers_get_exact_secret_scopes_and_empty_gets_none():
    env = {**environment(), "KEY_VAULT_URI": "https://test.vault.azure.net/"}
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return "[]" if "list" in args else ""
    native_access.grant_secrets(env, "principal", (), run=run)
    assert not calls
    native_access.grant_secrets(env, "principal", ("AUDIT-HMAC-KEY", "source-secret"), run=run)
    writes = [c for c in calls if "create" in c]
    assert {c[c.index("--scope")+1].rsplit("/secrets/", 1)[1] for c in writes} == {"AUDIT-HMAC-KEY", "source-secret"}
    assert all(c[c.index("--role")+1] == "4633458b-17de-408a-b874-0445c86b69e6" for c in writes)
    with pytest.raises(ValueError):
        native_access.tool_secret_names({"NATIVE_TOOL_SECRET_NAMES": '["../outside"]'})


def test_native_component_source_gate_preserves_pins_and_blocks_old_images_before_build(tmp_path):
    with pytest.raises(ValueError, match="compatible component pins"):
        native_deploy.validate_component_source(tmp_path, "agent-app-orchestrator", environment("container_apps"))
    (tmp_path / "src/native").mkdir(parents=True)
    (tmp_path / "src/native/durable.py").write_text("# fixture\n")
    native_deploy.validate_component_source(tmp_path, "agent-app-orchestrator", environment("container_apps"))
    with patch.object(hosted_image, "clone_pinned_source") as clone, \
         patch.object(hosted_image, "build_source_image") as build:
        with pytest.raises(ValueError, match="manifest-pinned"):
            hosted_image.prepare_hosted_image(
                image_version=None, registry="test", registry_endpoint="test.azurecr.io",
                image_name="native", source_repo="https://example.invalid/source",
                source_ref="v1", source_commit="b"*40, required_source_paths=("src/native/hosted.py",),
            )
        assert clone.call_args.kwargs["expected_commit"] == "b"*40
        build.assert_not_called()


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("failure", [False, True])
def test_real_native_hook_block_calls_shared_lifecycle_and_fails_closed(tmp_path, shell, failure):
    extension = "ps1" if shell == "pwsh" else "sh"
    source = (ROOT / "scripts" / f"preDeploy.{extension}").read_text(encoding="utf-8-sig")
    block = source.split("# BEGIN native application lifecycle", 1)[1].split("# END native application lifecycle", 1)[0]
    if shell == "pwsh":
        setup = (
            "$nativeMode=$true; $repoRoot='.'\n"
            "function Get-AzdEnv { return [pscustomobject]@{ ORCHESTRATION_HOST='hosted' } }\n"
            "function Invoke-PythonModule { param($ModuleName,$Arguments); Write-Output $ModuleName;"
            f" $global:LASTEXITCODE={'1' if failure else '0'} }}\n"
        )
        args = [shutil.which("pwsh"), "-NoProfile", "-File"]
    else:
        setup = (
            "native_mode=true; repo_root=.\nred() { printf '%s\\n' \"$*\" >&2; }\n"
            "python3() { printf '%s\\n' \"$2\";"
            f" return {'1' if failure else '0'}; }}\n"
        )
        args = [shutil.which("bash")]
    script = tmp_path / ("hook." + extension)
    script.write_text(setup + block, encoding="utf-8", newline="\n")
    result = subprocess.run([*args, str(script)], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert (result.returncode != 0) is failure
    assert "config.deployment.native_deploy" in result.stdout
    assert ("config.deployment.appconfig" in result.stdout) is not failure
