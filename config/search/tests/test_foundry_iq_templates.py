import inspect
import io
import itertools
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from config.search import setup
from config.search import foundry_iq_mcp_setup as mcp_setup
from config.search import sharepoint_indexed_setup as sharepoint_setup


TEMPLATE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
MCP_RUNTIME_CONTRACT_MIN_VERSION = "v3.7.0"
MCP_FIXTURE_CONTRACT_VERSION = "v3.7.0"


def version_tuple(tag):
    core = tag.removeprefix("v").split("-", 1)[0]
    return tuple(int(part) for part in core.split("."))


def render_json_template(template_name, context):
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    rendered = env.get_template(template_name).render(**context)
    return json.loads(rendered)


class FoundryIqTemplateTests(unittest.TestCase):
    def test_application_index_enforces_native_document_permissions(self):
        for backend in ("foundry_iq", "ai_search"):
            with self.subTest(backend=backend):
                settings = render_json_template(
                    "search.settings.j2",
                    {
                        "RESOURCE_TOKEN": "abc123",
                        "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                        "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                        "RETRIEVAL_BACKEND": backend,
                    },
                )
                definitions = render_json_template(
                    "search.j2",
                    {
                        **settings,
                        "STORAGE_ACCOUNT_RESOURCE_ID": (
                            "/subscriptions/s/resourceGroups/rg/providers/"
                            "Microsoft.Storage/storageAccounts/st"
                        ),
                        "EMBEDDING_MODEL_INFO": {},
                        "GPT_MODEL_INFO": {},
                    },
                )
                index = definitions["indexes"][0]
                self.assertEqual(index["permissionFilterOption"], "enabled")
                fields = {field["name"]: field for field in index["fields"]}
                for name, permission in (
                    ("metadata_security_user_ids", "userIds"),
                    ("metadata_security_group_ids", "groupIds"),
                    ("metadata_security_rbac_scope", "rbacScope"),
                ):
                    self.assertEqual(fields[name]["permissionFilter"], permission)
                    self.assertTrue(fields[name]["filterable"])

    def test_settings_template_derives_search_index_before_dependent_defaults(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_PROJECT_ENDPOINT": "https://aif-abc123.services.ai.azure.com/api/projects/proj",
            },
        )

        self.assertEqual(settings["SEARCH_RAG_INDEX_NAME"], "ragindex-abc123")
        self.assertEqual(settings["KNOWLEDGE_BASE_NAME"], "ragindex-abc123-rag-kb")
        self.assertEqual(settings["FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME"], "ragindex-abc123-blob-ks")
        self.assertEqual(
            settings["FOUNDRY_IQ_AI_SERVICES_ENDPOINT"],
            "https://aif-abc123.services.ai.azure.com/",
        )

    def test_standard_blob_knowledge_source_includes_ai_services_endpoint_without_unsupported_chat_model(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                "RETRIEVAL_BACKEND": "foundry_iq",
                "FOUNDRY_IQ_CONTENT_EXTRACTION_MODE": "standard",
            },
        )
        context = {
            **settings,
            "STORAGE_ACCOUNT_RESOURCE_ID": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st",
            "EMBEDDING_MODEL_INFO": {
                "endpoint": "https://aif-abc123.openai.azure.com/",
                "deployment_name": "text-embedding",
                "model_name": "text-embedding-3-large",
            },
            "GPT_MODEL_INFO": {
                "deployment_name": "chat",
                "model_name": "gpt-5-nano",
            },
        }

        search_definitions = render_json_template("search.j2", context)
        knowledge_source = search_definitions["knowledgeSources"][0]
        ingestion_parameters = knowledge_source["azureBlobParameters"]["ingestionParameters"]

        self.assertEqual(ingestion_parameters["contentExtractionMode"], "standard")
        self.assertEqual(
            ingestion_parameters["aiServices"]["uri"],
            "https://aif-abc123.services.ai.azure.com/",
        )
        self.assertIsNone(ingestion_parameters["chatCompletionModel"])

    def test_blob_knowledge_source_uses_configured_search_uai(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                "RETRIEVAL_BACKEND": "foundry_iq",
            },
        )
        identity_resource_id = (
            "/subscriptions/s/resourceGroups/rg/providers/"
            "Microsoft.ManagedIdentity/userAssignedIdentities/search-uai"
        )
        context = {
            **settings,
            "SEARCH_SERVICE_UAI_RESOURCE_ID": identity_resource_id,
            "STORAGE_ACCOUNT_RESOURCE_ID": (
                "/subscriptions/s/resourceGroups/rg/providers/"
                "Microsoft.Storage/storageAccounts/st"
            ),
            "EMBEDDING_MODEL_INFO": {},
            "GPT_MODEL_INFO": {},
        }

        search_definitions = render_json_template("search.j2", context)
        ingestion_parameters = search_definitions["knowledgeSources"][0][
            "azureBlobParameters"
        ]["ingestionParameters"]

        self.assertEqual(
            ingestion_parameters["identity"],
            {
                "@odata.type": "#Microsoft.Azure.Search.DataUserAssignedIdentity",
                "userAssignedIdentity": identity_resource_id,
            },
        )

    def test_standard_blob_knowledge_source_includes_supported_chat_model(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                "RETRIEVAL_BACKEND": "foundry_iq",
                "FOUNDRY_IQ_CONTENT_EXTRACTION_MODE": "standard",
            },
        )
        context = {
            **settings,
            "STORAGE_ACCOUNT_RESOURCE_ID": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st",
            "EMBEDDING_MODEL_INFO": {
                "endpoint": "https://aif-abc123.openai.azure.com/",
                "deployment_name": "text-embedding",
                "model_name": "text-embedding-3-large",
            },
            "GPT_MODEL_INFO": {
                "deployment_name": "chat",
                "model_name": "gpt-5.2",
            },
        }

        search_definitions = render_json_template("search.j2", context)
        knowledge_source = search_definitions["knowledgeSources"][0]
        ingestion_parameters = knowledge_source["azureBlobParameters"]["ingestionParameters"]

        self.assertEqual(
            ingestion_parameters["chatCompletionModel"]["azureOpenAIParameters"]["resourceUri"],
            ingestion_parameters["aiServices"]["uri"],
        )
        self.assertEqual(
            ingestion_parameters["chatCompletionModel"]["azureOpenAIParameters"]["modelName"],
            "gpt-5.2",
        )

    def test_network_isolated_blob_knowledge_source_sets_generated_indexer_private(self):
        credential = Mock()
        credential.get_token.return_value.token = "token"
        get_response = Mock()
        get_response.status_code = 200
        get_response.json.return_value = {
            "@odata.context": "https://search/$metadata#indexers/$entity",
            "name": "blob-ks-indexer",
            "dataSourceName": "blob-ks-datasource",
            "targetIndexName": "blob-ks-index",
            "parameters": {
                "configuration": {
                    "dataToExtract": "contentAndMetadata",
                }
            },
        }
        put_response = Mock()
        put_response.status_code = 200

        with patch.object(setup.requests, "get", return_value=get_response), patch.object(
            setup.requests, "put", return_value=put_response
        ) as put:
            setup.enforce_private_execution_for_generated_indexers(
                {
                    "knowledgeSources": [
                        {
                            "name": "blob-ks",
                            "kind": "azureBlob",
                            "azureBlobParameters": {},
                        }
                    ]
                },
                {"NETWORK_ISOLATION": "true"},
                credential,
                "https://search.search.windows.net",
                "2025-05-01-preview",
            )

        body = put.call_args.kwargs["json"]
        self.assertNotIn("@odata.context", body)
        self.assertEqual(body["parameters"]["configuration"]["executionEnvironment"], "Private")

    def test_non_network_isolated_setup_does_not_update_generated_indexer(self):
        credential = Mock()

        with patch.object(setup.requests, "get") as get:
            setup.enforce_private_execution_for_generated_indexers(
                {
                    "knowledgeSources": [
                        {
                            "name": "blob-ks",
                            "kind": "azureBlob",
                            "azureBlobParameters": {},
                        }
                    ]
                },
                {"NETWORK_ISOLATION": "false"},
                credential,
                "https://search.search.windows.net",
                "2025-05-01-preview",
            )

        get.assert_not_called()


    def test_conversation_upload_disabled_by_default_keeps_single_knowledge_source(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                "RETRIEVAL_BACKEND": "foundry_iq",
            },
        )
        self.assertEqual(settings["FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED"], "false")
        self.assertEqual(
            settings["FOUNDRY_IQ_CONVERSATION_KNOWLEDGE_SOURCE_NAME"],
            "ragindex-abc123-conv-ks",
        )

        context = {
            **settings,
            "STORAGE_ACCOUNT_RESOURCE_ID": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st",
            "EMBEDDING_MODEL_INFO": {
                "endpoint": "https://aif-abc123.openai.azure.com/",
                "deployment_name": "text-embedding",
                "model_name": "text-embedding-3-large",
            },
            "GPT_MODEL_INFO": {
                "deployment_name": "chat",
                "model_name": "gpt-5-nano",
            },
        }

        search_definitions = render_json_template("search.j2", context)
        self.assertEqual(len(search_definitions["knowledgeSources"]), 1)
        self.assertEqual(
            search_definitions["knowledgeSources"][0]["kind"], "azureBlob"
        )
        self.assertEqual(
            len(search_definitions["knowledgeBases"][0]["knowledgeSources"]), 1
        )

    def test_conversation_upload_enabled_adds_conversational_search_index_source(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                "RETRIEVAL_BACKEND": "foundry_iq",
                "FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED": "true",
            },
        )
        self.assertEqual(settings["FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED"], "true")

        context = {
            **settings,
            "STORAGE_ACCOUNT_RESOURCE_ID": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st",
            "EMBEDDING_MODEL_INFO": {
                "endpoint": "https://aif-abc123.openai.azure.com/",
                "deployment_name": "text-embedding",
                "model_name": "text-embedding-3-large",
            },
            "GPT_MODEL_INFO": {
                "deployment_name": "chat",
                "model_name": "gpt-5-nano",
            },
        }

        search_definitions = render_json_template("search.j2", context)
        knowledge_sources = search_definitions["knowledgeSources"]
        self.assertEqual(len(knowledge_sources), 2)
        self.assertEqual(knowledge_sources[0]["kind"], "azureBlob")

        conv_source = knowledge_sources[1]
        self.assertEqual(conv_source["name"], "ragindex-abc123-conv-ks")
        self.assertEqual(conv_source["kind"], "searchIndex")
        self.assertEqual(
            conv_source["searchIndexParameters"]["searchIndexName"],
            "ragindex-abc123",
        )
        self.assertEqual(
            conv_source["searchIndexParameters"]["semanticConfigurationName"],
            "semantic-config",
        )

        kb_sources = search_definitions["knowledgeBases"][0]["knowledgeSources"]
        self.assertEqual(
            [s["name"] for s in kb_sources],
            ["ragindex-abc123-blob-ks", "ragindex-abc123-conv-ks"],
        )

    def test_conversation_upload_not_added_for_search_index_pattern(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                "RETRIEVAL_BACKEND": "foundry_iq",
                "FOUNDRY_IQ_PATTERN": "searchIndex",
                "FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED": "true",
            },
        )

        context = {
            **settings,
            "STORAGE_ACCOUNT_RESOURCE_ID": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st",
            "EMBEDDING_MODEL_INFO": {
                "endpoint": "https://aif-abc123.openai.azure.com/",
                "deployment_name": "text-embedding",
                "model_name": "text-embedding-3-large",
            },
            "GPT_MODEL_INFO": {
                "deployment_name": "chat",
                "model_name": "gpt-5-nano",
            },
        }

        search_definitions = render_json_template("search.j2", context)
        self.assertEqual(len(search_definitions["knowledgeSources"]), 1)
        self.assertEqual(
            search_definitions["knowledgeSources"][0]["kind"], "searchIndex"
        )
        self.assertEqual(
            len(search_definitions["knowledgeBases"][0]["knowledgeSources"]), 1
        )


class WorkIqTemplateTests(unittest.TestCase):
    """Work IQ is opt-in and default-off. Rendered output must be byte-identical
    to the pre-Work IQ template when the feature is disabled.
    """

    def _foundry_iq_context(self, **overrides):
        settings_input = {
            "RESOURCE_TOKEN": "abc123",
            "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
            "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
            "RETRIEVAL_BACKEND": "foundry_iq",
        }
        settings_input.update(overrides)
        settings = render_json_template("search.settings.j2", settings_input)
        return settings, {
            **settings,
            "STORAGE_ACCOUNT_RESOURCE_ID": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st",
            "EMBEDDING_MODEL_INFO": {
                "endpoint": "https://aif-abc123.openai.azure.com/",
                "deployment_name": "text-embedding",
                "model_name": "text-embedding-3-large",
            },
            "GPT_MODEL_INFO": {
                "deployment_name": "chat",
                "model_name": "gpt-5-nano",
            },
        }

    def test_settings_defaults_work_iq_disabled_and_empty_name(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                "RETRIEVAL_BACKEND": "foundry_iq",
            },
        )
        self.assertEqual(settings["WORK_IQ_ENABLED"], "false")
        self.assertEqual(settings["WORK_IQ_KNOWLEDGE_SOURCE_NAME"], "")

    def test_work_iq_disabled_by_default_produces_no_workiq_entry(self):
        _, context = self._foundry_iq_context()
        search_definitions = render_json_template("search.j2", context)
        for ks in search_definitions["knowledgeSources"]:
            self.assertNotEqual(ks["kind"], "workIQ")
        kb_source_names = [
            s["name"] for s in search_definitions["knowledgeBases"][0]["knowledgeSources"]
        ]
        self.assertNotIn("work-iq-ks", kb_source_names)

    def test_work_iq_enabled_without_name_produces_no_workiq_entry(self):
        _, context = self._foundry_iq_context(WORK_IQ_ENABLED="true")
        search_definitions = render_json_template("search.j2", context)
        for ks in search_definitions["knowledgeSources"]:
            self.assertNotEqual(ks["kind"], "workIQ")

    def test_work_iq_enabled_adds_workiq_knowledge_source_and_kb_reference(self):
        _, context = self._foundry_iq_context(
            WORK_IQ_ENABLED="true",
            WORK_IQ_KNOWLEDGE_SOURCE_NAME="work-iq-ks",
            WORK_IQ_APPLICATION_ID="11111111-1111-1111-1111-111111111111",
            WORK_IQ_FEDERATED_CREDENTIAL_ID="22222222-2222-2222-2222-222222222222",
            WORK_IQ_TENANT_ID="33333333-3333-3333-3333-333333333333",
            FOUNDRY_IQ_API_VERSION="2026-08-01-preview",
        )
        search_definitions = render_json_template("search.j2", context)

        work_iq_sources = [
            ks for ks in search_definitions["knowledgeSources"] if ks["kind"] == "workIQ"
        ]
        self.assertEqual(len(work_iq_sources), 1)
        work_iq = work_iq_sources[0]
        self.assertEqual(work_iq["name"], "work-iq-ks")
        self.assertEqual(work_iq["kind"], "workIQ")
        self.assertIsNone(work_iq["encryptionKey"])
        # Work IQ is service-managed. It must not carry a filterAddOn, blob
        # parameters, or search-index parameters.
        self.assertNotIn("filterAddOn", work_iq)
        self.assertNotIn("azureBlobParameters", work_iq)
        self.assertNotIn("searchIndexParameters", work_iq)
        self.assertEqual(
            work_iq["workIQParameters"]["entraAppAuthentication"],
            {
                "applicationId": context["WORK_IQ_APPLICATION_ID"],
                "federatedCredentialId": context["WORK_IQ_FEDERATED_CREDENTIAL_ID"],
                "tenantId": context["WORK_IQ_TENANT_ID"],
            },
        )
        setup.validate_requested_knowledge_sources(search_definitions, context)

        kb_source_names = [
            s["name"] for s in search_definitions["knowledgeBases"][0]["knowledgeSources"]
        ]
        self.assertIn("work-iq-ks", kb_source_names)

    def test_native_sharepoint_source_uses_secretless_federation_and_native_acls(self):
        for isolated in ("false", "true"):
            with self.subTest(isolated=isolated):
                _, context = self._foundry_iq_context(
                    SHAREPOINT_INDEXED_ENABLED="true",
                    SHAREPOINT_INDEXED_KNOWLEDGE_SOURCE_NAME="sharepoint-ks",
                    SHAREPOINT_INDEXED_SITE_URL="https://contoso.sharepoint.com/sites/eng",
                    SHAREPOINT_INDEXED_TENANT_ID="11111111-1111-1111-1111-111111111111",
                    SHAREPOINT_INDEXED_APPLICATION_ID="22222222-2222-2222-2222-222222222222",
                    SHAREPOINT_INDEXED_FEDERATED_CREDENTIAL_APPLICATION_ID="33333333-3333-3333-3333-333333333333",
                    FOUNDRY_IQ_API_VERSION="2026-08-01-preview",
                )
                context["NETWORK_ISOLATION"] = isolated
                definitions = render_json_template("search.j2", context)
                source = next(
                    source for source in definitions["knowledgeSources"]
                    if source["kind"] == "indexedSharePoint"
                )
                parameters = source["indexedSharePointParameters"]
                self.assertEqual(
                    parameters["connectionString"],
                    "SharePointOnlineEndpoint=https://contoso.sharepoint.com/sites/eng;"
                    "ApplicationId=22222222-2222-2222-2222-222222222222;"
                    "FederatedCredentialApplicationId=33333333-3333-3333-3333-333333333333;"
                    "TenantId=11111111-1111-1111-1111-111111111111",
                )
                self.assertNotIn("indexName", parameters)
                self.assertNotIn("ApplicationSecret", parameters["connectionString"])
                ingestion = parameters["ingestionParameters"]
                self.assertEqual(ingestion["ingestionPermissionOptions"], ["userIds", "groupIds"])
                self.assertEqual(ingestion["networkAccessMode"], "private" if isolated == "true" else "public")
                self.assertEqual(
                    ingestion["embeddingModel"]["azureOpenAIParameters"]["deploymentId"],
                    "text-embedding",
                )
                setup.validate_requested_knowledge_sources(definitions, context)
                for bad_site in (
                    "http://contoso.sharepoint.com/sites/eng",
                    "https://contoso.sharepoint.com/sites/eng;ApplicationSecret=injected",
                    "https://contoso.sharepoint.com.evil.test/sites/eng",
                ):
                    with self.assertRaisesRegex(ValueError, "HTTPS SharePoint"):
                        setup.validate_requested_knowledge_sources(
                            definitions, {**context, "SHAREPOINT_INDEXED_SITE_URL": bad_site}
                        )

    def test_work_iq_authentication_rejects_missing_invalid_or_incompatible_inputs(self):
        _, context = self._foundry_iq_context(
            WORK_IQ_ENABLED="true",
            WORK_IQ_KNOWLEDGE_SOURCE_NAME="work-iq-ks",
            WORK_IQ_APPLICATION_ID="11111111-1111-1111-1111-111111111111",
            WORK_IQ_FEDERATED_CREDENTIAL_ID="22222222-2222-2222-2222-222222222222",
            FOUNDRY_IQ_API_VERSION="2026-08-01-preview",
        )
        definitions = render_json_template("search.j2", context)
        setup.validate_requested_knowledge_sources(definitions, context)
        source = next(source for source in definitions["knowledgeSources"] if source["kind"] == "workIQ")
        self.assertNotIn("tenantId", source["workIQParameters"]["entraAppAuthentication"])
        for override in (
            {"WORK_IQ_APPLICATION_ID": ""},
            {"WORK_IQ_FEDERATED_CREDENTIAL_ID": ""},
            {"WORK_IQ_APPLICATION_ID": "sensitive-invalid-value"},
            {"WORK_IQ_TENANT_ID": "sensitive-invalid-value"},
            {"FOUNDRY_IQ_API_VERSION": "2026-05-01-preview"},
        ):
            with self.subTest(override=override), self.assertRaises(ValueError) as error:
                setup.validate_requested_knowledge_sources(definitions, {**context, **override})
            self.assertNotIn("sensitive-invalid-value", str(error.exception))

    def test_work_iq_not_added_when_retrieval_backend_is_ai_search(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                "WORK_IQ_ENABLED": "true",
                "WORK_IQ_KNOWLEDGE_SOURCE_NAME": "work-iq-ks",
            },
        )
        context = {
            **settings,
            "STORAGE_ACCOUNT_RESOURCE_ID": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st",
            "EMBEDDING_MODEL_INFO": {
                "endpoint": "https://aif-abc123.openai.azure.com/",
                "deployment_name": "text-embedding",
                "model_name": "text-embedding-3-large",
            },
            "GPT_MODEL_INFO": {
                "deployment_name": "chat",
                "model_name": "gpt-5-nano",
            },
        }
        search_definitions = render_json_template("search.j2", context)
        # ai_search backend never emits knowledge sources at all.
        self.assertEqual(search_definitions["knowledgeSources"], [])
        self.assertEqual(search_definitions["knowledgeBases"], [])

    def test_settings_defaults_fabric_iq_disabled_and_empty(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                "RETRIEVAL_BACKEND": "foundry_iq",
            },
        )
        self.assertEqual(settings["FABRIC_IQ_ENABLED"], "false")
        self.assertEqual(settings["FABRIC_IQ_KNOWLEDGE_SOURCE_NAME"], "")
        self.assertEqual(settings["FABRIC_IQ_WORKSPACE_ID"], "")
        self.assertEqual(settings["FABRIC_IQ_ONTOLOGY_ID"], "")

    def test_fabric_sources_enable_a_planning_model_and_supported_reasoning(self):
        for binding in (
            {
                "FABRIC_IQ_ENABLED": "true",
                "FABRIC_IQ_KNOWLEDGE_SOURCE_NAME": "fabric-ks",
                "FABRIC_IQ_WORKSPACE_ID": "workspace",
                "FABRIC_IQ_ONTOLOGY_ID": "ontology",
            },
            {
                "FABRIC_DATA_AGENT_ENABLED": "true",
                "FABRIC_DATA_AGENT_KNOWLEDGE_SOURCE_NAME": "data-agent-ks",
                "FABRIC_DATA_AGENT_WORKSPACE_ID": "workspace",
                "FABRIC_DATA_AGENT_DATA_AGENT_ID": "data-agent",
            },
        ):
            with self.subTest(binding=binding):
                _, context = self._foundry_iq_context(**binding)
                kb = render_json_template("search.j2", context)["knowledgeBases"][0]
                self.assertEqual(kb["retrievalReasoningEffort"], {"kind": "low"})
                self.assertEqual(
                    kb["models"][0]["azureOpenAIParameters"],
                    {
                        "resourceUri": context["FOUNDRY_IQ_AI_SERVICES_ENDPOINT"],
                        "deploymentId": "chat",
                        "modelName": "gpt-5-nano",
                    },
                )

    def test_fabric_iq_disabled_by_default_produces_no_fabric_entry(self):
        _, context = self._foundry_iq_context()
        search_definitions = render_json_template("search.j2", context)
        for ks in search_definitions["knowledgeSources"]:
            self.assertNotEqual(ks["kind"], "fabricOntology")
        kb_source_names = [
            s["name"] for s in search_definitions["knowledgeBases"][0]["knowledgeSources"]
        ]
        self.assertNotIn("fabric-iq-ks", kb_source_names)

    def test_fabric_iq_enabled_without_binding_fields_produces_no_entry(self):
        # Enabled + name but missing workspace and ontology ids must not emit.
        _, context = self._foundry_iq_context(
            FABRIC_IQ_ENABLED="true",
            FABRIC_IQ_KNOWLEDGE_SOURCE_NAME="fabric-iq-ks",
        )
        search_definitions = render_json_template("search.j2", context)
        for ks in search_definitions["knowledgeSources"]:
            self.assertNotEqual(ks["kind"], "fabricOntology")

    def test_fabric_iq_enabled_adds_fabric_knowledge_source_and_kb_reference(self):
        _, context = self._foundry_iq_context(
            FABRIC_IQ_ENABLED="true",
            FABRIC_IQ_KNOWLEDGE_SOURCE_NAME="fabric-iq-ks",
            FABRIC_IQ_WORKSPACE_ID="ws-guid-1",
            FABRIC_IQ_ONTOLOGY_ID="ont-guid-1",
        )
        search_definitions = render_json_template("search.j2", context)

        fabric_sources = [
            ks
            for ks in search_definitions["knowledgeSources"]
            if ks["kind"] == "fabricOntology"
        ]
        self.assertEqual(len(fabric_sources), 1)
        fabric = fabric_sources[0]
        self.assertEqual(fabric["name"], "fabric-iq-ks")
        self.assertEqual(fabric["kind"], "fabricOntology")
        self.assertIsNone(fabric["encryptionKey"])
        # Fabric IQ is service-managed. It must not carry a filterAddOn.
        self.assertNotIn("filterAddOn", fabric)
        self.assertEqual(
            fabric["fabricOntologyParameters"],
            {"workspaceId": "ws-guid-1", "ontologyId": "ont-guid-1"},
        )

        kb_source_names = [
            s["name"] for s in search_definitions["knowledgeBases"][0]["knowledgeSources"]
        ]
        self.assertIn("fabric-iq-ks", kb_source_names)

    def test_settings_defaults_fabric_data_agent_disabled_and_empty(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                "RETRIEVAL_BACKEND": "foundry_iq",
            },
        )
        self.assertEqual(settings["FABRIC_DATA_AGENT_ENABLED"], "false")
        self.assertEqual(settings["FABRIC_DATA_AGENT_KNOWLEDGE_SOURCE_NAME"], "")
        self.assertEqual(settings["FABRIC_DATA_AGENT_WORKSPACE_ID"], "")
        self.assertEqual(settings["FABRIC_DATA_AGENT_DATA_AGENT_ID"], "")

    def test_fabric_data_agent_disabled_by_default_produces_no_entry(self):
        _, context = self._foundry_iq_context()
        search_definitions = render_json_template("search.j2", context)
        for ks in search_definitions["knowledgeSources"]:
            self.assertNotEqual(ks["kind"], "fabricDataAgent")
        kb_source_names = [
            s["name"] for s in search_definitions["knowledgeBases"][0]["knowledgeSources"]
        ]
        self.assertNotIn("fabric-data-agent-ks", kb_source_names)

    def test_fabric_data_agent_enabled_without_binding_fields_produces_no_entry(self):
        # Enabled + name but missing workspace and data agent ids must not emit.
        _, context = self._foundry_iq_context(
            FABRIC_DATA_AGENT_ENABLED="true",
            FABRIC_DATA_AGENT_KNOWLEDGE_SOURCE_NAME="fabric-data-agent-ks",
        )
        search_definitions = render_json_template("search.j2", context)
        for ks in search_definitions["knowledgeSources"]:
            self.assertNotEqual(ks["kind"], "fabricDataAgent")

    def test_fabric_data_agent_enabled_adds_knowledge_source_and_kb_reference(self):
        _, context = self._foundry_iq_context(
            FABRIC_DATA_AGENT_ENABLED="true",
            FABRIC_DATA_AGENT_KNOWLEDGE_SOURCE_NAME="fabric-data-agent-ks",
            FABRIC_DATA_AGENT_WORKSPACE_ID="ws-guid-2",
            FABRIC_DATA_AGENT_DATA_AGENT_ID="da-guid-2",
        )
        search_definitions = render_json_template("search.j2", context)

        agent_sources = [
            ks
            for ks in search_definitions["knowledgeSources"]
            if ks["kind"] == "fabricDataAgent"
        ]
        self.assertEqual(len(agent_sources), 1)
        agent = agent_sources[0]
        self.assertEqual(agent["name"], "fabric-data-agent-ks")
        self.assertEqual(agent["kind"], "fabricDataAgent")
        self.assertIsNone(agent["encryptionKey"])
        # Fabric Data Agent is service-managed. It must not carry a filterAddOn.
        self.assertNotIn("filterAddOn", agent)
        self.assertEqual(
            agent["fabricDataAgentParameters"],
            {"workspaceId": "ws-guid-2", "dataAgentId": "da-guid-2"},
        )

        kb_source_names = [
            s["name"] for s in search_definitions["knowledgeBases"][0]["knowledgeSources"]
        ]
        self.assertIn("fabric-data-agent-ks", kb_source_names)

    def test_settings_defaults_web_grounding_disabled_and_empty(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                "RETRIEVAL_BACKEND": "foundry_iq",
            },
        )
        self.assertEqual(settings["WEB_GROUNDING_ENABLED"], "false")
        self.assertEqual(settings["WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME"], "")
        self.assertEqual(settings["WEB_GROUNDING_ALLOWED_DOMAINS"], "")
        self.assertEqual(settings["WEB_GROUNDING_BLOCKED_DOMAINS"], "")

    def test_web_grounding_disabled_by_default_produces_no_entry(self):
        _, context = self._foundry_iq_context()
        search_definitions = render_json_template("search.j2", context)
        for ks in search_definitions["knowledgeSources"]:
            self.assertNotEqual(ks["kind"], "web")
        kb_source_names = [
            s["name"] for s in search_definitions["knowledgeBases"][0]["knowledgeSources"]
        ]
        self.assertNotIn("web-ks", kb_source_names)

    def test_web_grounding_enabled_without_name_produces_no_entry(self):
        _, context = self._foundry_iq_context(
            WEB_GROUNDING_ENABLED="true",
            WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME="",
        )
        search_definitions = render_json_template("search.j2", context)
        for ks in search_definitions["knowledgeSources"]:
            self.assertNotEqual(ks["kind"], "web")

    def test_web_grounding_enabled_adds_knowledge_source_and_kb_reference(self):
        _, context = self._foundry_iq_context(
            WEB_GROUNDING_ENABLED="true",
            WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME="web-ks",
            WEB_GROUNDING_ALLOWED_DOMAINS="Learn.Microsoft.com, azure.microsoft.com",
            WEB_GROUNDING_BLOCKED_DOMAINS="example.com",
        )
        search_definitions = render_json_template("search.j2", context)

        web_sources = [
            ks
            for ks in search_definitions["knowledgeSources"]
            if ks["kind"] == "web"
        ]
        self.assertEqual(len(web_sources), 1)
        web = web_sources[0]
        self.assertEqual(web["name"], "web-ks")
        self.assertEqual(web["kind"], "web")
        self.assertIsNone(web["encryptionKey"])
        # Public data - no ACL, no filterAddOn.
        self.assertNotIn("filterAddOn", web)
        self.assertEqual(
            web["webParameters"],
            {
                "domains": {
                    "allowedDomains": ["learn.microsoft.com", "azure.microsoft.com"],
                    "blockedDomains": ["example.com"],
                }
            },
        )

        kb_source_names = [
            s["name"] for s in search_definitions["knowledgeBases"][0]["knowledgeSources"]
        ]
        self.assertIn("web-ks", kb_source_names)

    def test_web_grounding_enabled_without_domains_emits_empty_lists(self):
        _, context = self._foundry_iq_context(
            WEB_GROUNDING_ENABLED="true",
            WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME="web-ks",
        )
        search_definitions = render_json_template("search.j2", context)
        web_sources = [
            ks
            for ks in search_definitions["knowledgeSources"]
            if ks["kind"] == "web"
        ]
        self.assertEqual(len(web_sources), 1)
        self.assertEqual(
            web_sources[0]["webParameters"],
            {"domains": {"allowedDomains": [], "blockedDomains": []}},
        )


class FoundryIqMcpTemplateTests(unittest.TestCase):
    """Generic MCP Server knowledge sources are opt-in and default-off.
    Rendered output must be unchanged when the feature is disabled.
    """

    def _foundry_iq_context(self, **overrides):
        settings_input = {
            "RESOURCE_TOKEN": "abc123",
            "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
            "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
            "RETRIEVAL_BACKEND": "foundry_iq",
        }
        settings_input.update(overrides)
        settings = render_json_template("search.settings.j2", settings_input)
        return settings, {
            **settings,
            "STORAGE_ACCOUNT_RESOURCE_ID": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st",
            "EMBEDDING_MODEL_INFO": {
                "endpoint": "https://aif-abc123.openai.azure.com/",
                "deployment_name": "text-embedding",
                "model_name": "text-embedding-3-large",
            },
            "GPT_MODEL_INFO": {
                "deployment_name": "chat",
                "model_name": "gpt-5-nano",
            },
        }

    def _mcp_source(self, **overrides):
        source = {
            "name": "monitor-mcp-ks",
            "description": "Azure Monitor MCP",
            "serverURL": "https://monitor-mcp.contoso.com/mcp",
            "tools": [
                {
                    "name": "query_logs",
                    "outputParsing": {"kind": "auto"},
                    "inclusionMode": "reranked",
                    "maxOutputTokens": 4096,
                }
            ],
        }
        source.update(overrides)
        return source

    def _query_headers(self):
        return [
            {
                "name": "Authorization",
                "valueFrom": {
                    "kind": "managedIdentity",
                    "scope": "api://monitor/.default",
                },
            },
            {
                "name": "x-user-token",
                "valueFrom": {
                    "kind": "obo",
                    "scope": "api://monitor/user_impersonation",
                },
            },
            {
                "name": "x-api-key",
                "valueFrom": {
                    "kind": "keyVaultSecret",
                    "secretName": "monitor-api-key",
                },
            },
            {"name": "x-no-auth", "valueFrom": {"kind": "none"}},
        ]

    def test_settings_defaults_mcp_disabled_and_empty(self):
        settings = render_json_template(
            "search.settings.j2",
            {
                "RESOURCE_TOKEN": "abc123",
                "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
                "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
                "RETRIEVAL_BACKEND": "foundry_iq",
            },
        )
        self.assertEqual(settings["FOUNDRY_IQ_MCP_ENABLED"], "false")
        self.assertEqual(settings["FOUNDRY_IQ_MCP_SOURCES_JSON"], [])
        self.assertEqual(settings["FOUNDRY_IQ_MCP_REASONING_EFFORT"], "low")
        self.assertEqual(settings["FOUNDRY_IQ_MCP_TRUSTED_HOSTS"], "")
        self.assertEqual(settings["FOUNDRY_IQ_MCP_LOG_TOOL_ARGUMENTS"], "false")

    def test_mcp_disabled_by_default_produces_no_entry_and_preserves_minimal_reasoning(self):
        _, context = self._foundry_iq_context()
        search_definitions = render_json_template("search.j2", context)
        for ks in search_definitions["knowledgeSources"]:
            self.assertNotEqual(ks["kind"], "mcpServer")
        kb = search_definitions["knowledgeBases"][0]
        self.assertNotIn("monitor-mcp-ks", [s["name"] for s in kb["knowledgeSources"]])
        self.assertEqual(kb["models"], [])
        self.assertEqual(kb["retrievalReasoningEffort"], {"kind": "minimal"})

    def test_mcp_enabled_without_sources_produces_no_entry(self):
        _, context = self._foundry_iq_context(FOUNDRY_IQ_MCP_ENABLED="true")
        search_definitions = render_json_template("search.j2", context)
        for ks in search_definitions["knowledgeSources"]:
            self.assertNotEqual(ks["kind"], "mcpServer")
        kb = search_definitions["knowledgeBases"][0]
        self.assertEqual(kb["models"], [])
        self.assertEqual(kb["retrievalReasoningEffort"], {"kind": "minimal"})

    def test_mcp_enabled_registers_source_with_kb_planning_model_and_reasoning(self):
        _, context = self._foundry_iq_context(
            FOUNDRY_IQ_MCP_ENABLED="true",
            FOUNDRY_IQ_MCP_REASONING_EFFORT="medium",
        )
        context["FOUNDRY_IQ_MCP_SOURCES_JSON"] = [
            self._mcp_source(
                failOnError=False,
                maxOutputDocuments=25,
                queryHeaders=self._query_headers(),
            )
        ]
        search_definitions = render_json_template("search.j2", context)

        mcp_sources = [ks for ks in search_definitions["knowledgeSources"] if ks["kind"] == "mcpServer"]
        self.assertEqual(len(mcp_sources), 1)
        source = mcp_sources[0]
        self.assertEqual(source["name"], "monitor-mcp-ks")
        self.assertIsNone(source["encryptionKey"])
        self.assertEqual(
            source["mcpServerParameters"],
            {
                "serverURL": "https://monitor-mcp.contoso.com/mcp",
                "tools": [
                    {
                        "name": "query_logs",
                        "outputParsing": {"kind": "auto"},
                        "inclusionMode": "reranked",
                        "maxOutputTokens": 4096,
                    }
                ],
            },
        )
        # Runtime query-header metadata must never be forwarded into Search
        # registration or knowledge-base retrieve parameters.
        self.assertNotIn("queryHeaders", json.dumps(source))
        self.assertNotIn("queryHeaders", json.dumps(search_definitions["knowledgeBases"]))
        self.assertNotIn("auth", source["mcpServerParameters"])
        self.assertNotIn("authentication", source["mcpServerParameters"])
        self.assertNotIn("authIdentity", source["mcpServerParameters"])

        kb = search_definitions["knowledgeBases"][0]
        self.assertIn("monitor-mcp-ks", [s["name"] for s in kb["knowledgeSources"]])
        # Never emit alwaysQuerySource for MCP knowledge source references.
        mcp_ref = next(s for s in kb["knowledgeSources"] if s["name"] == "monitor-mcp-ks")
        self.assertEqual(mcp_ref, {"name": "monitor-mcp-ks"})

        self.assertEqual(
            kb["models"],
            [
                {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": context["FOUNDRY_IQ_AI_SERVICES_ENDPOINT"],
                        "deploymentId": "chat",
                        "modelName": "gpt-5-nano",
                    },
                }
            ],
        )
        self.assertEqual(kb["retrievalReasoningEffort"], {"kind": "medium"})

    def test_mcp_tool_output_parsing_kinds_render_as_official_rest_shapes(self):
        """auto/none/split render as {"kind": "..."}; json nests documentsPath
        under jsonParameters, matching Search API 2026-05-01-preview
        (McpServerOutputParsing / McpServerJsonOutputParsing)."""
        _, context = self._foundry_iq_context(FOUNDRY_IQ_MCP_ENABLED="true")
        context["FOUNDRY_IQ_MCP_SOURCES_JSON"] = [
            self._mcp_source(
                tools=[
                    {
                        "name": "auto_tool",
                        "outputParsing": {"kind": "auto"},
                        "inclusionMode": "reranked",
                        "maxOutputTokens": 1024,
                    },
                    {
                        "name": "none_tool",
                        "outputParsing": {"kind": "none"},
                        "inclusionMode": "reranked",
                        "maxOutputTokens": 1024,
                    },
                    {
                        "name": "split_tool",
                        "outputParsing": {
                            "kind": "split",
                            "splitParameters": {
                                "textSplitMode": "pages",
                                "maximumPageLength": 4000,
                                "pageOverlapLength": 500,
                                "maximumPagesToTake": 10,
                                "defaultLanguageCode": "en",
                            },
                        },
                        "inclusionMode": "reranked",
                        "maxOutputTokens": 1024,
                    },
                    {
                        "name": "json_tool",
                        "outputParsing": {
                            "kind": "json",
                            "jsonParameters": {
                                "documentsPath": "$.results",
                                "includeContext": True,
                            },
                        },
                        "inclusionMode": "always",
                        "maxOutputTokens": 2048,
                    },
                ]
            )
        ]
        search_definitions = render_json_template("search.j2", context)
        tools = search_definitions["knowledgeSources"][-1]["mcpServerParameters"]["tools"]
        rendered = {tool["name"]: tool for tool in tools}

        self.assertEqual(rendered["auto_tool"]["outputParsing"], {"kind": "auto"})
        self.assertEqual(rendered["none_tool"]["outputParsing"], {"kind": "none"})
        self.assertEqual(
            rendered["split_tool"]["outputParsing"],
            {
                "kind": "split",
                "splitParameters": {
                    "textSplitMode": "pages",
                    "maximumPageLength": 4000,
                    "pageOverlapLength": 500,
                    "maximumPagesToTake": 10,
                    "defaultLanguageCode": "en",
                },
            },
        )
        self.assertEqual(
            rendered["json_tool"]["outputParsing"],
            {
                "kind": "json",
                "jsonParameters": {
                    "documentsPath": "$.results",
                    "includeContext": True,
                },
            },
        )
        # documentsPath must never be a tool-level sibling key.
        for tool in tools:
            self.assertNotIn("documentsPath", tool)

    def test_canonical_fixture_shared_with_runtime_validates_and_renders(self):
        _, context = self._foundry_iq_context(FOUNDRY_IQ_MCP_ENABLED="true")
        manifest = json.loads((REPO_ROOT / "manifest.json").read_text(encoding="utf-8"))
        orchestrator = next(
            component
            for component in manifest["components"]
            if component["name"] == "agent-app-orchestrator"
        )
        self.assertGreaterEqual(
            version_tuple(orchestrator["tag"]),
            version_tuple(MCP_RUNTIME_CONTRACT_MIN_VERSION),
        )

        fixture_path = (
            FIXTURE_DIR
            / f"foundry_iq_mcp_canonical_source_{MCP_FIXTURE_CONTRACT_VERSION.removeprefix('v').replace('.', '_')}.json"
        )
        source = json.loads(fixture_path.read_text(encoding="utf-8"))
        context["FOUNDRY_IQ_MCP_TRUSTED_HOSTS"] = "mcp.contoso.com"
        context["FOUNDRY_IQ_MCP_SOURCES_JSON"] = [source]

        mcp_setup.validate_foundry_iq_mcp_settings(context)
        self.assertEqual(context["FOUNDRY_IQ_MCP_SOURCES_JSON"], [source])

        search_definitions = render_json_template("search.j2", context)
        rendered_source = next(
            knowledge_source
            for knowledge_source in search_definitions["knowledgeSources"]
            if knowledge_source["name"] == source["name"]
        )
        self.assertEqual(
            rendered_source["mcpServerParameters"],
            {
                "serverURL": source["serverURL"],
                "tools": source["tools"],
            },
        )

    def test_multiple_mcp_sources_all_registered_and_referenced(self):
        _, context = self._foundry_iq_context(FOUNDRY_IQ_MCP_ENABLED="true")
        context["FOUNDRY_IQ_MCP_SOURCES_JSON"] = [
            self._mcp_source(name="monitor-mcp-ks", serverURL="https://monitor-mcp.contoso.com/mcp"),
            self._mcp_source(name="billing-mcp-ks", serverURL="https://billing-mcp.contoso.com/mcp"),
        ]
        search_definitions = render_json_template("search.j2", context)

        mcp_names = [
            ks["name"] for ks in search_definitions["knowledgeSources"] if ks["kind"] == "mcpServer"
        ]
        self.assertEqual(mcp_names, ["monitor-mcp-ks", "billing-mcp-ks"])

        kb_names = [s["name"] for s in search_definitions["knowledgeBases"][0]["knowledgeSources"]]
        self.assertIn("monitor-mcp-ks", kb_names)
        self.assertIn("billing-mcp-ks", kb_names)

    def test_mcp_coexists_with_web_grounding_and_sharepoint_indexed(self):
        _, context = self._foundry_iq_context(
            FOUNDRY_IQ_MCP_ENABLED="true",
            WEB_GROUNDING_ENABLED="true",
            WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME="web-ks",
            SHAREPOINT_INDEXED_ENABLED="true",
            SHAREPOINT_INDEXED_KNOWLEDGE_SOURCE_NAME="sp-ks",
            SHAREPOINT_INDEXED_INDEX_NAME="sp-index",
            SHAREPOINT_INDEXED_SITE_URL="https://contoso.sharepoint.com/sites/eng",
            SHAREPOINT_INDEXED_TENANT_ID="tenant-guid",
        )
        context["FOUNDRY_IQ_MCP_SOURCES_JSON"] = [self._mcp_source()]
        search_definitions = render_json_template("search.j2", context)

        kinds = {ks["kind"] for ks in search_definitions["knowledgeSources"]}
        self.assertTrue({"azureBlob", "web", "indexedSharePoint", "mcpServer"}.issubset(kinds))

        kb_names = [s["name"] for s in search_definitions["knowledgeBases"][0]["knowledgeSources"]]
        self.assertIn("web-ks", kb_names)
        self.assertIn("sp-ks", kb_names)
        self.assertIn("monitor-mcp-ks", kb_names)

    def test_rendering_is_deterministic(self):
        _, context = self._foundry_iq_context(FOUNDRY_IQ_MCP_ENABLED="true")
        context["FOUNDRY_IQ_MCP_SOURCES_JSON"] = [
            self._mcp_source(name="monitor-mcp-ks"),
            self._mcp_source(name="billing-mcp-ks", serverURL="https://billing-mcp.contoso.com/mcp"),
        ]
        first = render_json_template("search.j2", context)
        second = render_json_template("search.j2", context)
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))


class FoundryIqMcpValidationTests(unittest.TestCase):
    """Unit tests for the fail-closed validation in foundry_iq_mcp_setup."""

    def _context(self, sources=None, **overrides):
        context = {
            "RETRIEVAL_BACKEND": "foundry_iq",
            "FOUNDRY_IQ_MCP_ENABLED": "true",
            "FOUNDRY_IQ_MCP_SOURCES_JSON": sources if sources is not None else [],
            "FOUNDRY_IQ_MCP_TRUSTED_HOSTS": "monitor-mcp.contoso.com",
            "FOUNDRY_IQ_MCP_REASONING_EFFORT": "low",
            "GPT_MODEL_INFO": {"deployment_name": "chat", "model_name": "gpt-5-nano"},
            "FOUNDRY_IQ_AI_SERVICES_ENDPOINT": "https://aif-abc123.services.ai.azure.com/",
        }
        context.update(overrides)
        return context

    def _source(self, **overrides):
        source = {
            "name": "monitor-mcp-ks",
            "serverURL": "https://monitor-mcp.contoso.com/mcp",
            "tools": [
                {
                    "name": "query_logs",
                    "outputParsing": {"kind": "auto"},
                    "inclusionMode": "reranked",
                    "maxOutputTokens": 4096,
                }
            ],
        }
        source.update(overrides)
        return source

    def _query_headers(self):
        return [
            {
                "name": "Authorization",
                "valueFrom": {
                    "kind": "managedIdentity",
                    "scope": "api://monitor/.default",
                },
            },
            {
                "name": "x-user-token",
                "valueFrom": {
                    "kind": "obo",
                    "scope": "api://monitor/user_impersonation",
                },
            },
            {
                "name": "x-api-key",
                "valueFrom": {
                    "kind": "keyVaultSecret",
                    "secretName": "monitor-api-key",
                },
            },
            {"name": "x-no-auth", "valueFrom": {"kind": "none"}},
        ]

    def test_valid_query_header_metadata_is_preserved_in_canonical_json(self):
        source = self._source(queryHeaders=self._query_headers())
        context = self._context(sources=[source])

        canonical = mcp_setup.validate_and_get_mcp_sources(context)

        self.assertEqual(canonical[0]["queryHeaders"], self._query_headers())
        serialized = json.dumps(canonical)
        self.assertNotIn("literal-secret", serialized)
        self.assertNotIn('"value":', serialized)

    def test_query_headers_reject_literal_and_nested_credentials_without_echoing_values(self):
        cases = {
            "literal value": {
                "name": "Authorization",
                "value": "literal-secret-marker",
                "valueFrom": {
                    "kind": "managedIdentity",
                    "scope": "api://monitor/.default",
                },
            },
            "nested token": {
                "name": "Authorization",
                "valueFrom": {
                    "kind": "managedIdentity",
                    "scope": "api://monitor/.default",
                    "access_token": "literal-secret-marker",
                },
            },
            "headers blob": {
                "name": "x-custom",
                "valueFrom": {
                    "kind": "none",
                    "storedHeaders": {"x-api-key": "literal-secret-marker"},
                },
            },
            "connection string": {
                "name": "x-custom",
                "valueFrom": {
                    "kind": "none",
                    "connection-string": "literal-secret-marker",
                },
            },
        }
        for name, query_header in cases.items():
            with self.subTest(name=name):
                context = self._context(
                    sources=[self._source(queryHeaders=[query_header])]
                )
                with self.assertRaises(ValueError) as exc_info:
                    mcp_setup.validate_and_get_mcp_sources(context)
                self.assertIn("literal credentials", str(exc_info.exception))
                self.assertNotIn("literal-secret-marker", str(exc_info.exception))

    def test_query_headers_reject_forbidden_names_and_invalid_value_from_shapes(self):
        cases = {
            "invalid token": {
                "name": "bad header",
                "valueFrom": {"kind": "none"},
            },
            "host": {
                "name": "Host",
                "valueFrom": {"kind": "none"},
            },
            "content length": {
                "name": "Content-Length",
                "valueFrom": {"kind": "none"},
            },
            "hop by hop": {
                "name": "Connection",
                "valueFrom": {"kind": "none"},
            },
            "managed identity missing scope": {
                "name": "Authorization",
                "valueFrom": {"kind": "managedIdentity"},
            },
            "obo with secretName": {
                "name": "Authorization",
                "valueFrom": {
                    "kind": "obo",
                    "scope": "api://monitor/user_impersonation",
                    "secretName": "not-applicable",
                },
            },
            "key vault with scope": {
                "name": "x-api-key",
                "valueFrom": {
                    "kind": "keyVaultSecret",
                    "scope": "api://not-applicable",
                    "secretName": "monitor-api-key",
                },
            },
            "none with credential field": {
                "name": "x-none",
                "valueFrom": {"kind": "none", "scope": "api://not-applicable"},
            },
            "unknown nested field": {
                "name": "x-custom",
                "valueFrom": {"kind": "none", "issuer": "contoso"},
            },
        }
        for name, query_header in cases.items():
            with self.subTest(name=name):
                context = self._context(
                    sources=[self._source(queryHeaders=[query_header])]
                )
                with self.assertRaises(ValueError):
                    mcp_setup.validate_and_get_mcp_sources(context)

    def test_duplicate_query_header_names_are_rejected_case_insensitively(self):
        headers = [
            {"name": "X-Custom", "valueFrom": {"kind": "none"}},
            {"name": "x-custom", "valueFrom": {"kind": "none"}},
        ]
        context = self._context(sources=[self._source(queryHeaders=headers)])
        with self.assertRaisesRegex(ValueError, "unique"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_disabled_is_a_no_op(self):
        context = self._context(sources=[], FOUNDRY_IQ_MCP_ENABLED="false")
        mcp_setup.validate_foundry_iq_mcp_settings(context)  # must not raise

    def test_enabled_with_no_sources_raises(self):
        context = self._context(sources=[])
        with self.assertRaisesRegex(ValueError, "no sources"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_missing_planning_model_raises(self):
        context = self._context(sources=[self._source()], GPT_MODEL_INFO={})
        with self.assertRaisesRegex(ValueError, "planning model"):
            mcp_setup.validate_foundry_iq_mcp_settings(context)

    def test_missing_ai_services_endpoint_raises(self):
        context = self._context(sources=[self._source()], FOUNDRY_IQ_AI_SERVICES_ENDPOINT="")
        with self.assertRaisesRegex(ValueError, "AI Services endpoint"):
            mcp_setup.validate_foundry_iq_mcp_settings(context)

    def test_invalid_sources_json_type_raises(self):
        context = self._context(sources={"not": "a list"})
        with self.assertRaisesRegex(ValueError, "JSON array"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_duplicate_source_names_raise(self):
        context = self._context(
            sources=[self._source(), self._source(name="MONITOR-MCP-KS")]
        )
        with self.assertRaisesRegex(ValueError, "used more than once"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_invalid_source_name_raises_before_search_api_use(self):
        context = self._context(sources=[self._source(name="../indexes/victim")])
        with self.assertRaisesRegex(ValueError, "must start with a letter or number"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_non_https_scheme_raises(self):
        context = self._context(sources=[self._source(serverURL="http://monitor-mcp.contoso.com/mcp")])
        with self.assertRaisesRegex(ValueError, "https"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_malformed_port_raises(self):
        context = self._context(
            sources=[self._source(serverURL="https://monitor-mcp.contoso.com:notaport/mcp")]
        )
        with self.assertRaisesRegex(ValueError, "not a valid URL"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_userinfo_in_url_raises(self):
        context = self._context(
            sources=[self._source(serverURL="https://user:pass@monitor-mcp.contoso.com/mcp")]
        )
        with self.assertRaisesRegex(ValueError, "userinfo"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_fragment_in_url_raises(self):
        context = self._context(sources=[self._source(serverURL="https://monitor-mcp.contoso.com/mcp#frag")])
        with self.assertRaisesRegex(ValueError, "fragment"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_query_string_in_url_raises(self):
        for server_url in (
            "https://monitor-mcp.contoso.com/mcp?api-version=1",
            "https://monitor-mcp.contoso.com/mcp?",
        ):
            with self.subTest(server_url=server_url):
                context = self._context(sources=[self._source(serverURL=server_url)])
                with self.assertRaisesRegex(ValueError, "query string"):
                    mcp_setup.validate_and_get_mcp_sources(context)

    def test_source_scan_precedes_planning_model_validation(self):
        context = self._context(
            sources=[self._source(auth={"kind": "managedIdentity"})],
            GPT_MODEL_INFO={},
        )
        with self.assertRaisesRegex(ValueError, "not allowed"):
            mcp_setup.validate_foundry_iq_mcp_settings(context)

    def test_disabled_stale_source_content_is_discarded_without_parsing(self):
        context = self._context(
            sources="{not valid JSON",
            FOUNDRY_IQ_MCP_ENABLED="false",
        )
        mcp_setup.validate_foundry_iq_mcp_settings(context)
        self.assertEqual(context["FOUNDRY_IQ_MCP_SOURCES_JSON"], [])

    def test_ip_literal_host_raises(self):
        context = self._context(
            sources=[self._source(serverURL="https://203.0.113.10/mcp")],
            FOUNDRY_IQ_MCP_TRUSTED_HOSTS="203.0.113.10",
        )
        with self.assertRaisesRegex(ValueError, "IP literal"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_loopback_ip_literal_host_raises(self):
        context = self._context(
            sources=[self._source(serverURL="https://127.0.0.1/mcp")],
            FOUNDRY_IQ_MCP_TRUSTED_HOSTS="127.0.0.1",
        )
        with self.assertRaisesRegex(ValueError, "IP literal"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_localhost_host_raises(self):
        context = self._context(
            sources=[self._source(serverURL="https://localhost/mcp")],
            FOUNDRY_IQ_MCP_TRUSTED_HOSTS="localhost",
        )
        with self.assertRaisesRegex(ValueError, "local or reserved"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_reserved_or_single_label_host_raises(self):
        for host in (
            "home.arpa",
            "mcp.internal",
            "mcp.example",
            "mcp.corp",
            "mcp.intranet",
            "mcp.private",
            "mcp.123",
            "singlelabel",
        ):
            with self.subTest(host=host):
                context = self._context(
                    sources=[self._source(serverURL=f"https://{host}/mcp")],
                    FOUNDRY_IQ_MCP_TRUSTED_HOSTS=host,
                )
                with self.assertRaisesRegex(ValueError, "local or reserved"):
                    mcp_setup.validate_and_get_mcp_sources(context)

    def test_host_not_in_trusted_allowlist_raises(self):
        context = self._context(
            sources=[self._source()],
            FOUNDRY_IQ_MCP_TRUSTED_HOSTS="other-host.contoso.com",
        )
        with self.assertRaisesRegex(ValueError, "not an exact match"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_empty_trusted_hosts_raises(self):
        context = self._context(sources=[self._source()], FOUNDRY_IQ_MCP_TRUSTED_HOSTS="")
        with self.assertRaisesRegex(ValueError, "TRUSTED_HOSTS is empty"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_trusted_hosts_accept_runtime_json_array_shape(self):
        context = self._context(
            sources=[self._source()],
            FOUNDRY_IQ_MCP_TRUSTED_HOSTS='["monitor-mcp.contoso.com"]',
        )
        self.assertEqual(
            mcp_setup.validate_and_get_mcp_sources(context)[0]["serverURL"],
            "https://monitor-mcp.contoso.com/mcp",
        )

    def test_trusted_hosts_reject_non_hostname_entries(self):
        for trusted_hosts in (
            "https://monitor-mcp.contoso.com",
            "monitor-mcp.contoso.com/mcp",
            "monitor-mcp.contoso.com:443",
        ):
            with self.subTest(trusted_hosts=trusted_hosts):
                context = self._context(
                    sources=[self._source()],
                    FOUNDRY_IQ_MCP_TRUSTED_HOSTS=trusted_hosts,
                )
                with self.assertRaisesRegex(ValueError, "hostnames only"):
                    mcp_setup.validate_and_get_mcp_sources(context)

    def test_no_tools_raises(self):
        context = self._context(sources=[self._source(tools=[])])
        with self.assertRaisesRegex(ValueError, "non-empty array"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_duplicate_tool_names_raise(self):
        tool = {
            "name": "query_logs",
            "outputParsing": {"kind": "auto"},
            "inclusionMode": "reranked",
            "maxOutputTokens": 100,
        }
        context = self._context(
            sources=[
                self._source(
                    tools=[tool, {**tool, "name": tool["name"].upper()}]
                )
            ]
        )
        with self.assertRaisesRegex(ValueError, "used more than once"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_invalid_inclusion_mode_raises(self):
        context = self._context(
            sources=[self._source(tools=[{**self._source()["tools"][0], "inclusionMode": "sometimes"}])]
        )
        with self.assertRaisesRegex(ValueError, "inclusionMode"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_invalid_output_parsing_raises(self):
        context = self._context(
            sources=[
                self._source(
                    tools=[
                        {
                            **self._source()["tools"][0],
                            "outputParsing": {"kind": "yaml"},
                        }
                    ]
                )
            ]
        )
        with self.assertRaisesRegex(ValueError, "outputParsing"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_legacy_string_output_parsing_is_rejected(self):
        context = self._context(
            sources=[
                self._source(
                    tools=[
                        {
                            **self._source()["tools"][0],
                            "outputParsing": "auto",
                        }
                    ]
                )
            ]
        )
        with self.assertRaisesRegex(ValueError, "JSON object"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_json_output_parsing_without_documents_path_raises(self):
        context = self._context(
            sources=[
                self._source(
                    tools=[
                        {
                            **self._source()["tools"][0],
                            "outputParsing": {"kind": "json"},
                        }
                    ]
                )
            ]
        )
        with self.assertRaisesRegex(ValueError, "jsonParameters"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_documents_path_with_non_json_output_parsing_raises(self):
        """documentsPath only has an effect (and is only rendered) nested
        under outputParsing.jsonParameters when outputParsing is 'json';
        silently accepting it for other kinds would mislead operators."""
        context = self._context(
            sources=[
                self._source(
                    tools=[
                        {
                            **self._source()["tools"][0],
                            "outputParsing": {
                                "kind": "auto",
                                "jsonParameters": {"documentsPath": "$.results"},
                            },
                        }
                    ]
                )
            ]
        )
        with self.assertRaisesRegex(ValueError, "jsonParameters"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_invalid_documented_output_parsing_parameters_raise(self):
        cases = [
            (
                "includeContext must be boolean",
                {
                    "kind": "json",
                    "jsonParameters": {
                        "documentsPath": "$.results",
                        "includeContext": "true",
                    },
                },
                "includeContext",
            ),
            (
                "JSON parameter keys are strict",
                {
                    "kind": "json",
                    "jsonParameters": {
                        "documentsPath": "$.results",
                        "unexpected": True,
                    },
                },
                "unexpected key",
            ),
            (
                "split parameters require split kind",
                {
                    "kind": "auto",
                    "splitParameters": {"textSplitMode": "pages"},
                },
                "splitParameters",
            ),
            (
                "split parameter keys are strict",
                {
                    "kind": "split",
                    "splitParameters": {"unit": "azureOpenAITokens"},
                },
                "unexpected key",
            ),
            (
                "split mode is constrained",
                {
                    "kind": "split",
                    "splitParameters": {"textSplitMode": "paragraphs"},
                },
                "textSplitMode",
            ),
            (
                "split lengths must be integers",
                {
                    "kind": "split",
                    "splitParameters": {"maximumPageLength": True},
                },
                "positive integer",
            ),
            (
                "split overlap must be smaller than page length",
                {
                    "kind": "split",
                    "splitParameters": {
                        "maximumPageLength": 100,
                        "pageOverlapLength": 100,
                    },
                },
                "less than maximumPageLength",
            ),
        ]

        for label, output_parsing, expected_error in cases:
            with self.subTest(label):
                context = self._context(
                    sources=[
                        self._source(
                            tools=[
                                {
                                    **self._source()["tools"][0],
                                    "outputParsing": output_parsing,
                                }
                            ]
                        )
                    ]
                )
                with self.assertRaisesRegex(ValueError, expected_error):
                    mcp_setup.validate_and_get_mcp_sources(context)

    def test_non_positive_max_output_tokens_raises(self):
        context = self._context(
            sources=[self._source(tools=[{**self._source()["tools"][0], "maxOutputTokens": 0}])]
        )
        with self.assertRaisesRegex(ValueError, "positive integer"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_max_output_tokens_above_local_cap_raises(self):
        context = self._context(
            sources=[self._source(tools=[{**self._source()["tools"][0], "maxOutputTokens": 20000}])]
        )
        with self.assertRaisesRegex(ValueError, "local cap"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_always_query_source_on_tool_raises(self):
        context = self._context(
            sources=[self._source(tools=[{**self._source()["tools"][0], "alwaysQuerySource": True}])]
        )
        with self.assertRaisesRegex(ValueError, "alwaysQuerySource"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_always_query_source_on_source_raises(self):
        context = self._context(sources=[self._source(alwaysQuerySource=True)])
        with self.assertRaisesRegex(ValueError, "alwaysQuerySource"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_foundry_connection_auth_raises(self):
        context = self._context(sources=[self._source(auth={"kind": "foundryConnection"})])
        with self.assertRaisesRegex(ValueError, "not allowed"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_secret_like_auth_key_raises(self):
        context = self._context(sources=[self._source(apiKey="not-a-real-secret")])
        with self.assertRaisesRegex(ValueError, "literal credentials"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_unsupported_auth_kind_raises(self):
        context = self._context(sources=[self._source(auth={"kind": "oauth2"})])
        with self.assertRaisesRegex(ValueError, "not allowed"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_managed_identity_auth_is_rejected(self):
        """auth is rejected outright, at any nesting depth, regardless of
        kind -- it is never rendered/forwarded, so even a would-be-safe
        {'kind': 'managedIdentity'} value must not be silently accepted."""
        context = self._context(sources=[self._source(auth={"kind": "managedIdentity"})])
        with self.assertRaisesRegex(ValueError, "not allowed"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_authentication_key_is_rejected(self):
        context = self._context(sources=[self._source(authentication={"kind": "foundryConnection"})])
        with self.assertRaisesRegex(ValueError, "not allowed"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_auth_nested_inside_tool_is_rejected(self):
        tool = {**self._source()["tools"][0], "auth": {"kind": "managedIdentity"}}
        context = self._context(sources=[self._source(tools=[tool])])
        with self.assertRaisesRegex(ValueError, "not allowed"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_secret_like_key_nested_inside_tool_is_rejected(self):
        tool = {**self._source()["tools"][0], "token": "not-a-real-token"}
        context = self._context(sources=[self._source(tools=[tool])])
        with self.assertRaisesRegex(ValueError, "literal credentials"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_secret_like_key_two_levels_deep_is_rejected(self):
        """The scan must recurse arbitrarily deep, not just one level."""
        tool = {**self._source()["tools"][0], "extra": {"nested": {"bearer": "not-a-real-token"}}}
        context = self._context(sources=[self._source(tools=[tool])])
        with self.assertRaisesRegex(ValueError, "literal credentials"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_absent_auth_is_valid(self):
        context = self._context(sources=[self._source()])
        sources = mcp_setup.validate_and_get_mcp_sources(context)
        self.assertEqual(len(sources), 1)

    def test_unexpected_source_key_raises(self):
        context = self._context(sources=[self._source(unexpectedKey="value")])
        with self.assertRaisesRegex(ValueError, "unexpected key"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_runtime_retrieval_controls_are_validated_and_preserved(self):
        context = self._context(
            sources=[
                self._source(
                    failOnError=False,
                    maxOutputDocuments=25,
                )
            ]
        )

        sources = mcp_setup.validate_and_get_mcp_sources(context)

        self.assertFalse(sources[0]["failOnError"])
        self.assertEqual(sources[0]["maxOutputDocuments"], 25)

    def test_invalid_runtime_retrieval_controls_raise(self):
        cases = [
            ({"failOnError": "false"}, "failOnError"),
            ({"failOnError": None}, "failOnError"),
            ({"maxOutputDocuments": True}, "maxOutputDocuments"),
            ({"maxOutputDocuments": 0}, "maxOutputDocuments"),
            ({"maxOutputDocuments": 51}, "maxOutputDocuments"),
        ]
        for overrides, expected_error in cases:
            with self.subTest(overrides=overrides):
                context = self._context(sources=[self._source(**overrides)])
                with self.assertRaisesRegex(ValueError, expected_error):
                    mcp_setup.validate_and_get_mcp_sources(context)

    def test_legacy_server_url_casing_is_rejected(self):
        source = self._source()
        source["serverUrl"] = source.pop("serverURL")
        context = self._context(sources=[source])
        with self.assertRaisesRegex(ValueError, "unexpected key"):
            mcp_setup.validate_and_get_mcp_sources(context)

    def test_invalid_reasoning_effort_raises(self):
        context = self._context(sources=[self._source()], FOUNDRY_IQ_MCP_REASONING_EFFORT="minimal")
        with self.assertRaisesRegex(ValueError, "REASONING_EFFORT"):
            mcp_setup.validate_and_get_mcp_sources(context)


class FoundryIqMcpPreflightCliTests(unittest.TestCase):
    """Unit tests for the standalone pre-flight CLI entry point
    (mcp_setup.main / build_preflight_context_from_environ). This is the
    module scripts/postProvision.ps1 runs before it imports anything into
    Azure App Configuration, so a rejected configuration here proves the
    ordering bug (import happening before validation) cannot recur: a
    non-zero exit here happens before any write."""

    BASE_ENV = {
        "RETRIEVAL_BACKEND": "foundry_iq",
        "FOUNDRY_IQ_MCP_ENABLED": "true",
        "FOUNDRY_IQ_MCP_TRUSTED_HOSTS": "monitor-mcp.contoso.com",
        "FOUNDRY_IQ_MCP_REASONING_EFFORT": "low",
    }

    def _sources_json(self, **overrides):
        source = {
            "name": "monitor-mcp-ks",
            "serverURL": "https://monitor-mcp.contoso.com/mcp",
            "tools": [
                {
                    "name": "query_logs",
                    "outputParsing": {"kind": "auto"},
                    "inclusionMode": "reranked",
                    "maxOutputTokens": 4096,
                }
            ],
        }
        source.update(overrides)
        return json.dumps([source])

    def _run_main(self, **env_overrides):
        env = {**self.BASE_ENV, **env_overrides}
        with patch.dict(os.environ, env, clear=False):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = mcp_setup.main()
        return result, stderr.getvalue()

    def test_disabled_by_default_returns_zero_without_error(self):
        result, stderr = self._run_main(FOUNDRY_IQ_MCP_ENABLED="false", FOUNDRY_IQ_MCP_SOURCES_JSON="[]")
        self.assertEqual(result, 0)
        self.assertEqual(stderr, "")

    def test_disabled_malformed_json_returns_zero_without_parsing(self):
        result, stderr = self._run_main(
            FOUNDRY_IQ_MCP_ENABLED="false",
            FOUNDRY_IQ_MCP_SOURCES_JSON="{not valid JSON",
        )
        self.assertEqual(result, 0)
        self.assertEqual(stderr, "")

    def test_disabled_credential_json_returns_zero_without_scanning(self):
        result, stderr = self._run_main(
            FOUNDRY_IQ_MCP_ENABLED="false",
            FOUNDRY_IQ_MCP_SOURCES_JSON='[{"auth":{"kind":"foundryConnection","token":"stale"}}]',
        )
        self.assertEqual(result, 0)
        self.assertEqual(stderr, "")

    def test_valid_configuration_returns_zero(self):
        result, stderr = self._run_main(FOUNDRY_IQ_MCP_SOURCES_JSON=self._sources_json())
        self.assertEqual(result, 0)
        self.assertEqual(stderr, "")

    def test_valid_configuration_emits_canonical_json_for_app_configuration(self):
        query_headers = [
            {
                "name": " Authorization ",
                "valueFrom": {
                    "kind": "managedIdentity",
                    "scope": " api://monitor/.default ",
                },
            },
            {
                "name": "x-api-key",
                "valueFrom": {
                    "kind": "keyVaultSecret",
                    "secretName": "monitor-api-key",
                },
            },
        ]
        env = {
            **self.BASE_ENV,
            "FOUNDRY_IQ_MCP_SOURCES_JSON": self._sources_json(
                failOnError=False,
                maxOutputDocuments=25,
                queryHeaders=query_headers,
            ),
        }
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict(os.environ, env, clear=False):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = mcp_setup.main(emit_canonical=True)

        self.assertEqual(result, 0)
        self.assertEqual(stderr.getvalue(), "")
        canonical = json.loads(stdout.getvalue())
        self.assertFalse(canonical[0]["failOnError"])
        self.assertEqual(canonical[0]["maxOutputDocuments"], 25)
        self.assertEqual(
            canonical[0]["queryHeaders"],
            [
                {
                    "name": "Authorization",
                    "valueFrom": {
                        "kind": "managedIdentity",
                        "scope": "api://monitor/.default",
                    },
                },
                {
                    "name": "x-api-key",
                    "valueFrom": {
                        "kind": "keyVaultSecret",
                        "secretName": "monitor-api-key",
                    },
                },
            ],
        )

    def test_malformed_json_returns_one_before_any_write(self):
        result, stderr = self._run_main(FOUNDRY_IQ_MCP_SOURCES_JSON="{not valid json")
        self.assertEqual(result, 1)
        self.assertIn("valid JSON", stderr)

    def test_auth_key_returns_one_before_any_write(self):
        """The exact regression scenario for the postProvision.ps1 ordering
        fix: an operator-supplied auth key must fail this gate (exit 1)
        before scripts/postProvision.ps1 ever imports
        FOUNDRY_IQ_MCP_SOURCES_JSON into App Configuration."""
        result, stderr = self._run_main(
            FOUNDRY_IQ_MCP_SOURCES_JSON=self._sources_json(auth={"kind": "managedIdentity"})
        )
        self.assertEqual(result, 1)
        self.assertIn("not allowed", stderr)

    def test_secret_like_key_returns_one_before_any_write(self):
        result, stderr = self._run_main(FOUNDRY_IQ_MCP_SOURCES_JSON=self._sources_json(apiKey="not-a-real-secret"))
        self.assertEqual(result, 1)
        self.assertIn("literal credentials", stderr)

    def test_untrusted_host_returns_one_before_any_write(self):
        result, stderr = self._run_main(
            FOUNDRY_IQ_MCP_SOURCES_JSON=self._sources_json(),
            FOUNDRY_IQ_MCP_TRUSTED_HOSTS="other-host.contoso.com",
        )
        self.assertEqual(result, 1)
        self.assertIn("not an exact match", stderr)

    def test_module_has_no_azure_sdk_dependency(self):
        """Regression guard: this module must never itself write to Azure
        App Configuration (or import an SDK capable of it), so it can be run
        as a pure pre-flight gate with only the system Python interpreter,
        before scripts/postProvision.ps1 installs any pip dependency."""
        source = inspect.getsource(mcp_setup)
        self.assertNotIn("azure.appconfiguration", source)
        self.assertNotIn("AzureAppConfigurationClient", source)
        self.assertNotIn("import azure", source)


class PostProvisionMcpSourceGuardTests(unittest.TestCase):
    """Regression guards for the PowerShell validation/write ordering."""

    SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "postProvision.ps1"

    def test_disabled_path_skips_source_read_and_writes_safe_defaults(self):
        script = self.SCRIPT.read_text(encoding="utf-8")
        flag = script.index("$mcpEnabled = Test-Truthy")
        preflight = script.index(
            "Invoke-PythonModule -ModuleName 'config.search.foundry_iq_mcp_setup'"
        )
        canonical_output = script.index(
            "-Arguments @('--canonical')"
        )
        app_config_import = script.index("Set-AgentLzAppConfiguration -Endpoint")

        self.assertLess(flag, preflight)
        self.assertLess(preflight, canonical_output)
        self.assertLess(canonical_output, app_config_import)
        self.assertNotIn(
            "$mcpSourcesJson = Get-OptionalEnvValue 'FOUNDRY_IQ_MCP_SOURCES_JSON'",
            script,
        )
        self.assertIn("$mcpSourcesJson = '[]'", script)
        self.assertIn("$mcpReasoningEffort = 'low'", script)
        self.assertIn("$mcpTrustedHosts = ''", script)
        self.assertIn("$mcpLogToolArguments = 'false'", script)


class WorkIqPreflightTests(unittest.TestCase):
    def test_sharepoint_validation_never_drops_an_enabled_source(self):
        definitions = {
            "knowledgeSources": [{"name": "sharepoint-ks", "kind": "indexedSharePoint"}],
            "knowledgeBases": [{"name": "kb", "knowledgeSources": [{"name": "sharepoint-ks"}]}],
        }
        original = json.loads(json.dumps(definitions))
        with self.assertRaisesRegex(ValueError, "was not removed"):
            sharepoint_setup.filter_sharepoint_indexed_sources(
                definitions,
                {
                    "SHAREPOINT_INDEXED_ENABLED": "true",
                    "SHAREPOINT_INDEXED_KNOWLEDGE_SOURCE_NAME": "sharepoint-ks",
                },
            )
        self.assertEqual(definitions, original)
        sharepoint_setup.filter_sharepoint_indexed_sources(
            definitions, {"SHAREPOINT_INDEXED_ENABLED": "false"}
        )
        self.assertEqual(definitions, original)

    def test_consent_failure_precedes_search_mutation(self):
        context = {
            "RETRIEVAL_BACKEND": "foundry_iq",
            "WORK_IQ_ENABLED": "true",
            "WORK_IQ_KNOWLEDGE_SOURCE_NAME": "work-iq-ks",
            "WORK_IQ_APPLICATION_ID": "11111111-1111-1111-1111-111111111111",
            "WORK_IQ_FEDERATED_CREDENTIAL_ID": "22222222-2222-2222-2222-222222222222",
            "FOUNDRY_IQ_API_VERSION": "2026-08-01-preview",
            "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
            "SEARCH_API_VERSION": "2025-05-01-preview",
        }
        with (
            patch.object(setup, "check_work_iq_admin_consent", return_value=False),
            patch.object(setup, "ChainedTokenCredential"),
            patch.object(setup, "ensure_native_blob_private_links") as readiness,
            patch.object(setup, "prepare_index_updates") as prepare,
            patch.object(setup, "cleanup_knowledge_resources") as cleanup,
            self.assertRaisesRegex(RuntimeError, "Work IQ.*consent"),
        ):
            setup.execute_setup(
                {
                    "knowledgeSources": [{"name": "work-iq-ks", "kind": "workIQ"}],
                    "knowledgeBases": [{"name": "kb", "knowledgeSources": [{"name": "work-iq-ks"}]}],
                },
                context,
            )
        readiness.assert_not_called()
        prepare.assert_not_called()
        cleanup.assert_not_called()

    def test_incomplete_enabled_sources_fail_before_any_resource_discovery(self):
        for prefix in ("WORK_IQ", "FABRIC_IQ", "FABRIC_DATA_AGENT", "SHAREPOINT_INDEXED", "WEB_GROUNDING"):
            with self.subTest(prefix=prefix):
                with patch.object(setup, "ChainedTokenCredential") as credential:
                    with self.assertRaisesRegex(ValueError, "missing required settings"):
                        setup.execute_setup(
                            {},
                            {"RETRIEVAL_BACKEND": "foundry_iq", f"{prefix}_ENABLED": "true"},
                        )
                credential.assert_not_called()

    def test_enabled_source_cannot_be_omitted_from_rendered_payload(self):
        with self.assertRaisesRegex(ValueError, "absent from the rendered"):
            setup.validate_requested_knowledge_sources(
                {},
                {
                    "RETRIEVAL_BACKEND": "foundry_iq",
                    "WEB_GROUNDING_ENABLED": "true",
                    "WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME": "web-ks",
                },
            )

    def test_enabled_source_must_be_bound_to_the_selected_knowledge_base(self):
        definitions = {
            "knowledgeSources": [{"name": "web-ks", "kind": "web"}],
            "knowledgeBases": [{"name": "wrong-kb", "knowledgeSources": [{"name": "web-ks"}]}],
        }
        with self.assertRaisesRegex(ValueError, "not bound to the target"):
            setup.validate_requested_knowledge_sources(
                definitions,
                {
                    "RETRIEVAL_BACKEND": "foundry_iq",
                    "WEB_GROUNDING_ENABLED": "true",
                    "WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME": "web-ks",
                    "KNOWLEDGE_BASE_NAME": "selected-kb",
                },
            )

    def test_filter_work_iq_sources_no_op_when_disabled(self):
        defs = {
            "knowledgeSources": [
                {"name": "blob-ks", "kind": "azureBlob"},
            ],
            "knowledgeBases": [
                {"name": "kb", "knowledgeSources": [{"name": "blob-ks"}]},
            ],
        }
        setup.filter_work_iq_sources(
            defs,
            {"RETRIEVAL_BACKEND": "foundry_iq", "WORK_IQ_ENABLED": "false"},
            Mock(),
        )
        self.assertEqual(defs["knowledgeSources"], [{"name": "blob-ks", "kind": "azureBlob"}])
        self.assertEqual(defs["knowledgeBases"][0]["knowledgeSources"], [{"name": "blob-ks"}])

    def test_filter_work_iq_sources_fails_without_removing_unconsented_source(self):
        defs = {
            "knowledgeSources": [
                {"name": "blob-ks", "kind": "azureBlob"},
                {"name": "work-iq-ks", "kind": "workIQ"},
            ],
            "knowledgeBases": [
                {
                    "name": "kb",
                    "knowledgeSources": [{"name": "blob-ks"}, {"name": "work-iq-ks"}],
                }
            ],
        }
        credential = Mock()
        with patch.object(setup, "check_work_iq_admin_consent", return_value=False), self.assertRaisesRegex(
            RuntimeError, "Work IQ.*consent"
        ):
            setup.filter_work_iq_sources(
                defs,
                {
                    "RETRIEVAL_BACKEND": "foundry_iq",
                    "WORK_IQ_ENABLED": "true",
                    "WORK_IQ_KNOWLEDGE_SOURCE_NAME": "work-iq-ks",
                },
                credential,
            )
        self.assertEqual(
            [ks["name"] for ks in defs["knowledgeSources"]], ["blob-ks", "work-iq-ks"]
        )
        self.assertEqual(
            [ref["name"] for ref in defs["knowledgeBases"][0]["knowledgeSources"]],
            ["blob-ks", "work-iq-ks"],
        )

    def test_filter_work_iq_sources_keeps_source_when_consented(self):
        defs = {
            "knowledgeSources": [
                {"name": "work-iq-ks", "kind": "workIQ"},
            ],
            "knowledgeBases": [
                {"name": "kb", "knowledgeSources": [{"name": "work-iq-ks"}]}
            ],
        }
        with patch.object(setup, "check_work_iq_admin_consent", return_value=True):
            setup.filter_work_iq_sources(
                defs,
                {
                    "RETRIEVAL_BACKEND": "foundry_iq",
                    "WORK_IQ_ENABLED": "true",
                    "WORK_IQ_KNOWLEDGE_SOURCE_NAME": "work-iq-ks",
                },
                Mock(),
            )
        self.assertEqual([ks["name"] for ks in defs["knowledgeSources"]], ["work-iq-ks"])

    def test_filter_work_iq_sources_fails_without_removing_inconclusive_source(self):
        defs = {
            "knowledgeSources": [{"name": "work-iq-ks", "kind": "workIQ"}],
            "knowledgeBases": [
                {"name": "kb", "knowledgeSources": [{"name": "work-iq-ks"}]}
            ],
        }
        with patch.object(setup, "check_work_iq_admin_consent", return_value=None), self.assertRaisesRegex(
            RuntimeError, "Work IQ.*consent"
        ):
            setup.filter_work_iq_sources(
                defs,
                {
                    "RETRIEVAL_BACKEND": "foundry_iq",
                    "WORK_IQ_ENABLED": "true",
                    "WORK_IQ_KNOWLEDGE_SOURCE_NAME": "work-iq-ks",
                },
                Mock(),
            )
        self.assertEqual(defs["knowledgeSources"], [{"name": "work-iq-ks", "kind": "workIQ"}])
        self.assertEqual(
            defs["knowledgeBases"][0]["knowledgeSources"], [{"name": "work-iq-ks"}]
        )


class KnowledgeSourceNameUniquenessTests(unittest.TestCase):
    """Comprehensive collision coverage for
    setup.validate_unique_knowledge_source_names across every knowledge
    source kind search.j2 can render: Blob/Search Index, conversation
    Search Index, Work IQ, Fabric IQ, Fabric Data Agent, SharePoint Indexed,
    Web grounding, and MCP Server."""

    ALL_CATEGORIES = (
        "blob",
        "conversation",
        "work_iq",
        "fabric_iq",
        "fabric_data_agent",
        "sharepoint_indexed",
        "web_grounding",
        "mcp",
    )

    def _default_names(self, **overrides):
        names = {category: f"{category}-ks" for category in self.ALL_CATEGORIES}
        names.update(overrides)
        return names

    def _defs_with_all_categories_enabled(self, **name_overrides):
        names = self._default_names(**name_overrides)
        settings_input = {
            "RESOURCE_TOKEN": "abc123",
            "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
            "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
            "RETRIEVAL_BACKEND": "foundry_iq",
            "FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME": names["blob"],
            "FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED": "true",
            "FOUNDRY_IQ_CONVERSATION_KNOWLEDGE_SOURCE_NAME": names["conversation"],
            "WORK_IQ_ENABLED": "true",
            "WORK_IQ_KNOWLEDGE_SOURCE_NAME": names["work_iq"],
            "FABRIC_IQ_ENABLED": "true",
            "FABRIC_IQ_KNOWLEDGE_SOURCE_NAME": names["fabric_iq"],
            "FABRIC_IQ_WORKSPACE_ID": "workspace-1",
            "FABRIC_IQ_ONTOLOGY_ID": "ontology-1",
            "FABRIC_DATA_AGENT_ENABLED": "true",
            "FABRIC_DATA_AGENT_KNOWLEDGE_SOURCE_NAME": names["fabric_data_agent"],
            "FABRIC_DATA_AGENT_WORKSPACE_ID": "workspace-1",
            "FABRIC_DATA_AGENT_DATA_AGENT_ID": "agent-1",
            "SHAREPOINT_INDEXED_ENABLED": "true",
            "SHAREPOINT_INDEXED_KNOWLEDGE_SOURCE_NAME": names["sharepoint_indexed"],
            "SHAREPOINT_INDEXED_INDEX_NAME": "sp-index",
            "SHAREPOINT_INDEXED_SITE_URL": "https://contoso.sharepoint.com/sites/eng",
            "SHAREPOINT_INDEXED_TENANT_ID": "tenant-guid",
            "WEB_GROUNDING_ENABLED": "true",
            "WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME": names["web_grounding"],
            "FOUNDRY_IQ_MCP_ENABLED": "true",
        }
        settings = render_json_template("search.settings.j2", settings_input)
        context = {
            **settings,
            "STORAGE_ACCOUNT_RESOURCE_ID": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st",
            "EMBEDDING_MODEL_INFO": {
                "endpoint": "https://aif-abc123.openai.azure.com/",
                "deployment_name": "text-embedding",
                "model_name": "text-embedding-3-large",
            },
            "GPT_MODEL_INFO": {"deployment_name": "chat", "model_name": "gpt-5-nano"},
            "FOUNDRY_IQ_MCP_SOURCES_JSON": [
                {
                    "name": names["mcp"],
                    "serverURL": "https://mcp.contoso.com/mcp",
                    "tools": [
                        {
                            "name": "query",
                            "outputParsing": {"kind": "auto"},
                            "inclusionMode": "reranked",
                            "maxOutputTokens": 1024,
                        }
                    ],
                }
            ],
        }
        return render_json_template("search.j2", context)

    def test_all_categories_enabled_with_distinct_names_pass(self):
        defs = self._defs_with_all_categories_enabled()
        names = [ks["name"] for ks in defs["knowledgeSources"]]
        self.assertEqual(len(names), len(self.ALL_CATEGORIES))
        self.assertEqual(len(names), len(set(n.lower() for n in names)))
        setup.validate_unique_knowledge_source_names(defs)  # must not raise

    def test_exact_case_collision_across_every_category_pair_raises(self):
        for category_a, category_b in itertools.combinations(self.ALL_CATEGORIES, 2):
            with self.subTest(colliding=(category_a, category_b)):
                defs = self._defs_with_all_categories_enabled(**{category_b: f"{category_a}-ks"})
                with self.assertRaisesRegex(ValueError, "[Cc]ollides"):
                    setup.validate_unique_knowledge_source_names(defs)

    def test_case_insensitive_collision_raises(self):
        defs = self._defs_with_all_categories_enabled(mcp="BLOB-KS")
        with self.assertRaisesRegex(ValueError, "case-insensitive"):
            setup.validate_unique_knowledge_source_names(defs)

    def test_no_knowledge_sources_passes(self):
        setup.validate_unique_knowledge_source_names({"knowledgeSources": []})  # must not raise
        setup.validate_unique_knowledge_source_names({})  # must not raise

    def test_single_knowledge_source_passes(self):
        setup.validate_unique_knowledge_source_names({"knowledgeSources": [{"name": "blob-ks"}]})

    def test_two_distinct_names_pass(self):
        setup.validate_unique_knowledge_source_names(
            {"knowledgeSources": [{"name": "blob-ks"}, {"name": "mcp-ks"}]}
        )

    def test_duplicate_same_case_raises(self):
        with self.assertRaisesRegex(ValueError, "collides"):
            setup.validate_unique_knowledge_source_names(
                {"knowledgeSources": [{"name": "blob-ks"}, {"name": "blob-ks"}]}
            )


if __name__ == "__main__":
    unittest.main()
