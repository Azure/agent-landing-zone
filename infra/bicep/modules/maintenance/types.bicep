@export()
@description('Configuration object for a VM Maintenance Configuration resource.')
type vmMaintenanceDefinitionType = {
  @description('Required. Name of the Maintenance Configuration.')
  name: string

  @description('Optional. Enable or disable usage telemetry for the module. Default is true.')
  enableTelemetry: bool?

  @description('Optional. Extension properties of the Maintenance Configuration.')
  extensionProperties: {
    @description('Optional. Arbitrary key for each extension property.')
    *: string
  }?

  @description('Optional. Configuration settings for VM guest patching with Azure Update Manager.')
  installPatches: {
    @description('Optional. Linux patch classifications and package masks.')
    linuxParameters: {
      @description('Optional. Linux update classifications to include.')
      classificationsToInclude: string[]?
      @description('Optional. Linux package name masks to exclude.')
      packageNameMasksToExclude: string[]?
      @description('Optional. Linux package name masks to include.')
      packageNameMasksToInclude: string[]?
    }?
    @description('Optional. Reboot preference after patch installation.')
    rebootSetting: 'Always' | 'IfRequired' | 'Never'?
    @description('Optional. Windows patch classifications and KB filters.')
    windowsParameters: {
      @description('Optional. Windows update classifications to include.')
      classificationsToInclude: string[]?
      @description('Optional. Exclude patches that require a reboot.')
      excludeKbsRequiringReboot: bool?
      @description('Optional. Windows KB numbers to exclude.')
      kbNumbersToExclude: string[]?
      @description('Optional. Windows KB numbers to include.')
      kbNumbersToInclude: string[]?
    }?
  }?

  @description('Optional. Resource location. Defaults to the resource group location.')
  location: string?

  @description('Optional. Lock configuration for the Maintenance Configuration.')
  lock: {
    @description('Optional. Lock type.')
    kind: 'CanNotDelete' | 'None' | 'ReadOnly'?
    @description('Optional. Lock name.')
    name: string?
  }?

  @description('Optional. Maintenance scope of the configuration. Default is Host.')
  maintenanceScope: 'Extension' | 'Host' | 'InGuestPatch' | 'OSImage' | 'SQLDB' | 'SQLManagedInstance'?

  @description('Optional. Definition of the Maintenance Window.')
  maintenanceWindow: {
    @description('Optional. Duration of the maintenance window in HH:mm format.')
    duration: string?
    @description('Optional. Expiration date and time of the maintenance window.')
    expirationDateTime: string?
    @description('Optional. Recurrence expression for the maintenance window.')
    recurEvery: string?
    @description('Optional. Start date and time of the maintenance window.')
    startDateTime: string?
    @description('Optional. Time zone used by the maintenance window.')
    timeZone: string?
  }?

  @description('Optional. Namespace of the resource.')
  namespace: string?

  @description('Optional. Role assignments to apply to the Maintenance Configuration.')
  roleAssignments: {
    @description('Required. Principal ID of the identity being assigned.')
    principalId: string
    @description('Required. Role to assign (display name, GUID, or full resource ID).')
    roleDefinitionIdOrName: string
    @description('Optional. Condition for the role assignment.')
    condition: string?
    @description('Optional. Condition version.')
    conditionVersion: '2.0'?
    @description('Optional. Delegated managed identity resource ID.')
    delegatedManagedIdentityResourceId: string?
    @description('Optional. Description of the role assignment.')
    description: string?
    @description('Optional. Role assignment name (GUID). If omitted, a GUID is generated.')
    name: string?
    @description('Optional. Principal type of the assigned identity.')
    principalType: 'Device' | 'ForeignGroup' | 'Group' | 'ServicePrincipal' | 'User'?
  }[]?

  @description('Optional. Tags to apply to the Maintenance Configuration resource.')
  tags: {
    @description('Required. Arbitrary key for each tag.')
    *: string
  }?

  @description('Optional. Visibility of the configuration. Default is Custom.')
  visibility: '' | 'Custom' | 'Public'?
}
