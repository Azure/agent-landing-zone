"""Execute provider validation in both lifecycle hook variants."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
START = "# BEGIN infrastructure provider validation"
END = "# END infrastructure provider validation"


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize(
    ("configuration", "exit_code", "expected"),
    [
        ({"provider": "bicep"}, 0, "bicep"),
        ({"provider": "terraform"}, 0, "terraform"),
        ({"provider": "unsupported"}, 0, None),
        ({"provider": None}, 0, None),
        ({}, 0, None),
        ([], 0, None),
        ("invalid-json", 0, None),
        ({"provider": "terraform"}, 1, None),
    ],
)
def test_provider_validation_propagates_selection_or_stops(
    tmp_path, shell, configuration, exit_code, expected
):
    extension = "ps1" if shell == "pwsh" else "sh"
    source = (ROOT / "scripts" / f"preProvision.{extension}").read_text(encoding="utf-8-sig")
    block = source[source.index(START) : source.index(END)]
    values = configuration if isinstance(configuration, str) else json.dumps(configuration)
    environment = {
        **os.environ,
        "PROVIDER_CONFIGURATION": values,
        "PROVIDER_EXIT_CODE": str(exit_code),
    }
    if shell == "pwsh":
        script = tmp_path / "provider.ps1"
        script.write_text(
            "Set-StrictMode -Version Latest\n$ErrorActionPreference = 'Stop'\n"
            "$projectRoot = '.'\n"
            "function Invoke-PythonModule { param($ModuleName, $Arguments)\n"
            "if ($ModuleName -ne 'config.deployment.provider' -or "
            "$Arguments -notcontains '--repo-root') { exit 9 }\n"
            "$global:LASTEXITCODE = [int]$env:PROVIDER_EXIT_CODE\n"
            "return $env:PROVIDER_CONFIGURATION }\n"
            + block
            + "\nWrite-Output \"SELECTED=$infrastructureProvider\"\n",
            encoding="utf-8",
        )
        command = [shutil.which("pwsh"), "-NoProfile", "-File", str(script)]
    else:
        script = tmp_path / "provider.sh"
        script.write_text(
            'PROJECT_ROOT=.\nPYTHON_CMD=provider_python\n'
            "provider_python() {\n"
            'if [ "$1" = "-m" ]; then\n'
            '[ "$*" = "-m config.deployment.provider --repo-root ." ] || return 9\n'
            'printf "%s" "$PROVIDER_CONFIGURATION"\n'
            'return "$PROVIDER_EXIT_CODE"\n'
            "fi\n"
            'python "$@"\n}\n'
            + block
            + '\nprintf "SELECTED=%s\\n" "$INFRA_PROVIDER"\n',
            encoding="utf-8",
            newline="\n",
        )
        command = [shutil.which("bash"), str(script)]
    assert command[0], f"{shell} is required to exercise the shipped hook."
    result = subprocess.run(
        command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30
    )
    if expected is not None:
        assert result.returncode == 0, result.stdout + result.stderr
        assert f"SELECTED={expected}" in result.stdout
    else:
        assert result.returncode != 0, result.stdout + result.stderr
        assert "SELECTED=" not in result.stdout
        assert "Infrastructure provider validation" in result.stdout + result.stderr


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize(
    "values",
    [
        {"AGENTLZ_IMPORT_TEST": "literal ${UNEXPANDED} $(not-a-command) `text` 'quoted'\nnext"},
        {},
        [],
        {"INVALID-NAME": "value"},
        {"AGENTLZ_IMPORT_TEST": True},
        {"AGENTLZ_IMPORT_TEST": None},
        {"AGENTLZ_IMPORT_TEST": "invalid\0value"},
        "{",
    ],
)
def test_environment_import_preserves_literals_and_rejects_invalid_values(tmp_path, shell, values):
    extension = "ps1" if shell == "pwsh" else "sh"
    source = (ROOT / "scripts" / f"preProvision.{extension}").read_text(encoding="utf-8-sig")
    block = source.split("# BEGIN azd environment import\n", 1)[1].split(
        "# END azd environment import", 1
    )[0]
    environment = {
        **os.environ,
        "IMPORT_JSON": values if isinstance(values, str) else json.dumps(values),
    }
    if shell == "pwsh":
        helper = source.split("function Import-AzdEnvironment {", 1)[1].split(
            "# Locate the repository root", 1
        )[0]
        prefix = (
            "$ErrorActionPreference = 'Stop'\nSet-StrictMode -Version Latest\n"
            "function Import-AzdEnvironment {"
            + helper
            + "function Get-AzdEnvironmentJson { return $env:IMPORT_JSON }\n"
        )
        suffix = "\n@{ value = $env:AGENTLZ_IMPORT_TEST } | ConvertTo-Json -Compress\n"
        command = [shutil.which("pwsh"), "-NoProfile", "-File", str(tmp_path / "import.ps1")]
    else:
        helper = source.split("import_azd_environment() {", 1)[1].split(
            "# BEGIN azd environment import", 1
        )[0]
        prefix = (
            "PYTHON_CMD=python\n"
            "load_azd_environment_json() { printf '%s' \"$IMPORT_JSON\"; }\n"
            "import_azd_environment() {"
            + helper
        )
        suffix = (
            "\npython -c 'import json,os; "
            'print(json.dumps({"value": os.environ.get("AGENTLZ_IMPORT_TEST")}))'
            "'\n"
        )
        command = [shutil.which("bash"), str(tmp_path / "import.sh")]
    assert command[0], f"{shell} is required to exercise the shipped hook."
    (tmp_path / f"import.{extension}").write_text(
        prefix + block + suffix, encoding="utf-8", newline="\n"
    )
    result = subprocess.run(
        command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30
    )
    valid = isinstance(values, dict) and isinstance(values.get("AGENTLZ_IMPORT_TEST"), str)
    valid = valid and "\0" not in values["AGENTLZ_IMPORT_TEST"]
    if valid:
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["value"] == values["AGENTLZ_IMPORT_TEST"]
    else:
        assert result.returncode != 0, result.stdout + result.stderr


def test_powershell_python_module_receives_json_through_stdin(tmp_path):
    source = (ROOT / "scripts" / "preProvision.ps1").read_text(encoding="utf-8-sig")
    helper = source.split("function Invoke-PythonModule {", 1)[1].split(
        "function Get-AzdEnvironmentJson", 1
    )[0]
    value = {"literal": "${NOT_EXPANDED} and $(not-a-command)", "typed": [True, None, 7]}
    script = tmp_path / "stdin.ps1"
    script.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "$env:AGENTLZ_REPO_ROOT = $PWD.Path\n"
        "function Invoke-PythonModule {"
        + helper
        + "\nInvoke-PythonModule -ModuleName 'json.tool' -StandardInput $env:INPUT_JSON\n"
        "exit $LASTEXITCODE\n",
        encoding="utf-8",
    )
    executable = shutil.which("pwsh")
    assert executable, "PowerShell is required to exercise the shipped hook."
    result = subprocess.run(
        [executable, "-NoProfile", "-File", str(script)],
        cwd=tmp_path,
        env={**os.environ, "INPUT_JSON": json.dumps(value)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == value


HOOK_DRIVER = r'''
import json
import os
from pathlib import Path
import re
import subprocess
import sys

root = Path(os.environ["HOOK_ROOT"])
snapshot = root / "environment.json"
trace = root / "trace"
failure = os.environ["HOOK_FAILURE"]

def record(event):
    with trace.open("a", encoding="utf-8") as stream:
        stream.write(event + "\n")

def save(values):
    snapshot.write_text(json.dumps(values), encoding="utf-8")

command, *args = sys.argv[1:]
values = json.loads(snapshot.read_text(encoding="utf-8"))
if command == "azd":
    if args[:2] == ["env", "get-values"]:
        assert "--output" in args and "json" in args
        if values.get("HOOK_PREPARED") == "true":
            record("environment-reload")
            if failure == "reload":
                print("[]")
                sys.exit(0)
        print(json.dumps(values))
    else:
        assert args[:2] == ["env", "set"]
        values[args[2]] = args[3]
        save(values)
    sys.exit(0)

assert command == "python"
if args[0] == "-m":
    module, args = args[1], args[2:]
else:
    assert args[0] == "-c"
    match = re.search(r"runpy\.run_module\('([^']+)'", args[1])
    if not match:
        sys.exit(subprocess.call([sys.executable, *args]))
    module, args = match[1], args[2:]

def argument(name):
    return args[args.index(name) + 1]

if module == "config.deployment.provider":
    print(json.dumps({
        "provider": "terraform", "path": "infra/foundation", "module": "foundation",
    }))
elif module == "config.appdefinition":
    record("appdefinition")
    assert Path(argument("--validate")).is_file()
elif module == "config.deployment.terraform_groups":
    record("terraform_groups")
    assert argument("--environment") == "-"
    assert json.load(sys.stdin)["HOOK_LITERAL"] == values["HOOK_LITERAL"]
    values.update(AZURE_RESOURCE_GROUP="rg-ai", AZURE_APP_RESOURCE_GROUP="rg-app",
                  AZURE_NETWORK_RESOURCE_GROUP="rg-net", CREATE_RESOURCE_GROUPS="true")
    save(values)
    ownership = root / ".azure" / "offline" / "terraform-resource-groups.json"
    ownership.parent.mkdir(parents=True)
    ownership.write_text("{}", encoding="utf-8")
    print(json.dumps({
        "foundry": "rg-ai", "application": "rg-app", "network": "rg-net",
        "create_resource_groups": True, "ownershipFile": str(ownership),
    }))
elif module == "config.deployment.topology":
    record("topology")
    assert os.environ["AZURE_RESOURCE_GROUP"] == "rg-ai"
    assert os.environ["AZURE_APP_RESOURCE_GROUP"] == "rg-app"
    assert os.environ["AZURE_NETWORK_RESOURCE_GROUP"] == "rg-net"
    assert os.environ["CREATE_RESOURCE_GROUPS"] == "true"
    print("DEPLOYMENT_TOPOLOGY=classic")
    print("USE_FOUNDRY_HOSTED_AGENTS=false")
elif module == "config.deployment.firewall":
    record("firewall")
    assert Path(argument("--input")) == root / "main.parameters.json"
    if failure == "firewall":
        sys.exit(19)
    print("AZURE_FIREWALL_SKU=Basic")
    print("DEPLOY_AZURE_FIREWALL_SUBNET=true")
    print("DEPLOY_AZURE_FIREWALL_MANAGEMENT_SUBNET=true")
    print("DEPLOY_GATEWAY_SUBNET=false")
elif module == "config.deployment.terraform_inputs":
    record("inputs")
    assert argument("--environment") == "-"
    assert Path(argument("--app-definition")) == root / "app-definition.json"
    incoming = json.load(sys.stdin)
    assert incoming["DEPLOYMENT_TOPOLOGY"] == "classic"
    assert incoming["USE_FOUNDRY_HOSTED_AGENTS"] == "false"
    assert incoming["AZURE_FIREWALL_SKU"] == "Basic"
    assert incoming["DEPLOY_AZURE_FIREWALL_MANAGEMENT_SUBNET"] == "true"
    assert incoming["DEPLOY_GATEWAY_SUBNET"] == "false"
    assert incoming["HOOK_LITERAL"] == values["HOOK_LITERAL"]
    assert Path(argument("--input")) == root / "main.parameters.json"
    assert Path(argument("--resource-group-ownership")).is_file()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    commit = next(c["commit"] for c in manifest["components"]
                  if c["name"].endswith("-orchestrator"))
    assert argument("--hosted-source-commit") == commit
    destination = Path(argument("--output"))
    assert destination == root / "infra" / "foundation" / "foundation.tfvars.json"
    assert Path(argument("--diagnostic-output")) == root / "infra" / "main.parameters.json"
    if failure == "inputs":
        sys.exit(17)
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps({"literal": incoming["HOOK_LITERAL"]}), encoding="utf-8")
    (root / "infra" / "main.parameters.json").write_text(
        json.dumps({"parameters": {"location": {"value": "eastus2"}}}), encoding="utf-8")
    values.update(ARM_ENVIRONMENT="public", TF_STATE_SUBSCRIPTION_ID="normalized",
                  HOOK_PREPARED="true")
    save(values)
elif module == "config.deployment.egress":
    record("egress")
    assert args == ["--plan", "--save"]
    assert os.environ["ARM_ENVIRONMENT"] == "public"
    assert os.environ["TF_STATE_SUBSCRIPTION_ID"] == "normalized"
    assert os.environ["HOOK_LITERAL"] == values["HOOK_LITERAL"]
    assert (root / "infra" / "foundation" / "foundation.tfvars.json").is_file()
    if failure == "egress":
        sys.exit(19)
else:
    raise AssertionError("Unexpected module: " + module)
'''


@pytest.mark.parametrize("shell", ["pwsh", "bash"])
@pytest.mark.parametrize("failure", ["none", "firewall", "inputs", "reload", "egress"])
def test_complete_terraform_hook_prepares_reloads_and_short_circuits(tmp_path, shell, failure):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (tmp_path / "infra" / "scripts").mkdir(parents=True)
    for name in ("manifest.json", "azure.yaml", "app-definition.json", "main.parameters.json"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    extension = "ps1" if shell == "pwsh" else "sh"
    hook = scripts / f"preProvision.{extension}"
    shutil.copyfile(ROOT / "scripts" / hook.name, hook)
    literal = "${UNEXPANDED} $(not-a-command) 'quoted'\nnext"
    (tmp_path / "environment.json").write_text(json.dumps({
        "AZURE_ENV_NAME": "offline", "HOOK_LITERAL": literal,
        "ARM_ENVIRONMENT": "AzureCloud", "PREFLIGHT_SKIP": "false",
        "AGENTLZ_REGIONAL_PREFLIGHT_SKIP": "false",
        "AZURE_SKIP_NETWORK_ISOLATION_WARNING": "true",
    }), encoding="utf-8")
    driver = tmp_path / "driver.py"
    driver.write_text(HOOK_DRIVER, encoding="utf-8")
    preflight = (
        "param([string]$ProjectRoot, [string]$ParameterFile)\n"
        "$ErrorActionPreference = 'Stop'\n"
        "if ($env:ARM_ENVIRONMENT -ne 'public') { throw 'Environment not reloaded' }\n"
        "if (-not $ParameterFile) { $ParameterFile = Join-Path $env:HOOK_ROOT 'infra/main.parameters.json' }\n"
        "$document = Get-Content -LiteralPath $ParameterFile -Raw | ConvertFrom-Json\n"
        "if ($document.parameters.location.value -ne 'eastus2') { throw 'Wrong diagnostic input' }\n"
    )
    (scripts / "Invoke-RegionalPreflight.ps1").write_text(
        preflight + "Add-Content -LiteralPath (Join-Path $env:HOOK_ROOT 'trace') -Value regional-preflight\n",
        encoding="utf-8",
    )
    (tmp_path / "infra" / "scripts" / "Invoke-PreflightChecks.ps1").write_text(
        preflight + "Add-Content -LiteralPath (Join-Path $env:HOOK_ROOT 'trace') -Value foundation-preflight\n",
        encoding="utf-8",
    )
    environment = {
        **os.environ, "HOOK_ROOT": str(tmp_path), "HOOK_FAILURE": failure,
        "REAL_PYTHON": sys.executable, "HOOK_DRIVER": str(driver),
    }
    if shell == "pwsh":
        wrapper = tmp_path / "wrapper.ps1"
        wrapper.write_text(
            "function azd { & $env:REAL_PYTHON $env:HOOK_DRIVER azd @args; "
            "$global:LASTEXITCODE = $LASTEXITCODE }\n"
            "function python { $input | & $env:REAL_PYTHON $env:HOOK_DRIVER python @args; "
            "$global:LASTEXITCODE = $LASTEXITCODE }\n"
            "& (Join-Path $PSScriptRoot 'scripts/preProvision.ps1')\nexit $LASTEXITCODE\n",
            encoding="utf-8",
        )
        command = [shutil.which(shell), "-NoProfile", "-NonInteractive", "-File", str(wrapper)]
    else:
        binaries = tmp_path / "bin"
        binaries.mkdir()
        for name in ("azd", "python3", "python"):
            executable = binaries / name
            executable.write_text(
                '#!/bin/sh\nexec "$REAL_PYTHON" "$HOOK_DRIVER" '
                + ("azd" if name == "azd" else "python") + ' "$@"\n',
                encoding="utf-8", newline="\n",
            )
            executable.chmod(0o755)
        environment["PATH"] = str(binaries) + os.pathsep + environment["PATH"]
        command = [shutil.which(shell), str(hook)]
    assert command[0], f"{shell} is required to exercise the shipped hook."
    result = subprocess.run(
        command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=120
    )
    output = result.stdout + result.stderr
    expected = ["appdefinition", "terraform_groups", "topology", "firewall"]
    if failure != "firewall":
        expected.append("inputs")
    if failure not in ("firewall", "inputs"):
        expected.append("environment-reload")
        if failure != "reload":
            expected.append("egress")
            if failure == "none":
                expected += ["regional-preflight", "foundation-preflight"]
    assert (tmp_path / "trace").read_text(encoding="utf-8-sig").splitlines() == expected, output
    assert (result.returncode == 0) == (failure == "none"), output
    if failure == "inputs":
        assert result.returncode == 17, output
    if failure == "none":
        native = tmp_path / "infra" / "foundation" / "foundation.tfvars.json"
        assert json.loads(native.read_text(encoding="utf-8"))["literal"] == literal
