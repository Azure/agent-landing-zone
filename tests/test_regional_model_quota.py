"""Execute the shipped PowerShell model quota checks with a read-only CLI fixture."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
ACCOUNT_ID = (
    "/subscriptions/test-subscription/resourceGroups/test-group/"
    "providers/Microsoft.CognitiveServices/accounts/test-account"
)

DRIVER = r"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$SkipAzureCliChecks = $false
$SubscriptionId = 'test-subscription'
$script:FailureCount = 0
$script:WarningCount = 0
$script:Calls = @()
$script:Findings = [System.Collections.Generic.List[pscustomobject]]::new()
$fixture = Get-Content $env:QUOTA_FIXTURE -Raw | ConvertFrom-Json
. $env:QUOTA_HELPER
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:QUOTA_SOURCE, [ref]$tokens, [ref]$errors)
if ($errors.Count -gt 0) { throw 'PowerShell source parse failed.' }
$names = @('Write-PreflightCheck', 'Get-NormalizedLocation', 'Test-ModelReadiness', 'Add-Finding', 'Test-ModelQuota')
foreach ($node in $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in $names }, $false)) {
    Invoke-Expression $node.Extent.Text
}
function Invoke-AzJson {
    param([string[]]$Arguments, [switch]$AllowFailure)
    $script:Calls += ($Arguments -join ' ')
    if (($Arguments[0..2] -join ' ') -eq 'cognitiveservices model list') { return $fixture.available }
    if (($Arguments[0..2] -join ' ') -eq 'cognitiveservices usage list') { return $fixture.usage }
    if (($Arguments[0..1] -join ' ') -eq 'resource show') {
        if ($fixture.accountFailure) { return @{ failed = $true; error = 'fixture account denied' } }
        return $fixture.account
    }
    if (($Arguments[0..1] -join ' ') -eq 'resource list') {
        if ($fixture.PSObject.Properties['projects']) { return $fixture.projects }
        return @()
    }
    if (($Arguments[0..3] -join ' ') -eq 'cognitiveservices account deployment list') {
        if ($fixture.deploymentFailure) { return @{ failed = $true; error = 'fixture deployments denied' } }
        return $fixture.deployments
    }
    throw "Unexpected Azure operation: $($Arguments -join ' ')"
}
function Invoke-AzCliRaw {
    param([string[]]$Arguments)
    $value = Invoke-AzJson -Arguments $Arguments
    if ($value -is [hashtable] -and $value.failed) { return $null }
    return $value
}
function Get-AzdEnvValues {
    if ($fixture.PSObject.Properties['selectedEnvironment']) {
        $values = @{}
        foreach ($property in $fixture.selectedEnvironment.PSObject.Properties) {
            $values[$property.Name] = $property.Value
        }
        return $values
    }
    return @{
        AZURE_AI_PROJECT_RESOURCE_ID = $env:AZURE_AI_PROJECT_RESOURCE_ID
        AZURE_RESOURCE_GROUP = $env:AZURE_RESOURCE_GROUP
    }
}
if ($env:QUOTA_GATE -eq 'foundation') {
    Test-ModelQuota -Location 'westus3' -ModelDeployments $fixture.desired
    $script:FailureCount = @($script:Findings | Where-Object Severity -eq 'FAIL').Count
    $script:WarningCount = @($script:Findings | Where-Object Severity -eq 'WARN').Count
    foreach ($finding in $script:Findings) { Write-Host "$($finding.Severity) $($finding.Message)" }
} else {
    Test-ModelReadiness -Location 'westus3' -Models $fixture.desired
}
Write-Output ('RESULT:' + (@{ failures = $script:FailureCount; warnings = $script:WarningCount; calls = $script:Calls } | ConvertTo-Json -Compress))
"""


def deployment(name: str = "embedding", capacity: int = 100) -> dict:
    return {
        "name": name,
        "model": {"format": "OpenAI", "name": "text-embedding-3-large", "version": "1"},
        "sku": {"name": "Standard", "capacity": capacity},
    }


def fixture() -> dict:
    desired = deployment()
    return {
        "desired": [desired],
        "available": [{"model": {
            "name": desired["model"]["name"], "version": "1",
            "skus": [{"name": "Standard"}, {"name": "GlobalStandard"}],
        }}],
        "usage": [{"name": {"value": "OpenAI.Standard.text-embedding-3-large"},
                   "limit": 150, "currentValue": 100}],
        "account": {"id": ACCOUNT_ID, "location": "West US 3"},
        "deployments": [{
            "name": desired["name"], "sku": copy.deepcopy(desired["sku"]),
            "properties": {"model": copy.deepcopy(desired["model"]),
                           "provisioningState": "Succeeded"},
        }],
        "accountFailure": False,
        "deploymentFailure": False,
    }


@unittest.skipUnless(PWSH, "PowerShell is required for regional quota behavior tests")
class RegionalModelQuotaTests(unittest.TestCase):
    def run_check(self, data: dict, *, project: str = ACCOUNT_ID + "/projects/test-project",
                  group: str = "test-group", gate: str = "regional") -> tuple[dict, str]:
        with tempfile.TemporaryDirectory(prefix="model quota ") as directory:
            folder = Path(directory)
            (folder / "fixture.json").write_text(json.dumps(data), encoding="utf-8")
            (folder / "run.ps1").write_text(DRIVER, encoding="utf-8")
            environment = dict(
                os.environ, QUOTA_FIXTURE=str(folder / "fixture.json"),
                QUOTA_SOURCE=str(
                    ROOT / "infra" / "scripts" / "Invoke-PreflightChecks.ps1"
                    if gate == "foundation" else ROOT / "scripts" / "Invoke-RegionalPreflight.ps1"
                ),
                QUOTA_HELPER=str(ROOT / "infra" / "scripts" / "ModelQuota.ps1"),
                QUOTA_GATE=gate,
                AZURE_AI_PROJECT_RESOURCE_ID=project, AZURE_RESOURCE_GROUP=group,
            )
            result = subprocess.run(
                [PWSH, "-NoProfile", "-NonInteractive", "-File", str(folder / "run.ps1")],
                env=environment, capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        row = next(line for line in result.stdout.splitlines() if line.startswith("RESULT:"))
        return json.loads(row.removeprefix("RESULT:")), result.stdout

    def test_existing_unchanged_allocation_needs_no_remaining_quota(self) -> None:
        data = fixture()
        data["usage"][0]["currentValue"] = 155
        result, output = self.run_check(data)
        self.assertEqual(0, result["failures"], output)
        self.assertIn("verified existing credit 100, additional allocation 0", output)

    def test_fresh_allocation_still_requires_full_capacity(self) -> None:
        for available, failures in ((50, 1), (100, 0)):
            with self.subTest(available=available):
                data = fixture()
                data["usage"][0]["limit"] = 100 + available
                result, output = self.run_check(data, project="")
                self.assertEqual(failures, result["failures"], output)
                self.assertEqual(3, len(result["calls"]))
                self.assertIn("verified existing credit 0, additional allocation 100", output)

    def test_old_blank_output_recovers_only_unique_verified_project(self) -> None:
        data = fixture()
        data["projects"] = [{"id": ACCOUNT_ID + "/projects/test-project"}]
        result, output = self.run_check(data, project="")
        self.assertEqual(0, result["failures"], output)
        self.assertIn("verified existing credit 100, additional allocation 0", output)
        for projects in (
            [*data["projects"], {"id": ACCOUNT_ID + "/projects/other"}],
            [{"id": ACCOUNT_ID.replace("test-group", "other-group") + "/projects/test-project"}],
        ):
            with self.subTest(projects=projects):
                data["projects"] = projects
                result, output = self.run_check(data, project="")
                self.assertEqual(1, result["failures"], output)
                self.assertIn("verified existing credit 0", output)

    def test_only_increment_requires_available_quota(self) -> None:
        for capacity, failures in ((150, 0), (151, 1), (75, 0)):
            with self.subTest(capacity=capacity):
                data = fixture()
                data["desired"][0]["sku"]["capacity"] = capacity
                result, output = self.run_check(data)
                self.assertEqual(failures, result["failures"], output)

    def test_existing_allocation_is_not_transferable(self) -> None:
        for changed in ("name", "model", "version", "format", "sku", "state", "capacity"):
            with self.subTest(changed=changed):
                data = fixture()
                current = data["deployments"][0]
                if changed == "name":
                    current["name"] = "another-deployment"
                elif changed in {"model", "version", "format"}:
                    key = "name" if changed == "model" else changed
                    current["properties"]["model"][key] = "another-value"
                elif changed == "sku":
                    current["sku"]["name"] = "GlobalStandard"
                elif changed == "state":
                    current["properties"]["provisioningState"] = "Failed"
                else:
                    current["sku"]["capacity"] = 0
                result, output = self.run_check(data)
                self.assertEqual(1, result["failures"], output)
                self.assertIn("verified existing credit 0", output)

    def test_existing_target_requires_scope_and_location_proof(self) -> None:
        for changed in ("subscription", "group", "project", "account", "location"):
            with self.subTest(changed=changed):
                data = fixture()
                project = ACCOUNT_ID + "/projects/test-project"
                if changed == "subscription":
                    project = project.replace("test-subscription", "other-subscription")
                elif changed == "group":
                    project = project.replace("test-group", "other-group")
                elif changed == "project":
                    project = "malformed-resource-id"
                else:
                    data["account"]["id" if changed == "account" else "location"] = "another-value"
                result, output = self.run_check(data, project=project)
                self.assertEqual(1, result["failures"], output)
                self.assertEqual(1, result["warnings"], output)
                self.assertIn("verified existing credit 0", output)

    def test_failed_existing_reads_do_not_grant_credit(self) -> None:
        for boundary in ("accountFailure", "deploymentFailure"):
            with self.subTest(boundary=boundary):
                data = fixture()
                data[boundary] = True
                result, output = self.run_check(data)
                self.assertEqual(1, result["failures"], output)
                self.assertEqual(1, result["warnings"], output)

    def test_model_availability_is_not_skipped_for_existing_capacity(self) -> None:
        data = fixture()
        data["available"] = []
        result, output = self.run_check(data)
        self.assertEqual(1, result["failures"], output)
        self.assertIn("is not listed in westus3", output)
        self.assertIn("additional allocation 0", output)

    def test_multiple_deployments_share_one_quota_budget(self) -> None:
        data = fixture()
        data["desired"] = [deployment("one", 30), deployment("two", 30)]
        result, output = self.run_check(data)
        self.assertEqual(1, result["failures"], output)
        self.assertIn("additional allocation 60", output)

    def test_existing_credit_is_consumed_only_once(self) -> None:
        data = fixture()
        data["desired"].append(copy.deepcopy(data["desired"][0]))
        result, output = self.run_check(data)
        self.assertEqual(1, result["failures"], output)
        self.assertIn("duplicate deployment name", output.lower())

    def test_invalid_capacity_is_rejected(self) -> None:
        for capacity in (0, -1):
            with self.subTest(capacity=capacity):
                data = fixture()
                data["desired"][0]["sku"]["capacity"] = capacity
                result, output = self.run_check(data)
                self.assertEqual(1, result["failures"], output)

    def test_duplicate_existing_name_is_not_credited(self) -> None:
        data = fixture()
        data["deployments"].append(copy.deepcopy(data["deployments"][0]))
        result, output = self.run_check(data)
        self.assertEqual(1, result["failures"], output)
        self.assertIn("verified existing credit 0", output)

    def test_foundation_gate_enforces_the_same_incremental_budget(self) -> None:
        for case, failures in (
            ("unchanged", 0), ("fresh", 1), ("increase", 0), ("excess", 1),
            ("aggregate", 1), ("read-failure", 1), ("wrong-region", 1), ("duplicate", 1),
        ):
            with self.subTest(case=case):
                data = fixture()
                project = ACCOUNT_ID + "/projects/test-project"
                if case == "fresh":
                    project = ""
                elif case in {"increase", "excess"}:
                    data["desired"][0]["sku"]["capacity"] = 150 if case == "increase" else 151
                elif case == "aggregate":
                    data["desired"] = [deployment("one", 30), deployment("two", 30)]
                elif case == "read-failure":
                    data["accountFailure"] = True
                elif case == "wrong-region":
                    data["account"]["location"] = "eastus"
                elif case == "duplicate":
                    data["desired"].append(copy.deepcopy(data["desired"][0]))
                else:
                    data["usage"][0]["currentValue"] = 155
                result, output = self.run_check(data, project=project, gate="foundation")
                self.assertEqual(failures, result["failures"], output)

    def test_both_platform_hooks_invoke_the_shared_regional_gate(self) -> None:
        for suffix in ("ps1", "sh"):
            with self.subTest(suffix=suffix):
                source = (ROOT / "scripts" / f"preProvision.{suffix}").read_text(encoding="utf-8")
                self.assertIn("Invoke-RegionalPreflight.ps1", source)
                self.assertIn("Invoke-PreflightChecks.ps1", source)

    def test_foundation_uses_selected_environment_not_ambient_outputs(self) -> None:
        for wrong_selected_target in (False, True):
            with self.subTest(wrong_selected_target=wrong_selected_target):
                data = fixture()
                data["selectedEnvironment"] = {
                    "AZURE_AI_PROJECT_RESOURCE_ID": ACCOUNT_ID + "/projects/test-project",
                    "AZURE_RESOURCE_GROUP": "wrong-group" if wrong_selected_target else "test-group",
                }
                result, output = self.run_check(
                    data, project=ACCOUNT_ID.replace("test-group", "ambient-group") + "/projects/stale",
                    group="ambient-group", gate="foundation",
                )
                self.assertEqual(int(wrong_selected_target), result["failures"], output)
