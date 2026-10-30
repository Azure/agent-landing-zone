targetScope = 'resourceGroup'

@description('Optional application PE subnet name.')
param applicationSubnetName string = ''
@description('Optional application PE subnet IPv4 CIDR.')
param applicationSubnetPrefix string = ''
@description('Existing workload subnet names; a separate subnet must not replace one.')
param existingSubnetNames string[]
@description('Existing workload subnet IPv4 CIDRs.')
param existingSubnetPrefixes string[]
@description('Workload VNet IPv4 CIDRs.')
param vnetAddressPrefixes string[]
@description('Validate configured ranges only when creating or updating subnets. A reused BYO subnet has platform-owned addressing, not the new-VNet defaults.')
param validateAddressSpace bool = true

func cidrStart(prefix string) int => reduce(split(parseCidr(prefix).network, '.'), 0, (value, octet) => value * 256 + int(octet))
func cidrEnd(prefix string) int => reduce(split(parseCidr(prefix).broadcast, '.'), 0, (value, octet) => value * 256 + int(octet))

var enabled = !empty(applicationSubnetName)
var suppliedTogether = enabled == !empty(applicationSubnetPrefix)
var nameAvailable = !contains(map(existingSubnetNames, name => toLower(name)), toLower(applicationSubnetName))
var prefixValid = enabled && suppliedTogether
  ? length(split(split(applicationSubnetPrefix, '/')[0], '.')) == 4 && split(applicationSubnetPrefix, '/')[0] == parseCidr(applicationSubnetPrefix).network && int(split(applicationSubnetPrefix, '/')[1]) <= 29 && int(split(applicationSubnetPrefix, '/')[1]) >= 0
  : true
var ipv4SubnetPrefixes = filter(existingSubnetPrefixes, prefix => length(split(split(prefix, '/')[0], '.')) == 4)
var ipv4VnetPrefixes = filter(vnetAddressPrefixes, prefix => length(split(split(prefix, '/')[0], '.')) == 4)
var nonOverlapping = enabled && suppliedTogether && prefixValid && validateAddressSpace
  ? empty(filter(ipv4SubnetPrefixes, prefix => cidrStart(applicationSubnetPrefix) <= cidrEnd(prefix) && cidrEnd(applicationSubnetPrefix) >= cidrStart(prefix)))
  : true
var containedInVnet = enabled && suppliedTogether && prefixValid && validateAddressSpace
  ? !empty(filter(ipv4VnetPrefixes, prefix => cidrStart(applicationSubnetPrefix) >= cidrStart(prefix) && cidrEnd(applicationSubnetPrefix) <= cidrEnd(prefix)))
  : true

@description('Validation completes before any new subnet is written.')
output validated bool = !suppliedTogether
  ? fail('applicationPeSubnetName and applicationPeSubnetPrefix must be supplied together.')
  : enabled && !nameAvailable
    ? fail('The separate application PE subnet name must not replace an existing workload subnet.')
    : !prefixValid
      ? fail('The application PE subnet must be an aligned IPv4 CIDR with prefix length 0 through 29.')
      : !nonOverlapping
        ? fail('The application PE subnet CIDR overlaps an existing workload subnet.')
        : !containedInVnet
          ? fail('The application PE subnet CIDR must be contained in the workload VNet address prefixes.')
          : true
