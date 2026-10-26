targetScope = 'resourceGroup'

@description('Name of the deployed VM.')
param vmName string
@description('Workload region.')
param location string
@description('Root deployment name, preserving the existing rerun behavior.')
param forceUpdateTag string
@description('Installer URIs pinned by the root manifest.')
param fileUris array
@description('Installer command using application/root bootstrap context.')
param commandToExecute string

resource extension 'Microsoft.Compute/virtualMachines/extensions@2024-11-01' = {
  name: '${vmName}/cse'
  location: location
  properties: {
    publisher: 'Microsoft.Compute'
    type: 'CustomScriptExtension'
    typeHandlerVersion: '1.10'
    autoUpgradeMinorVersion: true
    forceUpdateTag: forceUpdateTag
    settings: {
      fileUris: fileUris
      commandToExecute: commandToExecute
    }
    protectedSettings: {}
  }
}
