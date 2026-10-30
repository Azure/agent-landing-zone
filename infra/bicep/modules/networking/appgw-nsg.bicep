// NSG for the Application Gateway subnet used by the optional public ingress (#49).
//
// The NSG is intentionally restrictive:
//   * Inbound from `GatewayManager` on 65200-65535 is required by Application
//     Gateway v2 control-plane and is always allowed.
//   * Inbound from `AzureLoadBalancer` is allowed for health probes.
//   * Inbound from the operator-supplied `allowedSourceAddressPrefixes` is allowed
//     on TCP/443 only — port 80 is never opened from the Internet by this NSG.
//   * All other inbound traffic is denied. The HTTP:80 listener on the gateway
//     is therefore inert until the operator supplies a cert + frontend host name
//     and the matching allow list (see `public-ingress.bicep`).

param name string
param location string

@description('CIDRs that are allowed to reach the public Application Gateway on TCP/443. Empty list keeps the gateway fully inert.')
param allowedSourceAddressPrefixes array = []

var allowedHttpsRules = empty(allowedSourceAddressPrefixes) ? [] : [
  {
    name: 'AllowHttpsFromAllowedSources'
    properties: {
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRange: '443'
      sourceAddressPrefixes: allowedSourceAddressPrefixes
      destinationAddressPrefix: '*'
      access: 'Allow'
      priority: 200
      direction: 'Inbound'
    }
  }
]

var requiredRules = [
  {
    name: 'AllowGatewayManagerInbound'
    properties: {
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRange: '65200-65535'
      sourceAddressPrefix: 'GatewayManager'
      destinationAddressPrefix: '*'
      access: 'Allow'
      priority: 100
      direction: 'Inbound'
    }
  }
  {
    name: 'AllowAzureLoadBalancerInbound'
    properties: {
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: 'AzureLoadBalancer'
      destinationAddressPrefix: '*'
      access: 'Allow'
      priority: 110
      direction: 'Inbound'
    }
  }
  {
    name: 'DenyAllInternetInbound'
    properties: {
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: 'Internet'
      destinationAddressPrefix: '*'
      access: 'Deny'
      priority: 4096
      direction: 'Inbound'
    }
  }
]

resource appGwNsg 'Microsoft.Network/networkSecurityGroups@2024-07-01' = {
  name: name
  location: location
  properties: {
    securityRules: concat(requiredRules, allowedHttpsRules)
  }
}

output id string = appGwNsg.id
output name string = appGwNsg.name
