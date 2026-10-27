from __future__ import annotations

import copy
import json
import os
import subprocess
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

from config.deployment.composition import hosted_startup_command_sha256
from config.deployment.hosted_prepare import (
    persist_digest,
    prepare_deployment,
    prepare_environment,
    main,
)
from config.deployment.private_network import PrivateNetworkError


DIGEST = "sha256:" + ("a" * 64)
NEW_DIGEST = "sha256:" + ("b" * 64)
SOURCE_COMMIT = "eaa787340c27d8df5bb550147e95c5ecd02ad385"
OLD_COMMIT = "1" * 40
MANIFEST = {
    "components": [
        {
            "name": "agent-app-orchestrator",
            "repo": "https://github.com/Azure/agent-app-orchestrator.git",
            "tag": "v3.10.0",
            "commit": SOURCE_COMMIT,
        }
    ]
}


def hosted_environment(**overrides: str) -> dict[str, str]:
    environment = {
        "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
        "HOSTED_AGENT_PREPARED": "true",
        "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
        "AZURE_AI_PROJECT_ENDPOINT": "https://project.example.test",
        "AZURE_AI_PROJECT_RESOURCE_ID": "/subscriptions/s/resourceGroups/r/providers/Microsoft.CognitiveServices/accounts/a/projects/p",
        "AZURE_CONTAINER_REGISTRY_ENDPOINT": "registry.azurecr.io",
        "AZURE_RESOURCE_GROUP": "rg-test",
        "NETWORK_ISOLATION": "false",
    }
    environment.update(overrides)
    return environment


class PrepareEnvironmentTests(unittest.TestCase):
    @patch("config.deployment.hosted_prepare.resolve_az_command", return_value="az")
    @patch("config.deployment.hosted_prepare.prepare_hosted_image", return_value=NEW_DIGEST)
    def test_foundry_split_never_moves_acr_builds_and_declared_registry_id_wins(self, prepare, resolve):
        subscription = "11111111-1111-1111-1111-111111111111"
        for declared, expected in (("", "rg-test"), (
            f"/subscriptions/{subscription}/resourceGroups/rg-registry/providers/Microsoft.ContainerRegistry/registries/registry",
            "rg-registry",
        )):
            environment = hosted_environment(
                AZURE_SUBSCRIPTION_ID=subscription,
                AZURE_RESOURCE_GROUP="rg-foundry",
                AZURE_APP_RESOURCE_GROUP="rg-test",
                AZURE_NETWORK_RESOURCE_GROUP="rg-network",
                AZURE_CONTAINER_REGISTRY_RESOURCE_ID=declared,
            )
            with self.subTest(declared=bool(declared)):
                prepare_environment(environment, MANIFEST)
                self.assertEqual(expected, prepare.call_args.kwargs["resource_group"])

    @patch("config.deployment.hosted_prepare.prepare_hosted_image")
    def test_classic_topology_is_a_no_build_noop(
        self, mock_prepare: MagicMock
    ) -> None:
        digest, source_commit = prepare_environment(
            {"DEPLOYMENT_TOPOLOGY": "classic"},
            MANIFEST,
        )

        self.assertIsNone(digest)
        self.assertIsNone(source_commit)
        mock_prepare.assert_not_called()

    @patch("config.deployment.hosted_prepare.resolve_az_command")
    @patch("config.deployment.hosted_prepare.prepare_hosted_image")
    def test_public_build_uses_manifest_pin_without_agent_pool(
        self,
        mock_prepare: MagicMock,
        mock_resolve_az: MagicMock,
    ) -> None:
        mock_prepare.return_value = NEW_DIGEST
        mock_resolve_az.return_value = "az"

        digest, source_commit = prepare_environment(
            hosted_environment(),
            MANIFEST,
        )

        self.assertEqual(NEW_DIGEST, digest)
        self.assertEqual(SOURCE_COMMIT, source_commit)
        self.assertEqual(
            "v3.10.0",
            mock_prepare.call_args.kwargs["source_ref"],
        )
        self.assertEqual(
            SOURCE_COMMIT,
            mock_prepare.call_args.kwargs["source_commit"],
        )
        self.assertIsNone(mock_prepare.call_args.kwargs["agent_pool"])

    @patch("config.deployment.hosted_prepare.prepare_hosted_image")
    def test_custom_startup_command_fails_closed(
        self,
        mock_prepare: MagicMock,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError, "Custom HOSTED_AGENT_STARTUP_COMMAND"
        ):
            prepare_environment(
                hosted_environment(
                    HOSTED_AGENT_STARTUP_COMMAND="python -m custom.hosted"
                ),
                MANIFEST,
            )
        mock_prepare.assert_not_called()

    @patch("config.deployment.hosted_prepare.check_stage")
    @patch("config.deployment.hosted_prepare.resolve_az_command")
    @patch("config.deployment.hosted_prepare.prepare_hosted_image")
    def test_private_build_uses_provisioned_agent_pool(
        self,
        mock_prepare: MagicMock,
        mock_resolve_az: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        mock_prepare.return_value = NEW_DIGEST
        mock_resolve_az.return_value = "az"

        environment = hosted_environment(
            NETWORK_ISOLATION="true",
            ACR_TASK_AGENT_POOL="build-pool",
        )
        events: list[str] = []
        mock_check.side_effect = lambda *_: events.append("probe")
        mock_prepare.side_effect = lambda **_: events.append("build") or NEW_DIGEST
        prepare_environment(environment, MANIFEST)
        mock_check.assert_called_once_with(environment, "hosted-build")
        self.assertEqual(["probe", "build"], events)

        self.assertEqual(
            "build-pool",
            mock_prepare.call_args.kwargs["agent_pool"],
        )

    @patch("config.deployment.hosted_prepare.prepare_hosted_image")
    def test_private_build_fails_without_agent_pool(
        self, mock_prepare: MagicMock
    ) -> None:
        with self.assertRaisesRegex(ValueError, "ACR_TASK_AGENT_POOL"):
            prepare_environment(
                hosted_environment(NETWORK_ISOLATION="true"),
                MANIFEST,
            )
        mock_prepare.assert_not_called()

    @patch("config.deployment.hosted_prepare.check_stage")
    @patch("config.deployment.hosted_prepare.prepare_hosted_image")
    def test_failed_network_prerequisite_never_builds(
        self, mock_prepare: MagicMock, mock_check: MagicMock,
    ) -> None:
        mock_check.side_effect = PrivateNetworkError("private DNS failed")
        with self.assertRaisesRegex(PrivateNetworkError, "private DNS"):
            prepare_environment(hosted_environment(
                NETWORK_ISOLATION="true", ACR_TASK_AGENT_POOL="build-pool",
                RUN_FROM_JUMPBOX="true",
            ), MANIFEST)
        mock_check.assert_called_once()
        mock_prepare.assert_not_called()

    @patch("config.deployment.hosted_prepare.check_stage")
    def test_private_immutable_paths_validate_digest_without_probe(
        self, mock_check: MagicMock,
    ) -> None:
        environment = hosted_environment(
            NETWORK_ISOLATION="true", AZURE_CONTAINER_REGISTRY_ENDPOINT="",
        )
        for overrides, command_digest, source in (
            ({}, DIGEST, None),
            ({"HOSTED_AGENT_IMAGE_VERSION": DIGEST}, None, None),
            ({
                "HOSTED_AGENT_IMAGE_VERSION": DIGEST,
                "HOSTED_AGENT_IMAGE_SOURCE_COMMIT": SOURCE_COMMIT,
                "HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256": hosted_startup_command_sha256(environment),
            }, None, SOURCE_COMMIT),
        ):
            with self.subTest(overrides=overrides, command_digest=command_digest):
                self.assertEqual((DIGEST, source), prepare_environment(
                    {**environment, **overrides}, MANIFEST, image_version_override=command_digest,
                ))
        with self.assertRaises(ValueError):
            prepare_environment(environment, MANIFEST, image_version_override="latest")
        self.assertEqual((None, None), prepare_environment(
            {"DEPLOYMENT_TOPOLOGY": "classic", "NETWORK_ISOLATION": "true"}, MANIFEST,
        ))
        mock_check.assert_not_called()

    @patch("config.deployment.hosted_prepare.prepare_hosted_image")
    def test_explicit_digest_override_skips_build(
        self, mock_prepare: MagicMock
    ) -> None:
        mock_prepare.return_value = DIGEST

        digest, source_commit = prepare_environment(
            hosted_environment(HOSTED_AGENT_IMAGE_VERSION=DIGEST),
            MANIFEST,
        )

        self.assertEqual(DIGEST, digest)
        self.assertIsNone(source_commit)
        self.assertEqual(
            DIGEST,
            mock_prepare.call_args.kwargs["image_version"],
        )
        self.assertEqual("", mock_prepare.call_args.kwargs["source_repo"])

    @patch("config.deployment.hosted_prepare.prepare_hosted_image")
    def test_command_override_clears_stale_generated_provenance(
        self, mock_prepare: MagicMock
    ) -> None:
        mock_prepare.return_value = NEW_DIGEST

        digest, source_commit = prepare_environment(
            hosted_environment(
                HOSTED_AGENT_IMAGE_VERSION=DIGEST,
                HOSTED_AGENT_IMAGE_SOURCE_COMMIT=SOURCE_COMMIT,
            ),
            MANIFEST,
            image_version_override=NEW_DIGEST,
        )

        self.assertEqual(NEW_DIGEST, digest)
        self.assertIsNone(source_commit)
        self.assertEqual(
            NEW_DIGEST,
            mock_prepare.call_args.kwargs["image_version"],
        )

    @patch("config.deployment.hosted_prepare.resolve_az_command")
    @patch("config.deployment.hosted_prepare.prepare_hosted_image")
    def test_stale_generated_digest_rebuilds_current_manifest_pin(
        self,
        mock_prepare: MagicMock,
        mock_resolve_az: MagicMock,
    ) -> None:
        mock_prepare.return_value = NEW_DIGEST
        mock_resolve_az.return_value = "az"

        digest, source_commit = prepare_environment(
            hosted_environment(
                HOSTED_AGENT_IMAGE_VERSION=DIGEST,
                HOSTED_AGENT_IMAGE_SOURCE_COMMIT=OLD_COMMIT,
            ),
            MANIFEST,
        )

        self.assertEqual(NEW_DIGEST, digest)
        self.assertEqual(SOURCE_COMMIT, source_commit)
        self.assertIsNone(mock_prepare.call_args.kwargs["image_version"])

    @patch("config.deployment.hosted_prepare.prepare_hosted_image")
    def test_changed_startup_command_fails_before_digest_reuse(
        self,
        mock_prepare: MagicMock,
    ) -> None:
        original_environment = hosted_environment()

        with self.assertRaisesRegex(
            ValueError, "Custom HOSTED_AGENT_STARTUP_COMMAND"
        ):
            prepare_environment(
                hosted_environment(
                    HOSTED_AGENT_IMAGE_VERSION=DIGEST,
                    HOSTED_AGENT_IMAGE_SOURCE_COMMIT=SOURCE_COMMIT,
                    HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256=(
                        hosted_startup_command_sha256(original_environment)
                    ),
                    HOSTED_AGENT_STARTUP_COMMAND="python -m custom.hosted",
                ),
                MANIFEST,
            )
        mock_prepare.assert_not_called()


class PersistDigestTests(unittest.TestCase):
    @patch("config.deployment.hosted_prepare.shutil.which")
    @patch("config.deployment.hosted_prepare.subprocess.run")
    def test_persists_digest_and_generated_source_commit(
        self,
        mock_run: MagicMock,
        mock_which: MagicMock,
    ) -> None:
        mock_which.return_value = "azd"
        mock_run.return_value = subprocess.CompletedProcess([], 0)

        persist_digest(
            {"AZURE_ENV_NAME": "test"},
            DIGEST,
            SOURCE_COMMIT,
        )

        self.assertEqual(4, mock_run.call_count)
        commands = [call.args[0] for call in mock_run.call_args_list]
        self.assertEqual(
            [
                "HOSTED_AGENT_IMAGE_VERSION",
                "HOSTED_AGENT_IMAGE_SOURCE_COMMIT",
                "HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256",
                "HOSTED_AGENT_IMAGE_VERSION",
            ],
            [command[3] for command in commands],
        )
        self.assertEqual("", commands[0][4])
        self.assertEqual(SOURCE_COMMIT, commands[1][4])
        self.assertEqual(64, len(commands[2][4]))
        self.assertEqual(DIGEST, commands[3][4])

    @patch("config.deployment.hosted_prepare.shutil.which")
    @patch("config.deployment.hosted_prepare.subprocess.run")
    def test_explicit_override_clears_generated_source_commit(
        self,
        mock_run: MagicMock,
        mock_which: MagicMock,
    ) -> None:
        mock_which.return_value = "azd"
        mock_run.return_value = subprocess.CompletedProcess([], 0)

        persist_digest(
            {"AZURE_ENV_NAME": "test"},
            DIGEST,
            None,
        )

        commands = [call.args[0] for call in mock_run.call_args_list]
        source_command = next(
            command
            for command in commands
            if "HOSTED_AGENT_IMAGE_SOURCE_COMMIT" in command
        )
        source_index = source_command.index(
            "HOSTED_AGENT_IMAGE_SOURCE_COMMIT"
        )
        self.assertEqual("", source_command[source_index + 1])

    @patch("config.deployment.hosted_prepare.shutil.which")
    @patch("config.deployment.hosted_prepare.subprocess.run")
    def test_partial_persistence_never_leaves_digest_without_provenance(
        self,
        mock_run: MagicMock,
        mock_which: MagicMock,
    ) -> None:
        mock_which.return_value = "azd"
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
            subprocess.CalledProcessError(1, ["azd"]),
        ]

        with self.assertRaises(subprocess.CalledProcessError):
            persist_digest(
                {"AZURE_ENV_NAME": "test"},
                DIGEST,
                SOURCE_COMMIT,
            )

        commands = [call.args[0] for call in mock_run.call_args_list]
        first_digest_index = commands[0].index(
            "HOSTED_AGENT_IMAGE_VERSION"
        )
        source_index = commands[1].index(
            "HOSTED_AGENT_IMAGE_SOURCE_COMMIT"
        )
        startup_index = commands[2].index(
            "HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256"
        )
        final_digest_index = commands[3].index(
            "HOSTED_AGENT_IMAGE_VERSION"
        )
        self.assertEqual("", commands[0][first_digest_index + 1])
        self.assertEqual(SOURCE_COMMIT, commands[1][source_index + 1])
        self.assertEqual(64, len(commands[2][startup_index + 1]))
        self.assertEqual(DIGEST, commands[3][final_digest_index + 1])


def deployment_environment(**overrides: str) -> dict[str, str]:
    environment = hosted_environment(AZURE_ENV_NAME="test", DEPLOY_HOSTED_AGENT="false")
    environment["HOSTED_AGENT_DEPLOYMENT"] = json.dumps({
        "enabled": False,
        "agent": None,
        "foundry": {
            "projectResourceId": environment["AZURE_AI_PROJECT_RESOURCE_ID"],
            "projectEndpoint": environment["AZURE_AI_PROJECT_ENDPOINT"],
            "projectPrincipalId": "project-principal",
            "agentSubnetResourceId": "agent-subnet",
        },
        "containerRegistry": {
            "endpoint": environment["AZURE_CONTAINER_REGISTRY_ENDPOINT"],
            "resourceId": "registry-id",
        },
        "privateBuild": {"required": False, "acrTaskAgentPoolName": ""},
        "workloadEgress": {"networkIsolation": False, "managedFirewallPolicyId": ""},
    })
    environment.update(overrides)
    return environment


class PrepareDeploymentTests(unittest.TestCase):
    @patch("config.deployment.hosted_prepare.resolve_az_command", return_value="az")
    @patch("config.deployment.hosted_prepare.subprocess.run")
    @patch("config.deployment.hosted_prepare.prepare_hosted_image", return_value=NEW_DIGEST)
    def test_prepare_only_foundation_is_sufficient(self, build, run, resolve) -> None:
        environment = deployment_environment()
        original = copy.deepcopy(environment)
        values = prepare_deployment(environment, MANIFEST)
        self.assertEqual(original, environment)
        self.assertEqual(NEW_DIGEST, values["HOSTED_AGENT_IMAGE_VERSION"])
        self.assertEqual(SOURCE_COMMIT, values["HOSTED_AGENT_IMAGE_SOURCE_COMMIT"])
        self.assertEqual("true", values["DEPLOY_HOSTED_AGENT"])
        handoff = json.loads(values["HOSTED_AGENT_DEPLOYMENT"])
        foundation = json.loads(environment["HOSTED_AGENT_DEPLOYMENT"])
        for section in ("foundry", "containerRegistry", "privateBuild", "workloadEgress"):
            self.assertEqual(foundation[section], handoff[section])
        self.assertTrue(handoff["enabled"])
        agent = handoff["agent"]
        self.assertEqual(NEW_DIGEST, agent["imageVersion"])
        self.assertEqual(f"registry.azurecr.io/agent-app-orchestrator@{NEW_DIGEST}", agent["image"])
        self.assertEqual({"cpu": "2", "memory": "4Gi"}, agent["runtime"])
        self.assertEqual(["responses", "invocations"], [p["protocol"] for p in agent["protocols"]])
        self.assertIn("src.api.hosted_entrypoint:app", agent["startupCommand"])
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(6, len(commands))
        self.assertTrue(all(command[1:3] == ["env", "set"] for command in commands))
        self.assertEqual(
            ["HOSTED_AGENT_DEPLOYMENT", "DEPLOY_HOSTED_AGENT"],
            [command[3] for command in commands[-2:]],
        )
        self.assertEqual(SOURCE_COMMIT, build.call_args.kwargs["source_commit"])

    @patch("config.deployment.hosted_prepare.subprocess.run")
    def test_explicit_and_unchanged_generated_digests_skip_builds(self, run) -> None:
        environment = deployment_environment(HOSTED_AGENT_IMAGE_VERSION=DIGEST)
        for provenance in (
            {},
            {
                "HOSTED_AGENT_IMAGE_SOURCE_COMMIT": SOURCE_COMMIT,
                "HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256": hosted_startup_command_sha256(environment),
            },
        ):
            with self.subTest(provenance=provenance), patch(
                "config.deployment.hosted_image.clone_pinned_source"
            ) as clone:
                values = prepare_deployment({**environment, **provenance}, MANIFEST)
                self.assertEqual(DIGEST, values["HOSTED_AGENT_IMAGE_VERSION"])
                clone.assert_not_called()

    @patch("config.deployment.hosted_prepare.prepare_hosted_image")
    @patch("config.deployment.hosted_prepare.subprocess.run")
    def test_invalid_foundation_never_builds_or_persists(self, run, build) -> None:
        environment = deployment_environment()
        for raw in ("", "[]", "{", "{}", json.dumps({
            **json.loads(environment["HOSTED_AGENT_DEPLOYMENT"]),
            "foundry": {"projectEndpoint": "https://different.example.test"},
        }), json.dumps({
            **json.loads(environment["HOSTED_AGENT_DEPLOYMENT"]),
            "containerRegistry": {"endpoint": "other.azurecr.io"},
        })):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                prepare_deployment({**environment, "HOSTED_AGENT_DEPLOYMENT": raw}, MANIFEST)
        build.assert_not_called()
        run.assert_not_called()

    @patch("config.deployment.hosted_prepare.prepare_hosted_image")
    @patch("config.deployment.hosted_prepare.subprocess.run")
    def test_missing_prerequisites_and_mutable_digest_never_publish(self, run, build) -> None:
        for overrides in (
            {"HOSTED_AGENT_PREPARED": "false"},
            {"HOSTED_AGENT_RESOURCE_SCOPE": ""},
            {"HOSTED_AGENT_STARTUP_COMMAND": "python custom.py"},
            {"AZURE_ENV_NAME": ""},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                prepare_deployment(deployment_environment(**overrides), MANIFEST)
        build.return_value = "latest"
        with self.assertRaisesRegex(ValueError, "immutable"):
            prepare_deployment(deployment_environment(HOSTED_AGENT_IMAGE_VERSION="latest"), MANIFEST)
        run.assert_not_called()

    @patch("config.deployment.hosted_prepare.prepare_environment")
    @patch("config.deployment.hosted_prepare.subprocess.run")
    def test_build_failure_never_persists_handoff(self, run, prepare) -> None:
        prepare.side_effect = RuntimeError("ACR build failed")
        with self.assertRaisesRegex(RuntimeError, "ACR build failed"):
            prepare_deployment(deployment_environment(), MANIFEST)
        run.assert_not_called()

    @patch("config.deployment.hosted_prepare.prepare_environment", return_value=(DIGEST, SOURCE_COMMIT))
    @patch("config.deployment.hosted_prepare.subprocess.run")
    def test_cli_emits_only_json_after_all_persistence_succeeds(self, run, prepare) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")
            for fail_at in (None, *range(6)):
                output = StringIO()
                run.reset_mock()
                run.side_effect = (
                    None if fail_at is None else [
                        *([subprocess.CompletedProcess([], 0)] * fail_at),
                        subprocess.CalledProcessError(1, ["azd"]),
                    ]
                )
                with self.subTest(fail_at=fail_at), patch.dict(
                    os.environ, deployment_environment(), clear=True
                ), redirect_stdout(output):
                    code = main(["--manifest", str(manifest), "--for-deploy"])
                if fail_at is None:
                    self.assertEqual(0, code)
                    self.assertEqual(DIGEST, json.loads(output.getvalue())["HOSTED_AGENT_IMAGE_VERSION"])
                else:
                    self.assertEqual(1, code)
                    self.assertEqual("", output.getvalue())


if __name__ == "__main__":
    unittest.main()
