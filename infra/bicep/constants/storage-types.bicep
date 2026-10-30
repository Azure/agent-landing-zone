@export()
@description('Supported network ACL bypass values for the solution Storage account, matching Storage AVM 0.26.2.')
type storageAccountNetworkAclsBypassType = 'None'
  | 'AzureServices'
  | 'Logging'
  | 'Metrics'
  | 'AzureServices, Logging'
  | 'AzureServices, Metrics'
  | 'AzureServices, Logging, Metrics'
  | 'Logging, Metrics'

@export()
@sealed()
@description('An explicitly approved resource-instance network access rule for the solution Storage account.')
type storageAccountResourceAccessRuleType = {
  @description('Full ARM resource ID of the eligible resource instance. Supply an existing approved resource; no resource is created by this rule.')
  @minLength(1)
  resourceId: string

  @description('Tenant ID of the resource instance. Azure requires the resource instance and Storage account to belong to the same tenant.')
  @minLength(1)
  tenantId: string
}
