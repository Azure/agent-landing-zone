"""Workload RG selection, bootstrap, persisted safety and hook parity, offline."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from config.deployment import resource_groups as rg

ROOT = Path(__file__).resolve().parents[1]
SUBSCRIPTION = "11111111-1111-1111-1111-111111111111"
OTHER_SUBSCRIPTION = "22222222-2222-2222-2222-222222222222"


class BootstrapDependencyTests(unittest.TestCase):
    def test_resource_group_cli_bootstraps_without_validation_packages(self) -> None:
        script = (
            "import runpy, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "sys.argv = ['config.deployment.resource_groups', '--help']\n"
            "try:\n"
            "    runpy.run_module('config.deployment.resource_groups', run_name='__main__')\n"
            "except SystemExit as error:\n"
            "    if error.code != 0:\n"
            "        raise\n"
            "assert 'yaml' not in sys.modules\n"
            "assert 'jsonschema' not in sys.modules\n"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-c", script, str(ROOT)],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--bind-only", result.stdout)


class ScratchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = ROOT / f".resource-group-test-{uuid4().hex}"
        self.scratch.mkdir()
        self.addCleanup(shutil.rmtree, self.scratch)
        self.azure_dir = self.scratch / ".azure"
        self.env_file = self.azure_dir / "offline" / ".env"
        self.env_file.parent.mkdir(parents=True)
        self.env_file.write_text(
            'AZURE_ENV_NAME="offline"\nUNRELATED_SECRET="not-logged"\n',
            encoding="utf-8",
        )
        self.environment = {
            "AZURE_ENV_NAME": "offline",
            "AZURE_RESOURCE_GROUP": "rg-app",
            "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION,
            "AZURE_LOCATION": "eastus2",
        }

    def prepare(self, **options: bool) -> rg.ResourceGroupSelection:
        return rg.prepare_resource_groups(
            self.environment, self.azure_dir, "offline", **options
        )


class InitializationTests(ScratchTest):
    def setUp(self) -> None:
        super().setUp()
        self.stored = dict(self.environment)
        self.saved = {}

    def azd(self, directory, arguments):
        self.assertEqual(self.azure_dir, directory)
        if arguments[:2] == ["env", "get-values"]:
            return json.dumps(self.stored)
        self.assertEqual(["env", "set"], arguments[:2])
        self.saved[arguments[2]] = arguments[3]
        self.stored[arguments[2]] = arguments[3]
        return ""

    def test_native_cli_initializes_three_groups_and_creates_only_additional_groups(self) -> None:
        self.environment.pop("AZURE_RESOURCE_GROUP")
        self.stored.pop("AZURE_RESOURCE_GROUP")
        existing = set()
        created = []

        def azure(arguments):
            self.assertEqual("group", arguments[0])
            name = arguments[arguments.index("--name") + 1]
            if arguments[1] == "exists":
                return 0, str(name in existing).lower(), ""
            self.assertEqual(4, len(self.saved))
            self.assertEqual("create", arguments[1])
            existing.add(name)
            created.append(name)
            return 0, json.dumps({
                "name": name, "id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{name}",
                "location": "eastus2",
            }), ""

        with patch.dict(os.environ, self.environment, clear=True), \
                patch.object(rg, "_run_azd", side_effect=self.azd), \
                patch.object(rg, "_run_az", side_effect=azure), \
                patch("sys.stdout", io.StringIO()) as output:
            self.assertEqual(0, rg.main(["--azure-dir", str(self.azure_dir), "--env-name", "offline"]))
            self.assertEqual("rg-offline", json.loads(output.getvalue())["foundry"])
        self.assertEqual(["rg-offline-app", "rg-offline-network"], created)
        self.assertEqual("true", self.saved["CREATE_RESOURCE_GROUPS"])
        selection = rg.read_binding(self.azure_dir, "offline")
        self.assertEqual(
            ("rg-offline", "rg-offline-app", "rg-offline-network"), selection.unique_groups,
        )

    def test_explicit_equal_names_choose_one_or_two_groups(self) -> None:
        for application, network, count in (
            ("rg-app", "rg-app", 1), ("rg-services", "rg-app", 2),
        ):
            context = {
                **self.environment, "AZURE_APP_RESOURCE_GROUP": application,
                "AZURE_NETWORK_RESOURCE_GROUP": network, "CREATE_RESOURCE_GROUPS": "false",
            }
            with self.subTest(count=count), patch.object(rg, "_run_azd", side_effect=self.azd), \
                    patch.object(rg, "_run_az", return_value=(0, "false", "")):
                initialized = rg.initialize_defaults(context, self.azure_dir, "offline")
                self.assertEqual(count, len(rg.resolve_resource_groups(initialized).unique_groups))
                self.assertEqual("false", initialized["CREATE_RESOURCE_GROUPS"])

    def test_bound_single_group_does_not_acquire_new_destinations(self) -> None:
        self.prepare(bind_only=True)
        with patch.object(rg, "_run_azd", side_effect=self.azd):
            initialized = rg.initialize_defaults(self.environment, self.azure_dir, "offline")
        self.assertFalse(self.saved)
        self.assertEqual(("rg-app",), rg.resolve_resource_groups(initialized).unique_groups)

    def test_existing_unbound_deployment_does_not_acquire_defaults(self) -> None:
        self.stored["APP_CONFIG_ENDPOINT"] = "https://example.azconfig.io"
        with patch.object(rg, "_run_azd", side_effect=self.azd):
            initialized = rg.initialize_defaults(self.environment, self.azure_dir, "offline")
        self.assertFalse(self.saved)
        self.assertEqual(("rg-app",), rg.resolve_resource_groups(initialized).unique_groups)

    def test_invalid_or_denied_local_environment_never_writes_azure(self) -> None:
        for raw in ("[]", '{"AZURE_RESOURCE_GROUP": 42}', "{"):
            with self.subTest(raw=raw), patch.object(rg, "_run_azd", return_value=raw), \
                    patch.object(rg, "_run_az") as azure:
                with self.assertRaisesRegex(rg.ResourceGroupError, "invalid local"):
                    rg.initialize_defaults(self.environment, self.azure_dir, "offline")
                azure.assert_not_called()
        with patch.object(rg.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), \
                patch.object(rg, "_run_az") as azure:
            with self.assertRaisesRegex(rg.ResourceGroupError, "local resource-group defaults"):
                rg.initialize_defaults(self.environment, self.azure_dir, "offline")
            azure.assert_not_called()

    def test_long_root_names_produce_distinct_valid_stable_destinations(self) -> None:
        first = rg._default_destination("a" * 90, "network")
        second = rg._default_destination("a" * 89 + "b", "network")
        self.assertEqual(90, len(first))
        self.assertNotEqual(first, second)
        self.assertEqual(first.casefold(), rg._default_destination("A" * 90, "network").casefold())

    def test_inventory_preserves_unbound_existing_environment_before_local_writes(self) -> None:
        with patch.object(rg, "_run_azd", side_effect=self.azd), \
                patch.object(rg, "_run_az", side_effect=[
                    (0, "true", ""),
                    (0, '[{"tags": {"azd-env-name": "offline"}}]', ""),
                ]):
            initialized = rg.initialize_defaults(self.environment, self.azure_dir, "offline")
        self.assertFalse(self.saved)
        self.assertEqual(("rg-app",), rg.resolve_resource_groups(initialized).unique_groups)

    def test_local_save_failure_aborts_before_group_creation(self) -> None:
        self.stored.pop("AZURE_RESOURCE_GROUP")
        def azd(directory, arguments):
            if arguments[:2] == ["env", "set"] and arguments[2] == "AZURE_APP_RESOURCE_GROUP":
                raise rg.ResourceGroupError("Cannot save local defaults")
            return self.azd(directory, arguments)

        with patch.dict(os.environ, self.environment, clear=True), \
                patch.object(rg, "_run_azd", side_effect=azd), \
                patch.object(rg, "_run_az", return_value=(0, "false", "")) as azure, \
                self.assertLogs(rg.LOGGER, level="ERROR"):
            self.assertEqual(1, rg.main(["--azure-dir", str(self.azure_dir), "--env-name", "offline"]))
        self.assertEqual(["AZURE_RESOURCE_GROUP"], list(self.saved))
        self.assertTrue(all(call.args[0][:2] == ["group", "exists"] for call in azure.call_args_list))
        self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())

    def test_persisted_environment_mismatch_cannot_be_hidden_by_process_environment(self) -> None:
        self.stored["AZURE_ENV_NAME"] = "another"
        with patch.object(rg, "_run_azd", side_effect=self.azd), \
                patch.object(rg, "_run_az") as azure:
            with self.assertRaisesRegex(rg.ResourceGroupError, "different environment"):
                rg.initialize_defaults(self.environment, self.azure_dir, "offline")
        self.assertFalse(self.saved)
        azure.assert_not_called()


class ResolverTests(ScratchTest):
    def test_foundry_is_native_root_and_application_is_an_override(self) -> None:
        self.environment.update(
            AZURE_RESOURCE_GROUP="rg-ai",
            AZURE_APP_RESOURCE_GROUP="rg-app",
            AZURE_NETWORK_RESOURCE_GROUP="rg-net",
        )
        selected = rg.resolve_resource_groups(self.environment)
        self.assertEqual(("rg-ai", "rg-app", "rg-net"), selected.unique_groups)
        self.assertEqual("rg-ai", selected.foundry)
        self.assertEqual("rg-app", selected.application)
        self.assertEqual("rg-net", selected.network)

    def test_legacy_foundry_output_cannot_retarget_an_existing_split(self) -> None:
        self.environment["AZURE_FOUNDRY_RESOURCE_GROUP"] = "rg-ai"
        with patch.object(rg, "_run_az") as run:
            with self.assertRaisesRegex(rg.ResourceGroupError, "original release"):
                self.prepare()
            run.assert_not_called()
        self.environment["AZURE_FOUNDRY_RESOURCE_GROUP"] = "RG-APP"
        self.assertEqual("rg-app", rg.resource_group_for(self.environment, "foundry"))

    def test_v1_split_cannot_change_native_root_by_rewriting_variable_names(self) -> None:
        self.environment.update(
            AZURE_RESOURCE_GROUP="rg-ai", AZURE_APP_RESOURCE_GROUP="rg-app",
            AZURE_NETWORK_RESOURCE_GROUP="rg-net",
        )
        path = rg.binding_path(self.azure_dir, "offline")
        original = json.dumps({
            "version": 1, "environment": "offline", "subscription": SUBSCRIPTION,
            "application": "rg-app", "foundry": "rg-ai", "network": "rg-net",
        })
        path.write_text(original, encoding="utf-8")
        with patch.object(rg, "_run_az") as run:
            with self.assertRaisesRegex(rg.ResourceGroupError, "original release"):
                self.prepare(bind_only=True)
            run.assert_not_called()
        self.assertEqual(original, path.read_text(encoding="utf-8"))

    def test_new_binding_records_foundry_root_contract_version(self) -> None:
        self.prepare(bind_only=True)
        self.assertEqual(
            2, json.loads(rg.binding_path(self.azure_dir, "offline").read_text())["version"],
        )

    def test_default_blank_overrides_and_pure_helper(self) -> None:
        self.environment.update(
            AZURE_APP_RESOURCE_GROUP="  ", AZURE_NETWORK_RESOURCE_GROUP=""
        )
        before = dict(self.environment)
        with patch.object(rg, "_run_az", return_value=(0, "false", "")) as run:
            for area in ("application", "foundry", "network"):
                self.assertEqual("rg-app", rg.resource_group_for(self.environment, area))
            self.assertEqual(("rg-app",), rg.resolve_resource_groups(self.environment).unique_groups)
        run.assert_not_called()
        self.assertEqual(before, self.environment)

    def test_one_two_three_destinations_and_case_collisions(self) -> None:
        for foundry, network, expected in (
            ("RG-App", "rG-apP", ("rg-app",)),
            ("rg-ai", "RG-AI", ("rg-app", "rg-ai")),
            ("rg-ai", "rg-net", ("rg-app", "rg-ai", "rg-net")),
        ):
            with self.subTest(foundry=foundry, network=network):
                self.environment.update(
                    AZURE_APP_RESOURCE_GROUP=foundry,
                    AZURE_NETWORK_RESOURCE_GROUP=network,
                )
                self.assertEqual(expected, rg.resolve_resource_groups(self.environment).unique_groups)

    def test_invalid_names_area_and_subscription(self) -> None:
        for name in ("bad/name", "rg.", "rg with spaces", "a" * 91, "--bad;whoami"):
            with self.subTest(name=name):
                self.environment["AZURE_APP_RESOURCE_GROUP"] = name
                with self.assertRaisesRegex(rg.ResourceGroupError, "resource-group name"):
                    rg.resolve_resource_groups(self.environment)
        self.environment.pop("AZURE_APP_RESOURCE_GROUP")
        for subscription in ("", "subscription-name", "/subscriptions/" + SUBSCRIPTION):
            self.environment["AZURE_SUBSCRIPTION_ID"] = subscription
            with self.assertRaisesRegex(rg.ResourceGroupError, "SUBSCRIPTION_ID"):
                rg.resolve_resource_groups(self.environment)
        with self.assertRaisesRegex(rg.ResourceGroupError, "area"):
            rg.resource_group_for(self.environment, "unknown")

    def test_strict_create_boolean(self) -> None:
        self.assertFalse(rg.resolve_resource_groups(self.environment).create_resource_groups)
        for value in ("", " ", "1", "0", "t", "yes", "false;", "null"):
            with self.subTest(value=value):
                self.environment["CREATE_RESOURCE_GROUPS"] = value
                with patch.object(rg, "_run_az") as run:
                    with self.assertRaisesRegex(rg.ResourceGroupError, "must be 'true' or 'false'"):
                        self.prepare()
                    run.assert_not_called()
        for value, expected in ((" TRUE ", True), ("false", False), ("False", False)):
            self.environment["CREATE_RESOURCE_GROUPS"] = value
            self.assertEqual(expected, rg.resolve_resource_groups(self.environment).create_resource_groups)

    def test_byo_cross_subscription_settings_untouched(self) -> None:
        self.environment["EXISTING_VNET_RESOURCE_ID"] = (
            f"/subscriptions/{OTHER_SUBSCRIPTION}/resourceGroups/external/providers/"
            "Microsoft.Network/virtualNetworks/hub"
        )
        self.environment["AZURE_PE_RESOURCE_GROUP_NAME"] = "external-pe-rg"
        self.environment["DEPLOYMENT_TOPOLOGY"] = "hosted-with-panel"
        before = dict(self.environment)
        self.assertEqual(("rg-app",), rg.resolve_resource_groups(self.environment).unique_groups)
        self.assertEqual(before, self.environment)

    def test_configured_application_pe_local_errors_precede_all_azure_and_binding(self) -> None:
        for name, prefix in (
            ("app-pe", ""), ("", "192.168.3.0/27"),
            ("bad/name", "192.168.3.0/27"), ("app-pe", "192.168.3.1/27"),
            ("app-pe", "192.168.3.0/30"), ("app-pe", "2001:db8::/64"),
            ("app-pe", "not-a-cidr"), ("app-pe", "192.168.3.0"),
        ):
            with self.subTest(name=name, prefix=prefix):
                self.environment.update(
                    AZURE_APPLICATION_PE_SUBNET_NAME=name,
                    AZURE_APPLICATION_PE_SUBNET_PREFIX=prefix,
                    AZURE_APP_RESOURCE_GROUP="rg-ai",
                    CREATE_RESOURCE_GROUPS="true",
                )
                with patch.object(rg, "_run_az") as run:
                    with self.assertRaisesRegex(rg.ResourceGroupError, "AZURE_APPLICATION_PE_SUBNET"):
                        self.prepare()
                    run.assert_not_called()
                self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())
        for name, prefix in (("", ""), ("app-pe", "192.168.4.0/27"),
                             ("a", "192.168.4.0/29")):
            rg.validate_application_pe_subnet({
                "AZURE_APPLICATION_PE_SUBNET_NAME": name,
                "AZURE_APPLICATION_PE_SUBNET_PREFIX": prefix,
            })

    def test_isolated_application_pe_overrides_resolve_each_omitted_default(self) -> None:
        for overrides in (
            {},
            {"AZURE_APPLICATION_PE_SUBNET_NAME": "tenant-app-pe"},
            {"AZURE_APPLICATION_PE_SUBNET_PREFIX": "10.30.3.128/26"},
        ):
            with self.subTest(overrides=overrides):
                rg.validate_application_pe_subnet({
                    "NETWORK_ISOLATION": "true", **overrides,
                })

    def test_isolated_application_pe_explicit_empty_is_not_shared_subnet_reuse(self) -> None:
        for create in ("true", "false"):
            with self.subTest(create=create):
                with self.assertRaisesRegex(rg.ResourceGroupError, "AZURE_APPLICATION_PE_SUBNET"):
                    rg.validate_application_pe_subnet({
                        "NETWORK_ISOLATION": "true",
                        "DEPLOY_APPLICATION_PE_SUBNET": create,
                        "AZURE_APPLICATION_PE_SUBNET_NAME": "",
                        "AZURE_APPLICATION_PE_SUBNET_PREFIX": "",
                    })

    def test_unselected_root_default_pending_but_explicit_extra_fails(self) -> None:
        self.environment.pop("AZURE_RESOURCE_GROUP")
        self.environment.pop("AZURE_SUBSCRIPTION_ID")
        with patch.object(rg, "_run_az") as run:
            self.assertIsNone(self.prepare().application)
            run.assert_not_called()
        self.assertIsNone(rg.read_binding(self.azure_dir, "offline").application)
        self.environment["AZURE_APP_RESOURCE_GROUP"] = "rg-ai"
        with patch.object(rg, "_run_az") as run:
            with self.assertRaisesRegex(rg.ResourceGroupError, "No root name is inferred"):
                self.prepare()
            run.assert_not_called()
        with self.assertRaisesRegex(rg.ResourceGroupError, "AZURE_RESOURCE_GROUP"):
            rg.resource_group_for({}, "foundry")


class BootstrapTests(ScratchTest):
    def test_existing_groups_reused_without_metadata_writes_and_idempotent_binding(self) -> None:
        self.environment.update(
            AZURE_APP_RESOURCE_GROUP="rg-ai", AZURE_NETWORK_RESOURCE_GROUP="RG-AI",
            CREATE_RESOURCE_GROUPS="true",
        )
        before_env = self.env_file.read_bytes()
        def azure(arguments: list[str]) -> tuple[int, str, str]:
            if arguments[:2] == ["resource", "list"]:
                self.assertNotIn("--tag", arguments)
                self.assertEqual(
                    "rg-app", arguments[arguments.index("--resource-group") + 1]
                )
                self.assertEqual(
                    SUBSCRIPTION, arguments[arguments.index("--subscription") + 1]
                )
                return 0, "[]", ""
            self.assertEqual(["group", "exists"], arguments[:2])
            return 0, "true", ""
        with patch.object(rg, "_run_az", side_effect=azure) as run:
            self.prepare()
            self.assertEqual(3, run.call_count)
            state = rg.binding_path(self.azure_dir, "offline")
            before = state.read_bytes()
            before_time = state.stat().st_mtime_ns
            self.prepare()
            self.environment["AZURE_RESOURCE_GROUP"] = "RG-APP"
            self.environment["AZURE_SUBSCRIPTION_ID"] = SUBSCRIPTION.upper()
            self.prepare()
            self.assertEqual(before, state.read_bytes())
            self.assertEqual(before_time, state.stat().st_mtime_ns)
        self.assertEqual(before_env, self.env_file.read_bytes())

    def test_legacy_inventory_filters_tags_without_widening_resource_scope(self) -> None:
        selection = rg.resolve_resource_groups(self.environment)
        for resources, expected in (
            ([], False),
            ([{"tags": None}], False),
            ([{"id": "untagged-resource"}], False),
            ([{"tags": {"azd-env-name": "another-environment"}}], False),
            ([{"tags": {"azd-env-name": "OFFLINE"}}], False),
            ([{"tags": {"azd-env-name": "offline"}}], True),
            ([{"tags": {"AZD-ENV-NAME": "offline"}}], True),
        ):
            with self.subTest(resources=resources), patch.object(
                rg, "_run_az", return_value=(0, json.dumps(resources), "")
            ) as run:
                self.assertEqual(
                    expected,
                    rg._legacy_deployed(
                        self.environment, self.env_file, selection, "offline",
                        check_inventory=True,
                    ),
                )
                run.assert_called_once_with([
                    "resource", "list", "--resource-group", "rg-app",
                    "--subscription", SUBSCRIPTION,
                    "--output", "json", "--only-show-errors",
                ])

    def test_legacy_inventory_malformed_or_inaccessible_fails_closed(self) -> None:
        selection = rg.resolve_resource_groups(self.environment)
        for response in (
            (0, "not-json", ""),
            (0, "{}", ""),
            (0, "[null]", ""),
            (0, '[{"tags": []}]', ""),
            (0, '[{"tags": "invalid"}]', ""),
            (0, '[{"tags": {"azd-env-name": 42}}]', ""),
            (1, "", "ERROR: (AuthorizationFailed) forbidden"),
        ):
            with self.subTest(response=response), patch.object(
                rg, "_run_az", return_value=response
            ) as run:
                with self.assertRaises(rg.ResourceGroupError):
                    rg._legacy_deployed(
                        self.environment, self.env_file, selection, "offline",
                        check_inventory=True,
                    )
                self.assertEqual(1, run.call_count)
                self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())

    def test_tagged_legacy_resources_still_reject_split_adoption_before_writes(self) -> None:
        self.environment["AZURE_APP_RESOURCE_GROUP"] = "rg-ai"

        def azure(arguments: list[str]) -> tuple[int, str, str]:
            if arguments[:2] == ["resource", "list"]:
                return 0, '[{"tags": {"azd-env-name": "offline"}}]', ""
            self.assertEqual(["group", "exists"], arguments[:2])
            return 0, "true", ""

        with patch.object(rg, "_run_az", side_effect=azure):
            with self.assertRaisesRegex(
                rg.ResourceGroupError, "existing deployment without a resource-group binding"
            ):
                self.prepare()
        self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())

    def test_missing_false_checks_all_destinations_without_any_writes(self) -> None:
        self.environment.update(
            AZURE_APP_RESOURCE_GROUP="rg-ai", AZURE_NETWORK_RESOURCE_GROUP="rg-net"
        )
        with patch.object(rg, "_run_az", return_value=(0, "false", "")) as run:
            with self.assertRaisesRegex(rg.ResourceGroupError, "rg-ai, rg-net"):
                self.prepare()
        self.assertEqual(3, run.call_count)
        self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())
        self.assertTrue(all(call.args[0][:2] == ["group", "exists"] for call in run.call_args_list))

    def test_no_authorization_transient_or_invalid_results_are_absence(self) -> None:
        self.environment.update(AZURE_APP_RESOURCE_GROUP="rg-ai", CREATE_RESOURCE_GROUPS="true")
        for response in (
            (1, "", "(AuthorizationFailed) secret-token"),
            (1, "", "(TooManyRequests) details"),
            (0, "not-a-bool", ""),
            (0, "", ""),
        ):
            with self.subTest(response=response):
                with patch.object(rg, "_run_az", side_effect=[(0, "false", ""), response]) as run:
                    with self.assertRaisesRegex(rg.ResourceGroupError, "Authorization errors are not absence") as raised:
                        self.prepare()
                    self.assertNotIn("secret-token", str(raised.exception))
                    self.assertFalse(any(c.args[0][1] == "create" for c in run.call_args_list))
                self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())

    def test_create_missing_additional_only_after_all_reads_binding_and_race_check(self) -> None:
        self.environment.update(
            AZURE_APP_RESOURCE_GROUP="rg-ai", AZURE_NETWORK_RESOURCE_GROUP="rg-net",
            CREATE_RESOURCE_GROUPS="true",
        )
        calls: list[tuple[str, str]] = []
        def azure(arguments: list[str]) -> tuple[int, str, str]:
            name = arguments[arguments.index("--name") + 1]
            calls.append((arguments[1], name))
            if arguments[1] == "exists":
                return 0, "false", ""
            self.assertTrue(rg.binding_path(self.azure_dir, "offline").is_file())
            self.assertNotIn("--tags", arguments)
            self.assertEqual("eastus2", arguments[arguments.index("--location") + 1])
            return 0, json.dumps({"id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{name}"}), ""
        with patch.object(rg, "_run_az", side_effect=azure):
            self.prepare()
        self.assertEqual(
            [("exists", "rg-app"), ("exists", "rg-ai"), ("exists", "rg-net"),
             ("exists", "rg-ai"), ("create", "rg-ai"),
             ("exists", "rg-net"), ("create", "rg-net")],
            calls,
        )

    def test_partial_failure_retains_binding_and_retry_converges_without_rollback(self) -> None:
        self.environment.update(
            AZURE_APP_RESOURCE_GROUP="rg-ai", AZURE_NETWORK_RESOURCE_GROUP="rg-net",
            CREATE_RESOURCE_GROUPS="true",
        )
        created: set[str] = set()
        fail = True
        def azure(arguments: list[str]) -> tuple[int, str, str]:
            name = arguments[arguments.index("--name") + 1]
            if arguments[1] == "exists":
                return 0, str(name in created).lower(), ""
            self.assertEqual("create", arguments[1])
            if name == "rg-net" and fail:
                return 1, "", "(AuthorizationFailed) confidential-request"
            created.add(name)
            return 0, json.dumps({"id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{name}"}), ""
        with patch.object(rg, "_run_az", side_effect=azure):
            with self.assertRaisesRegex(rg.ResourceGroupError, "created in this attempt: rg-ai") as raised:
                self.prepare()
            self.assertNotIn("confidential-request", str(raised.exception))
            self.assertTrue(rg.binding_path(self.azure_dir, "offline").is_file())
            fail = False
            self.prepare()
        self.assertEqual({"rg-ai", "rg-net"}, created)

    def test_creation_race_reuses_existing_without_put(self) -> None:
        self.environment.update(AZURE_APP_RESOURCE_GROUP="rg-ai", CREATE_RESOURCE_GROUPS="true")
        with patch.object(rg, "_run_az", side_effect=[
            (0, "false", ""), (0, "false", ""), (0, "true", ""),
        ]) as run:
            self.prepare()
        self.assertEqual(3, run.call_count)
        self.assertTrue(all(c.args[0][1] == "exists" for c in run.call_args_list))

    def test_known_create_conflict_rereads_and_reuses_exact_destination(self) -> None:
        self.environment.update(AZURE_APP_RESOURCE_GROUP="rg-ai", CREATE_RESOURCE_GROUPS="true")
        existing = {
            "id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/RG-AI",
            "location": "westus",
            "tags": {"external-owner": "unchanged"},
        }
        for conflict in ("InvalidResourceGroupLocation", "ResourceGroupAlreadyExists"):
            with self.subTest(conflict=conflict):
                with patch.object(rg, "_run_az", side_effect=[
                    (0, "false", ""), (0, "false", ""), (0, "false", ""),
                    (1, "", f"({conflict}) concurrent creator details"),
                    (0, json.dumps(existing), ""),
                ]) as run:
                    self.prepare()
                operations = [call.args[0][:2] for call in run.call_args_list]
                self.assertEqual(
                    [["group", "exists"]] * 3 + [["group", "create"], ["group", "show"]],
                    operations,
                )
                read = run.call_args_list[-1].args[0]
                self.assertEqual(SUBSCRIPTION, read[read.index("--subscription") + 1])
                self.assertEqual("rg-ai", read[read.index("--name") + 1])
                self.assertEqual("westus", existing["location"])
                self.assertEqual({"external-owner": "unchanged"}, existing["tags"])

    def test_conflict_reread_failure_or_wrong_identity_fails_closed(self) -> None:
        self.environment.update(AZURE_APP_RESOURCE_GROUP="rg-ai", CREATE_RESOURCE_GROUPS="true")
        for response in (
            (1, "", "(AuthorizationFailed) secret-details"),
            (1, "", "(ResourceGroupNotFound) secret-details"),
            (0, "not-json", ""),
            (0, "[]", ""),
            (0, json.dumps({"id": f"/subscriptions/{OTHER_SUBSCRIPTION}/resourceGroups/rg-ai"}), ""),
            (0, json.dumps({"id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/other"}), ""),
        ):
            with self.subTest(response=response):
                with patch.object(rg, "_run_az", side_effect=[
                    (0, "false", ""), (0, "false", ""), (0, "false", ""),
                    (1, "", "(InvalidResourceGroupLocation) concurrent creation"),
                    response,
                ]) as run:
                    with self.assertRaises(rg.ResourceGroupError) as raised:
                        self.prepare()
                self.assertIn("binding is retained", str(raised.exception))
                self.assertNotIn("secret-details", str(raised.exception))
                self.assertEqual(["group", "show"], run.call_args_list[-1].args[0][:2])
                self.assertTrue(rg.binding_path(self.azure_dir, "offline").is_file())

    def test_create_authorization_and_unknown_errors_never_trigger_conflict_recovery(self) -> None:
        self.environment.update(AZURE_APP_RESOURCE_GROUP="rg-ai", CREATE_RESOURCE_GROUPS="true")
        for error in ("AuthorizationFailed", "RequestDisallowedByPolicy", "TooManyRequests", "Conflict"):
            with self.subTest(error=error):
                with patch.object(rg, "_run_az", side_effect=[
                    (0, "false", ""), (0, "false", ""), (0, "false", ""),
                    (1, "", f"({error}) secret-details"),
                ]) as run:
                    with self.assertRaisesRegex(rg.ResourceGroupError, "no privilege elevation"):
                        self.prepare()
                self.assertEqual(4, run.call_count)

    def test_wrong_created_subscription_or_malformed_result_fails_retaining_binding(self) -> None:
        self.environment.update(AZURE_APP_RESOURCE_GROUP="rg-ai", CREATE_RESOURCE_GROUPS="true")
        for result in ("garbage", "[]", json.dumps({
            "id": f"/subscriptions/{OTHER_SUBSCRIPTION}/resourceGroups/rg-ai"
        })):
            with self.subTest(result=result):
                with patch.object(rg, "_run_az", side_effect=[
                    (0, "false", ""), (0, "false", ""), (0, "false", ""), (0, result, ""),
                ]):
                    with self.assertRaisesRegex(rg.ResourceGroupError, "exact created destination"):
                        self.prepare()
                self.assertTrue(rg.binding_path(self.azure_dir, "offline").is_file())

    def test_missing_create_location_fails_before_binding_or_write(self) -> None:
        self.environment.update(AZURE_APP_RESOURCE_GROUP="rg-ai", CREATE_RESOURCE_GROUPS="true")
        self.environment.pop("AZURE_LOCATION")
        with patch.object(rg, "_run_az", return_value=(0, "false", "")):
            with self.assertRaisesRegex(rg.ResourceGroupError, "AZURE_LOCATION"):
                self.prepare()
        self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())

    def test_existing_old_environment_cannot_adopt_overrides(self) -> None:
        self.environment["AZURE_APP_RESOURCE_GROUP"] = "rg-ai"
        self.environment["APP_CONFIG_ENDPOINT"] = "https://existing.example.test"
        with patch.object(rg, "_run_az") as run:
            with self.assertRaisesRegex(rg.ResourceGroupError, "no implicit migration"):
                self.prepare()
            run.assert_not_called()
        self.environment.pop("APP_CONFIG_ENDPOINT")
        with patch.object(rg, "_run_az", side_effect=[
            (0, "true", ""), (0, "true", ""),
            (0, '[{"id":"previous-resource","tags":{"azd-env-name":"offline"}}]', ""),
        ]):
            with self.assertRaisesRegex(rg.ResourceGroupError, "existing deployment"):
                self.prepare()
        self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())

    def test_local_legacy_state_blocks_unbound_split_even_when_new_root_is_absent(self) -> None:
        self.environment.update(
            AZURE_RESOURCE_GROUP="new-root", AZURE_APP_RESOURCE_GROUP="new-foundry",
            CREATE_RESOURCE_GROUPS="true",
        )
        for state in (
            {"infra": {"parameters": {"root": "previous-root"}}},
            {"provisioning": {"deployment": "previous-deployment"}},
        ):
            with self.subTest(state=state):
                (self.env_file.parent / "config.json").write_text(json.dumps(state), encoding="utf-8")
                with patch.object(rg, "_run_az", return_value=(0, "false", "")) as run:
                    with self.assertRaisesRegex(rg.ResourceGroupError, "no implicit migration"):
                        self.prepare()
                    run.assert_not_called()
                self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())


class PersistenceTests(ScratchTest):
    def test_unbound_legacy_same_group_cannot_retarget_root_or_subscription(self) -> None:
        application_vault = (
            f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-app/providers/"
            "Microsoft.KeyVault/vaults/vault"
        )
        for explicit_same_group in (False, True):
            for changed_key, changed_value in (
                ("AZURE_RESOURCE_GROUP", "new-root"),
                ("AZURE_SUBSCRIPTION_ID", OTHER_SUBSCRIPTION),
            ):
                with self.subTest(explicit=explicit_same_group, changed=changed_key):
                    environment = dict(self.environment, KEY_VAULT_RESOURCE_ID=application_vault)
                    environment[changed_key] = changed_value
                    if explicit_same_group:
                        environment["AZURE_APP_RESOURCE_GROUP"] = environment["AZURE_RESOURCE_GROUP"]
                        environment["AZURE_NETWORK_RESOURCE_GROUP"] = environment["AZURE_RESOURCE_GROUP"]
                    with patch.object(rg, "_run_az") as run:
                        with self.assertRaisesRegex(rg.ResourceGroupError, "persisted deployment scope"):
                            rg.prepare_resource_groups(environment, self.azure_dir, "offline")
                        run.assert_not_called()
                    self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())

    def test_persisted_legacy_id_cannot_be_hidden_by_process_environment(self) -> None:
        original_env = self.env_file.read_text(encoding="utf-8")
        for key, path in (
            ("KEY_VAULT_RESOURCE_ID", "Microsoft.KeyVault/vaults/vault"),
        ):
            with self.subTest(key=key):
                self.env_file.write_text(
                    original_env + f'{key}="/subscriptions/{SUBSCRIPTION}/resourceGroups/'
                    f'rg-app/providers/{path}"\n', encoding="utf-8",
                )
                self.environment["AZURE_RESOURCE_GROUP"] = "new-root"
                self.environment[key] = (
                    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/new-root/providers/{path}"
                )
                for mode in ({}, {"bind_only": True}, {"check_only": True}):
                    with self.subTest(mode=mode), patch.object(rg, "_run_az", return_value=(0, "false", "")) as run:
                        with self.assertRaisesRegex(rg.ResourceGroupError, "persisted deployment scope"):
                            self.prepare(**mode)
                        run.assert_not_called()
                    self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())
                self.environment.pop(key)

    def test_unchanged_legacy_default_adopts_without_guessing_from_byo_ids(self) -> None:
        self.environment.update(
            AZURE_RESOURCE_GROUP="RG-APP",
            AZURE_AI_PROJECT_RESOURCE_ID=(
                f"/subscriptions/{OTHER_SUBSCRIPTION}/resourceGroups/external-foundry/providers/"
                "Microsoft.CognitiveServices/accounts/account/projects/project"
            ),
            KEY_VAULT_RESOURCE_ID=(
                f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-app/providers/"
                "Microsoft.KeyVault/vaults/vault"
            ),
            AZURE_CONTAINER_REGISTRY_RESOURCE_ID=(
                f"/subscriptions/{OTHER_SUBSCRIPTION}/resourceGroups/external/providers/"
                "Microsoft.ContainerRegistry/registries/shared"
            ),
            LOG_ANALYTICS_RESOURCE_ID=(
                f"/subscriptions/{OTHER_SUBSCRIPTION}/resourceGroups/external/providers/"
                "Microsoft.OperationalInsights/workspaces/shared"
            ),
        )
        self.env_file.write_text(
            self.env_file.read_text(encoding="utf-8")
            + f'AZURE_AI_PROJECT_RESOURCE_ID="{self.environment["AZURE_AI_PROJECT_RESOURCE_ID"]}"\n',
            encoding="utf-8",
        )
        with patch.object(rg, "_run_az", return_value=(0, "true", "")) as run:
            self.prepare()
            self.prepare(check_only=True)
        self.assertEqual(1, run.call_count)
        self.assertEqual("RG-APP", rg.read_binding(self.azure_dir, "offline").application)

    def test_native_env_with_owned_application_proof_rejects_retarget_not_unchanged_default(self) -> None:
        self.env_file.write_text(
            self.env_file.read_text(encoding="utf-8")
            + f'AZURE_RESOURCE_GROUP="rg-app"\nAZURE_SUBSCRIPTION_ID="{SUBSCRIPTION}"\n'
            + f'KEY_VAULT_RESOURCE_ID="/subscriptions/{SUBSCRIPTION}/resourceGroups/'
            'rg-app/providers/Microsoft.KeyVault/vaults/vault"\n', encoding="utf-8",
        )
        self.environment["AZURE_RESOURCE_GROUP"] = "new-root"
        with patch.object(rg, "_run_az", return_value=(0, "false", "")) as run:
            with self.assertRaisesRegex(rg.ResourceGroupError, "persisted deployment scope"):
                self.prepare()
            run.assert_not_called()
        self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())
        self.environment["AZURE_RESOURCE_GROUP"] = "rg-app"
        with patch.object(rg, "_run_az", return_value=(0, "true", "")):
            self.prepare()
        self.assertEqual("rg-app", rg.read_binding(self.azure_dir, "offline").application)

    def test_pending_binding_cannot_freeze_root_conflicting_with_persisted_proof(self) -> None:
        original = dict(self.environment)
        original_env_file = self.env_file.read_text(encoding="utf-8")
        self.environment.pop("AZURE_RESOURCE_GROUP")
        with patch.object(rg, "_run_az") as run:
            self.prepare()
            run.assert_not_called()
        pending = rg.binding_path(self.azure_dir, "offline").read_bytes()
        self.environment = original
        self.environment["AZURE_RESOURCE_GROUP"] = "new-root"
        application_vault = (
            f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-app/providers/"
            "Microsoft.KeyVault/vaults/vault"
        )
        for proof in ("persisted-application-id", "process-application-id"):
            with self.subTest(proof=proof):
                self.env_file.write_text(
                    original_env_file + 'AZURE_RESOURCE_GROUP="rg-app"\n'
                    + (f'KEY_VAULT_RESOURCE_ID="{application_vault}"\n'
                       if proof == "persisted-application-id" else ""),
                    encoding="utf-8",
                )
                self.environment.pop("KEY_VAULT_RESOURCE_ID", None)
                if proof == "process-application-id":
                    self.environment["KEY_VAULT_RESOURCE_ID"] = application_vault
                for mode in ({}, {"bind_only": True}, {"check_only": True}):
                    with self.subTest(mode=mode), patch.object(rg, "_run_az", return_value=(0, "false", "")) as run:
                        with self.assertRaisesRegex(rg.ResourceGroupError, "persisted deployment scope"):
                            self.prepare(**mode)
                        run.assert_not_called()
                    self.assertEqual(pending, rg.binding_path(self.azure_dir, "offline").read_bytes())
        self.environment["AZURE_RESOURCE_GROUP"] = "RG-APP"
        with patch.object(rg, "_run_az") as run:
            self.prepare(bind_only=True)
            run.assert_not_called()
        self.assertEqual("RG-APP", rg.read_binding(self.azure_dir, "offline").application)

    def test_pending_first_selection_not_blocked_by_unrelated_infra_state(self) -> None:
        original = dict(self.environment)
        self.environment.pop("AZURE_RESOURCE_GROUP")
        with patch.object(rg, "_run_az") as run:
            self.prepare()
            (self.env_file.parent / "config.json").write_text(json.dumps({
                "infra": {"parameters": {"location": "eastus2", "vnetAddressPrefixes": ["192.168.0.0/21"]}}
            }), encoding="utf-8")
            self.environment = original
            self.prepare(bind_only=True)
            run.assert_not_called()
        self.assertEqual("rg-app", rg.read_binding(self.azure_dir, "offline").application)

    def test_retarget_subscription_root_or_removed_overrides_fails_before_azure(self) -> None:
        self.environment["AZURE_APP_RESOURCE_GROUP"] = "rg-ai"
        with patch.object(rg, "_run_az", side_effect=[
            (0, "true", ""), (0, "true", ""), (0, "[]", ""),
        ]):
            self.prepare()
        before = rg.binding_path(self.azure_dir, "offline").read_bytes()
        for key, value in (
            ("AZURE_SUBSCRIPTION_ID", OTHER_SUBSCRIPTION),
            ("AZURE_RESOURCE_GROUP", "new-root"),
            ("AZURE_APP_RESOURCE_GROUP", ""),
            ("AZURE_NETWORK_RESOURCE_GROUP", "rg-net"),
        ):
            with self.subTest(key=key):
                environment = dict(self.environment)
                environment[key] = value
                with patch.object(rg, "_run_az") as run:
                    with self.assertRaisesRegex(rg.ResourceGroupError, "conflicts"):
                        rg.prepare_resource_groups(environment, self.azure_dir, "offline")
                    run.assert_not_called()
                self.assertEqual(before, rg.binding_path(self.azure_dir, "offline").read_bytes())

    def test_pending_native_root_finalizes_once_without_azure_calls(self) -> None:
        environment = dict(self.environment)
        self.environment.pop("AZURE_RESOURCE_GROUP")
        self.environment.pop("AZURE_SUBSCRIPTION_ID")
        with patch.object(rg, "_run_az") as run:
            self.prepare()
            self.environment = environment
            self.prepare(bind_only=True)
            self.assertEqual("rg-app", rg.read_binding(self.azure_dir, "offline").application)
            self.prepare(check_only=True)
            run.assert_not_called()
        self.environment["AZURE_RESOURCE_GROUP"] = "moved"
        with self.assertRaisesRegex(rg.ResourceGroupError, "conflicts"):
            self.prepare(bind_only=True)

    def test_corrupted_binding_fails_closed(self) -> None:
        rg.binding_path(self.azure_dir, "offline").write_text("{}", encoding="utf-8")
        with patch.object(rg, "_run_az") as run:
            with self.assertRaisesRegex(rg.ResourceGroupError, "invalid or unreadable"):
                self.prepare()
            run.assert_not_called()

    def test_environment_path_traversal_rejected(self) -> None:
        for name in ("../other", "..\\other", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                rg.binding_path(self.azure_dir, name)

    def test_mismatched_selected_environment_fails_before_azure_or_state(self) -> None:
        self.environment["AZURE_ENV_NAME"] = "another-environment"
        with patch.object(rg, "_run_az") as run:
            with self.assertRaisesRegex(rg.ResourceGroupError, "does not match"):
                self.prepare()
            run.assert_not_called()
        self.assertFalse(rg.binding_path(self.azure_dir, "offline").exists())

    def test_cli_describe_check_bind_only_never_call_azure_or_log_secrets(self) -> None:
        for flag in ("--bind-only", "--check", "--describe"):
            with self.subTest(flag=flag):
                output = io.StringIO()
                with patch.dict(os.environ, self.environment, clear=True), \
                        patch.object(rg, "_run_az") as run, \
                        patch.object(rg, "_run_azd") as native, \
                        patch("sys.stdout", output):
                    self.assertEqual(0, rg.main([
                        "--azure-dir", str(self.azure_dir), "--env-name", "offline", flag
                    ]))
                    run.assert_not_called()
                    native.assert_not_called()
                self.assertEqual("rg-app", json.loads(output.getvalue())["application"])
                self.assertNotIn("not-logged", output.getvalue())
        self.assertNotIn("DEPLOYMENT_TOPOLOGY", rg.binding_path(self.azure_dir, "offline").read_text())


class HookTests(ScratchTest):
    @unittest.skipUnless(os.name == "nt" and shutil.which("azd") and shutil.which("pwsh"),
                         "Instrumented azd test requires Windows azd and PowerShell")
    def test_actual_azd_initializes_and_reloads_three_destinations_before_provider(self) -> None:
        (self.azure_dir / "config.json").write_text(
            json.dumps({"version": 1, "defaultEnvironment": "offline"}), encoding="utf-8"
        )
        self.env_file.write_text(
            f'AZURE_ENV_NAME="offline"\nAZURE_LOCATION="eastus2"\n'
            f'AZURE_SUBSCRIPTION_ID="{SUBSCRIPTION}"\n', encoding="utf-8",
        )
        (self.scratch / "azure.yaml").write_text(
            "name: rg-hook-ordering\nhooks:\n  preprovision:\n"
            "    - windows:\n        shell: pwsh\n        run: ./select.ps1\n"
            "        interactive: false\n"
            "    - windows:\n        shell: pwsh\n        run: ./abort.ps1\n"
            "        interactive: false\n", encoding="utf-8",
        )
        (self.scratch / "select.ps1").write_text(
            "Set-Content -LiteralPath (Join-Path $PSScriptRoot 'root-present') "
            "-Value ([bool]$env:AZURE_RESOURCE_GROUP)\n"
            "& $env:RG_TEST_PYTHON (Join-Path $PSScriptRoot 'defaults.py')\n"
            "exit $LASTEXITCODE\n", encoding="utf-8",
        )
        (self.scratch / "defaults.py").write_text(
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "from unittest.mock import patch\n"
            "sys.path.insert(0, os.environ['RG_TEST_SOURCE'])\n"
            "from config.deployment import resource_groups as rg\n"
            "created = []\n"
            "def azure(args):\n"
            "    assert args[0] == 'group'\n"
            "    if args[1] == 'exists':\n"
            "        return 0, 'false', ''\n"
            "    assert args[1] == 'create'\n"
            "    name = args[args.index('--name') + 1]\n"
            "    assert name in ('rg-offline-app', 'rg-offline-network')\n"
            "    created.append(name)\n"
            "    subscription = args[args.index('--subscription') + 1]\n"
            "    return 0, json.dumps({'id': '/subscriptions/' + subscription "
            "+ '/resourceGroups/' + name}), ''\n"
            "with patch.object(rg, '_run_az', side_effect=azure):\n"
            "    code = rg.main(['--env-name', 'offline'])\n"
            "Path('created-groups.json').write_text(json.dumps(created))\n"
            "raise SystemExit(code)\n", encoding="utf-8",
        )
        (self.scratch / "abort.ps1").write_text(
            "Write-Host ('DEFAULTS_RELOADED=' + ("
            "$env:AZURE_RESOURCE_GROUP -eq 'rg-offline' -and "
            "$env:AZURE_APP_RESOURCE_GROUP -eq 'rg-offline-app' -and "
            "$env:AZURE_NETWORK_RESOURCE_GROUP -eq 'rg-offline-network' -and "
            "$env:CREATE_RESOURCE_GROUPS -eq 'true'))\n"
            "exit 47\n", encoding="utf-8",
        )
        environment = dict(
            os.environ, AZURE_DEV_COLLECT_TELEMETRY="no",
            RG_TEST_PYTHON=sys.executable, RG_TEST_SOURCE=str(ROOT),
        )
        for key in ("AZURE_RESOURCE_GROUP", "AZURE_ENV_NAME", "AZURE_SUBSCRIPTION_ID",
                    "AZURE_APP_RESOURCE_GROUP", "AZURE_NETWORK_RESOURCE_GROUP"):
            environment.pop(key, None)
        result = subprocess.run(
            [shutil.which("azd"), "provision", "--no-prompt"],
            cwd=self.scratch, env=environment, capture_output=True, text=True, timeout=60,
        )
        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertEqual("False", (self.scratch / "root-present").read_text().strip())
        self.assertIn("DEFAULTS_RELOADED=True", output)
        self.assertEqual(
            ["rg-offline-app", "rg-offline-network"],
            json.loads((self.scratch / "created-groups.json").read_text()),
        )
        self.assertIn("exit code: '47'", output)
        self.assertNotIn("Initialize bicep provider", output)

    def test_both_hooks_bootstrap_after_app_binding_before_composition(self) -> None:
        for suffix in ("ps1", "sh"):
            script = (ROOT / "scripts" / f"preProvision.{suffix}").read_text(encoding="utf-8")
            validate = script.index("config.appdefinition")
            bootstrap = script.index("config.deployment.resource_groups")
            self.assertLess(validate, bootstrap)
            self.assertLess(bootstrap, script.index("config.deployment.topology"))
            self.assertLess(bootstrap, script.index("config.deployment.composition"))
            self.assertIn("--azure-dir", script)
            self.assertIn("--env-name", script)
            self.assertIn("RESOURCE_GROUP_EXIT" if suffix == "sh" else "$resourceGroupExitCode", script)
        parameters = json.loads((ROOT / "main.parameters.json").read_text())["parameters"]
        self.assertEqual(
            {"value": "${AZURE_APP_RESOURCE_GROUP=}"},
            parameters["applicationResourceGroupName"],
        )
        self.assertEqual(
            {"value": "${AZURE_NETWORK_RESOURCE_GROUP=}"},
            parameters["networkResourceGroupName"],
        )
        self.assertEqual(
            {"value": "${AZURE_APPLICATION_PE_SUBNET_NAME=application-pe-subnet}"},
            parameters["applicationPeSubnetName"],
        )
        self.assertEqual(
            {"value": "${AZURE_APPLICATION_PE_SUBNET_PREFIX=192.168.3.128/26}"},
            parameters["applicationPeSubnetPrefix"],
        )

    def test_subnet_creation_and_address_bindings_are_independent(self) -> None:
        parameters = json.loads((ROOT / "main.parameters.json").read_text())["parameters"]
        contracts = (
            ("Agent", "AGENT", "agent", "192.168.0.0/24"),
            ("AcaEnvironment", "ACA_ENVIRONMENT", "acaEnvironment", "192.168.1.0/24"),
            ("Pe", "PE", "pe", "192.168.2.0/26"),
            ("AzureBastion", "BASTION", "azureBastion", "192.168.2.64/26"),
            ("AzureFirewall", "FIREWALL", "azureFirewall", "192.168.2.128/26"),
            ("AzureFirewallManagement", "FIREWALL_MANAGEMENT", "azureFirewallManagement", "192.168.3.192/26"),
            ("Gateway", "GATEWAY", "gateway", "192.168.2.192/26"),
            ("AppGateway", "APP_GATEWAY", "azureAppGateway", "192.168.3.0/27"),
            ("Jumpbox", "JUMPBOX", "jumpbox", "192.168.3.64/27"),
            ("DevopsBuildAgents", "DEVOPS_BUILD_AGENTS", "devopsBuildAgents", "192.168.3.96/27"),
            ("ApplicationPe", "APPLICATION_PE", "applicationPe", "192.168.3.128/26"),
            ("PowerPlatform", "POWER_PLATFORM", "powerPlatform", "192.168.4.0/24"),
            ("AiGateway", "AI_GATEWAY", "aiGateway", "192.168.5.0/24"),
        )
        for flag, environment, prefix, cidr in contracts:
            with self.subTest(subnet=prefix):
                # Creation and address overrides are separate inputs, not service
                # enablement flags or a topology object that drops explicit values.
                flag_environment = {
                    "AzureBastion": "AZURE_BASTION",
                    "AzureFirewall": "AZURE_FIREWALL",
                    "AzureFirewallManagement": "AZURE_FIREWALL_MANAGEMENT",
                }.get(flag, environment)
                default = {
                    "AzureFirewall": "null", "AzureFirewallManagement": "null", "Gateway": "false",
                }.get(flag, "true")
                self.assertEqual(
                    {"value": f"${{DEPLOY_{flag_environment}_SUBNET={default}}}"},
                    parameters[f"deploy{flag}Subnet"],
                )
                self.assertEqual(
                    {"value": f"${{AZURE_{environment}_SUBNET_PREFIX={cidr}}}"},
                    parameters[f"{prefix}SubnetPrefix"],
                )
        self.assertIsInstance(parameters["vnetAddressPrefixes"]["value"], list)
        self.assertTrue(parameters["vnetAddressPrefixes"]["value"])
        self.assertEqual(
            {"value": "${DEPLOY_SUBNETS=true}"},
            parameters["deploySubnets"],
        )

    def test_composition_preserves_explicit_subnet_overrides_for_both_vnet_paths(self) -> None:
        from config.deployment.composition import compose_parameters

        source = json.loads((ROOT / "main.parameters.json").read_text())
        prefix_names = sorted(
            name for name in source["parameters"] if name.endswith("SubnetPrefix")
        )
        self.assertEqual(13, len(prefix_names))
        custom = {
            name: {"value": f"10.30.{index}.0/24"}
            for index, name in enumerate(prefix_names)
        }
        custom.update({
            "vnetAddressPrefixes": {"value": ["10.30.0.0/16"]},
            "applicationPeSubnetName": {"value": "tenant-app-pe"},
            "deployAgentSubnet": {"value": False},
            "deployApplicationPeSubnet": {"value": False},
        })
        for byo in (False, True):
            with self.subTest(use_existing_vnet=byo):
                requested = json.loads(json.dumps(source))
                requested["parameters"].update(custom)
                requested["parameters"]["useExistingVNet"] = {"value": byo}
                before = json.loads(json.dumps(requested))
                composed = compose_parameters(requested, {
                    "NETWORK_ISOLATION": "true",
                    "DEPLOYMENT_TOPOLOGY": "classic",
                })
                self.assertEqual(before, requested, "Composition must not mutate operator input.")
                for name, value in {
                    **custom, "useExistingVNet": {"value": byo},
                }.items():
                    self.assertEqual(value, composed["parameters"][name], name)

    def exercise_hook(
        self, shell: str, app_code: int, rg_code: int, inspect_defaults: bool = False,
        provider: str = "bicep",
    ) -> None:
        suffix = "ps1" if shell == "pwsh" else "sh"
        scripts = self.scratch / "scripts"
        scripts.mkdir(exist_ok=True)
        script = scripts / f"preProvision.{suffix}"
        shutil.copyfile(ROOT / "scripts" / script.name, script)
        for name in ("manifest.json", "azure.yaml", "app-definition.json"):
            shutil.copyfile(ROOT / name, self.scratch / name)
        trace = self.scratch / "trace"
        environment = dict(
            os.environ, TRACE=str(trace), APP_CODE=str(app_code), RG_CODE=str(rg_code),
            REAL_PYTHON=sys.executable,
            INFRA_TEST_PROVIDER=provider,
        )
        if inspect_defaults:
            (self.scratch / "infra").mkdir(exist_ok=True)
            if provider == "bicep":
                (self.scratch / "infra" / "main.bicep").write_text("", encoding="utf-8")
        selection = json.dumps({
            "foundry": "rg-ai", "application": "rg-app", "network": "rg-net",
            "create_resource_groups": True,
            "ownershipFile": str(self.azure_dir / "offline" / "terraform-resource-groups.json"),
        })
        if shell == "pwsh":
            wrapper = self.scratch / "wrapper.ps1"
            wrapper.write_text(
                "function azd { $global:LASTEXITCODE = 0; "
                "if ($args -contains 'json') { '{\"AZURE_ENV_NAME\":\"offline\"}' } "
                "else { 'AZURE_ENV_NAME=\"offline\"' } }\n"
                "function python {\n"
                " if ($args[1] -like '*config.deployment.provider*') {\n"
                "  $global:LASTEXITCODE = 0\n"
                "  @{ provider = $env:INFRA_TEST_PROVIDER; path = 'infra/terraform'; module = 'main' } | ConvertTo-Json -Compress\n"
                " } elseif ($args[1] -like '*config.appdefinition*') {\n"
                "  Add-Content -LiteralPath $env:TRACE -Value appdefinition\n"
                "  $global:LASTEXITCODE = [int]$env:APP_CODE\n"
                " } elseif ($args[1] -like '*config.deployment.resource_groups*' -or "
                "$args[1] -like '*config.deployment.terraform_groups*') {\n"
                "  $groupModule = if ($env:INFRA_TEST_PROVIDER -eq 'terraform') { 'terraform_groups' } else { 'resource_groups' }\n"
                "  Add-Content -LiteralPath $env:TRACE -Value $groupModule\n"
                "  $global:LASTEXITCODE = [int]$env:RG_CODE\n"
                f"  '{selection}'\n"
                " } elseif ($args[1] -like '*config.deployment.topology*') {\n"
                "  if ($env:AZURE_RESOURCE_GROUP -ne 'rg-ai' -or "
                "$env:AZURE_APP_RESOURCE_GROUP -ne 'rg-app' -or "
                "$env:AZURE_NETWORK_RESOURCE_GROUP -ne 'rg-net' -or "
                "$env:CREATE_RESOURCE_GROUPS -ne 'true') { throw 'Incorrect destinations' }\n"
                "  Add-Content -LiteralPath $env:TRACE -Value defaults_exported\n"
                "  $global:LASTEXITCODE = 5\n"
                " } else { throw 'Unexpected Python module' }\n"
                "}\n"
                "& (Join-Path $PSScriptRoot 'scripts\\preProvision.ps1')\n"
                "exit $LASTEXITCODE\n",
                encoding="utf-8",
            )
            command = [shutil.which(shell), "-NoProfile", "-NonInteractive", "-File", str(wrapper)]
        else:
            bin_dir = self.scratch / "bin"
            bin_dir.mkdir(exist_ok=True)
            (bin_dir / "azd").write_text(
                "#!/bin/sh\ncase \"$*\" in\n"
                "*'--output json'*) printf '%s\\n' '{\"AZURE_ENV_NAME\":\"offline\"}';;\n"
                "*) printf 'AZURE_ENV_NAME=\"offline\"\\n';;\nesac\n",
                encoding="utf-8",
            )
            (bin_dir / "python3").write_text(
                '#!/bin/sh\ncase "$2" in\n'
                'config.deployment.provider) printf \'{"provider":"%s","path":"infra/terraform","module":"main"}\\n\' "$INFRA_TEST_PROVIDER"; exit 0;;\n'
                'config.appdefinition) echo appdefinition >> "$TRACE"; exit "$APP_CODE";;\n'
                'config.deployment.resource_groups) echo resource_groups >> "$TRACE"; '
                f"printf '%s\\n' '{selection}'; " + 'exit "$RG_CODE";;\n'
                'config.deployment.terraform_groups) echo terraform_groups >> "$TRACE"; '
                f"printf '%s\\n' '{selection}'; " + 'exit "$RG_CODE";;\n'
                '*"import json, sys"*) exec "$REAL_PYTHON" "$@";;\n'
                'config.deployment.topology) '
                '[ "$AZURE_RESOURCE_GROUP" = rg-ai ] && '
                '[ "$AZURE_APP_RESOURCE_GROUP" = rg-app ] && '
                '[ "$AZURE_NETWORK_RESOURCE_GROUP" = rg-net ] && '
                '[ "$CREATE_RESOURCE_GROUPS" = true ] || exit 97; '
                'echo defaults_exported >> "$TRACE"; exit 5;;\n'
                '*"import json, shlex"*) exec "$REAL_PYTHON" "$@";;\n'
                '*) exit 99;;\nesac\n',
                encoding="utf-8",
            )
            for file in bin_dir.iterdir():
                file.chmod(0o755)
            environment["PATH"] = str(bin_dir) + os.pathsep + environment["PATH"]
            # Git bash converts the inherited Windows PATH and TRACE on startup.
            command = [shutil.which(shell), str(script)]
        result = subprocess.run(command, cwd=self.scratch, env=environment,
                                capture_output=True, text=True, timeout=30)
        group_module = "terraform_groups" if provider == "terraform" else "resource_groups"
        expected = ["appdefinition"] + ([group_module] if not app_code else [])
        if inspect_defaults:
            expected.append("defaults_exported")
        self.assertEqual(expected, trace.read_text(encoding="utf-8-sig").splitlines(), result.stdout + result.stderr)
        expected_code = 5 if inspect_defaults else app_code or rg_code or 1
        self.assertEqual(expected_code, result.returncode, result.stdout + result.stderr)
        if not app_code and not rg_code and not inspect_defaults:
            self.assertIn("infra/main.bicep", result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell unavailable")
    def test_powershell_behavioral_order_and_failures(self) -> None:
        for app_code, rg_code in ((2, 0), (0, 1), (0, 0)):
            with self.subTest(app_code=app_code, rg_code=rg_code):
                (self.scratch / "trace").unlink(missing_ok=True)
                self.exercise_hook("pwsh", app_code, rg_code)

    @unittest.skipUnless(shutil.which("bash"), "Bash unavailable")
    def test_shell_behavioral_order_and_failures(self) -> None:
        for app_code, rg_code in ((2, 0), (0, 1), (0, 0)):
            with self.subTest(app_code=app_code, rg_code=rg_code):
                (self.scratch / "trace").unlink(missing_ok=True)
                self.exercise_hook("bash", app_code, rg_code)

    def test_resolved_destinations_reach_later_modules_in_both_hooks(self) -> None:
        for shell in ("pwsh", "bash"):
            if shutil.which(shell):
                with self.subTest(shell=shell):
                    (self.scratch / "trace").unlink(missing_ok=True)
                    self.exercise_hook(shell, 0, 0, inspect_defaults=True)

    def test_terraform_destinations_do_not_use_the_bicep_bootstrap(self) -> None:
        for shell in ("pwsh", "bash"):
            if shutil.which(shell):
                with self.subTest(shell=shell):
                    (self.scratch / "trace").unlink(missing_ok=True)
                    self.exercise_hook(shell, 0, 0, inspect_defaults=True, provider="terraform")


if __name__ == "__main__":
    unittest.main()
