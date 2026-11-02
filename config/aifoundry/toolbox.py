"""Provision the managed Foundry IQ Toolbox after Search configures its KB."""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPToolboxTool
from azure.identity import (
    AzureCliCredential,
    ChainedTokenCredential,
    ManagedIdentityCredential,
)

from .appconfig import AppConfigClient

SETTINGS = (
    "RETRIEVAL_BACKEND",
    "AI_FOUNDRY_PROJECT_ENDPOINT", "AI_FOUNDRY_PROJECT_RESOURCE_ID", "TOOLBOX_ENDPOINT",
    "KNOWLEDGE_BASE_NAME", "KNOWLEDGE_BASE_ENDPOINT", "KNOWLEDGE_BASE_CONNECTION_ID", "FOUNDRY_IQ_API_VERSION",
)


@dataclass(frozen=True)
class KnowledgeToolbox:
    project_endpoint: str
    name: str
    server_url: str
    connection_name: str

    @classmethod
    def read(cls, values: Mapping[str, str]) -> "KnowledgeToolbox | None":
        if values.get("RETRIEVAL_BACKEND") != "foundry_iq":
            return None
        name = values.get("KNOWLEDGE_BASE_NAME", "")
        project = values.get("AI_FOUNDRY_PROJECT_ENDPOINT", "").rstrip("/")
        project_id = values.get("AI_FOUNDRY_PROJECT_RESOURCE_ID", "")
        search = values.get("KNOWLEDGE_BASE_ENDPOINT", "").rstrip("/")
        connection = values.get("KNOWLEDGE_BASE_CONNECTION_ID", "")
        api_version = values.get("FOUNDRY_IQ_API_VERSION", "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-preview)?", api_version):
            raise ValueError("Managed Toolbox requires FOUNDRY_IQ_API_VERSION from provisioning.")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Managed Toolbox requires a valid KNOWLEDGE_BASE_NAME.")
        if not re.fullmatch(r"https://[a-z0-9-]+\.services\.ai\.azure\.com/api/projects/[A-Za-z0-9_.-]+", project):
            raise ValueError("Managed Toolbox requires AI_FOUNDRY_PROJECT_ENDPOINT.")
        if not re.fullmatch(r"https://[a-z0-9-]+\.search\.windows\.net", search):
            raise ValueError("Managed Toolbox requires the provisioned KNOWLEDGE_BASE_ENDPOINT.")
        project_match = re.fullmatch(
            r"/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[^/]+/providers/"
            r"Microsoft\.CognitiveServices/accounts/([^/]+)/projects/([^/]+)", project_id,
        )
        if (
            project_match is None
            or project != f"https://{project_match[1]}.services.ai.azure.com/api/projects/{project_match[2]}"
            or not connection.startswith(project_id + "/connections/")
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", connection.rsplit("/", 1)[-1])
        ):
            raise ValueError("Managed Toolbox connection must belong to its provisioned Foundry project.")
        if values.get("TOOLBOX_ENDPOINT") != f"{project}/toolboxes/{name}/mcp?api-version=v1":
            raise ValueError("TOOLBOX_ENDPOINT must match the provisioned project and knowledge base.")
        return cls(
            project, name, f"{search}/knowledgebases/{name}/mcp?api-version={api_version}",
            connection.rsplit("/", 1)[-1],
        )

    def provision(self, client: AIProjectClient) -> None:
        version = client.toolboxes.create_version(
            self.name, description="Foundry IQ knowledge base behind one managed endpoint",
            tools=[MCPToolboxTool(
                name="knowledge_base", server_label="knowledge_base",
                server_url=self.server_url, project_connection_id=self.connection_name,
                allowed_tools=["knowledge_base_retrieve"], require_approval="never",
            )],
        )
        client.toolboxes.update(self.name, default_version=version.version)


def main() -> None:
    config = AppConfigClient()
    binding = KnowledgeToolbox.read({key: config.get(key) for key in SETTINGS if config.get(key) is not None})
    if binding is None:
        return
    with (
        ChainedTokenCredential(AzureCliCredential(), ManagedIdentityCredential()) as credential,
        AIProjectClient(endpoint=binding.project_endpoint, credential=credential) as client,
    ):
        binding.provision(client)


if __name__ == "__main__":
    main()
