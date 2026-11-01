// This module exists solely to pass the `containerAppsList` parameter through as an output,
// allowing you to assign the entire array directly as a key-value in your App Configuration.
// This is useful for scenarios where you want to do post-processing based on the list of container apps.

param containerAppsList array

@description('Label used for App Configuration key-value pairs.')
param appConfigLabel string

output containerAppsList array = containerAppsList

// prepare the output for App Configuration

// App endpoints, example: ORCHESTRATOR_APP_ENDPOINT: https://myapp-1234567890.eastus2.azurecontainerapps.io
output containerAppsEndpoints array = [
  for app in containerAppsList: { 
    name: '${app.canonical_name}_ENDPOINT', value: 'https://${app.fqdn}', label: appConfigLabel, contentType: 'text/plain' 
  }
]

// App names, example: ORCHESTRATOR_APP_NAME: ca-myapp-1234567890
output containerAppsName array = [
  for app in containerAppsList: { 
    name: '${app.canonical_name}_NAME', value: app.name, label: appConfigLabel, contentType: 'text/plain' 
  }
]
