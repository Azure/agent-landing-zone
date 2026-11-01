"""Optional current-product ingestion; no persisted selection or migration branch."""

import json
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

import pytest

from config.appdefinition.loader import effective_components, load_selected_definition
from config.appdefinition.roles import plan_assignments
from config.deployment import appconfig, composition
from config.deployment.native import OrchestrationHost

ROOT = Path(__file__).resolve().parents[1]
FLAG = "DEPLOY_INGESTION_CONTAINER_APP"


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
@pytest.mark.parametrize("mode", ["conversational", "workflow", "both"])
@pytest.mark.parametrize("enabled", [False, True])
def test_selection_agrees_in_composition_definition_roles_and_description(host, mode, enabled):
    env = {
        "ORCHESTRATION_HOST": host, "APPLICATION_MODE": mode,
        FLAG: str(enabled).lower(), "HOSTED_AGENT_RESOURCE_SCOPE": "https://ai.azure.com/.default",
    }
    assert composition.resolve_ingestion_selection(env) is enabled
    composed = composition.compose_parameters(json.loads((ROOT / "main.parameters.json").read_text()), env)
    apps = composed["parameters"]["containerAppsList"]["value"]
    assert any(item["service_name"] == "dataingest" for item in apps) is enabled
    definition = load_selected_definition(env)
    components = effective_components(definition, hosted_orchestration=host == "hosted", deploy_ingestion=enabled)
    assert any(item["name"] == "ingestion" for item in components) is enabled
    assignments = plan_assignments(definition, hosted_orchestration=host == "hosted", deploy_ingestion=enabled)
    assert any(item.component == "ingestion" for item in assignments) is enabled
    assert ("agent-app-ingestion" in composition.describe_application(env)["components"]) is enabled
    assert composition.materialized_settings(env)[FLAG] == str(enabled).lower()
    assert all("CosmosDBBuiltInDataContributor" not in item["roles"] for item in apps)


def test_unset_selection_is_off_even_with_existing_outputs():
    assert not composition.resolve_ingestion_selection({
        "AZURE_RESOURCE_GROUP": "existing", "APP_CONFIG_ENDPOINT": "https://existing.azconfig.io",
    })


@pytest.mark.parametrize("value", ["", "yes", "1", "invalid"])
def test_invalid_booleans_fail_before_endpoint_discovery(value):
    with patch.object(appconfig, "_container_app", side_effect=AssertionError("No discovery")):
        with pytest.raises(ValueError, match=FLAG):
            appconfig.build_settings({FLAG: value})


@pytest.mark.parametrize("settings", [
    {"RETRIEVAL_BACKEND": "ai_search"},
    {"FOUNDRY_IQ_PATTERN": "searchIndex", "FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND": "searchIndex"},
])
def test_app_dependent_sources_fail_before_endpoint_discovery(settings):
    with patch.object(appconfig, "_container_app", side_effect=AssertionError("No discovery")):
        with pytest.raises(ValueError, match="SEARCH_RAG_INDEX_NAME"):
            appconfig.build_settings({FLAG: "false", **settings})


def test_deliberate_external_index_is_preserved_without_inference():
    env = {
        "ORCHESTRATION_HOST": "container_apps", FLAG: "false",
        "RETRIEVAL_BACKEND": "ai_search", "SEARCH_RAG_INDEX_NAME": "external-index",
    }
    source = json.loads((ROOT / "main.parameters.json").read_text())
    result = composition.compose_parameters(source, env)["parameters"]
    settings = {item["name"]: item["value"] for item in result["additionalAppConfigurationSettings"]["value"]}
    assert settings["SEARCH_RAG_INDEX_NAME"] == "external-index"
    assert not any(item["service_name"] == "dataingest" for item in result["containerAppsList"]["value"])


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
def test_disabled_endpoint_reconciliation_never_looks_up_ingestion(host):
    env = {
        "ORCHESTRATION_HOST": host, FLAG: "false", "RESOURCE_TOKEN": "test",
        "AZURE_RESOURCE_GROUP": "rg-test", "HOSTED_AGENT_RESOURCE_SCOPE": "https://ai.azure.com/.default",
        "HOSTED_AGENT_DEPLOYMENT": json.dumps({"durableTask": {
            "endpoint": "https://test.eastus.durabletask.io", "taskHubName": "agent-lz",
            "resourceId": "/subscriptions/s/resourceGroups/g/providers/Microsoft.DurableTask/schedulers/test",
        }}),
    }
    with patch.object(appconfig, "_container_app", return_value={"fqdn": "test.example", "principalId": "test"}) as discovery:
        appconfig.build_settings(env)
    assert not any("dataingest" in call.args[1] for call in discovery.call_args_list)


@pytest.mark.parametrize("host", list(OrchestrationHost))
@pytest.mark.parametrize("enabled", [False, True])
def test_powershell_postprovision_skips_worker_ingress_and_optional_ingestion_reads(tmp_path, host, enabled):
    source = (ROOT / "scripts/postProvision.ps1").read_text(encoding="utf-8-sig")
    start = source.index("    $frontendFqdn = Invoke-AzTsv")
    end = source.index("    $modelDeployments = @(", start)
    script = f"""
$ErrorActionPreference = 'Stop'
$deployIngestion = ${str(enabled).lower()}
$hostedMode = ${str(host is OrchestrationHost.HOSTED).lower()}
$frontendAppName = 'frontend'; $orchestratorAppName = 'orchestrator'
$dataIngestAppName = 'dataingest'; $resourceGroup = 'test-group'
$script:calls = @()
function Invoke-AzTsv {{
    param($Arguments, $Description, [switch]$Required)
    $script:calls += ($Arguments -join ' ')
    return 'mock-value'
}}
""" + source[start:end] + """
[ordered]@{ apps = @($containerApps.serviceName); calls = $script:calls } | ConvertTo-Json -Compress
"""
    path = tmp_path / "hook.ps1"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run([shutil.which("pwsh"), "-NoProfile", "-File", str(path)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert ("dataingest" in payload["apps"]) is enabled
    assert any("dataingest" in call for call in payload["calls"]) is enabled
    assert not any("orchestrator" in call and "ingress.fqdn" in call for call in payload["calls"])


@pytest.mark.parametrize("shell,suffix", [("pwsh", "ps1"), ("bash", "sh")])
def test_both_predeploy_loops_skip_before_checkout_or_build(tmp_path, shell, suffix):
    text = (ROOT / "scripts" / f"preDeploy.{suffix}").read_text(encoding="utf-8-sig")
    if shell == "pwsh":
        start = text.index("foreach ($c in $manifest.components) {")
        end = text.index("  $repo = $c.repo", start)
        script = """
$manifest = @{ components = @(@{ name = 'agent-app-ingestion' }) }
$selectedComponents = @('agent-app-ui'); $definitionManifestNames = @('agent-app-ingestion')
$deploymentMode = 'hosted/conversational'
""" + text[start:end] + "\nthrow 'unselected component was checked out'\n}\n"
        args = ["-NoProfile", "-File"]
    else:
        start = text.index("while IFS= read -r comp; do", text.index("# ---------- Iterate components"))
        end = text.index('  repo="$(printf', start)
        script = """
set -e
selected_components='agent-app-ui'; definition_manifest_names=' agent-app-ingestion '
deployment_mode=hosted/conversational
yellow() { printf '%s\\n' "$*"; }
jq() { printf '%s\\n' agent-app-ingestion; }
""" + text[start:end] + "\necho 'unselected component was checked out'\nexit 99\ndone <<< '{}'\n"
        args = []
    path = tmp_path / f"hook.{suffix}"
    path.write_text(script, encoding="utf-8", newline="\n")
    result = subprocess.run([shutil.which(shell), *args, str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "unselected component was checked out" not in result.stdout
