"""Execute the real shared native publication/preparation blocks in both shells."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest
import yaml

from config.appdefinition import (
    AppDefinitionValidationError,
    is_reserved_hosted_agent_env,
    load_definition,
    validate_definition,
)
from config.deployment import custom_application, hosted

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("host", ["hosted", "container_apps"])
@pytest.mark.parametrize("mode", ["conversational", "workflow", "both"])
@pytest.mark.parametrize("failure", ["none", "deploy", "publish"])
def test_native_application_lifecycle_uses_one_path_and_fails_closed(tmp_path, shell, host, mode, failure):
    suffix = "ps1" if shell == "pwsh" else "sh"
    source = (ROOT / "scripts" / f"preDeploy.{suffix}").read_text(encoding="utf-8-sig")
    block = source[source.index("# BEGIN native application lifecycle"):source.index("# END native application lifecycle")]
    environment = {**os.environ, "FAILURE": failure, "ORCHESTRATION_HOST": host, "APPLICATION_MODE": mode}
    if shell == "pwsh":
        script = """
$nativeMode = $true; $repoRoot = '.'
$globalEnv = [pscustomobject]@{}
$script:calls = @()
function Invoke-PythonModule {
    param($ModuleName, $Arguments)
    $script:calls += "$ModuleName $($Arguments -join ' ')"
    $global:LASTEXITCODE = 0
    if (($env:FAILURE -eq 'deploy' -and $ModuleName -eq 'config.deployment.native_deploy') -or
        ($env:FAILURE -eq 'publish' -and $ModuleName -eq 'config.deployment.appconfig')) { $global:LASTEXITCODE = 1 }
}
function Get-AzdEnv { param($projectPath) return [pscustomobject]@{ ORCHESTRATION_HOST = $env:ORCHESTRATION_HOST; APPLICATION_MODE = $env:APPLICATION_MODE } }
""" + block + "\n$script:calls | ConvertTo-Json -Compress\n"
        command = [shutil.which(shell), "-NoProfile", "-File"]
    else:
        script = """
set -uo pipefail
native_mode=true; repo_root=.
red() { printf '%s\\n' "$*" >&2; }
python3() {
  printf '%s\\n' "$*" >> "$CALLS_FILE"
  [ "$FAILURE" != deploy ] || [ "$*" != '-m config.deployment.native_deploy --deploy' ] || return 1
  [ "$FAILURE" != publish ] || [ "$*" != '-m config.deployment.appconfig --require-hosted-endpoint' ] || return 1
}
""" + block
        environment["CALLS_FILE"] = str(tmp_path / "calls.txt")
        command = [shutil.which(shell)]
    path = tmp_path / f"hook.{suffix}"
    path.write_text(script, encoding="utf-8", newline="\n")
    result = subprocess.run([*command, str(path)], env=environment, cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    if failure == "none":
        assert result.returncode == 0, result.stdout + result.stderr
        calls = json.loads(result.stdout) if shell == "pwsh" else (tmp_path / "calls.txt").read_text().splitlines()
        expected = ["config.deployment.native_deploy --deploy", "config.deployment.appconfig --require-hosted-endpoint"]
        assert [call.removeprefix("-m ") for call in calls] == expected
    else:
        assert result.returncode != 0, result.stdout
        assert "components processed" not in result.stdout


@pytest.mark.parametrize("reserved_key", [
    "FOUNDRY_PROJECT_ENDPOINT",
    "FOUNDRY_AGENT_VERSION",
    "AGENT_ID",
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
])
def test_custom_hosted_deploy_rejects_reserved_env_before_azd_deploy(tmp_path, reserved_key):
    app = tmp_path / "hosted"
    shutil.copytree(ROOT / "samples" / "custom-app" / "hosted", app)
    azure_yaml = app / "azure.yaml"
    project = yaml.safe_load(azure_yaml.read_text(encoding="utf-8"))
    project["services"]["agent"]["env"][reserved_key] = "override"
    azure_yaml.write_text(yaml.safe_dump(project, sort_keys=False), encoding="utf-8")

    with patch.object(custom_application.subprocess, "run") as run:
        with pytest.raises(AppDefinitionValidationError) as caught:
            custom_application.deploy_service(
                str(app / "app-definition.json"), "agent", {"AZURE_ENV_NAME": "test"},
            )
    run.assert_not_called()
    assert f"azure.yaml#/services/agent/env/{reserved_key}" in str(caught.value)


def test_shipped_hosted_manifests_avoid_platform_reserved_env_vars():
    for rel_path, service_name in (
        ("hosted-agent/azure.yaml", "orchestrator-agent"),
        ("config/deployment/templates/native-hosted.yaml", "publication"),
        ("samples/custom-app/hosted/azure.yaml", "agent"),
    ):
        project = yaml.safe_load((ROOT / rel_path).read_text(encoding="utf-8"))
        env_map = project["services"][service_name].get("env") or {}
        assert not any(is_reserved_hosted_agent_env(key) for key in env_map), rel_path
        assert env_map.get("APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL") == "true"


def test_hosted_sample_runs_without_app_config_and_satisfies_responses_smoke(monkeypatch):
    sample_dir = ROOT / "samples" / "custom-app" / "hosted"
    validate_definition(load_definition(sample_dir, repo_root=ROOT), ROOT)
    azure_yaml_text = (sample_dir / "azure.yaml").read_text(encoding="utf-8")
    assert "APP_CONFIG_ENDPOINT" not in azure_yaml_text
    requirements_text = (sample_dir / "src" / "requirements.txt").read_text(encoding="utf-8")
    assert "azure-appconfiguration" not in requirements_text

    spec = importlib.util.spec_from_file_location("sample_hosted_main", sample_dir / "src" / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    doc = module.__doc__ or ""
    assert "azure-ai-agentserver-responses" in doc
    assert "GET /responses/{id}" in doc
    assert "invoke_agent" in doc

    for key in ("FOUNDRY_PROJECT_ENDPOINT", "AZURE_AI_PROJECT_ENDPOINT", "APP_CONFIG_ENDPOINT"):
        monkeypatch.delenv(key, raising=False)
    assert module.answer() == "Hello! Sample agent running on project unknown."

    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", "https://fallback.services.ai.azure.com/api/projects/local")
    assert module.answer() == (
        "Hello! Sample agent running on project https://fallback.services.ai.azure.com/api/projects/local."
    )

    foundry_endpoint = "https://foundry.services.ai.azure.com/api/projects/sample"
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", foundry_endpoint)
    assert module.answer() == f"Hello! Sample agent running on project {foundry_endpoint}."

    server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for probe in ("/health", "/readiness", "/liveness"):
            with opener.open(base_url + probe, timeout=5) as resp:
                assert resp.status == 200
                assert json.loads(resp.read().decode("utf-8")) == {"status": "ok"}

        req = urllib.request.Request(
            base_url + "/responses",
            data=b'{"input":[{"role":"user","content":"Hello!"}]}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(req, timeout=5) as resp:
            assert resp.status == 200
            raw_body = resp.read().decode("utf-8")
        hosted.validate_responses_smoke_output(raw_body)
        parsed = json.loads(raw_body)
        assert foundry_endpoint in parsed["output"][0]["content"][0]["text"]

        with pytest.raises(urllib.error.HTTPError) as not_found:
            opener.open(base_url + "/unknown", timeout=5)
        assert not_found.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
