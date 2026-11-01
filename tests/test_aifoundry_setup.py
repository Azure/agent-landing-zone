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


if __name__ == "__main__":
    unittest.main()
