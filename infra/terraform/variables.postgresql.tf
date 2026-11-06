# Optional foundation only. Environment aliases are resolved by the shared
# native adapter; these names are the exact Bicep/product contract.
variable "deployPostgreSql" {
  type     = bool
  default  = false
  nullable = false
}
variable "postgreSqlServerName" {
  type     = string
  default  = ""
  nullable = false
  validation {
    condition     = var.postgreSqlServerName == "" || can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.postgreSqlServerName))
    error_message = "PostgreSQL server name must be 3..63 lowercase letters, digits or hyphens, not starting/ending with a hyphen."
  }
}
variable "postgreSqlDatabaseName" {
  type     = string
  default  = "agentlz"
  nullable = false
  validation {
    condition     = can(regex("^[A-Za-z_][A-Za-z0-9_-]{0,62}$", var.postgreSqlDatabaseName)) && !contains(["postgres", "azure_maintenance", "azure_sys", "template0", "template1"], lower(var.postgreSqlDatabaseName))
    error_message = "Application database must be a non-system SQL identifier of 1..63 characters."
  }
}
variable "postgreSqlVersion" {
  type     = string
  default  = "16"
  nullable = false
  validation {
    condition     = contains(["13", "14", "15", "16", "17", "18"], var.postgreSqlVersion)
    error_message = "PostgreSQL version must be 13..18; regional/service availability is checked separately, never downgraded."
  }
}
variable "postgreSqlTier" {
  type     = string
  default  = "Burstable"
  nullable = false
  validation {
    condition     = contains(["Burstable", "GeneralPurpose", "MemoryOptimized"], var.postgreSqlTier)
    error_message = "PostgreSQL tier must be Burstable, GeneralPurpose or MemoryOptimized."
  }
}
variable "postgreSqlSkuName" {
  type     = string
  default  = "Standard_B1ms"
  nullable = false
}
variable "postgreSqlStorageSizeGb" {
  type     = number
  default  = 32
  nullable = false
  validation {
    condition     = contains([32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536], var.postgreSqlStorageSizeGb)
    error_message = "PostgreSQL storage must be a power-of-two integer GiB value in 32..65536."
  }
}
variable "postgreSqlBackupRetentionDays" {
  type     = number
  default  = 7
  nullable = false
  validation {
    condition     = var.postgreSqlBackupRetentionDays >= 7 && var.postgreSqlBackupRetentionDays <= 35 && floor(var.postgreSqlBackupRetentionDays) == var.postgreSqlBackupRetentionDays
    error_message = "PostgreSQL backup retention must be an integer in 7..35 days."
  }
}
variable "postgreSqlHighAvailability" {
  type     = string
  default  = "Disabled"
  nullable = false
  validation {
    condition     = contains(["Disabled", "SameZone", "ZoneRedundant"], var.postgreSqlHighAvailability)
    error_message = "PostgreSQL HA must be Disabled, SameZone or ZoneRedundant."
  }
}
variable "postgreSqlGeoRedundantBackup" {
  type     = bool
  default  = false
  nullable = false
}
variable "postgreSqlStorageAutoGrow" {
  type     = bool
  default  = false
  nullable = false
}
variable "postgreSqlAdministratorObjectId" {
  type     = string
  default  = ""
  nullable = false
}
variable "postgreSqlAdministratorPrincipalName" {
  type     = string
  default  = ""
  nullable = false
}
variable "postgreSqlAdministratorPrincipalType" {
  type     = string
  default  = ""
  nullable = false
}
variable "postgreSqlAllowedIpRanges" {
  type     = list(string)
  default  = []
  nullable = false
  validation {
    condition = alltrue([for ip in var.postgreSqlAllowedIpRanges : try(
      can(regex("^(0|[1-9][0-9]{0,2})(\\.(0|[1-9][0-9]{0,2})){3}(/(0|[1-9]|[12][0-9]|3[0-2]))?$", ip)) &&
      length(split(".", cidrhost(strcontains(ip, "/") ? ip : "${ip}/32", 0))) == 4 &&
      cidrhost(strcontains(ip, "/") ? ip : "${ip}/32", 0) != "0.0.0.0", false
    )])
    error_message = "PostgreSQL operator ranges must be canonical IPv4 addresses/CIDRs; all-address and 0.0.0.0 Azure-services rules are prohibited."
  }
}
variable "existingPrivateDnsZonePostgreSqlResourceId" {
  type     = string
  default  = ""
  nullable = false
  validation {
    condition     = var.existingPrivateDnsZonePostgreSqlResourceId == "" || can(regex("(?i)^/subscriptions/[0-9a-f-]{36}/resourceGroups/[^/]+/providers/Microsoft\\.Network/privateDnsZones/privatelink\\.postgres\\.database\\.azure\\.com$", var.existingPrivateDnsZonePostgreSqlResourceId))
    error_message = "Existing PostgreSQL DNS must identify privatelink.postgres.database.azure.com."
  }
}
