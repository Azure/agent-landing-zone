@description('Container Apps may be deployed only when the Container Apps Environment is deployed.')
param containerAppsRequireEnvironment bool

@description('Container App API keys require Container Apps, Key Vault, App Configuration, and appConfig runtime mode.')
param containerAppApiKeysHavePrerequisites bool

@description('Updating isolated BYO VNet subnets must not detach existing NSG associations.')
param existingSubnetNsgAssociationsAreProtected bool

output validated bool = containerAppsRequireEnvironment
  ? containerAppApiKeysHavePrerequisites
    ? existingSubnetNsgAssociationsAreProtected
      ? true
      : fail('A network-isolated deployment cannot update subnets in an existing VNet while deployNsgs is false.')
    : fail('Container App API keys require Container Apps, Key Vault, App Configuration, and appConfig runtime mode.')
  : fail('Container Apps require the Container Apps Environment.')
