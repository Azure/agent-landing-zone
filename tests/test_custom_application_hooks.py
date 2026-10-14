"""Run custom deployment sections with offline CLIs and shipped sample layout."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.test_hosted_smoke import completion

ROOT = Path(__file__).resolve().parents[1]


class CustomApplicationHookTests(unittest.TestCase):
    def check_directory_selection(self, shell: str) -> None:
        suffix = "ps1" if shell == "pwsh" else "sh"
        for hook in ("preProvision", "preDeploy"):
            with self.subTest(hook=hook), tempfile.TemporaryDirectory(prefix="app selection ") as directory:
                root = Path(directory)
                folder = root / "custom app"
                folder.mkdir()
                definition = folder / "app-definition.json"
                definition.write_text("{}", encoding="utf-8")
                source = (ROOT / "scripts" / f"{hook}.{suffix}").read_text(encoding="utf-8-sig")
                env = dict(os.environ, AGENTLZ_APP_DEFINITION=str(folder), FAKE_ROOT=str(root))
                if shell == "pwsh":
                    start = source.index("$appDefinitionPath = if")
                    marker = 'Write-Host "Validating and binding' if hook == "preProvision" else "$boundAppId ="
                    end = source.index(marker, start)
                    prefix = "$projectRoot = $env:FAKE_ROOT; $repoRoot = $projectRoot; $globalEnv = @{}\n"
                    script = root / "select.ps1"
                    script.write_text(prefix + source[start:end] + "\nWrite-Output $appDefinitionPath\n",
                                      encoding="utf-8")
                    command = [shutil.which(shell), "-NoProfile", "-File", str(script)]
                else:
                    variable = "APP_DEFINITION_PATH" if hook == "preProvision" else "app_definition_path"
                    start = source.index(f'{variable}="${{AGENTLZ_APP_DEFINITION')
                    marker = 'echo "${CYAN}Validating and binding' if hook == "preProvision" else "command -v python3"
                    end = source.index(marker, start)
                    prefix = r"""
if command -v cygpath >/dev/null; then
    AGENTLZ_APP_DEFINITION="$(cygpath -u "$AGENTLZ_APP_DEFINITION")"
    FAKE_ROOT="$(cygpath -u "$FAKE_ROOT")"
fi
PROJECT_ROOT="$FAKE_ROOT"
repo_root="$FAKE_ROOT"
red() { printf '%s\n' "$*"; }
"""
                    script = root / "select.sh"
                    script.write_text(prefix + source[start:end] + f'\nprintf "%s\\n" "${variable}"\n',
                                      encoding="utf-8", newline="\n")
                    command = [shutil.which(shell), str(script)]
                result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertTrue(result.stdout.strip().endswith("app-definition.json"), result.stdout)
                definition.unlink()
                result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=20)
                self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)

    def run_custom(self, shell: str, *, mismatch: bool = False, hosted: bool = False,
                   smoke_failure: bool = False) -> tuple[int, list[str], str]:
        suffix = "ps1" if shell == "pwsh" else "sh"
        source = (ROOT / "scripts" / f"preDeploy.{suffix}").read_text(encoding="utf-8-sig")
        with tempfile.TemporaryDirectory(prefix="custom app offline ") as directory:
            root = Path(directory)
            app = root / "application"
            shutil.copytree(ROOT / "samples" / "custom-app" / ("hosted" if hosted else "containerapp"), app)
            azure = root / ".azure"
            azure.mkdir()
            (azure / "config.json").write_text("{}", encoding="utf-8")
            definition = json.loads((app / "app-definition.json").read_text(encoding="utf-8"))
            component = definition["components"][0]
            component["source"] = {"commit": "1" * 40}
            (app / "app-definition.json").write_text(json.dumps(definition), encoding="utf-8")
            response = completion()["response"]
            if smoke_failure:
                response["status"] = "failed"
            (root / "response").write_text(json.dumps(response), encoding="utf-8")
            (root / "custom-deploy.py").write_text(
                "import os, sys, subprocess\n"
                "from pathlib import Path\n"
                "from unittest.mock import patch\n"
                "from types import SimpleNamespace\n"
                "from config.deployment import custom_application\n"
                "def run(args, **kwargs):\n"
                "    if args[0] == 'git':\n"
                "        return subprocess.CompletedProcess(args, 0, stdout=os.environ['FAKE_COMMIT'])\n"
                "    folder = Path(kwargs['cwd'])\n"
                "    assert (folder / 'azure.yaml').is_file()\n"
                "    assert (folder / '.azure' / 'config.json').is_file()\n"
                "    with (Path(os.environ['FAKE_ROOT']) / 'trace').open('a', encoding='utf-8') as f:\n"
                "        f.write(' '.join(args[1:]) + '\\n')\n"
                "    return subprocess.CompletedProcess(args, 0)\n"
                "with patch.object(custom_application.subprocess, 'run', side_effect=run), \\\n"
                "     patch.object(custom_application, 'discover_instance', return_value=SimpleNamespace(principal_id='verified', agent_version='1')), \\\n"
                "     patch.object(custom_application, 'assign_hosted_roles'):\n"
                "    sys.exit(custom_application.main(sys.argv[1:]))\n", encoding="utf-8")
            env = dict(os.environ, FAKE_ROOT=str(root), FAKE_APP=str(app),
                       FAKE_COMMIT=("2" if mismatch else "1") * 40, REAL_PYTHON=sys.executable,
                       AGENTLZ_REPO_ROOT=str(ROOT), REAL_REPO=str(ROOT), PYTHONPATH=str(ROOT))
            if shell == "pwsh":
                start = source.index("foreach ($dc in $definitionComponents)", source.index("# Components"))
                end = source.index("\nif ($hadErrors)", start)
                prefix = r"""
$ErrorActionPreference = 'Continue'
$appDefinitionDir = $env:FAKE_APP
$appDefinitionPath = Join-Path $appDefinitionDir 'app-definition.json'
$dotAzure = Join-Path $env:FAKE_ROOT '.azure'
$definitionComponents = @((Get-Content (Join-Path $appDefinitionDir 'app-definition.json') -Raw | ConvertFrom-Json).components)
$globalEnv = [pscustomobject]@{ AZURE_ENV_NAME = 'offline' }
$hadErrors = $false
function Get-ManifestComponentForDefinition { return $null }
function git { $global:LASTEXITCODE = 0; return $env:FAKE_COMMIT }
function python {
    if ($args.Count -ge 2 -and "$($args[1])".Contains('config.deployment.custom_application')) {
        & $env:REAL_PYTHON (Join-Path $env:FAKE_ROOT 'custom-deploy.py') @($args[2..($args.Count - 1)])
    } else { $input | & $env:REAL_PYTHON @args }
}
function azd {
    if (-not (Test-Path 'azure.yaml') -or -not (Test-Path 'src')) { throw 'Wrong project folder' }
    if (-not (Test-Path '.azure/config.json')) { throw 'Missing environment' }
    Add-Content (Join-Path $env:FAKE_ROOT 'trace') ($args -join ' ')
    if ($args[0] -eq 'ai') { Get-Content (Join-Path $env:FAKE_ROOT 'response') -Raw }
    $global:LASTEXITCODE = 0
}
"""
                script = root / "run.ps1"
                script.write_text(prefix + source[start:end] + "\nif ($hadErrors) { exit 1 }\n", encoding="utf-8")
                command = [shutil.which(shell), "-NoProfile", "-NonInteractive", "-File", str(script)]
            else:
                fake_bin = root / "bin"
                fake_bin.mkdir()
                (root / "jq.py").write_text(
                    "import json, sys\n"
                    "query = sys.argv[2]\n"
                    "doc = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else json.load(sys.stdin)\n"
                    "if query == '.components[]':\n"
                    "    for item in doc['components']: print(json.dumps(item))\n"
                    "else:\n"
                    "    value = doc\n"
                    "    for key in query.split(' // ')[0].strip('.').split('.'): value = value.get(key, {})\n"
                    "    print(value if value != {} else '')\n", encoding="utf-8")
                shim = fake_bin / "jq"
                shim.write_text('#!/usr/bin/env bash\nexec "$REAL_PYTHON" "$FAKE_ROOT/jq.py" "$@"\n',
                                encoding="utf-8", newline="\n")
                shim.chmod(0o755)
                python_shim = fake_bin / "python3"
                python_shim.write_text(
                    '#!/usr/bin/env bash\n'
                    'if [[ "$*" == *config.deployment.custom_application* ]]; then\n'
                    '  shift 2\n'
                    '  exec "$REAL_PYTHON" "$FAKE_ROOT/custom-deploy.py" "$@"\n'
                    'fi\nexec "$REAL_PYTHON" "$@"\n',
                                       encoding="utf-8", newline="\n")
                python_shim.chmod(0o755)
                start = source.index('while IFS= read -r dcomp; do', source.index("# Components"))
                end = source.index('\nif [ "$had_errors"', start)
                prefix = r"""
set -eu
if command -v cygpath >/dev/null; then
    FAKE_ROOT="$(cygpath -u "$FAKE_ROOT")"
    FAKE_APP="$(cygpath -u "$FAKE_APP")"
    REAL_REPO="$(cygpath -u "$REAL_REPO")"
fi
export PATH="$FAKE_ROOT/bin:$PATH" FAKE_ROOT
app_definition_dir="$FAKE_APP"
app_definition_path="$FAKE_APP/app-definition.json"
dot_azure="$FAKE_ROOT/.azure"
AZURE_ENV_NAME=offline
AZURE_AI_PROJECT_ENDPOINT=https://example.invalid/api/projects/offline
AZURE_AI_PROJECT_RESOURCE_ID=offline
repo_root="$REAL_REPO"
had_errors=0
red() { printf '%s\n' "$*"; }
green() { :; }
cyan() { :; }
manifest_component_for() { :; }
git() { printf '%s\n' "$FAKE_COMMIT"; }
copy_dot_azure() { cp -R "$1" "$2/"; }
azd() {
    [ "$PWD" = "$FAKE_APP" ] || return 91
    [ -f .azure/config.json ] || return 92
    printf '%s\n' "$*" >> "$FAKE_ROOT/trace"
    if [ "$1" = ai ]; then cat "$FAKE_ROOT/response"; fi
}
"""
                script = root / "run.sh"
                script.write_text(prefix + source[start:end] + '\nexit "$had_errors"\n', encoding="utf-8", newline="\n")
                command = [shutil.which(shell), str(script)]
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=30)
            trace = root / "trace"
            events = trace.read_text(encoding="utf-8-sig").splitlines() if trace.exists() else []
            return result.returncode, events, result.stdout + result.stderr

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_deploys_selected_service_from_definition_folder(self) -> None:
        self.check_directory_selection("pwsh")
        self.check_deploy("pwsh")

    @unittest.skipUnless(shutil.which("bash"), "Bash is not installed")
    def test_shell_deploys_selected_service_from_definition_folder(self) -> None:
        self.check_directory_selection("bash")
        self.check_deploy("bash")

    def check_deploy(self, shell: str) -> None:
        code, events, output = self.run_custom(shell)
        self.assertEqual(0, code, output)
        self.assertEqual(["deploy web --environment offline --no-prompt"], events)
        code, events, output = self.run_custom(shell, mismatch=True)
        self.assertNotEqual(0, code, output)
        self.assertEqual([], events)
        for failed in (False, True):
            code, events, output = self.run_custom(shell, hosted=True, smoke_failure=failed)
            if failed:
                self.assertNotEqual(0, code, output)
            else:
                self.assertEqual(0, code, output)
            self.assertIn("deploy agent --environment offline --no-prompt", events)
            smoke = next(event for event in events if event.startswith("ai agent invoke "))
            self.assertIn("ai agent invoke agent --protocol responses", smoke)
            self.assertIn("--output raw", smoke)


if __name__ == "__main__":
    unittest.main()
