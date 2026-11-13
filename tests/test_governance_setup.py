"""Store-free governance still provisions or reuses the selected vault key."""

from unittest.mock import Mock, patch

import pytest
from azure.core.exceptions import ResourceNotFoundError

from config.governance import setup


@pytest.mark.parametrize("mode", ["containerEnv", "none"])
@pytest.mark.parametrize("exists", [False, True])
def test_store_free_key_create_and_reuse(mode, exists):
    secret = Mock()
    if exists:
        secret.get_secret.return_value.value = setup.generate_audit_hmac_key()
    else:
        secret.get_secret.side_effect = ResourceNotFoundError()
    with (
        patch.object(setup, "load_setup_settings", return_value={
            "APP_RUNTIME_CONFIGURATION_MODE": mode,
            "APP_CONFIG_ENDPOINT": "https://unused.azconfig.io",
            "KEY_VAULT_URI": "https://vault.vault.azure.net/",
            "DEPLOY_KEY_VAULT": True,
        }, create=True),
        patch.object(setup, "create_credential"),
        patch.object(setup, "SecretClient", return_value=secret) as vault,
        patch.object(setup, "AzureAppConfigurationClient") as store,
    ):
        reference = setup.main()
    store.assert_not_called()
    assert vault.call_args.kwargs["vault_url"] == "https://vault.vault.azure.net/"
    assert secret.set_secret.call_count == int(not exists)
    assert reference == "https://vault.vault.azure.net/secrets/AUDIT-HMAC-KEY"


def test_enabled_audit_without_vault_fails_before_mutation():
    with (
        patch.object(setup, "load_setup_settings", return_value={
            "APP_RUNTIME_CONFIGURATION_MODE": "containerEnv",
            "DEPLOY_KEY_VAULT": False, "AUDIT_EVENTS_ENABLED": True,
        }, create=True),
        patch.object(setup, "SecretClient") as vault,
        pytest.raises(RuntimeError, match="Key Vault"),
    ):
        setup.main()
    vault.assert_not_called()


def test_unbound_uri_handoff_is_rejected_before_secret_access():
    with (
        patch.object(setup, "load_setup_settings", return_value={
            "APP_RUNTIME_CONFIGURATION_MODE": "containerEnv",
            "KEY_VAULT_URI": "https://vault.vault.azure.net/",
            "AUDIT_HMAC_KEY_URI": "https://other.vault.azure.net/secrets/AUDIT-HMAC-KEY",
        }),
        patch.object(setup, "create_credential"),
        patch.object(setup, "SecretClient") as vault,
        pytest.raises(RuntimeError, match="conflicts"),
    ):
        setup.main()
    vault.assert_not_called()


def test_denied_secret_access_propagates_without_publication_or_recreation():
    secret = Mock()
    secret.get_secret.side_effect = PermissionError("denied")
    with (
        patch.object(setup, "load_setup_settings", return_value={
            "APP_RUNTIME_CONFIGURATION_MODE": "containerEnv",
            "KEY_VAULT_URI": "https://vault.vault.azure.net/",
        }),
        patch.object(setup, "create_credential"),
        patch.object(setup, "SecretClient", return_value=secret),
        patch.object(setup, "AzureAppConfigurationClient") as store,
        pytest.raises(PermissionError, match="denied"),
    ):
        setup.main()
    secret.set_secret.assert_not_called()
    store.assert_not_called()
