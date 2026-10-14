"""Publish Agent Landing Zone platform outputs to App Configuration (R13).

After ``azd provision`` the landing zone publishes its non-secret endpoints for
any application as one JSON key, ``AGENTLZ_PLATFORM_OUTPUTS``, plus one flat
key per field, all under the App Configuration label ``agent-lz``. The JSON
document is validated against ``contracts/platform-outputs-v1.schema.json``
before anything is written.

The module also owns the ``azd deploy`` foundation guard: deploying without a
provisioned foundation fails with "run azd provision first" before any Azure
call is made.

Run as ``python -m config.deployment.outputs`` (publish) or
``python -m config.deployment.outputs --check-foundation`` (guard only).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from config import find_repo_root
from config.deployment.composition import APP_CONFIG_LABEL, is_truthy

PLATFORM_OUTPUTS_KEY = "AGENTLZ_PLATFORM_OUTPUTS"
SCHEMA_RELATIVE_PATH = Path("contracts") / "platform-outputs-v1.schema.json"
SCHEMA_VERSION = 1
FOUNDATION_MISSING_MESSAGE = (
    "The foundation is not provisioned. Run azd provision first."
)
# azd environment values that only exist after a successful ``azd provision``.
FOUNDATION_REQUIRED_ENV: tuple[str, ...] = (
    "AZURE_RESOURCE_GROUP",
    "APP_CONFIG_ENDPOINT",
)
IDENTITIES_ENV = "AGENTLZ_COMPONENT_IDENTITIES"

# (JSON path, flat key, azd environment source names in preference order).
_FIELDS: tuple[tuple[tuple[str, str], str, tuple[str, ...]], ...] = (
    (("foundry", "projectEndpoint"), "AGENTLZ_FOUNDRY_PROJECT_ENDPOINT",
     ("AZURE_AI_PROJECT_ENDPOINT", "AI_FOUNDRY_PROJECT_ENDPOINT")),
    (("foundry", "accountName"), "AGENTLZ_FOUNDRY_ACCOUNT_NAME",
     ("AI_FOUNDRY_ACCOUNT_NAME", "AZURE_AI_ACCOUNT_NAME")),
    (("registry", "loginServer"), "AGENTLZ_ACR_LOGIN_SERVER",
     ("AZURE_CONTAINER_REGISTRY_ENDPOINT", "CONTAINER_REGISTRY_LOGIN_SERVER")),
    (("appConfig", "endpoint"), "AGENTLZ_APPCONFIG_ENDPOINT",
     ("APP_CONFIG_ENDPOINT",)),
    (("search", "endpoint"), "AGENTLZ_SEARCH_ENDPOINT",
     ("SEARCH_SERVICE_ENDPOINT", "SEARCH_SERVICE_QUERY_ENDPOINT")),
    (("storage", "blobEndpoint"), "AGENTLZ_STORAGE_BLOB_ENDPOINT",
     ("STORAGE_BLOB_ENDPOINT", "STORAGE_ACCOUNT_BLOB_ENDPOINT")),
    (("cosmos", "endpoint"), "AGENTLZ_COSMOS_ENDPOINT",
     ("COSMOS_DB_ENDPOINT",)),
    (("keyVault", "uri"), "AGENTLZ_KEYVAULT_URI",
     ("KEY_VAULT_URI", "AZURE_KEY_VAULT_ENDPOINT")),
)
_OPTIONAL_SECTIONS = frozenset({"search", "cosmos"})


class PlatformOutputsError(ValueError):
    """Raised when platform outputs are incomplete or violate the contract."""


class FoundationMissingError(RuntimeError):
    """Raised by the ``azd deploy`` guard when no foundation is provisioned."""


def require_foundation(environment: Mapping[str, str]) -> None:
    """Fail before any Azure call when ``azd provision`` has not run."""
    missing = [
        name
        for name in FOUNDATION_REQUIRED_ENV
        if not (environment.get(name) or "").strip()
    ]
    if missing:
        raise FoundationMissingError(
            f"{FOUNDATION_MISSING_MESSAGE} Missing: {', '.join(missing)}."
        )


def _first(environment: Mapping[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = (environment.get(name) or "").strip()
        if value:
            return value
    return ""


def identity_flat_key(component: str) -> str:
    return f"AGENTLZ_IDENTITY_{component.upper().replace('-', '_')}_CLIENT_ID"


def _identities(
    environment: Mapping[str, str],
    identities: Mapping[str, str] | None,
) -> list[dict[str, str]]:
    if identities is None:
        raw = (environment.get(IDENTITIES_ENV) or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise PlatformOutputsError(
                f"{IDENTITIES_ENV} must be a JSON object of "
                f"component -> client id: {error}"
            ) from error
        if not isinstance(parsed, dict):
            raise PlatformOutputsError(
                f"{IDENTITIES_ENV} must be a JSON object of component -> client id."
            )
        identities = {str(k): str(v) for k, v in parsed.items()}
    return [
        {"component": component, "clientId": client_id}
        for component, client_id in sorted(identities.items())
    ]


def build_platform_outputs(
    environment: Mapping[str, str],
    identities: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble the platform outputs document from azd environment values.

    ``identities`` maps each ``containerapp`` component name to its managed
    identity client id; when omitted, ``AGENTLZ_COMPONENT_IDENTITIES`` (JSON)
    is read. Optional sections (Search, Cosmos DB) are omitted when empty.
    """
    document: dict[str, Any] = {"schemaVersion": SCHEMA_VERSION}
    missing: list[str] = []
    for (section, field), flat_key, sources in _FIELDS:
        value = _first(environment, sources)
        if not value:
            if section not in _OPTIONAL_SECTIONS:
                missing.append(f"{flat_key} (from {' or '.join(sources)})")
            continue
        document.setdefault(section, {})[field] = value
    if missing:
        raise PlatformOutputsError(
            "Cannot publish platform outputs; missing values: "
            + "; ".join(missing)
        )
    document["identities"] = _identities(environment, identities)
    document["network"] = {
        "isolated": is_truthy(environment.get("NETWORK_ISOLATION"))
    }
    return document


def load_schema(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    return json.loads((root / SCHEMA_RELATIVE_PATH).read_text(encoding="utf-8"))


def validate_platform_outputs(
    document: Mapping[str, Any],
    schema: Mapping[str, Any] | None = None,
) -> None:
    """Validate against ``contracts/platform-outputs-v1.schema.json``."""
    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(
        schema or load_schema(), format_checker=FormatChecker()
    )
    errors = sorted(
        validator.iter_errors(document), key=lambda e: list(e.absolute_path)
    )
    if errors:
        details = "; ".join(
            f"/{'/'.join(str(p) for p in error.absolute_path)}: {error.message}"
            for error in errors
        )
        raise PlatformOutputsError(
            f"Platform outputs violate {SCHEMA_RELATIVE_PATH.as_posix()}: {details}"
        )


def flat_settings(document: Mapping[str, Any]) -> dict[str, str]:
    """Return the flat keys that mirror ``document`` field by field."""
    settings: dict[str, str] = {}
    for (section, field), flat_key, _ in _FIELDS:
        value = (document.get(section) or {}).get(field)
        if value:
            settings[flat_key] = str(value)
    for identity in document.get("identities", []):
        settings[identity_flat_key(identity["component"])] = identity["clientId"]
    settings["AGENTLZ_NETWORK_ISOLATED"] = str(
        bool(document["network"]["isolated"])
    ).lower()
    return settings


def platform_settings(document: Mapping[str, Any]) -> dict[str, str]:
    """All keys to publish: the JSON document first, then the flat keys."""
    return {
        PLATFORM_OUTPUTS_KEY: json.dumps(
            document, separators=(",", ":"), sort_keys=True
        ),
        **flat_settings(document),
    }


def publish(endpoint: str, settings: Mapping[str, str]) -> None:
    """Write every key under ``agent-lz``. ``kv set`` overwrites, so re-runs converge."""
    from config.deployment.appconfig import _run_az

    for key, value in settings.items():
        _run_az(
            [
                "appconfig", "kv", "set",
                "--endpoint", endpoint,
                "--key", key,
                "--value", value,
                "--label", APP_CONFIG_LABEL,
                "--content-type",
                "application/json" if key == PLATFORM_OUTPUTS_KEY else "text/plain",
                "--auth-mode", "login",
                "--yes",
                "--output", "none",
            ],
            required=False,
        )


def main(argv: list[str] | None = None) -> int:
    from config.appdefinition import AppDefinitionError, load_selected_definition, validate_definition
    from config.appdefinition.roles import RoleAssignmentError, discover_component_identities
    from config.deployment.composition import DeploymentMode, DeploymentTopologyError, resolve_mode

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check-foundation",
        action="store_true",
        help="Only verify that azd provision has run (azd deploy guard).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the settings without writing them.",
    )
    args = parser.parse_args(argv)
    try:
        require_foundation(os.environ)
        if args.check_foundation:
            return 0
        identities = None
        if not (os.environ.get(IDENTITIES_ENV) or "").strip():
            definition = validate_definition(load_selected_definition(os.environ))
            identities = discover_component_identities(
                definition, os.environ,
                hosted_orchestration=resolve_mode(os.environ) is not DeploymentMode.CLASSIC,
            )
        document = build_platform_outputs(os.environ, identities)
        validate_platform_outputs(document)
    except (FoundationMissingError, PlatformOutputsError, AppDefinitionError,
            RoleAssignmentError, DeploymentTopologyError) as error:
        print(str(error), file=sys.stderr)
        return 1
    settings = platform_settings(document)
    if args.dry_run:
        print(json.dumps(settings, indent=2))
        return 0
    publish(os.environ["APP_CONFIG_ENDPOINT"].strip(), settings)
    print(f"Published {len(settings)} platform output keys (label {APP_CONFIG_LABEL}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
