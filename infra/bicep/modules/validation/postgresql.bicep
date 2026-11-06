@description('Parameter-only validation for direct IaC callers. Azure-aware identity, fresh binding and route checks belong to preflight/lifecycle.')
param serverName string
param databaseName string
param tier string
param skuName string
param highAvailability string
param storageSizeGb int
param administratorObjectId string
param administratorPrincipalName string
param administratorPrincipalType string
param basic bool
param deployContainerEnv bool
param workloadProfiles array
param acaSubnetPrefix string
param acaSubnetManaged bool
param useExistingVNet bool
param deployNsgs bool
param externalNextHop string
param existingRouteTableId string
param isolated bool
param policyManagedPrivateDns bool
param existingDnsZoneId string
param allowedIpRanges string[]

func onlyCharacters(value string, alphabet string) bool => empty(filter(range(0, length(value)), index => !contains(alphabet, substring(toLower(value), index, 1))))
func uuid(value string) bool => length(value) == 36 && length(split(value, '-')) == 5 && length(split(value, '-')[0]) == 8 && length(split(value, '-')[1]) == 4 && length(split(value, '-')[2]) == 4 && length(split(value, '-')[3]) == 4 && length(split(value, '-')[4]) == 12 && onlyCharacters(replace(value, '-', ''), '0123456789abcdef')
func operatorRangeValid(value string) bool => !contains(value, ':') && length(split(split(value, '/')[0], '.')) == 4 && parseCidr(contains(value, '/') ? value : '${value}/32').network != '0.0.0.0'

var tierPrefix = { Burstable: 'Standard_B', GeneralPurpose: 'Standard_D', MemoryOptimized: 'Standard_E' }
var serverNameValid = length(serverName) >= 3 && length(serverName) <= 63 && toLower(serverName) == serverName && onlyCharacters(serverName, 'abcdefghijklmnopqrstuvwxyz0123456789-') && !startsWith(serverName, '-') && !endsWith(serverName, '-')
var databaseNameValid = length(databaseName) >= 1 && length(databaseName) <= 63 && onlyCharacters(databaseName, 'abcdefghijklmnopqrstuvwxyz0123456789_-') && contains('abcdefghijklmnopqrstuvwxyz_', toLower(substring(databaseName, 0, 1))) && !contains(['postgres', 'azure_maintenance', 'azure_sys', 'template0', 'template1'], toLower(databaseName))
var namesValid = serverNameValid && databaseNameValid
var adminValid = uuid(administratorObjectId) && administratorObjectId != '00000000-0000-0000-0000-000000000000' && !empty(trim(administratorPrincipalName)) && contains(['User', 'Group', 'ServicePrincipal'], administratorPrincipalType)
var basicValid = !basic || (deployContainerEnv && !empty(workloadProfiles) && acaSubnetManaged && int(split(acaSubnetPrefix, '/')[1]) <= 27 && (!useExistingVNet || deployNsgs) && empty(externalNextHop) && empty(existingRouteTableId))
var dnsValid = empty(existingDnsZoneId) || (startsWith(toLower(existingDnsZoneId), '/subscriptions/') && contains(toLower(existingDnsZoneId), '/resourcegroups/') && endsWith(toLower(existingDnsZoneId), '/providers/microsoft.network/privatednszones/privatelink.postgres.database.azure.com'))
output validated bool = !namesValid
  ? fail('PostgreSQL requires a lowercase 3..63 character server name and a non-system application SQL identifier.')
  : !adminValid
    ? fail('Enabled PostgreSQL requires an explicit administrator object UUID, principal name and User/Group/ServicePrincipal type.')
    : !contains([32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536], storageSizeGb)
      ? fail('PostgreSQL storage must be a power-of-two integer GiB value in 32..65536.')
    : !startsWith(skuName, tierPrefix[tier]) || (tier == 'Burstable' && highAvailability != 'Disabled')
      ? fail('PostgreSQL SKU must match tier; Burstable HA is unsupported. No fallback is performed.')
      : !basicValid
        ? fail('Basic PostgreSQL requires fresh workload-profiles ACA, a managed /27-or-larger delegated subnet, safe BYO ownership and dedicated NAT without external route-table/next-hop bindings.')
        : !dnsValid || (isolated && policyManagedPrivateDns && !empty(existingDnsZoneId))
          ? fail('PostgreSQL existing DNS must identify privatelink.postgres.database.azure.com and must not compete with policy-managed DNS.')
          : !empty(filter(allowedIpRanges, value => !operatorRangeValid(value)))
            ? fail('PostgreSQL operator ranges must be IPv4/CIDRs, never all-address or Azure-services 0.0.0.0 rules.')
            : true
