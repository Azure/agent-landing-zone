from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from config.panel import setup


ENVIRONMENT_BASE = {
    "AZURE_SUBSCRIPTION_ID": "11111111-1111-1111-1111-111111111111",
    "AZURE_RESOURCE_GROUP": "rg-test",
    "DATABASE_ACCOUNT_NAME": "cosmos-test",
    "DATABASE_NAME": "agentlz-db",
    "RESOURCE_TOKEN": "abc123",
}


class PanelContainerGrantsTests(unittest.TestCase):
    def test_grants_cover_frontend_and_ingestion_only(self) -> None:
        grants = setup.panel_container_grants()
        service_names = {grant.service_name for grant in grants}

        self.assertEqual(
            service_names,
            {setup.FRONTEND_APP_SERVICE_NAME},
        )
        # The hosted agent/orchestrator identity must never appear here.
        self.assertNotIn("orchestrator", service_names)

    def test_frontend_gets_contributor_ingestion_gets_reader(self) -> None:
        grants = setup.panel_container_grants()

        frontend_roles = {
            grant.role_definition_guid
            for grant in grants
            if grant.service_name == setup.FRONTEND_APP_SERVICE_NAME
        }
        ingestion_roles = {
            grant.role_definition_guid
            for grant in grants
            if grant.service_name == setup.DATA_INGEST_APP_SERVICE_NAME
        }

        self.assertEqual(frontend_roles, {setup.COSMOS_DATA_CONTRIBUTOR_ROLE_GUID})
        self.assertEqual(ingestion_roles, set())

    def test_every_grant_targets_a_panel_only_container(self) -> None:
        from config.panel.settings import (
            FEEDBACK_CONTAINER_NAME,
            OWNER_INDEX_CONTAINER_NAME,
        )

        grants = setup.panel_container_grants()
        container_names = {grant.container_name for grant in grants}

        self.assertEqual(
            container_names, {"native-ui-metadata"}
        )
        self.assertNotIn("conversations", container_names)
        self.assertNotIn("datasources", container_names)
        self.assertNotIn("prompts", container_names)
        self.assertNotIn("mcp", container_names)


class ScopePathTests(unittest.TestCase):
    def test_container_scope_path_is_narrower_than_account_scope(self) -> None:
        scope = setup.container_scope_path(
            "sub", "rg", "acct", "db", "panel-feedback"
        )

        self.assertTrue(scope.endswith("/dbs/db/colls/panel-feedback"))
        self.assertIn(
            "/providers/Microsoft.DocumentDB/databaseAccounts/acct", scope
        )

    def test_container_scope_path_requires_every_component(self) -> None:
        with self.assertRaises(setup.PanelRbacError):
            setup.container_scope_path("", "rg", "acct", "db", "container")


class ConfigurePanelRbacTests(unittest.TestCase):
    def test_resolves_single_user_assigned_container_app_identity(self) -> None:
        identity = {
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.ManagedIdentity/userAssignedIdentities/frontend": {
                "clientId": "client",
                "principalId": "frontend-principal",
            }
        }
        with patch.object(
            setup,
            "_run_az",
            side_effect=["", json.dumps(identity)],
        ) as run_az:
            principal_id = setup.resolve_container_app_principal_id(
                "rg",
                "frontend",
            )

        self.assertEqual(principal_id, "frontend-principal")
        self.assertFalse(run_az.call_args_list[0].kwargs["required"])
        self.assertEqual(
            run_az.call_args_list[1].args[0][
                run_az.call_args_list[1].args[0].index("--query") + 1
            ],
            "identity.userAssignedIdentities",
        )

    def test_rejects_ambiguous_user_assigned_container_app_identities(self) -> None:
        identities = {
            "first": {"principalId": "principal-1"},
            "second": {"principalId": "principal-2"},
        }
        with patch.object(
            setup,
            "_run_az",
            side_effect=["", json.dumps(identities)],
        ):
            with self.assertRaisesRegex(
                setup.PanelRbacError,
                "exactly one managed-identity principal",
            ):
                setup.resolve_container_app_principal_id("rg", "frontend")

    def test_noop_when_panel_not_deployed(self) -> None:
        with patch.object(setup, "_run_az") as run_az:
            created = setup.configure_panel_rbac({})

        self.assertEqual(created, 0)
        run_az.assert_not_called()

    def test_raises_when_deployed_but_missing_required_values(self) -> None:
        # No AZURE_RESOURCE_GROUP/DATABASE_ACCOUNT_NAME/RESOURCE_TOKEN, and no
        # mocked _run_az: this must fail on the pure environment-variable
        # check before ever attempting an Azure CLI call (including the
        # AZURE_SUBSCRIPTION_ID fallback), so the test never depends on a
        # live `az` invocation.
        with patch.object(setup, "_run_az") as run_az:
            with self.assertRaises(setup.PanelRbacError):
                setup.configure_panel_rbac({"APPLICATION_MODE": "workflow"})
        run_az.assert_not_called()

    def test_falls_back_to_az_account_show_when_subscription_id_unset(self) -> None:
        environment = {
            key: value
            for key, value in ENVIRONMENT_BASE.items()
            if key != "AZURE_SUBSCRIPTION_ID"
        }

        with patch.object(
            setup, "_run_az", return_value="22222222-2222-2222-2222-222222222222"
        ) as run_az:
            subscription_id = setup.resolve_subscription_id(environment)

        self.assertEqual(subscription_id, "22222222-2222-2222-2222-222222222222")
        run_az.assert_called_once_with(
            ["account", "show", "--query", "id", "--output", "tsv"]
        )

    def test_creates_one_frontend_metadata_assignment_when_none_exist(self) -> None:
        environment = {**ENVIRONMENT_BASE, "APPLICATION_MODE": "both"}

        def fake_run_az(arguments, required=True):
            if arguments[:2] == ["containerapp", "show"]:
                name = arguments[arguments.index("--name") + 1]
                return f"11111111-0000-0000-0000-0000000000{'01' if 'frontend' in name else '02'}"
            if arguments[:4] == ["cosmosdb", "sql", "role", "assignment"] and (
                arguments[4] == "list"
            ):
                return json.dumps([])
            if arguments[:4] == ["cosmosdb", "sql", "role", "assignment"] and (
                arguments[4] == "create"
            ):
                return ""
            raise AssertionError(f"Unexpected az invocation: {arguments}")

        with patch.object(setup, "_run_az", side_effect=fake_run_az) as run_az:
            created = setup.configure_panel_rbac(environment)

        self.assertEqual(created, 1)
        create_calls = [
            call
            for call in run_az.call_args_list
            if call.args[0][:4] == ["cosmosdb", "sql", "role", "assignment"]
            and call.args[0][4] == "create"
        ]
        self.assertEqual(len(create_calls), 1)
        # Every create call's --scope must reference exactly one container,
        # never the bare account root.
        for call in create_calls:
            arguments = call.args[0]
            scope = arguments[arguments.index("--scope") + 1]
            self.assertIn("/dbs/", scope)
            self.assertIn("/colls/", scope)

    def test_skips_already_existing_assignment(self) -> None:
        environment = {**ENVIRONMENT_BASE, "APPLICATION_MODE": "workflow"}
        frontend_principal = "11111111-0000-0000-0000-000000000001"

        def fake_run_az(arguments, required=True):
            if arguments[:2] == ["containerapp", "show"]:
                name = arguments[arguments.index("--name") + 1]
                return (
                    frontend_principal
                    if "frontend" in name
                    else "11111111-0000-0000-0000-000000000002"
                )
            if arguments[:4] == ["cosmosdb", "sql", "role", "assignment"] and (
                arguments[4] == "list"
            ):
                scope = setup.container_scope_path(
                    ENVIRONMENT_BASE["AZURE_SUBSCRIPTION_ID"],
                    ENVIRONMENT_BASE["AZURE_RESOURCE_GROUP"],
                    ENVIRONMENT_BASE["DATABASE_ACCOUNT_NAME"],
                    ENVIRONMENT_BASE["DATABASE_NAME"],
                    setup.panel_container_grants()[0].container_name,
                )
                return json.dumps(
                    [{"principalId": frontend_principal, "scope": scope}]
                )
            if arguments[:4] == ["cosmosdb", "sql", "role", "assignment"] and (
                arguments[4] == "create"
            ):
                return ""
            raise AssertionError(f"Unexpected az invocation: {arguments}")

        with patch.object(setup, "_run_az", side_effect=fake_run_az) as run_az:
            created = setup.configure_panel_rbac(environment)

        # The only selected grant already exists; no duplicate or wider grant.
        self.assertEqual(created, 0)
        create_calls = [
            call
            for call in run_az.call_args_list
            if call.args[0][:4] == ["cosmosdb", "sql", "role", "assignment"]
            and call.args[0][4] == "create"
        ]
        self.assertEqual(len(create_calls), 0)


if __name__ == "__main__":
    unittest.main()
