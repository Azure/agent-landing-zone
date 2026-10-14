# Agent Landing Zone infrastructure

This directory contains the Bicep infrastructure foundation used by Agent Landing Zone. Deploy the solution from the [repository root](../README.md), not from this directory.

For configuration and deployment instructions, see the [Agent Landing Zone documentation](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/):

- [Configuration](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/configuration/)
- [Deploy the full stack](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/deploy-full-stack/)
- [Deploy infrastructure only](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/deploy-infra-only/)
- [Network isolation](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/network-isolation/)
- [Hosted agents](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/hosted-agents/)

For the broader architecture and implementation options, see [AI Landing Zones](https://aka.ms/ailz).

The infrastructure's source repository, version, and commit are recorded in the repository-root [`manifest.json`](../manifest.json), under `infra.source`. Deployment uses the code in this directory; it does not download that source version at provisioning time.
