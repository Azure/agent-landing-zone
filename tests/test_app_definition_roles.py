"""Capability-profile role assignment (T077) with a mocked Azure CLI boundary."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from config.appdefinition import expand_profiles, load_definition
from config.appdefinition.__main__ import main as cli_main
from config.appdefinition.roles import (
    RoleAssignmentError,
    assign_roles,
    assign_hosted_roles,
    discover_component_identities,
    load_role_guids,
    plan_assignments,
    resolve_scope,
)

ROOT = Path(__file__).resolve().parents[1]
RG = "rg-test"
SUB = "/subscriptions/0000/resourceGroups/rg-test/providers"
RESOURCES = {
    "Microsoft.AppConfiguration/configurationStores": [{"name": "appcs-x", "id": f"{SUB}/appcs"}],
    "Microsoft.ContainerRegistry/registries": [{"name": "crx", "id": f"{SUB}/cr"}],
    "Microsoft.KeyVault/vaults": [{"name": "kv-x", "id": f"{SUB}/kv"}],
    "Microsoft.CognitiveServices/accounts": [{"name": "aif-x", "id": f"{SUB}/aif"}],
    "Microsoft.Search/searchServices": [{"name": "srch-x", "id": f"{SUB}/srch"}],
    "Microsoft.Storage/storageAccounts": [
        {"name": "stx", "id": f"{SUB}/st"},
        {"name": "staifx", "id": f"{SUB}/staif"},
    ],
    "Microsoft.DocumentDB/databaseAccounts": [{"name": "cosmos-x", "id": f"{SUB}/cosmos"}],
}
SERVICES = {"frontend": "p-ui", "orchestrator": "p-orch", "dataingest": "p-ing"}


class FakeAz:
    """Records calls; existing assignments make re-runs converge."""

    def __init__(self, existing: set[tuple[str, str, str]] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.existing = set(existing or ())
        self.cosmos: list[dict[str, str]] = []

    def __call__(self, arguments: list[str], *, required: bool = True) -> str:
        self.calls.append(arguments)
        head = arguments[:3]
        if head[:2] == ["resource", "list"]:
            kind = arguments[arguments.index("--resource-type") + 1]
            return json.dumps(RESOURCES[kind])
        if head[:2] == ["containerapp", "list"]:
            query = arguments[arguments.index("--query") + 1]
            service = query.split("=='", 1)[1].split("'", 1)[0]
            if service not in SERVICES:
                return "[]"
            return json.dumps([{"name": f"ca-{service}", "identity": {"principalId": SERVICES[service]}}])
        if head == ["role", "assignment", "list"]:
            key = (arguments[arguments.index("--assignee") + 1], arguments[arguments.index("--role") + 1],
                   arguments[arguments.index("--scope") + 1])
            return json.dumps([{"id": "x"}] if key in self.existing else [])
        if head == ["role", "assignment", "create"]:
            self.existing.add((arguments[arguments.index("--assignee-object-id") + 1],
                               arguments[arguments.index("--role") + 1], arguments[arguments.index("--scope") + 1]))
            return ""
        if arguments[:4] == ["cosmosdb", "sql", "role", "assignment"] and arguments[4] == "list":
            return json.dumps(self.cosmos)
        if arguments[:4] == ["cosmosdb", "sql", "role", "assignment"] and arguments[4] == "create":
            self.cosmos.append({
                "principalId": arguments[arguments.index("--principal-id") + 1],
                "roleDefinitionId": f"{SUB}/cosmos/sqlRoleDefinitions/{arguments[arguments.index('--role-definition-id') + 1]}",
                "scope": f"{SUB}/cosmos",
            })
            return ""
        raise AssertionError(f"Unexpected az call: {arguments}")

    def creates(self) -> list[list[str]]:
        return [call for call in self.calls if "create" in call]


def bundled():
    return load_definition(ROOT / "app-definition.json", repo_root=ROOT)


class RoleAssignmentTests(unittest.TestCase):
    def test_key_vault_scope_uses_foundation_name_without_guessing(self):
        vaults = [{"name": "kv-app", "id": f"{SUB}/app"}, {"name": "kv-foundry", "id": f"{SUB}/foundry"}]
        with patch.dict(RESOURCES, {"Microsoft.KeyVault/vaults": vaults}):
            self.assertEqual(
                f"{SUB}/app",
                resolve_scope("keyVault", {"KEY_VAULT_NAME": "kv-app"}, RG, FakeAz()),
            )
            self.assertEqual(
                f"{SUB}/foundry",
                resolve_scope("keyVault", {
                    "AZURE_KEY_VAULT_NAME": "kv-foundry", "KEY_VAULT_NAME": "kv-app",
                }, RG, FakeAz()),
            )
            for environment in ({}, {"KEY_VAULT_NAME": "missing"}):
                with self.subTest(environment=environment), self.assertRaises(RoleAssignmentError):
                    resolve_scope("keyVault", environment, RG, FakeAz())

    def test_hosted_runtime_expands_profiles_and_converges_without_container_lookup(self):
        az = FakeAz()
        principal = "22222222-2222-4222-8222-222222222222"
        component = {"name": "agent", "profiles": ["retrieval-reader", "conversation-store"]}
        env = {"AZURE_RESOURCE_GROUP": RG}
        created = assign_hosted_roles(component, principal, env, run_az=az)
        self.assertEqual(
            {item.role for item in expand_profiles(component["profiles"])},
            {item.assignment.role for item in created},
        )
        self.assertFalse(any(call[:2] == ["containerapp", "list"] for call in az.calls))
        self.assertTrue(all(principal in call for call in az.creates()))
        az.calls.clear()
        self.assertEqual([], assign_hosted_roles(component, principal, env, run_az=az))
        self.assertEqual([], az.creates())

    def test_hosted_runtime_fails_before_writes_for_invalid_principal_or_ambiguous_scope(self):
        az = FakeAz()
        with self.assertRaises(ValueError):
            assign_hosted_roles({"name": "agent"}, "not-a-guid", {"AZURE_RESOURCE_GROUP": RG}, run_az=az)
        with self.assertRaises(RoleAssignmentError):
            assign_hosted_roles({"name": "agent"}, "00000000-0000-0000-0000-000000000000",
                                {"AZURE_RESOURCE_GROUP": RG}, run_az=az)
        vaults = [{"name": "kv-a", "id": f"{SUB}/kva"}, {"name": "kv-b", "id": f"{SUB}/kvb"}]
        with patch.dict(RESOURCES, {"Microsoft.KeyVault/vaults": vaults}):
            with self.assertRaisesRegex(RoleAssignmentError, "exactly one"):
                assign_hosted_roles({"name": "agent"}, "22222222-2222-4222-8222-222222222222",
                                    {"AZURE_RESOURCE_GROUP": RG}, run_az=az)
        self.assertEqual([], az.creates())

    def test_discovers_client_ids_without_role_writes(self) -> None:
        calls = []

        def az(arguments, *, required=True):
            calls.append(arguments)
            service = arguments[arguments.index("--query") + 1].split("=='", 1)[1].split("'", 1)[0]
            return json.dumps([{
                "name": f"ca-{service}",
                "identity": {"userAssignedIdentities": {
                    f"{SUB}/identity-{service}": {"principalId": f"p-{service}", "clientId": f"c-{service}"}
                }},
            }])

        actual = discover_component_identities(
            bundled(), {"AZURE_RESOURCE_GROUP": RG}, hosted_orchestration=True, run_az=az
        )
        self.assertEqual({"ui": "c-frontend", "ingestion": "c-dataingest"}, actual)
        self.assertTrue(all(call[:2] == ["containerapp", "list"] for call in calls))

    def test_client_id_lookup_is_exact_and_missing_identity_fails(self) -> None:
        definition = load_definition(ROOT / "samples" / "custom-app" / "containerapp")
        for system in (False, True):
            with self.subTest(system=system):
                calls = []

                def az(arguments, *, required=True):
                    calls.append(arguments)
                    if arguments[:2] == ["containerapp", "list"]:
                        identity = {"principalId": "principal"} if system else {
                            "userAssignedIdentities": {f"{SUB}/uai": {"principalId": "principal"}}
                        }
                        return json.dumps([{"name": "ca-web", "identity": identity}])
                    self.assertEqual(
                        ["ad", "sp", "show", "--id", "principal", "--query", "appId"] if system else
                        ["identity", "show", "--ids", f"{SUB}/uai", "--query", "clientId"],
                        arguments[:-3],
                    )
                    return json.dumps("client")

                self.assertEqual({"web": "client"}, discover_component_identities(
                    definition, {"AZURE_RESOURCE_GROUP": RG}, hosted_orchestration=False, run_az=az
                ))
                self.assertEqual(2, len(calls))
        with self.assertRaisesRegex(RoleAssignmentError, "found 0"):
            discover_component_identities(
                definition, {"AZURE_RESOURCE_GROUP": RG}, hosted_orchestration=False,
                run_az=lambda arguments, **kwargs: "[]",
            )
        with self.assertRaisesRegex(RoleAssignmentError, "found 2"):
            discover_component_identities(
                definition, {"AZURE_RESOURCE_GROUP": RG}, hosted_orchestration=False,
                run_az=lambda arguments, **kwargs: json.dumps([{
                    "name": "ca-web", "identity": {
                        "principalId": "p1", "userAssignedIdentities": {"uai": {"principalId": "p2"}}
                    }
                }]),
            )

    def test_hosted_only_definition_has_no_provision_time_identities(self) -> None:
        definition = load_definition(ROOT / "samples" / "custom-app" / "hosted")
        self.assertEqual({}, discover_component_identities(
            definition, {}, hosted_orchestration=False,
            run_az=lambda *args, **kwargs: self.fail("Hosted-only provision must not discover a Container App"),
        ))

    def test_plan_covers_only_containerapp_components_with_base_profile(self) -> None:
        classic = plan_assignments(bundled(), hosted_orchestration=False)
        self.assertEqual({"ui", "orchestrator", "ingestion"}, {item.component for item in classic})
        ui_roles = {item.assignment.role for item in classic if item.component == "ui"}
        self.assertEqual({a.role for a in expand_profiles(["blob-delegator"])}, ui_roles)
        self.assertIn("AcrPull", ui_roles)
        self.assertEqual({"frontend", "orchestrator", "dataingest"}, {item.service for item in classic})

        hosted = plan_assignments(bundled(), hosted_orchestration=True)
        # The hosted orchestrator is an azure.ai.agent; hosted_access owns it.
        self.assertNotIn("orchestrator", {item.component for item in hosted})

    def test_assigns_missing_roles_then_converges(self) -> None:
        az = FakeAz()
        environment = {"AZURE_RESOURCE_GROUP": RG}
        created = assign_roles(bundled(), environment, hosted_orchestration=False, run_az=az)
        planned = plan_assignments(bundled(), hosted_orchestration=False)
        self.assertEqual(len(planned), len(created))
        guids = load_role_guids(ROOT)
        rbac = [c for c in az.creates() if c[:2] == ["role", "assignment"]]
        self.assertIn(
            ["role", "assignment", "create", "--assignee-object-id", "p-ui", "--assignee-principal-type",
             "ServicePrincipal", "--role", guids["AcrPull"], "--scope", f"{SUB}/cr", "--output", "none",
             "--only-show-errors"],
            rbac,
        )
        # Foundry account storage is never chosen for the storage scope.
        self.assertFalse(any(f"{SUB}/staif" in call for call in az.calls))
        cosmos = [c for c in az.creates() if c[0] == "cosmosdb"]
        self.assertEqual({"p-orch", "p-ing"}, {c[c.index("--principal-id") + 1] for c in cosmos})

        az.calls.clear()
        self.assertEqual([], assign_roles(bundled(), environment, hosted_orchestration=False, run_az=az))
        self.assertEqual([], az.creates())

    def test_missing_container_app_fails_with_actionable_error(self) -> None:
        az = FakeAz()
        with patch.dict(SERVICES, {}, clear=True):
            with self.assertRaisesRegex(RoleAssignmentError, "azd-service-name=frontend.*azd provision"):
                assign_roles(bundled(), {"AZURE_RESOURCE_GROUP": RG}, hosted_orchestration=False, run_az=az)
        self.assertEqual([], az.creates())

    def test_ambiguous_scope_requires_explicit_name(self) -> None:
        az = FakeAz()
        vaults = [{"name": "kv-a", "id": f"{SUB}/kva"}, {"name": "kv-b", "id": f"{SUB}/kvb"}]
        with patch.dict(RESOURCES, {"Microsoft.KeyVault/vaults": vaults}):
            with self.assertRaisesRegex(RoleAssignmentError, "AZURE_KEY_VAULT_NAME"):
                assign_roles(bundled(), {"AZURE_RESOURCE_GROUP": RG}, hosted_orchestration=False, run_az=az)
            self.assertEqual([], az.creates(), "no partial assignment before the failure")
            created = assign_roles(
                bundled(),
                {"AZURE_RESOURCE_GROUP": RG, "KEY_VAULT_URI": "https://kv-b.vault.azure.net/"},
                hosted_orchestration=False,
                run_az=az,
            )
        self.assertTrue(created)
        self.assertTrue(any(f"{SUB}/kvb" in call for call in az.creates()))
        self.assertFalse(any(f"{SUB}/kva" in call for call in az.creates()))

    def test_cli_assign_roles_exit_codes(self) -> None:
        environment = {"AZURE_RESOURCE_GROUP": RG, "DEPLOYMENT_TOPOLOGY": "classic", "AGENTLZ_APP_DEFINITION": ""}
        with patch.dict("os.environ", environment), patch("config.deployment.appconfig._run_az", FakeAz()):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(0, cli_main(["--assign-roles"]))
        with patch.dict("os.environ", {**environment, "AZURE_RESOURCE_GROUP": ""}):
            with self.assertLogs("config.appdefinition", "ERROR") as logs, redirect_stderr(io.StringIO()):
                self.assertEqual(3, cli_main(["--assign-roles"]))
            self.assertIn("AZURE_RESOURCE_GROUP is required", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
