"""Exercise both shipped hook loaders with structured azd metadata."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("invalid", [None, {}, [], {"BAD-KEY": "value"}, {"KEY": 1}, {"KEY": "\0"}])
def test_deploy_environment_roundtrip_and_fail_closed(tmp_path, shell, invalid):
    values = {
        "HOSTED_AGENT_DEPLOYMENT": json.dumps({"foundry": {"projectEndpoint": "https://example.invalid/a?x=y"}}),
        "QUOTED": 'a "quote", backslash \\ and = sign',
        "MULTILINE": "first\nsecond\n",
        "EMPTY": "",
        "LITERAL": "$(never-execute); $HOME",
    }
    payload = values if invalid is None else invalid
    environment = {**os.environ, "FAKE_VALUES": json.dumps(payload), "REAL_PYTHON": subprocess.sys.executable}
    if shell == "pwsh":
        source = (ROOT / "scripts" / "preDeploy.ps1").read_text(encoding="utf-8-sig")
        snippet = source[source.index("function Get-AzdEnv"):source.index("function ResourceGroup-Exists")]
        script = tmp_path / "load.ps1"
        script.write_text(
            "function azd { $global:LASTEXITCODE = 0; return $env:FAKE_VALUES }\n"
            + snippet + "\nGet-AzdEnv '.' | ConvertTo-Json -Compress\n", encoding="utf-8",
        )
        command = [shutil.which("pwsh"), "-NoProfile", "-File", str(script)]
    else:
        source = (ROOT / "scripts" / "preDeploy.sh").read_text(encoding="utf-8")
        snippet = source[source.index('azd_values="$(cd'):source.index("# ---------- Global env & RG")]
        script = tmp_path / "load.sh"
        script.write_text(
            'repo_root=.\nred() { printf "%s\\n" "$*" >&2; }\n'
            'azd() { printf "%s" "$FAKE_VALUES"; }\n'
            + snippet
            + '\n"$REAL_PYTHON" -c "import json, os; print(json.dumps({k: os.environ[k] for k in '
            + repr(list(values)) + '}))"\n', encoding="utf-8", newline="\n",
        )
        command = [shutil.which("bash"), str(script)]
    result = subprocess.run(command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30)
    if invalid is None:
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout) == values
    else:
        assert result.returncode != 0, result.stdout
        assert "Invalid azd environment" in result.stderr or "nonempty object" in result.stderr
        assert "never-execute" not in result.stderr
