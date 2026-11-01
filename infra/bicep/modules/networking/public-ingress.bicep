// Optional Public Ingress for the AI Landing Zone (#49).
//
// Provisions an Application Gateway WAF v2 in front of the (internal) Container
// Apps environment. Default-disabled, opt-in. Designed to be operator-completed:
//
//   State A — "skeleton" (sslCertSecretId or frontendHostName missing):
//     * Public IP, WAF policy, AGW with HTTP:80 listener and a basic routing
//       rule pointing at the Container App backend over HTTPS:443.
//     * No HTTPS listener and no SSL certificate are deployed.
//     * The subnet NSG (deployed in main.bicep) denies all inbound, so the
//       skeleton is not reachable until the operator supplies the missing
//       parameters AND a non-empty `allowedSourceAddressPrefixes` list.
//
//   State B — "live" (cert + frontend host name + allow-list all set):
//     * HTTPS:443 listener using the Key Vault certificate referenced by
//       `sslCertSecretId` (versionless Key Vault secret URI).
//     * HTTP:80 listener turns into an HTTP→HTTPS permanent redirect.
//     * NSG opens TCP/443 from the supplied source CIDRs only.
//
// IMPORTANT — teardown semantics:
//   `azd`/ARM incremental deployments do NOT delete resources when a
//   conditional Bicep `if (...)` flips to `false` after a previous deploy.
//   To remove this stack, either run `azd down` or delete the resources
//   manually (Application Gateway, Public IP, WAF policy, NSG, UAI). Setting
//   `publicIngress.enabled = false` after the stack has been deployed will
//   leave the existing resources running.
//
// Cost note: WAF_v2 + a Standard Public IP incur hourly charges even when no
// traffic flows. Keep this disabled unless actively needed.

targetScope = 'resourceGroup'

@description('Name prefix used to compose resource names for all public-ingress resources.')
param namePrefix string

@description('Location for all resources created by this module.')
param location string

@description('Tags applied to all resources created by this module.')
param tags object = {}

@description('Resource ID of the Application Gateway subnet (must be a dedicated /27 or larger).')
param appGatewaySubnetResourceId string

@description('Resource ID of the Log Analytics workspace that receives Application Gateway diagnostic logs.')
param logAnalyticsWorkspaceResourceId string

@description('FQDN of the (single) backend Container App that the public ingress targets.')
param backendAppFqdn string

@description('Whether the gateway should use availability zones [1,2,3]. Recommended in regions that support zones.')
param useZoneRedundancy bool = true

@description('WAF mode for the OWASP CRS 3.2 ruleset.')
@allowed([
  'Prevention'
  'Detection'
])
param wafMode string = 'Prevention'

@description('Optional WAF custom rules merged with the OWASP managed ruleset.')
param wafCustomRules array = []

@description('AGW autoscale capacity. Defaults to min 0 / max 2.')
param capacity object = {
  minCapacity: 0
  maxCapacity: 2
}

@description('Optional sslPolicy block for the gateway. When empty, gateway uses Azure default policy.')
param sslPolicy object = {}

@description('Optional Key Vault secret ID (versionless) for the TLS certificate. When empty, the gateway is deployed without an HTTPS listener (skeleton mode).')
#disable-next-line secure-secrets-in-params
param sslCertSecretId string = ''

@description('Optional frontend host name presented to clients (e.g., app.contoso.com). Required to activate the HTTPS listener.')
param frontendHostName string = ''

@description('Resource ID of the Key Vault that holds the TLS certificate. Required when granting Key Vault Secrets User to the gateway identity.')
param keyVaultResourceId string = ''

@description('Name of the Key Vault that holds the TLS certificate. Used to scope the role assignment.')
param keyVaultName string = ''

var liveMode = !empty(sslCertSecretId) && !empty(frontendHostName)

var publicIpName = '${namePrefix}-pip'
var wafPolicyName = '${namePrefix}-waf'
var gatewayName = '${namePrefix}-agw'
var uaiName = '${namePrefix}-id'

resource agwIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: uaiName
  location: location
  tags: tags
}

resource publicIp 'Microsoft.Network/publicIPAddresses@2024-07-01' = {
  name: publicIpName
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Regional'
  }
  zones: useZoneRedundancy ? [
    '1'
    '2'
    '3'
  ] : []
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
    idleTimeoutInMinutes: 4
  }
}

resource wafPolicy 'Microsoft.Network/ApplicationGatewayWebApplicationFirewallPolicies@2024-07-01' = {
  name: wafPolicyName
  location: location
  tags: tags
  properties: {
    policySettings: {
      state: 'Enabled'
      mode: wafMode
      requestBodyCheck: true
      maxRequestBodySizeInKb: 128
      fileUploadLimitInMb: 100
    }
    customRules: wafCustomRules
    managedRules: {
      managedRuleSets: [
        {
          ruleSetType: 'OWASP'
          ruleSetVersion: '3.2'
        }
      ]
    }
  }
}

// Grant the AGW user-assigned identity the Key Vault Secrets User role on the
// landing zone Key Vault when it is available. Operators using an external
// Key Vault must grant the role themselves.
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource landingZoneKv 'Microsoft.KeyVault/vaults@2023-07-01' existing = if (!empty(keyVaultName)) {
  name: keyVaultName
}

resource kvSecretsUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(keyVaultResourceId) && !empty(keyVaultName)) {
  scope: landingZoneKv
  name: guid(keyVaultResourceId, agwIdentity.id, kvSecretsUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleId)
    principalId: agwIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Application Gateway
// ---------------------------------------------------------------------------

var gatewayId = resourceId('Microsoft.Network/applicationGateways', gatewayName)

var frontendIpConfigName = 'frontend-public'
var frontendPort80Name = 'port_80'
var frontendPort443Name = 'port_443'
var backendPoolName = 'aca-backend'
var backendHttpSettingsName = 'aca-https'
var probeName = 'aca-probe'
var sslCertName = 'tlsCert'
var httpListenerName = 'http-listener'
var httpsListenerName = 'https-listener'
var redirectConfigName = 'http-to-https'
var httpRoutingRuleName = liveMode ? 'http-redirect-rule' : 'http-rule'
var httpsRoutingRuleName = 'https-rule'

var frontendPorts = liveMode ? [
  {
    name: frontendPort80Name
    properties: {
      port: 80
    }
  }
  {
    name: frontendPort443Name
    properties: {
      port: 443
    }
  }
] : [
  {
    name: frontendPort80Name
    properties: {
      port: 80
    }
  }
]

var sslCertificates = liveMode ? [
  {
    name: sslCertName
    properties: {
      keyVaultSecretId: sslCertSecretId
    }
  }
] : []

var httpListenerCommon = {
  frontendIPConfiguration: {
    id: '${gatewayId}/frontendIPConfigurations/${frontendIpConfigName}'
  }
  frontendPort: {
    id: '${gatewayId}/frontendPorts/${frontendPort80Name}'
  }
  protocol: 'Http'
  requireServerNameIndication: false
}

var httpsListenerCommon = {
  frontendIPConfiguration: {
    id: '${gatewayId}/frontendIPConfigurations/${frontendIpConfigName}'
  }
  frontendPort: {
    id: '${gatewayId}/frontendPorts/${frontendPort443Name}'
  }
  protocol: 'Https'
  hostName: frontendHostName
  sslCertificate: {
    id: '${gatewayId}/sslCertificates/${sslCertName}'
  }
  requireServerNameIndication: true
}

var httpListeners = liveMode ? [
  {
    name: httpListenerName
    properties: httpListenerCommon
  }
  {
    name: httpsListenerName
    properties: httpsListenerCommon
  }
] : [
  {
    name: httpListenerName
    properties: httpListenerCommon
  }
]

var redirectConfigurations = liveMode ? [
  {
    name: redirectConfigName
    properties: {
      redirectType: 'Permanent'
      targetListener: {
        id: '${gatewayId}/httpListeners/${httpsListenerName}'
      }
      includePath: true
      includeQueryString: true
    }
  }
] : []

var requestRoutingRules = liveMode ? [
  {
    name: httpRoutingRuleName
    properties: {
      ruleType: 'Basic'
      priority: 100
      httpListener: {
        id: '${gatewayId}/httpListeners/${httpListenerName}'
      }
      redirectConfiguration: {
        id: '${gatewayId}/redirectConfigurations/${redirectConfigName}'
      }
    }
  }
  {
    name: httpsRoutingRuleName
    properties: {
      ruleType: 'Basic'
      priority: 110
      httpListener: {
        id: '${gatewayId}/httpListeners/${httpsListenerName}'
      }
      backendAddressPool: {
        id: '${gatewayId}/backendAddressPools/${backendPoolName}'
      }
      backendHttpSettings: {
        id: '${gatewayId}/backendHttpSettingsCollection/${backendHttpSettingsName}'
      }
    }
  }
] : [
  {
    name: httpRoutingRuleName
    properties: {
      ruleType: 'Basic'
      priority: 100
      httpListener: {
        id: '${gatewayId}/httpListeners/${httpListenerName}'
      }
      backendAddressPool: {
        id: '${gatewayId}/backendAddressPools/${backendPoolName}'
      }
      backendHttpSettings: {
        id: '${gatewayId}/backendHttpSettingsCollection/${backendHttpSettingsName}'
      }
    }
  }
]

resource appGateway 'Microsoft.Network/applicationGateways@2024-07-01' = {
  name: gatewayName
  location: location
  tags: tags
  zones: useZoneRedundancy ? [
    '1'
    '2'
    '3'
  ] : []
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${agwIdentity.id}': {}
    }
  }
  properties: union({
    sku: {
      name: 'WAF_v2'
      tier: 'WAF_v2'
    }
    autoscaleConfiguration: {
      minCapacity: capacity.?minCapacity ?? 0
      maxCapacity: capacity.?maxCapacity ?? 2
    }
    enableHttp2: true
    firewallPolicy: {
      id: wafPolicy.id
    }
    gatewayIPConfigurations: [
      {
        name: 'gateway-ip-config'
        properties: {
          subnet: {
            id: appGatewaySubnetResourceId
          }
        }
      }
    ]
    frontendIPConfigurations: [
      {
        name: frontendIpConfigName
        properties: {
          publicIPAddress: {
            id: publicIp.id
          }
        }
      }
    ]
    frontendPorts: frontendPorts
    sslCertificates: sslCertificates
    backendAddressPools: [
      {
        name: backendPoolName
        properties: {
          backendAddresses: [
            {
              fqdn: backendAppFqdn
            }
          ]
        }
      }
    ]
    probes: [
      {
        name: probeName
        properties: {
          protocol: 'Https'
          path: '/'
          interval: 30
          timeout: 30
          unhealthyThreshold: 3
          pickHostNameFromBackendHttpSettings: true
          port: 443
          match: {
            statusCodes: [
              '200-499'
            ]
          }
        }
      }
    ]
    backendHttpSettingsCollection: [
      {
        name: backendHttpSettingsName
        properties: {
          port: 443
          protocol: 'Https'
          cookieBasedAffinity: 'Disabled'
          pickHostNameFromBackendAddress: true
          requestTimeout: 30
          probe: {
            id: '${gatewayId}/probes/${probeName}'
          }
        }
      }
    ]
    httpListeners: httpListeners
    redirectConfigurations: redirectConfigurations
    requestRoutingRules: requestRoutingRules
  }, empty(sslPolicy) ? {} : {
    sslPolicy: sslPolicy
  })
  dependsOn: [
    kvSecretsUserAssignment
  ]
}

resource agwDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsWorkspaceResourceId)) {
  name: 'diag-${gatewayName}'
  scope: appGateway
  properties: {
    workspaceId: logAnalyticsWorkspaceResourceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

output enabled bool = true
output publicIp string = publicIp.properties.ipAddress
output publicIpResourceId string = publicIp.id
output gatewayResourceId string = appGateway.id
output gatewayName string = appGateway.name
output wafPolicyResourceId string = wafPolicy.id
output identityResourceId string = agwIdentity.id
output identityPrincipalId string = agwIdentity.properties.principalId
output liveMode bool = liveMode
