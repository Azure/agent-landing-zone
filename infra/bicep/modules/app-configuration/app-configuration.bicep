// This module exists to help you update app settings key-values after creating the App Configuration store in the main Bicep file.
// It allows you to create multiple key/value pairs in an existing App Configuration store.
// It is useful for scenarios where you want to update or add new key-values after the initial deployment.
// Updating key-values at the same time as deploying the store is not possible due to dependencies and race conditions.

@description('List of key/value pairs to create')
param keyValues array

@description('Name of the existing App Configuration store')
param storeName string

resource store 'Microsoft.AppConfiguration/configurationStores@2024-05-01' existing = {
  name: storeName
}

resource kvResources 'Microsoft.AppConfiguration/configurationStores/keyValues@2024-05-01' = [
  for kv in keyValues: {
    parent: store
    name: empty(kv.label) ? kv.name : '${kv.name}$${kv.label}' 
    properties: {
      value:        kv.value
      contentType:  kv.contentType
    }
  }
]
