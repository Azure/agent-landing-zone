"""T036/T037: infra-only provision and the azd deploy foundation guard (R7, R8)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from config.deployment import outputs
from config.deployment.existing_images import (
    PLACEHOLDER_IMAGE,
    PLACEHOLDER_IMAGE_PREFIX,
    parse_container_app_images,
    placeholder_plan,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_MESSAGE = "run azd provision first"
# Statements that reach Azure: any ``az`` command or ``azd deploy``.
AZURE_CALL = re.compile(r"^\s*(?:&\s*)?(?:az\s+[a-z]|azd\s+deploy\b)", re.IGNORECASE)

TRIO = [
    {"name": "ui", "kind": "containerapp"},
    {"name": "orchestrator", "kind": "azure.ai.agent"},
    {"name": "ingestion", "kind": "containerapp"},
]


# --- T036 -------------------------------------------------------------------


def test_provision_plans_placeholders_only_for_containerapp_components():
    plan = placeholder_plan(TRIO, images={})
    assert plan == {"ui": PLACEHOLDER_IMAGE, "ingestion": PLACEHOLDER_IMAGE}
    # Zero application images: every planned image is the public placeholder.
    assert all(image.startswith(PLACEHOLDER_IMAGE_PREFIX) for image in plan.values())


def test_hosted_only_app_gets_no_container_apps():
    assert placeholder_plan([{"name": "agent", "kind": "azure.ai.agent"}], {}) == {}


def test_reprovision_never_resets_a_deployed_image():
    discovered = parse_container_app_images(
        [
            {"tags": {"azd-service-name": "ui", "azd-env-name": "dev"},
             "image": "cr.azurecr.io/agent-app-ui:1"},
            {"tags": {"azd-service-name": "ingestion", "azd-env-name": "dev"},
             "image": PLACEHOLDER_IMAGE},
        ],
        "dev",
    )
    plan = placeholder_plan(TRIO, discovered)
    assert plan["ui"] == "cr.azurecr.io/agent-app-ui:1"
    assert plan["ingestion"] == PLACEHOLDER_IMAGE


def test_unknown_kind_and_duplicates_fail_closed():
    with pytest.raises(ValueError, match="unsupported kind"):
        placeholder_plan([{"name": "x", "kind": "function"}], {})
    with pytest.raises(ValueError, match="Duplicate"):
        placeholder_plan([{"name": "x", "kind": "containerapp"}] * 2, {})


# --- T037 -------------------------------------------------------------------


@pytest.mark.parametrize(
    "environment",
    [{}, {"AZURE_RESOURCE_GROUP": "rg"}, {"APP_CONFIG_ENDPOINT": "https://a.azconfig.io"}],
)
def test_guard_fails_before_any_azure_call(environment):
    with mock.patch("subprocess.run") as run, pytest.raises(
        outputs.FoundationMissingError
    ) as error:
        outputs.require_foundation(environment)
    run.assert_not_called()
    assert GUARD_MESSAGE in str(error.value).lower()


def test_guard_cli_exits_nonzero_without_azure_calls(monkeypatch, caplog):
    for name in outputs.FOUNDATION_REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    with mock.patch("subprocess.run") as run:
        assert outputs.main(["--check-foundation"]) == 1
    run.assert_not_called()
    assert GUARD_MESSAGE in caplog.text.lower()


def test_guard_command_reports_actionable_error_on_stderr():
    environment = {key: value for key, value in os.environ.items()
                   if key not in outputs.FOUNDATION_REQUIRED_ENV}
    result = subprocess.run(
        [sys.executable, "-m", "config.deployment.outputs", "--check-foundation"],
        cwd=REPO_ROOT, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert GUARD_MESSAGE in result.stderr.lower()


def test_guard_passes_when_foundation_exists():
    outputs.require_foundation(
        {"AZURE_RESOURCE_GROUP": "rg", "APP_CONFIG_ENDPOINT": "https://a.azconfig.io"}
    )


@pytest.mark.parametrize("script", ["preDeploy.ps1", "preDeploy.sh"])
def test_predeploy_guard_message_precedes_azure_calls(script):
    lines = (REPO_ROOT / "scripts" / script).read_text(encoding="utf-8").splitlines()
    code = [(i, line) for i, line in enumerate(lines) if not line.lstrip().startswith("#")]
    guard = next((i for i, line in code if GUARD_MESSAGE in line.lower()), None)
    assert guard is not None, f"{script} lacks the '{GUARD_MESSAGE}' guard"
    first_call = next((i for i, line in code if AZURE_CALL.search(line)), None)
    assert first_call is None or guard < first_call, (
        f"{script}: Azure call on line {first_call + 1} precedes the guard "
        f"on line {guard + 1}"
    )
