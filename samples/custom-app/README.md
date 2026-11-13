# Sample custom application

Two minimal applications that deploy on Agent Landing Zone through an
application definition (`app-definition.json`, schema
`contracts/app-definition-v1.schema.json`):

| Folder | Hosting | What it does |
|---|---|---|
| `containerapp/` | Azure Container Apps | `GET /health` and `GET /` returning the platform outputs from App Configuration (`AGENTLZ_PLATFORM_OUTPUTS`, label `agent-lz`). |
| `hosted/` | Microsoft Foundry hosted agent | Answers the Responses protocol with the platform-injected `FOUNDRY_PROJECT_ENDPOINT`, without requiring `APP_CONFIG_ENDPOINT`. |

`hosted/` stays dependency-free for greeting smoke validation whether App
Configuration is enabled or disabled. When graduating a hosted agent to
production, adopt `azure-ai-agentserver-responses` so `GET /responses/{id}`
lookups are persisted and GenAI OpenTelemetry `invoke_agent` spans are emitted
automatically when Foundry injects `APPLICATIONINSIGHTS_CONNECTION_STRING`. Do
not declare `FOUNDRY_*`, `AGENT_*`, or `APPLICATIONINSIGHTS_CONNECTION_STRING`
in `azure.yaml` because Microsoft Foundry reserves those variables.

## Use

1. Copy a folder into your own repository and replace each component
   `source.commit` with the commit you deploy (the all-zero value is a
   placeholder).
2. Validate it: `python -m config.appdefinition --validate <folder>`.
3. In a **new** azd environment: `azd env set AGENTLZ_APP_DEFINITION <folder>`,
   then `azd up` from the Agent Landing Zone repository root. An environment
   hosts exactly one application.

Rules: no lifecycle hooks, no remote URLs, no role names; permissions come only
from capability profiles. See [Custom applications](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/build-your-own-app/)
for the folder layout, source pinning, and hosted greeting protocol requirements.
