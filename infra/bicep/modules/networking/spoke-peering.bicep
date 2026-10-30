targetScope = 'resourceGroup'

@description('Name of the locally owned VNet.')
param vnetName string
@description('Peering name from the root naming contract.')
param name string
@description('Exact ARM ID of the external hub VNet.')
param hubVnetResourceId string
@description('Allow gateway transit.')
param allowGatewayTransit bool
@description('Use the hub gateway.')
param useRemoteGateways bool

resource vnet 'Microsoft.Network/virtualNetworks@2024-07-01' existing = {
  name: vnetName
}

resource peering 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-07-01' = {
  parent: vnet
  name: name
  properties: {
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: allowGatewayTransit
    useRemoteGateways: useRemoteGateways
    remoteVirtualNetwork: { id: hubVnetResourceId }
  }
}
