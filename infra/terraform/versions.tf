terraform {
  required_version = ">= 1.13.0, < 2.0.0"

  # Native azd 1.37.1 initializes with -upgrade. Exact root constraints prevent
  # provider upgrades; CI separately checks the committed lock file readonly.
  # Keep every transitive AVM provider exact-pinned here as well as checksum-locked.
  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "= 2.13.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 4.81.0"
    }
    modtm = {
      source  = "Azure/modtm"
      version = "= 0.4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "= 3.9.1"
    }
    time = {
      source  = "hashicorp/time"
      version = "= 0.14.2"
    }
  }
}
