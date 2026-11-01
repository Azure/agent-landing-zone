// Azure Cosmos DB for NoSQL account.
//
// The AVM database-account module (0.15.x) only sends locations, consistency,
// network rules, automatic failover and analytical storage when a database is
// passed in the same call. The landing zone deploys the database through
// modules/cosmos-db/sql-database.bicep, so the account is declared here with the
// full property set on every deployment. The values match what AVM produced
// in v2.5.x, so existing accounts are updated in place without drift.

@description('Name of the Azure Cosmos DB account.')
param name string

@description('Location of the Azure Cosmos DB account.')
param location string

@description('Use a system-assigned managed identity.')
param systemAssignedIdentity bool = true

@description('User-assigned managed identity resource IDs.')
param userAssignedResourceIds array = []

@description('Deploy the single region as zone redundant.')
param isZoneRedundant bool = false

@description('Default consistency level.')
param defaultConsistencyLevel string = 'Session'

@description('Capabilities to enable, for example EnableServerless.')
param capabilities array = []

@description('Enable analytical storage.')
param enableAnalyticalStorage bool = false

@description('Enable the free tier.')
param enableFreeTier bool = false

@description('Public network access: Enabled or Disabled.')
param publicNetworkAccess string = 'Disabled'

@description('IP addresses or CIDR ranges allowed through the firewall.')
param ipRules array = []

@description('Subnet resource IDs allowed through the virtual network filter.')
param virtualNetworkSubnetIds array = []

@description('Resource tags.')
param tags object = {}

var _identityType = systemAssignedIdentity
  ? (empty(userAssignedResourceIds) ? 'SystemAssigned' : 'SystemAssigned,UserAssigned')
  : (empty(userAssignedResourceIds) ? 'None' : 'UserAssigned')

resource databaseAccount 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: name
  location: location
  kind: 'GlobalDocumentDB'
  tags: tags
  identity: {
    type: _identityType
    userAssignedIdentities: empty(userAssignedResourceIds)
      ? null
      : toObject(userAssignedResourceIds, id => id, id => {})
  }
  properties: {
    databaseAccountOfferType: 'Standard'
    backupPolicy: {
      type: 'Continuous'
      continuousModeProperties: {
        tier: 'Continuous30Days'
      }
    }
    capabilities: [for capability in capabilities: { name: capability }]
    minimalTlsVersion: 'Tls12'
    capacity: {
      totalThroughputLimit: -1
    }
    publicNetworkAccess: publicNetworkAccess
    consistencyPolicy: {
      defaultConsistencyLevel: defaultConsistencyLevel
    }
    enableMultipleWriteLocations: false
    locations: [
      {
        failoverPriority: 0
        locationName: location
        isZoneRedundant: isZoneRedundant
      }
    ]
    ipRules: [for ipRule in ipRules: { ipAddressOrRange: ipRule }]
    virtualNetworkRules: [
      for subnetId in virtualNetworkSubnetIds: {
        id: subnetId
        ignoreMissingVNetServiceEndpoint: false
      }
    ]
    networkAclBypass: 'None'
    isVirtualNetworkFilterEnabled: !empty(ipRules) || !empty(virtualNetworkSubnetIds)
    enableFreeTier: enableFreeTier
    enableAutomaticFailover: true
    enableAnalyticalStorage: enableAnalyticalStorage
    disableLocalAuth: true
    disableKeyBasedMetadataWriteAccess: true
  }
}

output name string = databaseAccount.name
output resourceId string = databaseAccount.id
output endpoint string = databaseAccount.properties.documentEndpoint
