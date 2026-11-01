# Model: new deployment intent and resource ownership

## Firewall selection

Fields: network isolation, deployment mode, local firewall flag, external
next-hop/route-table selection, requested SKU and resolved SKU. SKU is a
Basic/Standard enum; there is no runtime application setting.

1. Validate explicit local/external ownership and routing.
2. Resolve Basic by default for isolated standalone; honor explicit Standard.
3. Reject unsupported/conflicting selections before writes.
4. Materialize and persist the same inputs for both providers.

An external firewall has no locally owned SKU state or policy writes.

## Creation intent

For firewall subnets, auto/absent selects the topology's requirement, true
requests creation under the supported topology, and false disables creation.
A required subnet with creation disabled must be validated as BYO.

GatewaySubnet defaults to false. Explicit true reserves a subnet without
creating a gateway. Management creation is always gated by active standalone
local isolated Basic, even if its flag is true.

## Management subnet

Purpose: `firewallManagement`; exact name: `AzureFirewallManagementSubnet`.
Proposed default: `192.168.3.192/26`. Require aligned IPv4, /26 or larger,
containment and no overlap. Respect global subnet creation and BYO ownership.

No generic NSG, delegation, service endpoints, NAT or workload UDR. Validate
BYO routing against platform-management requirements.

## Resources

| Resource | Owner and gate |
| --- | --- |
| Data subnet | Managed local firewall requirement or explicit reservation; may be BYO |
| Data public IP | Deployment-owned; local isolated firewall |
| Management subnet | Standalone local isolated Basic; may be validated BYO |
| Management public IP/NIC configuration | Deployment-owned; standalone local isolated Basic |
| Firewall/policy | Deployment-owned; local isolated firewall; matching SKU |
| GatewaySubnet | Explicit reservation only; may be BYO |
| Rule groups | Foundation/application ownership and priorities remain scoped |
| Hub firewall/policy/subnets | External owner; never adopted or modified |

Workload routes use the data-plane private IP, never the management IP.
Public outputs retain their meanings.

## Lifecycle

`selected inputs -> validated/resolved inputs -> provisioned resources
-> repeat provision with the same selection`.

Provider teardown removes only deployment-owned resources. Interrupted
provisioning is inspected before retry or explicitly authorized scoped cleanup.
