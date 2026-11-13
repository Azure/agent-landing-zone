#!/usr/bin/env python3
"""
Configure RAI and evaluation secrets using verified deployment settings.

The selected foundation must expose deployment metadata and the original typed
declarations must be available. Azure CLI or managed identity authentication
and the local RAI JSON definitions are required. No runtime store is used for
discovery. Evaluation API-key injection requires a selected vault when local
authentication is enabled; Entra-only accounts never request an API key.
"""

import os
import sys
import json
import logging
from typing import Any, Dict, Optional

from azure.identity import AzureCliCredential, ManagedIdentityCredential, ChainedTokenCredential
from azure.core.exceptions import ClientAuthenticationError, ResourceNotFoundError
from azure.appconfiguration import AzureAppConfigurationClient
from config.deployment.setup_settings import load_setup_settings
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.mgmt.cognitiveservices.models import (
    RaiBlocklist,
    RaiBlocklistProperties,
    RaiBlocklistItem,
    RaiBlocklistItemProperties
)
from .keyvault import KeyVaultClient
from config.deployment.resource_groups import resource_group_for
from config.deployment.context import bound_resource_id

# ── Constants ─────────────────────────────────────────
REQUIRED_ENV_VARS = ["APP_CONFIG_ENDPOINT"]
BLOCKLIST_NAME = "agentlzBlocklist"
POLICY_NAME = "agentlzRAIPolicy"
RAI_POLICIES_JSON_FILE = "config/aifoundry/raipolicies.json"
RAI_BLOCKLIST_JSON_FILE = "config/aifoundry/raiblocklist.json"
CANONICAL_DEPLOYMENT_NAME = "CHAT_DEPLOYMENT_NAME"
SECRET_NAME = "evaluationsModelApiKey"

# ── Logging ───────────────────────────────────────────
def configure_logging():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for logger_name in (
        "azure.core.pipeline.policies.http_logging_policy",
        "azure.identity",
        "azure.mgmt"
    ):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

# ── Environment Validation ────────────────────────────
def check_env() -> None:
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        logging.error("❗️ Missing environment variables:")
        for name in missing:
            logging.error("  • %s", name)
        sys.exit(1)

# ── Azure App Config Helper ───────────────────────────
def cfg(client: AzureAppConfigurationClient, key: str, label: str = 'agent-lz', required: bool = True) -> str:
    """Fetch a single value from App Configuration; exit if missing or empty."""
    try:
        setting = client.get_configuration_setting(key=key, label=label)
    except ResourceNotFoundError:
        if not required:
            return ""
        logging.error("❗️ Key '%s' not found in App Configuration", key)
        sys.exit(1)
    except Exception as e:
        logging.error("❗️ Could not fetch key '%s': %s", key, e)
        sys.exit(1)
    if required and (setting is None or not setting.value):
        logging.error("❗️ Key '%s' not found or empty in App Configuration", key)
        sys.exit(1)
    return setting.value


def foundry_resource_group(client: AzureAppConfigurationClient) -> str:
    context = {
        "AZURE_RESOURCE_GROUP": cfg(client, "AZURE_RESOURCE_GROUP"),
        "AZURE_FOUNDRY_RESOURCE_GROUP": cfg(client, "AZURE_FOUNDRY_RESOURCE_GROUP", required=False),
    }
    group = resource_group_for(context, "foundry")
    declared = (os.environ.get("AZURE_RESOURCE_GROUP") or "").strip()
    if declared and group.lower() != declared.lower():
        raise ValueError("App Configuration Foundry destination conflicts with the deployment environment.")
    return group

# ── JSON File Utilities ───────────────────────────────
def load_and_replace(path: str, replacements: Dict[str, str]) -> Dict[str, Any]:
    """Load a JSON file, apply replacements, and parse it."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        logging.error("❗️ Unable to open %s: %s", path, e)
        sys.exit(1)
    for ph, val in replacements.items():
        raw = raw.replace(ph, val)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logging.error("❗️ Failed to parse JSON in %s: %s", path, e)
        sys.exit(1)

def validate_json_file(path: str) -> None:
    """Validate that a JSON file exists, is readable, and is valid JSON."""
    if not os.path.exists(path):
        logging.error(f"❗️ File not found: {path!r}. Aborting configuration.")
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logging.error(f"❗️ Unable to read {path!r}: {e}. Aborting configuration.")
        sys.exit(1)
    if not content.strip():
        logging.error(f"❗️ File is empty: {path!r}. Aborting configuration.")
        sys.exit(1)
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        logging.error(f"❗️ Invalid JSON in {path!r}: {e}. Aborting configuration.")
        sys.exit(1)

# ── Azure Authentication ──────────────────────────────
def get_azure_credential() -> ChainedTokenCredential:
    """Get Azure credential (Managed Identity preferred, fallback to CLI)."""
    return ChainedTokenCredential(
                AzureCliCredential(process_timeout=30),
                ManagedIdentityCredential(process_timeout=30)
            )

# ── Key Vault Helper ─────────────────────────────────
def add_ai_foundry_account_api_key_to_key_vault(
    mgmt_client: CognitiveServicesManagementClient,
    resource_group: str,
    account_name: str,
    vault_uri: str,
    secret_name: str
) -> bool:
    """Store an evaluation API key only when the account allows local authentication."""
    try:
        account = mgmt_client.accounts.get(resource_group, account_name)
        if account.properties.disable_local_auth is True:
            logging.info(
                "Local authentication is disabled for account %s; "
                "evaluation API-key injection is not applicable. Use Microsoft Entra ID.",
                account_name,
            )
            return False
        if not vault_uri:
            raise ValueError("Foundry evaluation API-key injection requires a selected Key Vault.")
        logging.info("🔑 Fetching AI Foundry Account API key for account %s ...", account_name)
        keys = mgmt_client.accounts.list_keys(resource_group, account_name)
        api_key = keys.key1
        if not api_key:
            raise ValueError("The Foundry account returned an empty evaluation API key.")
        logging.info("🔒 Storing API key in Key Vault at %s ...", vault_uri)
        kv_client = KeyVaultClient(vault_uri)
        kv_client.set_secret(secret_name, api_key)
        logging.info("✅ Secret %s set successfully in Key Vault.", secret_name)
        return True
    except Exception as e:
        logging.error("❗️ Failed to set secret in Key Vault: %s", e)
        sys.exit(1)

# ── Blocklist Logic ──────────────────────────────────
def configure_blocklist(client: CognitiveServicesManagementClient, resource_group: str, account_name: str, bl_def: Dict[str, Any], bl_name: str) -> None:
    """Create or update the RAI blocklist and its items."""
    try:
        logging.info(f"📑 Creating/updating blocklist {bl_name} …")
        client.rai_blocklists.create_or_update(
            resource_group_name=resource_group,
            account_name=account_name,
            rai_blocklist_name=bl_name,
            rai_blocklist=RaiBlocklist(
                properties=RaiBlocklistProperties(
                    description=bl_def.get("description", "")
                )
            )
        )
        # Remove existing items
        for existing in client.rai_blocklist_items.list(resource_group, account_name, bl_name):
            logging.info(f"🗑️ Deleting blocklist item: {existing.name}")
            client.rai_blocklist_items.delete(
                resource_group_name=resource_group,
                account_name=account_name,
                rai_blocklist_name=bl_name,
                rai_blocklist_item_name=existing.name
            )
        # Re-add items
        for idx, item in enumerate(bl_def.get("blocklistItems", [])):
            pat = item.get("pattern", "") or ""
            if not pat.strip():
                logging.warning(f"⚠️ Skipping blocklist item {idx}: empty pattern")
                continue
            item_name = f"{bl_name}Item{idx}"
            logging.info(f"➕ Adding blocklist item {item_name} …")
            client.rai_blocklist_items.create_or_update(
                resource_group_name=resource_group,
                account_name=account_name,
                rai_blocklist_name=bl_name,
                rai_blocklist_item_name=item_name,
                rai_blocklist_item=RaiBlocklistItem(
                    properties=RaiBlocklistItemProperties(
                        pattern=pat,
                        is_regex=item.get("isRegex", False)
                    )
                )
            )
    except Exception as e:
        logging.error(f"❗️ Blocklist configuration failed: {e}")
        sys.exit(1)

# ── Policy Logic ─────────────────────────────────────
def configure_policy(client: CognitiveServicesManagementClient, resource_group: str, account_name: str, pol_def: Dict[str, Any], bl_name: str, policy_name: str) -> str:
    """Create or update the RAI policy and return its name."""
    try:
        p_name = pol_def.get("name")
        if not p_name:
            logging.error("❗️ Policy JSON must have top-level 'name'.")
            sys.exit(1)
        props = pol_def["properties"]
        prompt_bl = props.pop("promptBlocklists", [])
        comp_bl = props.pop("completionBlocklists", [])
        for x in prompt_bl: x["source"] = "Prompt"
        for x in comp_bl: x["source"] = "Completion"
        props["customBlocklists"] = prompt_bl + comp_bl
        # Normalize casing
        for f in props.get("contentFilters", []):
            if "allowedContentLevel" in f:
                lvl = f.pop("allowedContentLevel")
                f["severityThreshold"] = lvl.capitalize()
            if "source" in f:
                f["source"] = f["source"].capitalize()
        if "mode" in props:
            props["mode"] = props["mode"].capitalize()
        logging.info(f"📑 Creating/updating policy {p_name} …")
        client.rai_policies.create_or_update(
            resource_group_name=resource_group,
            account_name=account_name,
            rai_policy_name=p_name,
            rai_policy={"properties": props}
        )
        return p_name
    except Exception as e:
        logging.error(f"❗️ Policy configuration failed: {e}")
        sys.exit(1)

# ── Deployment Association ───────────────────────────
def associate_policy_to_deployment(client: CognitiveServicesManagementClient, resource_group: str, account_name: str, deployment_name: str, policy_name: str) -> None:
    """Associate the RAI policy to the deployment."""
    try:
        logging.info(f"🔗 Associating policy {policy_name} with deployment {deployment_name} …")
        existing = client.deployments.get(resource_group, account_name, deployment_name)
        dep_dict = existing.as_dict()
        dep_dict["properties"]["raiPolicyName"] = policy_name
        client.deployments.begin_create_or_update(
            resource_group_name=resource_group,
            account_name=account_name,
            deployment_name=deployment_name,
            deployment=dep_dict
        ).result()
    except Exception as e:
        logging.error(f"❗️ Failed to associate policy to deployment: {e}")
        sys.exit(1)

# ── Main Logic ───────────────────────────────────────
def main() -> None:
    configure_logging()
    settings = load_setup_settings()
    if settings.get("DEPLOY_AI_FOUNDRY") == "false":
        logging.info("Foundry account setup is not selected.")
        return
    validate_json_file(RAI_POLICIES_JSON_FILE)
    validate_json_file(RAI_BLOCKLIST_JSON_FILE)
    cred = get_azure_credential()
    subscription_id = settings["SUBSCRIPTION_ID"]
    resource_group = resource_group_for(settings, "foundry")
    account_name = settings["AI_FOUNDRY_ACCOUNT_NAME"]
    account_id = settings.get("AI_FOUNDRY_ACCOUNT_RESOURCE_ID")
    if account_id:
        context = bound_resource_id(account_id, {
            "AZURE_SUBSCRIPTION_ID": subscription_id,
            "AZURE_RESOURCE_GROUP": resource_group,
        }, "Microsoft.CognitiveServices/accounts", area="application")
        if context.name.lower() != account_name.lower():
            raise ValueError("Foundry account name and ARM ID conflict.")
    logging.info(f"Loaded: subscriptionId={subscription_id}, resourceGroupName={resource_group}")
    logging.info(f"Loaded: aiFoundryAccountName={account_name}")
    # Determine deployment name from list when local model deployments are enabled
    deploy_model_deployments = (
        str(settings.get("DEPLOY_MODEL_DEPLOYMENTS", "true")).strip().lower() != "false"
    )
    raw_list = settings["MODEL_DEPLOYMENTS"] if deploy_model_deployments else settings.get("MODEL_DEPLOYMENTS", [])
    try:
        deployments = json.loads(raw_list) if isinstance(raw_list, str) else raw_list
    except json.JSONDecodeError as e:
        logging.error("MODEL_DEPLOYMENTS is not valid JSON: %s", e)
        sys.exit(1)
    if not isinstance(deployments, list):
        logging.error("MODEL_DEPLOYMENTS must be a JSON array")
        sys.exit(1)
    deployment_name: Optional[str] = None
    if deploy_model_deployments:
        for canonical_name in (CANONICAL_DEPLOYMENT_NAME, "GPT_MODEL"):
            for item in deployments:
                if item.get("canonical_name") == canonical_name:
                    deployment_name = item.get("name")
                    break
            if deployment_name:
                break
        if not deployment_name:
            logging.error(
                "No deployment with canonical_name '%s' or 'GPT_MODEL' found in MODEL_DEPLOYMENTS",
                CANONICAL_DEPLOYMENT_NAME
            )
            sys.exit(1)
        logging.info(f"Selected deployment: {deployment_name} (canonical_name={canonical_name})")
    client = CognitiveServicesManagementClient(cred, subscription_id)
    if not settings.get("KEY_VAULT_URI"):
        account = client.accounts.get(resource_group, account_name)
        if account.properties.disable_local_auth is not True:
            raise RuntimeError("Foundry evaluation API-key injection requires a selected Key Vault.")
    # Blocklist
    bl_def = load_and_replace(
        RAI_BLOCKLIST_JSON_FILE,
        {"{{BlocklistName}}": BLOCKLIST_NAME}
    )
    bl_name = bl_def.get("name") or bl_def.get("blocklistname")
    if not bl_name:
        logging.error("❗️ Blocklist JSON must have top-level 'name' or 'blocklistname'.")
        sys.exit(1)
    configure_blocklist(client, resource_group, account_name, bl_def, bl_name)
    # Policy
    pol_def = load_and_replace(
        RAI_POLICIES_JSON_FILE,
        {
            "{{PolicyName}}": POLICY_NAME,
            "{{BlocklistName}}": bl_name
        }
    )
    p_name = configure_policy(client, resource_group, account_name, pol_def, bl_name, POLICY_NAME)
    # Associate policy to deployment when local model deployments are enabled
    if deployment_name:
        associate_policy_to_deployment(client, resource_group, account_name, deployment_name, p_name)
    else:
        logging.info(
            "Local model deployments are disabled (DEPLOY_MODEL_DEPLOYMENTS=false). "
            "Skipping RAI policy association to a local deployment while account-level "
            "RAI blocklist and policy remain configured."
        )
    # Store API key in Key Vault
    logging.info("🔑 Adding AI Foundry Account API Key to Key Vault …")
    key_vault_uri = settings.get("KEY_VAULT_URI")
    secret_stored = add_ai_foundry_account_api_key_to_key_vault(
        client,
        resource_group,
        account_name,
        key_vault_uri,
        SECRET_NAME
    )
    if deployment_name:
        logging.info("✅ RAI blocklist, policy, and deployment association complete.")
    else:
        logging.info("✅ Account-level RAI blocklist and policy configuration complete.")
    if secret_stored:
        logging.info("✅ Evaluation API-key injection complete.")

if __name__ == "__main__":
    main()
