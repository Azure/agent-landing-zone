import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from azure.core.exceptions import ResourceNotFoundError

from config.governance import setup


REPO_ROOT = Path(__file__).resolve().parents[3]
LOGICAL_CONTRACT_HASH = (
    "825db8ef40a81e2c19e5d80d37c565b6b47fc9a6540e9881d35cc12b8fde5aab"
)
WIRE_CONTRACT_HASH = (
    "066c8f5408610ab839d5121d06ca5bc59e8797e551d5c47c875c5ba52f7e0588"
)


class GovernanceSetupTests(TestCase):
    def test_defaults_keep_audit_and_provenance_disabled(self):
        self.assertEqual(setup.DEFAULT_SETTINGS["AUDIT_EVENTS_ENABLED"], "false")
        self.assertEqual(
            setup.DEFAULT_SETTINGS["AUDIT_SENSITIVE_CONTENT_ENABLED"], "false"
        )
        self.assertEqual(
            setup.DEFAULT_SETTINGS["INGESTION_PROVENANCE_ENABLED"], "false"
        )
        self.assertEqual(
            setup.DEFAULT_SETTINGS["INGESTION_REQUIRE_GOVERNANCE_METADATA"],
            "false",
        )
        self.assertEqual(
            setup.DEFAULT_SETTINGS["INGESTION_DEFAULT_CLASSIFICATION"],
            "unclassified",
        )
        self.assertEqual(
            setup.DEFAULT_SETTINGS["INGESTION_DEFAULT_RIGHT_TO_USE"],
            "not_asserted",
        )

    def test_generated_key_contains_exactly_256_random_bits(self):
        with patch.object(setup.secrets, "token_bytes", return_value=b"x" * 32) as token:
            encoded = setup.generate_audit_hmac_key()

        token.assert_called_once_with(32)
        decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        self.assertEqual(decoded, b"x" * 32)

    def test_vault_uri_uses_azd_key_vault_name_output(self):
        self.assertEqual(
            setup.resolve_vault_uri({"KEY_VAULT_NAME": "kv-example"}),
            "https://kv-example.vault.azure.net/",
        )

    def test_existing_valid_key_is_reused_without_rotation(self):
        secret_client = Mock()
        secret_client.get_secret.return_value = SimpleNamespace(value="ab" * 32)

        created = setup.ensure_audit_hmac_secret(secret_client)

        self.assertFalse(created)
        secret_client.set_secret.assert_not_called()

    def test_missing_key_is_created_without_returning_or_logging_its_value(self):
        secret_client = Mock()
        secret_client.get_secret.side_effect = ResourceNotFoundError("missing")

        created = setup.ensure_audit_hmac_secret(secret_client)

        self.assertTrue(created)
        secret_client.set_secret.assert_called_once()
        name, value = secret_client.set_secret.call_args.args
        self.assertEqual(name, setup.AUDIT_HMAC_SECRET_NAME)
        self.assertEqual(len(base64.urlsafe_b64decode(value + "=")), 32)

    def test_invalid_existing_key_fails_instead_of_rotating_silently(self):
        secret_client = Mock()
        secret_client.get_secret.return_value = SimpleNamespace(value="too-short")

        with self.assertRaisesRegex(ValueError, "exactly 32 bytes"):
            setup.ensure_audit_hmac_secret(secret_client)

        secret_client.set_secret.assert_not_called()

    def test_app_configuration_contains_defaults_and_only_a_key_vault_reference(self):
        app_config_client = Mock()
        app_config_client.get_configuration_setting.side_effect = ResourceNotFoundError(
            "missing"
        )
        secret_client = Mock()
        secret_client.get_secret.return_value = SimpleNamespace(value="ab" * 32)
        vault_uri = "https://kv-example.vault.azure.net/"

        setup.apply_governance_configuration(
            app_config_client,
            secret_client,
            vault_uri,
        )

        settings = {
            call.args[0].key: call.args[0]
            for call in app_config_client.set_configuration_setting.call_args_list
        }
        self.assertEqual(set(settings), {*setup.DEFAULT_SETTINGS, "AUDIT_HMAC_KEY"})
        reference = settings["AUDIT_HMAC_KEY"]
        self.assertEqual(
            reference.content_type,
            setup.KEY_VAULT_REFERENCE_CONTENT_TYPE,
        )
        self.assertEqual(
            reference.value,
            '{"uri":"https://kv-example.vault.azure.net/secrets/AUDIT-HMAC-KEY"}',
        )
        self.assertNotIn("ab" * 32, reference.value)

    def test_existing_operator_key_vault_reference_is_preserved(self):
        app_config_client = Mock()
        operator_reference = SimpleNamespace(
            key="AUDIT_HMAC_KEY",
            value='{"uri":"https://operator-kv.vault.azure.net/secrets/audit-key"}',
            content_type=setup.KEY_VAULT_REFERENCE_CONTENT_TYPE,
        )

        def get_setting(*, key, label):
            if key == "AUDIT_HMAC_KEY":
                return operator_reference
            raise ResourceNotFoundError("missing")

        app_config_client.get_configuration_setting.side_effect = get_setting
        secret_client = Mock()

        created = setup.apply_governance_configuration(
            app_config_client,
            secret_client,
            "https://platform-kv.vault.azure.net/",
        )

        self.assertFalse(created)
        secret_client.get_secret.assert_not_called()
        written_keys = {
            call.args[0].key
            for call in app_config_client.set_configuration_setting.call_args_list
        }
        self.assertNotIn("AUDIT_HMAC_KEY", written_keys)

    def test_plaintext_operator_key_is_migrated_without_rotation(self):
        plaintext_key = "cd" * 32
        app_config_client = Mock()

        def get_setting(*, key, label):
            if key == "AUDIT_HMAC_KEY":
                return SimpleNamespace(
                    key=key,
                    value=plaintext_key,
                    content_type="text/plain",
                )
            raise ResourceNotFoundError("missing")

        app_config_client.get_configuration_setting.side_effect = get_setting
        secret_client = Mock()
        secret_client.get_secret.side_effect = ResourceNotFoundError("missing")

        setup.apply_governance_configuration(
            app_config_client,
            secret_client,
            "https://platform-kv.vault.azure.net/",
        )

        self.assertEqual(secret_client.set_secret.call_args.args[1], plaintext_key)
        written = {
            call.args[0].key: call.args[0]
            for call in app_config_client.set_configuration_setting.call_args_list
        }
        self.assertEqual(
            written["AUDIT_HMAC_KEY"].content_type,
            setup.KEY_VAULT_REFERENCE_CONTENT_TYPE,
        )

    def test_key_vault_disabled_rejects_enabled_audit_setting(self):
        app_config_client = Mock()

        def get_setting(*, key, label):
            if key == "AUDIT_EVENTS_ENABLED":
                return SimpleNamespace(value="true")
            raise ResourceNotFoundError("missing")

        app_config_client.get_configuration_setting.side_effect = get_setting
        with patch.object(
            setup,
            "load_setup_settings",
            return_value={
                "APP_RUNTIME_CONFIGURATION_MODE": "appConfig",
                "APP_CONFIG_ENDPOINT": "https://config.azconfig.io",
                "DEPLOY_KEY_VAULT": "false",
            },
        ), patch.object(
            setup,
            "AzureAppConfigurationClient",
            return_value=app_config_client,
        ), patch.dict(
            setup.os.environ,
            {
                "APP_CONFIG_ENDPOINT": "https://config.azconfig.io",
                "DEPLOY_KEY_VAULT": "false",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "Key Vault is disabled"):
                setup.main()

    def test_existing_operator_settings_are_preserved_without_explicit_override(self):
        app_config_client = Mock()

        setup.seed_governance_settings(app_config_client)

        app_config_client.get_configuration_setting.assert_called()
        app_config_client.set_configuration_setting.assert_not_called()

    def test_explicit_environment_override_updates_existing_setting(self):
        app_config_client = Mock()

        setup.seed_governance_settings(
            app_config_client,
            {"AUDIT_EVENTS_ENABLED": "true"},
        )

        written = [
            call.args[0]
            for call in app_config_client.set_configuration_setting.call_args_list
        ]
        self.assertEqual(
            [(setting.key, setting.value) for setting in written],
            [("AUDIT_EVENTS_ENABLED", "true")],
        )

    def test_shared_contract_files_match_v3_8_0_hashes(self):
        logical = REPO_ROOT / "contracts" / "audit-event-v1.schema.json"
        wire = (
            REPO_ROOT
            / "contracts"
            / "audit-event-v1.application-insights.schema.json"
        )

        self.assertEqual(hashlib.sha256(logical.read_bytes()).hexdigest(), LOGICAL_CONTRACT_HASH)
        self.assertEqual(hashlib.sha256(wire.read_bytes()).hexdigest(), WIRE_CONTRACT_HASH)

    def test_deployment_surfaces_never_publish_the_secret_as_plaintext(self):
        parameters = json.loads(
            (REPO_ROOT / "main.parameters.json").read_text(encoding="utf-8")
        )
        serialized_parameters = json.dumps(parameters)
        self.assertNotIn("AUDIT_HMAC_KEY", serialized_parameters)

        for script_name in ("postProvision.ps1", "postProvision.sh"):
            script = (REPO_ROOT / "scripts" / script_name).read_text(encoding="utf-8")
            self.assertIn("config.governance.setup", script)

    def test_rollback_contract_pins_validated_governance_component_pair(self):
        rollback = json.loads(
            (REPO_ROOT / "tests" / "fixtures" / "historical-runtime-rollback.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(rollback["umbrella"]["tag"], "v3.7.0")
        self.assertEqual(
            rollback["components"]["gpt-rag-orchestrator"],
            "v3.8.0",
        )
        self.assertEqual(
            rollback["components"]["gpt-rag-ingestion"],
            "v2.5.0",
        )
