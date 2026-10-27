"""Execute both shipped lifecycle-hook egress boundaries without Azure."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("hook", ["preProvision", "postProvision", "preDeploy"])
@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("failure", [False, True])
def test_egress_hook_invocation_and_failure_propagation(tmp_path, hook, shell, failure):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(f"{shell} is unavailable")
    suffix = "ps1" if shell == "pwsh" else "sh"
    source = (ROOT / "scripts" / f"{hook}.{suffix}").read_text(encoding="utf-8-sig")
    snippet = source.split("# BEGIN component runtime egress\n", 1)[1].split(
        "# END component runtime egress", 1,
    )[0]
    if shell == "pwsh":
        prefix = r'''
$ErrorActionPreference = 'Stop'
$env:AGENTLZ_REPO_ROOT = $env:FAKE_ROOT
function python {
    Add-Content (Join-Path $env:FAKE_ROOT 'trace') ($args -join ' ')
    $global:LASTEXITCODE = [int]$env:FAKE_EXIT
}
function Invoke-PythonModule {
    param([string]$ModuleName, [string[]]$Arguments)
    python $ModuleName @Arguments
}
'''
        command = [executable, "-NoProfile", "-NonInteractive", "-File", str(tmp_path / "hook.ps1")]
    else:
        prefix = r'''
if command -v cygpath >/dev/null; then FAKE_ROOT="$(cygpath -u "$FAKE_ROOT")"; fi
PROJECT_ROOT="$FAKE_ROOT"
repo_root="$FAKE_ROOT"
PYTHON_CMD=python3
red() { printf '%s\n' "$*"; }
python3() { printf '%s\n' "$*" >> "$FAKE_ROOT/trace"; return "$FAKE_EXIT"; }
'''
        command = [executable, str(tmp_path / "hook.sh")]
    script = tmp_path / f"hook.{suffix}"
    script.write_text(prefix + snippet + "\n", encoding="utf-8", newline="\n")
    result = subprocess.run(
        command, env={**os.environ, "FAKE_ROOT": str(tmp_path), "FAKE_EXIT": "26" if failure else "0"},
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    trace = (tmp_path / "trace").read_text(encoding="utf-8-sig")
    assert "config.deployment.egress" in trace
    assert ("--plan --save" if hook == "preProvision" else "--apply") in trace
    assert (result.returncode != 0) is failure, result.stdout + result.stderr


def test_hook_order_keeps_validation_composition_private_guards_and_deferral():
    for suffix in ("ps1", "sh"):
        preprovision = (ROOT / "scripts" / f"preProvision.{suffix}").read_text(encoding="utf-8-sig")
        assert preprovision.index("config.appdefinition") < preprovision.index("config.deployment.composition")
        assert preprovision.index("config.deployment.composition") < preprovision.index("# BEGIN component runtime egress")
        for hook in ("postProvision", "preDeploy"):
            source = (ROOT / "scripts" / f"{hook}.{suffix}").read_text(encoding="utf-8-sig")
            assert source.index("config.deployment.resource_groups") < source.index("# BEGIN component runtime egress")
            assert source.index("config.deployment.private_network") < source.index("# BEGIN component runtime egress")
