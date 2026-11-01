# Offline only. Every run plans against mock providers: no credentials,
# resource creation, image publication, live lookup, apply or destroy.
mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id       = "00000000-0000-0000-0000-000000000002"
      subscription_id = "00000000-0000-0000-0000-000000000001"
      object_id       = "00000000-0000-0000-0000-000000000003"
      client_id       = "00000000-0000-0000-0000-000000000004"
    }
  }
  mock_data "azurerm_resource_group" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-contract"
      location = "swedencentral"
    }
  }
}
mock_provider "azapi" {
  mock_data "azapi_resource_list" {
    defaults = {
      output = { value = [] }
    }
  }
}
mock_provider "random" {}
mock_provider "modtm" {}
mock_provider "time" {}

variables {
  subscriptionId    = "00000000-0000-0000-0000-000000000001"
  tenantId          = "00000000-0000-0000-0000-000000000002"
  principalId       = "00000000-0000-0000-0000-000000000003"
  environmentName   = "contract"
  resourceGroupName = "rg-contract"
  location          = "swedencentral"
}

run "product_defaults" {
  command = plan

  assert {
    condition = (
      var.appConfigLabel == "agent-lz" && !var.networkIsolation && !var.deployCosmosDb &&
      !var.deployGroundingWithBing && !var.useZoneRedundancy &&
      var.vmSize == "Standard_D2s_v3" && !var.foundryIqFilterAddOnEnabled &&
      var.retrievalBackend == "foundry_iq"
    )
    error_message = "Effective product defaults must not revert to reusable Bicep defaults."
  }
  assert {
    condition = (
      var.azureFirewallSku == "Basic" && var.deployAzureFirewallSubnet == null &&
      var.deployAzureFirewallManagementSubnet == null && !var.deployGatewaySubnet &&
      var.azureFirewallManagementSubnetName == "AzureFirewallManagementSubnet" &&
      var.azureFirewallManagementSubnetPrefix == "192.168.3.192/26"
    )
    error_message = "Firewall defaults must retain Basic, nullable creation intent and opt-in gateway reservation."
  }
  assert {
    condition = (
      var.deployJumpbox == null && var.deployBastion == null && var.deployNatGateway == null &&
      !local.effective_flags.jumpbox && !local.effective_flags.bastion && !local.effective_flags.nat &&
      !local.effective_flags.acr_pool && !local.effective_flags.hosted_prerequisites
    )
    error_message = "Nullable component defaults must not create isolated-only resources in a public deployment."
  }
  assert {
    condition = (
      var.modelDeploymentList[0].model.name == "gpt-5-nano" &&
      var.modelDeploymentList[0].sku.capacity == 100 &&
      length(var.containerAppsList) == 3 &&
      var.containerAppsList[0].target_port == 8080 &&
      var.databaseContainersList[0].indexingPolicy.compositeIndexes[1][2].path == "/_ts"
    )
    error_message = "Typed collection defaults must retain models, target ports and custom Cosmos indexing."
  }
  assert {
    condition = (
      length(local.resource_names) == 18 &&
      length(local.resource_token) == 13 &&
      local.resource_names.aiFoundryAccountName == "aif-${local.caf_stem}" &&
      length(local.resource_names.storageAccountName) <= 24 &&
      can(regex("^[a-z0-9]+$", local.resource_names.storageAccountName))
    )
    error_message = "CAF names must be stable, typed and Azure-legal."
  }
  assert {
    condition = (
      length(local.foundation_metadata) == 64 &&
      var.azureCloud.environment == "public" &&
      local.deployment_context.storage_suffix == "core.windows.net" &&
      output.HOSTED_AGENT_DEPLOYMENT.agent == null &&
      output.HOSTED_AGENT_DEPLOYMENT.foundry == null &&
      output.HOSTED_AGENT_DEPLOYMENT.containerRegistry == null &&
      output.HOSTED_AGENT_DEPLOYMENT.privateBuild.required == false &&
      output.PUBLIC_INGRESS_LIVE == false
    )
    error_message = "The complete output contract must distinguish prepared/deployed/disabled contexts."
  }
}

run "native_json_inputs_preserve_types_and_literal_dollars" {
  command = plan
  # This is the generated adapter format, not a persisted set of envsubst
  # slots. Decode synthetic native JSON without reading a live private tfvars.
  variables {
    networkIsolation                   = jsondecode("false")
    dbDatabaseThroughput               = jsondecode("null")
    allowedIpRanges                    = jsondecode("[]")
    additionalAppConfigurationSettings = jsondecode("[{\"name\":\"CONTRACT_LITERAL\",\"value\":\"\\u0024{LITERAL} \\u0024(command)\",\"contentType\":\"text/plain\"}]")
  }
  assert {
    condition = (
      !var.networkIsolation && var.dbDatabaseThroughput == null &&
      length(var.allowedIpRanges) == 0 &&
      var.additionalAppConfigurationSettings[0].value == "$${LITERAL} $(command)" &&
      var.additionalAppConfigurationSettings[0].contentType == "text/plain"
    )
    error_message = "Generated dollar-escaped native JSON must retain scalar/collection types and literal dollar strings."
  }
}

run "government_cloud_storage_suffix" {
  command = plan
  variables {
    azureCloud = {
      environment        = "usgovernment"
      storage_dns_suffix = "core.usgovcloudapi.net"
    }
  }
  assert {
    condition     = local.deployment_context.storage_suffix == "core.usgovcloudapi.net" && var.acrDnsSuffix == "azurecr.io"
    error_message = "US Government must use its qualified storage suffix, never commercial Azure."
  }
}

run "china_cloud_storage_suffix" {
  command = plan
  variables {
    azureCloud = {
      environment        = "china"
      storage_dns_suffix = "core.chinacloudapi.cn"
    }
  }
  assert {
    condition     = local.deployment_context.storage_suffix == "core.chinacloudapi.cn" && var.acrDnsSuffix == "azurecr.io"
    error_message = "China must use its qualified storage suffix, never commercial Azure."
  }
}

run "acr_override_is_independent_of_storage_cloud" {
  command = plan
  variables {
    acrDnsSuffix = "registry.contract.invalid"
  }
  assert {
    condition     = var.acrDnsSuffix == "registry.contract.invalid" && local.deployment_context.storage_suffix == "core.windows.net"
    error_message = "A custom ACR DNS suffix must not select or invalidate the Azure storage cloud."
  }
}

run "mismatched_cloud_pair_is_rejected" {
  command = plan
  variables {
    azureCloud = {
      environment        = "usgovernment"
      storage_dns_suffix = "core.windows.net"
    }
  }
  expect_failures = [var.azureCloud]
}

run "unsupported_cloud_is_rejected" {
  command = plan
  variables {
    azureCloud = {
      environment        = "unqualified"
      storage_dns_suffix = "core.windows.net"
    }
  }
  expect_failures = [var.azureCloud]
}

run "disabled_services_have_typed_empty_scalars" {
  command = plan
  variables {
    deployAiFoundry         = false
    deployAppConfig         = false
    deployKeyVault          = false
    deployLogAnalytics      = false
    deployAppInsights       = false
    deploySearchService     = false
    deploySpeechService     = false
    deployStorageAccount    = false
    deployCosmosDb          = false
    deployContainerApps     = false
    deployContainerEnv      = false
    deployContainerRegistry = false
    retrievalBackend        = "ai_search"
  }
  assert {
    condition = alltrue([
      output.APP_CONFIG_ENDPOINT == "", output.KEY_VAULT_URI == "",
      output.KEY_VAULT_RESOURCE_ID == "", output.KEY_VAULT_NAME == "",
      output.LOG_ANALYTICS_RESOURCE_ID == "", output.APP_INSIGHTS_RESOURCE_ID == "",
      output.AZURE_SPEECH_ENDPOINT == "", output.AZURE_SPEECH_RESOURCE_ID == "",
      output.AZURE_SPEECH_REGION == "", output.AZURE_SPEECH_RESOURCE_NAME == "",
      output.AZURE_AI_PROJECT_ENDPOINT == "", output.AZURE_AI_PROJECT_RESOURCE_ID == "",
      output.AZURE_CONTAINER_REGISTRY_ENDPOINT == "", output.AZURE_CONTAINER_REGISTRY_RESOURCE_ID == "",
      output.KNOWLEDGE_BASE_ENDPOINT == "", output.KNOWLEDGE_BASE_CONNECTION_ID == "",
      output.PUBLIC_INGRESS_NSG_RESOURCE_ID == "", output.PUBLIC_INGRESS_WAF_POLICY_RESOURCE_ID == "",
      output.CONTAINER_APP_INTERNAL_FQDN == "", output.VNET_RESOURCE_ID == ""
    ])
    error_message = "Disabled optional scalar outputs must be strings, never dynamic null or invented IDs."
  }
  assert {
    condition = (
      jsondecode(jsonencode(output.HOSTED_AGENT_DEPLOYMENT)).enabled == false &&
      jsondecode(jsonencode(output.HOSTED_AGENT_DEPLOYMENT)).workloadEgress.subnets.containerapp == "" &&
      output.DEPLOY_CONTAINER_APPS == false && output.HOSTED_AGENT_PREPARED == false
    )
    error_message = "The hosted handoff must remain a serializable object with real bool/string values."
  }
}

run "legacy_and_explicit_names" {
  command = plan
  variables {
    resourceNamingMode = "legacy"
    resourceToken      = "contract123"
    keyVaultName       = "kv-explicit-contract"
    storageAccountName = "stexplicitcontract"
  }
  assert {
    condition = (
      output.RESOURCE_TOKEN == "contract123" &&
      local.resource_names.aiFoundryAccountName == "aif-contract123" &&
      local.resource_names.containerRegistryName == "crcontract123" &&
      local.resource_names.keyVaultName == "kv-explicit-contract" &&
      local.resource_names.storageAccountName == "stexplicitcontract"
    )
    error_message = "Legacy prefixes and explicit override precedence must be preserved."
  }
}

run "caf_sanitization_and_overrides" {
  command = plan
  variables {
    cafWorkloadName    = "Team_Contract!"
    cafEnvironmentName = "Test_Env"
    cafRegionName      = "Sweden Central"
    cafInstance        = "002"
    appConfigName      = "appcs-explicit-contract"
  }
  assert {
    condition = (
      local.resource_names.aiFoundryAccountName == "aif-teamcontract-testenv-swc-002" &&
      local.resource_names.appConfigName == "appcs-explicit-contract" &&
      !strcontains(local.resource_names.storageAccountName, "-") &&
      length(local.resource_names.keyVaultName) <= 24
    )
    error_message = "CAF token normalization, bounded names and overrides must work together."
  }
}

run "lookup_only_resource_group_default" {
  command = plan
  assert {
    condition = (
      length(azurerm_resource_group.managed) == 0 &&
      length(data.azurerm_resource_group.existing) == 1 &&
      output.AZURE_APP_RESOURCE_GROUP == "rg-contract" &&
      output.AZURE_NETWORK_RESOURCE_GROUP == "rg-contract"
    )
    error_message = "BYO groups must stay lookup-only and shared groups must be deduplicated."
  }
}

run "explicit_resource_group_ownership" {
  command = plan
  variables {
    createResourceGroup            = true
    applicationResourceGroupName   = "rg-contract-app"
    networkResourceGroupName       = "rg-contract-network"
    createApplicationResourceGroup = true
    createNetworkResourceGroup     = false
  }
  assert {
    condition = (
      toset(keys(azurerm_resource_group.managed)) == toset(["rg-contract", "rg-contract-app"]) &&
      toset(keys(data.azurerm_resource_group.existing)) == toset(["rg-contract-network"])
    )
    error_message = "Only explicitly selected groups belong to Terraform's destroy boundary."
  }
}

run "component_precedence_and_byo_suppression" {
  command = plan
  variables {
    networkIsolation             = true
    deployVM                     = true
    existingJumpboxResourceId    = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-contract/providers/Microsoft.Compute/virtualMachines/byo"
    existingBastionResourceId    = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-contract/providers/Microsoft.Network/bastionHosts/byo"
    existingNatGatewayResourceId = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-contract/providers/Microsoft.Network/natGateways/byo"
  }
  assert {
    condition     = !local.effective_flags.jumpbox && !local.effective_flags.bastion && !local.effective_flags.nat
    error_message = "BYO component IDs must suppress implicit creation despite the legacy deployVM default."
  }
  assert {
    condition     = length(random_password.jumpbox) == 0
    error_message = "A BYO jumpbox must not allocate a managed admin password."
  }
}

run "managed_jumpbox_requests_persistent_password_generation" {
  command = plan
  variables {
    networkIsolation = true
    vmAdminPassword  = null
  }
  assert {
    condition     = local.effective_flags.jumpbox && length(random_password.jumpbox) == 1 && alltrue([for password in random_password.jumpbox : password.length >= 24])
    error_message = "A null managed-jumpbox password must request persistent root-owned generation."
  }
}

run "hosted_preparation_is_not_deployment" {
  command = plan
  variables {
    prepareHostedAgent  = true
    deployContainerApps = false
    containerAppsList   = []
  }
  assert {
    condition = (
      output.HOSTED_AGENT_PREPARED && !output.DEPLOY_HOSTED_AGENT &&
      output.HOSTED_AGENT_DEPLOYMENT.agent == null &&
      output.HOSTED_AGENT_DEPLOYMENT.foundry != null &&
      output.HOSTED_AGENT_DEPLOYMENT.containerRegistry != null &&
      !output.HOSTED_AGENT_DEPLOYMENT.privateBuild.required
    )
    error_message = "Preparation must expose foundation context without inventing a deployed hosted version."
  }
}

run "hosted_deploy_handoff_keeps_immutable_version" {
  command = plan
  variables {
    deployHostedAgent   = true
    deployContainerApps = false
    containerAppsList   = []
    hostedAgent = {
      name           = "contract-agent"
      image          = "contract-agent"
      version        = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
      startupCommand = "python -m contract"
      runtime        = { cpu = "2", memory = "4Gi" }
      protocols      = [{ protocol = "responses", version = "2.0.0" }]
    }
  }
  assert {
    condition = (
      output.DEPLOY_HOSTED_AGENT && output.HOSTED_AGENT_PREPARED &&
      output.HOSTED_AGENT_DEPLOYMENT.agent.imageVersion == var.hostedAgent.version &&
      output.HOSTED_AGENT_DEPLOYMENT.agent.runtime.memory == "4Gi" &&
      output.HOSTED_AGENT_DEPLOYMENT.agent.protocols[0].protocol == "responses"
    )
    error_message = "The handoff must retain immutable image/version/runtime/protocol intent, without deploying it."
  }
}

run "invalid_container_environment_combination" {
  command = plan
  variables {
    deployContainerEnv = false
  }
  expect_failures = [terraform_data.root_contract, terraform_data.compute_contract]
}

run "invalid_api_key_prerequisites" {
  command = plan
  variables {
    useCAppAPIKey  = true
    deployKeyVault = false
  }
  expect_failures = [terraform_data.root_contract, terraform_data.compute_contract]
}

run "invalid_hosted_digest" {
  command = plan
  variables {
    deployHostedAgent = true
  }
  expect_failures = [terraform_data.root_contract]
}

run "invalid_bastion_tunneling" {
  command = plan
  variables {
    bastionSkuName         = "Basic"
    bastionEnableTunneling = true
  }
  expect_failures = [terraform_data.root_contract]
}

run "invalid_naming_mode" {
  command = plan
  variables {
    resourceNamingMode = "random"
  }
  expect_failures = [var.resourceNamingMode]
}

run "invalid_fractional_pool_count" {
  command = plan
  variables {
    acrTaskAgentPoolCount = 0.5
  }
  expect_failures = [var.acrTaskAgentPoolCount]
}
