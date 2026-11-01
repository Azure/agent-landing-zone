"""Both real Hosted bootstrap hooks, with offline CLIs.

Native root publication is covered by test_hosted_deploy_hooks. The retired
root stateless deploy/smoke/cutover section is not an executable product path.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.test_hosted_smoke import completion, sse


ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
BASH = shutil.which("bash")

# Execute the hook's actual Python entrypoint, mocking only subprocess at the
# Azure/azd boundary. No network, SDK, inference or real deployment is possible.
DRIVER = r'''
import json, os, subprocess, sys
sys.path.insert(0, os.environ["REAL_REPO"])
if sys.argv[1:] == ["-m", "config.deployment.hosted", "--validate-smoke"]:
    from config.deployment.hosted import main
    raise SystemExit(main(["--validate-smoke"]))
if sys.argv[1] == "-c" and sys.argv[3:] == ["--validate-smoke"]:
    code = sys.argv[2]
    sys.argv = ["-c", "--validate-smoke"]
    exec(code)
    raise AssertionError("Smoke CLI must exit")
from tests.test_hosted_access import AzureFixture, ENV, SECRET
from config.deployment import hosted_access as access

def event(value):
    with open(os.environ["FAKE_TRACE"], "a", encoding="utf-8") as stream:
        stream.write(value + "\n")

fixture = AzureFixture()
if os.environ.get("FAKE_FAIL") == "write":
    fixture.fail_role = access.Role.MODEL
if os.environ.get("FAKE_FAIL") == "identity":
    fixture.live["instance_identity"] = {}
if os.environ.get("FAKE_FAIL") == "conditional":
    fixture.assignments = [fixture.assignment(SECRET, access.Role.SECRET, condition="@operator-condition")]
env = dict(ENV, AZURE_ENV_NAME="offline-child", UNUSED='$(exit 98); "quoted"')
if os.environ.get("FAKE_CLASSIC") == "1":
    env = {"ORCHESTRATION_HOST": "container_apps", "AZURE_ENV_NAME": "offline-child"}

def run(command, **kwargs):
    if command[1:3] == ["env", "get-values"]:
        assert Path.cwd().name == "hosted-agent"
        assert command[command.index("--environment") + 1] == "offline-child"
        assert "--no-prompt" in command and "--output" in command
        event("env")
        return subprocess.CompletedProcess(command, 1 if os.environ.get("FAKE_FAIL") == "env" else 0, json.dumps(env), "PRIVATE-MARKER")
    assert command[-3:] == ["--output", "json", "--only-show-errors"]
    args = command[1:-3]
    if args[:3] == ["role", "assignment", "create"]:
        event("create:" + access.Role(args[args.index("--role") + 1]).name)
    try:
        return subprocess.CompletedProcess(command, 0, json.dumps(fixture(args)), "")
    except access.AzureCommandError:
        return subprocess.CompletedProcess(command, 1, "", "PRIVATE-MARKER")

from pathlib import Path
assert sys.argv[1] == "-c"
assert sys.argv[3:] == ["--azd-env", "--apply"]
assert Path(os.environ["AGENTLZ_REPO_ROOT"]).joinpath("hosted-agent").resolve() == Path.cwd().resolve()
subprocess.run = run
# Avoid runpy's pre-import warning; imports above are fixture setup only.
del sys.modules["config.deployment.hosted_access"]
code = sys.argv[2]
sys.argv = ["-c", *sys.argv[3:]]
exec(code)
'''

PS_PREFIX = r'''
$ErrorActionPreference = 'Stop'
$repoRoot = $env:FAKE_ROOT
$env:AGENTLZ_REPO_ROOT = $repoRoot
$hostedProject = Join-Path $repoRoot 'hosted-agent'
$hostedDigest = 'sha256:offline'
$globalEnv = [pscustomobject]@{
    AZURE_ENV_NAME = 'offline-child'
    AZURE_AI_PROJECT_ENDPOINT = 'https://test-foundry.services.ai.azure.com/api/projects/test-project'
    AZURE_AI_PROJECT_RESOURCE_ID = 'offline-fixture-only'
}
function python {
    $input | & $env:REAL_PYTHON (Join-Path $env:FAKE_ROOT 'driver.py') @args
}
function Get-AzdEnv { return @{} }
function azd {
    if ($args[0] -eq 'env') { $global:LASTEXITCODE = 0; return }
    if ($args[0] -eq 'deploy') {
        Add-Content -LiteralPath $env:FAKE_TRACE -Value 'deploy'
        & (Join-Path $env:FAKE_ROOT 'scripts/bootstrapHostedAccess.ps1')
        $global:LASTEXITCODE = $LASTEXITCODE
        return
    }
    if (($args[0..2] -join ' ') -eq 'ai agent invoke') {
        if (($args -join ' ') -notmatch '--protocol invocations --new-session') { throw 'Wrong smoke protocol' }
        $payloadIndex = [Array]::IndexOf($args, '--input-file') + 1
        $payload = Get-Content -LiteralPath $args[$payloadIndex] -Raw | ConvertFrom-Json | ConvertTo-Json -Depth 5 -Compress
        if ($payload -ne '{"messages":[{"role":"user","content":"Hello!"}]}') { throw 'Smoke must be a stateless greeting, not a retrieval/marker request' }
        Add-Content -LiteralPath $env:FAKE_TRACE -Value 'smoke'
        if ($env:FAKE_FAIL -eq 'smoke') {
            Write-Output '{"type":"error"}'
            $global:LASTEXITCODE = 9
        } else {
            Get-Content -LiteralPath (Join-Path $env:FAKE_ROOT 'response.txt') -Raw
            $global:LASTEXITCODE = 0
        }
        return
    }
    throw 'Unexpected azd operation'
}
'''

SH_PREFIX = r'''
set -eu
export FAKE_ROOT="$PWD" FAKE_TRACE="$PWD/trace.txt"
export PATH="$PWD/.fake-bin:$PATH"
repo_root="$PWD"
hosted_project="$PWD/hosted-agent"
environment_name=offline-child
hosted_agent_digest=sha256:offline
project_endpoint=https://test-foundry.services.ai.azure.com/api/projects/test-project
project_resource_id=offline-fixture-only
red() { printf '%s\n' "$*"; }
azd() {
    case "$1" in
        env) return 0 ;;
        deploy)
            echo deploy >> "$FAKE_TRACE"
            sh "$FAKE_ROOT/scripts/bootstrapHostedAccess.sh"
            return $? ;;
        ai)
            case "$*" in
                *"--protocol invocations --new-session"*) ;;
                *) return 96 ;;
            esac
            local previous="" payload_file="" argument
            for argument in "$@"; do
                if [ "$previous" = "--input-file" ]; then payload_file="$argument"; fi
                previous="$argument"
            done
            [ "$(cat "$payload_file")" = '{"messages":[{"role":"user","content":"Hello!"}]}' ] || return 96
            echo smoke >> "$FAKE_TRACE"
            if [ "${FAKE_FAIL:-}" = smoke ]; then
                printf '%s\n' '{"type":"error"}'
                return 9
            fi
            cat "$FAKE_ROOT/response.txt"
            return 0 ;;
        *) return 97 ;;
    esac
}
'''


class HostedAccessHookTests(unittest.TestCase):
    def run_hook(self, shell, *, fail="", container_apps=False):
        suffix = "ps1" if shell == "powershell" else "sh"
        with tempfile.TemporaryDirectory(prefix="hosted access offline ") as directory:
            temp = Path(directory)
            (temp / "scripts").mkdir()
            (temp / "hosted-agent").mkdir()
            shutil.copyfile(ROOT / "scripts" / f"bootstrapHostedAccess.{suffix}", temp / "scripts" / f"bootstrapHostedAccess.{suffix}")
            (temp / "driver.py").write_text(DRIVER, encoding="utf-8")
            response = sse(completion())
            if fail == "errorframe":
                response += sse({"type": "error", "message": "PRIVATE-MARKER"})
            elif fail == "missingcompletion":
                response = sse({"type": "response.output_text.delta", "delta": "Agent Landing Zone hosted smoke OK."})
            elif fail == "emptycompletion":
                response = sse(completion(""))
            (temp / "response.txt").write_text(response, encoding="utf-8")
            env = dict(os.environ, FAKE_ROOT=str(temp), FAKE_TRACE=str(temp / "trace.txt"),
                       REAL_REPO=str(ROOT), REAL_PYTHON=sys.executable, FAKE_FAIL=fail,
                       FAKE_CLASSIC="1" if container_apps else "0", AZURE_ENV_NAME="offline-child")
            if shell == "powershell":
                action = "& (Join-Path $env:FAKE_ROOT 'scripts/bootstrapHostedAccess.ps1')\nexit $LASTEXITCODE\n"
                command = [PWSH, "-NoProfile", "-NonInteractive", "-Command", PS_PREFIX + action]
            else:
                fake_bin = temp / ".fake-bin"
                fake_bin.mkdir()
                # The binary is explicit; no real az/azd can be invoked.
                shim = fake_bin / "python3"
                shim.write_text('#!/usr/bin/env bash\nexec "$REAL_PYTHON" "$FAKE_ROOT/driver.py" "$@"\n', encoding="utf-8", newline="\n")
                shim.chmod(0o755)
                action = 'sh scripts/bootstrapHostedAccess.sh\n'
                command = [BASH, "-c", SH_PREFIX + action]
            result = subprocess.run(command, cwd=temp, env=env, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=40, check=False)
            trace = temp / "trace.txt"
            events = trace.read_text(encoding="utf-8-sig").splitlines() if trace.exists() else []
            return result, events

    def cases(self, shell):
        for root in (False,):
            for fail in ("", "env", "identity", "write", "conditional"):
                with self.subTest(root=root, fail=fail):
                    result, events = self.run_hook(shell, fail=fail)
                    output = result.stdout + result.stderr
                    self.assertNotIn("PRIVATE-MARKER", output)
                    self.assertEqual(1, events.count("env"), output)
                    if fail:
                        self.assertNotEqual(0, result.returncode, output)
                        self.assertNotIn("smoke", events, output)
                        self.assertNotIn("cutover-boundary", events, output)
                        self.assertNotIn("NOT data-plane readiness", output)
                        if fail == "write":
                            self.assertIn("1/3 grants verified", output)
                        else:
                            self.assertFalse(any(e.startswith("create:") for e in events))
                    else:
                        self.assertEqual(0, result.returncode, output)
                        self.assertEqual(["create:CONFIG", "create:MODEL", "create:SECRET"], [e for e in events if e.startswith("create:")])
                        self.assertIn("NOT data-plane readiness", output)
                        if root:
                            self.assertEqual(["deploy", "env", "create:CONFIG", "create:MODEL", "create:SECRET", "smoke", "cutover-boundary"], events)
        result, events = self.run_hook(shell, container_apps=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(["env"], events)

    @unittest.skipUnless(PWSH, "PowerShell 7 is not installed")
    def test_powershell_direct_and_root_hook(self):
        self.cases("powershell")

    @unittest.skipUnless(BASH, "bash is not installed")
    def test_posix_direct_and_root_hook(self):
        self.cases("bash")

    def recovery(self, shell):
        failed, events = self.run_hook(shell, fail="identity")
        self.assertNotEqual(0, failed.returncode, failed.stdout + failed.stderr)
        self.assertFalse(any(event.startswith("create:") for event in events))
        recovered, events = self.run_hook(shell)
        self.assertEqual(0, recovered.returncode, recovered.stdout + recovered.stderr)
        self.assertEqual(["create:CONFIG", "create:MODEL", "create:SECRET"], events[1:])

    @unittest.skipUnless(PWSH, "PowerShell 7 is not installed")
    def test_powershell_identity_failure_blocks_writes_and_rerun_recovers(self):
        self.recovery("powershell")

    @unittest.skipUnless(BASH, "bash is not installed")
    def test_posix_identity_failure_blocks_writes_and_rerun_recovers(self):
        self.recovery("bash")

    def test_single_service_hook_no_duplicate_root_bootstrap(self):
        content = (ROOT / "hosted-agent/azure.yaml").read_text(encoding="utf-8")
        self.assertEqual(1, content.count("      postdeploy:"))
        self.assertIn("          run: hooks/postdeploy.ps1", content)
        self.assertIn("          run: hooks/postdeploy.sh", content)
        # azd rejects hook paths that escape the service project root.
        self.assertNotIn("run: ../", content)
        for suffix in ("ps1", "sh"):
            wrapper = (ROOT / "hosted-agent" / "hooks" / f"postdeploy.{suffix}").read_text(encoding="utf-8")
            self.assertIn(f"../../scripts/bootstrapHostedAccess.{suffix}", wrapper)
        for suffix in ("ps1", "sh"):
            root = (ROOT / "scripts" / f"preDeploy.{suffix}").read_text(encoding="utf-8-sig")
            self.assertNotIn("hosted_access", root)
            self.assertNotIn("bootstrapHostedAccess", root)
            self.assertIn("config.deployment.native_deploy", root)
            self.assertIn("--deploy", root)
            self.assertNotIn("azd deploy orchestrator-agent", root)
            self.assertNotIn("HOSTED_CUTOVER_COMPLETE", root)


if __name__ == "__main__":
    unittest.main()
