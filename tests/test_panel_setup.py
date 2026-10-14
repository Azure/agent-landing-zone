"""Panel RBAC resolves published database names without widening its grants."""

import unittest
from unittest.mock import patch

from config.panel import setup


class PanelPublishedDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "DEPLOY_ADMINISTRATIVE_PANEL": "true",
            "AZURE_RESOURCE_GROUP": "test-group",
            "RESOURCE_TOKEN": "testtoken",
            "AZURE_SUBSCRIPTION_ID": "test-subscription",
            "APP_CONFIG_ENDPOINT": "https://test-store.azconfig.io",
        }

    def test_published_account_and_database_are_used_for_container_scopes(self):
        with (
            patch.object(setup, "_run_az", side_effect=["test-account", "test-database"]) as az,
            patch.object(setup, "resolve_container_app_principal_id", side_effect=["ui", "ingestion"]),
            patch.object(setup, "ensure_cosmos_sql_role_assignment", return_value=True) as assign,
        ):
            self.assertEqual(setup.configure_panel_rbac(self.environment), 4)
        self.assertEqual([call.args[0][call.args[0].index("--key") + 1] for call in az.call_args_list],
                         ["DATABASE_ACCOUNT_NAME", "DATABASE_NAME"])
        for call in az.call_args_list:
            self.assertIn(setup.LABEL, call.args[0])
            self.assertIn("login", call.args[0])
        for call in assign.call_args_list:
            self.assertEqual(call.args[0], "test-account")
            self.assertIn("/dbs/test-database/colls/", call.args[-1])
            self.assertIn(call.args[3], ("ui", "ingestion"))

    def test_explicit_names_preserve_existing_behavior_without_config_read(self):
        self.environment.update(DATABASE_ACCOUNT_NAME="explicit-account", DATABASE_NAME="explicit-db")
        with (
            patch.object(setup, "_run_az") as az,
            patch.object(setup, "resolve_container_app_principal_id", return_value="test-identity"),
            patch.object(setup, "ensure_cosmos_sql_role_assignment", return_value=False),
        ):
            self.assertEqual(setup.configure_panel_rbac(self.environment), 0)
        az.assert_not_called()

    def test_empty_published_value_fails_before_any_role_change(self):
        with (
            patch.object(setup, "_run_az", return_value=""),
            patch.object(setup, "ensure_cosmos_sql_role_assignment") as assign,
            self.assertRaises(setup.PanelRbacError),
        ):
            setup.configure_panel_rbac(self.environment)
        assign.assert_not_called()

    def test_config_failure_propagates_without_role_changes(self):
        with (
            patch.object(setup, "_run_az", side_effect=setup.PanelRbacError("read failed")),
            patch.object(setup, "ensure_cosmos_sql_role_assignment") as assign,
            self.assertRaises(setup.PanelRbacError),
        ):
            setup.configure_panel_rbac(self.environment)
        assign.assert_not_called()


if __name__ == "__main__":
    unittest.main()
