param name string
param addressPrefix string
param delegations array = []
param serviceEndpoints array = []
param networkSecurityGroupId string = ''
param routeTableId string = ''
param natGatewayId string = ''

var gatewayAttachmentsAreSafe = last(split(name, '/')) != 'GatewaySubnet' || (empty(networkSecurityGroupId) && empty(routeTableId) && empty(delegations))

resource subnetsM 'Microsoft.Network/virtualNetworks/subnets@2024-07-01' = {
      name: name
      properties: {
        addressPrefix: gatewayAttachmentsAreSafe ? addressPrefix : fail('GatewaySubnet must not have an NSG, route table or delegation.')
        delegations: delegations
        serviceEndpoints: serviceEndpoints
        networkSecurityGroup: empty(networkSecurityGroupId) ? null : {
          id: networkSecurityGroupId
        }
        routeTable: empty(routeTableId) ? null : {
          id: routeTableId
        }
        natGateway: empty(natGatewayId) ? null : {
          id: natGatewayId
        }
    }
  }

output id string = subnetsM.id
