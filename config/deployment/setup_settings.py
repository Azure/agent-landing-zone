"""Resolve setup intent against verified resources, without store discovery."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Mapping

from config.deployment.appconfig_intent import normalize_settings
from config.deployment.metadata import MetadataError, VerifiedMetadata, aliases, load_metadata

# These are operational preferences, not destination or identity authority.
PREFERENCE_KEYS = frozenset("""
FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED FOUNDRY_IQ_CONVERSATION_KNOWLEDGE_SOURCE_NAME
WORK_IQ_ENABLED WORK_IQ_KNOWLEDGE_SOURCE_NAME WORK_IQ_APPLICATION_ID
WORK_IQ_FEDERATED_CREDENTIAL_ID WORK_IQ_TENANT_ID
FABRIC_IQ_ENABLED FABRIC_IQ_KNOWLEDGE_SOURCE_NAME FABRIC_IQ_WORKSPACE_ID FABRIC_IQ_ONTOLOGY_ID
FABRIC_DATA_AGENT_ENABLED FABRIC_DATA_AGENT_KNOWLEDGE_SOURCE_NAME FABRIC_DATA_AGENT_WORKSPACE_ID
FABRIC_DATA_AGENT_DATA_AGENT_ID SHAREPOINT_INDEXED_ENABLED SHAREPOINT_INDEXED_KNOWLEDGE_SOURCE_NAME
SHAREPOINT_INDEXED_INDEX_NAME SHAREPOINT_INDEXED_SITE_URL SHAREPOINT_INDEXED_TENANT_ID
SHAREPOINT_INDEXED_APPLICATION_ID SHAREPOINT_INDEXED_FEDERATED_CREDENTIAL_APPLICATION_ID
WEB_GROUNDING_ENABLED WEB_GROUNDING_KNOWLEDGE_SOURCE_NAME WEB_GROUNDING_ALLOWED_DOMAINS
WEB_GROUNDING_BLOCKED_DOMAINS FOUNDRY_IQ_MCP_ENABLED FOUNDRY_IQ_MCP_SOURCES_JSON
FOUNDRY_IQ_MCP_REASONING_EFFORT FOUNDRY_IQ_MCP_TRUSTED_HOSTS FOUNDRY_IQ_MCP_LOG_TOOL_ARGUMENTS
RETRIEVAL_AUTH_MODE HOSTED_AGENT_AUTH_MODE FOUNDRY_IQ_FORWARD_SOURCE_AUTH ALLOW_ANONYMOUS
AUDIT_EVENTS_ENABLED AUDIT_SENSITIVE_CONTENT_ENABLED AUDIT_SENSITIVE_CONTENT_FIELDS
AUDIT_ACTOR_PSEUDONYM_ENABLED AUDIT_SOURCE_EVENT_LIMIT AUDIT_HMAC_KEY_ID
AUDIT_ADDITIONAL_REDACTED_KEYS INGESTION_PROVENANCE_ENABLED INGESTION_REQUIRE_GOVERNANCE_METADATA
INGESTION_DEFAULT_CLASSIFICATION INGESTION_DEFAULT_RIGHT_TO_USE
""".split())

INPUTS = {
    "location": "LOCATION", "resourceToken": "RESOURCE_TOKEN", "useUAI": "USE_UAI",
    "useCAppAPIKey": "USE_CAPP_API_KEY", "networkIsolation": "NETWORK_ISOLATION",
    "deployAppConfig": "DEPLOY_APP_CONFIG", "deploySoftware": "DEPLOY_SOFTWARE",
    "deployAiFoundry": "DEPLOY_AI_FOUNDRY", "deployAfProject": "DEPLOY_AF_PROJECT",
    "deployKeyVault": "DEPLOY_KEY_VAULT", "deployLogAnalytics": "DEPLOY_LOG_ANALYTICS",
    "deployAppInsights": "DEPLOY_APP_INSIGHTS", "deploySearchService": "DEPLOY_SEARCH_SERVICE",
    "deploySpeechService": "DEPLOY_SPEECH_SERVICE", "deployStorageAccount": "DEPLOY_STORAGE_ACCOUNT",
    "deployCosmosDb": "DEPLOY_COSMOS_DB", "deployContainerApps": "DEPLOY_CONTAINER_APPS",
    "deployContainerRegistry": "DEPLOY_CONTAINER_REGISTRY", "deployContainerEnv": "DEPLOY_CONTAINER_ENV",
    "deployVmKeyVault": "DEPLOY_VM_KEY_VAULT", "retrievalBackend": "RETRIEVAL_BACKEND",
    "enableAgenticRetrieval": "ENABLE_AGENTIC_RETRIEVAL", "foundryIqPattern": "FOUNDRY_IQ_PATTERN",
    "foundryIqApiVersion": "FOUNDRY_IQ_API_VERSION",
    "foundryIqKnowledgeSourceName": "FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME",
    "foundryIqKnowledgeSourceKind": "FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND",
    "foundryIqStorageContainerName": "FOUNDRY_IQ_STORAGE_CONTAINER_NAME",
    "foundryIqStorageFolderPath": "FOUNDRY_IQ_STORAGE_FOLDER_PATH",
    "foundryIqIsAdlsGen2": "FOUNDRY_IQ_IS_ADLS_GEN2",
    "foundryIqContentExtractionMode": "FOUNDRY_IQ_CONTENT_EXTRACTION_MODE",
    "foundryIqIngestionPermissionOptions": "FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS",
    "foundryIqIngestionPermissionOptionsJson": "FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS",
    "foundryIqSecurityFieldName": "FOUNDRY_IQ_SECURITY_FIELD_NAME",
    "foundryIqMaxOutputDocuments": "FOUNDRY_IQ_MAX_OUTPUT_DOCUMENTS",
    "foundryIqFilterAddOnEnabled": "FOUNDRY_IQ_FILTER_ADD_ON_ENABLED",
    "foundryIqKnowledgeRetrievalBillingPlan": "FOUNDRY_IQ_KNOWLEDGE_RETRIEVAL_BILLING_PLAN",
    "foundryIqAiServicesEndpoint": "FOUNDRY_IQ_AI_SERVICES_ENDPOINT",
    "searchRagIndexName": "SEARCH_RAG_INDEX_NAME", "knowledgeBaseName": "KNOWLEDGE_BASE_NAME",
    "applicationMode": "APPLICATION_MODE", "orchestrationHost": "ORCHESTRATION_HOST",
    "deployIngestionContainerApp": "DEPLOY_INGESTION_CONTAINER_APP",
    "deployAgentAppMcp": "DEPLOY_AGENT_APP_MCP", "mcpToolsets": "MCP_TOOLSETS",
    "enableChatHistory": "ENABLE_CHAT_HISTORY", "enableUserFeedback": "ENABLE_USER_FEEDBACK",
    "enablePrivateAttachments": "ENABLE_PRIVATE_ATTACHMENTS",
    "nativeUiMetadataContainer": "NATIVE_UI_METADATA_CONTAINER",
}


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


def resolve_setup_settings(verified: VerifiedMetadata) -> dict[str, object]:
    """Adapt only declared setup intent and evaluated resource bindings."""
    document, parameters = verified.document, verified.parameters
    settings: dict[str, object] = dict(aliases(document))
    mode = document["context"]["runtimeConfigurationMode"]
    if mode != "appConfig":
        settings.pop("APP_CONFIG_ENDPOINT", None)
    elif document["resources"]["appConfig"]["status"] == "disabled":
        raise MetadataError("prerequisite.appConfig: appConfig mode requires the verified store.")
    if parameters.get("deployAgentAppMcp") is True and mode != "appConfig":
        raise MetadataError("prerequisite.mcp: Selected bundled MCP requires appConfig state and publication.")
    for parameter, name in INPUTS.items():
        if parameter in parameters:
            settings[name] = _text(parameters[parameter])
    for slot, name in (
        ("foundryAccount", "DEPLOY_AI_FOUNDRY"),
        ("foundryProject", "DEPLOY_AF_PROJECT"),
        ("search", "DEPLOY_SEARCH_SERVICE"),
    ):
        settings.setdefault(name, _text(document["resources"][slot]["status"] != "disabled"))
    if not parameters.get("resourceToken") and verified.environment.get("RESOURCE_TOKEN"):
        settings["RESOURCE_TOKEN"] = verified.environment["RESOURCE_TOKEN"]
    settings["MODEL_DEPLOYMENTS"] = [
        {
            "canonical_name": row["canonicalName"], "name": row["name"],
            "id": row["resourceId"], "model": dict(row["model"]),
            "api_version": row["apiVersion"], "endpoint": row["endpoint"],
        }
        for row in document["modelDeployments"]
    ]
    settings["CONTAINER_APPS"] = [
        {
            "canonical_name": row["canonicalName"], "service_name": row["serviceName"],
            "id": row["resourceId"], "name": row["name"], "fqdn": row["fqdn"],
            "identity": dict(row["identity"]),
        }
        for row in document["containerApps"]
    ]
    search_identity = (
        verified.live_resources.get("search", {}).get("identity") or {}
    ).get("userAssignedIdentities") or {}
    if len(search_identity) == 1:
        settings["SEARCH_SERVICE_UAI_RESOURCE_ID"] = next(iter(search_identity))
    elif search_identity:
        raise MetadataError("resources.search.identity: Ambiguous Search identity association. Select one identity.")
    databases = document["dataResources"]["cosmosDatabases"]
    if len(databases) == 1:
        settings["DATABASE_NAME"] = databases[0]["name"]
        settings["MCP_COSMOS_DATABASE"] = databases[0]["name"]
    if "COSMOS_DB_ENDPOINT" in settings:
        settings["MCP_COSMOS_ENDPOINT"] = settings["COSMOS_DB_ENDPOINT"]
    if (
        settings.get("RETRIEVAL_BACKEND") == "foundry_iq"
        and settings.get("SEARCH_SERVICE_QUERY_ENDPOINT")
        and settings.get("AI_FOUNDRY_PROJECT_RESOURCE_ID")
    ):
        name = parameters.get("knowledgeBaseName")
        connection = parameters.get("knowledgeBaseConnectionName")
        if not all(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in (name, connection)):
            raise MetadataError("prerequisite.knowledgeBase: Restore declared knowledge base and connection names.")
        settings["KNOWLEDGE_BASE_ENDPOINT"] = settings["SEARCH_SERVICE_QUERY_ENDPOINT"]
        settings["KNOWLEDGE_BASE_CONNECTION_ID"] = settings["AI_FOUNDRY_PROJECT_RESOURCE_ID"] + "/connections/" + connection
        settings["TOOLBOX_ENDPOINT"] = settings["AI_FOUNDRY_PROJECT_ENDPOINT"].rstrip("/") + "/toolboxes/" + name + "/mcp?api-version=v1"
    if settings.get("KEY_VAULT_URI"):
        settings["AUDIT_HMAC_KEY_URI"] = str(settings["KEY_VAULT_URI"]).rstrip("/") + "/secrets/AUDIT-HMAC-KEY"
    try:
        entries = normalize_settings(parameters.get("additionalAppConfigurationSettings", []))
    except ValueError:
        raise MetadataError("intent.settings: Invalid declared operational settings.") from None
    for entry in entries:
        if entry["label"] != "agent-lz":
            continue
        name, value = entry["name"], entry["value"]
        if name in settings:
            if _text(settings[name]) != value:
                raise MetadataError(f"intent.{name}: Declared setting conflicts with verified authority.")
        elif name in PREFERENCE_KEYS:
            if entry["contentType"] not in ("text/plain", "application/json"):
                raise MetadataError(f"intent.{name}: Operational preferences cannot contain secret references.")
            settings[name] = value
    for name in ("LOG_LEVEL", "CONTAINER_APP_MAX_WORKERS", "CONTAINER_APP_POLL_TIMEOUT_SECONDS"):
        if name in verified.environment:
            settings[name] = verified.environment[name]
    return settings


def load_setup_settings(
    environment: Mapping[str, str] | None = None, *, project_root: Path | None = None,
    input_path: Path | None = None,
) -> dict[str, object]:
    """Revalidate the selected native output on every independent invocation."""
    return resolve_setup_settings(load_metadata(
        environment, project_root=project_root, input_path=input_path,
    ))


def load_setup_environment(
    environment: Mapping[str, str] | None = None, *, project_root: Path | None = None,
    input_path: Path | None = None,
) -> dict[str, str]:
    """Provide string-valued adapters for existing deployment CLI consumers."""
    verified = load_metadata(environment, project_root=project_root, input_path=input_path)
    settings = resolve_setup_settings(verified)
    values = {**verified.environment, **{name: _text(value) for name, value in settings.items()}}
    if settings["APP_RUNTIME_CONFIGURATION_MODE"] != "appConfig":
        values.pop("APP_CONFIG_ENDPOINT", None)
    return values
