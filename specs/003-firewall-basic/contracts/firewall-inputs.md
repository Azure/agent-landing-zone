# Firewall input contract for new deployments

These settings are implemented by both providers and shared input preparation.

| Parameter | azd environment setting | Contract |
| --- | --- | --- |
| `azureFirewallSku` | `AZURE_FIREWALL_SKU` | Basic/Standard; Basic default for standalone |
| `azureFirewallManagementSubnetName` | `AZURE_FIREWALL_MANAGEMENT_SUBNET_NAME` | Exact name `AzureFirewallManagementSubnet` |
| `azureFirewallManagementSubnetPrefix` | `AZURE_FIREWALL_MANAGEMENT_SUBNET_PREFIX` | IPv4 CIDR; proposed default `192.168.3.192/26` |
| `deployAzureFirewallSubnet` | `DEPLOY_AZURE_FIREWALL_SUBNET` | Auto/nullable boolean; default follows local firewall requirement |
| `deployAzureFirewallManagementSubnet` | `DEPLOY_AZURE_FIREWALL_MANAGEMENT_SUBNET` | Auto/nullable boolean; creation gated by standalone local isolated Basic |
| `deployGatewaySubnet` | `DEPLOY_GATEWAY_SUBNET` | Boolean; default false |

Use the same native defaults/types and environment normalization in both
providers. Extend the shared nullable-boolean input mapping for both firewall
subnet flags. Resolve auto before provider input generation when using azd.
Explicit native template values and environment settings must not conflict.

## Effective rules

```text
localFirewall = networkIsolation AND deployAzureFirewall
basicManagement =
  localFirewall AND deploymentMode == standalone AND resolvedSku == Basic
createDataSubnet =
  networkIsolation AND deploySubnets
  AND (deployAzureFirewallSubnet ?? localFirewall)
createManagementSubnet =
  basicManagement AND deploySubnets
  AND (deployAzureFirewallManagementSubnet ?? true)
createGatewaySubnet =
  networkIsolation AND deploySubnets AND deployGatewaySubnet
```

The null-coalescing notation above describes equivalent behavior in both
languages, not literal Terraform syntax.

If creation is false but a consumer requires a subnet, validate its BYO
existence/properties or fail. Management resources never appear for an
inactive/unsupported topology. Explicit true can reserve the data subnet or
GatewaySubnet without deploying the corresponding service.

External hub egress requires local firewall deployment disabled and one valid
external routing option. A hub ID/mode label alone does not configure routing.
Reject integrated local Basic rather than deploying it without dependencies.

## Firewall interfaces

Bicep API `2024-07-01` uses `properties.managementIpConfiguration` referencing
the management public IP and subnet. Data `ipConfigurations` and private-IP
route consumers retain their meaning.

Terraform firewall AVM 0.4.0 exposes `firewall_sku_tier` and nullable
`firewall_management_ip_configuration` with `name`, `public_ip_address_id` and
`subnet_id`. Set the latter only for Basic.

Policy AVM 0.3.3 uses matching `firewall_policy_sku`. Omit Bicep DNS policy
settings and pass `firewall_policy_dns=null` for Basic. Preserve selectable
Standard proxy behavior and the source-scoped rule collections.

## Validation and ownership

Reject unknown SKU, Basic with DNS proxy, conflicting ownership/routing,
invalid CIDRs and missing/incompatible required BYO subnets before writes.
Enforce static guards at native provider boundaries and through shared
preflight. Never silently change SKU or DNS intent.

Hub and BYO resources stay outside the deployment's create/delete boundary.
No new public output or runtime App Configuration key is required.
