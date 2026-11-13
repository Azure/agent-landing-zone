"""Panel RBAC resolves published database names without widening its grants."""

import unittest
from unittest.mock import patch

from config.panel import setup
from config.deployment import setup_settings


class PanelPublishedDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "ORCHESTRATION_HOST": "hosted",
            "APPLICATION_MODE": "both",
            "AZURE_RESOURCE_GROUP": "test-group",
            "RESOURCE_TOKEN": "testtoken",
            "AZURE_SUBSCRIPTION_ID": "test-subscription",
            "APP_CONFIG_ENDPOINT": "https://test-store.azconfig.io",
            "DATABASE_ACCOUNT_NAME": "test-account",
            "DATABASE_NAME": "test-database",
            "FRONTEND_APP_NAME": "mapped-frontend",
        }
        loader = patch.object(setup_settings, "load_setup_settings", side_effect=lambda env: dict(env))
        loader.start()
        self.addCleanup(loader.stop)

    def test_published_account_and_database_are_used_for_container_scopes(self):
        with (
            patch.object(setup, "_run_az") as az,
            patch.object(setup, "resolve_container_app_principal_id", return_value="ui") as principal,
            patch.object(setup, "ensure_cosmos_sql_role_assignment", return_value=True) as assign,
        ):
            self.assertEqual(setup.configure_panel_rbac(self.environment), 1)
        az.assert_not_called()
        principal.assert_called_once_with("test-group", "mapped-frontend")
        for call in assign.call_args_list:
            self.assertEqual(call.args[0], "test-account")
            self.assertIn("/dbs/test-database/colls/", call.args[-1])
            self.assertEqual(call.args[3], "ui")
            self.assertTrue(call.args[-1].endswith("/colls/native-ui-metadata"))

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
        self.environment.pop("DATABASE_ACCOUNT_NAME")
        with (
            patch.object(setup, "_run_az", return_value=""),
            patch.object(setup, "ensure_cosmos_sql_role_assignment") as assign,
            self.assertRaises(setup.PanelRbacError),
        ):
            setup.configure_panel_rbac(self.environment)
        assign.assert_not_called()

    def test_config_failure_propagates_without_role_changes(self):
        with (
            patch.object(setup_settings, "load_setup_settings", side_effect=setup.PanelRbacError("read failed")),
            patch.object(setup, "ensure_cosmos_sql_role_assignment") as assign,
            self.assertRaises(setup.PanelRbacError),
        ):
            setup.configure_panel_rbac(self.environment)
        assign.assert_not_called()


if __name__ == "__main__":
    unittest.main()
