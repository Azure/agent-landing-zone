# AI Foundry Project `[AiMl/AiFoundryModulesProject]`

Creates an AI Foundry project and any associated Azure service connections.

## Navigation

- [Resource Types](#Resource-Types)
- [Parameters](#Parameters)
- [Outputs](#Outputs)
- [Cross-referenced modules](#Cross-referenced-modules)

## Resource Types

| Resource Type | API Version | References |
| :-- | :-- | :-- |
| `Microsoft.Authorization/locks` | 2020-05-01 | <ul style="padding-left: 0px;"><li>[AzAdvertizer](https://www.azadvertizer.net/azresourcetypes/microsoft.authorization_locks.html)</li><li>[Template reference](https://learn.microsoft.com/en-us/azure/templates/Microsoft.Authorization/2020-05-01/locks)</li></ul> |
| `Microsoft.Authorization/roleAssignments` | 2022-04-01 | <ul style="padding-left: 0px;"><li>[AzAdvertizer](https://www.azadvertizer.net/azresourcetypes/microsoft.authorization_roleassignments.html)</li><li>[Template reference](https://learn.microsoft.com/en-us/azure/templates/Microsoft.Authorization/2022-04-01/roleAssignments)</li></ul> |
| `Microsoft.CognitiveServices/accounts/capabilityHosts` | 2025-07-01-preview | <ul style="padding-left: 0px;"><li>[AzAdvertizer](https://www.azadvertizer.net/azresourcetypes/microsoft.cognitiveservices_accounts_capabilityhosts.html)</li><li>[Template reference](https://learn.microsoft.com/en-us/azure/templates/Microsoft.CognitiveServices/2025-07-01-preview/accounts/capabilityHosts)</li></ul> |
| `Microsoft.CognitiveServices/accounts/projects` | 2025-07-01-preview | <ul style="padding-left: 0px;"><li>[AzAdvertizer](https://www.azadvertizer.net/azresourcetypes/microsoft.cognitiveservices_accounts_projects.html)</li><li>[Template reference](https://learn.microsoft.com/en-us/azure/templates/Microsoft.CognitiveServices/2025-07-01-preview/accounts/projects)</li></ul> |
| `Microsoft.CognitiveServices/accounts/projects/capabilityHosts` | 2025-07-01-preview | <ul style="padding-left: 0px;"><li>[AzAdvertizer](https://www.azadvertizer.net/azresourcetypes/microsoft.cognitiveservices_accounts_projects_capabilityhosts.html)</li><li>[Template reference](https://learn.microsoft.com/en-us/azure/templates/Microsoft.CognitiveServices/2025-07-01-preview/accounts/projects/capabilityHosts)</li></ul> |
| `Microsoft.CognitiveServices/accounts/projects/connections` | 2025-07-01-preview | <ul style="padding-left: 0px;"><li>[AzAdvertizer](https://www.azadvertizer.net/azresourcetypes/microsoft.cognitiveservices_accounts_projects_connections.html)</li><li>[Template reference](https://learn.microsoft.com/en-us/azure/templates/Microsoft.CognitiveServices/2025-07-01-preview/accounts/projects/connections)</li></ul> |
| `Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments` | 2025-04-15 | <ul style="padding-left: 0px;"><li>[AzAdvertizer](https://www.azadvertizer.net/azresourcetypes/microsoft.documentdb_databaseaccounts_sqlroleassignments.html)</li><li>[Template reference](https://learn.microsoft.com/en-us/azure/templates/Microsoft.DocumentDB/2025-04-15/databaseAccounts/sqlRoleAssignments)</li></ul> |

## Parameters

**Required parameters**

| Parameter | Type | Description |
| :-- | :-- | :-- |
| [`accountName`](#parameter-accountname) | string | Name of the existing parent Foundry Account resource. |
| [`createAccountCapabilityHost`](#parameter-createaccountcapabilityhost) | bool | Whether to create the capability host for the Foundry account. Requires associated resource connections to be provided. |
| [`createProjectCapabilityHost`](#parameter-createprojectcapabilityhost) | bool | Whether to create the capability host for the Foundry project. Requires associated resource connections to be provided. |
| [`name`](#parameter-name) | string | The name of the AI Foundry project. |

**Optional parameters**

| Parameter | Type | Description |
| :-- | :-- | :-- |
| [`aiSearchConnection`](#parameter-aisearchconnection) | object | Azure Cognitive Search connection for the project. |
| [`cosmosDbConnection`](#parameter-cosmosdbconnection) | object | Azure Cosmos DB connection for the project. |
| [`desc`](#parameter-desc) | string | The description of the AI Foundry project. |
| [`displayName`](#parameter-displayname) | string | The display name of the AI Foundry project. |
| [`location`](#parameter-location) | string | Specifies the location for all the Azure resources. |
| [`lock`](#parameter-lock) | object | The lock settings of the service. |
| [`storageAccountConnection`](#parameter-storageaccountconnection) | object | Storage Account connection for the project. |
| [`tags`](#parameter-tags) | object | Tags to be applied to the resources. |

### Parameter: `accountName`

Name of the existing parent Foundry Account resource.

- Required: Yes
- Type: string

### Parameter: `createAccountCapabilityHost`

Whether to create the capability host for the Foundry account. Requires associated resource connections to be provided.

- Required: Yes
- Type: bool

### Parameter: `createProjectCapabilityHost`

Whether to create the capability host for the Foundry project. Requires associated resource connections to be provided.

- Required: Yes
- Type: bool

### Parameter: `name`

The name of the AI Foundry project.

- Required: Yes
- Type: string

### Parameter: `aiSearchConnection`

Azure Cognitive Search connection for the project.

- Required: No
- Type: object

**Required parameters**

| Parameter | Type | Description |
| :-- | :-- | :-- |
| [`resourceGroupName`](#parameter-aisearchconnectionresourcegroupname) | string | The resource group name of the resource. |
| [`resourceName`](#parameter-aisearchconnectionresourcename) | string | The resource name of the Azure resource for the connection. |
| [`subscriptionId`](#parameter-aisearchconnectionsubscriptionid) | string | The subscription ID of the resource. |

**Optional parameters**

| Parameter | Type | Description |
| :-- | :-- | :-- |
| [`name`](#parameter-aisearchconnectionname) | string | The name of the project connection. Will default to the resource name if not provided. |

### Parameter: `aiSearchConnection.resourceGroupName`

The resource group name of the resource.

- Required: Yes
- Type: string

### Parameter: `aiSearchConnection.resourceName`

The resource name of the Azure resource for the connection.

- Required: Yes
- Type: string

### Parameter: `aiSearchConnection.subscriptionId`

The subscription ID of the resource.

- Required: Yes
- Type: string

### Parameter: `aiSearchConnection.name`

The name of the project connection. Will default to the resource name if not provided.

- Required: No
- Type: string

### Parameter: `cosmosDbConnection`

Azure Cosmos DB connection for the project.

- Required: No
- Type: object

**Required parameters**

| Parameter | Type | Description |
| :-- | :-- | :-- |
| [`resourceGroupName`](#parameter-cosmosdbconnectionresourcegroupname) | string | The resource group name of the resource. |
| [`resourceName`](#parameter-cosmosdbconnectionresourcename) | string | The resource name of the Azure resource for the connection. |
| [`subscriptionId`](#parameter-cosmosdbconnectionsubscriptionid) | string | The subscription ID of the resource. |

**Optional parameters**

| Parameter | Type | Description |
| :-- | :-- | :-- |
| [`name`](#parameter-cosmosdbconnectionname) | string | The name of the project connection. Will default to the resource name if not provided. |

### Parameter: `cosmosDbConnection.resourceGroupName`

The resource group name of the resource.

- Required: Yes
- Type: string

### Parameter: `cosmosDbConnection.resourceName`

The resource name of the Azure resource for the connection.

- Required: Yes
- Type: string

### Parameter: `cosmosDbConnection.subscriptionId`

The subscription ID of the resource.

- Required: Yes
- Type: string

### Parameter: `cosmosDbConnection.name`

The name of the project connection. Will default to the resource name if not provided.

- Required: No
- Type: string

### Parameter: `desc`

The description of the AI Foundry project.

- Required: No
- Type: string

### Parameter: `displayName`

The display name of the AI Foundry project.

- Required: No
- Type: string

### Parameter: `location`

Specifies the location for all the Azure resources.

- Required: No
- Type: string
- Default: `[resourceGroup().location]`

### Parameter: `lock`

The lock settings of the service.

- Required: No
- Type: object

**Optional parameters**

| Parameter | Type | Description |
| :-- | :-- | :-- |
| [`kind`](#parameter-lockkind) | string | Specify the type of lock. |
| [`name`](#parameter-lockname) | string | Specify the name of lock. |
| [`notes`](#parameter-locknotes) | string | Specify the notes of the lock. |

### Parameter: `lock.kind`

Specify the type of lock.

- Required: No
- Type: string
- Allowed:
  ```Bicep
  [
    'CanNotDelete'
    'None'
    'ReadOnly'
  ]
  ```

### Parameter: `lock.name`

Specify the name of lock.

- Required: No
- Type: string

### Parameter: `lock.notes`

Specify the notes of the lock.

- Required: No
- Type: string

### Parameter: `storageAccountConnection`

Storage Account connection for the project.

- Required: No
- Type: object

**Required parameters**

| Parameter | Type | Description |
| :-- | :-- | :-- |
| [`resourceGroupName`](#parameter-storageaccountconnectionresourcegroupname) | string | The resource group name of the resource. |
| [`resourceName`](#parameter-storageaccountconnectionresourcename) | string | The resource name of the Azure resource for the connection. |
| [`subscriptionId`](#parameter-storageaccountconnectionsubscriptionid) | string | The subscription ID of the resource. |

**Optional parameters**

| Parameter | Type | Description |
| :-- | :-- | :-- |
| [`name`](#parameter-storageaccountconnectionname) | string | The name of the project connection. Will default to the resource name if not provided. |

### Parameter: `storageAccountConnection.resourceGroupName`

The resource group name of the resource.

- Required: Yes
- Type: string

### Parameter: `storageAccountConnection.resourceName`

The resource name of the Azure resource for the connection.

- Required: Yes
- Type: string

### Parameter: `storageAccountConnection.subscriptionId`

The subscription ID of the resource.

- Required: Yes
- Type: string

### Parameter: `storageAccountConnection.name`

The name of the project connection. Will default to the resource name if not provided.

- Required: No
- Type: string

### Parameter: `tags`

Tags to be applied to the resources.

- Required: No
- Type: object
- Default: `{}`

## Outputs

| Output | Type | Description |
| :-- | :-- | :-- |
| `desc` | string | Description of the Project. |
| `displayName` | string | Display name of the Project. |
| `name` | string | Name of the Project. |
| `resourceGroupName` | string | Name of the deployed Azure Resource Group. |
| `resourceId` | string | Resource ID of the Project. |

## Cross-referenced modules

This section gives you an overview of all local-referenced module files (i.e., other modules that are referenced in this module) and all remote-referenced files (i.e., Bicep modules that are referenced from a Bicep Registry or Template Specs).

| Reference | Type |
| :-- | :-- |
| `br/public:avm/utl/types/avm-common-types:0.6.1` | Remote reference |
