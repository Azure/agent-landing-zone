targetScope = 'resourceGroup'

import { vmMaintenanceDefinitionType } from 'types.bicep'

// Release source consumed when the Portal repository refreshes its generated
// portal/wrappers/avm.res.maintenance.maintenance-configuration.json artifact.
@description('Maintenance Configuration.')
param maintenanceConfig vmMaintenanceDefinitionType

module inner 'br/public:avm/res/maintenance/maintenance-configuration:0.3.1' = {
  name: 'maint-avm-${maintenanceConfig.name}'
  params: {
    name: maintenanceConfig.name
    enableTelemetry: maintenanceConfig.?enableTelemetry ?? true
    extensionProperties: maintenanceConfig.?extensionProperties ?? {}
    installPatches: maintenanceConfig.?installPatches ?? {}
    location: maintenanceConfig.?location ?? resourceGroup().location
    lock: maintenanceConfig.?lock
    maintenanceScope: maintenanceConfig.?maintenanceScope ?? 'Host'
    maintenanceWindow: maintenanceConfig.?maintenanceWindow ?? {}
    namespace: maintenanceConfig.?namespace ?? ''
    roleAssignments: maintenanceConfig.?roleAssignments
    tags: maintenanceConfig.?tags
    visibility: maintenanceConfig.?visibility ?? ''
  }
}

@description('The resource ID of the Maintenance Configuration.')
output resourceId string = inner.outputs.resourceId

@description('The resource name of the Maintenance Configuration.')
output name string = inner.outputs.name

@description('The resource group the Maintenance Configuration was deployed into.')
output resourceGroupName string = inner.outputs.resourceGroupName

@description('The location the resource was deployed into.')
output location string = inner.outputs.location
