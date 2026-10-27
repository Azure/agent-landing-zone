"""Pure runtime-egress boundary validation shared by planning and reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from typing import Mapping


@dataclass(frozen=True, order=True)
class Destination:
    fqdn: str
    protocol: str
    port: int


def validate_requirement(value: Mapping[str, object]) -> Destination:
    """Validate an exact DNS hostname and Azure Firewall application protocol."""
    if set(value) != {"fqdn", "protocol", "port", "purpose"}:
        raise ValueError("Egress requires exactly fqdn, protocol, port and purpose.")
    fqdn = value["fqdn"]
    if not isinstance(fqdn, str) or len(fqdn) > 253 or not re.fullmatch(
        r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
        r"[A-Za-z](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", fqdn, re.ASCII,
    ):
        raise ValueError("Egress fqdn must be an exact fully qualified DNS hostname, not a URL, IP or wildcard.")
    try:
        ipaddress.ip_address(fqdn)
    except ValueError:
        pass
    else:
        raise ValueError("Egress fqdn must not be an IP address.")
    if fqdn.lower().endswith((".localhost", ".local", ".internal")):
        raise ValueError("Egress fqdn must not be a local hostname.")
    protocol, port, purpose = value["protocol"], value["port"], value["purpose"]
    if protocol not in ("https", "http"):
        raise ValueError("Egress protocol must be https or http.")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 64000:
        raise ValueError("Egress port must be an integer from 1 through 64000.")
    if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 256 or any(
        ord(char) < 32 or ord(char) == 127 for char in purpose
    ):
        raise ValueError("Egress purpose must be nonblank text without control characters (at most 256 characters).")
    return Destination(fqdn.lower(), str(protocol), port)
