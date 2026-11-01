"""Credential-free private DNS/TLS prerequisites for deployment hosts."""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import os
import re
import socket
import ssl
import subprocess
import sys
import time
from typing import Mapping
from urllib.parse import urlsplit

from config.deployment.composition import is_bundled_application, is_truthy, requires_hosted_foundation, resolve_mode
from config.deployment.native import OrchestrationHost
from config.deployment.native import resolve_application, scheduler_settings, selected as native_selected


LOGGER = logging.getLogger(__name__)
STAGES = ("post-provision", "pre-deploy", "hosted-build")
DEFERRED = 20
DNS_TIMEOUT = 10
ENDPOINT_TIMEOUT = 20
MAX_ADDRESSES = 16
PRIVATE_NETWORKS = tuple(
    ipaddress.IPv4Network(prefix)
    for prefix in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
ENDPOINT_SUFFIXES = {
    "APP_CONFIG_ENDPOINT": ".azconfig.io",
    "AZURE_AI_PROJECT_ENDPOINT": ".services.ai.azure.com",
    "AZURE_CONTAINER_REGISTRY_ENDPOINT": ".azurecr.io",
    "DURABLE_TASK_SCHEDULER_ENDPOINT": ".durabletask.io",
}
_DNS_SCRIPT = (
    "import json, socket, sys; "
    "print(json.dumps(sorted({entry[4][0] for entry in "
    "socket.getaddrinfo(sys.argv[1], 443, type=socket.SOCK_STREAM)})))"
)


class PrivateNetworkError(ValueError):
    """The host has not established a required private network prerequisite."""


def _hostname(key: str, endpoint: str) -> str:
    invalid = PrivateNetworkError(
        f"{key}: expected the provisioned public-Azure service hostname over "
        "HTTPS on port 443, without credentials, query or fragment. "
        "Restore the provisioning output; do not substitute an IP or public proxy."
    )
    if not endpoint or any(ord(char) <= 32 for char in endpoint) or "\\" in endpoint:
        raise invalid
    if key == "AZURE_CONTAINER_REGISTRY_ENDPOINT" and "://" not in endpoint:
        endpoint = "https://" + endpoint
    try:
        parsed = urlsplit(endpoint)
        hostname = parsed.hostname or ""
        if (
            parsed.scheme != "https"
            or parsed.port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or "?" in endpoint
            or "#" in endpoint
            or not hostname.endswith(ENDPOINT_SUFFIXES[key])
            or len(hostname) > 253
            or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in hostname.split(".")
            )
        ):
            raise invalid
    except (ValueError, KeyError):
        raise invalid from None
    return hostname


def _resolve_addresses(hostname: str) -> list[str]:
    # Bound getaddrinfo in a child process; use OS DNS/NRPT, not a separate resolver.
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", _DNS_SCRIPT, hostname],
            capture_output=True,
            text=True,
            check=False,
            timeout=DNS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise PrivateNetworkError(
            f"{hostname}: DNS resolution timed out. Check VPN DNS and resolver access."
        ) from None
    except OSError:
        raise PrivateNetworkError(
            f"{hostname}: could not start the system DNS probe. Check the Python installation."
        ) from None
    if result.returncode != 0:
        raise PrivateNetworkError(
            f"{hostname}: DNS resolution failed. Check VPN/NRPT, private DNS links "
            "and provisioned endpoint records."
        )
    try:
        addresses = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise PrivateNetworkError(f"{hostname}: invalid DNS probe result.") from None
    if not isinstance(addresses, list) or not all(isinstance(ip, str) for ip in addresses):
        raise PrivateNetworkError(f"{hostname}: invalid DNS address list.")
    return addresses


def check_endpoint(key: str, endpoint: str) -> None:
    hostname = _hostname(key, endpoint)
    deadline = time.monotonic() + ENDPOINT_TIMEOUT
    addresses = _resolve_addresses(hostname)
    if not addresses or len(addresses) > MAX_ADDRESSES:
        raise PrivateNetworkError(f"{key}: DNS returned an empty or excessive address list.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise PrivateNetworkError(f"{key}: DNS returned an invalid address.") from None
        if not isinstance(ip, ipaddress.IPv4Address) or not any(
            ip in network for network in PRIVATE_NETWORKS
        ):
            raise PrivateNetworkError(
                f"{key} ({hostname}): every DNS answer must be a private IPv4 "
                "address (RFC1918). Check private DNS and VPN settings; public, "
                "mixed, loopback and link-local answers are not accepted."
            )

    def remaining() -> float:
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise PrivateNetworkError(f"{key} ({hostname}): private connectivity timed out.")
        return seconds

    try:
        context = ssl.create_default_context()
        for address in addresses:
            timeout = remaining()
            # Numeric AF_INET connects cannot re-resolve DNS. Keep the original
            # hostname for SNI and normal certificate/CA validation; send no HTTP.
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
                connection.settimeout(timeout)
                connection.connect((address, 443))
                connection.settimeout(remaining())
                with context.wrap_socket(connection, server_hostname=hostname):
                    remaining()
    except ssl.SSLCertVerificationError:
        raise PrivateNetworkError(
            f"{key} ({hostname}): TLS certificate validation failed. Check the "
            "endpoint hostname and trusted CA configuration; do not disable verification."
        ) from None
    except OSError:
        raise PrivateNetworkError(
            f"{key} ({hostname}): private TCP/TLS connection failed. Check the "
            "VPN, forward/return routes, NSG/firewall and TCP 443 access."
        ) from None
    LOGGER.info("%s: private DNS and TLS reachable; authorization and API health not tested.", key)


def check_stage(environment: Mapping[str, str], stage: str) -> int:
    if stage not in STAGES:
        raise PrivateNetworkError("Unknown private network check stage.")
    isolation = (environment.get("NETWORK_ISOLATION") or "").strip().lower()
    if not is_truthy(isolation):
        if isolation not in {"", "false", "0", "f", "no", "n"}:
            raise PrivateNetworkError("NETWORK_ISOLATION must be a boolean value.")
        return 0
    jumpbox = (environment.get("RUN_FROM_JUMPBOX") or "").strip().lower()
    if stage == "post-provision" and not is_truthy(jumpbox):
        if jumpbox in {"false", "0", "no", "skip"} or is_truthy(
            environment.get("AZURE_SKIP_NETWORK_ISOLATION_WARNING")
        ):
            LOGGER.warning(
                "Data-plane configuration NOT performed: explicitly deferred by "
                "RUN_FROM_JUMPBOX or AZURE_SKIP_NETWORK_ISOLATION_WARNING. "
                "Clear the deferral setting and rerun postProvision from a "
                "VPN/VNet-connected host. Provisioning alone is not application readiness."
            )
            return DEFERRED

    keys = ["APP_CONFIG_ENDPOINT"]
    if stage == "hosted-build":
        keys = ["AZURE_CONTAINER_REGISTRY_ENDPOINT"]
    elif stage == "pre-deploy" and requires_hosted_foundation(
        environment, hosted_orchestration=is_bundled_application(environment)
        and resolve_mode(environment) is OrchestrationHost.HOSTED,
    ):
        keys.append("AZURE_AI_PROJECT_ENDPOINT")
    endpoints = [(key, environment.get(key) or "") for key in keys]
    if stage == "pre-deploy" and is_bundled_application(environment) and resolve_application(environment).host == "container_apps":
        # Validate the actual output before probing it. No constructed hostname,
        # public-network fallback or RUN_FROM_JUMPBOX connectivity bypass.
        scheduler_settings(environment)
        backend = json.loads(environment["HOSTED_AGENT_DEPLOYMENT"])["durableTask"]
        endpoints.append(("DURABLE_TASK_SCHEDULER_ENDPOINT", backend["endpoint"]))
    for key, endpoint in endpoints:
        if not endpoint.strip():
            raise PrivateNetworkError(
                f"Missing {key}. Run provisioning and load the selected azd "
                "environment outputs before this stage."
            )
        _hostname(key, endpoint)
    for key, endpoint in endpoints:
        check_endpoint(key, endpoint)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        return check_stage(os.environ, args.stage)
    except ValueError as exc:
        LOGGER.error("Private network prerequisite failed: %s", exc)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
