"""Provider-aware ownership classification must never pre-create TF groups."""

import json
from unittest.mock import patch

import pytest

from config.deployment import resource_groups as groups
from config.deployment.terraform_groups import prepare_groups


SUBSCRIPTION = "11111111-1111-1111-1111-111111111111"
ENVIRONMENT = {
    "AZURE_ENV_NAME": "fixture",
    "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION,
    "AZURE_RESOURCE_GROUP": "rg-fixture",
    "AZURE_APP_RESOURCE_GROUP": "rg-fixture-app",
    "AZURE_NETWORK_RESOURCE_GROUP": "rg-fixture-network",
    "AZURE_LOCATION": "swedencentral",
    "CREATE_RESOURCE_GROUPS": "true",
}


def setup_environment(tmp_path):
    azure = tmp_path / ".azure"
    (azure / "fixture").mkdir(parents=True)
    (azure / "fixture/.env").write_text("AZURE_ENV_NAME=fixture\n")
    return azure


def test_fresh_groups_are_owned_existing_destinations_stay_byo_and_retry_is_sticky(tmp_path):
    azure = setup_environment(tmp_path)
    with (
        patch.object(groups, "initialize_defaults", return_value=ENVIRONMENT),
        patch.object(groups, "_exists", side_effect=lambda name, sub: name == "rg-fixture"),
        patch.object(groups, "_legacy_deployed", return_value=False),
        patch.object(groups, "_run_az", side_effect=AssertionError("No Azure write is allowed")),
    ):
        result = prepare_groups(ENVIRONMENT, azure, "fixture")
    path = result["ownershipFile"]
    assert json.loads(open(path, encoding="utf-8").read()) == {
        "managedResourceGroupNames": ["rg-fixture-app", "rg-fixture-network"],
    }
    assert groups.read_binding(azure, "fixture").foundry == "rg-fixture"
    # After apply these groups exist; do not reclassify them as BYO on reprovision.
    with (
        patch.object(groups, "initialize_defaults", return_value=ENVIRONMENT),
        patch.object(groups, "_exists", return_value=True),
        patch.object(groups, "_legacy_deployed", side_effect=AssertionError("No reclassification")),
    ):
        assert prepare_groups(ENVIRONMENT, azure, "fixture")["ownershipFile"] == path
    assert json.loads(open(path, encoding="utf-8").read())["managedResourceGroupNames"] == [
        "rg-fixture-app", "rg-fixture-network",
    ]


def test_missing_byo_groups_without_authorization_fail_without_persisting_ownership(tmp_path):
    azure = setup_environment(tmp_path)
    environment = {**ENVIRONMENT, "CREATE_RESOURCE_GROUPS": "false"}
    with (
        patch.object(groups, "initialize_defaults", return_value=environment),
        patch.object(groups, "_exists", return_value=False),
        patch.object(groups, "_legacy_deployed", return_value=False),
        pytest.raises(ValueError, match="CREATE_RESOURCE_GROUPS"),
    ):
        prepare_groups(environment, azure, "fixture")
    assert not (azure / "fixture/terraform-resource-groups.json").exists()


def test_bound_environment_without_tf_ownership_cannot_switch_providers(tmp_path):
    azure = setup_environment(tmp_path)
    selection = groups.resolve_resource_groups(ENVIRONMENT)
    groups._save_binding(azure, "fixture", selection)
    with (
        patch.object(groups, "initialize_defaults", return_value=ENVIRONMENT),
        pytest.raises(ValueError, match="ownership"),
    ):
        prepare_groups(ENVIRONMENT, azure, "fixture")


def test_classification_lookup_failure_never_claims_an_existing_group(tmp_path):
    azure = setup_environment(tmp_path)
    with (
        patch.object(groups, "initialize_defaults", return_value=ENVIRONMENT),
        patch.object(groups, "_exists", side_effect=groups.ResourceGroupError("Cannot verify destination")),
        pytest.raises(ValueError, match="Cannot verify"),
    ):
        prepare_groups(ENVIRONMENT, azure, "fixture")
    assert not (azure / "fixture/terraform-resource-groups.json").exists()
