"""Registry setup uses verified mappings, including when a store is present."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from config.containerapps import setup


@pytest.mark.parametrize("mode", ["containerEnv", "none", "appConfig"])
def test_selected_apps_are_actually_configured_without_store_discovery(mode):
    identity = {"kind": "userAssigned", "principalId": "principal",
                "clientId": "client", "resourceId": "/selected/uai"}
    settings = {
        "APP_RUNTIME_CONFIGURATION_MODE": mode,
        "APP_CONFIG_ENDPOINT": "https://unused.azconfig.io",
        "SUBSCRIPTION_ID": "subscription",
        "AZURE_RESOURCE_GROUP": "group",
        "CONTAINER_REGISTRY_NAME": "registry",
        "AZURE_CONTAINER_REGISTRY_ENDPOINT": "registry.azurecr.io",
        "USE_UAI": True,
        "CONTAINER_APPS": [{"name": "mapped-worker", "identity": identity}],
    }
    with (
        patch.object(setup, "load_setup_settings", return_value=settings, create=True),
        patch.object(setup, "get_credentials", return_value="credential"),
        patch.object(setup, "AzureAppConfigurationClient") as store,
        patch.object(setup, "update_single_container_app",
                     return_value=("mapped-worker", True, "ok")) as update,
    ):
        setup.main()
    store.assert_not_called()
    update.assert_called_once_with(
        "subscription", "group", "mapped-worker", "registry.azurecr.io", True, "credential",
        expected_identity=identity,
    )


def test_multiple_attached_identities_are_not_arbitrarily_selected():
    app = SimpleNamespace(identity=SimpleNamespace(
        user_assigned_identities={"/one": {}, "/two": {}},
    ))
    with pytest.raises(ValueError, match="exactly one"):
        setup._get_desired_identity(app, "worker", True)


def test_selected_app_failure_propagates():
    with (
        patch.object(setup, "load_setup_settings", return_value={
            "SUBSCRIPTION_ID": "sub", "AZURE_RESOURCE_GROUP": "group",
            "CONTAINER_REGISTRY_NAME": "registry", "USE_UAI": False,
            "AZURE_CONTAINER_REGISTRY_ENDPOINT": "registry.azurecr.io",
            "CONTAINER_APPS": [{"name": "worker"}],
        }, create=True),
        patch.object(setup, "get_credentials"),
        patch.object(setup, "update_single_container_app",
                     return_value=("worker", False, "denied")),
        pytest.raises(RuntimeError, match="failed"),
    ):
        setup.main()


def test_changed_principal_is_rejected_before_registry_write():
    client = SimpleNamespace(container_apps=Mock())
    client.container_apps.get.return_value = SimpleNamespace(
        provisioning_state="Succeeded",
        identity=SimpleNamespace(principal_id="changed-principal"),
    )
    with patch.object(setup, "ContainerAppsAPIClient", return_value=client):
        _, success, detail = setup.update_single_container_app(
            "sub", "group", "worker", "registry.azurecr.io", False, "credential",
            expected_identity={"kind": "systemAssigned", "principalId": "verified-principal"},
        )
    assert not success
    assert "conflicts with verified mapping" in detail
    client.container_apps.begin_create_or_update.assert_not_called()


def test_empty_apps_need_no_registry_identity_options_or_credentials():
    with (
        patch.object(setup, "load_setup_settings", return_value={"CONTAINER_APPS": []}),
        patch.object(setup, "get_credentials") as credential,
        patch.object(setup, "update_single_container_app") as update,
    ):
        setup.main()
    credential.assert_not_called()
    update.assert_not_called()


def test_selected_apps_without_registry_fail_before_mutation():
    with (
        patch.object(setup, "load_setup_settings", return_value={
            "SUBSCRIPTION_ID": "sub", "AZURE_RESOURCE_GROUP": "group",
            "USE_UAI": "false", "CONTAINER_APPS": [{"name": "worker"}],
        }),
        patch.object(setup, "get_credentials"),
        patch.object(setup, "update_single_container_app") as update,
        pytest.raises(RuntimeError, match="registry endpoint"),
    ):
        setup.main()
    update.assert_not_called()
