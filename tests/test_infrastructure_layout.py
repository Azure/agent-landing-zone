"""Keep the infrastructure tree focused on current product responsibilities."""

from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "relative",
    [
        "infra/bicep/main.bicep",
        "infra/bicep/main.parameters.json",
        "infra/shared/abbreviations.json",
        "infra/shared/roles.json",
        "infra/terraform/main.tf",
        "infra/terraform/.terraform.lock.hcl",
        "infra/LICENSE",
        "scripts/infra/Invoke-PreflightChecks.ps1",
        "scripts/infra/ModelQuota.ps1",
        "scripts/infra/Measure-MainJsonSize.ps1",
    ],
)
def test_current_infrastructure_assets_exist(relative: str) -> None:
    assert (ROOT / relative).is_file()


@pytest.mark.parametrize(
    "relative",
    [
        "infra/.github",
        "infra/.specify",
        "infra/specs",
        "infra/docs",
        "infra/media",
        "infra/pipelines",
        "infra/scripts",
        "infra/constants",
        "infra/modules",
        "infra/AGENTS.md",
        "infra/CHANGELOG.md",
        "infra/azure.yaml",
        "infra/manifest.json",
        "infra/main.bicep",
        "infra/main.parameters.json",
        "infra/tests/hub",
        "infra/tests/scripts/Deploy-Hub.ps1",
    ],
)
def test_retired_assets_are_not_tracked(relative: str) -> None:
    result = subprocess.run(
        ["git", "ls-files", "--", relative],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    existing = [path for path in result.stdout.splitlines() if (ROOT / path).is_file()]
    assert not existing, f"Retired infrastructure assets remain: {existing}"
    assert not (ROOT / relative).is_file()


def test_terraform_diagnostic_input_is_ignored() -> None:
    relative = "infra/shared/main.parameters.json"
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--", relative],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == relative
