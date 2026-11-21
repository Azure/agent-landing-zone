from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from azure.mgmt.cognitiveservices.models import MetricName, Usage

from util import prereqs


class OpenAiUsageTests(unittest.TestCase):
    def test_usage_lookup_preserves_sdk_quota_values_and_region(self) -> None:
        usage = Usage(
            name=MetricName(value="OpenAI.Standard.gpt-4"),
            current_value=12, limit=100, unit="Count",
        )
        with (
            patch("azure.mgmt.resource.ResourceManagementClient") as resource,
            patch("azure.mgmt.cognitiveservices.CognitiveServicesManagementClient") as cognitive,
        ):
            resource.return_value.providers.get.return_value.registration_state = "Registered"
            cognitive.return_value.usages.list.return_value = iter([usage])
            usages = prereqs.get_openai_usages("East US 2", MagicMock(), "subscription")
        resource.return_value.providers.register.assert_not_called()
        cognitive.return_value.usages.list.assert_called_once_with(location="EastUS2")
        self.assertEqual(usages, [usage])
        formatted = prereqs.format_usages_console(usages)
        self.assertIn("OpenAI.Standard.gpt-4", formatted)
        self.assertIn("12", formatted)
        self.assertIn("100", formatted)


class AzureCliResolutionTests(unittest.TestCase):
    def test_prerequisites_cli_source_is_ascii_console_safe(self) -> None:
        source = Path(prereqs.__file__).read_text(encoding="utf-8")

        self.assertTrue(source.isascii())

    @patch("util.prereqs.resolve_az_command")
    @patch("util.prereqs.subprocess.run")
    def test_subscription_lookup_uses_resolved_azure_cli(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_resolve.return_value = r"C:\path\to\az.cmd"
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="subscription-id\n",
            stderr="",
        )

        subscription_id = prereqs.get_default_subscription_id()

        self.assertEqual("subscription-id", subscription_id)
        self.assertEqual(
            r"C:\path\to\az.cmd",
            mock_run.call_args.args[0][0],
        )

    @patch("util.prereqs.resolve_az_command", return_value="az")
    @patch(
        "util.prereqs.subprocess.run",
        side_effect=FileNotFoundError("az not found"),
    )
    def test_missing_azure_cli_exits_without_traceback(
        self,
        _mock_run: MagicMock,
        _mock_resolve: MagicMock,
    ) -> None:
        with self.assertRaises(SystemExit) as raised:
            prereqs.get_default_subscription_id()

        self.assertEqual(1, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
