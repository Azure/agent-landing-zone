"""Shared post-provision defaults must not reset foundation configuration."""

import json
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

import pytest

from config.deployment import appconfig_seed as seed


@pytest.mark.parametrize("existing", [[], ["SEARCH_CONNECTION_ID"], ["SEARCH_CONNECTION_ID", "EXTRA"]])
def test_seed_only_adds_missing_exact_keys(existing):
    desired = {"SEARCH_CONNECTION_ID": "", "MODEL_DEPLOYMENTS": "default", "search_connection_id": "custom"}
    assert seed.select_missing_settings(desired, existing) == {
        key: value for key, value in desired.items() if key not in existing
    }


@pytest.mark.parametrize("desired,existing", [
    ([], []), ({"key": None}, []), ({"": "value"}, []),
    ({"key": "value"}, {}), ({}, [None]), ({}, [""]),
])
def test_seed_rejects_malformed_boundaries(desired, existing):
    with pytest.raises(ValueError):
        seed.select_missing_settings(desired, existing)


def test_seed_preserves_existing_references_and_model_metadata(tmp_path):
    payload = tmp_path / "defaults.json"
    payload.write_text(json.dumps({
        "SEARCH_CONNECTION_ID": "", "BING_CONNECTION_ID": "",
        "MODEL_DEPLOYMENTS": "defaults", "APP_API_KEY": "not-a-secret",
        "MISSING": "literal ${VALUE}\nnext",
    }), encoding="utf-8")
    with patch.object(seed, "_run_az", return_value=json.dumps([
        "SEARCH_CONNECTION_ID", "BING_CONNECTION_ID", "MODEL_DEPLOYMENTS", "APP_API_KEY",
    ])) as azure:
        assert seed.prepare_seed_file(payload, "https://example.azconfig.io") == 1
    assert json.loads(payload.read_text(encoding="utf-8")) == {"MISSING": "literal ${VALUE}\nnext"}
    arguments = azure.call_args.args[0]
    assert arguments[:3] == ["appconfig", "kv", "list"]
    assert arguments[arguments.index("--query") + 1] == "[].key"
    assert arguments[arguments.index("--label") + 1] == "agent-lz"
    assert "--all" in arguments


@pytest.mark.parametrize("response", ["invalid-json", "null", "{}", "[42]"])
def test_failed_inventory_never_rewrites_seed_file(tmp_path, response):
    payload = tmp_path / "defaults.json"
    original = '{"KEY": "literal-value"}'
    payload.write_text(original, encoding="utf-8")
    with patch.object(seed, "_run_az", return_value=response):
        with pytest.raises(ValueError):
            seed.prepare_seed_file(payload, "https://example.azconfig.io")
    assert payload.read_text(encoding="utf-8") == original


def test_failed_read_never_rewrites_seed_file(tmp_path):
    payload = tmp_path / "defaults.json"
    original = '{"KEY": "literal-value"}'
    payload.write_text(original, encoding="utf-8")
    with patch.object(seed, "_run_az", side_effect=RuntimeError("Access denied")):
        assert seed.main(["--input", str(payload), "--endpoint", "https://example.azconfig.io"]) == 1
    assert payload.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("count", [0, 1, None])
def test_powershell_seed_import_is_conditional_and_fails_closed(tmp_path, count):
    executable = shutil.which("pwsh")
    assert executable, "PowerShell is required to exercise the shipped hook."
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "postProvision.ps1").read_text(encoding="utf-8-sig")
    block = source.split('    $tempFile = Join-Path $repoRoot ".azure\\agentlz-appconfig-', 1)[1]
    block = '    $tempFile = Join-Path $repoRoot ".azure\\agentlz-appconfig-' + block.split(
        "\nSet-AgentLzAppConfiguration -Endpoint", 1
    )[0]
    (tmp_path / ".azure").mkdir()
    script = tmp_path / "seed.ps1"
    script.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "$repoRoot = $PSScriptRoot\n$Endpoint = 'https://example.azconfig.io'\n$Label = 'agent-lz'\n"
        "$flatSettings = @{ SEARCH_CONNECTION_ID = ''; MISSING = 'value' }\n"
        "function Invoke-NativeCommand { param([scriptblock]$Command) & $Command }\n"
        "function az {\n"
        "  $path = $args[([array]::IndexOf($args, '--path') + 1)]\n"
        "  $body = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json\n"
        "  if ($body.PSObject.Properties.Name -contains 'SEARCH_CONNECTION_ID') { throw 'Existing key imported' }\n"
        "  Set-Content -LiteralPath (Join-Path $PSScriptRoot 'imported') -Value yes\n"
        "  $global:LASTEXITCODE = 0\n}\n"
        "function Invoke-PythonModule { param($ModuleName, $Arguments)\n"
        "  if ($ModuleName -ne 'config.deployment.appconfig_seed') { throw 'Wrong module' }\n"
        + (
            "  $global:LASTEXITCODE = 7\n"
            if count is None
            else
            "  $path = $Arguments[([array]::IndexOf($Arguments, '--input') + 1)]\n"
            "  Set-Content -LiteralPath $path -Value '{\"MISSING\":\"value\"}'\n"
            f"  '{{\"seedCount\":{count}}}'\n  $global:LASTEXITCODE = 0\n"
        )
        + "}\nfunction Exercise-Seed {\n" + block + "\nExercise-Seed\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-File", str(script)],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert (result.returncode == 0) == (count is not None), result.stdout + result.stderr
    assert (tmp_path / "imported").exists() == (count == 1)
    assert not list((tmp_path / ".azure").iterdir())
