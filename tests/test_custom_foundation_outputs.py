"""Foundation endpoint handoff must not depend on bundled hosted selection."""

from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_deployment_schema_is_independent_closed_and_integrity_checked():
    import hashlib
    import json
    import jsonschema

    path = ROOT / "contracts/deployment-metadata-v1.schema.json"
    schema = json.loads(path.read_bytes())
    assert schema["additionalProperties"] is False
    assert "/specs/" not in schema["$id"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == path.with_suffix(
        ".json.sha256"
    ).read_text().split()[0]
    example = json.loads((ROOT / "tests/fixtures/deployment-metadata-v1.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(example)
    example["resources"]["appConfig"] = {"status": "disabled", "resource": {"name": "wrong"}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(example)
    runtime = ROOT / "contracts/platform-outputs-v1.schema.json"
    assert hashlib.sha256(runtime.read_bytes()).hexdigest() == (
        "7217acf4ab374fd2f6426f849d013756f911ae297ab99c13aed78bc976aecd3d"
    )
    assert runtime.with_suffix(".json.sha256").read_bytes() == (
        b"7217acf4ab374fd2f6426f849d013756f911ae297ab99c13aed78bc976aecd3d  platform-outputs-v1.schema.json\n"
    )


def test_native_named_terraform_and_azd_json_transport(tmp_path):
    """Resource-free native roundtrip, not an Azure deployment or state reader."""
    import json
    import shutil
    import subprocess

    terraform, azd = shutil.which("terraform"), shutil.which("azd")
    if not terraform or not azd:
        pytest.skip("Terraform and azd are required for native transport evidence")
    example = json.loads((ROOT / "tests/fixtures/deployment-metadata-v1.json").read_text())
    (tmp_path / "main.tf.json").write_text(json.dumps({
        "output": {"DEPLOYMENT_METADATA": {"value": example, "sensitive": False}},
    }), encoding="utf-8")
    for args in (["init", "-backend=false", "-input=false", "-lockfile=readonly"],
                 ["apply", "-input=false", "-auto-approve"]):
        result = subprocess.run([terraform, f"-chdir={tmp_path}", *args],
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
    result = subprocess.run([terraform, f"-chdir={tmp_path}", "output", "-json", "DEPLOYMENT_METADATA"],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == example
    # azd 1.37.3 manager.UpdateEnvironment json.Marshal's object values before
    # DotenvSet. Exercise the resulting string through its real persisted reader.
    encoded = json.dumps(json.loads(result.stdout), separators=(",", ":"))
    assert len(encoded.encode("utf-8")) < 32767
    (tmp_path / "azure.yaml").write_text("name: metadata-contract\n", encoding="utf-8")
    selected = tmp_path / ".azure" / "contract"
    selected.mkdir(parents=True)
    (selected / ".env").write_text('AZURE_ENV_NAME="contract"\n', encoding="utf-8")
    result = subprocess.run([azd, "env", "set", "DEPLOYMENT_METADATA", encoded,
                             "--cwd", str(tmp_path), "--environment", "contract", "--no-prompt"],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([azd, "env", "get-value", "DEPLOYMENT_METADATA",
                             "--cwd", str(tmp_path), "--environment", "contract", "--no-prompt"],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == example


@pytest.mark.parametrize("name,flag,value", [
    ("AZURE_AI_PROJECT_RESOURCE_ID", "deployAiFoundry", "aiFoundryProjectResourceId"),
    ("AZURE_AI_PROJECT_ENDPOINT", "deployAiFoundry", "aiFoundryProjectEndpoint"),
    ("AZURE_CONTAINER_REGISTRY_RESOURCE_ID", "deployContainerRegistry",
     "_hostedAgentContainerRegistryResourceId"),
    ("AZURE_CONTAINER_REGISTRY_ENDPOINT", "deployContainerRegistry",
     "_hostedAgentContainerRegistryEndpoint"),
])
def test_foundation_handoff_preserves_disabled_and_external_hosted_cases(name, flag, value):
    text = (ROOT / "infra" / "bicep" / "main.bicep").read_text(encoding="utf-8")
    expression = re.search(rf"^output {name} string = (.+)$", text, re.MULTILINE)[1]
    assert expression == f"({flag} || _hostedAgentPrerequisitesEnabled) ? {value} : ''"
    for provisioned, hosted, expected in (
        (False, False, ""), (True, False, value),
        (False, True, value), (True, True, value),
    ):
        assert (value if provisioned or hosted else "") == expected


def test_native_model_defaults_match_the_metadata_verifier():
    import hcl2
    from config.deployment.metadata import _DEFAULT_MODELS

    bicep = (ROOT / "infra" / "bicep" / "main.bicep").read_text(encoding="utf-8")
    assert "var _deploymentMetadataModels = deployModelDeployments ? (" in bicep
    fallback = re.search(
        r"var _deploymentMetadataModels = .*? : \[(.*?)^\]", bicep, re.M | re.S,
    )[1]
    bicep_models = re.findall(
        r"format: '([^']+)'\s+name: '([^']+)'\s+version: '([^']+)'", fallback,
    )
    terraform = (ROOT / "infra" / "terraform" / "main.foundry.tf").read_text(encoding="utf-8")
    fallback = re.search(
        r"services_model_deployments = var\.deployModelDeployments \? concat\(var\.modelDeploymentList, \[for deployment in "
        r"(\[.*?\]) : deployment if", terraform, re.S,
    )[1]
    terraform_models = hcl2.loads("locals { models = " + fallback + " }")["locals"][0]["models"]
    expected = [
        {"canonical_name": canonical, "name": name,
         "model": {"format": "OpenAI", "name": name, "version": version}}
        for canonical, name, version in _DEFAULT_MODELS
    ]
    assert bicep_models == [
        (row["model"]["format"], row["model"]["name"], row["model"]["version"])
        for row in expected
    ]
    assert "(index == 0 ? 'GPT_MODEL' : 'EMBEDDING_MODEL')" in bicep
    assert [
        {key: row[key] for key in ("canonical_name", "name", "model")}
        for row in terraform_models
    ] == expected
