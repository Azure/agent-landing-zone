<!--
page_type: sample
languages:
- azdeveloper
- powershell
- bicep
products:
- azure
- azure-ai-foundry
- azure-openai
- azure-ai-search
urlFragment: agent-landing-zone
name: Agent Landing Zone
description: Secure, enterprise-ready landing zone for deploying AI agent applications on Microsoft Foundry, with Zero-Trust networking and IaC-first deployment.
-->
<img src="media/logo.png" alt="Agent Landing Zone logo" width="80" align="left"/>

# Agent Landing Zone

Secure, enterprise-ready landing zone for deploying AI agent applications on Microsoft Foundry.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-AI%20Landing%20Zones-0078D4.svg)](https://azure.github.io/AI-Landing-Zones/)
[![Azure Developer CLI](https://img.shields.io/badge/azd-compatible-0078D4.svg)](https://learn.microsoft.com/azure/developer/azure-developer-cli/)

> [!NOTE]
> **GPT-RAG has evolved into Agent Landing Zone.** Same project, broader scope: infrastructure and applications for enterprise agents on Azure. For Agent Landing Zone, use the [current documentation](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/). For older GPT-RAG deployments, refer to the [legacy documentation](https://azure.github.io/agent-landing-zone/).

## Architecture

Standalone reference architecture for private-network deployments. Resource
selection and reuse depend on deployment settings. Select the image to open the
full-resolution PNG. For Platform Hub and AI Gateway combinations, see the
[reference architectures](https://azure.github.io/AI-Landing-Zones/#reference-architectures).

[![Standalone Agent Landing Zone architecture](media/AI-Landing-Zone-without-platform.png?v=aa651551c880)](media/AI-Landing-Zone-without-platform.png?v=aa651551c880)

## Deploy

- [Full stack](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/deploy-full-stack/) — Deploy the infrastructure and default agent application.
- [Infrastructure only](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/deploy-infra-only/) — Provision the foundation without deploying application images.
- [Custom applications](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/build-your-own-app/) — Deploy your own application on the foundation.

## Components

Component versions for this release are pinned in [manifest.json](manifest.json).

| Component | Repository |
|---|---|
| UI | [Azure/agent-app-ui](https://github.com/Azure/agent-app-ui) |
| Orchestrator | [Azure/agent-app-orchestrator](https://github.com/Azure/agent-app-orchestrator) |
| Ingestion (optional) | [Azure/agent-app-ingestion](https://github.com/Azure/agent-app-ingestion) |

## Documentation

The full documentation lives in the Agent Landing Zone section of the [AI Landing Zones documentation site](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and [SUPPORT.md](SUPPORT.md). Release history is in [CHANGELOG.md](CHANGELOG.md).

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft trademarks or logos is subject to and must follow [Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualpropertyandcustomerinfo/trademarks/usage/general). Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship. Any use of third-party trademarks or logos is subject to those third-party's policies.
