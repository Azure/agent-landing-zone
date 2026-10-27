"""Execute the shipped automatic preparation blocks in both hook variants."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "sha256:" + "a" * 64


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("failure", ["none", "foundation", "build", "json", "empty", "wrong-keys", "nul"])
def test_automatic_preparation_propagates_environment_and_stops_on_failure(tmp_path, shell, failure):
    values = {
        "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
        "HOSTED_AGENT_IMAGE_SOURCE_COMMIT": "b" * 40,
        "HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256": "c" * 64,
        "HOSTED_AGENT_DEPLOYMENT": json.dumps({"enabled": True, "agent": {"imageVersion": DIGEST}}),
        "DEPLOY_HOSTED_AGENT": "true",
    }
    invalid = {
        "json": "{",
        "empty": "{}",
        "wrong-keys": json.dumps({**values, "UNEXPECTED": "value"}),
        "nul": json.dumps({**values, "HOSTED_AGENT_IMAGE_SOURCE_COMMIT": "\0"}),
    }
    environment = {
        **os.environ,
        "PREPARED_VALUES": invalid.get(failure, json.dumps(values)),
        "PREPARED": "false" if failure == "foundation" else "true",
        "PREPARE_EXIT": "1" if failure == "build" else "0",
    }
    extension = "ps1" if shell == "pwsh" else "sh"
    source = (ROOT / "scripts" / f"preDeploy.{extension}").read_text(encoding="utf-8-sig")
    start = "# BEGIN automatic hosted image preparation"
    end = "# END automatic hosted image preparation"
    block = source[source.index(start):source.index(end)]
    if shell == "pwsh":
        script = tmp_path / "prepare.ps1"
        script.write_text(
            "$manifestPath = 'manifest.json'\n"
            "$globalEnv = [pscustomobject]@{ HOSTED_AGENT_PREPARED = $env:PREPARED; DEPLOY_HOSTED_AGENT = 'false' }\n"
            "function Invoke-PythonModule { param($ModuleName, $Arguments)\n"
            "if ($ModuleName -ne 'config.deployment.hosted_prepare' -or $Arguments -notcontains '--for-deploy') { exit 9 }\n"
            "$global:LASTEXITCODE = [int]$env:PREPARE_EXIT; return $env:PREPARED_VALUES }\n"
            + block + "\n"
            "$globalEnv | ConvertTo-Json -Compress\n"
            "if ($env:HOSTED_AGENT_IMAGE_VERSION -ne $globalEnv.HOSTED_AGENT_IMAGE_VERSION -or "
            "$env:HOSTED_AGENT_DEPLOYMENT -ne $globalEnv.HOSTED_AGENT_DEPLOYMENT) { exit 8 }\n",
            encoding="utf-8",
        )
        command = [shutil.which("pwsh"), "-NoProfile", "-File", str(script)]
    else:
        script = tmp_path / "prepare.sh"
        script.write_text(
            'set -uo pipefail\nrepo_root=.\nmanifest_path=manifest.json\nhosted_prepared="$PREPARED"\n'
            'red() { printf "%s\\n" "$*" >&2; }\n'
            'python3() { [ "$*" = "-m config.deployment.hosted_prepare --manifest manifest.json --for-deploy" ] || return 9;\n'
            'printf "%s" "$PREPARED_VALUES"; return "$PREPARE_EXIT"; }\n'
            + block + '\n'
            '[ "$hosted_agent_digest" = "$HOSTED_AGENT_IMAGE_VERSION" ] || exit 8\n'
            '[ "$deploy_hosted" = true ] || exit 8\n'
            'jq -n --arg digest "$HOSTED_AGENT_IMAGE_VERSION" --arg handoff "$HOSTED_AGENT_DEPLOYMENT" '
            '\'{"HOSTED_AGENT_IMAGE_VERSION": $digest, "HOSTED_AGENT_DEPLOYMENT": $handoff}\'\n',
            encoding="utf-8", newline="\n",
        )
        command = [shutil.which("bash"), str(script)]
    result = subprocess.run(command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30)
    if failure == "none":
        assert result.returncode == 0, result.stdout + result.stderr
        loaded = json.loads(result.stdout)
        for key in ("HOSTED_AGENT_IMAGE_VERSION", "HOSTED_AGENT_DEPLOYMENT"):
            assert loaded[key] == values[key]
    else:
        assert result.returncode != 0, result.stdout
        assert '"HOSTED_AGENT_IMAGE_VERSION":' not in result.stdout
