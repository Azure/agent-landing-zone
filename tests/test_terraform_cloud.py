"""Qualified Azure cloud context, independent of user-overridable workload DNS."""

import io
import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from config.deployment import terraform_cloud as cloud
from config.deployment import terraform_inputs as adapter
from config.deployment import terraform_identity as identity
from tests.test_deployment_inputs import ENVIRONMENT, ROOT, SUBSCRIPTION, values


CLOUDS = [
    ("AzureCloud", "public", "core.windows.net", "https://management.azure.com/", "https://login.microsoftonline.com"),
    ("AzureUSGovernment", "usgovernment", "core.usgovcloudapi.net", "https://management.usgovcloudapi.net/", "https://login.microsoftonline.us"),
    ("AzureChinaCloud", "china", "core.chinacloudapi.cn", "https://management.chinacloudapi.cn", "https://login.chinacloudapi.cn"),
]


def replies(name, suffix, resource_manager, authority):
    return [
        subprocess.CompletedProcess([], 0, json.dumps({
            "id": SUBSCRIPTION, "environmentName": name,
        }), ""),
        subprocess.CompletedProcess([], 0, json.dumps({
            "name": name, "suffixes": {"storageEndpoint": suffix},
            "endpoints": {"resourceManager": resource_manager, "activeDirectory": authority},
        }), ""),
    ]


@pytest.mark.parametrize("name,environment,suffix,resource_manager,authority", CLOUDS)
def test_cli_cloud_is_qualified_against_selected_subscription_and_actual_metadata(name, environment, suffix, resource_manager, authority):
    snapshot = {key: value for key, value in ENVIRONMENT.items() if key != "ARM_ENVIRONMENT"}
    with patch.object(cloud.subprocess, "run", side_effect=replies(name, suffix, resource_manager, authority)) as run:
        assert cloud.resolve_cloud(snapshot, {}) == {
            "environment": environment, "storage_dns_suffix": suffix,
        }
    assert "--subscription" in run.call_args_list[0].args[0]
    assert SUBSCRIPTION in run.call_args_list[0].args[0]
    assert run.call_args_list[1].args[0][1:3] == ["cloud", "show"]
    assert all("set" not in call.args[0] for call in run.call_args_list)


@pytest.mark.parametrize("name,environment,suffix,resource_manager,authority", CLOUDS)
def test_explicit_process_auth_cloud_never_uses_an_unrelated_cli_login(name, environment, suffix, resource_manager, authority):
    snapshot = {**ENVIRONMENT, "ARM_ENVIRONMENT": environment}
    with patch.object(cloud.subprocess, "run", side_effect=AssertionError("No CLI fallback")):
        assert cloud.resolve_cloud(snapshot, {
            "ARM_USE_OIDC": "true", "ARM_ENVIRONMENT": environment,
        }) == {"environment": environment, "storage_dns_suffix": suffix}


@pytest.mark.parametrize("process", [
    {"ARM_USE_MSI": "true"},
    {"ARM_CLIENT_ID": "client", "ARM_CLIENT_SECRET": "secret-sentinel"},
    {"ARM_USE_OIDC": "true"},
])
def test_process_auth_requires_explicit_cloud_instead_of_guessing_public(process):
    snapshot = {key: value for key, value in ENVIRONMENT.items() if key != "ARM_ENVIRONMENT"}
    with (
        patch.object(cloud.subprocess, "run", side_effect=AssertionError("No CLI fallback")),
        pytest.raises(ValueError, match="ARM_ENVIRONMENT"),
    ):
        cloud.resolve_cloud(snapshot, process)


def test_process_cloud_is_normalized_to_the_shared_provider_identifier():
    snapshot = {key: value for key, value in ENVIRONMENT.items() if key != "ARM_ENVIRONMENT"}
    with patch.object(cloud.subprocess, "run", side_effect=AssertionError("No CLI fallback")):
        assert cloud.resolve_cloud(snapshot, {
            "ARM_ENVIRONMENT": "UsGoVeRnMeNt", "ARM_USE_MSI": "true",
        }) == {"environment": "usgovernment", "storage_dns_suffix": "core.usgovcloudapi.net"}


@pytest.mark.parametrize("name,environment,suffix,resource_manager,authority", CLOUDS)
def test_automatic_principal_uses_the_same_qualified_sdk_cloud(name, environment, suffix, resource_manager, authority):
    credential = Mock()
    result = {"AZURE_PRINCIPAL_ID": ENVIRONMENT["AZURE_PRINCIPAL_ID"], "AZURE_PRINCIPAL_TYPE": "ServicePrincipal"}
    with (
        patch("azure.identity.ClientSecretCredential", return_value=credential) as factory,
        patch.object(identity, "_token_principal", return_value=result),
        patch.object(identity.subprocess, "run", side_effect=AssertionError("No CLI fallback")),
    ):
        assert identity.resolve_principal({**ENVIRONMENT, "ARM_ENVIRONMENT": environment}, {
            "ARM_CLIENT_ID": "client", "ARM_CLIENT_SECRET": "secret-sentinel",
        }) == result
    assert factory.call_args.kwargs["authority"] == authority
    credential.get_token.assert_called_once_with(resource_manager.rstrip("/") + "/.default")


@pytest.mark.parametrize("environment", ["unknown", "custom", "AzureCloud", "public ", "${CLOUD}"])
def test_unknown_cloud_rejected_without_echoing_input(environment):
    with pytest.raises(ValueError) as raised:
        cloud.cloud_context(environment)
    assert environment not in str(raised.value)


def test_cli_cloud_conflicting_with_explicit_environment_fails():
    with (
        patch.object(cloud.subprocess, "run", side_effect=replies(*(
            CLOUDS[1][0], CLOUDS[1][2], CLOUDS[1][3], CLOUDS[1][4],
        ))),
        pytest.raises(ValueError, match="ARM_ENVIRONMENT"),
    ):
        cloud.resolve_cloud({**ENVIRONMENT, "ARM_ENVIRONMENT": "public"}, {})


def test_process_and_store_cloud_mismatch_is_not_silently_overridden():
    with (
        patch.object(cloud.subprocess, "run", side_effect=AssertionError("No CLI fallback")),
        pytest.raises(ValueError, match="ARM_ENVIRONMENT"),
    ):
        cloud.resolve_cloud({**ENVIRONMENT, "ARM_ENVIRONMENT": "public"}, {
            "ARM_USE_MSI": "true", "ARM_ENVIRONMENT": "china",
        })


@pytest.mark.parametrize("index,section,key,bad", [
    (0, None, "environmentName", "UnknownCloud"),
    (0, None, "id", "44444444-4444-4444-4444-444444444444"),
    (1, None, "name", "AzureChinaCloud"),
    (1, "suffixes", "storageEndpoint", "custom.invalid"),
    (1, "endpoints", "resourceManager", "https://custom.invalid"),
    (1, "endpoints", "activeDirectory", "https://custom.invalid"),
])
def test_unknown_subscription_or_modified_cloud_metadata_fails_closed(index, section, key, bad):
    responses = replies(CLOUDS[0][0], CLOUDS[0][2], CLOUDS[0][3], CLOUDS[0][4])
    document = json.loads(responses[index].stdout)
    target = document if section is None else document[section]
    target[key] = bad
    responses[index].stdout = json.dumps(document)
    with (
        patch.object(cloud.subprocess, "run", side_effect=responses),
        pytest.raises(ValueError),
    ):
        cloud.resolve_cloud(ENVIRONMENT, {})


@pytest.mark.parametrize("name,environment,suffix,resource_manager,authority", CLOUDS)
def test_native_context_and_acr_override_and_literal_json_are_independent(name, environment, suffix, resource_manager, authority):
    product = values()
    product["acrDnsSuffix"] = "custom.registry.example"
    product["deploymentTags"] = {"literal": '${LITERAL} "quote" \\ slash\n'}
    result = adapter.compose_inputs(product, {**ENVIRONMENT, "ARM_ENVIRONMENT": environment})
    assert result["azureCloud"] == {"environment": environment, "storage_dns_suffix": suffix}
    assert result["acrDnsSuffix"] == "custom.registry.example"
    rendered = adapter.render_template(result)
    assert "$" not in rendered
    assert json.loads(rendered) == result


def test_pure_composition_default_is_qualified_public_without_cli_io():
    snapshot = {key: value for key, value in ENVIRONMENT.items() if key != "ARM_ENVIRONMENT"}
    with patch.object(cloud.subprocess, "run", side_effect=AssertionError("Pure composition")):
        assert adapter.compose_inputs(values(), snapshot)["azureCloud"] == {
            "environment": "public", "storage_dns_suffix": "core.windows.net",
        }


def test_preparation_persists_detected_cloud_before_native_inputs_and_excludes_it_from_diagnostic(tmp_path, monkeypatch, capsys):
    environment_dir = tmp_path / ".azure/fixture"
    environment_dir.mkdir(parents=True)
    (environment_dir / ".env").touch()
    monkeypatch.setattr(adapter, "find_repo_root", lambda *args: tmp_path)
    snapshot = {key: value for key, value in ENVIRONMENT.items() if key != "ARM_ENVIRONMENT"}
    output = tmp_path / "main.tfvars.json"
    diagnostic = tmp_path / "diagnostic.json"
    monkeypatch.setattr(adapter.sys, "stdin", io.StringIO(json.dumps(snapshot)))
    calls = []

    def persist(azure_dir, arguments):
        assert not output.exists()
        binding = json.loads((environment_dir / "terraform-backend.json").read_text())
        assert binding["environment"] == "usgovernment"
        calls.append(arguments[2:4])
        return ""

    with (
        patch.dict(adapter.os.environ, {}, clear=True),
        patch.object(cloud.subprocess, "run", side_effect=replies(
            CLOUDS[1][0], CLOUDS[1][2], CLOUDS[1][3], CLOUDS[1][4],
        )),
        patch.object(adapter, "_run_azd", side_effect=persist),
    ):
        assert adapter.main([
            "--input", str(ROOT / "main.parameters.json"), "--environment", "-",
            "--output", str(output), "--diagnostic-output", str(diagnostic),
            "--no-preserve-images",
        ]) == 0
    assert dict(calls) == {"ARM_ENVIRONMENT": "usgovernment"}
    assert json.loads(output.read_text())["azureCloud"] == {
        "environment": "usgovernment", "storage_dns_suffix": "core.usgovcloudapi.net",
    }
    assert "azureCloud" not in json.loads(diagnostic.read_text())["parameters"]
    assert json.loads(capsys.readouterr().out)["normalizedEnvironment"]["ARM_ENVIRONMENT"] == "usgovernment"
