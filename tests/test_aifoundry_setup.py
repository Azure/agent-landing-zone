"""Foundry evaluation keys respect account authentication and fail explicitly."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from config.aifoundry import setup


class FoundryEvaluationKeyTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.accounts.get.return_value = SimpleNamespace(
            properties=SimpleNamespace(disable_local_auth=False)
        )
        self.client.accounts.list_keys.return_value = SimpleNamespace(key1="test-key")
        self.vault_patch = patch.object(setup, "KeyVaultClient")
        self.vault = self.vault_patch.start()
        self.addCleanup(self.vault_patch.stop)

    def inject(self):
        return setup.add_ai_foundry_account_api_key_to_key_vault(
            self.client, "test-group", "test-foundry",
            "https://test-vault.vault.azure.net/", "evaluationsModelApiKey",
        )

    def test_disabled_local_auth_never_reads_or_stores_a_key(self):
        self.client.accounts.get.return_value.properties.disable_local_auth = True
        with self.assertLogs(level="INFO") as logs:
            self.assertFalse(self.inject())
        self.assertIn("Use Microsoft Entra ID", "\n".join(logs.output))
        self.client.accounts.list_keys.assert_not_called()
        self.vault.assert_not_called()

    def test_enabled_local_auth_preserves_key_injection(self):
        self.assertTrue(self.inject())
        self.client.accounts.get.assert_called_once_with("test-group", "test-foundry")
        self.client.accounts.list_keys.assert_called_once_with("test-group", "test-foundry")
        self.vault.return_value.set_secret.assert_called_once_with(
            "evaluationsModelApiKey", "test-key"
        )

    def test_read_and_write_failures_are_not_reported_as_success(self):
        for boundary in (
            self.client.accounts.get,
            self.client.accounts.list_keys,
            self.vault.return_value.set_secret,
        ):
            with self.subTest(boundary=boundary):
                boundary.side_effect = RuntimeError("boundary unavailable")
                with self.assertLogs(level="ERROR"), self.assertRaises(SystemExit) as error:
                    self.inject()
                self.assertEqual(error.exception.code, 1)
                boundary.side_effect = None

    def test_empty_key_is_rejected_before_vault_write(self):
        self.client.accounts.list_keys.return_value.key1 = ""
        with self.assertLogs(level="ERROR"), self.assertRaises(SystemExit):
            self.inject()
        self.vault.assert_not_called()

    def test_missing_vault_never_falls_back_to_store_discovery(self):
        with self.assertLogs(level="ERROR"), self.assertRaises(SystemExit):
            setup.add_ai_foundry_account_api_key_to_key_vault(
                self.client, "test-group", "test-foundry", None, "evaluationsModelApiKey",
            )
        self.client.accounts.list_keys.assert_not_called()
        self.vault.assert_not_called()

    def test_store_free_setup_performs_rai_and_evaluation_operations(self):
        settings = {
            "SUBSCRIPTION_ID": "sub", "AZURE_RESOURCE_GROUP": "group",
            "AI_FOUNDRY_ACCOUNT_NAME": "foundry",
            "KEY_VAULT_URI": "https://vault.vault.azure.net/",
            "MODEL_DEPLOYMENTS": [
                {"canonical_name": "GPT_MODEL", "name": "native-chat"},
                {"canonical_name": "CHAT_DEPLOYMENT_NAME", "name": "selected-chat"},
            ],
        }
        with (
            patch.object(setup, "load_setup_settings", return_value=settings),
            patch.object(setup, "get_azure_credential"),
            patch.object(setup, "CognitiveServicesManagementClient", return_value=self.client),
            patch.object(setup, "AzureAppConfigurationClient") as store,
            patch.object(setup, "configure_blocklist") as blocklist,
            patch.object(setup, "configure_policy", return_value="policy"),
            patch.object(setup, "associate_policy_to_deployment") as associate,
        ):
            setup.main()
        store.assert_not_called()
        blocklist.assert_called_once()
        associate.assert_called_once_with(self.client, "group", "foundry", "selected-chat", "policy")
        self.vault.return_value.set_secret.assert_called_once_with("evaluationsModelApiKey", "test-key")

    def test_disabled_foundry_needs_no_account_models_or_credentials(self):
        with (
            patch.object(setup, "load_setup_settings", return_value={"DEPLOY_AI_FOUNDRY": "false"}),
            patch.object(setup, "get_azure_credential") as credential,
            patch.object(setup, "CognitiveServicesManagementClient") as client,
            patch.object(setup, "configure_blocklist") as blocklist,
        ):
            setup.main()
        credential.assert_not_called()
        client.assert_not_called()
        blocklist.assert_not_called()
        self.vault.assert_not_called()

    def test_selected_foundry_without_account_does_not_report_success(self):
        with (
            patch.object(setup, "load_setup_settings", return_value={
                "DEPLOY_AI_FOUNDRY": "true", "SUBSCRIPTION_ID": "sub",
                "AZURE_RESOURCE_GROUP": "group",
            }),
            patch.object(setup, "get_azure_credential"),
            self.assertRaises(KeyError),
        ):
            setup.main()
        self.vault.assert_not_called()

    def test_native_fallback_chat_model_receives_selected_rai_policy(self):
        settings = {
            "DEPLOY_AI_FOUNDRY": "true", "SUBSCRIPTION_ID": "sub",
            "AZURE_RESOURCE_GROUP": "group", "AI_FOUNDRY_ACCOUNT_NAME": "foundry",
            "MODEL_DEPLOYMENTS": [
                {"canonical_name": "GPT_MODEL", "name": "gpt-5-nano"},
                {"canonical_name": "EMBEDDING_MODEL", "name": "text-embedding-3-large"},
            ],
        }
        self.client.accounts.get.return_value.properties.disable_local_auth = True
        with (
            patch.object(setup, "load_setup_settings", return_value=settings),
            patch.object(setup, "get_azure_credential"),
            patch.object(setup, "CognitiveServicesManagementClient", return_value=self.client),
            patch.object(setup, "configure_blocklist"),
            patch.object(setup, "configure_policy", return_value="policy"),
            patch.object(setup, "associate_policy_to_deployment") as associate,
        ):
            setup.main()
        associate.assert_called_once_with(self.client, "group", "foundry", "gpt-5-nano", "policy")
        self.client.accounts.list_keys.assert_not_called()
        self.vault.assert_not_called()

    def test_selected_foundry_does_not_guess_an_unrecognized_chat_mapping(self):
        with (
            patch.object(setup, "load_setup_settings", return_value={
                "DEPLOY_AI_FOUNDRY": "true", "SUBSCRIPTION_ID": "sub",
                "AZURE_RESOURCE_GROUP": "group", "AI_FOUNDRY_ACCOUNT_NAME": "foundry",
                "MODEL_DEPLOYMENTS": [{"canonical_name": "UNRELATED_MODEL", "name": "arbitrary"}],
            }),
            patch.object(setup, "get_azure_credential"),
            patch.object(setup, "CognitiveServicesManagementClient") as client,
            self.assertLogs(level="ERROR"), self.assertRaises(SystemExit),
        ):
            setup.main()
        client.assert_not_called()
        self.vault.assert_not_called()


if __name__ == "__main__":
    unittest.main()
