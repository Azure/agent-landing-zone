"""Search rendering does not use a runtime store as deployment discovery."""

from unittest.mock import Mock, patch
from pathlib import Path

import pytest

from config.search import setup


def test_real_templates_derive_setup_values_before_store_free_execution():
    settings = {
        "APP_RUNTIME_CONFIGURATION_MODE": "containerEnv",
        "RESOURCE_TOKEN": "fixture",
        "SEARCH_SERVICE_QUERY_ENDPOINT": "https://verified.search.windows.net",
        "AI_FOUNDRY_ACCOUNT_NAME": "verified-foundry",
        "STORAGE_ACCOUNT_RESOURCE_ID": (
            "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/group/"
            "providers/Microsoft.Storage/storageAccounts/verifiedstorage"
        ),
        "NETWORK_ISOLATION": "false",
        "RETRIEVAL_BACKEND": "ai_search",
        "MODEL_DEPLOYMENTS": [{
            "canonical_name": "EMBEDDING_DEPLOYMENT_NAME", "name": "selected-embedding",
            "model": {"name": "text-embedding-3-large", "format": "OpenAI"},
            "endpoint": "https://verified-foundry.openai.azure.com",
            "api_version": "2025-01-01-preview",
        }],
    }
    template_owned = {
        "SEARCH_API_VERSION": "2025-05-01-preview",
        "SEARCH_ANALYZER_NAME": "standard.lucene",
        "EMBEDDINGS_VECTOR_DIMENSIONS": "3072",
        "SEARCH_QUERIES_INDEX_NAME": "nl2sql-fixture-queries",
        "SEARCH_TABLES_INDEX_NAME": "nl2sql-fixture-tables",
        "SEARCH_MEASURES_INDEX_NAME": "nl2sql-fixture-measures",
    }
    assert not template_owned.keys() & settings.keys()
    template_dir = Path(setup.__file__).parent
    with (
        patch.object(setup, "load_setup_settings", return_value=settings),
        patch.object(setup, "AzureAppConfigurationClient") as store,
        patch.object(setup, "ChainedTokenCredential"),
        patch.object(setup.requests, "get", return_value=Mock(status_code=404)),
        patch.object(setup.requests, "delete", return_value=Mock(status_code=404)),
        patch.object(setup.requests, "put", return_value=Mock(status_code=200)) as put,
    ):
        definitions, context = setup.prepare_context_and_render(setup.TEMPLATE_NAME, str(template_dir))
        assert definitions is not None
        assert {key: context[key] for key in template_owned} == template_owned
        index = definitions["indexes"][0]
        vector = next(field for field in index["fields"] if field["name"] == "contentVector")
        assert vector["dimensions"] == 3072
        setup.execute_setup(definitions, context)
    store.assert_not_called()
    assert any("/indexes/ragindex-fixture?api-version=2025-05-01-preview" in call.args[0]
               for call in put.call_args_list)


@pytest.mark.parametrize("mode", ["containerEnv", "none"])
def test_store_free_strict_render_and_actual_setup(tmp_path, mode):
    (tmp_path / "resources.j2").write_text(
        '{"indexes":[{"name":"{{ SEARCH_SERVICE_QUERY_ENDPOINT }}","body":{}}]}',
    )
    settings = {
        "APP_RUNTIME_CONFIGURATION_MODE": mode,
        "APP_CONFIG_ENDPOINT": "https://unused.azconfig.io",
        "SEARCH_SERVICE_QUERY_ENDPOINT": "https://verified.search.windows.net",
    }
    with (
        patch.object(setup, "load_setup_settings", return_value=settings, create=True),
        patch.object(setup, "AzureAppConfigurationClient") as store,
    ):
        definitions, context = setup.prepare_context_and_render("resources.j2", str(tmp_path))
    store.assert_not_called()
    assert definitions["indexes"][0]["name"] == settings["SEARCH_SERVICE_QUERY_ENDPOINT"]
    assert context["SEARCH_SERVICE_QUERY_ENDPOINT"] == settings["SEARCH_SERVICE_QUERY_ENDPOINT"]


def test_missing_template_input_is_not_silently_substituted(tmp_path):
    (tmp_path / "resources.j2").write_text('{"value":"{{ MISSING_RESOURCE }}"}')
    with patch.object(setup, "load_setup_settings", return_value={}, create=True):
        definitions, _ = setup.prepare_context_and_render("resources.j2", str(tmp_path))
    assert definitions is None


def test_selected_search_without_endpoint_fails_explicitly():
    with pytest.raises(RuntimeError, match="SEARCH_SERVICE_QUERY_ENDPOINT"):
        setup.execute_setup({}, {})


def test_store_free_render_reaches_actual_knowledge_source_and_base_requests(tmp_path):
    (tmp_path / "resources.j2").write_text(
        '{"knowledgeSources":[{"name":"selected-source","kind":"searchIndex",'
        '"searchIndexParameters":{"searchIndexName":"selected-index"}}],'
        '"knowledgeBases":[{"name":"{{ KNOWLEDGE_BASE_NAME }}",'
        '"knowledgeSources":[{"name":"selected-source"}]}]}',
    )
    settings = {
        "APP_RUNTIME_CONFIGURATION_MODE": "containerEnv",
        "SEARCH_SERVICE_QUERY_ENDPOINT": "https://verified.search.windows.net",
        "SEARCH_API_VERSION": "2025-05-01-preview",
        "FOUNDRY_IQ_API_VERSION": "2026-05-01-preview",
        "RETRIEVAL_BACKEND": "foundry_iq", "KNOWLEDGE_BASE_NAME": "selected-kb",
        "HOSTED_AGENT_AUTH_MODE": "service_identity",
    }
    with (
        patch.object(setup, "load_setup_settings", return_value=settings),
        patch.object(setup, "AzureAppConfigurationClient") as store,
        patch.object(setup, "ChainedTokenCredential"),
        patch.object(setup.requests, "put", return_value=Mock(status_code=200)) as put,
    ):
        definitions, context = setup.prepare_context_and_render("resources.j2", str(tmp_path))
        setup.execute_setup(definitions, context)
    store.assert_not_called()
    assert [call.args[0] for call in put.call_args_list] == [
        "https://verified.search.windows.net/knowledgesources/selected-source?api-version=2026-05-01-preview",
        "https://verified.search.windows.net/knowledgebases/selected-kb?api-version=2026-05-01-preview",
    ]


def test_appconfig_preferences_cannot_supply_resource_aliases(tmp_path):
    from azure.core.exceptions import ResourceNotFoundError
    (tmp_path / "resources.j2").write_text('{"endpoint":"{{ SEARCH_SERVICE_QUERY_ENDPOINT }}"}')
    client = Mock()
    client.get_configuration_setting.side_effect = ResourceNotFoundError()
    with (
        patch.object(setup, "load_setup_settings", return_value={
            "APP_RUNTIME_CONFIGURATION_MODE": "appConfig",
            "APP_CONFIG_ENDPOINT": "https://verified.azconfig.io",
            "SEARCH_SERVICE_QUERY_ENDPOINT": "https://verified.search.windows.net",
        }),
        patch.object(setup, "AzureAppConfigurationClient", return_value=client),
        patch.object(setup, "ChainedTokenCredential"),
    ):
        definitions, _ = setup.prepare_context_and_render("resources.j2", str(tmp_path))
    assert definitions["endpoint"] == "https://verified.search.windows.net"
    client.list_configuration_settings.assert_not_called()
    assert {call.kwargs["key"] for call in client.get_configuration_setting.call_args_list} == setup.SEARCH_PREFERENCE_KEYS
    assert all(call.kwargs["label"] == "agent-lz" for call in client.get_configuration_setting.call_args_list)
