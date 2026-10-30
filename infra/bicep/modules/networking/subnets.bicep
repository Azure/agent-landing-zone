targetScope = 'resourceGroup'

param vnetName string
param location string
param resourceGroupName string
param subscriptionId string = subscription().subscriptionId
param tags object = {}
param subnets array = []
param addressPrefixes array
param useExistingVNet bool = false
param deploySubnets bool = true
param deployNsgs bool = true
param prefix string = 'nsg-'
param virtualNetworkResourceId string

// Defense at this module boundary as well as the orchestrator projection.
// Never silently strip explicit associations from a network-team-owned subnet.
var managementAttachmentsAreSafe = empty(filter(subnets, subnet => subnet.name == 'AzureFirewallManagementSubnet' && (!empty(subnet.?networkSecurityGroupResourceId ?? '') || !empty(subnet.?routeTableResourceId ?? '') || !empty(subnet.?natGatewayResourceId ?? '') || !empty(subnet.?delegation ?? '') || !empty(subnet.?serviceEndpoints ?? []))))
var validatedSubnets = managementAttachmentsAreSafe ? subnets : fail('AzureFirewallManagementSubnet must not have an NSG, route table, NAT gateway, delegation or service endpoints.')

module virtualNetwork 'br/public:avm/res/network/virtual-network:0.7.0' = if (!useExistingVNet && deploySubnets) {
  name: 'virtualNetworkDeployment'
  scope: resourceGroup(subscriptionId, resourceGroupName)
  params: {
    addressPrefixes: addressPrefixes
    name: vnetName
    location: location
    tags: tags
    subnets: validatedSubnets
  }
}

module nsgsM 'network-security-group.bicep' = [
  for subnet in subnets : if (deploySubnets && deployNsgs && !contains(invalidNsgSubnets, subnet.name) && empty(subnet.?networkSecurityGroupResourceId ?? '')) {
    name: '${prefix}${vnetName}-${subnet.name}'
    scope: resourceGroup(subscriptionId, resourceGroupName)
    params : {
      name: '${prefix}${vnetName}-${subnet.name}'
      location: location
    }
  }
]

// Reserved subnets must not inherit a generic NSG; explicit service NSGs still win.
var invalidNsgSubnets = ['AzureFirewallSubnet','AppGatewaySubnet','AzureBastionSubnet','GatewaySubnet','AzureFirewallManagementSubnet']

@batchSize(1)
module subnetsM 'subnet.bicep' = [
  for i in range(0,  length(subnets)) : if (useExistingVNet && deploySubnets) {
      name: '${subnets[i].name}'
      scope: resourceGroup(subscriptionId, resourceGroupName)
      params: {
        name: '${vnetName}/${subnets[i].name}'
        addressPrefix: managementAttachmentsAreSafe ? subnets[i].addressPrefix : fail('AzureFirewallManagementSubnet must not have an NSG, route table, NAT gateway, delegation or service endpoints.')
        delegations: empty(subnets[i].delegation) ? [] : [
          {
            name: subnets[i].delegation
            properties: {
              serviceName: subnets[i].delegation
            }
          }
        ]
        serviceEndpoints: empty(subnets[i].serviceEndpoints) ? [] : [
          { 
            service : subnets[i].serviceEndpoints[0]
          }
        ]
        networkSecurityGroupId: !empty(subnets[i].?networkSecurityGroupResourceId ?? '')
          ? string(subnets[i].networkSecurityGroupResourceId)
          : (deployNsgs && !contains(invalidNsgSubnets, subnets[i].name) ? nsgsM[i]!.outputs.id : '')
        routeTableId: string(subnets[i].?routeTableResourceId ?? '')
        natGatewayId: string(subnets[i].?natGatewayResourceId ?? '')
    }
  }
]

var subnetResourceIds = [for i in range(0,  length(subnets)): {
    id : '${virtualNetworkResourceId}/subnets/${subnets[i].name}'
  }
]
