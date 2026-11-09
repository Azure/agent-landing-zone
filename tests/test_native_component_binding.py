"""Actual component source / published SDK gate; no copied parsers or cloud I/O.

Set AGENTLZ_NATIVE_RUNTIME_SOURCE and AGENTLZ_NATIVE_UI_SOURCE to the actual
component checkouts and run in their compatible published Durable SDK environment.
An unconfigured platform-only checkout skips this integration gate; supplying
either source makes both sources and the published SDK mandatory.
"""

import asyncio
import importlib
import json
import os
from importlib.metadata import distribution
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from config.deployment.native import scheduler_settings
from config.deployment.native_deploy import runtime_settings
from config.deployment.composition import compose_parameters


@pytest.fixture
def actual_components(monkeypatch):
    runtime_source = os.environ.get("AGENTLZ_NATIVE_RUNTIME_SOURCE")
    ui_source = os.environ.get("AGENTLZ_NATIVE_UI_SOURCE")
    if not runtime_source and not ui_source:
        pytest.skip("Cross-component gate requires the actual runtime/UI sources and published Durable SDK")
    assert runtime_source and ui_source, "Both actual component source paths are required"
    runtime_root, ui_root = Path(runtime_source).resolve(), Path(ui_source).resolve()
    for root in (runtime_root, ui_root):
        assert (root / "src").is_dir(), "Component source directory is missing"
        monkeypatch.syspath_prepend(str(root / "src"))
    # Platform collection already imports util; the runtime owns distinct submodules.
    utilities = importlib.import_module("util")
    monkeypatch.setattr(utilities, "__path__", [
        str(runtime_root / "src" / "util"), *utilities.__path__,
    ])
    for name, expected in (
        ("agent-framework-durabletask", "1.0.0b261029"),
        ("durabletask-azuremanaged", "1.12.0"),
    ):
        package = distribution(name)
        assert package.version == expected
        direct = package.read_text("direct_url.json")
        assert not direct or not json.loads(direct).get("dir_info", {}).get("editable")
    runtime = importlib.import_module("native.durable")
    contracts = importlib.import_module("native.contracts")
    ui = importlib.import_module("gpt_rag_ui.clients.native_durable")
    foundry_platform = importlib.import_module("util.foundry_platform")
    assert Path(foundry_platform.__file__).resolve() == runtime_root / "src/util/foundry_platform.py"
    assert Path(runtime.__file__).resolve() == runtime_root / "src/native/durable.py"
    assert Path(contracts.__file__).resolve() == runtime_root / "src/native/contracts.py"
    ui_file = ui_root / "src" / Path(*ui.__name__.split(".")).with_suffix(".py")
    assert Path(ui.__file__).resolve() == ui_file
    return SimpleNamespace(runtime=runtime, contracts=contracts, ui=ui)


@pytest.fixture
def producer_environment():
    return {
        "ORCHESTRATION_HOST": "container_apps", "APPLICATION_MODE": "both",
        "HOSTED_AGENT_DEPLOYMENT": json.dumps({"durableTask": {
            "resourceId": "/subscriptions/example/resourceGroups/example/providers/Microsoft.DurableTask/schedulers/example",
            "endpoint": "https://returned.eastus.durabletask.io", "taskHubName": "agent-lz",
        }}),
    }


def test_actual_producer_binding_reaches_both_actual_parsers_and_native_constructors(actual_components, producer_environment):
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
    from durabletask.azuremanaged.client import DurableTaskSchedulerClient
    from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker

    settings = runtime_settings(producer_environment)
    binding = settings["DURABLE_TASK_SCHEDULER_CONNECTION_STRING"]
    assert binding == (
        "Endpoint=https://returned.eastus.durabletask.io;"
        "TaskHub=agent-lz;Authentication=ManagedIdentity"
    )
    worker_options = actual_components.runtime.scheduler_binding(binding)
    ui_options = actual_components.ui.scheduler_options(binding)
    assert worker_options == {"host_address": "https://returned.eastus.durabletask.io", "taskhub": "agent-lz"}
    assert ui_options == {"host_address": "returned.eastus.durabletask.io", "taskhub": "agent-lz", "client_id": ""}
    # Real product parsers and SDK constructors, only the transport is mocked.
    # The worker defers its channel until start; no worker start/RPC/token request.
    with patch("grpc.secure_channel") as tls, patch("grpc.insecure_channel") as insecure, \
         patch.object(DefaultAzureCredential, "get_token", side_effect=AssertionError("No token requests")), \
         patch.object(ManagedIdentityCredential, "get_token", side_effect=AssertionError("No token requests")):
        with ManagedIdentityCredential() as credential:
            worker = actual_components.runtime.DurableTaskSchedulerWorker(
                **worker_options, token_credential=credential, secure_channel=True,
            )
            ui_settings = actual_components.ui.NativeSettings(
                host="container_apps", mode="both", scheduler_binding=binding,
                agent_name=settings["DURABLE_AGENT_NAME"], workflow_name=settings["DURABLE_WORKFLOW_NAME"],
            )
            client = actual_components.ui.NativeDurableClient(ui_settings)
            try:
                assert isinstance(worker, DurableTaskSchedulerWorker)
                assert isinstance(client.client, DurableTaskSchedulerClient)
                tls.assert_called_once()
                insecure.assert_not_called()
            finally:
                asyncio.run(client.aclose())
                worker.stop()


@pytest.mark.parametrize("mutation", ["key", "authentication", "credentials"])
def test_actual_consumers_reject_secret_bearing_binding(actual_components, producer_environment, mutation):
    binding = scheduler_settings(producer_environment)["DURABLE_TASK_SCHEDULER_CONNECTION_STRING"]
    if mutation == "key":
        binding += ";AccountKey=synthetic-test-value"
    elif mutation == "authentication":
        binding = binding.replace("Authentication=ManagedIdentity", "Authentication=AccessKey")
    else:
        binding = binding.replace("https://returned.", "https://example:synthetic-test-value@returned.")
    with pytest.raises(ValueError):
        actual_components.runtime.scheduler_binding(binding)
    with pytest.raises(actual_components.ui.ConfigurationError):
        actual_components.ui.scheduler_options(binding)


def test_generated_registration_names_match_actual_runtime(actual_components, producer_environment):
    settings = runtime_settings(producer_environment)
    assert settings["DURABLE_AGENT_NAME"] == actual_components.contracts.AGENT_NAME
    assert settings["DURABLE_WORKFLOW_NAME"] == actual_components.contracts.WORKFLOW_NAME


@pytest.mark.parametrize("host", ["hosted", "container_apps"])
def test_actual_platform_private_flag_reaches_actual_ui_and_native_content_types(actual_components, producer_environment, host):
    import base64
    from config.appdefinition.loader import DEFINITION_ENV, load_selected_definition
    from config.appdefinition.validator import validate_definition

    root = Path(__file__).resolve().parents[1]
    env = {
        **producer_environment, "ORCHESTRATION_HOST": host, "APPLICATION_MODE": "conversational",
        DEFINITION_ENV: str(root / "app-definition.json"), "ENABLE_PRIVATE_ATTACHMENTS": "true",
        "ENABLE_CHAT_HISTORY": "false", "ENABLE_USER_FEEDBACK": "false", "NL2SQL_ENABLED": "false",
        "AZURE_RESOURCE_GROUP": "rg-test", "RESOURCE_TOKEN": "test",
        "HOSTED_AGENT_RESOURCE_SCOPE": "https://ai.azure.com/.default",
    }
    validate_definition(load_selected_definition(env, repo_root=root), repo_root=root)
    result = compose_parameters(json.loads((root / "main.parameters.json").read_text()), env)["parameters"]
    assert result["deployCosmosDb"]["value"] is True
    assert all(app["service_name"] != "dataingest" for app in result["containerAppsList"]["value"])
    values = {item["name"]: item["value"] for item in result["additionalAppConfigurationSettings"]["value"]}
    values.update(runtime_settings(env))
    values.update({
        "DATABASE_ACCOUNT_NAME": "ui-account", "DATABASE_NAME": "ui-db",
        "NATIVE_UI_TOKEN_AUDIENCE": "ui-audience", "OAUTH_AZURE_AD_TENANT_ID": "tenant",
        "HOSTED_AGENT_BASE_URL": "https://example.invalid/agent" if host == "hosted" else "",
    })

    class Config:
        def get(self, key, default="", type=str):
            return values.get(key, default)

    ui_config = importlib.import_module(actual_components.ui.NativeSettings.__module__)
    settings = ui_config.load_native_settings(Config())
    assert settings.private_uploads and settings.persistent_metadata
    attachment = actual_components.ui.InlineAttachment(
        name="note.txt", content_type="text/plain", data_base64=base64.b64encode(b"private input").decode(),
    )
    assert attachment.decode() == b"private input"
    assert attachment.hosted_content() == {
        "type": "input_file", "filename": "note.txt",
        "file_data": "data:text/plain;base64," + base64.b64encode(b"private input").decode(),
    }
    assert attachment.durable_content().text == "[File: note.txt]\nprivate input"
