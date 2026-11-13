"""Exercise both shipped hook loaders with structured azd metadata."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("mode", ["appConfig", "containerEnv", "none"])
def test_postprovision_dispatch_skips_unselected_foundry_and_apps(tmp_path, shell, mode):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(f"{shell} unavailable")
    suffix = "ps1" if shell == "pwsh" else "sh"
    source = (ROOT / "scripts" / f"postProvision.{suffix}").read_text(encoding="utf-8-sig")
    driver = tmp_path / "optional_setup.py"
    driver.write_text(
        "import importlib, os, sys\n"
        "from unittest.mock import patch\n"
        "sys.path.insert(0, sys.argv[2])\n"
        "if sys.argv[1] == 'config.governance.setup': sys.exit(0)\n"
        "module = importlib.import_module(sys.argv[1])\n"
        "settings = {'DEPLOY_AI_FOUNDRY': 'false', 'CONTAINER_APPS': [],\n"
        "            'APP_RUNTIME_CONFIGURATION_MODE': os.environ['TEST_RUNTIME_MODE']}\n"
        "credential_name = 'get_azure_credential' if sys.argv[1] == 'config.aifoundry.setup' else 'get_credentials'\n"
        "with patch.object(module, 'load_setup_settings', return_value=settings), "
        "patch.object(module, credential_name, side_effect=AssertionError('Unselected credential acquisition')) as credential:\n"
        "    module.main()\n"
        "    credential.assert_not_called()\n"
        "print('skipped:' + sys.argv[1])\n",
        encoding="utf-8",
    )
    if shell == "pwsh":
        start = source.index("foreach ($module in @(", source.index("# Selected services decide applicability"))
        block = source[start:source.index("# BEGIN selected Search setup", start)]
        prefix = (
            "function Invoke-PythonModule { param($ModuleName)\n"
            "& $env:REAL_PYTHON $env:SETUP_DRIVER $ModuleName $env:TEST_REPO_ROOT }\n"
        )
        command = [executable, "-NoProfile", "-File", str(tmp_path / "dispatch.ps1")]
        tail = "\nWrite-Output 'next-stage'\n"
    else:
        start = source.index("# 3) AI Foundry Setup")
        block = source[start:source.index("# 5) AI Search Setup", start)]
        prefix = 'python() { "$REAL_PYTHON" "$SETUP_DRIVER" "$2" "$TEST_REPO_ROOT"; }\n'
        command = [executable, str(tmp_path / "dispatch.sh")]
        tail = "\necho next-stage\n"
    Path(command[-1]).write_text(prefix + block + tail, encoding="utf-8")
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env={
        **os.environ, "REAL_PYTHON": subprocess.sys.executable, "SETUP_DRIVER": str(driver),
        "TEST_REPO_ROOT": str(ROOT), "TEST_RUNTIME_MODE": mode,
    }, timeout=60)
    assert result.returncode == 0, result.stderr
    assert [line for line in result.stdout.splitlines() if line.startswith("skipped:")] == [
        "skipped:config.aifoundry.setup", "skipped:config.containerapps.setup",
    ]
    assert "next-stage" in result.stdout


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("software,search,project,backend,expected", [
    ("false", "true", "true", "foundry_iq", []),
    ("true", "false", "true", "foundry_iq", []),
    ("true", "true", "false", "foundry_iq", ["config.search.setup"]),
    ("true", "true", "true", "ai_search", ["config.search.setup"]),
    ("true", "true", "true", "foundry_iq", ["config.search.setup", "config.aifoundry.toolbox"]),
])
@pytest.mark.parametrize("failure", ["", "config.search.setup", "config.aifoundry.toolbox"])
def test_search_setup_uses_typed_selection_and_propagates_selected_failures(
    tmp_path, shell, software, search, project, backend, expected, failure,
):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(f"{shell} unavailable")
    suffix = "ps1" if shell == "pwsh" else "sh"
    source = (ROOT / "scripts" / f"postProvision.{suffix}").read_text(encoding="utf-8-sig")
    block = source.split("# BEGIN selected Search setup\n", 1)[1].split(
        "# END selected Search setup", 1
    )[0]
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import os, sys, runpy, types\n"
        "settings = types.ModuleType('config.deployment.setup_settings')\n"
        "settings.load_setup_settings = lambda: dict(os.environ)\n"
        "sys.modules[settings.__name__] = settings\n"
        "def invoke(module, **kwargs):\n"
        "    print(module, flush=True)\n"
        "    if module == os.environ['FAILED_MODULE']: raise RuntimeError('Required setup failed')\n"
        "runpy.run_module = invoke\n"
        "assert sys.argv[1] == '-c'\n"
        "exec(sys.argv[2])\n", encoding="utf-8",
    )
    script = tmp_path / f"setup.{suffix}"
    if shell == "pwsh":
        prefix = "function python { & $env:REAL_PYTHON $env:SETUP_DRIVER @args }\n"
        command = [executable, "-NoProfile", "-File", str(script)]
        tail = "\nWrite-Output 'next-stage'\n"
    else:
        prefix = 'python() { "$REAL_PYTHON" "$SETUP_DRIVER" "$@"; }\n'
        command = [executable, str(script)]
        tail = "\necho next-stage\n"
    script.write_text(prefix + block + tail, encoding="utf-8")
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env={
        **os.environ, "REAL_PYTHON": subprocess.sys.executable, "SETUP_DRIVER": str(driver),
        "DEPLOY_SOFTWARE": software, "DEPLOY_SEARCH_SERVICE": search,
        "DEPLOY_AF_PROJECT": project, "RETRIEVAL_BACKEND": backend, "FAILED_MODULE": failure,
    })
    failed = failure in expected
    reached = expected[:expected.index(failure) + 1] if failed else expected
    assert [line for line in result.stdout.splitlines() if line.startswith("config.")] == reached
    assert (result.returncode != 0) == failed, result.stderr
    assert ("next-stage" in result.stdout) != failed


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("hook", ["preDeploy", "postProvision"])
@pytest.mark.parametrize("status", [0, 7])
@pytest.mark.parametrize("provider", ["bicep", "terraform"])
@pytest.mark.parametrize("mode", ["appConfig", "containerEnv", "none"])
def test_metadata_guard_executed_before_mutations(tmp_path, shell, hook, status, provider, mode):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(f"{shell} unavailable")
    suffix = "ps1" if shell == "pwsh" else "sh"
    source = (ROOT / "scripts" / f"{hook}.{suffix}").read_text(encoding="utf-8-sig")
    block = source.split("# BEGIN deployment metadata verification\n", 1)[1].split(
        "# END deployment metadata verification", 1
    )[0]
    guard_position = source.index("# BEGIN deployment metadata verification")
    for marker in ("# BEGIN PostgreSQL protection", "# BEGIN component runtime egress"):
        if marker in source:
            assert guard_position < source.index(marker)
    if shell == "pwsh":
        prefix = (
            "$env:AZURE_ENV_NAME='selected'; $repoRoot='.'; $env:AGENTLZ_REPO_ROOT='.'\n"
            "function python { $global:LASTEXITCODE = " + str(status) + " }\n"
            "function Invoke-PythonModule { param($ModuleName, $Arguments)\n"
            "if ($ModuleName -ne 'config.deployment.metadata' -or "
            "$Arguments -notcontains '--check' -or $Arguments -notcontains '--environment' -or "
            "$Arguments -notcontains 'selected' -or $Arguments -notcontains '--project-root') { exit 91 }; python }\n"
        )
        script = tmp_path / "guard.ps1"
        script.write_text(prefix + block + "\nWrite-Output 'mutation'\n", encoding="utf-8")
        command = [executable, "-NoProfile", "-File", str(script)]
    else:
        script = tmp_path / "guard.sh"
        script.write_text(
            "AZURE_ENV_NAME=selected\nPROJECT_ROOT=.\nrepo_root=.\n"
            f"python3() {{ [ \"$*\" = '-m config.deployment.metadata --check --environment selected --project-root .' ] || return 91; return {status}; }}\n"
            "red() { printf '%s\\n' \"$*\"; }\n" + block + "\necho mutation\n",
            encoding="utf-8",
        )
        command = [executable, str(script)]
    # Each invocation verifies again, without any transient state from the first.
    for _ in range(2):
        result = subprocess.run(
            command, capture_output=True, text=True,
            env={**os.environ, "INFRA_PROVIDER": provider, "APP_RUNTIME_CONFIGURATION_MODE": mode},
        )
        assert (result.returncode == 0) == (status == 0), result.stderr
        assert result.returncode == status, result.stderr
        assert ("mutation" in result.stdout) == (status == 0)


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("mode", ["appConfig", "containerEnv", "none"])
@pytest.mark.parametrize("status", [0, 7])
def test_postprovision_publication_only_for_selected_runtime(tmp_path, shell, mode, status):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(f"{shell} unavailable")
    suffix = "ps1" if shell == "pwsh" else "sh"
    source = (ROOT / "scripts" / f"postProvision.{suffix}").read_text(encoding="utf-8-sig")
    block = source.split("# BEGIN runtime configuration publication\n", 1)[1].split(
        "# END runtime configuration publication", 1
    )[0]
    script = tmp_path / f"publish.{suffix}"
    if shell == "pwsh":
        prefix = (
            f"$runtimeMode='{mode}'\n"
            "function Invoke-PythonModule { param($ModuleName)\n"
            f"Write-Output 'publication'; $global:LASTEXITCODE={status} }}\n"
        )
        command = [executable, "-NoProfile", "-File", str(script)]
        suffix_text = "\nWrite-Output 'setup'\n"
    else:
        prefix = (
            f"set -e\nAPP_RUNTIME_CONFIGURATION_MODE={mode}\nPROJECT_ROOT=.\n"
            f"python3() {{ echo publication; return {status}; }}\n"
        )
        command = [executable, str(script)]
        suffix_text = "\necho setup\n"
    script.write_text(prefix + block + suffix_text, encoding="utf-8")
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    selected = mode == "appConfig"
    assert ("publication" in result.stdout) == selected
    assert ("setup" in result.stdout) == (not selected or status == 0)
    assert (result.returncode == 0) == (not selected or status == 0)


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("hook", ["preDeploy", "postProvision"])
@pytest.mark.parametrize("invalid", [None, {}, [], {"BAD-KEY": "value"}, {"KEY": 1}, {"KEY": "\0"}])
def test_deploy_environment_roundtrip_and_fail_closed(tmp_path, shell, hook, invalid):
    if shell == "bash" and not shutil.which("jq"):
        pytest.skip("jq is required for the shipped Bash environment loader")
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
