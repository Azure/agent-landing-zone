import os
from azure.identity import ChainedTokenCredential, ManagedIdentityCredential, AzureCliCredential
from azure.keyvault.secrets import SecretClient
from azure.core.exceptions import AzureError
from config.deployment.setup_settings import load_setup_settings

class KeyVaultClient:
    """
    Simple wrapper to fetch and set secrets in Azure Key Vault.
    Optionally accepts a verified vault URI; otherwise verifies deployment settings.
    """
    def __init__(self, vault_uri: str = None):
        # Determine vault URI
        if vault_uri is None:
            vault_uri = load_setup_settings().get("KEY_VAULT_URI")
            if not vault_uri:
                raise EnvironmentError("A selected Key Vault is required for Foundry secrets.")
        # Authenticate
        credential = ChainedTokenCredential(AzureCliCredential(),ManagedIdentityCredential())
        try:
            self._client = SecretClient(vault_url=vault_uri, credential=credential)
        except AzureError as e:
            raise RuntimeError(f"Failed to create SecretClient: {e}")

    def get_secret(self, name: str) -> str:
        """
        Returns the secret value, or raises on error.
        """
        try:
            secret = self._client.get_secret(name)
            return secret.value
        except AzureError as e:
            raise RuntimeError(f"Error retrieving secret '{name}': {e}")

    def set_secret(self, name: str, value: str) -> None:
        """
        Stores (or updates) a secret in Key Vault.
        """
        try:
            self._client.set_secret(name, value)
        except AzureError as e:
            raise RuntimeError(f"Error setting secret '{name}': {e}")
