"""Foundry evaluation keys respect account authentication and fail explicitly."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.mgmt.cognitiveservices.models import Deployment, DeploymentProperties, DeploymentModel, Sku

from config.aifoundry import setup


class FoundrySdkCompatibilityTests(unittest.TestCase):
    def test_blocklist_models_preserve_description_pattern_and_regex(self):
        sdk = CognitiveServicesManagementClient(Mock(), "subscription")
        self.addCleanup(sdk.close)
        with (
            patch.object(sdk.rai_blocklists, "create_or_update") as create,
            patch.object(sdk.rai_blocklist_items, "list", return_value=[
                SimpleNamespace(name="old-item"),
            ]),
            patch.object(sdk.rai_blocklist_items, "begin_delete") as delete,
            patch.object(sdk.rai_blocklist_items, "create_or_update") as create_item,
        ):
            delete.return_value.result.side_effect = lambda: create_item.assert_not_called()
            setup.configure_blocklist(sdk, "group", "account", {
                "description": "Blocked terms",
                "blocklistItems": [{"pattern": "blocked.*", "isRegex": True}],
            }, "blocklist")
        self.assertEqual(
            create.call_args.kwargs["rai_blocklist"].as_dict(),
            {"properties": {"description": "Blocked terms"}},
        )
        delete.assert_called_once_with(
            resource_group_name="group", account_name="account",
            rai_blocklist_name="blocklist", rai_blocklist_item_name="old-item",
        )
        delete.return_value.result.assert_called_once_with()
        self.assertEqual(
            create_item.call_args.kwargs["rai_blocklist_item"].as_dict(),
            {"properties": {"pattern": "blocked.*", "isRegex": True}},
        )

    def test_failed_item_deletion_stops_before_replacement(self):
        client = Mock()
        client.rai_blocklist_items.list.return_value = [SimpleNamespace(name="old-item")]
        client.rai_blocklist_items.begin_delete.return_value.result.side_effect = RuntimeError(
            "deletion failed"
        )
        with self.assertLogs(level="ERROR"), self.assertRaises(SystemExit) as error:
            setup.configure_blocklist(client, "group", "account", {
                "blocklistItems": [{"pattern": "replacement"}],
            }, "blocklist")
        self.assertEqual(error.exception.code, 1)
        client.rai_blocklist_items.create_or_update.assert_not_called()

    def test_policy_association_preserves_deployment_model_and_capacity(self):
        sdk = CognitiveServicesManagementClient(Mock(), "subscription")
        self.addCleanup(sdk.close)
        deployment = Deployment(
            sku=Sku(name="GlobalStandard", capacity=10),
            properties=DeploymentProperties(
                model=DeploymentModel(format="OpenAI", name="gpt-4", version="test-version"),
                rai_policy_name="old-policy",
            ),
        )
        with (
            patch.object(sdk.rai_policies, "create_or_update") as policy,
            patch.object(sdk.deployments, "get", return_value=deployment),
            patch.object(sdk.deployments, "begin_create_or_update") as update,
        ):
            name = setup.configure_policy(sdk, "group", "account", {
                "name": "policy",
                "properties": {
                    "mode": "blocking",
                    "promptBlocklists": [{"blocklistName": "blocklist", "blocking": True}],
                    "contentFilters": [{
                        "name": "Hate", "source": "prompt", "allowedContentLevel": "high",
                    }],
                },
            }, "blocklist", "policy")
            setup.associate_policy_to_deployment(sdk, "group", "account", "chat", name)
        self.assertEqual(policy.call_args.kwargs["rai_policy"]["properties"], {
            "mode": "Blocking",
            "customBlocklists": [{
                "blocklistName": "blocklist", "blocking": True, "source": "Prompt",
            }],
            "contentFilters": [{
                "name": "Hate", "source": "Prompt", "severityThreshold": "High",
            }],
        })
        expected = deployment.as_dict()
        expected["properties"]["raiPolicyName"] = "policy"
        update.assert_called_once_with(
            resource_group_name="group", account_name="account",
            deployment_name="chat", deployment=expected,
        )
        self.assertEqual(expected["sku"]["capacity"], 10)
        self.assertEqual(expected["properties"]["model"]["name"], "gpt-4")
        update.return_value.result.assert_called_once_with()


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
        with self.assertLogs(level="INFO") as logs:
            self.assertTrue(self.inject())
        self.client.accounts.get.assert_called_once_with("test-group", "test-foundry")
        self.client.accounts.list_keys.assert_called_once_with("test-group", "test-foundry")
        self.vault.return_value.set_secret.assert_called_once_with(
            "evaluationsModelApiKey", "test-key"
        )
        output = "\n".join(logs.output)
        self.assertIn("Evaluation API key stored in Key Vault", output)
        self.assertNotIn("test-key", output)

    def test_failure_messages_never_echo_the_key_value(self):
        self.vault.return_value.set_secret.side_effect = RuntimeError(
            "vault rejected value test-key for test-key"
        )
        with self.assertLogs(level="ERROR") as logs, self.assertRaises(SystemExit):
            self.inject()
        output = "\n".join(logs.output)
        self.assertNotIn("test-key", output)
        self.assertIn("vault rejected value [REDACTED] for [REDACTED]", output)

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

    def test_selected_foundry_with_local_models_enabled_still_fails_on_empty_deployments(self):
        for flag in ("true", "TRUE", None):
            with self.subTest(flag=flag):
                settings = {
                    "DEPLOY_AI_FOUNDRY": "true", "SUBSCRIPTION_ID": "sub",
                    "AZURE_RESOURCE_GROUP": "group", "AI_FOUNDRY_ACCOUNT_NAME": "foundry",
                    "MODEL_DEPLOYMENTS": [],
                }
                if flag is not None:
                    settings["DEPLOY_MODEL_DEPLOYMENTS"] = flag
                with (
                    patch.object(setup, "load_setup_settings", return_value=settings),
                    patch.object(setup, "get_azure_credential"),
                    patch.object(setup, "CognitiveServicesManagementClient") as client,
                    self.assertLogs(level="ERROR"), self.assertRaises(SystemExit) as error,
                ):
                    setup.main()
                self.assertEqual(error.exception.code, 1)
                client.assert_not_called()
                self.vault.assert_not_called()

    def test_external_gateway_mode_configures_account_rai_and_eval_key_without_local_deployment(self):
        for raw_flag in ("false", "FALSE"):
            for raw_deployments in ([], "[]"):
                with self.subTest(raw_flag=raw_flag, raw_deployments=raw_deployments):
                    self.client.reset_mock()
                    self.vault.reset_mock()
                    self.client.accounts.get.return_value = SimpleNamespace(
                        properties=SimpleNamespace(disable_local_auth=False)
                    )
                    settings = {
                        "DEPLOY_AI_FOUNDRY": "true",
                        "DEPLOY_MODEL_DEPLOYMENTS": raw_flag,
                        "SUBSCRIPTION_ID": "sub",
                        "AZURE_RESOURCE_GROUP": "group",
                        "AI_FOUNDRY_ACCOUNT_NAME": "foundry",
                        "KEY_VAULT_URI": "https://vault.vault.azure.net/",
                        "MODEL_DEPLOYMENTS": raw_deployments,
                    }
                    with (
                        patch.object(setup, "load_setup_settings", return_value=settings),
                        patch.object(setup, "get_azure_credential"),
                        patch.object(setup, "CognitiveServicesManagementClient", return_value=self.client),
                        patch.object(setup, "configure_blocklist") as blocklist,
                        patch.object(setup, "configure_policy", return_value="policy") as policy,
                        patch.object(setup, "associate_policy_to_deployment") as associate,
                        self.assertLogs(level="INFO") as logs,
                    ):
                        setup.main()
                    blocklist.assert_called_once()
                    policy.assert_called_once()
                    associate.assert_not_called()
                    self.vault.return_value.set_secret.assert_called_once_with(
                        "evaluationsModelApiKey", "test-key"
                    )
                    self.assertIn("DEPLOY_MODEL_DEPLOYMENTS=false", "\n".join(logs.output))

    def test_external_gateway_mode_entra_only_account_skips_key_injection(self):
        self.client.accounts.get.return_value.properties.disable_local_auth = True
        settings = {
            "DEPLOY_AI_FOUNDRY": "true",
            "DEPLOY_MODEL_DEPLOYMENTS": "false",
            "SUBSCRIPTION_ID": "sub",
            "AZURE_RESOURCE_GROUP": "group",
            "AI_FOUNDRY_ACCOUNT_NAME": "foundry",
            "MODEL_DEPLOYMENTS": [],
        }
        with (
            patch.object(setup, "load_setup_settings", return_value=settings),
            patch.object(setup, "get_azure_credential"),
            patch.object(setup, "CognitiveServicesManagementClient", return_value=self.client),
            patch.object(setup, "configure_blocklist") as blocklist,
            patch.object(setup, "configure_policy", return_value="policy") as policy,
            patch.object(setup, "associate_policy_to_deployment") as associate,
        ):
            setup.main()
        blocklist.assert_called_once()
        policy.assert_called_once()
        associate.assert_not_called()
        self.client.accounts.list_keys.assert_not_called()
        self.vault.assert_not_called()


if __name__ == "__main__":
    unittest.main()
