#!/usr/bin/env python3
"""
Simple script to associate each Container App from App Configuration
with Azure Container Registry (ACR) via its system-assigned or user-assigned identity.

Prerequisites:
- Export the environment variable APP_CONFIG_ENDPOINT with your Azure App Configuration endpoint, e.g.:
    export APP_CONFIG_ENDPOINT="https://<your-app-config-name>.azconfig.io"
- The following keys must be present in App Configuration (label: agent-lz):
    - SUBSCRIPTION_ID
    - AZURE_RESOURCE_GROUP
    - AZURE_APP_RESOURCE_GROUP (optional; defaults to AZURE_RESOURCE_GROUP)
    - CONTAINER_REGISTRY_NAME
    - USE_UAI
    - CONTAINER_APPS (JSON list)
- Azure CLI or Managed Identity authentication must be available.

This script will:
- Read container app definitions from Azure App Configuration.
- For each app, associate the specified Azure Container Registry (ACR) using either system-assigned or user-assigned identity.
- Update the registry configuration for each Container App in Azure (parallelized).
"""

import os
import sys
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from azure.identity import (
    ManagedIdentityCredential,
    AzureCliCredential,
    ChainedTokenCredential
)
from azure.appconfiguration import AzureAppConfigurationClient
from azure.mgmt.appcontainers import ContainerAppsAPIClient
from azure.core.exceptions import ResourceNotFoundError

from config.deployment.resource_groups import resource_group_for


POLL_TIMEOUT_SECONDS = int(os.getenv("CONTAINER_APP_POLL_TIMEOUT_SECONDS", "600"))
MAX_WORKERS = int(os.getenv("CONTAINER_APP_MAX_WORKERS", "2"))   

def _get_desired_identity(app, app_name, use_uai):
    """Return the identity string/resource id we expect to use for registry auth."""
    logging.debug(f"[{app_name}] Checking identity configuration. USE_UAI={use_uai}")
    
    if use_uai.lower() == "true":
        logging.debug(f"[{app_name}] Using User-Assigned Identity (UAI)")
        uai_dict = getattr(app.identity, "user_assigned_identities", None)
        
        if not uai_dict:
            logging.error(f"[{app_name}] No user-assigned identity found for app.")
            return None
        
        identity_id = next(iter(uai_dict.keys()), None)
        logging.debug(f"[{app_name}] Found UAI: {identity_id}")
        return identity_id
    
    logging.debug(f"[{app_name}] Using System-Assigned Identity")
    return "system"


def _registry_matches(app, server, desired_identity):
    registries = getattr(app.configuration, "registries", None) or []
    logging.debug(f"Checking {len(registries)} existing registries for server '{server}'")
    
    for idx, reg in enumerate(registries):
        reg_server = reg.get("server") if isinstance(reg, dict) else getattr(reg, "server", None)
        reg_identity = reg.get("identity") if isinstance(reg, dict) else getattr(reg, "identity", None)
        
        logging.debug(f"  Registry [{idx}]: server={reg_server}, identity={reg_identity}")
        
        if reg_server != server:
            continue
        
        if desired_identity == "system" and reg_identity in (None, "system"):
            logging.debug(f"  ✓ Match found: server={reg_server}, identity=system")
            return True
        
        if desired_identity and reg_identity == desired_identity:
            logging.debug(f"  ✓ Match found: server={reg_server}, identity={reg_identity}")
            return True
    
    logging.debug(f"  ✗ No matching registry found for server '{server}' with identity '{desired_identity}'")
    return False


def configure_logging():
    """Configure logging for Azure SDKs and the script."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, log_level, logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Suppress verbose Azure SDK logs unless DEBUG is set
    azure_log_level = logging.DEBUG if log_level == "DEBUG" else logging.WARNING
    for logger_name in (
        "azure.core.pipeline.policies.http_logging_policy",
        "azure.identity",
        "azure.appconfiguration",
        "azure.mgmt.appcontainers",
    ):
        logging.getLogger(logger_name).setLevel(azure_log_level)
    
    logging.info(f"Logging configured at level: {log_level}")


def get_credentials():
    """Return a ChainedTokenCredential for Azure authentication (CLI → ManagedIdentity)."""
    logging.info("🔐 Creating ChainedTokenCredential (CLI → ManagedIdentity)...")
    
    try:
        # Create chained credential with CLI first, then Managed Identity
        credential = ChainedTokenCredential(
            AzureCliCredential(process_timeout=30),
            ManagedIdentityCredential(process_timeout=30)
        )

        # Test the credential
        token = credential.get_token("https://management.azure.com/.default")
        logging.info("✅ ChainedTokenCredential validated successfully")
        return credential
        
    except Exception as e:
        logging.error(f"❌ ChainedTokenCredential failed: {e}")
        sys.exit(1)


def get_config_value(appconfig, key, required=True, max_retries=3):
    logging.debug(f"Fetching config value for key='{key}', label='agent-lz'")
    
    for attempt in range(max_retries):
        try:
            setting = appconfig.get_configuration_setting(key=key, label="agent-lz")
            value = setting.value
            
            # Mask sensitive values in logs
            if any(sensitive in key.upper() for sensitive in ["PASSWORD", "SECRET", "KEY", "TOKEN"]):
                logging.debug(f"  Retrieved '{key}' = <masked>")
            else:
                logging.debug(f"  Retrieved '{key}' = '{value}'")
            
            return value
        except Exception as e:
            if not required and isinstance(e, ResourceNotFoundError):
                return None
            if attempt == max_retries - 1:
                logging.error(f"Failed to fetch '{key}' after {max_retries} attempts: {e}")
                sys.exit(1)
            else:
                logging.warning(f"Attempt {attempt + 1}/{max_retries} failed for '{key}': {e}. Retrying...")
                time.sleep(2)


def update_single_container_app(subscription_id, resource_group, name, acr_server, use_uai, shared_credential,
                                *, preserve_other_registries: bool = False):
    """Update registry auth; custom callers can retain unrelated registries.

    The default retains the existing bundled setup behavior.
    """
    start_time = time.time()
    logging.info(f"[{name}] Starting Container App update process")
    logging.debug(f"[{name}] Parameters: subscription={subscription_id}, rg={resource_group}, acr={acr_server}")
    
    try:
        # Use the shared credential instead of creating a new one for each thread
        client = ContainerAppsAPIClient(shared_credential, subscription_id)
        
        logging.info(f"[{name}] Associating ACR '{acr_server}'...")
        
        # Get current app configuration
        logging.debug(f"[{name}] Fetching current Container App configuration")
        app = client.container_apps.get(resource_group, name)
        logging.debug(f"[{name}] Current provisioning state: {app.provisioning_state}")
        
        # Check identity
        desired_identity = _get_desired_identity(app, name, use_uai)
        if not desired_identity:
            elapsed = time.time() - start_time
            logging.error(f"[{name}] Failed: No desired identity found (elapsed: {elapsed:.2f}s)")
            return name, False, "No desired identity found"

        # Check if already configured
        logging.debug(f"[{name}] Checking if registry is already configured")
        if _registry_matches(app, acr_server, desired_identity):
            elapsed = time.time() - start_time
            logging.info(f"[{name}] ✓ Registry already configured, skipping update (elapsed: {elapsed:.2f}s)")
            return name, True, "Already configured"

        # Update registry configuration
        logging.info(f"[{name}] Updating registry configuration with identity: {desired_identity}")
        retained = [
            reg for reg in (app.configuration.registries or [])
            if (reg.get("server") if isinstance(reg, dict) else getattr(reg, "server", None)) != acr_server
        ] if preserve_other_registries else []
        app.configuration.registries = retained + [
            {"server": acr_server, "identity": desired_identity}
        ]
        
        logging.debug(f"[{name}] Starting create_or_update operation (timeout={POLL_TIMEOUT_SECONDS}s)")
        poller = client.container_apps.begin_create_or_update(resource_group, name, app)
        
        try:
            logging.debug(f"[{name}] Waiting for operation to complete...")
            result = poller.result(timeout=POLL_TIMEOUT_SECONDS)
            elapsed = time.time() - start_time
            
            logging.info(f"[{name}] ✅ Successfully updated! (elapsed: {elapsed:.2f}s)")
            logging.debug(f"[{name}] Final provisioning state: {result.provisioning_state}")
            return name, True, "Success"
            
        except Exception as exc:
            message = str(exc).lower()
            elapsed = time.time() - start_time
            
            if "timeout" in message or "did not complete" in message:
                logging.warning(
                    f"[{name}] ⏱️ Operation timed out after {POLL_TIMEOUT_SECONDS}s (total elapsed: {elapsed:.2f}s)"
                )
                return name, False, "Timeout"
            
            logging.error(f"[{name}] Operation failed: {exc} (elapsed: {elapsed:.2f}s)")
            raise
            
    except Exception as e:
        elapsed = time.time() - start_time
        logging.error(f"[{name}] ❌ Unexpected error: {e} (elapsed: {elapsed:.2f}s)", exc_info=True)
        return name, False, str(e)


def main():
    configure_logging()
    overall_start = time.time()

    logging.info("="*60)
    logging.info("Container Apps Setup - ACR Association")
    logging.info("="*60)

    endpoint = os.getenv("APP_CONFIG_ENDPOINT")
    if not endpoint:
        logging.error("Environment variable APP_CONFIG_ENDPOINT is not set.")
        sys.exit(1)
    
    logging.info(f"App Configuration Endpoint: {endpoint}")
    logging.info(f"Max Workers: {MAX_WORKERS}")
    logging.info(f"Poll Timeout: {POLL_TIMEOUT_SECONDS}s")

    # Create and test credentials once
    logging.debug("Creating and testing shared credential")
    shared_credential = get_credentials()
    
    appconfig = AzureAppConfigurationClient(endpoint, shared_credential)

    # Read global settings
    logging.info("Fetching configuration from App Configuration...")
    subscription_id = get_config_value(appconfig, "SUBSCRIPTION_ID")
    resource_group = resource_group_for({
        "AZURE_RESOURCE_GROUP": get_config_value(appconfig, "AZURE_RESOURCE_GROUP"),
        "AZURE_APP_RESOURCE_GROUP": get_config_value(
            appconfig, "AZURE_APP_RESOURCE_GROUP", required=False,
        ) or "",
    }, "application")
    acr_name = get_config_value(appconfig, "CONTAINER_REGISTRY_NAME")
    use_uai = get_config_value(appconfig, "USE_UAI")
    acr_server = f"{acr_name}.azurecr.io"
    
    logging.info(f"Configuration loaded:")
    logging.info(f"  Subscription: {subscription_id}")
    logging.info(f"  Resource Group: {resource_group}")
    logging.info(f"  ACR Server: {acr_server}")
    logging.info(f"  Use UAI: {use_uai}")

    # Read and parse the list of container apps
    logging.debug("Fetching CONTAINER_APPS list")
    raw_list = get_config_value(appconfig, "CONTAINER_APPS")
    try:
        apps_list = json.loads(raw_list)
        logging.debug(f"Parsed {len(apps_list)} container app entries")
    except json.JSONDecodeError as e:
        logging.error(f"CONTAINER_APPS is not valid JSON: {e}")
        sys.exit(1)

    # Extract app names
    app_names = [entry.get("name") for entry in apps_list if entry.get("name")]
    
    if not app_names:
        logging.warning("No container apps found to process.")
        return
    
    logging.info(f"Found {len(app_names)} container apps to process: {', '.join(app_names)}")
    
    if MAX_WORKERS == 2:
        logging.info("Processing apps ...")
        logging.info("-"*60)
        
        # Process sequentially
        results = []
        for i, name in enumerate(app_names, 1):
            logging.info(f"Processing {i}/{len(app_names)}: {name}")
            try:
                result = update_single_container_app(subscription_id, resource_group, name, acr_server, use_uai, shared_credential)
                results.append(result)
            except Exception as e:
                logging.error(f"Failed to process {name}: {e}")
                results.append((name, False, str(e)))
    else:
        logging.info(f"Processing with {MAX_WORKERS} parallel workers...")
        logging.info("-"*60)
        
        # Process in parallel with shared credential
        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            logging.debug("Submitting tasks to thread pool")
            futures = {
                executor.submit(
                    update_single_container_app,
                    subscription_id,
                    resource_group,
                    name,
                    acr_server,
                    use_uai,
                    shared_credential
                ): name
                for name in app_names
            }
            
            completed_count = 0
            for future in as_completed(futures):
                completed_count += 1
                name = futures[future]
                try:
                    app_name, success, message = future.result()
                    results.append((app_name, success, message))
                    logging.info(f"Progress: {completed_count}/{len(app_names)} apps processed")
                except Exception as e:
                    logging.error(f"Unexpected error processing '{name}': {e}", exc_info=True)
                    results.append((name, False, str(e)))
    
    # Summary
    overall_elapsed = time.time() - overall_start
    
    print()  # Blank line before summary
    logging.info("="*60)
    logging.info("FINAL SUMMARY")
    logging.info("="*60)
    
    successful = sum(1 for _, success, _ in results if success)
    logging.info(f"✅ Successful: {successful}/{len(results)}")
    
    failed = [(name, msg) for name, success, msg in results if not success]
    if failed:
        logging.info(f"❌ Failed: {len(failed)}")
        for name, msg in failed:
            logging.info(f"   - {name}: {msg}")
    
    logging.info(f"⏱️  Total execution time: {overall_elapsed:.2f}s ({overall_elapsed/60:.2f}m)")
    logging.info("="*60)


if __name__ == "__main__":
    main()