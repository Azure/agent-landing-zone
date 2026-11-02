"""Real shared CLI: canonical selection with no Azure or old-state classification."""

import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from config.deployment import topology
from config.deployment.native import OBSOLETE_SELECTION_KEYS

ROOT = Path(__file__).resolve().parents[1]


def run_cli(selection, *args):
    env = {key: value for key, value in os.environ.items()
           if key not in OBSOLETE_SELECTION_KEYS | {
               "APPLICATION_MODE", "ORCHESTRATION_HOST", "ENABLE_CHAT_HISTORY",
               "ENABLE_USER_FEEDBACK", "ENABLE_PRIVATE_ATTACHMENTS",
               "DEPLOY_COSMOS_DB", "AGENTLZ_APP_DEFINITION",
           }}
    env.update(selection)
    return subprocess.run(
        [sys.executable, "-m", "config.deployment.topology", *args], cwd=ROOT,
        env=env, capture_output=True, text=True, timeout=30,
    )


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
@pytest.mark.parametrize("mode", ["conversational", "workflow", "both"])
def test_cli_materialization_and_description_agree(host, mode):
    selection = {"ORCHESTRATION_HOST": host, "APPLICATION_MODE": mode}
    output = run_cli(selection)
    assert output.returncode == 0, output.stderr
    settings = dict(line.split("=", 1) for line in output.stdout.splitlines())
    description = run_cli(selection, "--describe")
    assert description.returncode == 0, description.stderr
    values = json.loads(description.stdout)
    assert values["ORCHESTRATION_HOST"] == settings["ORCHESTRATION_HOST"] == host
    assert values["APPLICATION_MODE"] == settings["APPLICATION_MODE"] == mode
    assert values["metadata_required"] is (mode != "conversational")
    assert "agent-app-ui" in values["components"]
    assert not set(settings).intersection(OBSOLETE_SELECTION_KEYS)
    assert all(settings[key] == "false" for key in (
        "ENABLE_CHAT_HISTORY", "ENABLE_USER_FEEDBACK", "ENABLE_PRIVATE_ATTACHMENTS",
    ))
    assert "hosted-panel" not in description.stdout and "classic" not in description.stdout


@pytest.mark.parametrize("selection", [
    {"ORCHESTRATION_HOST": ""}, {"ORCHESTRATION_HOST": "classic"},
    {"ORCHESTRATION_HOST": "hosted-panel"}, {"ORCHESTRATION_HOST": "functions"},
    {"APPLICATION_MODE": ""}, {"APPLICATION_MODE": "agent"},
    {"APPLICATION_MODE": "classic"},
])
def test_invalid_canonical_values_fail_without_success_output(selection):
    output = run_cli(selection)
    assert output.returncode == 1
    assert not output.stdout


@pytest.mark.parametrize("key", sorted(OBSOLETE_SELECTION_KEYS))
def test_even_false_or_empty_obsolete_input_is_not_a_migration_request(key):
    for value in ("", "false"):
        output = run_cli({key: value})
        assert output.returncode == 1
        assert not output.stdout
        assert key in output.stderr and "Remove these settings" in output.stderr


def test_resolver_never_reads_existing_deployment_state():
    with patch("subprocess.run", side_effect=AssertionError("Azure reads are forbidden")):
        app = topology.resolve_environment_plan({
            "AZURE_RESOURCE_GROUP": "existing-group",
            "APP_CONFIG_ENDPOINT": "https://unreachable.azconfig.io",
            "HOSTED_AGENT_BASE_URL": "https://old-artifact.example",
        })
    assert app.host == "hosted" and not app.metadata
    assert not hasattr(topology, "read_persisted_settings")
    assert not hasattr(topology, "resource_group_has_resources")


def test_shared_service_profile_is_validated_by_existing_cross_platform_preprovision_entrypoint():
    selection = {
        "HOSTED_AGENT_AUTH_MODE": "service_identity",
        "FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS": "[]",
    }
    with patch("subprocess.run", side_effect=AssertionError("Azure reads are forbidden")):
        assert topology.resolve_environment_plan(selection).host == "hosted"
        with pytest.raises(ValueError, match="WORK_IQ_ENABLED"):
            topology.resolve_environment_plan({**selection, "WORK_IQ_ENABLED": "true"})
        with pytest.raises(ValueError, match="explicitly approved"):
            topology.resolve_environment_plan({**selection, "FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS": "null"})
    for hook in ("preProvision.ps1", "preProvision.sh"):
        source = (ROOT / "scripts" / hook).read_text()
        assert source.index("config.deployment.topology") < source.index("config.deployment.provider")
