from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from config.deployment import appconfig
from config.deployment.composition import (
    ConflictingTopologySignalsError,
    DeploymentMode,
    compose_parameters,
    describe_mode,
    materialized_settings,
    panel_database_containers,
    resolve_database_containers,
    resolve_explicit_topology,
    resolve_mode,
    resolve_topology,
    selected_components,
)
from config.deployment.hosted import invocations_base_url
from config.panel.settings import (
    FEEDBACK_CONTAINER_CONFIG_KEY,
    FEEDBACK_CONTAINER_NAME,
    OWNER_INDEX_CONTAINER_CONFIG_KEY,
    OWNER_INDEX_CONTAINER_NAME,
)


ROOT = Path(__file__).resolve().parents[1]
DIGEST = "sha256:" + ("a" * 64)


def source_parameters() -> dict[str, object]:
    return json.loads((ROOT / "main.parameters.json").read_text(encoding="utf-8"))


def settings_by_name(document: dict[str, object]) -> dict[str, str]:
    settings = document["parameters"]["additionalAppConfigurationSettings"]["value"]
    return {item["name"]: item["value"] for item in settings}


class DeploymentCompositionTests(unittest.TestCase):
    def test_false_defaults_preserve_classic_composition(self) -> None:
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
        }

        composed = compose_parameters(source_parameters(), environment)
        parameters = composed["parameters"]
        apps = parameters["containerAppsList"]["value"]

        self.assertEqual(DeploymentMode.CLASSIC, resolve_mode(environment))
        self.assertEqual(
            ("agent-app-ui", "agent-app-orchestrator", "agent-app-ingestion"),
            selected_components(DeploymentMode.CLASSIC),
        )
        self.assertEqual(
            ["orchestrator", "frontend", "dataingest"],
            [app["service_name"] for app in apps],
        )
        self.assertTrue(parameters["deployCosmosDb"]["value"])
        self.assertFalse(parameters["prepareHostedAgent"]["value"])
        self.assertFalse(parameters["deployHostedAgent"]["value"])
        settings = settings_by_name(composed)
        expected = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
            "PREPARE_HOSTED_AGENT": "false",
            "DEPLOY_HOSTED_AGENT": "false",
            "HOSTED_AGENT_PREPARED": "false",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            "DEPLOYMENT_TOPOLOGY": "classic",
            "CHAT_BACKEND": "orchestrator",
            "HOSTED_AGENT_BASE_URL": "",
            "HOSTED_AGENT_RESOURCE_SCOPE": "",
            "HOSTED_AGENT_IMAGE_VERSION": "",
            "HOSTED_AGENT_SSE_IDLE_TIMEOUT_SECONDS": "60",
        }
        self.assertTrue(expected.items() <= settings.items())
        self.assertEqual(
            settings["HOSTED_CONVERSATION_OWNER_BINDING"],
            "delegated",
        )
        self.assertEqual(
            settings["HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED"],
            "false",
        )
        self.assertEqual(
            settings["HOSTED_AGENT_RESPONSES_PROTOCOL_VERSION"],
            "2.0.0",
        )
        self.assertEqual(
            settings["HOSTED_CONTINUITY_UNAVAILABLE_STATUS_CODE"],
            "503",
        )

    def test_panel_flag_does_not_change_classic_mode(self) -> None:
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
            "DEPLOY_ADMINISTRATIVE_PANEL": "true",
        }

        composed = compose_parameters(source_parameters(), environment)

        self.assertEqual(DeploymentMode.CLASSIC, resolve_mode(environment))
        self.assertEqual(
            "false",
            settings_by_name(composed)["DEPLOY_ADMINISTRATIVE_PANEL"],
        )

    def test_hosted_without_panel_removes_orchestrator_and_cosmos(self) -> None:
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
        }

        composed = compose_parameters(source_parameters(), environment)
        parameters = composed["parameters"]
        apps = parameters["containerAppsList"]["value"]
        dataingest = next(
            app for app in apps if app["service_name"] == "dataingest"
        )

        self.assertEqual(DeploymentMode.HOSTED_NO_PANEL, resolve_mode(environment))
        self.assertEqual(
            ("agent-app-ui", "agent-app-ingestion"),
            selected_components(DeploymentMode.HOSTED_NO_PANEL),
        )
        self.assertEqual(
            ["frontend", "dataingest"],
            [app["service_name"] for app in apps],
        )
        self.assertFalse(parameters["deployCosmosDb"]["value"])
        self.assertTrue(parameters["prepareHostedAgent"]["value"])
        self.assertTrue(parameters["deployHostedAgent"]["value"])
        self.assertEqual([], parameters["databaseContainersList"]["value"])
        self.assertNotIn(
            "CosmosDBBuiltInDataContributor", dataingest["roles"]
        )
        self.assertEqual("hosted_agent", settings_by_name(composed)["CHAT_BACKEND"])

    def test_fresh_hosted_composition_allows_automatic_image_preparation(
        self,
    ) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
        }

        composed = compose_parameters(source_parameters(), environment)

        self.assertTrue(composed["parameters"]["prepareHostedAgent"]["value"])
        self.assertFalse(composed["parameters"]["deployHostedAgent"]["value"])
        self.assertEqual(
            "",
            composed["parameters"]["hostedAgent"]["value"]["version"],
        )
        self.assertNotIn(
            "orchestrator",
            [
                app["service_name"]
                for app in composed["parameters"]["containerAppsList"]["value"]
            ],
        )
        self.assertEqual(
            "hosted_agent",
            settings_by_name(composed)["CHAT_BACKEND"],
        )

    def test_isolated_hosted_preparation_requests_dedicated_acr_pool(
        self,
    ) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "NETWORK_ISOLATION": "true",
        }

        composed = compose_parameters(source_parameters(), environment)

        self.assertTrue(
            composed["parameters"]["deployAcrTaskAgentPool"]["value"]
        )

    def test_classic_composition_preserves_acr_pool_operator_setting(
        self,
    ) -> None:
        source = source_parameters()

        composed = compose_parameters(
            source,
            {"DEPLOYMENT_TOPOLOGY": "classic", "NETWORK_ISOLATION": "true"},
        )

        self.assertEqual(
            source["parameters"]["deployAcrTaskAgentPool"],
            composed["parameters"]["deployAcrTaskAgentPool"],
        )

    def test_prepare_only_migration_preserves_classic_runtime(
        self,
    ) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "PRESERVE_CLASSIC_RUNTIME": "true",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
        }

        composed = compose_parameters(source_parameters(), environment)
        parameters = composed["parameters"]

        self.assertTrue(parameters["prepareHostedAgent"]["value"])
        self.assertFalse(parameters["deployHostedAgent"]["value"])
        self.assertTrue(parameters["deployCosmosDb"]["value"])
        self.assertEqual(
            ["orchestrator", "frontend", "dataingest"],
            [
                app["service_name"]
                for app in parameters["containerAppsList"]["value"]
            ],
        )
        self.assertNotEqual([], parameters["databaseContainersList"]["value"])
        self.assertEqual(
            "orchestrator",
            settings_by_name(composed)["CHAT_BACKEND"],
        )
        self.assertEqual(
            "classic",
            settings_by_name(composed)["DEPLOYMENT_TOPOLOGY"],
        )

    def test_migration_handoff_keeps_classic_runtime_until_endpoint(
        self,
    ) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "PRESERVE_CLASSIC_RUNTIME": "true",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
        }

        composed = compose_parameters(source_parameters(), environment)

        self.assertTrue(composed["parameters"]["deployHostedAgent"]["value"])
        self.assertIn(
            "orchestrator",
            [
                app["service_name"]
                for app in composed["parameters"]["containerAppsList"]["value"]
            ],
        )
        self.assertTrue(composed["parameters"]["deployCosmosDb"]["value"])
        self.assertEqual(
            "orchestrator",
            settings_by_name(composed)["CHAT_BACKEND"],
        )

    def test_migration_endpoint_without_success_marker_stays_classic(
        self,
    ) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "PRESERVE_CLASSIC_RUNTIME": "true",
            "HOSTED_AGENT_BASE_URL": "https://agent.example.test/protocols",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
        }

        composed = compose_parameters(source_parameters(), environment)

        self.assertIn(
            "orchestrator",
            [
                app["service_name"]
                for app in composed["parameters"]["containerAppsList"]["value"]
            ],
        )
        self.assertTrue(composed["parameters"]["deployCosmosDb"]["value"])
        self.assertEqual(
            "orchestrator",
            settings_by_name(composed)["CHAT_BACKEND"],
        )

    def test_migration_cuts_over_after_digest_and_endpoint_exist(self) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "PRESERVE_CLASSIC_RUNTIME": "true",
            "HOSTED_CUTOVER_COMPLETE": "true",
            "HOSTED_AGENT_BASE_URL": "https://agent.example.test/protocols",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
        }

        composed = compose_parameters(source_parameters(), environment)

        self.assertNotIn(
            "orchestrator",
            [
                app["service_name"]
                for app in composed["parameters"]["containerAppsList"]["value"]
            ],
        )
        self.assertFalse(composed["parameters"]["deployCosmosDb"]["value"])
        self.assertEqual(
            "hosted_agent",
            settings_by_name(composed)["CHAT_BACKEND"],
        )

    def test_migration_does_not_cut_over_without_success_marker(self) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "PRESERVE_CLASSIC_RUNTIME": "true",
            "HOSTED_AGENT_BASE_URL": "https://agent.example.test/protocols",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
        }

        composed = compose_parameters(source_parameters(), environment)

        self.assertEqual(
            "orchestrator",
            settings_by_name(composed)["CHAT_BACKEND"],
        )
        self.assertIn(
            "orchestrator",
            [
                app["service_name"]
                for app in composed["parameters"]["containerAppsList"]["value"]
            ],
        )

    def test_digest_materializes_deploy_handoff(self) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
        }

        composed = compose_parameters(source_parameters(), environment)

        self.assertTrue(composed["parameters"]["prepareHostedAgent"]["value"])
        self.assertTrue(composed["parameters"]["deployHostedAgent"]["value"])
        self.assertEqual(
            DIGEST,
            composed["parameters"]["hostedAgent"]["value"]["version"],
        )

    def test_network_isolated_hosted_mode_provisions_acr_agent_pool(self) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "NETWORK_ISOLATION": "true",
        }

        composed = compose_parameters(source_parameters(), environment)

        self.assertTrue(
            composed["parameters"]["deployAcrTaskAgentPool"]["value"]
        )

    def test_stale_generated_source_defers_image_binding_to_deploy(self) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
            "HOSTED_AGENT_IMAGE_SOURCE_COMMIT": "a" * 40,
        }

        composed = compose_parameters(
            source_parameters(), environment, expected_hosted_source_commit="b" * 40,
        )
        self.assertTrue(composed["parameters"]["prepareHostedAgent"]["value"])
        self.assertFalse(composed["parameters"]["deployHostedAgent"]["value"])
        self.assertEqual("", composed["parameters"]["hostedAgent"]["value"]["version"])

    def test_stale_generated_startup_defers_image_binding_to_deploy(self) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
            "HOSTED_AGENT_IMAGE_SOURCE_COMMIT": "a" * 40,
            "HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256": "0" * 64,
        }

        composed = compose_parameters(
            source_parameters(), environment, expected_hosted_source_commit="a" * 40,
        )
        self.assertTrue(composed["parameters"]["prepareHostedAgent"]["value"])
        self.assertFalse(composed["parameters"]["deployHostedAgent"]["value"])
        self.assertEqual("", composed["parameters"]["hostedAgent"]["value"]["version"])

    def test_hosted_with_panel_composes_only_panel_resources(self) -> None:
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "DEPLOY_ADMINISTRATIVE_PANEL": "true",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
        }

        composed = compose_parameters(source_parameters(), environment)
        parameters = composed["parameters"]
        apps = parameters["containerAppsList"]["value"]

        self.assertEqual(DeploymentMode.HOSTED_PANEL, resolve_mode(environment))
        self.assertEqual(
            ["frontend", "dataingest"],
            [app["service_name"] for app in apps],
        )
        self.assertTrue(parameters["deployCosmosDb"]["value"])
        self.assertEqual(
            panel_database_containers(),
            parameters["databaseContainersList"]["value"],
        )
        settings = settings_by_name(composed)
        self.assertEqual("hosted_agent", settings["CHAT_BACKEND"])
        self.assertEqual("true", settings["DEPLOY_ADMINISTRATIVE_PANEL"])
        self.assertEqual("false", settings["PANEL_HISTORY_ENABLED"])
        self.assertEqual("false", settings["PANEL_OPERATOR_SURFACES_ENABLED"])

    def test_legacy_generated_digest_without_startup_provenance_remains_valid(
        self,
    ) -> None:
        manifest = json.loads(
            (ROOT / "manifest.json").read_text(encoding="utf-8")
        )
        orchestrator = next(
            component
            for component in manifest["components"]
            if component["name"] == "agent-app-orchestrator"
        )
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
            "HOSTED_AGENT_IMAGE_SOURCE_COMMIT": orchestrator["commit"],
        }

        composed = compose_parameters(source_parameters(), environment)

        self.assertTrue(composed["parameters"]["deployHostedAgent"]["value"])

    def test_deployment_topology_hosted_panel_resolves(self) -> None:
        environment = {"DEPLOYMENT_TOPOLOGY": "hosted-panel"}

        self.assertEqual(DeploymentMode.HOSTED_PANEL, resolve_mode(environment))

    def test_hosted_mode_rejects_mutable_image_reference(self) -> None:
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "HOSTED_AGENT_IMAGE_VERSION": "v3.9.0",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
        }

        with self.assertRaisesRegex(ValueError, "immutable OCI digest"):
            compose_parameters(source_parameters(), environment)

    def test_hosted_mode_rejects_noncanonical_uppercase_digest(self) -> None:
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "HOSTED_AGENT_IMAGE_VERSION": "sha256:" + ("A" * 64),
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
        }

        with self.assertRaisesRegex(ValueError, "immutable OCI digest"):
            compose_parameters(source_parameters(), environment)

    def test_hosted_mode_rejects_missing_delegated_scope(self) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
        }

        with self.assertRaisesRegex(ValueError, "delegated-user data-plane scope"):
            compose_parameters(source_parameters(), environment)


class PanelPlatformContractTests(unittest.TestCase):
    """Issue #611 / ADR-0004 platform-contract composition.

    The topology is deployable only with explicit operator selection. Its
    user-history and operator surfaces remain independently fail closed behind
    their disabled-by-default evidence gates.
    """

    def test_panel_database_containers_are_metadata_only_and_distinct(self) -> None:
        containers = panel_database_containers()
        names = {container["name"] for container in containers}
        canonical_names = {container["canonical_name"] for container in containers}

        self.assertEqual(names, {OWNER_INDEX_CONTAINER_NAME, FEEDBACK_CONTAINER_NAME})
        self.assertEqual(
            canonical_names,
            {OWNER_INDEX_CONTAINER_CONFIG_KEY, FEEDBACK_CONTAINER_CONFIG_KEY},
        )
        # Never the classic chat-content/orchestrator containers.
        self.assertNotIn("conversations", names)
        self.assertNotIn("datasources", names)
        self.assertNotIn("prompts", names)
        self.assertNotIn("mcp", names)
        for container in containers:
            self.assertEqual(container["partitionKey"], "/principal_id")

    def test_resolve_database_containers_classic_keeps_existing_list(self) -> None:
        existing = [{"name": "conversations", "canonical_name": "X"}]

        result = resolve_database_containers(DeploymentMode.CLASSIC, existing)

        self.assertEqual(result, existing)

    def test_resolve_database_containers_hosted_no_panel_has_zero_cosmos(self) -> None:
        existing = [{"name": "conversations", "canonical_name": "X"}]

        result = resolve_database_containers(
            DeploymentMode.HOSTED_NO_PANEL, existing
        )

        self.assertEqual(result, [])

    def test_resolve_database_containers_hosted_panel_uses_only_panel_containers(
        self,
    ) -> None:
        existing = [{"name": "conversations", "canonical_name": "X"}]

        result = resolve_database_containers(DeploymentMode.HOSTED_PANEL, existing)

        self.assertEqual(result, panel_database_containers())
        names = {container["name"] for container in result}
        self.assertNotIn("conversations", names)

    def test_resolve_database_containers_preserving_classic_runtime_wins(self) -> None:
        existing = [{"name": "conversations", "canonical_name": "X"}]

        result = resolve_database_containers(
            DeploymentMode.HOSTED_PANEL,
            existing,
            preserving_classic_runtime=True,
        )

        self.assertEqual(result, existing)

    def test_container_app_gets_no_cosmos_conversations_role(self) -> None:
        # The hosted agent/orchestrator identity is unconditionally removed
        # from containerAppsList in every hosted mode (no-panel and panel
        # share this same code path), so it can never receive
        # CosmosDBBuiltInDataContributor (or any other role) through the
        # generic account-scope role loop.
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
        }

        composed = compose_parameters(source_parameters(), environment)
        apps = composed["parameters"]["containerAppsList"]["value"]

        service_names = {app["service_name"] for app in apps}
        self.assertNotIn("orchestrator", service_names)

    def test_dataingest_loses_account_scope_cosmos_role_in_hosted_mode(self) -> None:
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
        }

        composed = compose_parameters(source_parameters(), environment)
        apps = composed["parameters"]["containerAppsList"]["value"]
        dataingest = next(app for app in apps if app["service_name"] == "dataingest")

        self.assertNotIn("CosmosDBBuiltInDataContributor", dataingest["roles"])

    def test_dataingest_keeps_existing_blob_role_for_corpus_curation(self) -> None:
        # agent-app-ingestion's (formerly gpt-rag-ingestion) corpus-curation decisions (PR #274) are written
        # to the existing per-file-log blob control store this identity
        # already owns, via Blob Storage ETag optimistic concurrency -- never
        # Cosmos. This asserts that identity's existing blob RBAC (already
        # sufficient for the classic Files tab's blocked/unblock flow) is
        # untouched by the hosted-mode Cosmos-role stripping above.
        # Hosted-panel uses the same hosted component path; this stripping
        # removes only CosmosDBBuiltInDataContributor and leaves the existing
        # blob role unchanged.
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
        }

        composed = compose_parameters(source_parameters(), environment)
        apps = composed["parameters"]["containerAppsList"]["value"]
        dataingest = next(app for app in apps if app["service_name"] == "dataingest")

        self.assertIn("StorageBlobDataContributor", dataingest["roles"])

    def test_panel_app_configuration_defaults_are_published_and_safe(self) -> None:
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
        }

        composed = compose_parameters(source_parameters(), environment)
        settings = settings_by_name(composed)

        self.assertEqual(settings["PANEL_HISTORY_ENABLED"], "false")
        self.assertEqual(settings["PANEL_HISTORY_OWNER_BINDING_VALIDATED"], "false")
        self.assertEqual(
            settings["PANEL_CONVERSATION_ENUMERATION_MODE"], "owner_index"
        )
        self.assertEqual(
            settings[OWNER_INDEX_CONTAINER_CONFIG_KEY], OWNER_INDEX_CONTAINER_NAME
        )
        self.assertEqual(
            settings[FEEDBACK_CONTAINER_CONFIG_KEY], FEEDBACK_CONTAINER_NAME
        )
        self.assertEqual(settings["PANEL_CURSOR_TTL_SECONDS"], "600")
        self.assertEqual(settings["PANEL_OVERVIEW_MIN_CARDINALITY"], "5")
        # agent-app-ingestion (formerly gpt-rag-ingestion) operator surfaces (PR #274, merge 5569dd6):
        # exact key names, safe defaults, feature never set true here.
        self.assertEqual(settings["PANEL_OPERATOR_SURFACES_ENABLED"], "false")
        self.assertEqual(settings["PANEL_OPERATOR_APP_ROLE"], "")
        self.assertEqual(settings["PANEL_OPERATOR_GROUP_ID"], "")

    def test_panel_owner_binding_validated_gate_cannot_be_set_via_environment(
        self,
    ) -> None:
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            "PANEL_HISTORY_OWNER_BINDING_VALIDATED": "true",
        }

        composed = compose_parameters(source_parameters(), environment)
        settings = settings_by_name(composed)

        self.assertEqual(settings["PANEL_HISTORY_OWNER_BINDING_VALIDATED"], "false")

    def test_panel_operator_surfaces_enabled_gate_cannot_be_set_via_environment(
        self,
    ) -> None:
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            "PANEL_OPERATOR_SURFACES_ENABLED": "true",
            "PANEL_OPERATOR_APP_ROLE": "PanelOperator",
            "PANEL_OPERATOR_GROUP_ID": "11111111-1111-1111-1111-111111111111",
        }

        composed = compose_parameters(source_parameters(), environment)
        settings = settings_by_name(composed)

        self.assertEqual(settings["PANEL_OPERATOR_SURFACES_ENABLED"], "false")
        # Role/group are plain operator inputs -- pass through unmodified.
        self.assertEqual(settings["PANEL_OPERATOR_APP_ROLE"], "PanelOperator")
        self.assertEqual(
            settings["PANEL_OPERATOR_GROUP_ID"],
            "11111111-1111-1111-1111-111111111111",
        )

    def test_no_panel_containers_or_settings_leak_into_classic_composition(
        self,
    ) -> None:
        composed = compose_parameters(
            source_parameters(),
            {
                "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
                "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            },
        )
        containers = composed["parameters"]["databaseContainersList"]["value"]
        names = {container["name"] for container in containers}

        self.assertNotIn(OWNER_INDEX_CONTAINER_NAME, names)
        self.assertNotIn(FEEDBACK_CONTAINER_NAME, names)

    def test_no_panel_containers_leak_into_hosted_no_panel_composition(self) -> None:
        environment = {
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
        }

        composed = compose_parameters(source_parameters(), environment)

        self.assertEqual(
            [], composed["parameters"]["databaseContainersList"]["value"]
        )


class EnvironmentTopologyResolutionTests(unittest.TestCase):
    """Regression tests for ADR-0001 rev. 5 fresh-vs-existing resolution.

    ``resolve_topology`` is the single source of truth used by both
    ``preProvision`` implementations (PowerShell and POSIX shell) via
    ``config.deployment.topology``. These tests exercise it directly against
    synthetic "resource group exists" / "persisted App Config settings"
    inputs so the decision matrix is verified without any Azure CLI calls.
    """

    def test_fresh_deployment_defaults_to_hosted_no_panel(self) -> None:
        mode = resolve_topology({}, resource_group_exists=False)

        self.assertEqual(DeploymentMode.HOSTED_NO_PANEL, mode)
        self.assertEqual("hosted_agent", describe_mode(mode)["chat_backend"])

    def test_existing_environment_with_persisted_classic_topology_stays_classic(
        self,
    ) -> None:
        mode = resolve_topology(
            {},
            resource_group_exists=True,
            persisted_settings={"DEPLOYMENT_TOPOLOGY": "classic"},
        )

        self.assertEqual(DeploymentMode.CLASSIC, mode)

    def test_existing_environment_with_persisted_hosted_topology_stays_hosted(
        self,
    ) -> None:
        mode = resolve_topology(
            {},
            resource_group_exists=True,
            persisted_settings={
                "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
                "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            },
        )

        self.assertEqual(DeploymentMode.HOSTED_NO_PANEL, mode)

    def test_existing_environment_with_persisted_panel_topology_stays_panel(
        self,
    ) -> None:
        mode = resolve_topology(
            {},
            resource_group_exists=True,
            persisted_settings={
                "DEPLOYMENT_TOPOLOGY": "hosted-panel",
                "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
                "DEPLOY_ADMINISTRATIVE_PANEL": "true",
                "CHAT_BACKEND": "hosted_agent",
            },
        )

        self.assertEqual(DeploymentMode.HOSTED_PANEL, mode)

    def test_existing_unmarked_pre_cutover_environment_is_classic(self) -> None:
        # A resource group exists (this is not a fresh deployment) but no
        # ADR-0001 topology markers were ever persisted -- this is a
        # pre-cutover environment and must not be silently promoted to
        # hosted just because it predates the new default.
        mode = resolve_topology({}, resource_group_exists=True, persisted_settings={})

        self.assertEqual(DeploymentMode.CLASSIC, mode)

    def test_existing_environment_without_persisted_settings_argument_is_classic(
        self,
    ) -> None:
        mode = resolve_topology({}, resource_group_exists=True)

        self.assertEqual(DeploymentMode.CLASSIC, mode)

    def test_persisted_chat_backend_is_a_topology_signal(self) -> None:
        mode = resolve_topology(
            {},
            resource_group_exists=True,
            persisted_settings={"CHAT_BACKEND": "orchestrator"},
        )

        self.assertEqual(DeploymentMode.CLASSIC, mode)

    def test_conflicting_persisted_backend_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            ConflictingTopologySignalsError, "migration"
        ):
            resolve_topology(
                {},
                resource_group_exists=True,
                persisted_settings={
                    "DEPLOYMENT_TOPOLOGY": "classic",
                    "CHAT_BACKEND": "hosted_agent",
                },
            )

    def test_explicit_topology_wins_over_fresh_default(self) -> None:
        mode = resolve_topology(
            {"DEPLOYMENT_TOPOLOGY": "classic"},
            resource_group_exists=False,
        )

        self.assertEqual(DeploymentMode.CLASSIC, mode)

    def test_explicit_topology_wins_over_persisted_classic(self) -> None:
        mode = resolve_topology(
            {"DEPLOYMENT_TOPOLOGY": "hosted-no-panel"},
            resource_group_exists=True,
            persisted_settings={"DEPLOYMENT_TOPOLOGY": "classic"},
        )

        self.assertEqual(DeploymentMode.HOSTED_NO_PANEL, mode)

    def test_conflicting_persisted_signals_fail_with_migration_guidance(
        self,
    ) -> None:
        persisted = {
            "DEPLOYMENT_TOPOLOGY": "classic",
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
        }

        with self.assertRaisesRegex(
            ConflictingTopologySignalsError, "migration"
        ):
            resolve_topology(
                {}, resource_group_exists=True, persisted_settings=persisted
            )

    def test_canonical_topology_overrides_stale_materialized_flags(
        self,
    ) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
        }

        self.assertEqual(
            DeploymentMode.HOSTED_NO_PANEL,
            resolve_explicit_topology(environment),
        )
        self.assertEqual(
            DeploymentMode.HOSTED_NO_PANEL,
            resolve_topology(environment, resource_group_exists=True),
        )

    def test_explicit_classic_rollback_overrides_materialized_hosted_flags(
        self,
    ) -> None:
        environment = {
            "DEPLOYMENT_TOPOLOGY": "classic",
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "DEPLOY_ADMINISTRATIVE_PANEL": "true",
            "CHAT_BACKEND": "hosted_agent",
        }

        self.assertEqual(
            DeploymentMode.CLASSIC,
            resolve_topology(environment, resource_group_exists=True),
        )

    def test_unknown_deployment_topology_value_fails_closed(self) -> None:
        with self.assertRaises(Exception):
            resolve_mode({"DEPLOYMENT_TOPOLOGY": "not-a-real-topology"})

    def test_materialized_settings_agree_with_describe_mode(self) -> None:
        for mode in DeploymentMode:
            materialized = materialized_settings(mode)
            description = describe_mode(mode)

            self.assertEqual(
                materialized["CHAT_BACKEND"], description["chat_backend"]
            )
            self.assertEqual(
                materialized["DEPLOY_ADMINISTRATIVE_PANEL"] == "true",
                description["deploy_administrative_panel"],
            )
            self.assertEqual(
                materialized["DEPLOY_HOSTED_AGENT_ORCHESTRATION"] == "true",
                description["deploy_hosted_agent_orchestration"],
            )
            # Materialized settings must round-trip: feeding them back
            # through resolve_mode as an explicit signal must reproduce the
            # same mode, since preDeploy/postProvision read them back via
            # `--describe` with no further Azure CLI lookups.
            self.assertEqual(mode, resolve_mode(materialized))

    def test_materialized_migration_preservation_round_trips(self) -> None:
        materialized = materialized_settings(
            DeploymentMode.HOSTED_NO_PANEL,
            preserve_classic_runtime=True,
        )

        self.assertEqual("true", materialized["PRESERVE_CLASSIC_RUNTIME"])
        self.assertEqual("false", materialized["DEPLOY_HOSTED_AGENT_ORCHESTRATION"])
        self.assertEqual("hosted-no-panel", materialized["DEPLOYMENT_TOPOLOGY"])
        self.assertEqual("orchestrator", materialized["CHAT_BACKEND"])
        self.assertTrue(
            describe_mode(
                DeploymentMode.HOSTED_NO_PANEL,
                preserve_classic_runtime=True,
            )["preserve_classic_runtime"]
        )

    def test_materialized_migration_switches_after_cutover(self) -> None:
        materialized = materialized_settings(
            DeploymentMode.HOSTED_NO_PANEL,
            preserve_classic_runtime=True,
            runtime_mode=DeploymentMode.HOSTED_NO_PANEL,
        )

        self.assertEqual("true", materialized["DEPLOY_HOSTED_AGENT_ORCHESTRATION"])
        self.assertEqual("hosted-no-panel", materialized["DEPLOYMENT_TOPOLOGY"])
        self.assertEqual("hosted_agent", materialized["CHAT_BACKEND"])


class AppConfigurationContractTests(unittest.TestCase):
    @staticmethod
    def _app(_resource_group: str, name: str, *, required: bool, subscription: str = "") -> dict[str, str]:
        del required
        return {"fqdn": f"{name}.example.test", "principalId": f"id-{name}"}

    @patch("config.deployment.appconfig._container_app", side_effect=_app)
    def test_classic_runtime_references_orchestrator(self, _mock: object) -> None:
        settings = appconfig.build_settings(
            {
                "AZURE_RESOURCE_GROUP": "rg-test",
                "RESOURCE_TOKEN": "test",
                "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
            }
        )

        self.assertEqual("orchestrator", settings["CHAT_BACKEND"])
        self.assertEqual(
            "https://ca-test-orchestrator.example.test",
            settings["ORCHESTRATOR_BASE_URL"],
        )
        self.assertEqual("", settings["HOSTED_AGENT_BASE_URL"])
        self.assertEqual(3, len(json.loads(settings["CONTAINER_APPS"])))

    @patch("config.deployment.appconfig._container_app", side_effect=_app)
    def test_hosted_runtime_uses_explicit_data_plane_contract(
        self, _mock: object
    ) -> None:
        settings = appconfig.build_settings(
            {
                "AZURE_RESOURCE_GROUP": "rg-test",
                "RESOURCE_TOKEN": "test",
                "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
                "DEPLOY_ADMINISTRATIVE_PANEL": "false",
                "HOSTED_AGENT_BASE_URL": "https://agent.example.test/protocols",
                "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
                "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
                "HOSTED_CONTINUITY_ENABLED": "true",
                "HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED": "true",
            },
            require_hosted_endpoint=True,
        )

        self.assertEqual("hosted_agent", settings["CHAT_BACKEND"])
        self.assertEqual("", settings["ORCHESTRATOR_BASE_URL"])
        self.assertEqual(
            "https://agent.example.test/protocols",
            settings["HOSTED_AGENT_BASE_URL"],
        )
        self.assertEqual(DIGEST, settings["HOSTED_AGENT_IMAGE_VERSION"])
        self.assertEqual(2, len(json.loads(settings["CONTAINER_APPS"])))
        self.assertEqual("delegated", settings["HOSTED_CONVERSATION_OWNER_BINDING"])
        self.assertEqual("false", settings["HOSTED_CONTINUITY_ENABLED"])
        self.assertEqual(
            "false",
            settings["HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED"],
        )

    @patch("config.deployment.appconfig._container_app", side_effect=_app)
    def test_prepare_only_migration_keeps_classic_runtime_settings(
        self, _mock: object
    ) -> None:
        settings = appconfig.build_settings(
            {
                "AZURE_RESOURCE_GROUP": "rg-test",
                "RESOURCE_TOKEN": "test",
                "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
                "PRESERVE_CLASSIC_RUNTIME": "true",
                "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            }
        )

        self.assertEqual("orchestrator", settings["CHAT_BACKEND"])
        self.assertEqual("classic", settings["DEPLOYMENT_TOPOLOGY"])
        self.assertEqual(
            "https://ca-test-orchestrator.example.test",
            settings["ORCHESTRATOR_BASE_URL"],
        )
        self.assertEqual(3, len(json.loads(settings["CONTAINER_APPS"])))

    @patch("config.deployment.appconfig._container_app", side_effect=_app)
    def test_fresh_hosted_without_endpoint_remains_fail_closed(
        self, _mock: object
    ) -> None:
        settings = appconfig.build_settings(
            {
                "AZURE_RESOURCE_GROUP": "rg-test",
                "RESOURCE_TOKEN": "test",
                "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
                "PRESERVE_CLASSIC_RUNTIME": "false",
                "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            }
        )

        self.assertEqual("hosted_agent", settings["CHAT_BACKEND"])
        self.assertEqual("hosted-no-panel", settings["DEPLOYMENT_TOPOLOGY"])
        self.assertEqual("", settings["ORCHESTRATOR_BASE_URL"])
        self.assertEqual("", settings["HOSTED_AGENT_BASE_URL"])
        self.assertEqual(2, len(json.loads(settings["CONTAINER_APPS"])))

    @patch("config.deployment.appconfig._container_app", side_effect=_app)
    def test_migration_switches_only_after_digest_and_endpoint_exist(
        self, _mock: object
    ) -> None:
        settings = appconfig.build_settings(
            {
                "AZURE_RESOURCE_GROUP": "rg-test",
                "RESOURCE_TOKEN": "test",
                "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
                "PRESERVE_CLASSIC_RUNTIME": "true",
                "HOSTED_CUTOVER_COMPLETE": "true",
                "HOSTED_AGENT_BASE_URL": "https://agent.example.test/protocols",
                "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
                "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
            }
        )

        self.assertEqual("hosted_agent", settings["CHAT_BACKEND"])
        self.assertEqual("hosted-no-panel", settings["DEPLOYMENT_TOPOLOGY"])
        self.assertEqual("", settings["ORCHESTRATOR_BASE_URL"])
        self.assertEqual(2, len(json.loads(settings["CONTAINER_APPS"])))

    @patch("config.deployment.appconfig._container_app", side_effect=_app)
    def test_migration_does_not_publish_hosted_before_success_marker(
        self, _mock: object
    ) -> None:
        settings = appconfig.build_settings(
            {
                "AZURE_RESOURCE_GROUP": "rg-test",
                "RESOURCE_TOKEN": "test",
                "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
                "PRESERVE_CLASSIC_RUNTIME": "true",
                "HOSTED_AGENT_BASE_URL": "https://agent.example.test/protocols",
                "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
                "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
            }
        )

        self.assertEqual("orchestrator", settings["CHAT_BACKEND"])
        self.assertEqual("classic", settings["DEPLOYMENT_TOPOLOGY"])
        self.assertNotEqual("", settings["ORCHESTRATOR_BASE_URL"])

    @patch("config.deployment.appconfig._run_az")
    def test_publish_writes_chat_selector_after_hosted_prerequisites(
        self, mock_run_az: object
    ) -> None:
        appconfig.publish_settings(
            "https://config.example.test",
            {
                "CHAT_BACKEND": "hosted_agent",
                "HOSTED_AGENT_BASE_URL": "https://agent.example.test/protocols",
                "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
            },
        )

        published_keys = [
            call.args[0][call.args[0].index("--key") + 1]
            for call in mock_run_az.call_args_list
        ]
        self.assertEqual(
            [
                "HOSTED_AGENT_BASE_URL",
                "HOSTED_AGENT_IMAGE_VERSION",
                "CHAT_BACKEND",
            ],
            published_keys,
        )

    @patch("config.deployment.appconfig._container_app", side_effect=_app)
    def test_hosted_runtime_fails_closed_without_scope(self, _mock: object) -> None:
        with self.assertRaisesRegex(ValueError, "delegated-user data-plane scope"):
            appconfig.build_settings(
                {
                    "AZURE_RESOURCE_GROUP": "rg-test",
                    "RESOURCE_TOKEN": "test",
                    "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
                    "HOSTED_AGENT_BASE_URL": "https://agent.example.test/protocols",
                },
                require_hosted_endpoint=True,
            )

    @patch("config.deployment.appconfig._container_app", side_effect=_app)
    def test_hosted_runtime_fails_closed_with_malformed_scope(
        self, _mock: object
    ) -> None:
        # A scope value that is present but does not end in '/.default' is
        # not a valid delegated-user data-plane scope and must fail closed
        # exactly like a missing scope, never silently coerced or accepted.
        with self.assertRaisesRegex(ValueError, "delegated-user data-plane scope"):
            appconfig.build_settings(
                {
                    "AZURE_RESOURCE_GROUP": "rg-test",
                    "RESOURCE_TOKEN": "test",
                    "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
                    "HOSTED_AGENT_BASE_URL": "https://agent.example.test/protocols",
                    "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/user_impersonation",
                },
                require_hosted_endpoint=True,
            )

    @patch("config.deployment.appconfig._container_app", side_effect=_app)
    def test_hosted_runtime_rejects_scope_without_resource_identifier(
        self, _mock: object
    ) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty resource identifier"):
            appconfig.build_settings(
                {
                    "AZURE_RESOURCE_GROUP": "rg-test",
                    "RESOURCE_TOKEN": "test",
                    "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
                    "HOSTED_AGENT_BASE_URL": "https://agent.example.test/protocols",
                    "HOSTED_AGENT_RESOURCE_SCOPE": "/.default",
                },
                require_hosted_endpoint=True,
            )

    @patch("config.deployment.appconfig._container_app", side_effect=_app)
    def test_hosted_runtime_fails_closed_without_base_url(
        self, _mock: object
    ) -> None:
        with self.assertRaisesRegex(ValueError, "HOSTED_AGENT_BASE_URL"):
            appconfig.build_settings(
                {
                    "AZURE_RESOURCE_GROUP": "rg-test",
                    "RESOURCE_TOKEN": "test",
                    "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
                    "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
                },
                require_hosted_endpoint=True,
            )


class RunAzCommandResolutionTests(unittest.TestCase):
    """Regression tests for the Windows ``az.cmd`` shim lookup.

    ``subprocess.run(["az", ...])`` fails with ``FileNotFoundError``
    on Windows because ``CreateProcess`` does not consult ``PATHEXT``
    the way an interactive shell does. ``_run_az`` must resolve the
    executable via ``shutil.which`` first.
    """

    @patch("config.deployment.appconfig.resolve_az_command")
    @patch("config.deployment.appconfig.subprocess.run")
    def test_uses_resolved_executable_path(
        self, mock_run: object, mock_which: object
    ) -> None:
        mock_which.return_value = r"C:\path\to\az.cmd"
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok", stderr=""
        )

        result = appconfig._run_az(["group", "show"])

        mock_which.assert_called_once_with()
        called_args = mock_run.call_args.args[0]
        self.assertEqual(r"C:\path\to\az.cmd", called_args[0])
        self.assertEqual("ok", result)

    @patch("util.azure_cli.shutil.which")
    def test_falls_back_to_bare_command_when_unresolved(
        self, mock_which: object
    ) -> None:
        mock_which.return_value = None

        self.assertEqual("az", appconfig._resolve_az_command())


class HostedEndpointContractTests(unittest.TestCase):
    def test_protocol_endpoint_is_normalized_for_ui_client(self) -> None:
        self.assertEqual(
            "https://agent.example.test/protocols",
            invocations_base_url(
                "https://agent.example.test/protocols/invocations"
                "?api-version=2025-05-15-preview"
            ),
        )

    def test_non_invocations_endpoint_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "end with '/invocations'"):
            invocations_base_url(
                "https://agent.example.test/protocols/responses"
            )

    def test_non_https_endpoint_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "absolute HTTPS"):
            invocations_base_url("http://agent.example.test/invocations")


class AgentLandingZoneTemplateTests(unittest.TestCase):
    """T016: template metadata uses the Agent Landing Zone identity."""

    def test_template_metadata(self) -> None:
        import yaml

        content = (ROOT / "azure.yaml").read_text(encoding="utf-8")
        project = yaml.safe_load(content)
        self.assertEqual("agent-landing-zone", project["name"])
        self.assertEqual("agent-landing-zone", project["metadata"]["template"])
        self.assertIn("https://github.com/Azure/agent-landing-zone", content)
        self.assertNotIn("azure-gpt-rag", content)
        hosted = (ROOT / "hosted-agent" / "azure.yaml").read_text(encoding="utf-8")
        self.assertNotIn("azure-gpt-rag", hosted)
        self.assertNotIn("GPT_RAG_", hosted)
        for suffix in ("ps1", "sh"):
            hook = (ROOT / "hosted-agent" / "hooks" / f"postdeploy.{suffix}").read_text(encoding="utf-8")
            self.assertNotIn("GPT_RAG_", hook)
            self.assertIn("AGENTLZ_HOSTED_SERVICE", hook)


class AgentLandingZoneAppConfigurationLabelTests(unittest.TestCase):
    """T017: the umbrella writes only label agent-lz and no GPT_RAG_ keys."""

    def test_composed_parameters_use_agent_lz_label(self) -> None:
        source = source_parameters()
        self.assertEqual("agent-lz", source["parameters"]["appConfigLabel"]["value"])
        for environment in (
            {"DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false", "DEPLOY_ADMINISTRATIVE_PANEL": "false"},
            {
                "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
                "DEPLOY_ADMINISTRATIVE_PANEL": "false",
                "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
                "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            },
        ):
            with self.subTest(environment=environment):
                parameters = compose_parameters(source, environment)["parameters"]
                self.assertEqual("agent-lz", parameters["appConfigLabel"]["value"])
                for item in parameters["additionalAppConfigurationSettings"]["value"]:
                    self.assertEqual("agent-lz", item["label"], item["name"])
                    self.assertFalse(item["name"].startswith("GPT_RAG_"), item["name"])

    @patch("config.deployment.appconfig._run_az", return_value="")
    def test_published_settings_use_agent_lz_label(self, run_az: object) -> None:
        appconfig.publish_settings(
            "https://appcs.example.test",
            {"AGENTLZ_PLATFORM_OUTPUTS": "{}", "CHAT_BACKEND": "hosted_agent"},
        )
        calls = run_az.call_args_list  # type: ignore[attr-defined]
        self.assertEqual(2, len(calls))
        for call in calls:
            arguments = call.args[0]
            self.assertEqual("agent-lz", arguments[arguments.index("--label") + 1])
            key = arguments[arguments.index("--key") + 1]
            self.assertFalse(key.startswith("GPT_RAG_"), key)
            self.assertNotIn("gpt-rag", arguments)


class AppDefinitionDeploymentTests(unittest.TestCase):
    """T068: the bundled trio and both sample variants validate."""

    def test_bundled_and_sample_definitions_validate(self) -> None:
        from config.appdefinition import load_definition, validate_definition

        cases = {
            ROOT / "app-definition.json": True,
            ROOT / "samples" / "custom-app" / "containerapp": False,
            ROOT / "samples" / "custom-app" / "hosted": False,
        }
        for path, bundled in cases.items():
            with self.subTest(path=str(path)):
                definition = load_definition(path, repo_root=ROOT)
                self.assertEqual(bundled, definition.bundled)
                validate_definition(definition, ROOT)

    def test_samples_cover_both_hosting_modes(self) -> None:
        from config.appdefinition import load_definition

        kinds = {
            component["kind"]
            for variant in ("containerapp", "hosted")
            for component in load_definition(
                ROOT / "samples" / "custom-app" / variant, repo_root=ROOT
            ).document["components"]
        }
        self.assertEqual({"containerapp", "azure.ai.agent"}, kinds)

    def test_trio_matches_selected_components_in_each_mode(self) -> None:
        from config.appdefinition import effective_components, load_definition

        trio = load_definition(ROOT / "app-definition.json", repo_root=ROOT)
        classic = effective_components(trio, hosted_orchestration=False)
        hosted = effective_components(trio, hosted_orchestration=True)
        self.assertEqual(
            len(selected_components(DeploymentMode.CLASSIC)),
            sum(c["kind"] == "containerapp" for c in classic),
        )
        self.assertEqual(
            len(selected_components(DeploymentMode.HOSTED_NO_PANEL)),
            sum(c["kind"] == "containerapp" for c in hosted),
        )


class OrchestratorApiKeyGateTests(unittest.TestCase):
    HOSTED_ENV = {
        "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
        "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
        "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
    }

    def _api_key_param(self, env: dict[str, str]) -> object:
        composed = compose_parameters(source_parameters(), env)
        return composed["parameters"]["useCAppAPIKey"]

    def test_classic_api_key_default_disabled(self) -> None:
        value = self._api_key_param(
            {
                "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
                "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            }
        )
        self.assertEqual(value, {"value": "${USE_CAPP_API_KEY=false}"})

    def test_hosted_modes_do_not_create_api_key(self) -> None:
        for panel in ("false", "true"):
            with self.subTest(panel=panel):
                env = {**self.HOSTED_ENV, "DEPLOY_ADMINISTRATIVE_PANEL": panel}
                self.assertEqual(self._api_key_param(env), {"value": False})

    def test_preserved_classic_runtime_keeps_api_key(self) -> None:
        value = self._api_key_param(
            {
                "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
                "PRESERVE_CLASSIC_RUNTIME": "true",
                "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            }
        )
        self.assertNotEqual(value, {"value": False})



class KeylessOrchestratorAuthTests(unittest.TestCase):
    def test_container_app_extracts_user_assigned_identity(self) -> None:
        payload = json.dumps(
            {
                "fqdn": "ui.example",
                "principalId": None,
                "userAssigned": {
                    "/subs/x/uai": {"clientId": "cid", "principalId": "pid"}
                },
            }
        )
        with patch.object(appconfig, "_run_az", return_value=payload):
            app = appconfig._container_app("rg", "ui", required=True)
        self.assertEqual(app["uaiClientId"], "cid")
        self.assertEqual(app["uaiPrincipalId"], "pid")
        self.assertEqual(app["principalId"], "")

    def test_caller_settings_prefer_user_assigned_identity(self) -> None:
        settings = appconfig.orchestrator_caller_settings(
            {},
            {"principalId": "sys", "uaiClientId": "cid", "uaiPrincipalId": "pid"},
        )
        self.assertEqual(
            settings,
            {
                "ORCHESTRATOR_AUTH_AUDIENCE": "cid",
                "ORCHESTRATOR_ALLOWED_CALLER_IDS": "pid",
            },
        )

    def test_caller_settings_environment_override(self) -> None:
        settings = appconfig.orchestrator_caller_settings(
            {
                "ORCHESTRATOR_AUTH_AUDIENCE": "api://orch",
                "ORCHESTRATOR_ALLOWED_CALLER_IDS": "a,b",
            },
            {"uaiClientId": "cid", "uaiPrincipalId": "pid"},
        )
        self.assertEqual(settings["ORCHESTRATOR_AUTH_AUDIENCE"], "api://orch")
        self.assertEqual(settings["ORCHESTRATOR_ALLOWED_CALLER_IDS"], "a,b")

    def test_caller_settings_system_assigned_fallback(self) -> None:
        settings = appconfig.orchestrator_caller_settings(
            {}, {"principalId": "sys"}
        )
        self.assertEqual(
            settings["ORCHESTRATOR_AUTH_AUDIENCE"],
            appconfig.SYSTEM_IDENTITY_FALLBACK_AUDIENCE,
        )
        self.assertEqual(settings["ORCHESTRATOR_ALLOWED_CALLER_IDS"], "sys")

    def test_caller_settings_no_identity_stays_empty(self) -> None:
        settings = appconfig.orchestrator_caller_settings({}, {})
        self.assertEqual(settings["ORCHESTRATOR_AUTH_AUDIENCE"], "")
        self.assertEqual(settings["ORCHESTRATOR_ALLOWED_CALLER_IDS"], "")

    def test_publish_skips_empty_keyless_values(self) -> None:
        with patch.object(appconfig, "_run_az", return_value="") as run:
            appconfig.publish_settings(
                "https://cfg",
                {
                    "ORCHESTRATOR_AUTH_AUDIENCE": "",
                    "ORCHESTRATOR_ALLOWED_CALLER_IDS": "pid",
                    "OTHER": "",
                },
            )
        keys = [c.args[0][c.args[0].index("--key") + 1] for c in run.call_args_list]
        self.assertEqual(keys, ["ORCHESTRATOR_ALLOWED_CALLER_IDS", "OTHER"])


if __name__ == "__main__":
    unittest.main()
