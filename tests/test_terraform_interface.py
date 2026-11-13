"""Keep both infrastructure entrypoints on the same public input/output contract."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_ROOT = REPO_ROOT / "infra" / "terraform"
# Approved PostgreSQL provider difference: preserve all 64 native Bicep
# outputs. The verified shared adapter materializes these azd keys for BOTH
# providers from the immutable binding/live resources, outside outputs v1.
POSTGRESQL_ADAPTER_OUTPUTS = {
    "POSTGRESQL_SERVER_RESOURCE_ID", "POSTGRESQL_HOST", "POSTGRESQL_PORT",
    "POSTGRESQL_DATABASE_NAME", "CONTAINER_APPS_POSTGRESQL_EGRESS_IP",
}


def _bicep_names(kind: str) -> set[str]:
    source = (REPO_ROOT / "infra" / "bicep" / "main.bicep").read_text(encoding="utf-8")
    return set(re.findall(rf"^{kind}\s+([A-Za-z_][A-Za-z0-9_]*)\s+", source, re.MULTILINE))


def _terraform_names(kind: str) -> list[str]:
    files = sorted(TERRAFORM_ROOT.glob("*.tf"))
    assert files, "The integrated Terraform root must be present."
    return [
        name
        for path in files
        for name in re.findall(
            rf'^{kind}\s+"([A-Za-z_][A-Za-z0-9_]*)"\s*\{{',
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    ]


def test_terraform_declares_the_shared_infrastructure_inputs():
    expected = _bicep_names("param")
    actual = _terraform_names("variable")
    assert expected, "The Bicep entrypoint must expose its public parameters."
    assert len(actual) == len(set(actual)), "Terraform input declarations must be unique."
    assert not expected - set(actual), f"Missing Terraform inputs: {sorted(expected - set(actual))}"


def test_terraform_preserves_every_lifecycle_output_name():
    expected = _bicep_names("output")
    actual = _terraform_names("output")
    assert expected, "The Bicep entrypoint must expose its lifecycle outputs."
    assert len(actual) == len(set(actual)), "Terraform output declarations must be unique."
    assert len(expected) == 64, "Preserve the pre-PostgreSQL Bicep output budget."
    assert "DEPLOYMENT_METADATA" in expected
    assert "OBSERVABILITY_MIXED_WORKSPACES_ALLOWED" not in expected
    assert not expected & POSTGRESQL_ADAPTER_OUTPUTS
    assert set(actual) == expected | POSTGRESQL_ADAPTER_OUTPUTS, (
        f"Missing outputs: {sorted(expected - set(actual))}; "
        f"unexpected outputs: {sorted(set(actual) - expected - POSTGRESQL_ADAPTER_OUTPUTS)}"
    )


def test_terraform_accepts_explicit_azure_deployment_context():
    required = {"subscriptionId", "tenantId", "resourceGroupName", "deploymentName"}
    actual = set(_terraform_names("variable"))
    assert required <= actual, f"Missing deployment context: {sorted(required - actual)}"


def test_metadata_application_id_is_a_typed_shared_input_not_a_store_label():
    import json

    default = json.loads((REPO_ROOT / "app-definition.json").read_text(encoding="utf-8"))["id"]
    bicep = (REPO_ROOT / "infra/bicep/main.bicep").read_text(encoding="utf-8")
    variables = (TERRAFORM_ROOT / "variables.tf").read_text(encoding="utf-8")
    outputs = (TERRAFORM_ROOT / "outputs.tf").read_text(encoding="utf-8")
    assert f"param applicationId string = '{default}'" in bicep
    assert "applicationId: applicationId" in bicep
    declaration = re.search(r'variable "applicationId" \{(.*?)^\}', variables, re.S | re.M)
    assert declaration and re.search(r"type\s*=\s*string", declaration[1])
    assert re.search(rf'default\s*=\s*"{re.escape(default)}"', declaration[1])
    assert re.search(r"applicationId\s*=\s*var.applicationId", outputs)
    parameters = json.loads((REPO_ROOT / "main.parameters.json").read_text(encoding="utf-8"))
    assert parameters["parameters"]["applicationId"]["value"] == "${AGENTLZ_APP_ID=" + default + "}"


def test_metadata_is_explicitly_public_without_declassifying_dependencies():
    source = (TERRAFORM_ROOT / "outputs.tf").read_text(encoding="utf-8")
    block = re.search(r'output "DEPLOYMENT_METADATA" \{(.*?)^\}', source, re.S | re.M)
    assert block, "Dedicated output must not be hidden inside hosted metadata."
    assert re.search(r"^\s*sensitive\s*=\s*false\s*$", block[1], re.M)
    assert "nonsensitive(" not in source
    for prohibited in (
        "existingApplicationInsightsConnectionString", "connection_string",
        "instrumentation_key", "app_config_bootstrap", "additionalAppConfigurationSettings",
        "compute_jumpbox_password", "legacy_application_key",
    ):
        assert prohibited not in source
    assert "OBSERVABILITY_MIXED_WORKSPACES_ALLOWED" not in source
    for path in (TERRAFORM_ROOT / "variables.tf", REPO_ROOT / "infra/bicep/main.bicep"):
        assert "allowMixedObservabilityWorkspaces" in path.read_text(encoding="utf-8")
