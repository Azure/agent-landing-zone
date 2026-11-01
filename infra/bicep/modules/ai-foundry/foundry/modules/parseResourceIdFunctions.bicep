@export()
@description('Splits Resource ID into its components.')
func getResourceParts(resourceId string?) string[] => split(resourceId ?? '', '/')

@export()
@description('Extracts the Resource Name from a Resource ID.')
func getResourceName(resourceId string?, parts string[]) string =>
  !empty(resourceId) && contains(resourceId!, '/') && !empty(parts) ? last(parts)! : resourceId ?? ''

@export()
@description('Extracts the Subscription ID from a Resource ID.')
func getSubscriptionId(parts string[]) string => length(parts) > 2 ? parts[2] : subscription().subscriptionId

@export()
@description('Extracts the Resource Group Name from a Resource ID.')
func getResourceGroupName(parts string[]) string => length(parts) > 4 ? parts[4] : resourceGroup().name
