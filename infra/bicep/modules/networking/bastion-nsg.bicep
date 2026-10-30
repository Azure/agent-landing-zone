param name string
param location string
param bastionAllowedSourceIPs array = []

var allowedSourceRules = [
  for (ip, i) in bastionAllowedSourceIPs: {
    name: 'AllowHttpsFromTrustedIP-${i}'
    properties: {
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRange: '443'
      sourceAddressPrefix: ip
      destinationAddressPrefix: '*'
      access: 'Allow'
      priority: 200 + i
      direction: 'Inbound'
    }
  }
]

var requiredRules = [
  // Inbound rules
  {
    name: 'AllowGatewayManagerInbound'
    properties: {
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRange: '443'
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
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRange: '443'
      sourceAddressPrefix: 'AzureLoadBalancer'
      destinationAddressPrefix: '*'
      access: 'Allow'
      priority: 110
      direction: 'Inbound'
    }
  }
  {
    name: 'AllowBastionHostCommunicationInbound'
    properties: {
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRanges: [
        '8080'
        '5701'
      ]
      sourceAddressPrefix: 'VirtualNetwork'
      destinationAddressPrefix: 'VirtualNetwork'
      access: 'Allow'
      priority: 120
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
  // Outbound rules
  {
    name: 'AllowSshRdpOutbound'
    properties: {
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRanges: [
        '22'
        '3389'
      ]
      sourceAddressPrefix: '*'
      destinationAddressPrefix: 'VirtualNetwork'
      access: 'Allow'
      priority: 100
      direction: 'Outbound'
    }
  }
  {
    name: 'AllowAzureCloudOutbound'
    properties: {
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRange: '443'
      sourceAddressPrefix: '*'
      destinationAddressPrefix: 'AzureCloud'
      access: 'Allow'
      priority: 110
      direction: 'Outbound'
    }
  }
  {
    name: 'AllowBastionHostCommunicationOutbound'
    properties: {
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRanges: [
        '8080'
        '5701'
      ]
      sourceAddressPrefix: 'VirtualNetwork'
      destinationAddressPrefix: 'VirtualNetwork'
      access: 'Allow'
      priority: 120
      direction: 'Outbound'
    }
  }
  {
    name: 'AllowGetSessionInformationOutbound'
    properties: {
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '80'
      sourceAddressPrefix: '*'
      destinationAddressPrefix: 'Internet'
      access: 'Allow'
      priority: 130
      direction: 'Outbound'
    }
  }
]

resource bastionNsg 'Microsoft.Network/networkSecurityGroups@2024-07-01' = {
  name: name
  location: location
  properties: {
    securityRules: concat(requiredRules, allowedSourceRules)
  }
}

output id string = bastionNsg.id
