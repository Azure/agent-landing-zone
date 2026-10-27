@description('Explicit subnet selections and enabled consumer requirements. No resource IDs or runtime resource properties.')
param subnetDefinitions array
param vnetAddressPrefixes array
param useExistingVNet bool
param deployNsgs bool

func cidrStart(prefix string) int => reduce(split(parseCidr(prefix).network, '.'), 0, (value, octet) => value * 256 + int(octet))
func cidrEnd(prefix string) int => reduce(split(parseCidr(prefix).broadcast, '.'), 0, (value, octet) => value * 256 + int(octet))
func alignedIpv4(prefix string) bool => length(split(prefix, '/')) == 2
  ? length(split(split(prefix, '/')[0], '.')) == 4 && split(prefix, '/')[0] == parseCidr(prefix).network && int(split(prefix, '/')[1]) >= 0 && int(split(prefix, '/')[1]) <= 29
  : false

var relevant = filter(subnetDefinitions, subnet => subnet.create || subnet.required)
var selected = filter(subnetDefinitions, subnet => subnet.create)
var names = map(relevant, subnet => toLower(subnet.name))
var namesValid = empty(filter(relevant, subnet => empty(subnet.name) || length(subnet.name) > 80 || contains(subnet.name, '/') || contains(subnet.name, ' ')))
var namesUnique = length(names) == length(union(names, names))
var reservedNames = {
  gateway: 'GatewaySubnet'
  bastion: 'AzureBastionSubnet'
  firewall: 'AzureFirewallSubnet'
}
var reservedNamesValid = empty(filter(relevant, subnet => contains(reservedNames, subnet.purpose) ? subnet.name != reservedNames[subnet.purpose] : contains(['gatewaysubnet', 'azurebastionsubnet', 'azurefirewallsubnet'], toLower(subnet.name))))
var prefixesPresent = empty(filter(relevant, subnet => empty(subnet.addressPrefix)))
var prefixesValid = prefixesPresent ? empty(filter(selected, subnet => !alignedIpv4(subnet.addressPrefix))) : false
var vnetPrefixesValid = useExistingVNet ? true : !empty(vnetAddressPrefixes) && empty(filter(vnetAddressPrefixes, prefix => !alignedIpv4(prefix)))
var rangesValid = prefixesValid && vnetPrefixesValid
var overlaps = rangesValid
  ? !empty(filter(selected, subnet => !empty(filter(selected, other => subnet.name != other.name && cidrStart(subnet.addressPrefix) <= cidrEnd(other.addressPrefix) && cidrEnd(subnet.addressPrefix) >= cidrStart(other.addressPrefix)))))
  : false
// Actual BYO address space and existing-subnet overlaps belong to Azure-aware
// preflight, not the new-VNet default address space supplied by the caller.
var contained = !useExistingVNet && rangesValid
  ? empty(filter(selected, subnet => empty(filter(vnetAddressPrefixes, prefix => cidrStart(subnet.addressPrefix) >= cidrStart(prefix) && cidrEnd(subnet.addressPrefix) <= cidrEnd(prefix)))))
  : true
var aiGatewayValid = prefixesValid
  ? empty(filter(selected, subnet => subnet.purpose == 'aiGateway' && (int(split(subnet.addressPrefix, '/')[1]) > 27 || !deployNsgs)))
  : false
var consumersHaveSubnets = useExistingVNet || empty(filter(subnetDefinitions, subnet => subnet.required && !subnet.create))
var byoNsgsProtected = !useExistingVNet || empty(selected) || deployNsgs

output validated bool = !namesValid || !namesUnique || !reservedNamesValid
  ? fail('Subnet names must be nonempty, unique, valid names and use the exact reserved GatewaySubnet, AzureBastionSubnet and AzureFirewallSubnet names for those purposes.')
  : !prefixesPresent || !prefixesValid || !vnetPrefixesValid
    ? fail('Required subnet prefixes must be nonempty; managed subnet and new VNet prefixes must be aligned IPv4 CIDRs with prefix length 0 through 29.')
    : overlaps || !contained
      ? fail('Managed subnet CIDRs must not overlap and must be contained in the new VNet address space.')
      : !aiGatewayValid
        ? fail('Managed AI Gateway integration requires a /27 or larger subnet and deployNsgs=true.')
        : !consumersHaveSubnets
          ? fail('An enabled consumer requires a subnet that is not managed in the new VNet. Enable its subnet creation or disable the consumer.')
          : !byoNsgsProtected
            ? fail('Managed BYO subnet writes require deployNsgs=true to protect NSG associations.')
            : true
