"""Keep both infrastructure entrypoints on the same public input/output contract."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_ROOT = REPO_ROOT / "infra" / "terraform"


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
    assert set(actual) == expected, (
        f"Missing outputs: {sorted(expected - set(actual))}; "
        f"unexpected outputs: {sorted(set(actual) - expected)}"
    )


def test_terraform_accepts_explicit_azure_deployment_context():
    required = {"subscriptionId", "tenantId", "resourceGroupName", "deploymentName"}
    actual = set(_terraform_names("variable"))
    assert required <= actual, f"Missing deployment context: {sorted(required - actual)}"
