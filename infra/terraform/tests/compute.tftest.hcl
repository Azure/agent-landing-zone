# Offline Azure provider mocks, including the stateful mock-apply runs.
# Password lifecycle runs explicitly use the real local Random provider:
# no Azure operations and no password outputs or diagnostic interpolation.
# These tests do not establish Azure image-pull readiness, private connectivity,
# effective RBAC, OBO/document trimming, or a live post-deploy reprovision.
mock_provider "azurerm" {
  override_during = plan
  mock_resource "azurerm_container_registry" {
    defaults = {
      id           = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.ContainerRegistry/registries/acrtfcompute001"
      login_server = "acrtfcompute001.azurecr.io"
    }
  }
  mock_resource "azurerm_user_assigned_identity" {
    defaults = {
      id           = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.ManagedIdentity/userAssignedIdentities/mockfixture"
      principal_id = "00000000-0000-0000-0000-000000000008"
      client_id    = "00000000-0000-0000-0000-000000000009"
    }
  }
  mock_resource "azurerm_container_app" {
    defaults = {
      id                            = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.App/containerApps/ca-mockfixture"
      custom_domain_verification_id = "00000000000000000000000000000000"
      latest_revision_name          = "ca-mockfixture--azd-mock"
      latest_revision_fqdn          = "ca-mockfixture--azd-mock.fixture.eastus.azurecontainerapps.io"
      location                      = "eastus"
      ingress                       = { fqdn = "ca-mockfixture.fixture.eastus.azurecontainerapps.io" }
      template = {
        revision_suffix = "azd-mock"
        container       = { ephemeral_storage = "1Gi" }
      }
      identity = {
        principal_id = "00000000-0000-0000-0000-000000000010"
        tenant_id    = "00000000-0000-0000-0000-000000000002"
      }
    }
  }
  mock_resource "azurerm_network_interface" {
    defaults = {
      id                          = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.Network/networkInterfaces/nic-mockfixture"
      applied_dns_servers         = []
      internal_domain_name_suffix = "fixture.example.test"
      mac_address                 = "00-11-22-33-44-55"
      private_ip_address          = "10.0.7.4"
      private_ip_addresses        = ["10.0.7.4"]
      virtual_machine_id          = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.Compute/virtualMachines/vm-mockfixture"
      ip_configuration = {
        gateway_load_balancer_frontend_ip_configuration_id = ""
        primary                                            = true
        private_ip_address                                 = "10.0.7.4"
      }
    }
  }
  mock_resource "azurerm_windows_virtual_machine" {
    defaults = {
      id                                = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.Compute/virtualMachines/vm-mockfixture"
      allow_extension_operations        = true
      automatic_updates_enabled         = true
      enable_automatic_updates          = true
      disk_controller_type              = "SCSI"
      hotpatching_enabled               = false
      os_managed_disk_id                = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.Compute/disks/os-mockfixture"
      patch_assessment_mode             = "ImageDefault"
      patch_mode                        = "AutomaticByOS"
      private_ip_address                = "10.0.7.4"
      private_ip_addresses              = ["10.0.7.4"]
      public_ip_address                 = ""
      public_ip_addresses               = []
      provision_vm_agent                = true
      virtual_machine_id                = "00000000-0000-0000-0000-000000000013"
      vm_agent_platform_updates_enabled = false
      os_disk = {
        id   = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.Compute/disks/os-mockfixture"
        name = "os-mockfixture"
      }
      identity = {
        principal_id = "00000000-0000-0000-0000-000000000011"
        tenant_id    = "00000000-0000-0000-0000-000000000002"
      }
    }
  }
  mock_resource "azurerm_route_table" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.Network/routeTables/rt-mockfixture"
    }
  }
  mock_data "azurerm_client_config" {
    defaults = {
      subscription_id = "00000000-0000-0000-0000-000000000001"
      tenant_id       = "00000000-0000-0000-0000-000000000002"
      object_id       = "00000000-0000-0000-0000-000000000003"
      client_id       = "00000000-0000-0000-0000-000000000004"
    }
  }
  mock_data "azurerm_resource_group" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute"
      location = "eastus"
    }
  }
}
mock_provider "azapi" {
  override_during = plan
  mock_data "azapi_resource" {
    defaults = {
      exists = false
      output = null
    }
  }
  mock_resource "azapi_resource" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.CognitiveServices/accounts/mockfixture"
      location = "eastus"
      output = {
        properties = {
          primaryEndpoints   = { blob = "https://tfcompute.blob.core.windows.net/" }
          documentEndpoint   = "https://tfcompute.documents.azure.com:443/"
          endpoint           = "https://tfcompute.azconfig.io"
          ConnectionString   = "InstrumentationKey=00000000-0000-0000-0000-000000000005;IngestionEndpoint=https://eastus.in.applicationinsights.azure.com/"
          InstrumentationKey = "00000000-0000-0000-0000-000000000005"
          internalId         = "00112233445566778899aabbccddeeff"
        }
      }
    }
  }
}
mock_provider "modtm" {}
mock_provider "random" {}
mock_provider "time" {}

provider "random" {
  alias = "password_test"
}

override_resource {
  target          = azapi_resource.container_environment
  override_during = plan
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.App/managedEnvironments/cae-mockfixture"
    identity = {
      principal_id = "00000000-0000-0000-0000-000000000012"
      tenant_id    = "00000000-0000-0000-0000-000000000002"
    }
    output = {
      properties = { defaultDomain = "fixture.eastus.azurecontainerapps.io", staticIp = "192.0.2.1" }
    }
  }
}

# Preserve producer resource namespaces: native SQL-role validation must see a
# Cosmos account, never the generic Cognitive Services mock's fallback ID.
override_resource {
  target          = azapi_resource.application_cosmos
  override_during = plan
  values = {
    id     = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.DocumentDB/databaseAccounts/cosmostfcompute"
    output = { properties = { documentEndpoint = "https://cosmostfcompute.documents.azure.com:443/" } }
  }
}
override_resource {
  target          = azapi_resource.foundry_cosmos
  override_during = plan
  values = {
    id     = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.DocumentDB/databaseAccounts/cosmosmemory"
    output = { properties = { documentEndpoint = "https://cosmosmemory.documents.azure.com:443/" } }
  }
}

# App Configuration publication must consume the actual executor grant's
# completion ID; other grants and the publisher must not produce readiness.
override_resource {
  target          = module.application_configuration[0].azapi_resource.this
  override_during = plan
  values = {
    id     = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.AppConfiguration/configurationStores/configtfcompute"
    output = { properties = { endpoint = "https://configtfcompute.azconfig.io" } }
  }
}
override_resource {
  target          = azurerm_role_assignment.app_config_executor["this"]
  override_during = plan
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.AppConfiguration/configurationStores/configtfcompute/providers/Microsoft.Authorization/roleAssignments/00000000-0000-0000-0000-000000000014"
  }
}

# Full-root plans still validate the network AVM's resource-ID contracts.
# Keep distinct, correctly typed IDs for the exact compute subnet purposes.
override_resource {
  target          = module.network_vnet[0].azapi_resource.vnet
  override_during = plan
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.Network/virtualNetworks/vnet-fixture"
  }
}
override_resource {
  target          = module.network_subnet["jumpbox"].azapi_resource.subnet[0]
  override_during = plan
  values = {
    id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.Network/virtualNetworks/vnet-fixture/subnets/jumpbox-subnet"
    location = "eastus"
  }
}
override_resource {
  target          = module.network_subnet["acaEnvironment"].azapi_resource.subnet[0]
  override_during = plan
  values = {
    id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.Network/virtualNetworks/vnet-fixture/subnets/aca-environment-subnet"
    location = "eastus"
  }
}
override_resource {
  target          = module.network_subnet["devopsBuildAgents"].azapi_resource.subnet[0]
  override_during = plan
  values = {
    id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.Network/virtualNetworks/vnet-fixture/subnets/devops-build-agents-subnet"
    location = "eastus"
  }
}

variables {
  subscriptionId        = "00000000-0000-0000-0000-000000000001"
  tenantId              = "00000000-0000-0000-0000-000000000002"
  principalId           = "00000000-0000-0000-0000-000000000003"
  environmentName       = "tf-compute"
  resourceGroupName     = "rg-tf-compute"
  location              = "eastus"
  resourceToken         = "tfcompute001"
  containerRegistryName = "acrtfcompute001"
  vnetName              = "vnet-fixture"
  dbAccountName         = "cosmostfcompute"
  containerEnvName      = "cae-mockfixture"
  appConfigName         = "configtfcompute"
  # Short, valid connection names isolate this domain from service naming.
  aiFoundryAccountName       = "aifcompute"
  aiFoundryCosmosDbName      = "cosmosmemory"
  aiFoundrySearchServiceName = "searchmemory"
  searchServiceName          = "searchfixture"
  storageAccountName         = "stfixture"
  deployJumpbox              = false
  deployBastion              = false
  deployNatGateway           = false
  deploySoftware             = false
  deployGroundingWithBing    = false
  # Exercise supported external egress; firewall policy provisioning belongs
  # to network tests. This is not outbound-readiness/installer evidence.
  deployAzureFirewall           = false
  hubIntegrationEgressNextHopIp = "10.0.4.4"
  # Exercise the supported policy-owned DNS mode; managed DNS payloads and
  # links are validated by the networking suite, not by generic compute mocks.
  policyManagedPrivateDns = true
  # Accounts/native SQL authorization remain enabled; service-owned container
  # payload/index-policy parity is outside this focused compute fixture.
  databaseContainersList = []
}

run "public_classic_foundation_and_least_privilege" {
  command = plan
  assert {
    condition = (
      toset(keys(local.container_apps)) == toset(["orchestrator", "frontend", "dataingest"]) &&
      length(azurerm_container_app.shell) == 3 &&
      length(azapi_resource.acr_agent_pool) == 0 &&
      length(azurerm_windows_virtual_machine.jumpbox) == 0 &&
      length(random_password.jumpbox) == 0 &&
      length(azurerm_user_assigned_identity.compute) == 0 &&
      module.container_registry["this"].resource.sku == "Basic"
    )
    error_message = "Public classic mode must create only actual ACA shells, a Basic registry, and no isolated-only compute."
  }
  assert {
    condition = (
      local.container_apps.frontend.image == local.compute_placeholder_image &&
      azurerm_container_app.shell["frontend"].ingress[0].target_port == 8080 &&
      !azurerm_container_app.shell["frontend"].ingress[0].allow_insecure_connections &&
      azurerm_container_app.shell["frontend"].dapr[0].app_port == 8080 &&
      azurerm_container_app.shell["frontend"].identity[0].type == "SystemAssigned" &&
      !contains(keys(local.compute_app_environment.frontend), "AZURE_CLIENT_ID")
    )
    error_message = "Shell ingress/Dapr/identity bootstrap must preserve target-port defaults, TLS and SAMI behavior."
  }
  assert {
    condition = (
      contains(keys(local.rbac_assignments), "app:frontend:storage:StorageBlobDelegator") &&
      !contains(keys(local.rbac_assignments), "app:frontend:search:SearchIndexDataReader") &&
      !contains(keys(local.cosmos_application_grants), "app:frontend") &&
      contains(keys(local.cosmos_application_grants), "app:orchestrator") &&
      !contains([for grant in concat(local.executor_grants, local.app_grants, local.cross_service_grants) : grant.role], "CosmosDBBuiltInDataContributor")
    )
    error_message = "Apps receive only requested conditional grants; Cosmos SQL roles must never become ARM RBAC."
  }
  assert {
    condition = (
      azapi_resource.container_environment["this"].body.properties.appLogsConfiguration.destination == null &&
      length(azapi_resource.container_environment["this"].body.properties.workloadProfiles) == 2 &&
      azapi_resource.container_environment["this"].body.properties.vnetConfiguration == null &&
      length(azapi_resource.foundry_memory) == 1 &&
      endswith(azapi_resource.foundry_memory["this"].body.properties.scope, "/dbs/enterprise_memory") &&
      azurerm_role_assignment.foundry_workspace_storage["this"].condition_version == "2.0" &&
      strcontains(azurerm_role_assignment.foundry_workspace_storage["this"].condition, "StringLikeIgnoreCase '*-azureml-agent'") &&
      strcontains(azurerm_role_assignment.foundry_workspace_storage["this"].condition, local.foundry_context.project_workspace_id)
    )
    error_message = "Environment logging/profiles and service-owned enterprise-memory authorization must retain their contracts."
  }
  assert {
    condition = (
      local.compute_context.environment_principal_id == azapi_resource.container_environment["this"].identity[0].principal_id &&
      local.compute_context.environment_principal_id == "00000000-0000-0000-0000-000000000012" &&
      azapi_resource.foundation_setting[jsonencode(["CONTAINER_ENV_PRINCIPAL_ID", "agent-lz"])].body.properties.value == local.compute_context.environment_principal_id &&
      length(local.app_config_authorization_ready) == 1 &&
      one(local.app_config_authorization_ready) == azurerm_role_assignment.app_config_executor["this"].id &&
      terraform_data.app_config_authorization[0].input == local.app_config_authorization_ready &&
      azurerm_role_assignment.app_config_executor["this"].scope == local.data_context.app_config.id &&
      azurerm_role_assignment.app_config_executor["this"].principal_id == var.principalId &&
      !contains(keys(azurerm_role_assignment.foundation), "executor:app_config:AppConfigurationDataOwner") &&
      contains(keys(local.rbac_assignments), "executor:app_config:AppConfigurationDataOwner") &&
      azurerm_role_assignment.app_config_executor["this"].name == uuidv5("url", lower("${local.foundation_rbac_assignments["executor:app_config:AppConfigurationDataOwner"].scope}|${var.principalId}|${local.foundation_rbac_assignments["executor:app_config:AppConfigurationDataOwner"].role_definition_id}"))
    )
    error_message = "SAMI bootstrap must publish the actual CAE principal and wait on only the completed store-scoped executor Data Owner grant."
  }
}

run "isolated_registry_pool_jumpbox_and_uai" {
  command = plan
  variables {
    networkIsolation = true
    useUAI           = true
    deployJumpbox    = true
    deploySoftware   = true
    # Synthetic test fixture, never an operator credential.
    vmAdminPassword       = "OfflineMock-NotARealPassword-123!"
    vmName                = "fixture-jumpbox-long-name"
    acrTaskAgentPoolCount = 0
    useZoneRedundancy     = true
  }
  assert {
    condition = (
      module.container_registry["this"].resource.sku == "Premium" &&
      !module.container_registry["this"].resource.public_network_access_enabled &&
      module.container_registry["this"].resource.data_endpoint_enabled &&
      length(azapi_resource.acr_agent_pool) == 1 &&
      azapi_resource.acr_agent_pool["this"].body.properties.count == 0 &&
      azapi_resource.acr_agent_pool["this"].body.properties.virtualNetworkSubnetResourceId == local.subnet_ids.devopsBuildAgents
    )
    error_message = "Isolated builds require a private Premium registry and the exact build subnet, including zero-sized pools."
  }
  assert {
    condition = (
      azapi_resource.container_environment["this"].body.properties.vnetConfiguration.internal &&
      azapi_resource.container_environment["this"].body.properties.vnetConfiguration.infrastructureSubnetId == local.subnet_ids.acaEnvironment &&
      azurerm_windows_virtual_machine.jumpbox["this"].name == "fixture-jumpbox" &&
      azurerm_windows_virtual_machine.jumpbox["this"].os_disk[0].disk_size_gb == 250 &&
      azurerm_windows_virtual_machine.jumpbox["this"].os_disk[0].storage_account_type == "Standard_LRS" &&
      !azurerm_windows_virtual_machine.jumpbox["this"].encryption_at_host_enabled &&
      azurerm_windows_virtual_machine.jumpbox["this"].identity[0].type == "UserAssigned" &&
      contains(keys(local.compute_app_environment.frontend), "AZURE_CLIENT_ID")
    )
    error_message = "Private environment/jumpbox/UAI contracts must not silently use public or differently sized resources."
  }
  assert {
    condition = (
      endswith(jsondecode(azurerm_virtual_machine_extension.jumpbox_bootstrap["this"].settings).fileUris[0], "/refs/tags/${local.compute_manifest.infra.source.tag}/install.ps1") &&
      strcontains(jsondecode(azurerm_virtual_machine_extension.jumpbox_bootstrap["this"].settings).commandToExecute, "-AzureResourceGroupName \"rg-tf-compute\"")
    )
    error_message = "Jumpbox bootstrap must reuse the manifest-pinned installer and safely quote destination arguments."
  }
  assert {
    condition = (
      length(azurerm_cosmosdb_sql_role_assignment.application) == 4 &&
      length(azurerm_role_assignment.container_pull) == 3 &&
      !contains(keys(local.foundation_rbac_assignments), "app:frontend:registry:AcrPull") &&
      contains(keys(local.rbac_assignments), "app:frontend:registry:AcrPull") &&
      contains(keys(local.rbac_assignments), "executor:registry:AcrPull") &&
      contains(keys(local.rbac_assignments), "jumpbox:root:Reader") &&
      contains(keys(local.rbac_assignments), "jumpbox:registry:ContainerRegistryTasksContributor") &&
      !contains([for grant in concat(local.executor_grants, local.jumpbox_grants, local.jumpbox_destination_grants, local.app_grants, local.cross_service_grants) : grant.role], "Owner")
    )
    error_message = "Jumpbox bootstrap needs scoped discovery/build grants, never subscription Owner."
  }
  assert {
    condition = (
      local.compute_context.environment_principal_id == azurerm_user_assigned_identity.compute["environment"].principal_id &&
      local.compute_context.environment_principal_id != azapi_resource.container_environment["this"].identity[0].principal_id &&
      azapi_resource.foundation_setting[jsonencode(["CONTAINER_ENV_PRINCIPAL_ID", "agent-lz"])].body.properties.value == local.compute_context.environment_principal_id &&
      length(local.app_config_authorization_ready) == 1 &&
      one(local.app_config_authorization_ready) == azurerm_role_assignment.app_config_executor["this"].id
    )
    error_message = "UAI bootstrap must publish the selected environment UAI principal, not the environment's SAMI field or application identities."
  }
}

run "store_authorization_does_not_depend_on_aca_grants" {
  command = plan
  plan_options {
    target = [terraform_data.app_config_authorization]
  }
  # If readiness traverses any app/grant, the intentionally foreign live-app
  # read fails the ownership guard. Executor readiness must not visit it.
  override_data {
    target = data.azapi_resource.compute_app
    values = {
      exists = true
      output = {
        tags       = { "azd-env-name" = "foreign-environment" }
        properties = { template = { containers = [] } }
      }
    }
  }
  assert {
    condition = (
      length(local.app_config_authorization_ready) == 1 &&
      one(local.app_config_authorization_ready) == azurerm_role_assignment.app_config_executor["this"].id &&
      terraform_data.app_config_authorization[0].input == local.app_config_authorization_ready
    )
    error_message = "Executor readiness must depend only on its completed store grant, not any ACA app/application-grant collection."
  }
}

run "disabled_store_and_environment_publish_no_authorization_or_principal" {
  command = plan
  variables {
    deployAppConfig     = false
    deployContainerApps = false
    deployContainerEnv  = false
    useUAI              = true
  }
  assert {
    condition = (
      local.compute_context.environment_principal_id == "" &&
      !contains(keys(azurerm_user_assigned_identity.compute), "environment") &&
      length(local.app_config_authorization_ready) == 0 &&
      length(azurerm_role_assignment.app_config_executor) == 0 &&
      !contains(keys(azurerm_role_assignment.foundation), "executor:app_config:AppConfigurationDataOwner") &&
      length(terraform_data.app_config_authorization) == 0 &&
      length(azapi_resource.foundation_setting) == 0
    )
    error_message = "Disabled producers must expose an empty principal and no authorization handle or publisher, including UAI mode without an environment."
  }
}

run "container_env_mode_keeps_store_authorization_separate_from_publication" {
  command = plan
  variables {
    appRuntimeConfigurationMode = "containerEnv"
  }
  assert {
    condition = (
      length(local.app_config_authorization_ready) == 1 &&
      one(local.app_config_authorization_ready) == azurerm_role_assignment.app_config_executor["this"].id &&
      length(terraform_data.app_config_authorization) == 0 &&
      length(azapi_resource.foundation_setting) == 0 &&
      local.compute_context.environment_principal_id == azapi_resource.container_environment["this"].identity[0].principal_id
    )
    error_message = "An enabled store retains its real executor grant, but containerEnv mode must not create ARM settings or publication-readiness consumers."
  }
}

run "hosted_prerequisites_without_aca_placeholders" {
  command = plan
  variables {
    prepareHostedAgent  = true
    deployContainerApps = false
    deployContainerEnv  = false
    containerAppsList   = []
  }
  assert {
    condition = (
      length(local.container_apps) == 0 && length(azurerm_container_app.shell) == 0 &&
      length(azapi_resource.container_environment) == 0 &&
      local.compute_context.environment_principal_id == "" &&
      local.hosted_registry.pull_role == "AcrPull" &&
      contains(keys(local.rbac_assignments), "cross:project_registry") &&
      contains(keys(local.rbac_assignments), "executor:project:AzureAIProjectManager") &&
      !anytrue([for key in keys(local.rbac_assignments) : startswith(key, "hosted-instance:")])
    )
    error_message = "Hosted preparation creates prerequisites, not ACA apps, versions or invented runtime principals."
  }
}

run "external_abac_registry_uses_repository_reader" {
  command = plan
  variables {
    prepareHostedAgent                             = true
    deployContainerApps                            = false
    deployContainerEnv                             = false
    containerAppsList                              = []
    deployContainerRegistry                        = false
    hostedAgentContainerRegistryResourceId         = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-registry-fixture/providers/Microsoft.ContainerRegistry/registries/externalfixture"
    hostedAgentContainerRegistryEndpoint           = "externalfixture.azurecr.io"
    hostedAgentContainerRegistryRoleAssignmentMode = "rbac-abac"
    grantHostedAgentProjectManager                 = false
  }
  assert {
    condition = (
      length(module.container_registry) == 0 &&
      local.registry_context.id == "" &&
      local.hosted_registry.resource_id == var.hostedAgentContainerRegistryResourceId &&
      local.hosted_registry.endpoint == "externalfixture.azurecr.io" &&
      local.hosted_registry.pull_role == "ContainerRegistryRepositoryReader" &&
      endswith(local.rbac_assignments["cross:project_registry"].role_definition_id, "b93aa761-3e63-49ed-ac28-beffa264f7ac") &&
      !contains(keys(local.rbac_assignments), "executor:project:AzureAIProjectManager")
    )
    error_message = "An external ABAC registry must be read-only infrastructure and use Repository Reader, not AcrPull or an executor project-manager grant."
  }
}

run "custom_app_definition_port_resources_dapr_and_roles" {
  command = plan
  variables {
    useUAI                             = true
    appRuntimeConfigurationMode        = "containerEnv"
    additionalAppConfigurationSettings = [{ name = "LOG_LEVEL", value = "DEBUG" }]
    containerAppsList = [{
      name           = "ca-custom"
      service_name   = "worker"
      canonical_name = "CUSTOM_WORKER"
      external       = false
      profile_name   = "Consumption"
      min_replicas   = 0
      max_replicas   = 2
      target_port    = 9090
      cpu            = 0.75
      memory         = "1.5Gi"
      dapr           = { enabled = true, enableApiLogging = true }
      roles          = ["AcrPull", "SearchIndexDataReader", "SearchIndexDataReader"]
    }]
  }
  assert {
    condition = (
      keys(local.container_apps) == ["worker"] &&
      azurerm_container_app.shell["worker"].name == "ca-custom" &&
      azurerm_container_app.shell["worker"].ingress[0].target_port == 9090 &&
      azurerm_container_app.shell["worker"].dapr[0].app_port == 9090 &&
      azurerm_container_app.shell["worker"].template[0].container[0].cpu == 0.75 &&
      azapi_update_resource.container_app_dapr_logging["worker"].body.properties.configuration.dapr.enableApiLogging &&
      local.compute_app_environment.worker.LOG_LEVEL.value == "DEBUG" &&
      contains(keys(local.rbac_assignments), "app:worker:search:SearchIndexDataReader") &&
      length([for key in keys(local.rbac_assignments) : key if key == "app:worker:search:SearchIndexDataReader"]) == 1 &&
      !contains(keys(local.cosmos_application_grants), "app:worker")
    )
    error_message = "Custom app definitions must preserve workload shape, deduplicate grants and not acquire unrequested conversation data access."
  }
}

run "invalid_external_registry_binding_rejected" {
  command = plan
  variables {
    prepareHostedAgent                     = true
    deployContainerRegistry                = false
    hostedAgentContainerRegistryResourceId = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-registry-fixture/providers/Microsoft.ContainerRegistry/registries/expectedfixture"
    hostedAgentContainerRegistryEndpoint   = "differentfixture.azurecr.io"
  }
  expect_failures = [terraform_data.compute_contract]
}

run "container_env_filters_active_label_before_flattening_names" {
  command = plan
  variables {
    appRuntimeConfigurationMode = "containerEnv"
    appConfigLabel              = "Active"
    additionalAppConfigurationSettings = [
      { name = "LOG_LEVEL", value = "WARN", label = "Active" },
      { name = "LOG_LEVEL", value = "ERROR", label = "staging" },
      { name = "LOG_LEVEL", value = "TRACE", label = "active" },
      { name = "MISSING_LABEL", value = "defaulted" },
      { name = "NULL_LABEL", value = "defaulted-null", label = null },
      { name = "UNLABELED_ONLY", value = "unlabeled", label = "" },
      { name = "INACTIVE_ONLY", value = "inactive", label = "staging" },
      { name = "CASE_ONLY", value = "wrong-case", label = "active" },
    ]
    containerAppsList = [{
      name     = "ca-label-fixture", service_name = "worker", canonical_name = "CUSTOM_WORKER"
      external = false, profile_name = "Consumption", min_replicas = 0, max_replicas = 1, roles = []
    }]
  }
  assert {
    condition = (
      local.compute_app_environment.worker.LOG_LEVEL.value == "WARN" &&
      local.compute_app_environment.worker.MISSING_LABEL.value == "defaulted" &&
      local.compute_app_environment.worker.NULL_LABEL.value == "defaulted-null" &&
      !contains(keys(local.compute_runtime_environment), "UNLABELED_ONLY") &&
      !contains(keys(local.compute_app_environment.worker), "INACTIVE_ONLY") &&
      !contains(keys(local.compute_app_environment.worker), "CASE_ONLY") &&
      one([for env in azurerm_container_app.shell["worker"].template[0].container[0].env : env.value if env.name == "LOG_LEVEL"]) == "WARN"
    )
    error_message = "Flatten only exact active-label settings: default null/missing labels, but never merge explicit empty, inactive or differently cased labels."
  }
}

run "invalid_profile_rejected" {
  command = plan
  variables {
    containerAppsList = [{
      service_name = "worker", canonical_name = "CUSTOM_WORKER", external = false
      profile_name = "not-a-selected-profile", min_replicas = 0, max_replicas = 1, roles = []
    }]
  }
  expect_failures = [terraform_data.compute_contract]
}

run "negative_pool_count_rejected" {
  command = plan
  variables {
    acrTaskAgentPoolCount = -1
  }
  expect_failures = [var.acrTaskAgentPoolCount]
}

run "unrecognized_app_role_rejected" {
  command = plan
  variables {
    containerAppsList = [{
      service_name = "worker", canonical_name = "CUSTOM_WORKER", external = false
      profile_name = "Consumption", min_replicas = 0, max_replicas = 1, roles = ["Owner"]
    }]
  }
  expect_failures = [terraform_data.compute_contract]
}

run "unsafe_bootstrap_arguments_rejected" {
  command = plan
  variables {
    environmentName  = "unsafe\"fixture"
    networkIsolation = true
    deployJumpbox    = true
    deploySoftware   = true
    vmAdminPassword  = "OfflineMock-NotARealPassword-123!"
  }
  expect_failures = [terraform_data.compute_contract]
}

# Deliberately use one resource key across these final runs to exercise real
# Terraform lifecycle planning against a mocked state, not just string matching.
run "seed_published_image_in_mock_state" {
  command = apply
  variables {
    deployAiFoundry         = false
    deployAppConfig         = false
    deployKeyVault          = false
    deploySearchService     = false
    deployStorageAccount    = false
    deployCosmosDb          = false
    deployContainerRegistry = false
    deployAppInsights       = false
    deployLogAnalytics      = false
    retrievalBackend        = "ai_search"
    containerAppsList = [{
      name     = "ca-preserve", service_name = "worker", canonical_name = "CUSTOM_WORKER"
      external = false, profile_name = "Consumption", min_replicas = 0, max_replicas = 1
      roles    = []
      image    = "externalfixture.azurecr.io/worker@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }]
  }
  assert {
    condition     = azurerm_container_app.shell["worker"].template[0].container[0].image == "externalfixture.azurecr.io/worker@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    error_message = "The initial shell must honor an explicit immutable image."
  }
}

run "reprovision_keeps_image_runtime_refs_and_reconciles_security" {
  command = plan
  variables {
    deployAiFoundry         = false
    deployAppConfig         = false
    deployKeyVault          = false
    deploySearchService     = false
    deployStorageAccount    = false
    deployCosmosDb          = false
    deployContainerRegistry = false
    deployAppInsights       = false
    deployLogAnalytics      = false
    retrievalBackend        = "ai_search"
    containerAppsList = [{
      name        = "ca-preserve", service_name = "worker", canonical_name = "CUSTOM_WORKER"
      external    = false, profile_name = "Consumption", min_replicas = 0, max_replicas = 2
      target_port = 9191, cpu = 0.75, memory = "1.5Gi", roles = []
      image       = "externalfixture.azurecr.io/worker:ignored-foundation-image"
    }]
  }
  override_data {
    target = data.azapi_resource.compute_app["worker"]
    values = {
      exists = true
      output = {
        id   = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.App/containerApps/ca-preserve"
        tags = { "azd-env-name" = "tf-compute", "azd-service-name" = "worker" }
        properties = {
          template = {
            containers = [{
              name  = "worker"
              image = "externalfixture.azurecr.io/worker@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
              env = [
                { name = "CUSTOM_RUNTIME", value = "keep" },
                { name = "SECRET_REF", secretRef = "audit" },
                { name = "AZURE_CLIENT_ID", value = "stale-uai-must-not-survive-sami" },
                { name = "AZURE_TENANT_ID", value = "wrong-tenant-must-be-corrected" },
              ]
            }]
          }
          configuration = {
            registries = [
              { server = "externalfixture.azurecr.io", identity = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-tf-compute/providers/Microsoft.ManagedIdentity/userAssignedIdentities/stale" },
              { server = "unrelated.example.test", identity = "system" },
            ]
            secrets = [{
              name = "audit", keyVaultUrl = "https://vaulttfcompute.vault.azure.net/secrets/audit", identity = "System"
            }]
          }
        }
      }
    }
  }
  assert {
    condition = (
      azurerm_container_app.shell["worker"].template[0].container[0].image == "externalfixture.azurecr.io/worker@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" &&
      azurerm_container_app.shell["worker"].template[0].container[0].cpu == 0.75 &&
      azurerm_container_app.shell["worker"].template[0].max_replicas == 2 &&
      azurerm_container_app.shell["worker"].ingress[0].target_port == 9191 &&
      !azurerm_container_app.shell["worker"].ingress[0].allow_insecure_connections &&
      azurerm_container_app.shell["worker"].identity[0].type == "SystemAssigned"
    )
    error_message = "Image preservation must not suppress infrastructure resources, scaling, network/TLS or managed identity reconciliation."
  }
  assert {
    condition = (
      local.compute_app_environment.worker.CUSTOM_RUNTIME.value == "keep" &&
      local.compute_app_environment.worker.SECRET_REF.secret_ref == "audit" &&
      local.compute_app_environment.worker.AZURE_TENANT_ID.value == var.tenantId &&
      !contains(keys(local.compute_app_environment.worker), "AZURE_CLIENT_ID") &&
      length(azurerm_container_app.shell["worker"].secret) == 1 &&
      one([for registry in azurerm_container_app.shell["worker"].registry : registry.identity if registry.server == "externalfixture.azurecr.io"]) == "system" &&
      length(azurerm_container_app.shell["worker"].registry) == 2
    )
    error_message = "Preserve runtime env/Key Vault refs and unrelated registries, but correct stale tenant/client and managed pull identity."
  }
}

run "inline_secrets_fail_closed_before_reprovision" {
  command = plan
  variables {
    containerAppsList = [{
      name     = "ca-preserve", service_name = "worker", canonical_name = "CUSTOM_WORKER"
      external = false, profile_name = "Consumption", min_replicas = 0, max_replicas = 1, roles = []
    }]
  }
  override_data {
    target = data.azapi_resource.compute_app["worker"]
    values = {
      exists = true
      output = {
        tags = { "azd-env-name" = "tf-compute", "azd-service-name" = "worker" }
        properties = {
          template      = { containers = [{ name = "worker", env = [] }] }
          configuration = { registries = [], secrets = [{ name = "unrecoverable-inline-value" }] }
        }
      }
    }
  }
  expect_failures = [azurerm_container_app.shell["worker"]]
}

run "project_disabled_suppresses_project_and_post_capability_grants" {
  command = plan
  variables {
    deployAfProject = false
  }
  assert {
    condition = (
      length(local.foundry_authorization_ready) == 0 &&
      length(terraform_data.foundry_capability_ready) == 0 &&
      length(azurerm_role_assignment.foundry_workspace_storage) == 0 &&
      length(azapi_resource.foundry_memory) == 0 &&
      length([
        for key in keys(local.rbac_assignments) : key
        if startswith(key, "cross:project_") || startswith(key, "cross:associated_") || startswith(key, "post:") || startswith(key, "executor:project:")
      ]) == 0 &&
      contains(keys(local.rbac_assignments), "executor:foundry:CognitiveServicesOpenAIUser") &&
      contains(keys(local.rbac_assignments), "cross:search_foundry")
    )
    error_message = "Disabling the project must suppress every project/bootstrap/post-capability grant, but retain applicable account-level authorization."
  }
}

run "byo_cosmos_sql_targets_the_exported_foreign_account" {
  command = plan
  variables {
    aiFoundryCosmosDBAccountResourceId = "/subscriptions/00000000-0000-0000-0000-000000000099/resourceGroups/rg-shared/providers/Microsoft.DocumentDB/databaseAccounts/sharedcosmos"
  }
  override_data {
    target = data.azapi_resource.foundry_existing_dependency["cosmos"]
    values = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000099/resourceGroups/rg-shared/providers/Microsoft.DocumentDB/databaseAccounts/sharedcosmos"
      exists   = true
      location = "eastus"
      output   = { properties = { documentEndpoint = "https://sharedcosmos.documents.azure.com:443/" } }
    }
  }
  assert {
    condition = (
      local.foundry_dependencies.cosmos_id == var.aiFoundryCosmosDBAccountResourceId &&
      split("/", local.foundry_dependencies.cosmos_id)[2] != var.subscriptionId &&
      azapi_resource.foundry_memory["this"].parent_id == local.foundry_dependencies.cosmos_id &&
      azapi_resource.foundry_memory["this"].body.properties.scope == "${local.foundry_dependencies.cosmos_id}/dbs/enterprise_memory" &&
      azapi_resource.foundry_memory["this"].body.properties.roleDefinitionId == "${local.foundry_dependencies.cosmos_id}/sqlRoleDefinitions/${local.identity_roles.CosmosDBBuiltInDataContributor.guid}" &&
      azapi_resource.foundry_memory["this"].body.properties.principalId == local.foundry_context.project_principal_id &&
      local.foundation_rbac_assignments["cross:associated_cosmos"].scope == local.foundry_dependencies.cosmos_id &&
      local.foundation_rbac_assignments["cross:associated_cosmos"].role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000099/providers/Microsoft.Authorization/roleDefinitions/${local.identity_roles.CosmosDBOperator.guid}"
    )
    error_message = "Native SQL parent/role/database scope and ARM authorization must use the exported actual BYO account ID, including its foreign subscription."
  }
}

# Real local Random state, Azure mocks only. A replacement random_password
# result is unknown during plan; the second run must instead retain a known
# sensitive result from the first apply, even when the VM size changes.
run "seed_generated_jumpbox_password_in_state" {
  command = apply
  providers = {
    azurerm = azurerm
    azapi   = azapi
    modtm   = modtm
    random  = random.password_test
    time    = time
  }
  variables {
    networkIsolation        = true
    deployJumpbox           = true
    vmAdminPassword         = null
    deployAiFoundry         = false
    deployAppConfig         = false
    deployKeyVault          = false
    deploySearchService     = false
    deployStorageAccount    = false
    deployCosmosDb          = false
    deployContainerRegistry = false
    deployContainerApps     = false
    deployContainerEnv      = false
    deployAppInsights       = false
    deployLogAnalytics      = false
    retrievalBackend        = "ai_search"
  }
  assert {
    condition = (
      length(random_password.jumpbox) == 1 &&
      length(random_password.jumpbox[0].result) == random_password.jumpbox[0].length &&
      random_password.jumpbox[0].length >= 24 &&
      issensitive(random_password.jumpbox[0].result) &&
      can(regex("[a-z]", random_password.jumpbox[0].result)) &&
      can(regex("[A-Z]", random_password.jumpbox[0].result)) &&
      can(regex("[0-9]", random_password.jumpbox[0].result)) &&
      can(regex("[!#$%&*+=?@^_-]", random_password.jumpbox[0].result)) &&
      azurerm_windows_virtual_machine.jumpbox["this"].admin_password == random_password.jumpbox[0].result &&
      issensitive(azurerm_windows_virtual_machine.jumpbox["this"].admin_password)
    )
    error_message = "An absent managed-jumpbox password must be generated once with Windows-compatible complexity and remain sensitive."
  }
}

run "reprovision_retains_generated_jumpbox_password" {
  command = plan
  providers = {
    azurerm = azurerm
    azapi   = azapi
    modtm   = modtm
    random  = random.password_test
    time    = time
  }
  variables {
    networkIsolation        = true
    deployJumpbox           = true
    vmAdminPassword         = null
    vmSize                  = "Standard_D4s_v3"
    deployAiFoundry         = false
    deployAppConfig         = false
    deployKeyVault          = false
    deploySearchService     = false
    deployStorageAccount    = false
    deployCosmosDb          = false
    deployContainerRegistry = false
    deployContainerApps     = false
    deployContainerEnv      = false
    deployAppInsights       = false
    deployLogAnalytics      = false
    retrievalBackend        = "ai_search"
  }
  assert {
    condition = (
      length(random_password.jumpbox) == 1 &&
      length(random_password.jumpbox[0].result) == random_password.jumpbox[0].length &&
      random_password.jumpbox[0].length >= 24 &&
      random_password.jumpbox[0].keepers == null &&
      issensitive(random_password.jumpbox[0].result) &&
      azurerm_windows_virtual_machine.jumpbox["this"].admin_password == random_password.jumpbox[0].result &&
      azurerm_windows_virtual_machine.jumpbox["this"].size == "Standard_D4s_v3"
    )
    error_message = "A repeated plan must retain the already-known sensitive password in state without rotation, while VM changes still reconcile."
  }
}

run "supplied_password_overrides_generated_password_in_state" {
  command = apply
  providers = {
    azurerm = azurerm
    azapi   = azapi
    modtm   = modtm
    random  = random.password_test
    time    = time
  }
  variables {
    networkIsolation        = true
    deployJumpbox           = true
    vmAdminPassword         = "OfflineMock-NotARealPassword-123!"
    deployAiFoundry         = false
    deployAppConfig         = false
    deployKeyVault          = false
    deploySearchService     = false
    deployStorageAccount    = false
    deployCosmosDb          = false
    deployContainerRegistry = false
    deployContainerApps     = false
    deployContainerEnv      = false
    deployAppInsights       = false
    deployLogAnalytics      = false
    retrievalBackend        = "ai_search"
  }
  assert {
    condition = (
      length(random_password.jumpbox) == 0 &&
      azurerm_windows_virtual_machine.jumpbox["this"].admin_password == var.vmAdminPassword &&
      issensitive(azurerm_windows_virtual_machine.jumpbox["this"].admin_password)
    )
    error_message = "Explicit input must take precedence, remain sensitive and remove the unused generated credential from current state."
  }
}

run "reprovision_keeps_explicit_password_without_generation" {
  command = plan
  providers = {
    azurerm = azurerm
    azapi   = azapi
    modtm   = modtm
    random  = random.password_test
    time    = time
  }
  variables {
    networkIsolation        = true
    deployJumpbox           = true
    vmAdminPassword         = "OfflineMock-NotARealPassword-123!"
    vmSize                  = "Standard_D4s_v3"
    deployAiFoundry         = false
    deployAppConfig         = false
    deployKeyVault          = false
    deploySearchService     = false
    deployStorageAccount    = false
    deployCosmosDb          = false
    deployContainerRegistry = false
    deployContainerApps     = false
    deployContainerEnv      = false
    deployAppInsights       = false
    deployLogAnalytics      = false
    retrievalBackend        = "ai_search"
  }
  assert {
    condition = (
      length(random_password.jumpbox) == 0 &&
      azurerm_windows_virtual_machine.jumpbox["this"].admin_password == var.vmAdminPassword &&
      issensitive(azurerm_windows_virtual_machine.jumpbox["this"].admin_password) &&
      azurerm_windows_virtual_machine.jumpbox["this"].size == "Standard_D4s_v3"
    )
    error_message = "Reprovisioning with explicit input must not create a random credential, alter the supplied value or ignore VM configuration."
  }
}

run "invalid_explicit_jumpbox_password_is_not_replaced" {
  command = plan
  variables {
    networkIsolation = true
    deployJumpbox    = true
    # Meets AzureRM's 8-character/complexity check, but not root's 12 minimum.
    vmAdminPassword = "Short123!"
  }
  expect_failures = [terraform_data.root_contract]
  assert {
    condition     = length(random_password.jumpbox) == 0
    error_message = "Invalid explicit input must fail validation rather than silently generate a different credential."
  }
}

run "empty_jumpbox_password_requests_generation" {
  command = plan
  variables {
    networkIsolation = true
    deployJumpbox    = true
    vmAdminPassword  = ""
  }
  assert {
    condition     = length(random_password.jumpbox) == 1 && local.compute_generate_jumpbox_password
    error_message = "An empty substitution must request generation, matching the root nullable-password contract."
  }
}
