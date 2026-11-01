"""Exercise delegated-subnet provider checks without Azure access."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
DRIVER = r"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$SubscriptionId = 'workload-sub'
$SkipAzureCliChecks = $false
$script:FailureCount = 0
$script:WarningCount = 0
$script:ProviderCache = @{}
$script:Calls = @()
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:SUBNET_SOURCE, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Regional preflight did not parse.' }
$names = @('Write-PreflightCheck', 'Resolve-TemplateValue', 'Get-ParameterValue',
    'Get-DeploymentFlag', 'Test-Truthy', 'Test-DelegatedSubnetProviders',
    'Get-Provider', 'Test-ProviderRegistration')
foreach ($node in $ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in $names
}, $false)) { Invoke-Expression $node.Extent.Text }
function Invoke-AzJson {
    param([string[]]$Arguments)
    if (($Arguments[0..1] -join ' ') -ne 'provider show') { throw 'Unexpected Azure operation.' }
    $script:Calls += ($Arguments -join ' ')
    return @{ registrationState = $env:SUBNET_REGISTRATION }
}
$parameters = Get-Content $env:SUBNET_PARAMETERS -Raw | ConvertFrom-Json
Test-DelegatedSubnetProviders -Parameters $parameters
if ($env:SUBNET_TEST_CACHE -eq 'true') {
    $null = Get-Provider -Namespace 'Microsoft.Web' -TargetSubscriptionId 'workload-sub'
    $null = Get-Provider -Namespace 'Microsoft.Web' -TargetSubscriptionId 'workload-sub'
}
Write-Output ('RESULT:' + (@{ failures = $script:FailureCount; calls = @($script:Calls) } | ConvertTo-Json -Compress))
"""


@unittest.skipUnless(PWSH, "PowerShell is required for subnet provider checks")
class SubnetProviderPreflightTests(unittest.TestCase):
    def run_check(
        self, values: dict, *, registration: str = "Registered", cache: bool = False,
    ) -> dict:
        with tempfile.TemporaryDirectory(prefix="subnet providers ") as directory:
            folder = Path(directory)
            parameters = {name: {"value": value} for name, value in values.items()}
            (folder / "parameters.json").write_text(json.dumps(parameters), encoding="utf-8")
            (folder / "run.ps1").write_text(DRIVER, encoding="utf-8")
            environment = dict(
                os.environ,
                SUBNET_SOURCE=str(ROOT / "scripts" / "Invoke-RegionalPreflight.ps1"),
                SUBNET_PARAMETERS=str(folder / "parameters.json"),
                SUBNET_REGISTRATION=registration,
                SUBNET_TEST_CACHE=str(cache).lower(),
            )
            result = subprocess.run(
                [PWSH, "-NoProfile", "-NonInteractive", "-File", str(folder / "run.ps1")],
                env=environment, capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        row = next(line for line in result.stdout.splitlines() if line.startswith("RESULT:"))
        return json.loads(row.removeprefix("RESULT:"))

    def test_isolated_default_checks_both_delegation_providers(self) -> None:
        result = self.run_check({"networkIsolation": True})
        self.assertEqual(0, result["failures"])
        self.assertEqual(2, len(result["calls"]))
        for namespace, call in zip(("Microsoft.PowerPlatform", "Microsoft.Web"), result["calls"]):
            self.assertIn(f"--namespace {namespace}", call)
            self.assertIn("--subscription workload-sub", call)

    def test_public_or_global_opt_out_makes_no_provider_request(self) -> None:
        for values in ({}, {"networkIsolation": False},
                       {"networkIsolation": True, "deploySubnets": False}):
            with self.subTest(values=values):
                self.assertEqual([], self.run_check(values)["calls"])

    def test_individual_flags_select_only_managed_delegations(self) -> None:
        for power, gateway in ((False, False), (True, False), (False, True)):
            with self.subTest(power=power, gateway=gateway):
                result = self.run_check({
                    "networkIsolation": True,
                    "deployPowerPlatformSubnet": power, "deployAiGatewaySubnet": gateway,
                })
                self.assertEqual(int(power) + int(gateway), len(result["calls"]))
                self.assertEqual(power, any("Microsoft.PowerPlatform" in c for c in result["calls"]))
                self.assertEqual(gateway, any("Microsoft.Web" in c for c in result["calls"]))

    def test_byo_uses_network_subscription_and_cache_is_subscription_specific(self) -> None:
        result = self.run_check({
            "networkIsolation": True, "useExistingVNet": True,
            "existingVnetResourceId": (
                "/subscriptions/network-sub/resourceGroups/network/"
                "providers/Microsoft.Network/virtualNetworks/shared"
            ),
        }, cache=True)
        self.assertEqual(0, result["failures"])
        self.assertEqual(3, len(result["calls"]))
        self.assertTrue(all("--subscription network-sub" in call for call in result["calls"][:2]))
        self.assertIn("--subscription workload-sub", result["calls"][2])

    def test_missing_byo_id_and_unregistered_providers_fail(self) -> None:
        missing = self.run_check({"networkIsolation": True, "useExistingVNet": True})
        self.assertEqual(1, missing["failures"])
        self.assertEqual([], missing["calls"])
        unregistered = self.run_check({"networkIsolation": True}, registration="NotRegistered")
        self.assertEqual(2, unregistered["failures"])

    def test_no_delegation_writes_do_not_require_provider_target(self) -> None:
        result = self.run_check({
            "networkIsolation": True, "useExistingVNet": True,
            "deployPowerPlatformSubnet": False, "deployAiGatewaySubnet": False,
        })
        self.assertEqual(0, result["failures"])
        self.assertEqual([], result["calls"])


if __name__ == "__main__":
    unittest.main()
