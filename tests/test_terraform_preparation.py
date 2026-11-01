"""Backend persistence and authenticated principal lookup; no live credentials."""

import base64
import io
import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from config.deployment import terraform_identity as identity
from config.deployment import terraform_inputs as adapter
from tests.test_deployment_inputs import ENVIRONMENT, ROOT, SUBSCRIPTION

TENANT = ENVIRONMENT["AZURE_TENANT_ID"]
PRINCIPAL = ENVIRONMENT["AZURE_PRINCIPAL_ID"]
BACKEND = {
    "TF_STATE_RESOURCE_GROUP": "rg-independent-state",
    "TF_STATE_STORAGE_ACCOUNT": "fixturestate001",
    "TF_STATE_CONTAINER": "tfstate",
    "ARM_ENVIRONMENT": "public",
}


@pytest.fixture(autouse=True)
def qualified_public_cloud(monkeypatch):
    # Cloud metadata I/O has its own integration-style tests.
    monkeypatch.setattr(adapter, "resolve_cloud", lambda environment, process: {
        "environment": "public", "storage_dns_suffix": "core.windows.net",
    })


@pytest.fixture(autouse=True)
def local_project(tmp_path, monkeypatch):
    """Keep local backend-binding writes outside the shared worktree."""
    project = tmp_path / "project"
    environment_dir = project / ".azure" / ENVIRONMENT["AZURE_ENV_NAME"]
    environment_dir.mkdir(parents=True)
    (environment_dir / ".env").touch()
    monkeypatch.setattr(adapter, "find_repo_root", lambda *args: project)
    return project


def token(**claims):
    payload = base64.urlsafe_b64encode(json.dumps({
        "oid": PRINCIPAL, "tid": TENANT, **claims,
    }).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


@pytest.mark.parametrize("kind,expected", [("user", "User"), ("servicePrincipal", "ServicePrincipal")])
def test_cli_principal_uses_selected_subscription_and_token_oid_not_client_id(kind, expected):
    replies = [
        subprocess.CompletedProcess([], 0, json.dumps({
            "id": SUBSCRIPTION, "tenantId": TENANT,
            "userType": kind,
        }), ""),
        subprocess.CompletedProcess([], 0, token(idtyp="user" if kind == "user" else "app"), ""),
    ]
    with patch.object(identity.subprocess, "run", side_effect=replies) as run:
        result = identity.resolve_principal(ENVIRONMENT, {})
    assert result == {"AZURE_PRINCIPAL_ID": PRINCIPAL, "AZURE_PRINCIPAL_TYPE": expected}
    for call in run.call_args_list:
        assert "--subscription" in call.args[0]
        assert SUBSCRIPTION in call.args[0]
        assert call.kwargs["timeout"] > 0
    assert "get-access-token" in run.call_args_list[-1].args[0]


@pytest.mark.parametrize("override", [
    {"tid": "44444444-4444-4444-4444-444444444444"},
    {"oid": "not-an-object-id"},
    {"oid": None},
    {"idtyp": "app"},
])
def test_invalid_or_mismatched_cli_identity_fails_closed_without_token_logs(override, caplog):
    replies = [
        subprocess.CompletedProcess([], 0, json.dumps({
            "id": SUBSCRIPTION, "tenantId": TENANT, "userType": "user",
        }), ""),
        subprocess.CompletedProcess([], 0, token(**override), ""),
    ]
    with patch.object(identity.subprocess, "run", side_effect=replies):
        with pytest.raises(ValueError) as raised:
            identity.resolve_principal(ENVIRONMENT, {})
    assert "AZURE_PRINCIPAL_ID" in str(raised.value)
    assert "header." not in str(raised.value) + caplog.text


@pytest.mark.parametrize("mode,process,credential_name", [
    ("secret", {"ARM_CLIENT_ID": "client", "ARM_CLIENT_SECRET": "secret-sentinel", "ARM_TENANT_ID": TENANT}, "ClientSecretCredential"),
    ("mi", {"ARM_USE_MSI": "true", "ARM_CLIENT_ID": "client"}, "ManagedIdentityCredential"),
])
def test_process_credentials_never_fall_back_to_cli(mode, process, credential_name):
    credential = Mock()
    credential.get_token.return_value.token = token(idtyp="app")
    with (
        patch(f"azure.identity.{credential_name}", return_value=credential) as factory,
        patch.object(identity.subprocess, "run", side_effect=AssertionError("No CLI identity fallback")),
    ):
        assert identity.resolve_principal(ENVIRONMENT, process)["AZURE_PRINCIPAL_TYPE"] == "ServicePrincipal"
    assert factory.call_count == 1
    credential.close.assert_called_once()


def test_managed_identity_failure_never_uses_a_different_interactive_principal(caplog):
    credential = Mock()
    credential.get_token.side_effect = RuntimeError("secret-sentinel token-sentinel")
    with (
        patch("azure.identity.ManagedIdentityCredential", return_value=credential),
        patch.object(identity.subprocess, "run", side_effect=AssertionError("No fallback")),
        pytest.raises(ValueError) as raised,
    ):
        identity.resolve_principal(ENVIRONMENT, {"ARM_USE_MSI": "true"})
    assert "AZURE_PRINCIPAL_ID" in str(raised.value)
    assert "secret-sentinel" not in str(raised.value) + caplog.text
    assert "token-sentinel" not in str(raised.value) + caplog.text
    credential.close.assert_called_once()


@pytest.mark.parametrize("process", [
    {"ARM_USE_OIDC": "true"},
    {"ARM_USE_MSI": "true", "ARM_MSI_ENDPOINT": "http://endpoint.invalid"},
    {"ARM_USE_MSI": "true", "AZURE_FEDERATED_TOKEN_FILE": "token-file"},
])
def test_unsupported_automatic_auth_mode_requires_explicit_identity_not_a_guess(process):
    with (
        patch.object(identity.subprocess, "run", side_effect=AssertionError("No fallback")),
        pytest.raises(ValueError, match="AZURE_PRINCIPAL_ID"),
    ):
        identity.resolve_principal(ENVIRONMENT, process)


def test_cli_failure_has_no_raw_diagnostics_or_token_output(caplog):
    with patch.object(identity.subprocess, "run", return_value=subprocess.CompletedProcess(
        [], 1, "token-sentinel", "secret-sentinel",
    )):
        with pytest.raises(ValueError) as raised:
            identity.resolve_principal(ENVIRONMENT, {})
    assert "secret-sentinel" not in str(raised.value) + caplog.text
    assert "token-sentinel" not in str(raised.value) + caplog.text


def test_principal_type_conflict_is_not_silently_overwritten():
    environment = {**ENVIRONMENT, **BACKEND, "AZURE_PRINCIPAL_TYPE": "User"}
    environment.pop("AZURE_PRINCIPAL_ID")
    with (
        patch.dict(adapter.os.environ, {}, clear=True),
        patch.object(adapter, "resolve_principal", return_value={
            "AZURE_PRINCIPAL_ID": PRINCIPAL, "AZURE_PRINCIPAL_TYPE": "ServicePrincipal",
        }),
        pytest.raises(ValueError, match="AZURE_PRINCIPAL_TYPE"),
    ):
        adapter.prepare_environment(environment)


@pytest.mark.parametrize("key", ["ARM_ACCESS_KEY", "ARM_SAS_TOKEN"])
def test_preparation_rejects_actual_process_backend_overrides_before_identity_or_persistence(key, monkeypatch):
    monkeypatch.setenv(key, "secret-sentinel")
    environment = {**ENVIRONMENT, **BACKEND}
    with (
        patch.object(adapter, "resolve_principal", side_effect=AssertionError("No lookup")),
        pytest.raises(ValueError, match=key) as raised,
    ):
        adapter.prepare_environment(environment)
    assert "secret-sentinel" not in str(raised.value)


def test_preparation_normalizes_backend_and_infers_missing_principal_type_without_mutation():
    environment = {**ENVIRONMENT, **BACKEND}
    del environment["AZURE_PRINCIPAL_ID"]
    before = dict(environment)
    inferred = {"AZURE_PRINCIPAL_ID": PRINCIPAL, "AZURE_PRINCIPAL_TYPE": "ServicePrincipal"}
    with patch.object(adapter, "resolve_principal", return_value=inferred), patch.dict(adapter.os.environ, {}, clear=True):
        normalized, fields = adapter.prepare_environment(environment)
    assert environment == before
    assert normalized["TF_STATE_SUBSCRIPTION_ID"] == SUBSCRIPTION
    assert normalized["AZURE_PRINCIPAL_TYPE"] == "ServicePrincipal"
    assert fields == {**BACKEND, "TF_STATE_SUBSCRIPTION_ID": SUBSCRIPTION, **inferred}


def test_backend_is_validated_before_automatic_identity_lookup():
    environment = {key: value for key, value in ENVIRONMENT.items() if not key.startswith("TF_STATE_")}
    with (
        patch.object(adapter, "resolve_principal", side_effect=AssertionError("No lookup")),
        pytest.raises(ValueError, match="TF_STATE_"),
    ):
        adapter.prepare_environment(environment)


def test_cli_stdin_persists_only_normalized_safe_values_before_writing_artifacts(tmp_path, monkeypatch, capsys):
    environment = {**ENVIRONMENT, **BACKEND, "ARM_CLIENT_SECRET": "snapshot-secret-sentinel"}
    environment.pop("TF_STATE_SUBSCRIPTION_ID", None)
    environment.pop("AZURE_PRINCIPAL_ID", None)
    output = tmp_path / "main.tfvars.json"
    diagnostic = tmp_path / "diagnostic.json"
    inferred = {"AZURE_PRINCIPAL_ID": PRINCIPAL, "AZURE_PRINCIPAL_TYPE": "ServicePrincipal"}
    monkeypatch.setattr(adapter.sys, "stdin", io.StringIO(json.dumps(environment)))
    calls = []

    def persist(azure_dir, arguments):
        assert not output.exists()
        assert arguments[:2] == ["env", "set"]
        assert arguments[-3:] == ["--environment", "fixture", "--no-prompt"]
        assert "snapshot-secret-sentinel" not in arguments
        calls.append(arguments[2:4])
        return ""

    with (
        patch.dict(adapter.os.environ, {}, clear=True),
        patch.object(adapter, "resolve_principal", return_value=inferred),
        patch.object(adapter, "_run_azd", side_effect=persist),
    ):
        assert adapter.main([
            "--input", str(ROOT / "main.parameters.json"), "--environment", "-",
            "--output", str(output), "--diagnostic-output", str(diagnostic),
            "--no-preserve-images",
        ]) == 0
    assert dict(calls) == {"TF_STATE_SUBSCRIPTION_ID": SUBSCRIPTION, **inferred}
    result = json.loads(output.read_text())
    assert result["principalId"] == PRINCIPAL
    assert result["principalType"] == "ServicePrincipal"
    stdout = capsys.readouterr().out
    assert json.loads(stdout)["normalizedEnvironment"]["TF_STATE_SUBSCRIPTION_ID"] == SUBSCRIPTION
    assert "snapshot-secret-sentinel" not in stdout + output.read_text() + diagnostic.read_text()


def test_persistence_failure_prevents_emitting_usable_artifacts(tmp_path, monkeypatch, caplog):
    from config.deployment.resource_groups import ResourceGroupError

    environment = {**ENVIRONMENT, **BACKEND}
    environment.pop("TF_STATE_SUBSCRIPTION_ID", None)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(environment))
    output = tmp_path / "main.tfvars.json"
    with (
        patch.dict(adapter.os.environ, {}, clear=True),
        patch.object(adapter, "_run_azd", side_effect=ResourceGroupError("not a successful write")),
    ):
        assert adapter.main([
            "--input", str(ROOT / "main.parameters.json"), "--environment", str(snapshot),
            "--output", str(output), "--no-preserve-images",
        ]) == 1
    assert not output.exists()
    assert "persist" in caplog.text.lower()


@pytest.mark.parametrize("selection,has_web,hosted_foundation", [
    ("containerapp", True, False),
    ("hosted", False, True),
])
def test_cli_explicit_definition_preserves_custom_binding_without_store_path(
    selection, has_web, hosted_foundation, tmp_path, monkeypatch, capsys,
):
    definition_path = ROOT / "samples/custom-app" / selection / "app-definition.json"
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    environment = {**ENVIRONMENT, "AGENTLZ_APP_ID": definition["id"]}
    assert "AGENTLZ_APP_DEFINITION" not in environment
    monkeypatch.setattr(adapter.sys, "stdin", io.StringIO(json.dumps(environment)))
    output = tmp_path / "main.tfvars.json"
    diagnostic = tmp_path / "diagnostic.json"
    with (
        patch.dict(adapter.os.environ, {}, clear=True),
        patch.object(adapter, "_run_azd", side_effect=AssertionError("No path or defaults should be persisted")),
    ):
        assert adapter.main([
            "--input", str(ROOT / "main.parameters.json"), "--environment", "-",
            "--app-definition", str(definition_path), "--output", str(output),
            "--diagnostic-output", str(diagnostic), "--no-preserve-images",
        ]) == 0
    native = json.loads(output.read_text(encoding="utf-8"))
    assert ("web" in {app["service_name"] for app in native["containerAppsList"]}) is has_web
    assert native["prepareHostedAgent"] is hosted_foundation
    assert native["deployHostedAgent"] is False
    if hosted_foundation:
        assert native["grantHostedAgentProjectManager"] is False
    diagnostic_values = json.loads(diagnostic.read_text(encoding="utf-8"))["parameters"]
    assert diagnostic_values["containerAppsList"]["value"] == native["containerAppsList"]
    assert diagnostic_values["prepareHostedAgent"]["value"] is hosted_foundation
    stdout = capsys.readouterr().out
    assert "AGENTLZ_APP_DEFINITION" not in json.loads(stdout)["normalizedEnvironment"]
    assert str(definition_path) not in stdout + output.read_text() + diagnostic.read_text()
    assert "AGENTLZ_APP_DEFINITION" not in environment


@pytest.mark.parametrize("selection", [None, "hosted"])
def test_bound_custom_definition_cannot_fall_back_to_bundle_or_mismatched_selection(
    selection, tmp_path, monkeypatch, caplog,
):
    environment = {**ENVIRONMENT, "AGENTLZ_APP_ID": "sample-containerapp"}
    snapshot = tmp_path / "environment.json"
    snapshot.write_text(json.dumps(environment), encoding="utf-8")
    output = tmp_path / "main.tfvars.json"
    arguments = [
        "--input", str(ROOT / "main.parameters.json"),
        "--environment", str(snapshot), "--output", str(output), "--no-preserve-images",
    ]
    if selection:
        arguments += ["--app-definition", str(ROOT / "samples/custom-app" / selection)]
    with (
        patch.dict(adapter.os.environ, {
            # An ambient process path is not a substitute for the explicit flag.
            "AGENTLZ_APP_DEFINITION": str(ROOT / "samples/custom-app/containerapp"),
        }, clear=True),
        patch.object(adapter, "_run_azd", side_effect=AssertionError("No writes on binding mismatch")),
    ):
        assert adapter.main(arguments) == 1
    assert not output.exists()
    assert "bound" in caplog.text.lower()


def test_explicit_definition_overrides_a_stale_snapshot_path_locally(tmp_path, monkeypatch):
    environment = {
        **ENVIRONMENT, "AGENTLZ_APP_ID": "sample-containerapp",
        "AGENTLZ_APP_DEFINITION": "app-definition.json",
    }
    snapshot = tmp_path / "environment.json"
    snapshot.write_text(json.dumps(environment), encoding="utf-8")
    output = tmp_path / "main.tfvars.json"
    with (
        patch.dict(adapter.os.environ, {}, clear=True),
        patch.object(adapter, "_run_azd", side_effect=AssertionError("No path persistence")),
    ):
        assert adapter.main([
            "--input", str(ROOT / "main.parameters.json"), "--environment", str(snapshot),
            "--app-definition", str(ROOT / "samples/custom-app/containerapp"),
            "--output", str(output), "--no-preserve-images",
        ]) == 0
    assert "web" in {
        app["service_name"] for app in json.loads(output.read_text())["containerAppsList"]
    }
    assert json.loads(snapshot.read_text()) == environment


@pytest.mark.parametrize("cloud", ["public", "usgovernment", "china"])
def test_cli_binds_qualified_backend_before_persisting_native_settings(
    cloud, local_project, tmp_path, monkeypatch,
):
    environment = {**ENVIRONMENT, "ARM_ENVIRONMENT": cloud}
    monkeypatch.setattr(adapter, "resolve_cloud", lambda environment, process: {"environment": cloud})
    environment.pop("TF_STATE_SUBSCRIPTION_ID")
    monkeypatch.setattr(adapter.sys, "stdin", io.StringIO(json.dumps(environment)))
    output = tmp_path / "main.tfvars.json"
    binding = local_project / ".azure/fixture/terraform-backend.json"

    def persist(*args):
        recorded = json.loads(binding.read_text())
        assert recorded["subscription"] == SUBSCRIPTION
        assert recorded["environment"] == cloud
        assert recorded["key"] == "agent-landing-zone/fixture.tfstate"
        assert not output.exists()

    with (
        patch.dict(adapter.os.environ, {}, clear=True),
        patch.object(adapter, "_run_azd", side_effect=persist) as writes,
    ):
        assert adapter.main([
            "--input", str(ROOT / "main.parameters.json"), "--environment", "-",
            "--output", str(output), "--no-preserve-images",
        ]) == 0
    writes.assert_called_once()
    assert output.exists()
    assert set(json.loads(binding.read_text())) == {
        "version", "subscription", "resourceGroup", "storageAccount", "container", "key", "environment",
    }


@pytest.mark.parametrize("marker", ["endpoint", "infra", "provisioning", "corrupt-config"])
def test_deployed_environment_missing_backend_binding_requires_restoration(
    marker, local_project, tmp_path, monkeypatch, caplog,
):
    environment = dict(ENVIRONMENT)
    environment_dir = local_project / ".azure/fixture"
    if marker == "endpoint":
        environment["APP_CONFIG_ENDPOINT"] = "https://deployed.azconfig.io"
    elif marker == "corrupt-config":
        (environment_dir / "config.json").write_text("not-json")
    else:
        (environment_dir / "config.json").write_text(json.dumps({marker: {"deployed": True}}))
    monkeypatch.setattr(adapter.sys, "stdin", io.StringIO(json.dumps(environment)))
    output = tmp_path / "main.tfvars.json"
    diagnostic = tmp_path / "diagnostic.json"
    with (
        patch.dict(adapter.os.environ, {}, clear=True),
        patch.object(adapter, "_run_azd", side_effect=AssertionError("No persistence")),
    ):
        assert adapter.main([
            "--input", str(ROOT / "main.parameters.json"), "--environment", "-",
            "--output", str(output), "--diagnostic-output", str(diagnostic),
            "--no-preserve-images",
        ]) == 1
    assert not output.exists() and not diagnostic.exists()
    assert not (environment_dir / "terraform-backend.json").exists()
    assert "restore" in caplog.text.lower()


def test_changed_backend_binding_blocks_persistence_and_native_artifacts(
    local_project, tmp_path, monkeypatch, caplog,
):
    from util.terraform_backend import ensure_backend_binding, resolve_backend

    azure_dir = local_project / ".azure"
    ensure_backend_binding(resolve_backend(ENVIRONMENT), azure_dir, allow_create=True)
    binding = azure_dir / "fixture/terraform-backend.json"
    original_binding = binding.read_bytes()
    environment = {**ENVIRONMENT, "TF_STATE_CONTAINER": "different-state"}
    monkeypatch.setattr(adapter.sys, "stdin", io.StringIO(json.dumps(environment)))
    output = tmp_path / "main.tfvars.json"
    with (
        patch.dict(adapter.os.environ, {}, clear=True),
        patch.object(adapter, "_run_azd", side_effect=AssertionError("No persistence")),
    ):
        assert adapter.main([
            "--input", str(ROOT / "main.parameters.json"), "--environment", "-",
            "--output", str(output), "--no-preserve-images",
        ]) == 1
    assert not output.exists()
    assert binding.read_bytes() == original_binding
    assert "original backend" in caplog.text.lower()


def test_matching_backend_binding_allows_reprovision_with_deployment_markers(
    local_project, tmp_path, monkeypatch,
):
    from util.terraform_backend import ensure_backend_binding, resolve_backend

    azure_dir = local_project / ".azure"
    ensure_backend_binding(resolve_backend(ENVIRONMENT), azure_dir, allow_create=True)
    binding = azure_dir / "fixture/terraform-backend.json"
    original_binding = binding.read_bytes()
    environment = {**ENVIRONMENT, "APP_CONFIG_ENDPOINT": "https://deployed.azconfig.io"}
    monkeypatch.setattr(adapter.sys, "stdin", io.StringIO(json.dumps(environment)))
    output = tmp_path / "main.tfvars.json"
    with (
        patch.dict(adapter.os.environ, {}, clear=True),
        patch.object(adapter, "_run_azd", side_effect=AssertionError("No changed defaults")),
    ):
        assert adapter.main([
            "--input", str(ROOT / "main.parameters.json"), "--environment", "-",
            "--output", str(output), "--no-preserve-images",
        ]) == 0
    assert output.exists()
    assert binding.read_bytes() == original_binding
