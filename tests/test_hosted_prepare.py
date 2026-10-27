from __future__ import annotations

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from config.deployment.composition import hosted_startup_command_sha256
from config.deployment.hosted_prepare import (
    persist_digest,
    prepare_environment,
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
                AZURE_FOUNDRY_RESOURCE_GROUP="rg-foundry",
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


if __name__ == "__main__":
    unittest.main()
