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


@pytest.mark.parametrize("mode", ["appConfig", "containerEnv", "none"])
@pytest.mark.parametrize("failure", [False, True])
def test_powershell_seed_import_is_conditional_and_fails_closed(tmp_path, mode, failure):
    """Seeding belongs to Python; the hook must select it and propagate failure.

    The seed-file tests above independently prove existing keys survive. The
    hook must not retain its former second, PowerShell-only flat-settings import.
    """
    executable = shutil.which("pwsh")
    assert executable, "PowerShell is required to exercise the shipped hook."
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "postProvision.ps1").read_text(encoding="utf-8-sig")
    block = source.split("# BEGIN runtime configuration publication\n", 1)[1].split(
        "# END runtime configuration publication", 1
    )[0]
    script = tmp_path / "seed.ps1"
    script.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f"$runtimeMode = '{mode}'\n"
        "function az { throw 'Hook must not flatten/import settings itself' }\n"
        "function Invoke-PythonModule { param($ModuleName, $Arguments)\n"
        "  if ($ModuleName -ne 'config.deployment.appconfig') { throw 'Wrong owner' }\n"
        "  Set-Content -LiteralPath (Join-Path $PSScriptRoot 'published') -Value yes\n"
        f"  $global:LASTEXITCODE = {7 if failure else 0}\n"
        "}\n" + block + "\nWrite-Output 'setup'\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-File", str(script)],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    selected = mode == "appConfig"
    assert (result.returncode == 0) == (not selected or not failure), result.stdout + result.stderr
    assert (tmp_path / "published").exists() == selected
    assert ("setup" in result.stdout) == (not selected or not failure)
