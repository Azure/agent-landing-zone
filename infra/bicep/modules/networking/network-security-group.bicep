param name string
param location string

resource nsgsM 'Microsoft.Network/networkSecurityGroups@2024-07-01' = {
  name: name
  location: location
}

output id string = nsgsM.id
