import io
import json
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from config.deployment import existing_images
from config.deployment.existing_images import (
    PLACEHOLDER_IMAGE,
    apply_existing_images,
    definition_placeholder_plan,
    parse_container_app_images,
    placeholder_plan,
)


def test_parse_skips_placeholder_foreign_env_and_untagged():
    payload = [
        {"tags": {"azd-service-name": "frontend", "azd-env-name": "e1"},
         "image": "cr.azurecr.io/agent-app-ui:abc"},
        {"tags": {"azd-service-name": "dataingest", "azd-env-name": "e1"},
         "image": "mcr.microsoft.com/dotnet/samples:aspnetapp"},
        {"tags": {"azd-service-name": "orchestrator", "azd-env-name": "other"},
         "image": "cr.azurecr.io/orch:1"},
        {"tags": {}, "image": "cr.azurecr.io/x:1"},
        "garbage",
    ]
    assert parse_container_app_images(payload, "e1") == {
        "frontend": "cr.azurecr.io/agent-app-ui:abc"
    }
    assert parse_container_app_images({"not": "a list"}) == {}


def test_apply_sets_only_missing_images():
    apps = [
        {"service_name": "frontend"},
        {"service_name": "dataingest", "image": "explicit:1"},
        {"service_name": "orchestrator"},
    ]
    updated = apply_existing_images(
        apps, {"frontend": "ui:2", "dataingest": "ing:2"}
    )
    assert updated == ["frontend"]
    assert apps[0]["image"] == "ui:2"
    assert apps[1]["image"] == "explicit:1"
    assert "image" not in apps[2]


def test_apply_touches_only_selected_services():
    apps = [{"service_name": "frontend"}, {"service_name": "dataingest"}]
    updated = apply_existing_images(
        apps, {"frontend": "ui:2", "dataingest": "ing:2"}, selected=["dataingest"]
    )
    assert updated == ["dataingest"]
    assert "image" not in apps[0]


def test_placeholder_path_accepts_only_components_passed_in():
    images = {"ui": "ui:3", "stray": "stray:1", "agent": "agent:1"}
    plan = placeholder_plan(
        [
            {"name": "ui", "kind": "containerapp"},
            {"name": "worker", "kind": "containerapp"},
            {"name": "agent", "kind": "azure.ai.agent"},
        ],
        images,
    )
    assert plan == {"ui": "ui:3", "worker": PLACEHOLDER_IMAGE}
    assert placeholder_plan([], images) == {}


def test_definition_plan_uses_effective_containerapp_components_and_service_tags():
    # Images are discovered by azd-service-name; the bundled ui/ingestion map
    # to frontend/dataingest. A hosted orchestrator gets no Container App.
    images = {"frontend": "cr.azurecr.io/ui:1", "orchestrator": "cr.azurecr.io/orch:1"}
    classic = definition_placeholder_plan(
        {"ORCHESTRATION_HOST": "container_apps", "DEPLOY_INGESTION_CONTAINER_APP": "true", "AGENTLZ_APP_DEFINITION": ""}, images
    )
    assert classic == {
        "ui": "cr.azurecr.io/ui:1",
        "orchestrator": "cr.azurecr.io/orch:1",
        "ingestion": PLACEHOLDER_IMAGE,
    }
    hosted = definition_placeholder_plan(
        {"ORCHESTRATION_HOST": "hosted", "DEPLOY_INGESTION_CONTAINER_APP": "true", "AGENTLZ_APP_DEFINITION": ""}, images
    )
    assert hosted == {"ui": "cr.azurecr.io/ui:1", "ingestion": PLACEHOLDER_IMAGE}


def test_cli_reports_plan_and_fails_closed_on_invalid_definition(tmp_path, caplog):
    environment = {"ORCHESTRATION_HOST": "container_apps", "DEPLOY_INGESTION_CONTAINER_APP": "true", "AZURE_RESOURCE_GROUP": "rg", "AGENTLZ_APP_DEFINITION": ""}
    stdout = io.StringIO()
    with patch.dict("os.environ", environment), patch.object(
        existing_images, "discover_existing_images", return_value={"dataingest": "cr.azurecr.io/ing:2"}
    ) as discover, redirect_stdout(stdout), redirect_stderr(io.StringIO()):
        assert existing_images.main(["--json"]) == 0
    discover.assert_called_once_with("rg", None, None)
    assert json.loads(stdout.getvalue())["ingestion"] == "cr.azurecr.io/ing:2"

    missing = tmp_path / "missing.json"
    with patch.dict("os.environ", {**environment, "AGENTLZ_APP_DEFINITION": str(missing)}), patch.object(
        existing_images, "discover_existing_images", return_value={}
    ), redirect_stderr(io.StringIO()):
        assert existing_images.main([]) == 1
    assert "does not exist" in caplog.text
