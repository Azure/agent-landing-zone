# Sample custom application

Two minimal applications that deploy on Agent Landing Zone through an
application definition (`app-definition.json`, schema
`contracts/app-definition-v1.schema.json`):

| Folder | Hosting | What it does |
|---|---|---|
| `containerapp/` | Azure Container Apps | `GET /health` and `GET /` returning the platform outputs. |
| `hosted/` | Microsoft Foundry hosted agent | Answers the responses protocol with the Foundry project endpoint. |

Both read the platform outputs contract (`AGENTLZ_PLATFORM_OUTPUTS`, label
`agent-lz`) from App Configuration through `APP_CONFIG_ENDPOINT`.

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
