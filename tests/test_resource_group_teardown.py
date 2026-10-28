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
from util.terraform_backend import ensure_backend_binding, resolve_backend


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"AZURE_RESOURCE_GROUP": "rg-app"},
        {"AZURE_RESOURCE_GROUP": "rg-ai", "AZURE_APP_RESOURCE_GROUP": "RG-AI"},
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
        {"AZURE_RESOURCE_GROUP": "rg-ai", "AZURE_APP_RESOURCE_GROUP": "rg-app"},
        {"AZURE_APP_RESOURCE_GROUP": "rg-app"},
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


def _terraform_binding(tmp_path, *, managed=None):
    subscription = "11111111-1111-1111-1111-111111111111"
    environment = {
        "AZURE_ENV_NAME": "selected", "AZURE_SUBSCRIPTION_ID": subscription,
        "AZURE_RESOURCE_GROUP": "rg-ai", "AZURE_APP_RESOURCE_GROUP": "rg-app",
        "AZURE_NETWORK_RESOURCE_GROUP": "rg-net",
        "TF_STATE_RESOURCE_GROUP": "rg-state", "TF_STATE_STORAGE_ACCOUNT": "examplestate",
        "TF_STATE_CONTAINER": "tfstate", "TF_STATE_SUBSCRIPTION_ID": subscription,
        "ARM_ENVIRONMENT": "public",
    }
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "resource-groups.json").write_text(json.dumps({
        "version": 2, "environment": "selected", "subscription": subscription,
        "foundry": "rg-ai", "application": "rg-app", "network": "rg-net",
    }), encoding="utf-8")
    (directory / "terraform-resource-groups.json").write_text(json.dumps({
        "managedResourceGroupNames": ["rg-ai", "rg-app", "rg-net"] if managed is None else managed,
    }), encoding="utf-8")
    ensure_backend_binding(resolve_backend(environment), tmp_path, allow_create=True)
    return environment


@pytest.mark.parametrize("managed", [[], ["rg-ai"], ["rg-ai", "rg-app", "rg-net"]])
def test_native_terraform_down_allows_bound_split_and_byo_groups_without_azure_calls(tmp_path, managed):
    environment = _terraform_binding(tmp_path, managed=managed)
    with patch.object(teardown.subprocess, "run", side_effect=AssertionError("No Azure calls")):
        teardown.require_safe_teardown(environment, tmp_path, "selected", provider="terraform")


@pytest.mark.parametrize("mutation", [
    {"AZURE_SUBSCRIPTION_ID": "22222222-2222-2222-2222-222222222222"},
    {"AZURE_RESOURCE_GROUP": "rg-other"},
    {"AZURE_APP_RESOURCE_GROUP": "rg-other"},
    {"AZURE_NETWORK_RESOURCE_GROUP": ""},
    {"TF_STATE_STORAGE_ACCOUNT": "anotherstate"},
    {"TF_STATE_CONTAINER": "another-container"},
    {"TF_STATE_RESOURCE_GROUP": "rg-app"},
    {"ARM_ENVIRONMENT": "china"},
    {"ARM_ACCESS_KEY": "not-a-secret"},
])
def test_terraform_down_cannot_retarget_recorded_scope_or_state(tmp_path, mutation):
    environment = _terraform_binding(tmp_path)
    environment.update(mutation)
    with pytest.raises(ValueError):
        teardown.require_safe_teardown(environment, tmp_path, "selected", provider="terraform")


@pytest.mark.parametrize("filename", [
    "resource-groups.json", "terraform-resource-groups.json", "terraform-backend.json",
])
def test_terraform_down_requires_original_private_records(tmp_path, filename):
    environment = _terraform_binding(tmp_path)
    (tmp_path / "selected" / filename).unlink()
    with pytest.raises(ValueError):
        teardown.require_safe_teardown(environment, tmp_path, "selected", provider="terraform")
    assert not (tmp_path / "selected" / filename).exists()


@pytest.mark.parametrize("document", [
    {}, [], {"managedResourceGroupNames": ["rg-foreign"]},
    {"managedResourceGroupNames": ["rg-ai", "RG-AI"]},
])
def test_terraform_down_rejects_malformed_or_foreign_ownership(tmp_path, document):
    environment = _terraform_binding(tmp_path)
    (tmp_path / "selected" / "terraform-resource-groups.json").write_text(
        json.dumps(document), encoding="utf-8",
    )
    with pytest.raises(ValueError):
        teardown.require_safe_teardown(environment, tmp_path, "selected", provider="terraform")


def test_bicep_selection_cannot_delete_a_terraform_owned_environment(tmp_path):
    environment = _terraform_binding(tmp_path)
    with pytest.raises(teardown.TeardownError, match="Terraform ownership"):
        teardown.require_safe_teardown(environment, tmp_path, "selected")


def test_backend_binding_is_stable_and_never_implicitly_retargeted(tmp_path):
    environment = _terraform_binding(tmp_path)
    path = tmp_path / "selected" / "terraform-backend.json"
    original = path.read_bytes()
    ensure_backend_binding(resolve_backend(environment), tmp_path, allow_create=True)
    assert path.read_bytes() == original
    environment["TF_STATE_STORAGE_ACCOUNT"] = "anotherstate"
    with pytest.raises(ValueError, match="recorded state address"):
        ensure_backend_binding(resolve_backend(environment), tmp_path, allow_create=True)
    assert path.read_bytes() == original


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
