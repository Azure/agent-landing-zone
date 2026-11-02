"""Typed selection and Cosmos contracts for the optional MCP component."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from config.deployment.native import boolean

DEPLOY_AGENT_APP_MCP = "DEPLOY_AGENT_APP_MCP"
MCP_COMPONENT = "agent-app-mcp"
MCP_SERVICE = "mcp"


def selected(environment: Mapping[str, str]) -> bool:
    return boolean(environment, DEPLOY_AGENT_APP_MCP)


def retained_catalog(environment: Mapping[str, str]) -> bool:
    # The shared hook persists catalog ownership independently of the server.
    return boolean(environment, "COSMOS_VECTOR_SEARCH_ENABLED")


def vector_required(environment: Mapping[str, str]) -> bool:
    return selected(environment) or retained_catalog(environment)


def settings(environment: Mapping[str, str]) -> dict[str, str]:
    result = {
        DEPLOY_AGENT_APP_MCP: str(selected(environment)).lower(),
        "MCP_SOURCES_CONTAINER": environment.get(
            "MCP_SOURCES_CONTAINER", "mcp-sources"
        ),
        "MCP_METADATA_CONTAINER": environment.get(
            "MCP_METADATA_CONTAINER", "mcp-nl2sql-metadata"
        ),
        "MCP_EMBEDDING_DIMENSIONS": environment.get("MCP_EMBEDDING_DIMENSIONS", "3072"),
        "MCP_QUERY_TIMEOUT_SECONDS": environment.get("MCP_QUERY_TIMEOUT_SECONDS", "75"),
        "MCP_METADATA_TOP_K": environment.get("MCP_METADATA_TOP_K", "8"),
        "MCP_SQL_SECRET_NAMES": environment.get("MCP_SQL_SECRET_NAMES", "[]"),
    }
    for key in ("MCP_SOURCES_CONTAINER", "MCP_METADATA_CONTAINER"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,254}", result[key]):
            raise ValueError(f"{key} must be a valid Cosmos container name.")
    if result["MCP_SOURCES_CONTAINER"] == result["MCP_METADATA_CONTAINER"]:
        raise ValueError("MCP source and vector metadata containers must be distinct.")
    for key, minimum, maximum in (
        ("MCP_EMBEDDING_DIMENSIONS", 1, 4096),
        ("MCP_QUERY_TIMEOUT_SECONDS", 31, 300),
        ("MCP_METADATA_TOP_K", 1, 32),
    ):
        value = result[key]
        if not value.isdecimal() or not minimum <= int(value) <= maximum:
            raise ValueError(
                f"{key} must be an integer between {minimum} and {maximum}."
            )
    secrets = json.loads(result["MCP_SQL_SECRET_NAMES"])
    if not isinstance(secrets, list) or any(
        not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,127}", name)
        for name in secrets
    ):
        raise ValueError(
            "MCP_SQL_SECRET_NAMES must contain only declared Key Vault secret names."
        )
    return result


def cosmos_containers(environment: Mapping[str, str]) -> list[dict[str, object]]:
    if not vector_required(environment):
        return []
    values = settings(environment)
    return [
        {
            "name": values["MCP_SOURCES_CONTAINER"],
            "canonical_name": "MCP_SOURCES_CONTAINER",
            "partitionKey": "/source_id",
        },
        {
            "name": values["MCP_METADATA_CONTAINER"],
            "canonical_name": "MCP_METADATA_CONTAINER",
            "partitionKey": "/source_id",
            "vectorEmbeddingPolicy": {
                "vectorEmbeddings": [
                    {
                        "path": "/embedding",
                        "dataType": "float32",
                        "distanceFunction": "cosine",
                        "dimensions": int(values["MCP_EMBEDDING_DIMENSIONS"]),
                    }
                ]
            },
            "indexingPolicy": {
                "indexingMode": "consistent",
                "automatic": True,
                "includedPaths": [{"path": "/*"}],
                "excludedPaths": [{"path": "/embedding/*"}],
                "vectorIndexes": [{"path": "/embedding", "type": "quantizedFlat"}],
            },
        },
    ]


def account_capabilities(environment: Mapping[str, str]) -> list[str]:
    capabilities = json.loads(
        environment.get("COSMOS_ACCOUNT_CAPABILITIES", '["EnableServerless"]')
    )
    if not isinstance(capabilities, list) or any(
        not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]+", name)
        for name in capabilities
    ):
        raise ValueError(
            "COSMOS_ACCOUNT_CAPABILITIES must be an array of capability names."
        )
    return list(
        dict.fromkeys(
            [
                "EnableServerless",
                *capabilities,
                *(["EnableNoSQLVectorSearch"] if vector_required(environment) else []),
            ]
        )
    )


def consumer_settings(
    environment: Mapping[str, str], endpoint: str, scope: str
) -> dict[str, str]:
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/mcp")
    ):
        raise ValueError(
            "The provisioned MCP endpoint must be an HTTPS service endpoint."
        )
    previous = environment.get("MCP_APP_ENDPOINT", "").rstrip("/")
    if previous and previous.removesuffix("/mcp") != endpoint.rstrip("/").removesuffix(
        "/mcp"
    ):
        raise ValueError(
            "Agent App MCP conflicts with an existing external MCP endpoint. Select one explicitly."
        )
    timeout = int(environment.get("MCP_CLIENT_TIMEOUT", "90"))
    if timeout <= int(settings(environment)["MCP_QUERY_TIMEOUT_SECONDS"]):
        raise ValueError(
            "MCP_CLIENT_TIMEOUT must exceed the complete MCP query deadline."
        )
    return {
        "MCP_ENABLED": "true",
        "MCP_APP_ENDPOINT": endpoint,
        "MCP_AUTH_RESOURCE_SCOPE": scope,
        "MCP_SERVER_TRANSPORT": "streamable-http",
        "MCP_TRUSTED_HOSTS": json.dumps([parsed.hostname]),
        "MCP_CLIENT_TIMEOUT": str(timeout),
    }
