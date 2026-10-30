targetScope = 'resourceGroup'

@description('Bastion name from the root naming contract.')
param name string
@description('Public IP name from the root naming contract.')
param publicIpName string
@description('Workload region.')
param location string
@description('Deployment tags.')
param tags object
@description('Bastion subnet ARM ID, including any BYO subscription.')
param subnetResourceId string
@description('Bastion SKU.')
param skuName string
@description('Enable native client tunneling on supported SKUs.')
param enableTunneling bool
@description('Use zone redundancy.')
param useZoneRedundancy bool

resource publicIp 'Microsoft.Network/publicIPAddresses@2024-07-01' = {
  name: publicIpName
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Regional'
  }
  zones: useZoneRedundancy ? ['1', '2', '3'] : []
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
  }
}

resource bastion 'Microsoft.Network/bastionHosts@2024-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  zones: useZoneRedundancy ? ['1', '2', '3'] : []
  properties: {
    enableTunneling: enableTunneling && skuName != 'Basic'
    ipConfigurations: [
      {
        name: 'IpConfAzureBastionSubnet'
        properties: {
          subnet: { id: subnetResourceId }
          publicIPAddress: { id: publicIp.id }
        }
      }
    ]
  }
}
