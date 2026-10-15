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
> **GPT-RAG has evolved into Agent Landing Zone.** Same project, new name and broader scope: infrastructure and application layers for enterprise agents on Azure.
> Documentation: [Agent Landing Zone docs](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/). Old links such as `aka.ms/gpt-rag` redirect there.

## Architecture

![Zero Trust Architecture](media/architecture_zero_trust.png)

## Deploy

Choose one of two options:

| Option | Guide | What you get |
|---|---|---|
| Full stack | [Deploy full stack](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/deploy-full-stack/) | Infrastructure, a chat UI and an orchestrator agent, with an optional ingestion Container App. |
| Infrastructure only | [Deploy infra only](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/deploy-infra-only/) | Provision the foundation with `azd provision` without deploying application images. |

The orchestrator agent runs in Microsoft Foundry by default, or in Azure Container Apps with the classic topology. Fresh environments use native Foundry IQ Blob ingestion without the ingestion Container App. Existing environments keep their ingestion selection. Native source ingestion does not provide chat attachment uploads. See [ingestion selection](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/configuration/#ingestion-application-selection).

To deploy your own application, select its `app-definition.json` before the first provision. See [Custom applications](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/build-your-own-app/) and the examples in [samples/custom-app](samples/custom-app).

Prerequisites, network-isolated deployment, and configuration are covered in the [central documentation](#documentation).

## Components

Component versions for this release are pinned in [manifest.json](manifest.json).

| Component | Repository | Version |
|---|---|---|
| UI | [Azure/agent-app-ui](https://github.com/Azure/agent-app-ui) | see `manifest.json` |
| Orchestrator | [Azure/agent-app-orchestrator](https://github.com/Azure/agent-app-orchestrator) | see `manifest.json` |
| Ingestion (optional) | [Azure/agent-app-ingestion](https://github.com/Azure/agent-app-ingestion) | see `manifest.json` |

## Documentation

The full documentation lives in the Agent Landing Zone section of the [AI Landing Zones documentation site](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and [SUPPORT.md](SUPPORT.md). Release history is in [CHANGELOG.md](CHANGELOG.md).

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft trademarks or logos is subject to and must follow [Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualpropertyandcustomerinfo/trademarks/usage/general). Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship. Any use of third-party trademarks or logos is subject to those third-party's policies.
