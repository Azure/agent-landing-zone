"""Execute the real shared native publication/preparation blocks in both shells."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("host", ["hosted", "container_apps"])
@pytest.mark.parametrize("mode", ["conversational", "workflow", "both"])
@pytest.mark.parametrize("failure", ["none", "deploy", "publish"])
def test_native_application_lifecycle_uses_one_path_and_fails_closed(tmp_path, shell, host, mode, failure):
    suffix = "ps1" if shell == "pwsh" else "sh"
    source = (ROOT / "scripts" / f"preDeploy.{suffix}").read_text(encoding="utf-8-sig")
    block = source[source.index("# BEGIN native application lifecycle"):source.index("# END native application lifecycle")]
    environment = {**os.environ, "FAILURE": failure, "ORCHESTRATION_HOST": host, "APPLICATION_MODE": mode}
    if shell == "pwsh":
        script = """
$nativeMode = $true; $repoRoot = '.'
$globalEnv = [pscustomobject]@{}
$script:calls = @()
function Invoke-PythonModule {
    param($ModuleName, $Arguments)
    $script:calls += "$ModuleName $($Arguments -join ' ')"
    $global:LASTEXITCODE = 0
    if (($env:FAILURE -eq 'deploy' -and $ModuleName -eq 'config.deployment.native_deploy') -or
        ($env:FAILURE -eq 'publish' -and $ModuleName -eq 'config.deployment.appconfig')) { $global:LASTEXITCODE = 1 }
}
function Get-AzdEnv { param($projectPath) return [pscustomobject]@{ ORCHESTRATION_HOST = $env:ORCHESTRATION_HOST; APPLICATION_MODE = $env:APPLICATION_MODE } }
""" + block + "\n$script:calls | ConvertTo-Json -Compress\n"
        command = [shutil.which(shell), "-NoProfile", "-File"]
    else:
        script = """
set -uo pipefail
native_mode=true; repo_root=.
red() { printf '%s\\n' "$*" >&2; }
python3() {
  printf '%s\\n' "$*" >> "$CALLS_FILE"
  [ "$FAILURE" != deploy ] || [ "$*" != '-m config.deployment.native_deploy --deploy' ] || return 1
  [ "$FAILURE" != publish ] || [ "$*" != '-m config.deployment.appconfig --require-hosted-endpoint' ] || return 1
}
""" + block
        environment["CALLS_FILE"] = str(tmp_path / "calls.txt")
        command = [shutil.which(shell)]
    path = tmp_path / f"hook.{suffix}"
    path.write_text(script, encoding="utf-8", newline="\n")
    result = subprocess.run([*command, str(path)], env=environment, cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    if failure == "none":
        assert result.returncode == 0, result.stdout + result.stderr
        calls = json.loads(result.stdout) if shell == "pwsh" else (tmp_path / "calls.txt").read_text().splitlines()
        expected = ["config.deployment.native_deploy --deploy", "config.deployment.appconfig --require-hosted-endpoint"]
        assert [call.removeprefix("-m ") for call in calls] == expected
    else:
        assert result.returncode != 0, result.stdout
        assert "components processed" not in result.stdout
