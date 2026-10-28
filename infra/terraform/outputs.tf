# Keep the flat azd contract. Scalars are explicitly converted to concrete
# types because azd 1.37.1 cannot import Terraform's untyped "dynamic" null.
locals {
  foundation_metadata = {
    TENANT_ID                              = tostring(local.deployment_context.tenant_id)
    SUBSCRIPTION_ID                        = tostring(local.deployment_context.subscription_id)
    AZURE_RESOURCE_GROUP                   = tostring(local.deployment_context.foundry_rg)
    AZURE_APP_RESOURCE_GROUP               = tostring(local.deployment_context.application_rg)
    AZURE_NETWORK_RESOURCE_GROUP           = tostring(local.deployment_context.network_rg)
    LOCATION                               = tostring(local.effective_locations.main)
    ENVIRONMENT_NAME                       = tostring(var.environmentName)
    DEPLOYMENT_NAME                        = tostring(local.deployment_context.deployment_name)
    RESOURCE_TOKEN                         = tostring(local.resource_token)
    RELEASE                                = tostring(local.manifest.tag)
    NETWORK_ISOLATION                      = tobool(local.effective_flags.network_isolation)
    USE_UAI                                = tobool(local.effective_flags.use_uai)
    USE_CAPP_API_KEY                       = tobool(local.effective_flags.use_capp_api_key)
    APP_RUNTIME_CONFIGURATION_MODE         = tostring(var.appRuntimeConfigurationMode)
    DEPLOY_APP_CONFIG                      = tobool(var.deployAppConfig)
    DEPLOY_SOFTWARE                        = tobool(var.deploySoftware)
    DEPLOY_KEY_VAULT                       = tobool(var.deployKeyVault)
    DEPLOY_LOG_ANALYTICS                   = tobool(var.deployLogAnalytics)
    DEPLOY_APP_INSIGHTS                    = tobool(var.deployAppInsights)
    DEPLOY_SEARCH_SERVICE                  = tobool(var.deploySearchService)
    DEPLOY_SPEECH_SERVICE                  = tobool(var.deploySpeechService)
    DEPLOY_STORAGE_ACCOUNT                 = tobool(var.deployStorageAccount)
    DEPLOY_COSMOS_DB                       = tobool(var.deployCosmosDb)
    DEPLOY_CONTAINER_APPS                  = tobool(var.deployContainerApps)
    DEPLOY_CONTAINER_REGISTRY              = tobool(var.deployContainerRegistry)
    DEPLOY_CONTAINER_ENV                   = tobool(var.deployContainerEnv)
    DEPLOY_VM_KEY_VAULT                    = tobool(var.deployVmKeyVault)
    ACR_TASK_AGENT_POOL                    = tostring(local.effective_flags.acr_pool ? var.acrTaskAgentPoolName : "")
    APP_CONFIG_ENDPOINT                    = tostring(var.deployAppConfig ? local.data_context.app_config.endpoint : "")
    KEY_VAULT_URI                          = tostring(var.deployKeyVault ? local.data_context.key_vault.uri : "")
    RETRIEVAL_BACKEND                      = tostring(var.retrievalBackend)
    FOUNDRY_IQ_PATTERN                     = tostring(var.foundryIqPattern)
    KNOWLEDGE_BASE_NAME                    = tostring(var.retrievalBackend == "foundry_iq" ? var.knowledgeBaseName : "")
    KNOWLEDGE_BASE_ENDPOINT                = tostring(var.retrievalBackend == "foundry_iq" && var.deploySearchService ? local.data_context.search.endpoint : "")
    KNOWLEDGE_BASE_CONNECTION_ID           = tostring(var.retrievalBackend == "foundry_iq" && var.deployAiFoundry && var.deploySearchService ? local.foundry_context.knowledge_base_connection_id : "")
    FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME       = tostring(var.retrievalBackend == "foundry_iq" ? var.foundryIqKnowledgeSourceName : "")
    FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND       = tostring(coalesce(var.foundryIqKnowledgeSourceKind, var.foundryIqPattern == "searchIndex" ? "searchIndex" : "azureBlob"))
    AZURE_SPEECH_RESOURCE_ID               = tostring(var.deploySpeechService ? local.data_context.speech.id : "")
    AZURE_SPEECH_ENDPOINT                  = tostring(var.deploySpeechService ? local.data_context.speech.endpoint : "")
    AZURE_SPEECH_REGION                    = tostring(var.deploySpeechService ? local.data_context.speech.location : "")
    AZURE_SPEECH_RESOURCE_NAME             = tostring(var.deploySpeechService ? local.data_context.speech.name : "")
    PUBLIC_INGRESS_ENABLED                 = tobool(local.effective_flags.public_ingress)
    PUBLIC_INGRESS_PUBLIC_IP               = tostring(local.effective_flags.public_ingress ? local.network_ingress_context.public_ip : "")
    PUBLIC_INGRESS_PUBLIC_IP_RESOURCE_ID   = tostring(local.effective_flags.public_ingress ? local.network_ingress_context.public_ip_resource_id : "")
    PUBLIC_INGRESS_GATEWAY_RESOURCE_ID     = tostring(local.effective_flags.public_ingress ? local.network_ingress_context.gateway_resource_id : "")
    PUBLIC_INGRESS_NSG_RESOURCE_ID         = tostring(local.effective_flags.public_ingress ? local.network_ingress_context.nsg_resource_id : "")
    PUBLIC_INGRESS_WAF_POLICY_RESOURCE_ID  = tostring(local.effective_flags.public_ingress ? local.network_ingress_context.waf_policy_resource_id : "")
    PUBLIC_INGRESS_IDENTITY_PRINCIPAL_ID   = tostring(local.effective_flags.public_ingress ? local.network_ingress_context.identity_principal_id : "")
    PUBLIC_INGRESS_LIVE                    = tobool(local.effective_flags.public_ingress ? local.network_ingress_context.live_mode : false)
    APP_GATEWAY_SUBNET_RESOURCE_ID         = tostring(var.networkIsolation ? local.subnet_ids.appGateway : "")
    VNET_RESOURCE_ID                       = tostring(local.network_context.vnet_id)
    KEY_VAULT_RESOURCE_ID                  = tostring(var.deployKeyVault ? local.data_context.key_vault.id : "")
    KEY_VAULT_NAME                         = tostring(var.deployKeyVault ? local.data_context.key_vault.name : "")
    LOG_ANALYTICS_RESOURCE_ID              = tostring(local.effective_observability.law_id)
    APP_INSIGHTS_RESOURCE_ID               = tostring(local.effective_observability.app_insights_id)
    OBSERVABILITY_MIXED_WORKSPACES_ALLOWED = tobool(var.allowMixedObservabilityWorkspaces)
    CONTAINER_APP_INTERNAL_FQDN = tostring(
      local.effective_flags.container_apps && length(var.containerAppsList) > 0 ?
      try(local.compute_context.apps[var.containerAppsList[var.publicIngress.backendAppIndex].service_name].fqdn, "") : ""
    )
    DEPLOY_HOSTED_AGENT                  = tobool(var.deployHostedAgent)
    HOSTED_AGENT_PREPARED                = tobool(local.effective_flags.hosted_prerequisites)
    AZURE_AI_PROJECT_RESOURCE_ID         = tostring(var.deployAiFoundry || local.effective_flags.hosted_prerequisites ? local.foundry_context.project_id : "")
    AZURE_AI_PROJECT_ENDPOINT            = tostring(var.deployAiFoundry || local.effective_flags.hosted_prerequisites ? local.foundry_context.project_endpoint : "")
    AZURE_CONTAINER_REGISTRY_RESOURCE_ID = tostring(var.deployContainerRegistry || local.effective_flags.hosted_prerequisites ? local.hosted_registry.resource_id : "")
    AZURE_CONTAINER_REGISTRY_ENDPOINT    = tostring(var.deployContainerRegistry || local.effective_flags.hosted_prerequisites ? local.hosted_registry.endpoint : "")
    HOSTED_AGENT_DEPLOYMENT = {
      workloadEgress = {
        networkIsolation        = tobool(var.networkIsolation)
        managedFirewallPolicyId = tostring(local.network_context.firewall_policy_id)
        subnets = {
          containerapp     = tostring(var.networkIsolation ? local.subnet_ids.acaEnvironment : "")
          "azure.ai.agent" = tostring(var.networkIsolation ? local.subnet_ids.agent : "")
        }
      }
      enabled = tobool(var.deployHostedAgent)
      # These null *members* preserve the Bicep JSON schema; the outer output
      # remains a concrete object, never an untyped null scalar.
      agent = var.deployHostedAgent ? {
        name           = var.hostedAgent.name
        image          = "${local.hosted_registry.endpoint}/${var.hostedAgent.image}@${var.hostedAgent.version}"
        imageVersion   = var.hostedAgent.version
        startupCommand = var.hostedAgent.startupCommand
        runtime        = var.hostedAgent.runtime
        protocols      = var.hostedAgent.protocols
      } : null
      foundry = local.effective_flags.hosted_prerequisites ? {
        projectResourceId     = tostring(local.foundry_context.project_id)
        projectEndpoint       = tostring(local.foundry_context.project_endpoint)
        projectPrincipalId    = tostring(local.foundry_context.project_principal_id)
        agentSubnetResourceId = tostring(var.networkIsolation ? local.subnet_ids.agent : "")
      } : null
      containerRegistry = local.effective_flags.hosted_prerequisites ? {
        resourceId = tostring(local.hosted_registry.resource_id)
        endpoint   = tostring(local.hosted_registry.endpoint)
      } : null
      privateBuild = {
        required             = tobool(local.effective_flags.hosted_prerequisites && var.networkIsolation)
        subnetResourceId     = tostring(local.effective_flags.hosted_prerequisites && var.networkIsolation ? local.subnet_ids.devopsBuildAgents : "")
        jumpboxResourceId    = tostring(local.effective_flags.hosted_prerequisites && var.networkIsolation ? local.compute_context.jumpbox_id : "")
        acrTaskAgentPoolName = tostring(local.effective_flags.hosted_prerequisites && local.effective_flags.acr_pool ? var.acrTaskAgentPoolName : "")
      }
    }
  }
}

output "TENANT_ID" {
  value = local.foundation_metadata.TENANT_ID
}
output "SUBSCRIPTION_ID" {
  value = local.foundation_metadata.SUBSCRIPTION_ID
}
output "AZURE_RESOURCE_GROUP" {
  value = local.foundation_metadata.AZURE_RESOURCE_GROUP
}
output "AZURE_APP_RESOURCE_GROUP" {
  value = local.foundation_metadata.AZURE_APP_RESOURCE_GROUP
}
output "AZURE_NETWORK_RESOURCE_GROUP" {
  value = local.foundation_metadata.AZURE_NETWORK_RESOURCE_GROUP
}
output "LOCATION" {
  value = local.foundation_metadata.LOCATION
}
output "ENVIRONMENT_NAME" {
  value = local.foundation_metadata.ENVIRONMENT_NAME
}
output "DEPLOYMENT_NAME" {
  value = local.foundation_metadata.DEPLOYMENT_NAME
}
output "RESOURCE_TOKEN" {
  value = local.foundation_metadata.RESOURCE_TOKEN
}
output "RELEASE" {
  value = local.foundation_metadata.RELEASE
}
output "NETWORK_ISOLATION" {
  value = local.foundation_metadata.NETWORK_ISOLATION
}
output "USE_UAI" {
  value = local.foundation_metadata.USE_UAI
}
output "USE_CAPP_API_KEY" {
  value = local.foundation_metadata.USE_CAPP_API_KEY
}
output "APP_RUNTIME_CONFIGURATION_MODE" {
  value = local.foundation_metadata.APP_RUNTIME_CONFIGURATION_MODE
}
output "DEPLOY_APP_CONFIG" {
  value = local.foundation_metadata.DEPLOY_APP_CONFIG
}
output "DEPLOY_SOFTWARE" {
  value = local.foundation_metadata.DEPLOY_SOFTWARE
}
output "DEPLOY_KEY_VAULT" {
  value = local.foundation_metadata.DEPLOY_KEY_VAULT
}
output "DEPLOY_LOG_ANALYTICS" {
  value = local.foundation_metadata.DEPLOY_LOG_ANALYTICS
}
output "DEPLOY_APP_INSIGHTS" {
  value = local.foundation_metadata.DEPLOY_APP_INSIGHTS
}
output "DEPLOY_SEARCH_SERVICE" {
  value = local.foundation_metadata.DEPLOY_SEARCH_SERVICE
}
output "DEPLOY_SPEECH_SERVICE" {
  value = local.foundation_metadata.DEPLOY_SPEECH_SERVICE
}
output "DEPLOY_STORAGE_ACCOUNT" {
  value = local.foundation_metadata.DEPLOY_STORAGE_ACCOUNT
}
output "DEPLOY_COSMOS_DB" {
  value = local.foundation_metadata.DEPLOY_COSMOS_DB
}
output "DEPLOY_CONTAINER_APPS" {
  value = local.foundation_metadata.DEPLOY_CONTAINER_APPS
}
output "DEPLOY_CONTAINER_REGISTRY" {
  value = local.foundation_metadata.DEPLOY_CONTAINER_REGISTRY
}
output "DEPLOY_CONTAINER_ENV" {
  value = local.foundation_metadata.DEPLOY_CONTAINER_ENV
}
output "DEPLOY_VM_KEY_VAULT" {
  value = local.foundation_metadata.DEPLOY_VM_KEY_VAULT
}
output "ACR_TASK_AGENT_POOL" {
  value = local.foundation_metadata.ACR_TASK_AGENT_POOL
}
output "APP_CONFIG_ENDPOINT" {
  value = local.foundation_metadata.APP_CONFIG_ENDPOINT
}
output "KEY_VAULT_URI" {
  value = local.foundation_metadata.KEY_VAULT_URI
}
output "RETRIEVAL_BACKEND" {
  value = local.foundation_metadata.RETRIEVAL_BACKEND
}
output "FOUNDRY_IQ_PATTERN" {
  value = local.foundation_metadata.FOUNDRY_IQ_PATTERN
}
output "KNOWLEDGE_BASE_NAME" {
  value = local.foundation_metadata.KNOWLEDGE_BASE_NAME
}
output "KNOWLEDGE_BASE_ENDPOINT" {
  value = local.foundation_metadata.KNOWLEDGE_BASE_ENDPOINT
}
output "KNOWLEDGE_BASE_CONNECTION_ID" {
  value = local.foundation_metadata.KNOWLEDGE_BASE_CONNECTION_ID
}
output "FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME" {
  value = local.foundation_metadata.FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME
}
output "FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND" {
  value = local.foundation_metadata.FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND
}
output "AZURE_SPEECH_RESOURCE_ID" {
  value = local.foundation_metadata.AZURE_SPEECH_RESOURCE_ID
}
output "AZURE_SPEECH_ENDPOINT" {
  value = local.foundation_metadata.AZURE_SPEECH_ENDPOINT
}
output "AZURE_SPEECH_REGION" {
  value = local.foundation_metadata.AZURE_SPEECH_REGION
}
output "AZURE_SPEECH_RESOURCE_NAME" {
  value = local.foundation_metadata.AZURE_SPEECH_RESOURCE_NAME
}
output "PUBLIC_INGRESS_ENABLED" {
  value = local.foundation_metadata.PUBLIC_INGRESS_ENABLED
}
output "PUBLIC_INGRESS_PUBLIC_IP" {
  value = local.foundation_metadata.PUBLIC_INGRESS_PUBLIC_IP
}
output "PUBLIC_INGRESS_PUBLIC_IP_RESOURCE_ID" {
  value = local.foundation_metadata.PUBLIC_INGRESS_PUBLIC_IP_RESOURCE_ID
}
output "PUBLIC_INGRESS_GATEWAY_RESOURCE_ID" {
  value = local.foundation_metadata.PUBLIC_INGRESS_GATEWAY_RESOURCE_ID
}
output "PUBLIC_INGRESS_NSG_RESOURCE_ID" {
  value = local.foundation_metadata.PUBLIC_INGRESS_NSG_RESOURCE_ID
}
output "PUBLIC_INGRESS_WAF_POLICY_RESOURCE_ID" {
  value = local.foundation_metadata.PUBLIC_INGRESS_WAF_POLICY_RESOURCE_ID
}
output "PUBLIC_INGRESS_IDENTITY_PRINCIPAL_ID" {
  value = local.foundation_metadata.PUBLIC_INGRESS_IDENTITY_PRINCIPAL_ID
}
output "PUBLIC_INGRESS_LIVE" {
  value = local.foundation_metadata.PUBLIC_INGRESS_LIVE
}
output "APP_GATEWAY_SUBNET_RESOURCE_ID" {
  value = local.foundation_metadata.APP_GATEWAY_SUBNET_RESOURCE_ID
}
output "VNET_RESOURCE_ID" {
  value = local.foundation_metadata.VNET_RESOURCE_ID
}
output "KEY_VAULT_RESOURCE_ID" {
  value = local.foundation_metadata.KEY_VAULT_RESOURCE_ID
}
output "KEY_VAULT_NAME" {
  value = local.foundation_metadata.KEY_VAULT_NAME
}
output "LOG_ANALYTICS_RESOURCE_ID" {
  value = local.foundation_metadata.LOG_ANALYTICS_RESOURCE_ID
}
output "APP_INSIGHTS_RESOURCE_ID" {
  value = local.foundation_metadata.APP_INSIGHTS_RESOURCE_ID
}
output "OBSERVABILITY_MIXED_WORKSPACES_ALLOWED" {
  value = local.foundation_metadata.OBSERVABILITY_MIXED_WORKSPACES_ALLOWED
}
output "CONTAINER_APP_INTERNAL_FQDN" {
  value = local.foundation_metadata.CONTAINER_APP_INTERNAL_FQDN
}
output "DEPLOY_HOSTED_AGENT" {
  value = local.foundation_metadata.DEPLOY_HOSTED_AGENT
}
output "HOSTED_AGENT_PREPARED" {
  value = local.foundation_metadata.HOSTED_AGENT_PREPARED
}
output "AZURE_AI_PROJECT_RESOURCE_ID" {
  value = local.foundation_metadata.AZURE_AI_PROJECT_RESOURCE_ID
}
output "AZURE_AI_PROJECT_ENDPOINT" {
  value = local.foundation_metadata.AZURE_AI_PROJECT_ENDPOINT
}
output "AZURE_CONTAINER_REGISTRY_RESOURCE_ID" {
  value = local.foundation_metadata.AZURE_CONTAINER_REGISTRY_RESOURCE_ID
}
output "AZURE_CONTAINER_REGISTRY_ENDPOINT" {
  value = local.foundation_metadata.AZURE_CONTAINER_REGISTRY_ENDPOINT
}
output "HOSTED_AGENT_DEPLOYMENT" {
  value = local.foundation_metadata.HOSTED_AGENT_DEPLOYMENT
}
