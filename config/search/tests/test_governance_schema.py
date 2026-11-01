import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from config.search import setup


TEMPLATE_DIR = Path(__file__).resolve().parents[1]
PROVENANCE_FIELDS = {
    "provenance_id": ("Edm.String", {"filterable": True}),
    "source_uri_id": ("Edm.String", {"filterable": True}),
    "source_version_id": ("Edm.String", {"filterable": True}),
    "content_checksum_sha256": ("Edm.String", {"filterable": True}),
    "ingested_at": (
        "Edm.DateTimeOffset",
        {"filterable": True, "sortable": True},
    ),
    "ingest_run_id": ("Edm.String", {"filterable": True}),
    "data_classification": (
        "Edm.String",
        {"filterable": True, "facetable": True},
    ),
    "right_to_use": ("Edm.String", {"filterable": True, "facetable": True}),
    "retention_class": (
        "Edm.String",
        {"filterable": True, "facetable": True},
    ),
    "delete_after": (
        "Edm.String",
        {"filterable": True, "sortable": True},
    ),
}


def render(template_name, context):
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        undefined=StrictUndefined,
    )
    return json.loads(environment.get_template(template_name).render(**context))


def search_context():
    settings = render(
        "search.settings.j2",
        {
            "RESOURCE_TOKEN": "abc123",
            "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
            "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
            "RETRIEVAL_BACKEND": "foundry_iq",
        },
    )
    return {
        **settings,
        "STORAGE_ACCOUNT_RESOURCE_ID": (
            "/subscriptions/s/resourceGroups/rg/providers/"
            "Microsoft.Storage/storageAccounts/st"
        ),
        "EMBEDDING_MODEL_INFO": {
            "endpoint": "https://aif-abc123.openai.azure.com/",
            "deployment_name": "text-embedding",
            "model_name": "text-embedding-3-large",
        },
        "GPT_MODEL_INFO": {
            "deployment_name": "chat",
            "model_name": "gpt-5.2",
            "model_format": "OpenAI",
        },
    }


class GovernanceSearchSchemaTests(unittest.TestCase):
    def test_rag_index_contains_provenance_fields_with_safe_types(self):
        definitions = render("search.j2", search_context())
        rag_index = definitions["indexes"][0]
        fields = {field["name"]: field for field in rag_index["fields"]}
        self.assertIsInstance(fields["contentVector"]["dimensions"], int)

        for name, (expected_type, expected_attributes) in PROVENANCE_FIELDS.items():
            with self.subTest(name=name):
                self.assertEqual(fields[name]["type"], expected_type)
                self.assertTrue(fields[name]["retrievable"])
                self.assertFalse(fields[name]["searchable"])
                for attribute, expected_value in expected_attributes.items():
                    self.assertEqual(fields[name][attribute], expected_value)

    def test_additive_merge_preserves_documents_and_custom_fields(self):
        existing = {
            "@odata.etag": '"etag"',
            "name": "rag-index",
            "fields": [
                {"name": "id", "type": "Edm.String", "key": True},
                {"name": "operator_custom", "type": "Edm.String"},
            ],
            "semantic": {"configurations": [{"name": "operator-owned"}]},
        }
        desired = {
            "name": "rag-index",
            "fields": [
                {"name": "id", "type": "Edm.String", "key": True},
                {
                    "name": "provenance_id",
                    "type": "Edm.String",
                    "filterable": True,
                },
            ],
        }

        merged, added = setup.merge_additive_index_schema(existing, desired)

        self.assertEqual(added, ["provenance_id"])
        self.assertNotIn("@odata.etag", merged)
        self.assertIn(
            "operator_custom",
            {field["name"] for field in merged["fields"]},
        )
        self.assertEqual(
            merged["semantic"],
            {"configurations": [{"name": "operator-owned"}]},
        )

    def test_incompatible_existing_field_fails_without_mutation(self):
        existing = {
            "name": "rag-index",
            "fields": [
                {"name": "delete_after", "type": "Edm.DateTimeOffset"}
            ],
        }
        desired = {
            "name": "rag-index",
            "fields": [
                {"name": "delete_after", "type": "Edm.String"}
            ],
        }

        with self.assertRaisesRegex(ValueError, "existing index was not modified"):
            setup.merge_additive_index_schema(existing, desired)

        self.assertEqual(existing["fields"][0]["type"], "Edm.DateTimeOffset")

    def test_existing_index_permission_enforcement_is_reconciled_without_rebuild(self):
        desired = {
            "name": "rag-index",
            "permissionFilterOption": "enabled",
            "fields": [
                {
                    "name": "metadata_security_user_ids",
                    "type": "Collection(Edm.String)",
                    "filterable": True,
                    "permissionFilter": "userIds",
                }
            ],
        }
        for current_option in (None, "disabled", "enabled"):
            with self.subTest(current_option=current_option):
                existing = {
                    **desired,
                    "semantic": {"configurations": [{"name": "operator-owned"}]},
                }
                if current_option is None:
                    del existing["permissionFilterOption"]
                else:
                    existing["permissionFilterOption"] = current_option
                with patch.object(
                    setup, "get_search_resource", return_value=(existing, '"etag"')
                ):
                    updates = setup.prepare_index_updates(
                        {"indexes": [desired]},
                        Mock(),
                        "https://search.search.windows.net",
                        "2025-05-01-preview",
                    )
                _, body, added_fields, etag, if_none_match = updates[0]
                self.assertEqual(added_fields, [])
                self.assertEqual(etag, '"etag"')
                self.assertIsNone(if_none_match)
                self.assertEqual(existing.get("permissionFilterOption"), current_option)
                if current_option == "enabled":
                    self.assertIsNone(body)
                else:
                    self.assertEqual(body["permissionFilterOption"], "enabled")
                    self.assertEqual(body["semantic"], existing["semantic"])

    def test_incompatible_permission_annotation_blocks_upgrade(self):
        existing = {
            "fields": [
                {"name": "users", "type": "Collection(Edm.String)", "filterable": True}
            ]
        }
        desired = {
            "permissionFilterOption": "enabled",
            "fields": [
                {
                    **existing["fields"][0],
                    "permissionFilter": "userIds",
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "permissionFilter"):
            setup.merge_additive_index_schema(existing, desired)

    def test_existing_index_is_updated_with_put_and_never_deleted(self):
        credential = Mock()
        existing = {
            "name": "rag-index",
            "fields": [{"name": "id", "type": "Edm.String", "key": True}],
        }
        desired = {
            "name": "rag-index",
            "fields": [
                {"name": "id", "type": "Edm.String", "key": True},
                {
                    "name": "provenance_id",
                    "type": "Edm.String",
                    "filterable": True,
                },
            ],
        }

        with patch.object(
            setup,
            "get_search_resource",
            return_value=(existing, '"etag"'),
        ), patch.object(setup, "call_search_api", return_value=True) as call:
            setup.provision_indexes(
                {"indexes": [desired]},
                {},
                credential,
                "https://search.search.windows.net",
                "2025-09-01",
            )

        call.assert_called_once()
        self.assertEqual(call.call_args.args[4], "put")
        self.assertEqual(call.call_args.kwargs["if_match"], '"etag"')
        self.assertIsNone(call.call_args.kwargs["if_none_match"])
        self.assertNotIn(
            "delete",
            [argument for argument in call.call_args.args if isinstance(argument, str)],
        )

    def test_schema_preflight_fails_before_dependent_cleanup(self):
        definitions = {"indexes": [{"name": "rag-index", "fields": []}]}
        context = {
            "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
            "SEARCH_API_VERSION": "2025-09-01",
        }

        with patch.object(
            setup,
            "prepare_index_updates",
            side_effect=ValueError("incompatible"),
        ), patch.object(setup, "cleanup_knowledge_resources") as cleanup:
            with self.assertRaisesRegex(ValueError, "incompatible"):
                setup.execute_setup(definitions, context)

        cleanup.assert_not_called()

    def test_missing_index_uses_conditional_create(self):
        desired = {
            "name": "rag-index",
            "fields": [{"name": "id", "type": "Edm.String", "key": True}],
        }

        with patch.object(
            setup,
            "get_search_resource",
            return_value=(None, None),
        ), patch.object(setup, "call_search_api", return_value=True) as call:
            setup.provision_indexes(
                {"indexes": [desired]},
                {},
                Mock(),
                "https://search.search.windows.net",
                "2025-09-01",
            )

        self.assertEqual(call.call_args.kwargs["if_none_match"], "*")
        self.assertIsNone(call.call_args.kwargs["if_match"])

    def test_index_update_runs_before_dependent_cleanup(self):
        definitions = {"indexes": [{"name": "rag-index", "fields": []}]}
        context = {
            "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
            "SEARCH_API_VERSION": "2025-09-01",
        }
        events = []
        prepared = [("rag-index", None, [], '"etag"', None)]

        with patch.object(
            setup,
            "prepare_index_updates",
            return_value=prepared,
        ), patch.object(
            setup,
            "provision_indexes",
            side_effect=lambda *args: events.append("indexes"),
        ), patch.object(
            setup,
            "cleanup_knowledge_resources",
            side_effect=lambda *args: events.append("cleanup"),
        ), patch.object(setup, "provision_datasources"), patch.object(
            setup, "provision_skillsets"
        ), patch.object(setup, "provision_indexers"), patch.object(
            setup, "filter_work_iq_sources"
        ), patch.object(
            setup, "provision_knowledge_sources", return_value=True
        ), patch.object(
            setup, "enforce_private_execution_for_generated_indexers"
        ), patch.object(
            setup, "provision_knowledge_bases", return_value=True
        ):
            setup.execute_setup(definitions, context)

        self.assertEqual(events, ["indexes", "cleanup"])


if __name__ == "__main__":
    unittest.main()
