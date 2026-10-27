"""Exercise both shipped hook loaders with structured azd metadata."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("hook", ["preDeploy", "postProvision"])
@pytest.mark.parametrize("invalid", [None, {}, [], {"BAD-KEY": "value"}, {"KEY": 1}, {"KEY": "\0"}])
def test_deploy_environment_roundtrip_and_fail_closed(tmp_path, shell, hook, invalid):
    values = {
        "HOSTED_AGENT_DEPLOYMENT": json.dumps({"foundry": {"projectEndpoint": "https://example.invalid/a?x=y"}}),
        "AGENTLZ_COMPONENT_IDENTITIES": json.dumps({"ui": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}),
        "QUOTED": 'a "quote", backslash \\ and = sign',
        "MULTILINE": "first\nsecond\n",
        "EMPTY": "",
        "LITERAL": "$(never-execute); $HOME",
    }
    payload = values if invalid is None else invalid
    dotenv = "\n".join(f"{key}={json.dumps(value)}" for key, value in payload.items()) if isinstance(payload, dict) else json.dumps(payload)
    environment = {
        **os.environ, "FAKE_VALUES": json.dumps(payload), "FAKE_DOTENV": dotenv,
        "REAL_PYTHON": subprocess.sys.executable,
    }
    if shell == "pwsh":
        source = (ROOT / "scripts" / f"{hook}.ps1").read_text(encoding="utf-8-sig")
        if hook == "preDeploy":
            snippet = source[source.index("function Get-AzdEnv"):source.index("function ResourceGroup-Exists")]
            result_expression = "Get-AzdEnv '.' | ConvertTo-Json -Compress\n"
        else:
            snippet = source[source.index("$azdValues ="):source.index("# Private deployment-host prerequisite")]
            result_expression = (
                "@{"
                + "; ".join(f"'{key}' = [Environment]::GetEnvironmentVariable('{key}')" for key in values)
                + "} | ConvertTo-Json -Compress\n"
            )
        script = tmp_path / "load.ps1"
        script.write_text(
            "function azd { $global:LASTEXITCODE = 0; "
            "if ($args -contains 'json') { return $env:FAKE_VALUES }; return ($env:FAKE_DOTENV -split \"`n\") }\n"
            + snippet + "\n" + result_expression, encoding="utf-8",
        )
        command = [shutil.which("pwsh"), "-NoProfile", "-File", str(script)]
    else:
        source = (ROOT / "scripts" / f"{hook}.sh").read_text(encoding="utf-8")
        if hook == "preDeploy":
            snippet = source[source.index('azd_values="$(cd'):source.index("# ---------- Global env & RG")]
        else:
            snippet = source[source.index('azd_values="$('):source.index("is_truthy()")]
        script = tmp_path / "load.sh"
        script.write_text(
            'repo_root=.\nred() { printf "%s\\n" "$*" >&2; }\n'
            'azd() { if [[ "$*" == *"--output json"* ]]; then printf "%s" "$FAKE_VALUES"; '
            'else printf "%s" "$FAKE_DOTENV"; fi; }\n'
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
