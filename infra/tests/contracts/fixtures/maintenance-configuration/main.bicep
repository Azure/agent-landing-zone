targetScope = 'resourceGroup'

module defaultMaintenance '../../../../bicep/modules/maintenance/avm.res.maintenance.maintenance-configuration.bicep' = {
  name: 'maintenance-default-contract'
  params: {
    maintenanceConfig: {
      name: 'mc-default'
    }
  }
}

module inGuestPatchMaintenance '../../../../bicep/modules/maintenance/avm.res.maintenance.maintenance-configuration.bicep' = {
  name: 'maintenance-in-guest-patch-contract'
  params: {
    maintenanceConfig: {
      name: 'mc-in-guest-patch'
      enableTelemetry: false
      extensionProperties: {
        InGuestPatchMode: 'User'
      }
      installPatches: {
        linuxParameters: {
          classificationsToInclude: [
            'Critical'
            'Security'
          ]
          packageNameMasksToExclude: [
            'kernel*'
          ]
          packageNameMasksToInclude: [
            'openssl*'
          ]
        }
        rebootSetting: 'IfRequired'
        windowsParameters: {
          classificationsToInclude: [
            'Critical'
            'Security'
          ]
          excludeKbsRequiringReboot: true
          kbNumbersToExclude: [
            'KB0000001'
          ]
          kbNumbersToInclude: [
            'KB0000002'
          ]
        }
      }
      location: 'eastus2'
      lock: {
        kind: 'CanNotDelete'
        name: 'maintenance-lock'
      }
      maintenanceScope: 'InGuestPatch'
      maintenanceWindow: {
        duration: '03:00'
        recurEvery: '1Week Saturday'
        startDateTime: '2024-06-15 22:00'
        timeZone: 'UTC'
      }
      namespace: 'Microsoft.Maintenance'
      roleAssignments: [
        {
          principalId: '00000000-0000-0000-0000-000000000001'
          roleDefinitionIdOrName: 'Contributor'
          principalType: 'ServicePrincipal'
        }
      ]
      tags: {
        scenario: 'in-guest-patch'
      }
      visibility: 'Custom'
    }
  }
}
