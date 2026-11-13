"""Environment binding (T066, FR-015g): one application per azd environment."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from config.appdefinition import (
    APP_ID_ENV,
    BindingMismatchError,
    DefinitionNotFoundError,
    bind,
    check_binding,
    env_file_path,
    resolve_definition_path,
    resolve_env_name,
)
from config.appdefinition.__main__ import main as cli_main
from config.deployment.metadata import MetadataError

ROOT = Path(__file__).resolve().parents[1]


class BindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="agentlz-binding-")
        self.azure_dir = Path(self._tmp.name) / ".azure"
        self.env_file = env_file_path(self.azure_dir, "dev")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_first_bind_writes_app_id_and_preserves_other_values(self) -> None:
        self.env_file.parent.mkdir(parents=True)
        self.env_file.write_text('AZURE_ENV_NAME="dev"\nAZURE_LOCATION="eastus2"\n', encoding="utf-8")
        result = bind(self.env_file, "agent-lz-default")
        self.assertTrue(result.newly_bound)
        content = self.env_file.read_text(encoding="utf-8")
        self.assertIn(f'{APP_ID_ENV}="agent-lz-default"', content)
        self.assertIn('AZURE_LOCATION="eastus2"', content)

    def test_same_id_redeploy_is_allowed_and_idempotent(self) -> None:
        bind(self.env_file, "my-app")
        before = self.env_file.read_text(encoding="utf-8")
        result = bind(self.env_file, "my-app")
        self.assertFalse(result.newly_bound)
        self.assertEqual(before, self.env_file.read_text(encoding="utf-8"))
        self.assertEqual("my-app", check_binding(self.env_file, "my-app"))

    def test_changed_definition_fails_without_writing(self) -> None:
        bind(self.env_file, "my-app")
        before = self.env_file.read_text(encoding="utf-8")
        for operation in (bind, check_binding):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(BindingMismatchError) as raised:
                    operation(self.env_file, "other-app")
                self.assertIn("Create a new azd environment", str(raised.exception))
                self.assertIn("my-app", str(raised.exception))
                self.assertIn("other-app", str(raised.exception))
                self.assertEqual(before, self.env_file.read_text(encoding="utf-8"))

    def test_env_name_from_variable_or_azd_default(self) -> None:
        self.assertEqual("prod", resolve_env_name(self.azure_dir, {"AZURE_ENV_NAME": "prod"}))
        self.azure_dir.mkdir(parents=True)
        (self.azure_dir / "config.json").write_text(json.dumps({"version": 1, "defaultEnvironment": "dev"}), encoding="utf-8")
        self.assertEqual("dev", resolve_env_name(self.azure_dir, {}))

    def test_cli_bind_fails_before_any_azure_change(self) -> None:
        trio = str(ROOT / "app-definition.json")
        environment = {"AZURE_ENV_NAME": "dev", "AGENTLZ_APP_DEFINITION": ""}
        with patch.dict(os.environ, environment), patch("subprocess.run") as run, redirect_stderr(io.StringIO()):
            self.assertEqual(0, cli_main(["--validate", trio, "--bind", "--azure-dir", str(self.azure_dir)]))
            self.assertEqual("agent-lz-default", check_binding(self.env_file, "agent-lz-default"))
            self.env_file.write_text(f'{APP_ID_ENV}="someone-else"\n', encoding="utf-8")
            with self.assertLogs("config.appdefinition", level="ERROR") as logs:
                self.assertEqual(2, cli_main(["--validate", trio, "--bind", "--azure-dir", str(self.azure_dir)]))
                self.assertEqual(2, cli_main(["--validate", trio, "--check-binding", "--azure-dir", str(self.azure_dir)]))
            run.assert_not_called()
        self.assertTrue(all("Create a new azd environment" in line for line in logs.output))
        self.assertIn("someone-else", self.env_file.read_text(encoding="utf-8"))


class DefinitionSelectionTests(unittest.TestCase):
    def test_default_is_bundled_root_definition(self) -> None:
        self.assertEqual((ROOT / "app-definition.json").resolve(), resolve_definition_path({}, ROOT))

    def test_variable_selects_folder_or_file(self) -> None:
        folder = ROOT / "samples" / "custom-app" / "containerapp"
        expected = (folder / "app-definition.json").resolve()
        self.assertEqual(expected, resolve_definition_path({"AGENTLZ_APP_DEFINITION": str(folder)}, ROOT))
        self.assertEqual(expected, resolve_definition_path({"AGENTLZ_APP_DEFINITION": "samples/custom-app/containerapp/app-definition.json"}, ROOT))

    def test_missing_selection_fails_with_actionable_message(self) -> None:
        with self.assertRaises(DefinitionNotFoundError) as raised:
            resolve_definition_path({"AGENTLZ_APP_DEFINITION": "does/not/exist"}, ROOT)
        self.assertIn("AGENTLZ_APP_DEFINITION", str(raised.exception))
        self.assertIn("does/not/exist", str(raised.exception))


class DirectRoleEntryTests(unittest.TestCase):
    def test_metadata_rejection_prevents_role_assignments(self):
        for field in ("source.missing", "source.stale", "context.environmentName",
                      "resourceGroups", "resource.identity", "containerApps.identity"):
            with (
                self.subTest(field=field),
                patch("config.deployment.setup_settings.load_setup_environment",
                      side_effect=MetadataError(field + ": Restore selected metadata.")),
                patch("config.appdefinition.roles.assign_roles") as assign,
                self.assertLogs("config.appdefinition", "ERROR"),
            ):
                self.assertEqual(3, cli_main(["--assign-roles"]))
            assign.assert_not_called()

    def test_roles_use_verified_selection_not_caller_mode_or_destinations(self):
        verified = {
            "AGENTLZ_APP_ID": "agent-lz-default",
            "ORCHESTRATION_HOST": "container_apps",
            "APP_RUNTIME_CONFIGURATION_MODE": "none",
            "AZURE_RESOURCE_GROUP": "verified-group",
        }
        with (
            patch.dict(os.environ, {"ORCHESTRATION_HOST": "hosted", "AZURE_RESOURCE_GROUP": "foreign"}),
            patch("config.deployment.setup_settings.load_setup_environment", return_value=verified),
            patch("config.appdefinition.roles.assign_roles", return_value=[]) as assign,
        ):
            self.assertEqual(0, cli_main(["--assign-roles"]))
        self.assertEqual(assign.call_args.args[1], verified)
        self.assertFalse(assign.call_args.kwargs["hosted_orchestration"])

    def test_different_application_cannot_receive_selected_foundation_roles(self):
        with (
            patch("config.deployment.setup_settings.load_setup_environment",
                  return_value={"AGENTLZ_APP_ID": "another-application"}),
            patch("config.appdefinition.roles.assign_roles") as assign,
            self.assertLogs("config.appdefinition", "ERROR"),
        ):
            self.assertEqual(3, cli_main(["--assign-roles"]))
        assign.assert_not_called()


if __name__ == "__main__":
    unittest.main()
