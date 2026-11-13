"""Local protected retrieval deployment contracts; no Azure credentials."""

import json
import traceback
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from config.deployment import appconfig
from config.deployment import hosted_access as access
from tests.test_hosted_access import (
    ACCOUNT, ENV as ACCESS_ENV, MODEL, OTHER, PREFIX, PRINCIPAL, PROJECT,
    SUB, AzureFixture,
)


ENV = {
    "AZURE_RESOURCE_GROUP": "test-group",
    "RESOURCE_TOKEN": "test",
    "ORCHESTRATION_HOST": "hosted",
    "HOSTED_AGENT_DEPLOYMENT": json.dumps({"durableTask": {
        "resourceId": "/subscriptions/example/resourceGroups/example/providers/Microsoft.DurableTask/schedulers/example",
        "endpoint": "https://returned.eastus.durabletask.io", "taskHubName": "agent-lz",
    }}),
    "HOSTED_AGENT_RESOURCE_SCOPE": "https://ai.azure.com/.default",
}
SOURCE_IDS = {
    "WORK_IQ_APPLICATION_ID": "11111111-1111-4111-8111-111111111111",
    "WORK_IQ_FEDERATED_CREDENTIAL_ID": "22222222-2222-4222-8222-222222222222",
    "WORK_IQ_TENANT_ID": "33333333-3333-4333-8333-333333333333",
    "SHAREPOINT_INDEXED_APPLICATION_ID": "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
    "SHAREPOINT_INDEXED_FEDERATED_CREDENTIAL_APPLICATION_ID": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
}


class RetrievalPublicationTests(unittest.TestCase):
    def build(self, **overrides):
        with patch(
            "config.deployment.appconfig._container_app",
            return_value={"fqdn": "app.example.test", "principalId": "fixture"},
        ):
            return appconfig.build_settings({**ENV, **overrides})

    def test_normal_hosted_deploy_publishes_native_route_and_preserves_invocation(self):
        for mode in ("conversational", "workflow", "both"):
            with self.subTest(mode=mode):
                settings = self.build(APPLICATION_MODE=mode)
                self.assertEqual("native_search", settings["RETRIEVAL_AUTH_MODE"])
                self.assertEqual("user_delegated", settings["HOSTED_AGENT_AUTH_MODE"])
                self.assertNotIn("RETRIEVAL_AUTH_CONFIG_JSON", settings)

    def test_source_publication_does_not_map_superseded_sharepoint_key(self):
        settings = self.build(
            SHAREPOINT_INDEXED_FEDERATED_CREDENTIAL_ID="PRIVATE-MARKER",
        )
        self.assertNotIn("SHAREPOINT_INDEXED_FEDERATED_CREDENTIAL_ID", settings)
        self.assertNotIn("SHAREPOINT_INDEXED_FEDERATED_CREDENTIAL_APPLICATION_ID", settings)

    def test_container_apps_has_no_hosted_invocation_route(self):
        settings = self.build(
            ORCHESTRATION_HOST="container_apps", RETRIEVAL_AUTH_MODE="native_search",
        )
        self.assertEqual("", settings["RETRIEVAL_AUTH_MODE"])
        self.assertNotIn("HOSTED_AGENT_AUTH_MODE", settings)
        self.assertNotIn("CHAT_BACKEND", settings)
        with self.assertRaisesRegex(ValueError, "requires ORCHESTRATION_HOST=hosted"):
            self.build(ORCHESTRATION_HOST="container_apps", HOSTED_AGENT_AUTH_MODE="service_identity")

    def test_retired_preservation_controls_fail_before_discovery(self):
        for key in ("PRESERVE_CLASSIC_RUNTIME", "HOSTED_CUTOVER_COMPLETE"):
            with self.subTest(key=key), patch("config.deployment.appconfig._container_app") as read:
                with self.assertRaisesRegex(ValueError, "[Oo]bsolete"):
                    self.build(**{key: "false"})
                read.assert_not_called()

    def test_unknown_or_unimplemented_modes_fail_before_azure_reads(self):
        for mode in ("foundry_toolbox", "bff_obo", "auto", "native-search", "{}", 1):
            for topology in ("hosted", "container_apps"):
                with self.subTest(mode=mode, topology=topology), patch(
                    "config.deployment.appconfig._container_app"
                ) as read:
                    with self.assertRaisesRegex(ValueError, "RETRIEVAL_AUTH_MODE"):
                        appconfig.build_settings({
                            **ENV, "ORCHESTRATION_HOST": topology,
                            "RETRIEVAL_AUTH_MODE": mode,
                        })
                    read.assert_not_called()

    def test_native_route_rejects_unknown_invocation_auth(self):
        for auth in ("bff_obo", "unknown"):
            with self.subTest(auth=auth), self.assertRaisesRegex(
                ValueError, "HOSTED_AGENT_AUTH_MODE"
            ):
                self.build(HOSTED_AGENT_AUTH_MODE=auth)

    def test_explicit_common_blob_service_profile_uses_same_native_route(self):
        settings = self.build(
            HOSTED_AGENT_AUTH_MODE="service_identity",
            FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS="[]",
        )
        self.assertEqual("service_identity", settings["HOSTED_AGENT_AUTH_MODE"])
        self.assertEqual("native_search", settings["RETRIEVAL_AUTH_MODE"])
        self.assertNotIn("FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS", settings)

    def test_service_profile_does_not_restrict_source_types_or_capabilities(self):
        for override in (
            {"FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS": None},
            {"FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS": '["rbacScope"]'},
            {"FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS": "null"},
            {"FOUNDRY_IQ_IS_ADLS_GEN2": "true"}, {"FOUNDRY_IQ_PATTERN": "searchIndex"},
            {"RETRIEVAL_BACKEND": "ai_search"}, {"WORK_IQ_ENABLED": "true"},
            {"SHAREPOINT_INDEXED_ENABLED": "true"}, {"FABRIC_IQ_ENABLED": "true"},
            {"FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED": "true"},
            {"FOUNDRY_IQ_MCP_ENABLED": "true"}, {"MCP_ENABLED": "true"},
            {"MULTIMODAL_ENABLED": "true"}, {"SEARCH_RETRIEVAL_ENABLED": "true"},
        ):
            with self.subTest(override=override):
                settings = self.build(**{
                    "HOSTED_AGENT_AUTH_MODE": "service_identity",
                    "DEPLOY_INGESTION_CONTAINER_APP": "true", **override,
                })
                self.assertEqual("service_identity", settings["HOSTED_AGENT_AUTH_MODE"])
                self.assertEqual("native_search", settings["RETRIEVAL_AUTH_MODE"])
                self.assertTrue(override.keys().isdisjoint(settings))

    def test_native_route_rejects_anonymous_and_disabled_source_authorization(self):
        for override in (
            {"ALLOW_ANONYMOUS": "true"},
            {"FOUNDRY_IQ_FORWARD_SOURCE_AUTH": "false"},
            {"HOSTED_AGENT_AUTH_MODE": "service_identity", "ALLOW_ANONYMOUS": "true"},
        ):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.build(**override)

    def test_default_native_blob_and_existing_index_routes_remain_automatic(self):
        for override in (
            {}, {"FOUNDRY_IQ_PATTERN": "managed", "DEPLOY_INGESTION_CONTAINER_APP": "true"},
            {"FOUNDRY_IQ_IS_ADLS_GEN2": "true"},
            {"FOUNDRY_IQ_PATTERN": "searchIndex",
             "FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS": "[]", "DEPLOY_INGESTION_CONTAINER_APP": "true"},
            {"RETRIEVAL_BACKEND": "ai_search",
             "FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS": "[]", "DEPLOY_INGESTION_CONTAINER_APP": "true"},
            {"FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED": "true"},
        ):
            with self.subTest(override=override):
                self.assertEqual("native_search", self.build(**override)["RETRIEVAL_AUTH_MODE"])

    def test_route_selection_does_not_change_source_permissions_or_enable_flags(self):
        # Source validation is owned by Search setup. A mode setting must not
        # broaden source permissions, omit a mixed-KB member, or guess audiences.
        source_settings = {
            "FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS": '["rbacScope"]',
            "WORK_IQ_ENABLED": "true", "FABRIC_IQ_ENABLED": "true",
            "FABRIC_DATA_AGENT_ENABLED": "true", "SHAREPOINT_INDEXED_ENABLED": "true",
            "FOUNDRY_IQ_MCP_ENABLED": "true",
        }
        for topology in ("hosted", "container_apps"):
            with self.subTest(topology=topology):
                settings = self.build(ORCHESTRATION_HOST=topology, **source_settings)
                self.assertTrue(source_settings.keys().isdisjoint(settings))
                self.assertNotIn("RETRIEVAL_AUTH_CONFIG_JSON", settings)

    def test_backend_contract_rejects_unknown_values(self):
        for backend in (
            "unknown", "Foundry_IQ", "foundry_toolbox",
        ):
            with self.subTest(backend=backend), self.assertRaisesRegex(ValueError, "RETRIEVAL_BACKEND"):
                self.build(RETRIEVAL_BACKEND=backend, DEPLOY_INGESTION_CONTAINER_APP="true")

    def test_publication_uses_shared_label_without_retired_route_selector(self):
        settings = self.build()
        with patch("config.deployment.appconfig._run_az") as azure:
            appconfig.publish_settings("https://store.azconfig.io", settings)
        commands = [call.args[0] for call in azure.call_args_list]
        keys = [args[args.index("--key") + 1] for args in commands]
        self.assertNotIn("CHAT_BACKEND", keys)
        for key in ("RETRIEVAL_AUTH_MODE", "HOSTED_AGENT_AUTH_MODE"):
            command = commands[keys.index(key)]
            self.assertEqual("agent-lz", command[command.index("--label") + 1])
            self.assertEqual(settings[key], command[command.index("--value") + 1])

    def test_optional_source_ids_have_no_defaults_and_do_not_enable_sources(self):
        for overrides in (
            {}, {"ORCHESTRATION_HOST": "container_apps"},
            {"APPLICATION_MODE": "workflow"},
        ):
            with self.subTest(overrides=overrides):
                self.assertTrue(SOURCE_IDS.keys().isdisjoint(self.build(**overrides)))
                settings = self.build(**overrides, **SOURCE_IDS)
                self.assertEqual(SOURCE_IDS, {key: settings[key] for key in SOURCE_IDS})
                for flag in ("WORK_IQ_ENABLED", "SHAREPOINT_INDEXED_ENABLED"):
                    self.assertNotIn(flag, settings)
                self.assertNotIn("KNOWLEDGE_BASE_CONNECTION_ID", settings)
                self.assertNotIn("RETRIEVAL_AUTH_CONFIG_JSON", settings)

    def test_source_publication_preserves_explicit_ids_and_empty_clears_under_shared_label(self):
        for key, identifier in SOURCE_IDS.items():
            for value in (identifier, ""):
                with self.subTest(key=key, empty=not value):
                    settings = self.build(**{key: value})
                    self.assertEqual({key}, SOURCE_IDS.keys() & settings.keys())
                    with patch("config.deployment.appconfig._run_az") as azure:
                        appconfig.publish_settings("https://store.azconfig.io", settings)
                    commands = [call.args[0] for call in azure.call_args_list]
                    source_commands = [
                        args for args in commands if args[args.index("--key") + 1] in SOURCE_IDS
                    ]
                    self.assertEqual(1, len(source_commands))
                    command = source_commands[0]
                    self.assertEqual(key, command[command.index("--key") + 1])
                    self.assertEqual(value, command[command.index("--value") + 1])
                    self.assertEqual("agent-lz", command[command.index("--label") + 1])
                    self.assertEqual("text/plain", command[command.index("--content-type") + 1])
                    self.assertNotIn("CHAT_BACKEND", [args[args.index("--key") + 1] for args in commands])

    def test_invalid_source_ids_fail_before_resource_discovery_without_echoing_values(self):
        for key in SOURCE_IDS:
            for value in ("PRIVATE-MARKER", "not-a-uuid", " ", None, 123):
                for topology in ("hosted", "container_apps"):
                    with self.subTest(key=key, value_type=type(value).__name__, topology=topology), patch(
                        "config.deployment.appconfig._container_app"
                    ) as resource, patch("config.deployment.appconfig._run_az") as azure:
                        try:
                            appconfig.build_settings({
                                **ENV, "ORCHESTRATION_HOST": topology, key: value,
                            })
                        except ValueError as error:
                            self.assertIn(key, str(error))
                            self.assertIn("UUID", str(error))
                            self.assertNotIn("PRIVATE-MARKER", "".join(
                                traceback.format_exception(error)
                            ))
                        else:
                            self.fail("Invalid source identity input was accepted.")
                        resource.assert_not_called()
                        azure.assert_not_called()


SEARCH = PREFIX + "Microsoft.Search/searchServices/test-search"
SEARCH_ENDPOINT = "https://test-search.search.windows.net"


class NativeSearchTransportTests(unittest.TestCase):
    def test_service_bootstrap_keeps_scoped_identity_independent_of_source_policy(self):
        for key, value in {
            "RETRIEVAL_BACKEND": "foundry_iq",
            "HOSTED_AGENT_AUTH_MODE": "service_identity",
            "FOUNDRY_IQ_PATTERN": "azureBlob", "FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND": "azureBlob",
            "FOUNDRY_IQ_IS_ADLS_GEN2": "false", "FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS": "[]",
        }.items():
            self.azure.settings[key] = {"key": key, "label": "agent-lz", "value": value}
        plan = self.discover(HOSTED_AGENT_AUTH_MODE="service_identity")
        self.assertEqual([], [
            grant for grant in plan.grants if grant.role is access.Role.SEARCH
        ])
        self.assertEqual([access.Grant(access.Role.TOOLBOX, PROJECT)], [
            grant for grant in plan.grants if grant.role is access.Role.TOOLBOX
        ])
        self.assertTrue(plan.toolbox)
        self.assertEqual(4, len(plan.grants))
        for key, value in (
            ("FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS", '["rbacScope"]'),
            ("WORK_IQ_ENABLED", "true"),
        ):
            original = self.azure.settings.get(key)
            self.azure.settings[key] = {"key": key, "label": "agent-lz", "value": value}
            self.assertEqual(plan, self.discover(HOSTED_AGENT_AUTH_MODE="service_identity"))
            if original is None:
                del self.azure.settings[key]
            else:
                self.azure.settings[key] = original
        self.assertEqual([], self.azure.writes)

    def setUp(self):
        self.azure = AzureFixture()
        for key, value in {
            "RETRIEVAL_BACKEND": "ai_search",
            "RETRIEVAL_AUTH_MODE": "native_search",
            "SEARCH_SERVICE_RESOURCE_ID": SEARCH,
            "SEARCH_SERVICE_NAME": "test-search",
            "SEARCH_SERVICE_QUERY_ENDPOINT": SEARCH_ENDPOINT,
            "AI_FOUNDRY_PROJECT_RESOURCE_ID": PROJECT,
            "AI_FOUNDRY_PROJECT_ENDPOINT": ACCESS_ENV["AZURE_AI_PROJECT_ENDPOINT"],
            "KNOWLEDGE_BASE_NAME": "test-kb",
            "TOOLBOX_ENDPOINT": ACCESS_ENV["AZURE_AI_PROJECT_ENDPOINT"] + "/toolboxes/test-kb/mcp?api-version=v1",
        }.items():
            self.azure.settings[key] = {"key": key, "label": "agent-lz", "value": value}
        self.azure.resources[SEARCH] = {
            "id": SEARCH, "name": "test-search", "type": "Microsoft.Search/searchServices",
        }

    def discover(self, **overrides):
        selected = {
            key: row["value"] for key, row in self.azure.settings.items()
            if key in {
                "RETRIEVAL_BACKEND", "SEARCH_SERVICE_RESOURCE_ID",
                "SEARCH_SERVICE_NAME", "SEARCH_SERVICE_QUERY_ENDPOINT",
                "AI_FOUNDRY_PROJECT_RESOURCE_ID", "AI_FOUNDRY_PROJECT_ENDPOINT",
                "KNOWLEDGE_BASE_NAME", "TOOLBOX_ENDPOINT",
            }
        }
        return access.discover({**ACCESS_ENV, **selected, **overrides}, run=self.azure)

    def test_existing_bootstrap_adds_only_exact_search_transport_for_actual_instance(self):
        plan = self.discover()
        self.assertTrue(plan.search_transport)
        self.assertEqual(PRINCIPAL, plan.principal_id)
        search_grants = [grant for grant in plan.grants if grant.role is access.Role.SEARCH]
        self.assertEqual([access.Grant(access.Role.SEARCH, SEARCH)], search_grants)
        self.assertEqual(
            {access.Role.CONFIG, access.Role.MODEL, access.Role.SECRET, access.Role.SEARCH},
            {grant.role for grant in plan.grants},
        )
        self.assertEqual([], self.azure.writes)
        self.assertIn(["resource", "show", "--ids", SEARCH], self.azure.calls)

    def test_container_apps_and_no_retrieval_deployments_never_add_hosted_search_grant(self):
        plan = self.discover(ORCHESTRATION_HOST="container_apps")
        self.assertFalse(plan.search_transport)
        self.assertEqual((), plan.grants)
        self.assertEqual([], self.azure.calls)
        del self.azure.settings["RETRIEVAL_BACKEND"]
        self.assertFalse(self.discover().search_transport)
        self.assertNotIn(["resource", "show", "--ids", SEARCH], self.azure.calls)

    def test_native_backends_receive_only_their_own_transport_scope(self):
        del self.azure.settings["RETRIEVAL_AUTH_MODE"]
        for backend in ("foundry_iq", "ai_search"):
            self.azure.settings["RETRIEVAL_BACKEND"]["value"] = backend
            plan = self.discover(RETRIEVAL_BACKEND=backend)
            self.assertEqual(backend == "ai_search", plan.search_transport)
            self.assertEqual(backend == "foundry_iq", plan.toolbox)

    def test_managed_toolbox_binding_and_closed_project_role_fail_before_writes(self):
        self.azure.settings["RETRIEVAL_BACKEND"]["value"] = "foundry_iq"
        plan = self.discover()
        roles = json.loads((Path(__file__).resolve().parents[1] / "infra/shared/roles.json").read_text())
        self.assertEqual(roles["AzureAIUser"]["guid"], access.Role.TOOLBOX.value)
        for key in ("TOOLBOX_ENDPOINT", "AI_FOUNDRY_PROJECT_ENDPOINT", "AI_FOUNDRY_PROJECT_RESOURCE_ID"):
            original = self.azure.settings[key]["value"]
            self.azure.settings[key]["value"] = original + "-unreviewed"
            with self.subTest(key=key), self.assertRaises(access.AccessError):
                self.discover()
            self.azure.settings[key]["value"] = original
        for invalid in (
            replace(plan, toolbox=False), replace(plan, toolbox="true"),
            replace(plan, grants=tuple(g for g in plan.grants if g.role is not access.Role.TOOLBOX)),
        ):
            with self.assertRaises(access.AccessError):
                invalid.validate()
        self.assertEqual([], self.azure.writes)

    def test_split_resource_groups_keep_search_in_foundry_not_application(self):
        foundry_group = "foundry-group"
        for old in (PROJECT, ACCOUNT, MODEL, SEARCH):
            new = old.replace("test-group", foundry_group)
            self.azure.resources[new] = {**self.azure.resources.pop(old), "id": new}
        self.azure.settings["AZURE_RESOURCE_GROUP"]["value"] = foundry_group
        self.azure.settings["AZURE_APP_RESOURCE_GROUP"] = {
            "key": "AZURE_APP_RESOURCE_GROUP", "label": "agent-lz", "value": "test-group",
        }
        self.azure.settings["SEARCH_SERVICE_RESOURCE_ID"]["value"] = SEARCH.replace(
            "test-group", foundry_group
        )
        self.azure.settings["AI_FOUNDRY_PROJECT_RESOURCE_ID"]["value"] = PROJECT.replace(
            "test-group", foundry_group
        )
        plan = self.discover(
            AZURE_RESOURCE_GROUP=foundry_group, AZURE_APP_RESOURCE_GROUP="test-group",
            AZURE_AI_PROJECT_RESOURCE_ID=PROJECT.replace("test-group", foundry_group),
            AI_FOUNDRY_ACCOUNT_RESOURCE_ID=MODEL.replace("test-group", foundry_group),
        )
        self.assertEqual(
            SEARCH.replace("test-group", foundry_group),
            next(g.scope for g in plan.grants if g.role is access.Role.SEARCH),
        )
        with self.assertRaises(access.AccessError):
            replace(plan, grants=tuple(
                access.Grant(access.Role.SEARCH, SEARCH) if g.role is access.Role.SEARCH else g
                for g in plan.grants
            )).validate()

    def test_missing_bindings_never_guess_a_service_or_create_a_grant(self):
        for key in ("SEARCH_SERVICE_RESOURCE_ID", "SEARCH_SERVICE_NAME", "SEARCH_SERVICE_QUERY_ENDPOINT"):
            with self.subTest(key=key):
                row = self.azure.settings.pop(key)
                try:
                    with self.assertRaises(access.AccessError):
                        self.discover()
                finally:
                    self.azure.settings[key] = row
        del self.azure.settings["RETRIEVAL_BACKEND"]
        self.assertFalse(self.discover().search_transport)
        del self.azure.settings["SEARCH_SERVICE_RESOURCE_ID"]
        with self.assertRaises(access.AccessError):
            self.discover(RETRIEVAL_BACKEND="foundry_iq")
        self.assertEqual([], self.azure.writes)

    def test_unbound_or_broad_scopes_are_rejected_before_resource_read(self):
        for scope in (
            SEARCH.replace(SUB, OTHER), SEARCH.replace("test-group", "wrong-group"),
            PREFIX, SEARCH + "/indexes/documents", SEARCH + "?redirect=PRIVATE-MARKER",
        ):
            with self.subTest(scope=scope):
                self.azure.settings["SEARCH_SERVICE_RESOURCE_ID"]["value"] = scope
                with self.assertRaises(access.AccessError) as error:
                    self.discover()
                self.assertNotIn("PRIVATE-MARKER", str(error.exception))
                self.assertNotIn(["resource", "show", "--ids", scope], self.azure.calls)
        self.assertEqual([], self.azure.writes)

    def test_endpoint_and_arm_identity_cannot_redirect_the_grant(self):
        for endpoint in (
            "https://other.search.windows.net", SEARCH_ENDPOINT + ".evil.invalid",
            SEARCH_ENDPOINT.replace("https:", "http:"), SEARCH_ENDPOINT + "/indexes",
            SEARCH_ENDPOINT + "?token=PRIVATE-MARKER",
        ):
            with self.subTest(endpoint=endpoint):
                self.azure.settings["SEARCH_SERVICE_QUERY_ENDPOINT"]["value"] = endpoint
                with self.assertRaises(access.AccessError) as error:
                    self.discover()
                self.assertNotIn("PRIVATE-MARKER", str(error.exception))
        self.azure.settings["SEARCH_SERVICE_QUERY_ENDPOINT"]["value"] = SEARCH_ENDPOINT
        for key, value in (("id", MODEL), ("name", "other"), ("type", "Microsoft.Storage/storageAccounts")):
            with self.subTest(key=key):
                original = self.azure.resources[SEARCH][key]
                self.azure.resources[SEARCH][key] = value
                try:
                    with self.assertRaises(access.AccessError):
                        self.discover()
                finally:
                    self.azure.resources[SEARCH][key] = original
        self.assertEqual([], self.azure.writes)

    def test_environment_and_persisted_binding_conflicts_fail_closed(self):
        for overrides in (
            {"RETRIEVAL_BACKEND": "unsupported"}, {"SEARCH_SERVICE_RESOURCE_ID": MODEL},
            {"SEARCH_SERVICE_ENDPOINT": "https://other.search.windows.net"},
            {"RETRIEVAL_AUTH_MODE": "foundry_toolbox"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises((ValueError, access.AccessError)):
                self.discover(**overrides)
        self.azure.settings["RETRIEVAL_AUTH_MODE"]["value"] = "foundry_toolbox"
        with self.assertRaisesRegex(access.AccessError, "RETRIEVAL_AUTH_MODE"):
            self.discover()
        self.assertEqual([], self.azure.writes)

    def test_reader_assignment_is_exact_idempotent_and_never_uses_project_principal(self):
        plan = self.discover()
        # An inherited assignment is not sufficient and is never removed.
        self.azure.assignments = [
            self.azure.assignment(scope=f"/subscriptions/{SUB}", role=access.Role.SEARCH)
        ]
        access.apply(plan, run=self.azure)
        self.assertEqual(4, len(self.azure.writes))
        access.apply(self.discover(), run=self.azure)
        self.assertEqual(4, len(self.azure.writes))
        for command in self.azure.writes:
            self.assertEqual(PRINCIPAL, command[command.index("--assignee-object-id") + 1])
            if command[command.index("--role") + 1] == access.Role.SEARCH.value:
                self.assertEqual(SEARCH, command[command.index("--scope") + 1])

    def test_conditional_search_assignment_blocks_all_writes(self):
        self.azure.assignments = [
            self.azure.assignment(SEARCH, access.Role.SEARCH, condition="@operator-condition")
        ]
        with self.assertRaisesRegex(access.AccessError, "Conflicting"):
            access.apply(self.discover(), run=self.azure)
        self.assertEqual([], self.azure.writes)

    def test_plan_requires_search_role_if_and_only_if_transport_was_configured(self):
        plan = self.discover()
        for invalid in (
            replace(plan, search_transport=False),
            replace(plan, search_transport="true"),
            replace(plan, grants=tuple(g for g in plan.grants if g.role is not access.Role.SEARCH)),
            replace(plan, grants=plan.grants + (access.Grant(access.Role.SEARCH, SEARCH),)),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(access.AccessError):
                access.apply(invalid, run=self.azure)
        self.assertEqual([], self.azure.writes)
