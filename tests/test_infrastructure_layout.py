"""Keep the infrastructure tree focused on current product responsibilities."""

from pathlib import Path
import re
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


def test_terraform_public_ips_tolerate_policy_tags_and_keep_state() -> None:
    """A policy-added ip_tags diff must never replace an in-use public IP."""
    source = (ROOT / "infra/terraform/main.networking.tf").read_text(encoding="utf-8")
    resource = source.split('resource "azurerm_public_ip" "network" {', 1)[1].split("\nmoved {", 1)[0]
    assert re.search(r"ignore_changes\s*=\s*\[\s*ip_tags\s*\]", resource)
    assert 'module "network_public_ip"' not in source
    for key in ("firewall", "firewallManagement", "bastion", "ingress"):
        assert (
            f'from = module.network_public_ip["{key}"].azurerm_public_ip.this\n'
            f'  to   = azurerm_public_ip.network["{key}"]'
        ) in source
