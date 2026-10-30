targetScope = 'resourceGroup'

@description('NAT gateway name from the root naming contract.')
param name string
@description('Public IP name and DNS label from the root naming contract.')
param publicIpName string
@description('Workload region.')
param location string
@description('Deployment tags.')
param tags object

resource publicIp 'Microsoft.Network/publicIPAddresses@2024-07-01' = {
  name: publicIpName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Regional'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
    idleTimeoutInMinutes: 30
    dnsSettings: {
      domainNameLabel: publicIpName
    }
  }
  tags: tags
}

#disable-next-line BCP081
resource natGateway 'Microsoft.Network/natGateways@2024-10-01' = {
  name: name
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIpAddresses: [
      { id: publicIp.id }
    ]
  }
}

@description('Actual ARM ID of the NAT gateway.')
output resourceId string = natGateway.id
