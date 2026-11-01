terraform {
  # Required, existing backend; never fall back to local state. azd renders
  # provider.conf.json into its environment directory and supplies it to init.
  # The backend resource group must not be a workload teardown destination.
  # azd 1.37.1 passes -lock=false to plan/apply, disabling Azure Blob lease
  # protection. Shared state requires the approved single authorized executor
  # and an external queue; that operating policy does not restore native locking.
  backend "azurerm" {}
}

# Terraform authenticates independently of azd auth. Native providers support
# az login and process ARM_* credentials; no azd global auth setting is changed.
# Do not put client secrets, certificates or tokens in Terraform input files.
# Leave native ARM_USE_OIDC / ARM_USE_MSI options available to credentialed CI.
provider "azurerm" {
  features {}

  subscription_id                 = var.subscriptionId
  tenant_id                       = var.tenantId
  environment                     = var.azureCloud.environment
  use_cli                         = true
  storage_use_azuread             = true
  resource_provider_registrations = "none"
}

provider "azapi" {
  subscription_id            = var.subscriptionId
  tenant_id                  = var.tenantId
  environment                = var.azureCloud.environment
  use_cli                    = true
  skip_provider_registration = true
}
