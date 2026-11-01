"""Custom image-passthrough services must use their attached registry identity."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from config.containerapps import setup

ENV = {
    "AZURE_SUBSCRIPTION_ID": "subscription",
    "AZURE_RESOURCE_GROUP": "group",
    "AZURE_CONTAINER_REGISTRY_ENDPOINT": "platform.azurecr.io",
}
IMAGE = "platform.azurecr.io/custom/worker@sha256:" + "a" * 64


def app(name="actual-worker", service="worker", identities=None, principal=None):
    return SimpleNamespace(
        name=name, tags={"azd-service-name": service},
        identity=SimpleNamespace(
            user_assigned_identities=identities, principal_id=principal,
        ),
    )


def test_custom_registry_resolves_arbitrary_service_and_reuses_update():
    from config.containerapps.registry import configure_service_registry

    client = SimpleNamespace(container_apps=SimpleNamespace(
        list_by_resource_group=lambda group: [
            app(service="frontend"), app(identities={"/existing/uai": object()}),
        ],
    ))
    with patch.object(setup, "get_credentials", return_value="credential"), \
            patch.object(setup, "ContainerAppsAPIClient", return_value=client), \
            patch.object(setup, "update_single_container_app",
                         return_value=("actual-worker", True, "Success")) as update:
        configure_service_registry("worker", IMAGE, ENV)
    update.assert_called_once_with(
        "subscription", "group", "actual-worker", "platform.azurecr.io", "true", "credential",
        preserve_other_registries=True,
    )


@pytest.mark.parametrize("apps", [
    [], [app(), app()],
    [app(identities={})],
    [app(identities={"/one": object(), "/two": object()})],
    [app(identities={"/one": object()}, principal="system-principal")],
])
def test_custom_registry_rejects_missing_or_ambiguous_app_identity(apps):
    from config.containerapps.registry import configure_service_registry

    client = SimpleNamespace(container_apps=SimpleNamespace(list_by_resource_group=lambda group: apps))
    with patch.object(setup, "get_credentials"), \
            patch.object(setup, "ContainerAppsAPIClient", return_value=client), \
            patch.object(setup, "update_single_container_app") as update:
        with pytest.raises(RuntimeError, match="exactly one"):
            configure_service_registry("worker", IMAGE, ENV)
    update.assert_not_called()


def test_custom_registry_supports_existing_system_identity_and_propagates_failure():
    from config.containerapps.registry import configure_service_registry

    client = SimpleNamespace(container_apps=SimpleNamespace(
        list_by_resource_group=lambda group: [app(principal="existing-system")],
    ))
    with patch.object(setup, "get_credentials"), \
            patch.object(setup, "ContainerAppsAPIClient", return_value=client), \
            patch.object(setup, "update_single_container_app",
                         return_value=("actual-worker", False, "assignment denied")) as update:
        with pytest.raises(RuntimeError, match="assignment denied"):
            configure_service_registry("worker", IMAGE, ENV)
    assert update.call_args.args[4] == "false"


@pytest.mark.parametrize("image", [None, "external.azurecr.io/custom@sha256:" + "b" * 64])
def test_normal_azd_build_and_external_image_do_not_change_platform_registry(image):
    from config.containerapps.registry import configure_service_registry

    with patch.object(setup, "get_credentials") as credential:
        configure_service_registry("worker", image, ENV)
    credential.assert_not_called()


@pytest.mark.parametrize("preserve", [False, True])
def test_existing_registry_update_preserves_bundled_default_and_custom_other_registries(preserve):
    other = {"server": "other.azurecr.io", "identity": "/other/uai"}
    current = app(identities={"/existing/uai": object()})
    current.provisioning_state = "Succeeded"
    current.configuration = SimpleNamespace(registries=[
        other, {"server": "platform.azurecr.io", "identity": "/stale/uai"},
    ])
    poller = SimpleNamespace(result=lambda timeout: SimpleNamespace(provisioning_state="Succeeded"))
    client = SimpleNamespace(container_apps=SimpleNamespace(
        get=lambda group, name: current,
        begin_create_or_update=lambda group, name, payload: poller,
    ))
    with patch.object(setup, "ContainerAppsAPIClient", return_value=client):
        args = {"preserve_other_registries": True} if preserve else {}
        _, success, _ = setup.update_single_container_app(
            "subscription", "group", current.name, "platform.azurecr.io", "true", "credential", **args,
        )
    assert success
    desired = {"server": "platform.azurecr.io", "identity": "/existing/uai"}
    assert current.configuration.registries == ([other, desired] if preserve else [desired])


def test_registry_update_is_idempotent_for_existing_managed_identity():
    current = app(identities={"/existing/uai": object()})
    current.provisioning_state = "Succeeded"
    current.configuration = SimpleNamespace(registries=[
        {"server": "platform.azurecr.io", "identity": "/existing/uai"},
    ])
    with patch.object(setup, "ContainerAppsAPIClient") as factory:
        factory.return_value.container_apps.get.return_value = current
        assert setup.update_single_container_app(
            "subscription", "group", current.name, "platform.azurecr.io", "true", "credential",
            preserve_other_registries=True,
        )[1]
        factory.return_value.container_apps.begin_create_or_update.assert_not_called()


def test_custom_registry_discovery_denial_is_actionable_and_does_not_update():
    from azure.core.exceptions import HttpResponseError
    from config.containerapps.registry import configure_service_registry

    with patch.object(setup, "get_credentials"), \
            patch.object(setup, "ContainerAppsAPIClient") as factory, \
            patch.object(setup, "update_single_container_app") as update:
        factory.return_value.container_apps.list_by_resource_group.side_effect = HttpResponseError("access denied")
        with pytest.raises(RuntimeError, match="Cannot discover.*worker.*access denied"):
            configure_service_registry("worker", IMAGE, ENV)
    update.assert_not_called()


@pytest.mark.parametrize("missing", ["AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP"])
def test_custom_registry_missing_target_stops_before_authentication(missing):
    from config.containerapps.registry import configure_service_registry

    with patch.object(setup, "get_credentials") as credential:
        with pytest.raises(ValueError, match="requires"):
            configure_service_registry("worker", IMAGE, {**ENV, missing: ""})
    credential.assert_not_called()
