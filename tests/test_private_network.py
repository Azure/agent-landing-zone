from __future__ import annotations

import json
import socket
import ssl
import subprocess
import unittest
from unittest.mock import MagicMock, call, patch

from config.deployment import private_network as network


PRIVATE = {
    "NETWORK_ISOLATION": "true",
    "ORCHESTRATION_HOST": "hosted",
    "APP_CONFIG_ENDPOINT": "https://config.azconfig.io",
    "AZURE_AI_PROJECT_ENDPOINT": "https://foundry.services.ai.azure.com/api/projects/demo",
    "AZURE_CONTAINER_REGISTRY_ENDPOINT": "registry.azurecr.io",
}


class StageTests(unittest.TestCase):
    @patch.object(network, "check_endpoint")
    def test_public_needs_no_endpoints_or_network(self, probe: MagicMock) -> None:
        for stage in network.STAGES:
            for flag in ("", "false", "0", "no", "FALSE"):
                with self.subTest(stage=stage, flag=flag):
                    self.assertEqual(0, network.check_stage({"NETWORK_ISOLATION": flag}, stage))
        probe.assert_not_called()

    @patch.object(network, "check_endpoint")
    def test_invalid_stage_and_isolation_fail_closed(self, probe: MagicMock) -> None:
        for stage, env in (
            ("unknown", {}),
            ("pre-deploy", {**PRIVATE, "NETWORK_ISOLATION": "tru"}),
            ("pre-deploy", {**PRIVATE, "ORCHESTRATION_HOST": "invalid"}),
        ):
            with self.subTest(stage=stage, env=env), self.assertRaises(ValueError):
                network.check_stage(env, stage)
        probe.assert_not_called()

    @patch.object(network, "check_endpoint")
    def test_vpn_needs_no_jumpbox_flag(self, probe: MagicMock) -> None:
        original = dict(PRIVATE)
        self.assertEqual(0, network.check_stage(PRIVATE, "pre-deploy"))
        self.assertEqual(
            ["APP_CONFIG_ENDPOINT", "AZURE_AI_PROJECT_ENDPOINT"],
            [item.args[0] for item in probe.call_args_list],
        )
        self.assertEqual(original, PRIVATE)

    @patch.object(network, "check_endpoint")
    def test_postprovision_only_needs_entry_endpoint(self, probe: MagicMock) -> None:
        env = {"NETWORK_ISOLATION": "true", "APP_CONFIG_ENDPOINT": PRIVATE["APP_CONFIG_ENDPOINT"]}
        self.assertEqual(0, network.check_stage(env, "post-provision"))
        probe.assert_called_once_with("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])

    @patch.object(network, "check_endpoint")
    def test_custom_container_only_does_not_probe_foundry_or_dts(self, probe: MagicMock) -> None:
        env = {**PRIVATE, "ORCHESTRATION_HOST": "container_apps", "AGENTLZ_APP_DEFINITION": "samples/custom-app/containerapp", "AZURE_AI_PROJECT_ENDPOINT": ""}
        self.assertEqual(0, network.check_stage(env, "pre-deploy"))
        probe.assert_called_once_with("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])

    @patch.object(network, "check_endpoint")
    def test_hosted_topologies_require_foundry(self, probe: MagicMock) -> None:
        for mode in ("conversational", "workflow", "both"):
            with self.subTest(mode=mode):
                probe.reset_mock()
                self.assertEqual(0, network.check_stage(
                    {**PRIVATE, "APPLICATION_MODE": mode}, "pre-deploy"
                ))
                self.assertEqual(2, probe.call_count)

    @patch.object(network, "check_endpoint")
    def test_build_only_probes_registry(self, probe: MagicMock) -> None:
        self.assertEqual(0, network.check_stage({
            "NETWORK_ISOLATION": "true",
            "AZURE_CONTAINER_REGISTRY_ENDPOINT": PRIVATE["AZURE_CONTAINER_REGISTRY_ENDPOINT"],
        }, "hosted-build"))
        probe.assert_called_once_with(
            "AZURE_CONTAINER_REGISTRY_ENDPOINT", PRIVATE["AZURE_CONTAINER_REGISTRY_ENDPOINT"]
        )

    @patch.object(network, "check_endpoint")
    def test_explicit_postprovision_deferral_is_preserved(self, probe: MagicMock) -> None:
        for flag in ("false", "0", "no", "skip", " FALSE "):
            with self.subTest(flag=flag), self.assertLogs(network.LOGGER, level="WARNING") as logs:
                self.assertEqual(network.DEFERRED, network.check_stage(
                    {"NETWORK_ISOLATION": "true", "RUN_FROM_JUMPBOX": flag}, "post-provision"
                ))
                self.assertIn("NOT performed", " ".join(logs.output))
        with self.assertLogs(network.LOGGER, level="WARNING"):
            self.assertEqual(network.DEFERRED, network.check_stage({
                **PRIVATE, "AZURE_SKIP_NETWORK_ISOLATION_WARNING": "true",
            }, "post-provision"))
        probe.assert_not_called()

    @patch.object(network, "check_endpoint")
    def test_unset_or_blank_jumpbox_probes_unless_warning_defers(self, probe: MagicMock) -> None:
        for flag in ("", " "):
            with self.subTest(flag=flag):
                probe.reset_mock()
                env = {**PRIVATE, "RUN_FROM_JUMPBOX": flag}
                self.assertEqual(0, network.check_stage(env, "post-provision"))
                probe.assert_called_once()
                probe.reset_mock()
                with self.assertLogs(network.LOGGER, level="WARNING"):
                    self.assertEqual(network.DEFERRED, network.check_stage({
                        **env, "AZURE_SKIP_NETWORK_ISOLATION_WARNING": "true",
                    }, "post-provision"))
                probe.assert_not_called()

    @patch.object(network, "check_endpoint")
    def test_jumpbox_overrides_warning_but_not_probe(self, probe: MagicMock) -> None:
        for flag in ("true", "1", "yes", "t", "y"):
            with self.subTest(flag=flag):
                env = {**PRIVATE, "RUN_FROM_JUMPBOX": flag,
                       "AZURE_SKIP_NETWORK_ISOLATION_WARNING": "true"}
                probe.reset_mock()
                probe.side_effect = None
                self.assertEqual(0, network.check_stage(env, "post-provision"))
                probe.assert_called_once()
                probe.side_effect = network.PrivateNetworkError("unreachable")
                with self.assertRaises(network.PrivateNetworkError):
                    network.check_stage(env, "post-provision")

    @patch.object(network, "check_endpoint")
    def test_deferral_flags_never_skip_deployment(self, probe: MagicMock) -> None:
        for stage in ("pre-deploy", "hosted-build"):
            for flag in ("false", "true"):
                with self.subTest(stage=stage, flag=flag):
                    probe.reset_mock()
                    probe.side_effect = network.PrivateNetworkError("unreachable")
                    with self.assertRaises(network.PrivateNetworkError):
                        network.check_stage({
                            **PRIVATE, "RUN_FROM_JUMPBOX": flag,
                            "AZURE_SKIP_NETWORK_ISOLATION_WARNING": "true",
                        }, stage)
                    probe.assert_called_once()

    @patch.object(network, "check_endpoint")
    def test_missing_or_bad_values_fail_before_any_probe(self, probe: MagicMock) -> None:
        for stage, key in (
            ("post-provision", "APP_CONFIG_ENDPOINT"),
            ("pre-deploy", "AZURE_AI_PROJECT_ENDPOINT"),
            ("hosted-build", "AZURE_CONTAINER_REGISTRY_ENDPOINT"),
        ):
            for value in ("", " ", "http://invalid", PRIVATE[key] + "\n"):
                with self.subTest(stage=stage, value=value), self.assertRaisesRegex(
                    network.PrivateNetworkError, key
                ):
                    network.check_stage({**PRIVATE, key: value}, stage)
        probe.assert_not_called()

    def test_cli_reports_failure_not_success(self) -> None:
        with patch.object(network.os, "environ", PRIVATE), patch.object(
            network, "check_endpoint", side_effect=network.PrivateNetworkError("DNS failed")
        ), self.assertLogs(network.LOGGER, level="ERROR") as logs:
            self.assertEqual(4, network.main(["--stage", "pre-deploy"]))
        self.assertIn("DNS failed", " ".join(logs.output))


class EndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolve = self.enterContext(
            patch.object(network, "_resolve_addresses", return_value=["10.240.2.5"])
        )
        self.socket = self.enterContext(patch.object(network.socket, "socket"))
        self.context = self.enterContext(patch.object(network.ssl, "create_default_context"))
        self.raw_socket = self.socket.return_value.__enter__.return_value

    def test_private_ip_pinned_with_hostname_validation(self) -> None:
        with patch.object(network.socket, "getaddrinfo") as resolver:
            network.check_endpoint("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])
        self.resolve.assert_called_once_with("config.azconfig.io")
        resolver.assert_not_called()
        self.socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        self.raw_socket.connect.assert_called_once_with(("10.240.2.5", 443))
        for item in self.raw_socket.settimeout.call_args_list:
            self.assertGreater(item.args[0], 0)
            self.assertLessEqual(item.args[0], 20)
        self.context.assert_called_once_with()
        self.context.return_value.wrap_socket.assert_called_once_with(
            self.raw_socket, server_hostname="config.azconfig.io"
        )
        self.raw_socket.sendall.assert_not_called()
        self.raw_socket.send.assert_not_called()

    def test_every_returned_address_is_checked(self) -> None:
        self.resolve.return_value = ["10.240.2.5", "172.16.0.5", "192.168.2.5"]
        network.check_endpoint("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])
        self.assertEqual(
            [call((ip, 443)) for ip in self.resolve.return_value],
            self.raw_socket.connect.call_args_list,
        )

    def test_rfc1918_boundaries(self) -> None:
        self.resolve.return_value = [
            "10.0.0.0", "10.255.255.255", "172.16.0.0", "172.31.255.255",
            "192.168.0.0", "192.168.255.255",
        ]
        network.check_endpoint("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])
        self.assertEqual(6, self.socket.call_count)

    def test_public_or_special_or_mixed_answers_never_connect(self) -> None:
        for ip in (
            "8.8.8.8", "127.0.0.1", "169.254.169.254", "168.63.129.16",
            "0.0.0.0", "100.64.0.1", "::1", "::ffff:10.240.2.5", "fc00::1",
            "9.255.255.255", "11.0.0.0", "172.15.255.255", "172.32.0.0",
            "192.167.255.255", "192.169.0.0", "224.0.0.1", "2001:db8::1",
        ):
            for answers in ([ip], ["10.240.2.5", ip]):
                with self.subTest(answers=answers), self.assertRaisesRegex(
                    network.PrivateNetworkError, "private IPv4"
                ):
                    self.resolve.return_value = answers
                    network.check_endpoint("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])
        self.socket.assert_not_called()

    def test_bad_urls_never_resolve_or_expose_secrets(self) -> None:
        for endpoint in (
            "", "http://config.azconfig.io", "https://config.azconfig.io:8443",
            "https://user:SECRET@config.azconfig.io",
            "https://config.azconfig.io/?token=SECRET", "https://config.azconfig.io/#SECRET",
            "https://10.0.0.5", "https://[fd00::1]", "https://config.azconfig.io.attacker.test",
            "https://azconfig.io", "https://config.azconfig.io\\@attacker.test",
            "https://config.azconfig.io\n", "https://config.azconfig.io:invalid",
            "https://bad_name.azconfig.io", "https://-bad.azconfig.io", "https://bad-.azconfig.io",
            "https://config.azconfig.io.", "https://" + "a" * 64 + ".azconfig.io",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(
                network.PrivateNetworkError
            ) as error:
                network.check_endpoint("APP_CONFIG_ENDPOINT", endpoint)
            self.assertNotIn("SECRET", str(error.exception))
        self.resolve.assert_not_called()
        self.socket.assert_not_called()

    def test_project_path_and_bare_registry_are_supported(self) -> None:
        for key, endpoint in (
            ("AZURE_AI_PROJECT_ENDPOINT", PRIVATE["AZURE_AI_PROJECT_ENDPOINT"]),
            ("AZURE_CONTAINER_REGISTRY_ENDPOINT", PRIVATE["AZURE_CONTAINER_REGISTRY_ENDPOINT"]),
            ("AZURE_CONTAINER_REGISTRY_ENDPOINT", "https://registry.azurecr.io:443"),
            ("APP_CONFIG_ENDPOINT", "https://config.azconfig.io:443/"),
        ):
            network.check_endpoint(key, endpoint)
        self.assertEqual(4, self.socket.call_count)

    def test_dns_timeout_is_terminal(self) -> None:
        self.resolve.side_effect = network.PrivateNetworkError("DNS resolution timed out")
        with self.assertRaisesRegex(network.PrivateNetworkError, "DNS"):
            network.check_endpoint("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])
        self.socket.assert_not_called()

    def test_empty_and_malformed_dns_answers_are_terminal(self) -> None:
        for answers in ([], ["not-an-ip"], ["10.0.0.1"] * 17):
            self.resolve.return_value = answers
            with self.subTest(answers=answers), self.assertRaises(network.PrivateNetworkError):
                network.check_endpoint("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])
        self.socket.assert_not_called()

    def test_address_limit_is_inclusive(self) -> None:
        self.resolve.return_value = [f"10.0.0.{n}" for n in range(1, 17)]
        network.check_endpoint("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])
        self.assertEqual(16, self.socket.call_count)

    def test_connect_and_certificate_errors_are_terminal(self) -> None:
        for error in (TimeoutError("timed out"), ConnectionRefusedError("refused")):
            self.raw_socket.connect.side_effect = error
            with self.assertRaisesRegex(network.PrivateNetworkError, "TCP/TLS"):
                network.check_endpoint("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])
        self.raw_socket.connect.side_effect = None
        for error, message in (
            (ssl.SSLCertVerificationError("bad cert"), "certificate"),
            (ssl.SSLError("bad handshake"), "TCP/TLS"),
            (TimeoutError("timed out"), "TCP/TLS"),
        ):
            self.context.return_value.wrap_socket.side_effect = error
            with self.assertRaisesRegex(network.PrivateNetworkError, message):
                network.check_endpoint("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])

    def test_budget_exhaustion_before_connect_is_terminal(self) -> None:
        with patch.object(network.time, "monotonic", side_effect=[0, 21]):
            with self.assertRaisesRegex(network.PrivateNetworkError, "timed out"):
                network.check_endpoint("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])
        self.socket.assert_not_called()

    def test_dns_tcp_and_tls_share_one_budget(self) -> None:
        self.resolve.return_value = ["10.0.0.1", "10.0.0.2"]
        with patch.object(network.time, "monotonic", side_effect=[0, 10, 14, 19, 20]):
            with self.assertRaisesRegex(network.PrivateNetworkError, "timed out"):
                network.check_endpoint("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])
        self.assertEqual([call(10), call(6)], self.raw_socket.settimeout.call_args_list)
        self.raw_socket.connect.assert_called_once_with(("10.0.0.1", 443))

    def test_last_handshake_cannot_report_success_after_budget(self) -> None:
        with patch.object(network.time, "monotonic", side_effect=[0, 10, 14, 21]):
            with self.assertRaisesRegex(network.PrivateNetworkError, "timed out"):
                network.check_endpoint("APP_CONFIG_ENDPOINT", PRIVATE["APP_CONFIG_ENDPOINT"])


class ResolverTests(unittest.TestCase):
    @patch.object(network.subprocess, "run")
    def test_dns_subprocess_is_bounded_and_uses_system_resolver(self, run: MagicMock) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps(["10.0.0.1"]), "")
        self.assertEqual(["10.0.0.1"], network._resolve_addresses("config.azconfig.io"))
        self.assertEqual(10, run.call_args.kwargs["timeout"])
        self.assertEqual("-I", run.call_args.args[0][1])
        self.assertIn("socket.getaddrinfo", run.call_args.args[0][3])
        self.assertEqual("config.azconfig.io", run.call_args.args[0][-1])
        self.assertNotIn("shell", run.call_args.kwargs)

    @patch.object(network.subprocess, "run")
    def test_resolver_failures_do_not_fall_back(self, run: MagicMock) -> None:
        for result in (
            subprocess.CompletedProcess([], 1, "", "socket error"),
            subprocess.CompletedProcess([], 0, "not-json", ""),
            subprocess.CompletedProcess([], 0, '"not-a-list"', ""),
            subprocess.CompletedProcess([], 0, '["10.0.0.1", 42]', ""),
            subprocess.CompletedProcess([], 0, "null", ""),
        ):
            run.return_value = result
            with self.subTest(result=result), self.assertRaises(network.PrivateNetworkError):
                network._resolve_addresses("config.azconfig.io")
        for error, message in (
            (subprocess.TimeoutExpired("python", 10), "timed out"),
            (OSError("unavailable"), "could not start"),
        ):
            run.side_effect = error
            with self.assertRaisesRegex(network.PrivateNetworkError, message):
                network._resolve_addresses("config.azconfig.io")


if __name__ == "__main__":
    unittest.main()
