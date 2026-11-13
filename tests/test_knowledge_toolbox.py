"""Managed KB registration through the real pinned project SDK, offline only."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AccessToken

from config.aifoundry.toolbox import KnowledgeToolbox

PROJECT = "https://test-foundry.services.ai.azure.com/api/projects/test-project"
PROJECT_ID = (
    "/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/test-group/providers/"
    "Microsoft.CognitiveServices/accounts/test-foundry/projects/test-project"
)
BASE = {
    "RETRIEVAL_BACKEND": "foundry_iq", "AI_FOUNDRY_PROJECT_ENDPOINT": PROJECT,
    "AI_FOUNDRY_PROJECT_RESOURCE_ID": PROJECT_ID, "KNOWLEDGE_BASE_NAME": "test-kb",
    "KNOWLEDGE_BASE_ENDPOINT": "https://test-search.search.windows.net",
    "KNOWLEDGE_BASE_CONNECTION_ID": PROJECT_ID + "/connections/kb-connection",
    "TOOLBOX_ENDPOINT": PROJECT + "/toolboxes/test-kb/mcp?api-version=v1",
    "FOUNDRY_IQ_API_VERSION": "2026-05-01-preview",
}
SERVICE = {
    "HOSTED_AGENT_AUTH_MODE": "service_identity", "FOUNDRY_IQ_PATTERN": "azureBlob",
    "FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND": "azureBlob", "FOUNDRY_IQ_IS_ADLS_GEN2": "false",
    "FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS": "[]",
}


@pytest.mark.parametrize("profile", [{}, SERVICE])
def test_real_sdk_registers_kb_tool_and_promotes_version_without_user_credentials(profile):
    binding = KnowledgeToolbox.read({**BASE, **profile})
    assert binding is not None
    packets = []

    def boundary(method, url, **kwargs):
        body = json.loads(kwargs["data"])
        packets.append((method, url, body))
        response = requests.Response()
        response.status_code = 200
        response.headers["Content-Type"] = "application/json"
        response._content = json.dumps({
            "id": "test-toolbox", "name": "test-kb", "version": "1",
            "default_version": "1", "tools": body.get("tools", []),
        }).encode()
        response.raw = SimpleNamespace()
        response._content_consumed = True
        return response

    credential = SimpleNamespace(get_token=Mock(return_value=AccessToken("synthetic-agent-token", 2**31)))
    with patch("requests.Session.request", side_effect=boundary), AIProjectClient(
        endpoint=PROJECT, credential=credential,
    ) as client:
        binding.provision(client)
    assert [(method, url) for method, url, _ in packets] == [
        ("POST", PROJECT + "/toolboxes/test-kb/versions?api-version=v1"),
        ("PATCH", PROJECT + "/toolboxes/test-kb?api-version=v1"),
    ]
    assert packets[0][2]["tools"] == [{
        "type": "mcp", "name": "knowledge_base", "server_label": "knowledge_base",
        "server_url": "https://test-search.search.windows.net/knowledgebases/test-kb/mcp?api-version=2026-05-01-preview",
        "project_connection_id": "kb-connection", "require_approval": "never",
        "allowed_tools": ["knowledge_base_retrieve"],
    }]
    assert packets[1][2] == {"default_version": "1"}
    assert credential.get_token.call_args.args == ("https://ai.azure.com/.default",)
    assert "synthetic-agent-token" not in json.dumps(packets)
    assert "x-ms-query-source-authorization" not in json.dumps(packets)


@pytest.mark.parametrize("override", [
    {"KNOWLEDGE_BASE_NAME": "../other"}, {"TOOLBOX_ENDPOINT": PROJECT + "/other"},
    {"KNOWLEDGE_BASE_CONNECTION_ID": PROJECT_ID + "-other/connections/kb"},
    {"AI_FOUNDRY_PROJECT_ENDPOINT": "https://other.services.ai.azure.com/api/projects/test-project"},
])
def test_invalid_toolbox_binding_rejected_before_sdk_use(override):
    with pytest.raises(ValueError):
        KnowledgeToolbox.read({**BASE, **SERVICE, **override})


@pytest.mark.parametrize("source", [
    {}, {"FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS": None},
    {"FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS": '["rbacScope"]'},
    {"FOUNDRY_IQ_IS_ADLS_GEN2": "true"},
    {"FOUNDRY_IQ_PATTERN": "searchIndex", "FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND": "searchIndex"},
    {"WORK_IQ_ENABLED": "true"}, {"FOUNDRY_IQ_MCP_ENABLED": "true"},
])
def test_service_toolbox_registration_does_not_restrict_source_types_or_change_permissions(source):
    settings = {**BASE, "HOSTED_AGENT_AUTH_MODE": "service_identity", **source}
    original = dict(settings)
    assert KnowledgeToolbox.read(settings) == KnowledgeToolbox.read(BASE)
    assert settings == original


def test_default_protected_policy_remains_unchanged_and_non_kb_is_not_provisioned():
    settings = dict(BASE)
    before = dict(settings)
    assert KnowledgeToolbox.read(settings)
    assert settings == before
    assert "FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS" not in settings
    assert KnowledgeToolbox.read({"RETRIEVAL_BACKEND": "ai_search"}) is None


def test_failed_registration_never_promotes_or_retries_without_its_connection():
    client = Mock()
    client.toolboxes.create_version.side_effect = RuntimeError("registration denied")
    binding = KnowledgeToolbox.read(BASE)
    with pytest.raises(RuntimeError, match="registration denied"):
        binding.provision(client)
    client.toolboxes.create_version.assert_called_once()
    client.toolboxes.update.assert_not_called()


def test_store_free_entrypoint_provisions_verified_toolbox():
    from config.aifoundry import toolbox
    with (
        patch.object(toolbox, "load_setup_settings", return_value=BASE) as loader,
        patch.object(toolbox, "ChainedTokenCredential"),
        patch.object(toolbox, "AIProjectClient") as projects,
    ):
        toolbox.main()
    loader.assert_called_once_with()
    client = projects.return_value.__enter__.return_value
    client.toolboxes.create_version.assert_called_once()
    client.toolboxes.update.assert_called_once()


def test_hooks_order_and_provider_binding_publication_are_coherent():
    root = Path(__file__).resolve().parents[1]
    for path in ("scripts/postProvision.ps1", "scripts/postProvision.sh"):
        source = (root / path).read_text(encoding="utf-8-sig")
        assert source.index("config.search.setup") < source.index("config.aifoundry.toolbox")
    for path in ("infra/bicep/main.bicep", "infra/terraform/main.compute.tf", "infra/terraform/main.data.tf"):
        source = (root / path).read_text()
        assert "TOOLBOX_ENDPOINT" in source and "/toolboxes/" in source and "/mcp?api-version=v1" in source
