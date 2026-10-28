"""Regression tests for the shared topology-resolution CLI/integration.

``config.deployment.topology`` is the single shared entry point used by both
``preProvision`` implementations (PowerShell and POSIX shell) to detect a
fresh vs. existing environment and materialize the resolved topology; and by
``preDeploy``/``postProvision`` (via ``--describe``) to read it back without
any further Azure CLI calls. These tests cover the Azure CLI plumbing
(``resource_group_exists``, ``read_persisted_settings``) in isolation from
the network, and the CLI wrapper's default/``--describe`` behavior end to
end.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

from config.deployment import topology
from config.deployment.composition import DeploymentMode


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class ResourceGroupExistsTests(unittest.TestCase):
    def test_empty_name_short_circuits_without_calling_az(self) -> None:
        with patch("config.deployment.topology.subprocess.run") as mock_run:
            self.assertFalse(topology.resource_group_exists(""))
            self.assertFalse(topology.resource_group_exists(None))
            mock_run.assert_not_called()

    @patch("config.deployment.topology.subprocess.run")
    def test_true_when_az_reports_true(self, mock_run: object) -> None:
        mock_run.return_value = _completed(0, "true")

        self.assertTrue(
            topology.resource_group_exists("rg-test", "subscription-test")
        )
        called_args = mock_run.call_args.args[0]
        self.assertIn("--subscription", called_args)
        self.assertIn("subscription-test", called_args)

    @patch("config.deployment.topology.subprocess.run")
    def test_false_when_az_reports_false(self, mock_run: object) -> None:
        mock_run.return_value = _completed(0, "false")

        self.assertFalse(topology.resource_group_exists("rg-test"))

    @patch("config.deployment.topology.subprocess.run")
    def test_fails_closed_when_az_command_fails(self, mock_run: object) -> None:
        mock_run.return_value = _completed(1, "", "ERROR: not found")

        with self.assertRaisesRegex(Exception, "cannot safely continue"):
            topology.resource_group_exists("rg-test")


class ResourceGroupHasResourcesTests(unittest.TestCase):
    @patch("config.deployment.topology.subprocess.run")
    def test_true_when_resource_group_contains_resources(
        self, mock_run: object
    ) -> None:
        mock_run.return_value = _completed(
            0, "/subscriptions/test/resourceGroups/rg-test/providers/test"
        )

        self.assertTrue(
            topology.resource_group_has_resources(
                "rg-test", "subscription-test"
            )
        )

    @patch("config.deployment.topology.subprocess.run")
    def test_false_when_resource_group_is_empty(self, mock_run: object) -> None:
        mock_run.return_value = _completed(0, "")

        self.assertFalse(topology.resource_group_has_resources("rg-test"))

    @patch("config.deployment.topology.subprocess.run")
    def test_fails_closed_when_resource_query_fails(
        self, mock_run: object
    ) -> None:
        mock_run.return_value = _completed(1, "", "ERROR: forbidden")

        with self.assertRaisesRegex(Exception, "cannot safely continue"):
            topology.resource_group_has_resources("rg-test")


class ReadPersistedSettingsTests(unittest.TestCase):
    def test_empty_endpoint_short_circuits_without_calling_az(self) -> None:
        with patch("config.deployment.topology.subprocess.run") as mock_run:
            self.assertEqual({}, topology.read_persisted_settings(""))
            self.assertEqual({}, topology.read_persisted_settings(None))
            mock_run.assert_not_called()

    @patch("config.deployment.topology.subprocess.run")
    def test_reads_only_keys_that_exist(self, mock_run: object) -> None:
        mock_run.return_value = _completed(
            0,
            json.dumps(
                [
                    {"key": "DEPLOYMENT_TOPOLOGY", "value": "classic"},
                    {"key": "UNRELATED", "value": "ignored"},
                ]
            ),
        )

        settings = topology.read_persisted_settings("https://appconfig.example.test")

        self.assertEqual({"DEPLOYMENT_TOPOLOGY": "classic"}, settings)

    @patch("config.deployment.topology.subprocess.run")
    def test_returns_empty_when_nothing_persisted(self, mock_run: object) -> None:
        mock_run.return_value = _completed(0, "[]")

        settings = topology.read_persisted_settings("https://appconfig.example.test")

        self.assertEqual({}, settings)

    @patch("config.deployment.topology.subprocess.run")
    def test_fails_closed_when_existing_settings_cannot_be_read(
        self, mock_run: object
    ) -> None:
        mock_run.return_value = _completed(1, "", "ERROR: forbidden")

        with self.assertRaisesRegex(Exception, "cannot safely continue"):
            topology.read_persisted_settings("https://appconfig.example.test")


class ResolveEnvironmentTopologyTests(unittest.TestCase):
    @patch("config.deployment.topology.read_persisted_settings")
    @patch("config.deployment.topology.resource_group_exists")
    def test_fresh_environment_defaults_to_hosted_no_panel(
        self, mock_rg_exists: object, mock_read_settings: object
    ) -> None:
        mock_rg_exists.return_value = False

        mode = topology.resolve_environment_topology(
            {}, resource_group_name="rg-test", app_config_endpoint="https://x"
        )

        self.assertEqual(DeploymentMode.HOSTED_NO_PANEL, mode)
        mock_read_settings.assert_not_called()

    @patch("config.deployment.topology.read_persisted_settings")
    @patch("config.deployment.topology.resource_group_exists")
    def test_unmarked_existing_environment_stays_classic_without_private_lookup(
        self, mock_rg_exists: object, mock_read_settings: object
    ) -> None:
        mock_rg_exists.return_value = True
        mock_read_settings.side_effect = RuntimeError(
            "private App Configuration is inaccessible"
        )

        mode = topology.resolve_environment_topology(
            {},
            resource_group_name="rg-test",
            app_config_endpoint="https://private.example.test",
        )

        self.assertEqual(DeploymentMode.CLASSIC, mode)
        mock_read_settings.assert_not_called()

    @patch("config.deployment.topology.read_persisted_settings")
    @patch(
        "config.deployment.topology.resource_group_has_resources",
        return_value=False,
    )
    @patch("config.deployment.topology.resource_group_exists")
    def test_explicit_hosted_empty_azd_resource_group_is_fresh(
        self,
        mock_rg_exists: object,
        _mock_has_resources: object,
        mock_read_settings: object,
    ) -> None:
        mock_rg_exists.return_value = True

        mode = topology.resolve_environment_topology(
            {"DEPLOYMENT_TOPOLOGY": "hosted-panel"},
            resource_group_name="rg-test",
            app_config_endpoint="https://x",
        )

        self.assertEqual(DeploymentMode.HOSTED_PANEL, mode)
        mock_read_settings.assert_not_called()

    @patch("config.deployment.topology.read_persisted_settings")
    @patch("config.deployment.topology.resource_group_exists")
    def test_explicit_classic_skips_all_azure_lookups(
        self, mock_rg_exists: object, mock_read_settings: object
    ) -> None:
        mode = topology.resolve_environment_topology(
            {"DEPLOYMENT_TOPOLOGY": "classic"},
            resource_group_name="rg-test",
            app_config_endpoint="https://x",
        )

        self.assertEqual(DeploymentMode.CLASSIC, mode)
        mock_rg_exists.assert_not_called()
        mock_read_settings.assert_not_called()

    @patch("config.deployment.topology.read_persisted_settings")
    @patch(
        "config.deployment.topology.resource_group_has_resources",
        return_value=True,
    )
    @patch("config.deployment.topology.resource_group_exists")
    def test_explicit_hosted_migration_preserves_existing_classic_runtime(
        self,
        mock_rg_exists: object,
        _mock_has_resources: object,
        mock_read_settings: object,
    ) -> None:
        mock_rg_exists.return_value = True
        mock_read_settings.return_value = {
            "DEPLOYMENT_TOPOLOGY": "classic",
            "CHAT_BACKEND": "orchestrator",
        }

        resolution = topology.resolve_environment_plan(
            {"DEPLOYMENT_TOPOLOGY": "hosted-no-panel"},
            resource_group_name="rg-test",
            app_config_endpoint="https://x",
        )

        self.assertEqual(DeploymentMode.HOSTED_NO_PANEL, resolution.mode)
        self.assertTrue(resolution.preserve_classic_runtime)
        mock_read_settings.assert_called_once_with("https://x")

    @patch("config.deployment.topology.read_persisted_settings")
    @patch("config.deployment.topology.resource_group_exists")
    def test_explicit_hosted_existing_hosted_does_not_preserve_classic(
        self, mock_rg_exists: object, mock_read_settings: object
    ) -> None:
        mock_rg_exists.return_value = True
        mock_read_settings.return_value = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "CHAT_BACKEND": "hosted_agent",
        }

        resolution = topology.resolve_environment_plan(
            {
                "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
                "CHAT_BACKEND": "hosted_agent",
            },
            resource_group_name="rg-test",
            app_config_endpoint="https://x",
        )

        self.assertFalse(resolution.preserve_classic_runtime)

    @patch("config.deployment.topology.read_persisted_settings")
    @patch(
        "config.deployment.topology.resource_group_has_resources",
        return_value=True,
    )
    @patch("config.deployment.topology.resource_group_exists")
    def test_ambiguous_existing_hosted_request_preserves_persisted_classic(
        self,
        mock_rg_exists: object,
        _mock_has_resources: object,
        mock_read_settings: object,
    ) -> None:
        mock_rg_exists.return_value = True
        mock_read_settings.return_value = {}

        resolution = topology.resolve_environment_plan(
            {"DEPLOYMENT_TOPOLOGY": "hosted-no-panel"},
            resource_group_name="rg-test",
            app_config_endpoint="https://private.example.test",
        )

        self.assertTrue(resolution.preserve_classic_runtime)
        mock_read_settings.assert_called_once_with(
            "https://private.example.test"
        )

    @patch("config.deployment.topology.read_persisted_settings")
    @patch(
        "config.deployment.topology.resource_group_has_resources",
        return_value=True,
    )
    @patch("config.deployment.topology.resource_group_exists")
    def test_ambiguous_explicit_hosted_request_fails_when_state_is_inaccessible(
        self,
        mock_rg_exists: object,
        _mock_has_resources: object,
        mock_read_settings: object,
    ) -> None:
        mock_rg_exists.return_value = True
        mock_read_settings.side_effect = topology.DeploymentTopologyError(
            "cannot safely continue"
        )

        with self.assertRaisesRegex(Exception, "cannot safely continue"):
            topology.resolve_environment_plan(
                {"DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true"},
                resource_group_name="rg-test",
                app_config_endpoint="https://private.example.test",
            )

    @patch("config.deployment.topology.read_persisted_settings")
    @patch("config.deployment.topology.resource_group_exists")
    def test_partial_local_state_fails_when_persisted_state_is_inaccessible(
        self, mock_rg_exists: object, mock_read_settings: object
    ) -> None:
        mock_rg_exists.return_value = True
        mock_read_settings.side_effect = topology.DeploymentTopologyError(
            "cannot safely continue"
        )

        with self.assertRaisesRegex(Exception, "cannot safely continue"):
            topology.resolve_environment_plan(
                {"CHAT_BACKEND": "hosted_agent"},
                resource_group_name="rg-test",
                app_config_endpoint="https://private.example.test",
            )

    @patch("config.deployment.topology.read_persisted_settings")
    @patch("config.deployment.topology.resource_group_exists")
    def test_legacy_hosted_contract_reads_missing_ingestion_selection(
        self, mock_rg_exists: object, mock_read_settings: object
    ) -> None:
        mock_rg_exists.return_value = True
        mock_read_settings.return_value = {}

        resolution = topology.resolve_environment_plan(
            {
                "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
                "DEPLOY_ADMINISTRATIVE_PANEL": "false",
                "HOSTED_AGENT_BASE_URL": (
                    "https://agent.example.test/protocols"
                ),
                "HOSTED_AGENT_IMAGE_VERSION": "sha256:" + ("a" * 64),
            },
            resource_group_name="rg-test",
            app_config_endpoint="https://private.example.test",
        )

        self.assertEqual(DeploymentMode.HOSTED_NO_PANEL, resolution.mode)
        self.assertFalse(resolution.preserve_classic_runtime)
        mock_read_settings.assert_called_once_with("https://private.example.test")

    @patch("config.deployment.topology.read_persisted_settings")
    @patch("config.deployment.topology.resource_group_exists")
    def test_materialized_fresh_hosted_skips_private_appconfig_lookup(
        self, mock_rg_exists: object, mock_read_settings: object
    ) -> None:
        mock_rg_exists.return_value = True

        resolution = topology.resolve_environment_plan(
            {
                "DEPLOY_INGESTION_CONTAINER_APP": "false",
                "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
                "CHAT_BACKEND": "hosted_agent",
                "PRESERVE_CLASSIC_RUNTIME": "false",
            },
            resource_group_name="rg-test",
            app_config_endpoint="https://private.example.test",
        )

        self.assertFalse(resolution.preserve_classic_runtime)
        mock_read_settings.assert_not_called()

    @patch("config.deployment.topology.read_persisted_settings")
    @patch("config.deployment.topology.resource_group_exists")
    def test_materialized_classic_detects_migration_without_private_lookup(
        self, mock_rg_exists: object, mock_read_settings: object
    ) -> None:
        mock_rg_exists.return_value = True

        resolution = topology.resolve_environment_plan(
            {
                "DEPLOY_INGESTION_CONTAINER_APP": "true",
                "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
                "CHAT_BACKEND": "orchestrator",
                "PRESERVE_CLASSIC_RUNTIME": "false",
            },
            resource_group_name="rg-test",
            app_config_endpoint="https://private.example.test",
        )

        self.assertTrue(resolution.preserve_classic_runtime)
        mock_read_settings.assert_not_called()

    @patch("config.deployment.topology.read_persisted_settings")
    @patch("config.deployment.topology.resource_group_exists")
    def test_materialized_migration_clears_after_cutover_without_private_lookup(
        self, mock_rg_exists: object, mock_read_settings: object
    ) -> None:
        mock_rg_exists.return_value = True

        resolution = topology.resolve_environment_plan(
            {
                "DEPLOY_INGESTION_CONTAINER_APP": "true",
                "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
                "CHAT_BACKEND": "hosted_agent",
                "PRESERVE_CLASSIC_RUNTIME": "true",
                "HOSTED_CUTOVER_COMPLETE": "true",
                "HOSTED_AGENT_BASE_URL": "https://agent.example.test/protocols",
                "HOSTED_AGENT_IMAGE_VERSION": "sha256:" + ("a" * 64),
            },
            resource_group_name="rg-test",
            app_config_endpoint="https://private.example.test",
        )

        self.assertFalse(resolution.preserve_classic_runtime)
        mock_read_settings.assert_not_called()


class MainCliTests(unittest.TestCase):
    @patch("config.deployment.topology.resource_group_exists", return_value=False)
    def test_default_mode_prints_materialized_settings(
        self, _mock_rg_exists: object
    ) -> None:
        argv = ["prog"]
        env = {"AZURE_RESOURCE_GROUP": "rg-test"}
        with patch("sys.argv", argv), patch("os.environ", env):
            with patch("builtins.print") as mock_print:
                exit_code = topology.main()

        self.assertEqual(0, exit_code)
        printed = "\n".join(call.args[0] for call in mock_print.call_args_list)
        self.assertIn("DEPLOYMENT_TOPOLOGY=hosted-no-panel", printed)
        self.assertIn("CHAT_BACKEND=hosted_agent", printed)
        self.assertIn("PRESERVE_CLASSIC_RUNTIME=false", printed)

    def test_describe_mode_prints_json_without_any_azure_cli_call(self) -> None:
        argv = ["prog", "--describe"]
        env = {"DEPLOYMENT_TOPOLOGY": "classic"}
        with patch("sys.argv", argv), patch("os.environ", env):
            with patch("config.deployment.topology.subprocess.run") as mock_run:
                with patch("builtins.print") as mock_print:
                    exit_code = topology.main()
                mock_run.assert_not_called()

        self.assertEqual(0, exit_code)
        (payload,) = mock_print.call_args_list[0].args
        description = json.loads(payload)
        self.assertEqual("classic", description["topology"])
        self.assertEqual("orchestrator", description["chat_backend"])
        self.assertTrue(description["deploy_cosmos_db"])

    def test_describe_includes_explicit_hosted_cosmos_selection_without_azure_calls(self) -> None:
        for selected in ("true", "false"):
            with self.subTest(selected=selected):
                environment = {
                    "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
                    "DEPLOY_COSMOS_DB": selected,
                }
                with patch("sys.argv", ["prog", "--describe"]), patch("os.environ", environment):
                    with patch("config.deployment.topology.subprocess.run") as run:
                        with patch("builtins.print") as output:
                            self.assertEqual(0, topology.main())
                        run.assert_not_called()
                self.assertEqual(
                    selected == "true", json.loads(output.call_args.args[0])["deploy_cosmos_db"]
                )

    def test_describe_preserves_migrating_runtime_until_cutover(self) -> None:
        argv = ["prog", "--describe"]
        env = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "PRESERVE_CLASSIC_RUNTIME": "true",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "HOSTED_AGENT_IMAGE_VERSION": "sha256:" + ("a" * 64),
        }
        with patch("sys.argv", argv), patch("os.environ", env):
            with patch("builtins.print") as mock_print:
                exit_code = topology.main()

        self.assertEqual(0, exit_code)
        description = json.loads(mock_print.call_args.args[0])
        self.assertEqual("hosted-no-panel", description["topology"])
        self.assertTrue(description["deploy_hosted_agent_orchestration"])
        self.assertEqual("classic", description["runtime_topology"])
        self.assertEqual("orchestrator", description["runtime_chat_backend"])
        self.assertTrue(description["deploy_cosmos_db"])

    @patch(
        "config.deployment.topology.read_persisted_settings",
        return_value={
            "DEPLOYMENT_TOPOLOGY": "classic",
            "CHAT_BACKEND": "orchestrator",
        },
    )
    @patch("config.deployment.topology.resource_group_exists", return_value=True)
    def test_materialize_preserves_migrating_runtime_until_cutover(
        self,
        _mock_rg_exists: object,
        _mock_read_settings: object,
    ) -> None:
        argv = ["prog"]
        env = {
            "AZURE_RESOURCE_GROUP": "rg-test",
            "APP_CONFIG_ENDPOINT": "https://x",
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "HOSTED_AGENT_IMAGE_VERSION": "sha256:" + ("a" * 64),
        }
        with patch("sys.argv", argv), patch("os.environ", env):
            with patch("builtins.print") as mock_print:
                exit_code = topology.main()

        self.assertEqual(0, exit_code)
        printed = "\n".join(call.args[0] for call in mock_print.call_args_list)
        self.assertIn("DEPLOYMENT_TOPOLOGY=hosted-no-panel", printed)
        self.assertIn("DEPLOY_HOSTED_AGENT_ORCHESTRATION=false", printed)
        self.assertIn("CHAT_BACKEND=orchestrator", printed)
        self.assertIn("PRESERVE_CLASSIC_RUNTIME=true", printed)

    @patch(
        "config.deployment.topology.read_persisted_settings",
        return_value={
            "DEPLOYMENT_TOPOLOGY": "classic",
            "CHAT_BACKEND": "orchestrator",
        },
    )
    @patch("config.deployment.topology.resource_group_exists", return_value=True)
    def test_materialize_switches_migrating_runtime_after_cutover(
        self,
        _mock_rg_exists: object,
        _mock_read_settings: object,
    ) -> None:
        argv = ["prog"]
        env = {
            "AZURE_RESOURCE_GROUP": "rg-test",
            "APP_CONFIG_ENDPOINT": "https://x",
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "HOSTED_CUTOVER_COMPLETE": "true",
            "HOSTED_AGENT_BASE_URL": "https://agent.example",
            "HOSTED_AGENT_IMAGE_VERSION": "sha256:" + ("a" * 64),
        }
        with patch("sys.argv", argv), patch("os.environ", env):
            with patch("builtins.print") as mock_print:
                exit_code = topology.main()

        self.assertEqual(0, exit_code)
        printed = "\n".join(call.args[0] for call in mock_print.call_args_list)
        self.assertIn("DEPLOYMENT_TOPOLOGY=hosted-no-panel", printed)
        self.assertIn("DEPLOY_HOSTED_AGENT_ORCHESTRATION=true", printed)
        self.assertIn("CHAT_BACKEND=hosted_agent", printed)
        self.assertIn("PRESERVE_CLASSIC_RUNTIME=false", printed)

    def test_describe_reports_hosted_runtime_after_cutover(self) -> None:
        argv = ["prog", "--describe"]
        env = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "PRESERVE_CLASSIC_RUNTIME": "true",
            "HOSTED_CUTOVER_COMPLETE": "true",
            "HOSTED_AGENT_BASE_URL": "https://agent.example.test/protocols",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "HOSTED_AGENT_IMAGE_VERSION": "sha256:" + ("a" * 64),
        }
        with patch("sys.argv", argv), patch("os.environ", env):
            with patch("builtins.print") as mock_print:
                exit_code = topology.main()

        self.assertEqual(0, exit_code)
        description = json.loads(mock_print.call_args.args[0])
        self.assertEqual("hosted-no-panel", description["runtime_topology"])
        self.assertEqual("hosted_agent", description["runtime_chat_backend"])
        self.assertFalse(description["deploy_cosmos_db"])

    def test_validate_hosted_deploy_rejects_missing_foundry_project(self) -> None:
        argv = ["prog", "--validate-hosted-deploy"]
        env = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            "HOSTED_AGENT_IMAGE_VERSION": "sha256:" + ("a" * 64),
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
        }
        with patch("sys.argv", argv), patch("os.environ", env):
            with patch("builtins.print") as mock_print:
                exit_code = topology.main()

        self.assertEqual(1, exit_code)
        self.assertIn("AZURE_AI_PROJECT_ENDPOINT", mock_print.call_args.args[0])

    def test_validate_hosted_context_allows_digest_to_be_prepared_later(
        self,
    ) -> None:
        argv = ["prog", "--validate-hosted-context"]
        env = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "AZURE_AI_PROJECT_ENDPOINT": "https://project.example.test",
            "AZURE_AI_PROJECT_RESOURCE_ID": "/subscriptions/test/projects/p",
        }
        with patch("sys.argv", argv), patch("os.environ", env):
            with patch("builtins.print") as mock_print:
                exit_code = topology.main()

        self.assertEqual(0, exit_code)
        (payload,) = mock_print.call_args_list[0].args
        self.assertEqual("hosted-no-panel", json.loads(payload)["topology"])

    def test_validate_hosted_deploy_rejects_unprepared_image(self) -> None:
        argv = ["prog", "--validate-hosted-deploy"]
        env = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true",
            "DEPLOY_ADMINISTRATIVE_PANEL": "false",
            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            "AZURE_AI_PROJECT_ENDPOINT": "https://project.example.test",
            "AZURE_AI_PROJECT_RESOURCE_ID": "/subscriptions/test/projects/p",
        }
        with patch("sys.argv", argv), patch("os.environ", env):
            with patch("builtins.print") as mock_print:
                exit_code = topology.main()

        self.assertEqual(1, exit_code)
        self.assertIn(
            "HOSTED_AGENT_IMAGE_VERSION",
            mock_print.call_args.args[0],
        )

    def test_canonical_topology_overrides_stale_compatibility_flag(
        self,
    ) -> None:
        argv = ["prog", "--describe"]
        env = {
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
        }
        with patch("sys.argv", argv), patch("os.environ", env):
            with patch("builtins.print") as mock_print:
                exit_code = topology.main()

        self.assertEqual(0, exit_code)
        (payload,) = mock_print.call_args_list[0].args
        description = json.loads(payload)
        self.assertEqual("hosted-no-panel", description["topology"])


if __name__ == "__main__":
    unittest.main()
