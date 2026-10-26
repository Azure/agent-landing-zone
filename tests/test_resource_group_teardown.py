"""Offline protection of resource groups during azd teardown."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from config.deployment import teardown


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"AZURE_RESOURCE_GROUP": "rg-app"},
        {
            "AZURE_RESOURCE_GROUP": "rg-app",
            "AZURE_FOUNDRY_RESOURCE_GROUP": "RG-APP",
            "AZURE_NETWORK_RESOURCE_GROUP": " rg-app ",
        },
    ],
)
def test_legacy_and_same_group_teardown_retains_native_behavior(environment):
    teardown.require_single_resource_group(environment)


@pytest.mark.parametrize(
    "environment",
    [
        {"AZURE_RESOURCE_GROUP": "rg-app", "AZURE_FOUNDRY_RESOURCE_GROUP": "rg-ai"},
        {"AZURE_RESOURCE_GROUP": "rg-app", "AZURE_NETWORK_RESOURCE_GROUP": "rg-net"},
        {"AZURE_FOUNDRY_RESOURCE_GROUP": "rg-ai"},
        {
            "AZURE_RESOURCE_GROUP": "rg-app",
            "AZURE_FOUNDRY_RESOURCE_GROUP": "rg-ai",
            "AZURE_NETWORK_RESOURCE_GROUP": "rg-net",
        },
    ],
)
def test_split_or_ambiguous_scope_cannot_use_automatic_teardown(environment):
    with pytest.raises(teardown.TeardownError, match="blocked"):
        teardown.require_single_resource_group(environment)


@pytest.mark.parametrize("stdout", ["null", "[]", '{"AZURE_RESOURCE_GROUP": 3}', "{"])
def test_invalid_azd_environment_fails_closed(stdout):
    result = CompletedProcess([], 0, stdout, "")
    with patch.object(teardown.shutil, "which", return_value="azd"), patch.object(
        teardown.subprocess, "run", return_value=result
    ):
        with pytest.raises(teardown.TeardownError):
            teardown.read_environment()


def test_selected_environment_is_read_without_azure_or_delete_operations():
    values = {"AZURE_RESOURCE_GROUP": "rg-app"}
    result = CompletedProcess([], 0, json.dumps(values), "")
    with patch.object(teardown.shutil, "which", return_value="azd"), patch.object(
        teardown.subprocess, "run", return_value=result
    ) as run:
        assert teardown.read_environment("selected") == values
    assert run.call_args.args[0] == [
        "azd", "env", "get-values", "--output", "json", "--environment", "selected"
    ]


def test_unrelated_structured_outputs_do_not_change_legacy_teardown():
    values = {"AZURE_RESOURCE_GROUP": "rg-app", "CONTAINER_APPS": [{"name": "ui"}]}
    result = CompletedProcess([], 0, json.dumps(values), "")
    with patch.object(teardown.shutil, "which", return_value="azd"), patch.object(
        teardown.subprocess, "run", return_value=result
    ):
        assert teardown.read_environment() == {"AZURE_RESOURCE_GROUP": "rg-app"}


def test_azd_read_failure_blocks_teardown(caplog, tmp_path):
    with patch.object(
        teardown, "read_environment", side_effect=teardown.TeardownError("read failed")
    ):
        assert teardown.main(["--azure-dir", str(tmp_path)]) == 1
    assert "read failed" in caplog.text


def _binding(tmp_path, *, foundry="rg-app"):
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "resource-groups.json").write_text(json.dumps({
        "version": 1,
        "environment": "selected",
        "subscription": "11111111-1111-1111-1111-111111111111",
        "application": "rg-app",
        "foundry": foundry,
        "network": "rg-app",
    }), encoding="utf-8")


def test_recorded_split_cannot_be_hidden_by_removing_overrides(tmp_path):
    _binding(tmp_path, foundry="rg-ai")
    environment = {"AZURE_RESOURCE_GROUP": "rg-app"}
    with pytest.raises(teardown.TeardownError, match="recorded"):
        teardown.require_safe_teardown(environment, tmp_path, "selected")


def test_same_group_binding_is_not_a_teardown_blocker(tmp_path):
    _binding(tmp_path)
    teardown.require_safe_teardown(
        {
            "AZURE_RESOURCE_GROUP": "RG-APP",
            "AZURE_SUBSCRIPTION_ID": "11111111-1111-1111-1111-111111111111",
        }, tmp_path, "selected"
    )


def test_retargeted_root_is_not_authorized_by_old_single_group_binding(tmp_path):
    _binding(tmp_path)
    with pytest.raises(teardown.TeardownError, match="differ"):
        teardown.require_safe_teardown(
            {
                "AZURE_RESOURCE_GROUP": "rg-other",
                "AZURE_SUBSCRIPTION_ID": "11111111-1111-1111-1111-111111111111",
            }, tmp_path, "selected"
        )


def test_retargeted_subscription_is_blocked_even_with_the_same_root(tmp_path):
    _binding(tmp_path)
    with pytest.raises(teardown.TeardownError, match="subscription differs"):
        teardown.require_safe_teardown(
            {
                "AZURE_RESOURCE_GROUP": "rg-app",
                "AZURE_SUBSCRIPTION_ID": "22222222-2222-2222-2222-222222222222",
            }, tmp_path, "selected"
        )


def test_corrupt_binding_blocks_cli_before_teardown(tmp_path, caplog):
    _binding(tmp_path)
    (tmp_path / "selected" / "resource-groups.json").write_text("{}", encoding="utf-8")
    with patch.object(teardown, "read_environment", return_value={"AZURE_RESOURCE_GROUP": "rg-app"}):
        assert teardown.main(["--azure-dir", str(tmp_path), "--env-name", "selected"]) == 1
    assert "binding is invalid" in caplog.text


def test_environment_mismatch_is_not_a_teardown_authorization(tmp_path):
    with pytest.raises(teardown.TeardownError, match="does not match"):
        teardown.require_safe_teardown({"AZURE_ENV_NAME": "other"}, tmp_path, "selected")


def test_both_hooks_use_the_same_guard():
    root = Path(__file__).resolve().parents[1]
    for name in ("preDown.ps1", "preDown.sh"):
        text = (root / "scripts" / name).read_text(encoding="utf-8")
        assert "config.deployment.teardown" in text
        assert "--azure-dir" in text
    import yaml

    hooks = yaml.safe_load((root / "azure.yaml").read_text(encoding="utf-8"))["hooks"]
    assert hooks["predown"]["windows"]["run"] == "scripts/preDown.ps1"
    assert hooks["predown"]["posix"]["run"] == "scripts/preDown.sh"


def test_powershell_hook_propagates_guard_failure():
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell is not installed")
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "preDown.ps1"
    command = (
        "function python { "
        "if (($args -join ' ') -notmatch 'config.deployment.teardown') { throw 'wrong guard' }; "
        "if (($args -join ' ') -notmatch '--azure-dir') { throw 'missing state directory' }; "
        "$global:LASTEXITCODE = 19 }; "
        f"& '{str(script).replace(chr(39), chr(39) * 2)}'; exit $LASTEXITCODE"
    )
    completed = subprocess.run([pwsh, "-NoProfile", "-Command", command], capture_output=True)
    assert completed.returncode == 19, completed.stderr.decode(errors="replace")


def test_shell_hook_propagates_guard_failure(tmp_path):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash is not installed")
    root = Path(__file__).resolve().parents[1]
    executable = tmp_path / "python3"
    executable.write_text(
        "#!/bin/sh\n"
        'case "$*" in *config.deployment.teardown*--azure-dir*) exit 19 ;; *) exit 27 ;; esac\n',
        encoding="utf-8",
    )
    executable.chmod(0o755)
    environment = dict(os.environ)
    environment["GUARD_BIN"] = str(tmp_path)
    completed = subprocess.run(
        [
            bash, "-c",
            'if command -v cygpath >/dev/null 2>&1; then '
            'GUARD_BIN="$(cygpath -u "$GUARD_BIN")"; fi; '
            'export PATH="$GUARD_BIN:$PATH"; bash scripts/preDown.sh',
        ],
        cwd=root, env=environment, capture_output=True,
    )
    assert completed.returncode == 19, completed.stderr.decode(errors="replace")
