<#
.SYNOPSIS
    Pre-flight validation for AI Landing Zone deployments.

.DESCRIPTION
    Validates the effective parameter set (azd env + main.parameters.json) BEFORE
    `azd provision` reaches Azure Resource Manager. Catches the common topology
    mistakes that otherwise surface as deep, late, hard-to-debug ARM errors:

      * Conflicting Private DNS settings (policy-managed + BYO overrides at the
        same time)
      * Mutually-exclusive hub-integration parameters
      * Invalid IP allow-list shape
      * Subnet prefixes that overflow the VNet address space or overlap each
        other
      * Subnets too small for the services that consume them
      * Observability parameters that would produce telemetry split-brain
      * BYO resources (VNet, Private DNS zones, Log Analytics, App Insights,
        route table) that the operator promised but that don't actually exist

    The script is **read-only**: it never modifies Azure state. It is safe to
    run from a `preprovision` hook, from CI, or interactively at any time.

.PARAMETER SubscriptionId
    Subscription to perform Azure lookups against. Defaults to the current
    `az account show` subscription.

.PARAMETER AzdEnv
    Name of the azd environment to read values from. Defaults to
    `$env:AZURE_ENV_NAME` (which azd sets), then to the current default env.

.PARAMETER ParametersFile
    Path to `main.parameters.json`. Defaults to the file at the repo root
    relative to this script.

.PARAMETER Strict
    Treat warnings as failures (exit 2 instead of 0 when only warnings are
    reported).

.PARAMETER SkipAzureLookups
    Skip every check that requires an `az` call. Use for offline testing.
    BYO network validation fails as unverified in this mode: actual address
    space, retained overlaps and reused subnet properties require live reads.

.PARAMETER Skip
    Skip all checks. Equivalent to setting `$env:PREFLIGHT_SKIP='true'`.
    Provided as an emergency escape hatch for the `azd` preprovision hook.

.PARAMETER SkipRegional
    Skip only the regional-readiness block (provider/location support,
    jumpbox VM SKU availability, AI model quota, transient capacity warnings).
    Equivalent to setting `$env:LZ_PREFLIGHT_REGIONAL_SKIP='true'`. All other
    deterministic checks still run.

.EXAMPLE
    pwsh ./scripts/Invoke-PreflightChecks.ps1

    Run the default pre-flight against the current azd env.

.EXAMPLE
    pwsh ./scripts/Invoke-PreflightChecks.ps1 -Strict -SkipAzureLookups

    CI mode: only the deterministic parameter checks, fail on warnings.

.NOTES
    Exit codes
        0 — pass (possibly with warnings; warnings non-fatal unless -Strict)
        1 — fatal: at least one FAIL finding
        2 — warnings only, but -Strict was set
#>

[CmdletBinding()]
param(
    [string]$SubscriptionId,
    [string]$AzdEnv = $env:AZURE_ENV_NAME,
    [string]$ParametersFile,
    [switch]$Strict,
    [switch]$SkipAzureLookups,
    [switch]$Skip,
    [switch]$SkipRegional
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ModelQuota.ps1')

# --------------------------------------------------------------------------
# Emergency bypass
# --------------------------------------------------------------------------
if ($Skip -or $env:PREFLIGHT_SKIP -eq 'true' -or $env:PREFLIGHT_SKIP -eq '1') {
    Write-Host "[preflight] Skipped (PREFLIGHT_SKIP=true)." -ForegroundColor Yellow
    exit 0
}

# --------------------------------------------------------------------------
# Findings accumulator
# --------------------------------------------------------------------------
$script:Findings = [System.Collections.Generic.List[pscustomobject]]::new()

function Add-Finding {
    param(
        [Parameter(Mandatory)] [ValidateSet('PASS', 'INFO', 'WARN', 'FAIL')] [string]$Severity,
        [Parameter(Mandatory)] [string]$Code,
        [Parameter(Mandatory)] [string]$Message,
        [string]$Hint
    )
    $script:Findings.Add([pscustomobject]@{
            Severity = $Severity
            Code     = $Code
            Message  = $Message
            Hint     = $Hint
        }) | Out-Null
}

# --------------------------------------------------------------------------
# CIDR helpers (pure PowerShell, no external dependencies)
# --------------------------------------------------------------------------

function ConvertTo-IpUint32 {
    param([string]$Ip)
    $bytes = [System.Net.IPAddress]::Parse($Ip).GetAddressBytes()
    if ($bytes.Length -ne 4) { throw "Only IPv4 supported; got '$Ip'." }
    [Array]::Reverse($bytes)
    return [System.BitConverter]::ToUInt32($bytes, 0)
}

function Get-CidrRange {
    param([Parameter(Mandatory)] [string]$Cidr, [switch]$RequireAligned)
    if ($RequireAligned -and $Cidr -notmatch '^(0|[1-9]\d{0,2})(\.(0|[1-9]\d{0,2})){3}/(0|[1-9]\d?)$') {
        throw "Expected an IPv4 network CIDR; got '$Cidr'."
    }
    $parts = $Cidr -split '/', 2
    $ip = $parts[0]
    $prefix = if ($parts.Count -eq 2) { [int]$parts[1] } else { 32 }
    if ($prefix -lt 0 -or $prefix -gt 32) { throw "Invalid prefix length '$prefix' in '$Cidr'." }
    $ipVal = ConvertTo-IpUint32 -Ip $ip
    if ($prefix -eq 0) {
        $maskVal = [uint32]0
        $size = [uint64]4294967296
    }
    else {
        $hostBitCount = 32 - $prefix
        $hostMax = [uint32]([math]::Pow(2, $hostBitCount) - 1)
        $maskVal = [uint32]([uint64][uint32]::MaxValue - $hostMax)
        $size = [uint64]($hostMax + 1)
    }
    $start = [uint32]($ipVal -band $maskVal)
    if ($RequireAligned -and $ipVal -ne $start) { throw "CIDR '$Cidr' has host bits set." }
    $end = [uint32]($start + ($size - 1))
    [pscustomobject]@{ Start = [uint32]$start; End = $end; Prefix = $prefix; Cidr = $Cidr }
}

function Test-CidrOverlap {
    param([string]$A, [string]$B)
    $ra = Get-CidrRange -Cidr $A
    $rb = Get-CidrRange -Cidr $B
    return ($ra.Start -le $rb.End) -and ($rb.Start -le $ra.End)
}

function Test-CidrContains {
    param([string]$Outer, [string]$Inner)
    $ro = Get-CidrRange -Cidr $Outer
    $ri = Get-CidrRange -Cidr $Inner
    return ($ri.Start -ge $ro.Start) -and ($ri.End -le $ro.End)
}

# --------------------------------------------------------------------------
# Parameter resolution: read azd env values, layer over ${VAR=default} substitutions
# --------------------------------------------------------------------------

function Get-AzdEnvValues {
    if (-not (Get-Command azd -ErrorAction SilentlyContinue)) { return @{} }
    try {
        $azdArgs = @('env', 'get-values')
        if ($AzdEnv) { $azdArgs += @('--environment', $AzdEnv) }
        $raw = & azd @azdArgs 2>$null
        if ($LASTEXITCODE -ne 0) { return @{} }
        $h = @{}
        foreach ($line in $raw) {
            if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*"?(.*?)"?\s*$') {
                $h[$matches[1]] = $matches[2]
            }
        }
        return $h
    }
    catch {
        return @{}
    }
}

function Expand-ParamValue {
    param(
        $Raw,
        [hashtable]$EnvValues
    )
    if ($null -eq $Raw) { return $null }
    if ($Raw -isnot [string]) { return $Raw }
    # Match ${NAME} or ${NAME=default}
    $regex = [regex]'\$\{([A-Z0-9_]+)(?:=([^}]*))?\}'
    return $regex.Replace($Raw, {
            param($m)
            $name = $m.Groups[1].Value
            $def = if ($m.Groups[2].Success) { $m.Groups[2].Value } else { '' }
            if ($EnvValues.ContainsKey($name)) {
                return $EnvValues[$name]
            }
            return $def
        })
}

function Get-EffectiveParameters {
    param([Parameter(Mandatory)] [string]$Path)

    if (-not (Test-Path -Path $Path)) {
        Add-Finding -Severity FAIL -Code 'PARAMS_FILE_MISSING' -Message "Parameters file '$Path' not found."
        return @{}
    }
    $jsonRaw = Get-Content -Path $Path -Raw
    try {
        $parsed = $jsonRaw | ConvertFrom-Json
    }
    catch {
        Add-Finding -Severity FAIL -Code 'PARAMS_FILE_INVALID' -Message "Parameters file '$Path' is not valid JSON: $_"
        return @{}
    }
    if (-not $parsed.parameters) {
        Add-Finding -Severity FAIL -Code 'PARAMS_FILE_NO_PARAMETERS' -Message "Parameters file '$Path' has no 'parameters' key."
        return @{}
    }

    $envValues = Get-AzdEnvValues
    $effective = @{}
    $unresolvedRegex = [regex]'\$\{[A-Z0-9_]+\}'

    foreach ($prop in $parsed.parameters.PSObject.Properties) {
        $name = $prop.Name
        $rawVal = $prop.Value.value
        $expanded = Expand-ParamValue -Raw $rawVal -EnvValues $envValues
        if ($expanded -is [string] -and $unresolvedRegex.IsMatch($expanded)) {
            Add-Finding -Severity WARN -Code 'PARAM_UNRESOLVED' `
                -Message "Parameter '$name' still has unresolved environment tokens after substitution: '$expanded'." `
                -Hint "Set the missing env vars via 'azd env set <NAME> <VALUE>', or supply a default in main.parameters.json."
        }
        $effective[$name] = $expanded
    }
    return $effective
}

function ConvertTo-Bool {
    param($V)
    if ($null -eq $V) { return $false }
    if ($V -is [bool]) { return $V }
    if ($V -is [string]) {
        switch ($V.Trim().ToLowerInvariant()) {
            'true' { return $true }
            '1' { return $true }
            'yes' { return $true }
            default { return $false }
        }
    }
    return [bool]$V
}

function Get-StringValue {
    param($V)
    if ($null -eq $V) { return '' }
    if ($V -is [string]) { return $V }
    return [string]$V
}

function Get-ArrayValue {
    param($V)
    if ($null -eq $V) { return @() }
    if ($V -is [System.Collections.IEnumerable] -and $V -isnot [string]) { return @($V) }
    if ($V -is [string]) {
        $s = $V.Trim()
        if ([string]::IsNullOrEmpty($s)) { return @() }
        if ($s.StartsWith('[')) {
            try { return @(($s | ConvertFrom-Json)) } catch { }
        }
        return @($s)
    }
    return @($V)
}

function Resolve-DeployJumpbox {
    # Mirror main.bicep `_deployJumpbox`:
    #   deployJumpbox ?? deployVM ?? (networkIsolation && !existingJumpboxResourceId)
    # main.parameters.json substitutes unset env vars as the literal string 'null'
    # (e.g. "${DEPLOY_JUMPBOX=null}"), which ConvertTo-Bool would silently turn
    # into $false and mask the Bicep default. Honor explicit true/false here and
    # otherwise fall through to the same default-derivation Bicep uses.
    param([hashtable]$P)
    foreach ($key in 'deployJumpbox', 'deployVM') {
        $raw = (Get-StringValue $P[$key]).Trim().ToLowerInvariant()
        if ($raw -in 'true', '1', 'yes')  { return $true }
        if ($raw -in 'false', '0', 'no')  { return $false }
    }
    $hasExisting = -not [string]::IsNullOrWhiteSpace((Get-StringValue $P['existingJumpboxResourceId']))
    return (ConvertTo-Bool $P['networkIsolation']) -and -not $hasExisting
}

function Resolve-DeployFlag {
    # Resolve a feature-flag parameter to a bool, honoring an explicit value and
    # falling back to $Default when the parameter is null, empty, or still an
    # unresolved '${VAR}' token. Mirrors the default-on/off semantics expressed
    # in main.parameters.json (e.g. "${DEPLOY_SEARCH_SERVICE=true}").
    param(
        [hashtable]$P,
        [Parameter(Mandatory)] [string]$Key,
        [bool]$Default
    )
    $raw = Get-StringValue $P[$Key]
    if ([string]::IsNullOrWhiteSpace($raw)) { return $Default }
    if ($raw -match '^\$\{') { return $Default }
    return [bool](ConvertTo-Bool $raw)
}

function Test-BooleanParameterValues {
    param([hashtable]$P)

    $booleanParameters = [ordered]@{
        deployCosmosDb             = 'DEPLOY_COSMOS_DB'
        deployContainerApps        = 'DEPLOY_CONTAINER_APPS'
        deployContainerRegistry    = 'DEPLOY_CONTAINER_REGISTRY'
        deployContainerEnv         = 'DEPLOY_CONTAINER_ENV'
        deployNsgs                 = 'DEPLOY_NSGS'
        deploySubnets              = 'DEPLOY_SUBNETS'
        deployAgentSubnet          = 'DEPLOY_AGENT_SUBNET'
        deployPeSubnet             = 'DEPLOY_PE_SUBNET'
        deployApplicationPeSubnet  = 'DEPLOY_APPLICATION_PE_SUBNET'
        deployAzureBastionSubnet   = 'DEPLOY_AZURE_BASTION_SUBNET'
        deployAzureFirewallSubnet  = 'DEPLOY_AZURE_FIREWALL_SUBNET'
        deployGatewaySubnet        = 'DEPLOY_GATEWAY_SUBNET'
        deployAppGatewaySubnet     = 'DEPLOY_APP_GATEWAY_SUBNET'
        deployJumpboxSubnet        = 'DEPLOY_JUMPBOX_SUBNET'
        deployAcaEnvironmentSubnet = 'DEPLOY_ACA_ENVIRONMENT_SUBNET'
        deployDevopsBuildAgentsSubnet = 'DEPLOY_DEVOPS_BUILD_AGENTS_SUBNET'
        deployPowerPlatformSubnet  = 'DEPLOY_POWER_PLATFORM_SUBNET'
        deployAiGatewaySubnet      = 'DEPLOY_AI_GATEWAY_SUBNET'
        deployAiFoundrySubnet      = 'DEPLOY_AI_FOUNDRY_SUBNET'
        aiFoundryDisableLocalAuth  = 'AI_FOUNDRY_DISABLE_LOCAL_AUTH'
    }

    foreach ($entry in $booleanParameters.GetEnumerator()) {
        if (-not $P.ContainsKey($entry.Key)) { continue }

        $value = $P[$entry.Key]
        if ($value -is [bool]) { continue }

        $normalized = (Get-StringValue $value).Trim().ToLowerInvariant()
        if ($normalized -notin 'true', 'false') {
            Add-Finding -Severity FAIL -Code 'BOOL_VALUE_INVALID' `
                -Message "Parameter '$($entry.Key)' from $($entry.Value) must be 'true' or 'false'; received '$value'." `
                -Hint "Run 'azd env set $($entry.Value) true' or 'azd env set $($entry.Value) false'. Values such as yes/no and 1/0 are not accepted."
        }
    }
}

# --------------------------------------------------------------------------
# Deterministic topology checks (no Azure calls)
# --------------------------------------------------------------------------

function Test-Tooling {
    foreach ($t in 'pwsh', 'az') {
        if (-not (Get-Command $t -ErrorAction SilentlyContinue)) {
            Add-Finding -Severity FAIL -Code 'TOOL_MISSING' -Message "'$t' is not on PATH." `
                -Hint "Install Azure CLI (https://aka.ms/installazcli) and PowerShell 7 (https://aka.ms/install-pwsh)."
        }
    }
    if (-not (Get-Command azd -ErrorAction SilentlyContinue)) {
        Add-Finding -Severity WARN -Code 'AZD_MISSING' -Message "'azd' is not on PATH — env-var values cannot be sourced from the azd environment." `
            -Hint "Install Azure Developer CLI (https://aka.ms/azd-install)."
    }
    if ($PSVersionTable.PSVersion.Major -lt 7) {
        Add-Finding -Severity WARN -Code 'PWSH_OLD' -Message "Running on PowerShell $($PSVersionTable.PSVersion). pwsh 7+ is recommended."
    }
}

function Test-Topology {
    param([hashtable]$P)

    $deployContainerApps = Resolve-DeployFlag -P $P -Key 'deployContainerApps' -Default $true
    $deployContainerEnv = Resolve-DeployFlag -P $P -Key 'deployContainerEnv' -Default $true
    $deployKeyVault = Resolve-DeployFlag -P $P -Key 'deployKeyVault' -Default $true
    $deployAppConfig = Resolve-DeployFlag -P $P -Key 'deployAppConfig' -Default $true
    $deployNsgs = Resolve-DeployFlag -P $P -Key 'deployNsgs' -Default $true
    $useContainerAppApiKey = Resolve-DeployFlag -P $P -Key 'useCAppAPIKey' -Default $false
    $runtimeConfigMode = (Get-StringValue $P['appRuntimeConfigurationMode']).Trim()

    if ($deployContainerApps -and -not $deployContainerEnv) {
        Add-Finding -Severity FAIL -Code 'ACA_APPS_REQUIRE_ENV' `
            -Message 'deployContainerApps=true requires deployContainerEnv=true.' `
            -Hint 'Enable DEPLOY_CONTAINER_ENV or disable DEPLOY_CONTAINER_APPS.'
    }
    elseif ($deployContainerEnv -and -not $deployContainerApps) {
        Add-Finding -Severity INFO -Code 'ACA_ENVIRONMENT_ONLY' `
            -Message 'The Container Apps environment will be deployed without any Container Apps.'
    }

    if ($useContainerAppApiKey -and -not (
            $deployContainerApps -and
            $deployKeyVault -and
            $deployAppConfig -and
            $runtimeConfigMode -eq 'appConfig'
        )) {
        Add-Finding -Severity FAIL -Code 'CAPP_API_KEY_PREREQUISITES' `
            -Message 'useCAppAPIKey=true requires Container Apps, Key Vault, App Configuration, and appRuntimeConfigurationMode=appConfig.' `
            -Hint 'Enable all API-key prerequisites or set useCAppAPIKey=false.'
    }

    # Private DNS conflict: policy-managed + BYO overrides
    $policyMgr = ConvertTo-Bool $P['policyManagedPrivateDns']
    $byoDnsParams = $P.Keys | Where-Object { $_ -like 'existingPrivateDnsZone*ResourceId' }
    $byoDnsSet = @($byoDnsParams | Where-Object { -not [string]::IsNullOrEmpty((Get-StringValue $P[$_])) })
    if ($policyMgr -and $byoDnsSet.Count -gt 0) {
        Add-Finding -Severity FAIL -Code 'DNS_POLICY_VS_BYO' `
            -Message "policyManagedPrivateDns=true conflicts with BYO Private DNS overrides: $($byoDnsSet -join ', ')." `
            -Hint "Pick one: either let policy manage Private DNS (clear all existingPrivateDnsZone*ResourceId), or supply BYO zones explicitly (set policyManagedPrivateDns=false)."
    }

    # Egress mutex
    $egressIp = Get-StringValue $P['hubIntegrationEgressNextHopIp']
    $existingRt = Get-StringValue $P['hubIntegrationExistingRouteTableResourceId']
    if (-not [string]::IsNullOrEmpty($egressIp) -and -not [string]::IsNullOrEmpty($existingRt)) {
        Add-Finding -Severity FAIL -Code 'EGRESS_MUTEX' `
            -Message "hubIntegrationEgressNextHopIp and hubIntegrationExistingRouteTableResourceId are mutually exclusive." `
            -Hint "Either let the spoke deploy its own route table pointing at the hub next-hop IP, OR bring an existing route table — not both."
    }

    # Local firewall + external egress
    $deployFw = ConvertTo-Bool $P['deployAzureFirewall']
    if ($deployFw -and -not [string]::IsNullOrEmpty($egressIp)) {
        Add-Finding -Severity WARN -Code 'FW_AND_EXTERNAL_EGRESS' `
            -Message "deployAzureFirewall=true with hubIntegrationEgressNextHopIp set: a local spoke firewall AND an external egress IP are both configured." `
            -Hint "In ailz-integrated topologies the hub firewall is typically the only egress point — consider deployAzureFirewall=false."
    }

    # deploymentMode = ailz-integrated declared but no hub integration
    $mode = Get-StringValue $P['deploymentMode']
    if ($mode -eq 'ailz-integrated') {
        $hubSignals = @(
            (Get-StringValue $P['hubIntegrationHubVnetResourceId']),
            (Get-StringValue $P['hubIntegrationEgressNextHopIp']),
            (Get-StringValue $P['hubIntegrationExistingRouteTableResourceId'])
        ) | Where-Object { -not [string]::IsNullOrEmpty($_) }
        if ($hubSignals.Count -eq 0) {
            Add-Finding -Severity WARN -Code 'AILZ_NO_HUB_PARAMS' `
                -Message "deploymentMode=ailz-integrated but none of (hubIntegrationHubVnetResourceId, hubIntegrationEgressNextHopIp, hubIntegrationExistingRouteTableResourceId) are set." `
                -Hint "Either set the hub integration parameters or change deploymentMode to 'standalone'."
        }
    }

    # Observability: existing App Insights without connection string
    $hasExistAppI = -not [string]::IsNullOrEmpty((Get-StringValue $P['existingApplicationInsightsResourceId']))
    $hasExistLaw = -not [string]::IsNullOrEmpty((Get-StringValue $P['existingLogAnalyticsWorkspaceResourceId']))
    $hasExistConn = -not [string]::IsNullOrEmpty((Get-StringValue $P['existingApplicationInsightsConnectionString']))
    $allowMixed = ConvertTo-Bool $P['allowMixedObservabilityWorkspaces']

    if ($hasExistAppI -and -not $hasExistConn) {
        Add-Finding -Severity FAIL -Code 'APPI_NO_CONNSTR' `
            -Message "existingApplicationInsightsResourceId is set but existingApplicationInsightsConnectionString is empty." `
            -Hint "Run 'az monitor app-insights component show -g <rg> -a <name> --query connectionString -o tsv' and set EXISTING_APPLICATION_INSIGHTS_CONNECTION_STRING."
    }
    if ($hasExistAppI -and -not $hasExistLaw -and -not $allowMixed) {
        Add-Finding -Severity FAIL -Code 'APPI_NO_LAW' `
            -Message "existingApplicationInsightsResourceId is set without a matching existingLogAnalyticsWorkspaceResourceId." `
            -Hint "Either also set EXISTING_LOG_ANALYTICS_WORKSPACE_RESOURCE_ID to the LAW that backs your App Insights, or set ALLOW_MIXED_OBSERVABILITY_WORKSPACES=true if the split is intentional."
    }

    # Network isolation without any access path
    $netIso = ConvertTo-Bool $P['networkIsolation']
    $useExistingVNet = ConvertTo-Bool $P['useExistingVNet']
    $managedSubnets = @(Get-SubnetSelection -P $P | Where-Object Managed)
    if ($netIso -and $useExistingVNet -and $managedSubnets.Count -gt 0 -and -not $deployNsgs) {
        Add-Finding -Severity FAIL -Code 'BYO_SUBNET_NSG_DETACH' `
            -Message 'A network-isolated deployment cannot update subnets in an existing VNet while deployNsgs=false because existing NSG associations would be removed.' `
            -Hint 'Set DEPLOY_NSGS=true, or set deploySubnets=false and manage the existing subnets and NSG associations outside this deployment.'
    }
    elseif (-not $deployNsgs) {
        Add-Finding -Severity WARN -Code 'NSGS_DISABLED' `
            -Message 'Network security group deployment is disabled. Verify that every workload subnet retains equivalent controls.'
    }

    $disableFoundryLocalAuth = Resolve-DeployFlag -P $P -Key 'aiFoundryDisableLocalAuth' -Default $true
    if (-not $disableFoundryLocalAuth) {
        Add-Finding -Severity WARN -Code 'AI_FOUNDRY_LOCAL_AUTH_ENABLED' `
            -Message 'AI Foundry local API-key authentication is enabled.' `
            -Hint 'Keep AI_FOUNDRY_DISABLE_LOCAL_AUTH=true unless API-key authentication is an explicit requirement.'
    }

    $deployJump = Resolve-DeployJumpbox $P
    $allowedIps = Get-ArrayValue $P['allowedIpRanges']
    if ($netIso -and -not $deployJump -and $allowedIps.Count -eq 0) {
        Add-Finding -Severity WARN -Code 'ISO_NO_INGRESS' `
            -Message "networkIsolation=true but no jumpbox/VM is deployed and allowedIpRanges is empty." `
            -Hint "You will not have any way to reach the workload after deployment. Set DEPLOY_JUMPBOX=true, ALLOWED_IP_RANGES=<your-ip>, or plan to use an existing hub jumpbox via EXISTING_JUMPBOX_RESOURCE_ID."
    }
}

function Test-ExistingHostedOperatorAccess {
    param([hashtable]$P)

    if ($SkipAzureLookups) {
        Add-Finding -Severity INFO -Code 'HOSTED_OPERATOR_ACCESS_NOT_VERIFIED' `
            -Message 'Existing Hosted operator authorization requires live role verification before apply.'
        return
    }
    $values = Get-AzdEnvValues
    $scope = (Get-StringValue $values['AZURE_AI_PROJECT_RESOURCE_ID']).Trim()
    $principal = (Get-StringValue $P['principalId']).Trim()
    $subscription = (Get-StringValue $values['AZURE_SUBSCRIPTION_ID']).Trim()
    $group = Get-FoundryResourceGroup -ApplicationResourceGroup $values['AZURE_RESOURCE_GROUP'] `
        -FoundryResourceGroup $values['AZURE_FOUNDRY_RESOURCE_GROUP']
    $prefix = "/subscriptions/$subscription/resourceGroups/$group/providers/Microsoft.CognitiveServices/accounts/"
    $newProject = [string]::IsNullOrWhiteSpace($scope)
    if (-not $principal -or -not $subscription -or
        (-not $newProject -and (-not $group -or
            -not $scope.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or
            $scope -notmatch '/accounts/[^/]+/projects/[^/]+$'))) {
        Add-Finding -Severity FAIL -Code 'HOSTED_OPERATOR_SCOPE_REQUIRED' `
            -Message 'Suppressing Project Manager requires a bound existing project and executor principal.' `
            -Hint 'Hydrate the selected environment and verify existing scoped authorization before provisioning. No operator role will be granted automatically.'
        return
    }
    if ($newProject) {
        # Before the first foundation exists, check inherited management
        # access. The unchanged deployAiFoundry executor role already grants
        # Cognitive Services User data access on its new account. This is not
        # a new Project Manager grant or an invented existing permission.
        $scope = "/subscriptions/$subscription"
        if ($group) { $scope += "/resourceGroups/$group" }
    }
    $assignments = Invoke-AzCli -Arguments @('role', 'assignment', 'list', '--scope', $scope,
        '--include-inherited', '--assignee-object-id', $principal, '--fill-principal-name', 'false', '-o', 'json')
    $requirements = @(
        @{ Kind = 'actions'; Exclude = 'notActions'; Operation = 'Microsoft.CognitiveServices/accounts/projects/read' }
        @{ Kind = 'dataActions'; Exclude = 'notDataActions'; Operation = 'Microsoft.CognitiveServices/accounts/AIServices/agents/read' }
        @{ Kind = 'dataActions'; Exclude = 'notDataActions'; Operation = 'Microsoft.CognitiveServices/accounts/AIServices/agents/write' }
    )
    if ($newProject) {
        $requirements = @($requirements | Where-Object Kind -eq 'actions')
        if (-not (Resolve-DeployFlag -P $P -Key 'deployAiFoundry' -Default $true)) {
            Add-Finding -Severity FAIL -Code 'HOSTED_OPERATOR_ACCESS_REQUIRED' `
                -Message 'New project operator data authorization requires the declared Foundry foundation executor role; no Project Manager grant will be substituted.'
            return
        }
    }
    $permissions = @()
    foreach ($assignment in @($assignments)) {
        if (-not $assignment -or $assignment.principalId -ne $principal -or $assignment.condition) { continue }
        # CLI --name accepts the role UUID, not the ARM roleDefinitionId:
        # passing the full ID returns an empty successful list.
        $roleId = ([string]$assignment.roleDefinitionId -split '/')[-1]
        if ($roleId -notmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$') { continue }
        $definition = Invoke-AzCli -Arguments @('role', 'definition', 'list', '--name', $roleId, '-o', 'json')
        foreach ($role in @($definition)) {
            if ($role) { $permissions += @($role.permissions) }
        }
    }
    $missing = @($requirements | Where-Object {
        $requirement = $_
        -not @($permissions | Where-Object {
            $allow = @($_.($requirement.Kind) | Where-Object { $requirement.Operation -like $_ }).Count -gt 0
            $deny = @($_.($requirement.Exclude) | Where-Object { $requirement.Operation -like $_ }).Count -gt 0
            $allow -and -not $deny
        }).Count
    })
    if ($missing.Count) {
        Add-Finding -Severity FAIL -Code 'HOSTED_OPERATOR_ACCESS_REQUIRED' `
            -Message 'Required existing operator project/agent permissions are missing or could not be verified.' `
            -Hint 'Have an authorized administrator review scoped operator permissions; this preparation does not grant Project Manager or change Entra consent.'
    } else {
        Add-Finding -Severity PASS -Code 'HOSTED_OPERATOR_ACCESS_VERIFIED' `
            -Message $(if ($newProject) {
                'Inherited operator project read verified; new account data authorization is supplied by the unchanged declared Cognitive Services User executor role, not Project Manager.'
            } else {
                'Existing scoped operator project read and agent read/write permissions verified; no Project Manager assignment requested.'
            })
    }
}

function Test-HostedAgentConfiguration {
    param([hashtable]$P)

    $prepareHostedAgent = Resolve-DeployFlag -P $P -Key 'prepareHostedAgent' -Default $false
    $deployHostedAgent = Resolve-DeployFlag -P $P -Key 'deployHostedAgent' -Default $false
    if (-not ($prepareHostedAgent -or $deployHostedAgent)) { return }
    if (-not (Resolve-DeployFlag -P $P -Key 'grantHostedAgentProjectManager' -Default $true)) {
        Test-ExistingHostedOperatorAccess -P $P
    }

    $deployAiFoundry = Resolve-DeployFlag -P $P -Key 'deployAiFoundry' -Default $true
    if (-not $deployAiFoundry) {
        Add-Finding -Severity FAIL -Code 'HOSTED_AGENT_FOUNDRY_REQUIRED' `
            -Message 'Hosted-agent preparation or deployment requires deployAiFoundry=true.' `
            -Hint 'Enable the shared Foundry account/project or disable hosted-agent prerequisites.'
    }

    $deployRegistry = Resolve-DeployFlag -P $P -Key 'deployContainerRegistry' -Default $true
    $existingRegistryId = (Get-StringValue $P['hostedAgentContainerRegistryResourceId']).Trim()
    $existingRegistryEndpoint = (Get-StringValue $P['hostedAgentContainerRegistryEndpoint']).Trim()
    $registryRoleAssignmentMode = (Get-StringValue $P['hostedAgentContainerRegistryRoleAssignmentMode']).Trim()
    if ([string]::IsNullOrWhiteSpace($registryRoleAssignmentMode)) {
        $registryRoleAssignmentMode = 'rbac'
    }
    if ($registryRoleAssignmentMode -notin @('rbac', 'rbac-abac')) {
        Add-Finding -Severity FAIL -Code 'HOSTED_AGENT_REGISTRY_ROLE_MODE_INVALID' `
            -Message 'hostedAgentContainerRegistryRoleAssignmentMode must be rbac or rbac-abac.' `
            -Hint 'Use rbac for RBAC Registry Permissions or rbac-abac for RBAC Registry + ABAC Repository Permissions.'
    }
    if (-not $deployRegistry -and ([string]::IsNullOrWhiteSpace($existingRegistryId) -or [string]::IsNullOrWhiteSpace($existingRegistryEndpoint))) {
        Add-Finding -Severity FAIL -Code 'HOSTED_AGENT_REGISTRY_REQUIRED' `
            -Message 'Hosted-agent preparation or deployment requires the landing-zone registry or both existing registry inputs.' `
            -Hint 'Enable DEPLOY_CONTAINER_REGISTRY, or set HOSTED_AGENT_CONTAINER_REGISTRY_RESOURCE_ID and HOSTED_AGENT_CONTAINER_REGISTRY_ENDPOINT.'
    }

    if ((ConvertTo-Bool $P['networkIsolation'])) {
        Add-Finding -Severity INFO -Code 'HOSTED_AGENT_PRIVATE_BUILD_REQUIRED' `
            -Message 'The hosted-agent registry is private. Build and push from a VNet-connected runner/agent or the jumpbox fallback; shared ACR Tasks do not bypass private endpoint access.'
    }

    if (-not $deployHostedAgent) { return }

    $agent = $P['hostedAgent']
    if ($null -eq $agent) {
        Add-Finding -Severity FAIL -Code 'HOSTED_AGENT_CONFIG_REQUIRED' -Message 'deployHostedAgent=true requires the typed hostedAgent object.'
        return
    }

    if (@($agent.PSObject.Properties.Name) -contains 'roles') {
        Add-Finding -Severity FAIL -Code 'HOSTED_AGENT_ROLES_UNSUPPORTED' `
            -Message 'hostedAgent.roles is not supported because the hosted-agent identity is created by downstream azd deploy.' `
            -Hint 'After deployment, use the emitted agent identity and explicit Azure role definition IDs to assign least-privilege access to external resources.'
    }

    $envValues = Get-AzdEnvValues
    $name = (Get-StringValue (Expand-ParamValue -Raw $agent.name -EnvValues $envValues)).Trim()
    $image = (Get-StringValue (Expand-ParamValue -Raw $agent.image -EnvValues $envValues)).Trim()
    $version = Get-StringValue (Expand-ParamValue -Raw $agent.version -EnvValues $envValues)
    $startupCommand = (Get-StringValue (Expand-ParamValue -Raw $agent.startupCommand -EnvValues $envValues)).Trim()
    $cpu = (Get-StringValue (Expand-ParamValue -Raw $agent.runtime.cpu -EnvValues $envValues)).Trim()
    $memory = (Get-StringValue (Expand-ParamValue -Raw $agent.runtime.memory -EnvValues $envValues)).Trim()

    foreach ($required in @(
            @{ Name = 'name'; Value = $name },
            @{ Name = 'image'; Value = $image },
            @{ Name = 'runtime.cpu'; Value = $cpu },
            @{ Name = 'runtime.memory'; Value = $memory }
        )) {
        if ([string]::IsNullOrWhiteSpace($required.Value)) {
            Add-Finding -Severity FAIL -Code 'HOSTED_AGENT_CONFIG_REQUIRED' `
                -Message "hostedAgent.$($required.Name) is required when deployHostedAgent=true."
        }
    }

    if ($version -cnotmatch '\Asha256:[0-9a-f]{64}\z') {
        Add-Finding -Severity FAIL -Code 'HOSTED_AGENT_IMAGE_NOT_IMMUTABLE' `
            -Message 'hostedAgent.version must use the exact immutable OCI digest syntax sha256:<64 lowercase hex characters>, without surrounding whitespace.' `
            -Hint 'Build and push the image first, then pin the digest rather than using a mutable tag.'
    }

    [double]$cpuValue = 0
    $cpuIsValid = [double]::TryParse(
        $cpu,
        [System.Globalization.NumberStyles]::Float,
        [System.Globalization.CultureInfo]::InvariantCulture,
        [ref]$cpuValue
    ) -and $cpuValue -ge 0.25 -and $cpuValue -le 4.0
    if (-not $cpuIsValid) {
        Add-Finding -Severity FAIL -Code 'HOSTED_AGENT_CPU_INVALID' `
            -Message 'hostedAgent.runtime.cpu must be a number from 0.25 through 4.0.' `
            -Hint 'Use a value supported by the current azure.ai.agent container.resources contract, for example 0.5 or 1.'
    }

    $memoryMatch = [regex]::Match($memory, '^(?<value>\d+(?:\.\d+)?)Gi$')
    [double]$memoryValue = 0
    $memoryIsValid = $memoryMatch.Success -and [double]::TryParse(
        $memoryMatch.Groups['value'].Value,
        [System.Globalization.NumberStyles]::Float,
        [System.Globalization.CultureInfo]::InvariantCulture,
        [ref]$memoryValue
    ) -and $memoryValue -ge 0.5 -and $memoryValue -le 8.0
    if (-not $memoryIsValid) {
        Add-Finding -Severity FAIL -Code 'HOSTED_AGENT_MEMORY_INVALID' `
            -Message 'hostedAgent.runtime.memory must use Gi units with a value from 0.5Gi through 8Gi.' `
            -Hint 'Use a value supported by the current azure.ai.agent container.resources contract, for example 0.5Gi or 1Gi.'
    }

    $protocols = @($agent.protocols)
    if ($protocols.Count -eq 0) {
        Add-Finding -Severity FAIL -Code 'HOSTED_AGENT_PROTOCOL_REQUIRED' `
            -Message 'hostedAgent.protocols must contain at least one supported invocation protocol.'
    }
    foreach ($protocol in $protocols) {
        $protocolName = (Get-StringValue (Expand-ParamValue -Raw $protocol.protocol -EnvValues $envValues)).Trim()
        if ($protocolName -notin @('responses', 'invocations', 'invocations_ws', 'a2a')) {
            Add-Finding -Severity FAIL -Code 'HOSTED_AGENT_PROTOCOL_INVALID' `
                -Message "Hosted-agent protocol '$protocolName' is not supported by the current Microsoft Foundry contract."
        }
    }

}

function Test-AllowedIpRanges {
    param([hashtable]$P)
    $list = Get-ArrayValue $P['allowedIpRanges']
    if ($list.Count -eq 0) { return }
    foreach ($entry in $list) {
        $cidr = (Get-StringValue $entry).Trim()
        if ([string]::IsNullOrEmpty($cidr)) { continue }
        if ($cidr -eq '0.0.0.0/0' -or $cidr -eq '0.0.0.0') {
            Add-Finding -Severity WARN -Code 'IP_ANY' `
                -Message "allowedIpRanges contains '$cidr' — this is equivalent to no restriction." `
                -Hint "Tighten the allow-list to specific developer or runner CIDRs."
            continue
        }
        if ($cidr -notmatch '^(\d{1,3}\.){3}\d{1,3}(/\d{1,2})?$') {
            Add-Finding -Severity FAIL -Code 'IP_FORMAT' `
                -Message "allowedIpRanges entry '$cidr' is not a valid IPv4 CIDR." `
                -Hint "Use X.X.X.X or X.X.X.X/Y format."
            continue
        }
        try { Get-CidrRange -Cidr $cidr | Out-Null }
        catch {
            Add-Finding -Severity FAIL -Code 'IP_PARSE' -Message "allowedIpRanges entry '$cidr' did not parse: $_"
        }
    }
}

function Resolve-SubnetCreationFlag {
    # Unlike nullable service switches, creation switches default only when
    # absent. Test-BooleanParameterValues rejects explicit empty/null/aliases.
    param([hashtable]$P, [string]$Key)
    if (-not $P.ContainsKey($Key)) { return $true }
    return (Get-StringValue $P[$Key]).Trim() -ieq 'true'
}

function Get-SubnetSelection {
    param([hashtable]$P)

    $isolated = ConvertTo-Bool $P['networkIsolation']
    $create = $isolated -and (Resolve-SubnetCreationFlag -P $P -Key 'deploySubnets')
    $foundry = Resolve-DeployFlag -P $P -Key 'deployAiFoundry' -Default $true
    $cosmos = Resolve-DeployFlag -P $P -Key 'deployCosmosDb' -Default $true
    $envEnabled = Resolve-DeployFlag -P $P -Key 'deployContainerEnv' -Default $true
    $registry = Resolve-DeployFlag -P $P -Key 'deployContainerRegistry' -Default $true
    $jump = Resolve-DeployJumpbox $P
    # Mirror nullable deployBastion, including deployVM's legacy default.
    $bastionDefault = $isolated -and $jump -and [string]::IsNullOrWhiteSpace((Get-StringValue $P['existingBastionResourceId']))
    $legacy = (Get-StringValue $P['deployVM']).Trim()
    if ($legacy -in 'true', 'false') { $bastionDefault = $bastionDefault -and (ConvertTo-Bool $legacy) }
    $bastionRaw = (Get-StringValue $P['deployBastion']).Trim()
    $bastion = if ($bastionRaw -in 'true', 'false') { ConvertTo-Bool $bastionRaw } else { $bastionDefault }
    $ampls = (Resolve-DeployFlag -P $P -Key 'enablePrivateLogAnalytics' -Default $true) -and
        (Resolve-DeployFlag -P $P -Key 'deployAppInsights' -Default $true) -and
        (Resolve-DeployFlag -P $P -Key 'deployLogAnalytics' -Default $true) -and
        [string]::IsNullOrWhiteSpace((Get-StringValue $P['existingLogAnalyticsWorkspaceResourceId'])) -and
        [string]::IsNullOrWhiteSpace((Get-StringValue $P['existingApplicationInsightsResourceId']))
    $foundryPe = $foundry -or $cosmos -or
        (Resolve-DeployFlag -P $P -Key 'deployStorageAccount' -Default $true) -or
        (Resolve-DeployFlag -P $P -Key 'deploySearchService' -Default $true) -or
        (Resolve-DeployFlag -P $P -Key 'deploySpeechService' -Default $false)
    $applicationPe = $cosmos -or $envEnabled -or $registry -or $ampls -or
        (Resolve-DeployFlag -P $P -Key 'deployKeyVault' -Default $true) -or
        (Resolve-DeployFlag -P $P -Key 'deployAppConfig' -Default $true)
    $ingress = $P['publicIngress']
    if ($P.ContainsKey('publicIngress')) {
        try {
            if ($ingress -is [string]) { $ingress = $ingress | ConvertFrom-Json -NoEnumerate -ErrorAction Stop }
            if ($ingress -is [array] -or
                ($ingress -isnot [System.Collections.IDictionary] -and $ingress -isnot [pscustomobject]) -or
                $ingress.enabled -isnot [bool]) {
                throw 'Expected an object with a Boolean enabled property.'
            }
        } catch {
            Add-Finding -Severity FAIL -Code 'PUBLIC_INGRESS_INVALID' `
                -Message 'publicIngress must be a valid object with a Boolean enabled property; its subnet consumer requirements could not be determined.'
            $ingress = $null
        }
    }
    $appGateway = (ConvertTo-Bool $ingress.enabled) -and $envEnabled -and
        (Resolve-DeployFlag -P $P -Key 'deployContainerApps' -Default $true) -and
        @(Get-ArrayValue $P['containerAppsList']).Count -gt 0

    # Flag, name/prefix parameter stem, defaults, required delegation, largest
    # allowed prefix, enabled consumer. /29 is Azure's general subnet ceiling;
    # Power Platform's /24 is capacity only, not a platform-specific minimum.
    $definitions = @(
        @('deployAgentSubnet', 'agentSubnet', 'agent-subnet', '192.168.0.0/24', 'Microsoft.App/environments', 27, ($foundry -and (Resolve-DeployFlag -P $P -Key 'deployAiFoundrySubnet' -Default $true))),
        @('deployPeSubnet', 'peSubnet', 'pe-subnet', '192.168.2.0/26', '', 28, $foundryPe),
        @('deployApplicationPeSubnet', 'applicationPeSubnet', 'application-pe-subnet', '192.168.3.128/26', '', 28, $applicationPe),
        @('deployAzureBastionSubnet', 'azureBastionSubnet', 'AzureBastionSubnet', '192.168.2.64/26', '', 26, $bastion),
        @('deployAzureFirewallSubnet', 'azureFirewallSubnet', 'AzureFirewallSubnet', '192.168.2.128/26', '', 26, (Resolve-DeployFlag -P $P -Key 'deployAzureFirewall' -Default $true)),
        @('deployGatewaySubnet', 'gatewaySubnet', 'GatewaySubnet', '192.168.2.192/26', '', 29, $false),
        @('deployAppGatewaySubnet', 'azureAppGatewaySubnet', 'AppGatewaySubnet', '192.168.3.0/27', '', 29, $appGateway),
        @('deployJumpboxSubnet', 'jumpboxSubnet', 'jumpbox-subnet', '192.168.3.64/27', '', 29, $jump),
        @('deployAcaEnvironmentSubnet', 'acaEnvironmentSubnet', 'aca-environment-subnet', '192.168.1.0/24', 'Microsoft.App/environments', 27, ($envEnabled -or $cosmos)),
        @('deployDevopsBuildAgentsSubnet', 'devopsBuildAgentsSubnet', 'devops-build-agents-subnet', '192.168.3.96/27', '', 28, ($registry -and (Resolve-DeployFlag -P $P -Key 'deployAcrTaskAgentPool' -Default $true))),
        @('deployPowerPlatformSubnet', 'powerPlatformSubnet', 'powerplatform-subnet', '192.168.4.0/24', 'Microsoft.PowerPlatform/enterprisePolicies', 29, $false),
        @('deployAiGatewaySubnet', 'aiGatewaySubnet', 'ai-gateway-subnet', '192.168.5.0/24', 'Microsoft.Web/serverFarms', 27, $false)
    )
    foreach ($d in $definitions) {
        $nameKey = "$($d[1])Name"
        $prefixKey = "$($d[1])Prefix"
        [pscustomobject]@{
            Flag = $d[0]; NameKey = $nameKey; PrefixKey = $prefixKey
            Name = if ($P.ContainsKey($nameKey)) { Get-StringValue $P[$nameKey] } else { $d[2] }
            Cidr = if ($P.ContainsKey($prefixKey)) { Get-StringValue $P[$prefixKey] } else { $d[3] }
            Delegation = $d[4]; MaxPrefix = $d[5]
            Managed = $create -and (Resolve-SubnetCreationFlag -P $P -Key $d[0])
            Required = $isolated -and $d[6]
        }
    }
}

function Test-SubnetRange {
    param($Subnet, [string]$Cidr, [string[]]$VnetPrefixes, [hashtable]$P)
    try { $range = Get-CidrRange -Cidr $Cidr -RequireAligned }
    catch {
        Add-Finding -Severity FAIL -Code 'SUBNET_CIDR_BAD' -Message "Subnet '$($Subnet.Name)' has invalid IPv4 network CIDR '$Cidr': $_"
        return
    }
    if ($range.Prefix -gt $Subnet.MaxPrefix) {
        $code = if ($Subnet.Flag -eq 'deployAcaEnvironmentSubnet') { 'ACA_SUBNET_TOO_SMALL' } else { 'SUBNET_TOO_SMALL' }
        Add-Finding -Severity FAIL -Code $code -Message "Subnet '$($Subnet.Name)' ($Cidr) must be /$($Subnet.MaxPrefix) or larger."
    }
    elseif ($Subnet.Flag -eq 'deployAiGatewaySubnet' -and $range.Prefix -gt 24) {
        Add-Finding -Severity WARN -Code 'AI_GATEWAY_SUBNET_BELOW_RECOMMENDED' -Message "AI Gateway subnet '$($Subnet.Name)' ($Cidr) meets /27 minimum; /24 is recommended for scaling."
    }
    if ($Subnet.Flag -eq 'deployAcaEnvironmentSubnet' -and $range.Prefix -in 24, 25, 26, 27 -and
        @(Get-ArrayValue $P['workloadProfiles'] | Where-Object { $_.workloadProfileType -and $_.workloadProfileType -ne 'Consumption' }).Count -gt 0) {
        Add-Finding -Severity WARN -Code 'ACA_SUBNET_BELOW_RECOMMENDED' -Message "ACA subnet '$($Subnet.Name)' ($Cidr) is below the recommended /23 for workload-profile environments."
    }
    if ($VnetPrefixes.Count -gt 0 -and -not @($VnetPrefixes | Where-Object { Test-CidrContains -Outer $_ -Inner $Cidr }).Count) {
        Add-Finding -Severity FAIL -Code 'SUBNET_OUTSIDE_VNET' -Message "Subnet '$($Subnet.Name)' ($Cidr) is outside the selected VNet address space: $($VnetPrefixes -join ', ')."
    }
}

function Test-VnetPrefixes {
    param([string[]]$Prefixes)
    if ($Prefixes.Count -eq 0) {
        Add-Finding -Severity FAIL -Code 'VNET_CIDR_BAD' -Message 'The selected VNet address space is empty or could not be verified.'
        return $false
    }
    foreach ($prefix in $Prefixes) {
        try { Get-CidrRange -Cidr $prefix -RequireAligned | Out-Null }
        catch {
            Add-Finding -Severity FAIL -Code 'VNET_CIDR_BAD' -Message "Invalid VNet IPv4 network CIDR '$prefix': $_"
            return $false
        }
    }
    for ($i = 0; $i -lt $Prefixes.Count; $i++) {
        for ($j = $i + 1; $j -lt $Prefixes.Count; $j++) {
            if (Test-CidrOverlap $Prefixes[$i] $Prefixes[$j]) {
                Add-Finding -Severity FAIL -Code 'VNET_CIDR_OVERLAP' -Message "VNet prefixes '$($Prefixes[$i])' and '$($Prefixes[$j])' overlap."
            }
        }
    }
    return $true
}

function Test-SubnetOverlaps {
    param([object[]]$Subnets)
    for ($i = 0; $i -lt $Subnets.Count; $i++) {
        for ($j = $i + 1; $j -lt $Subnets.Count; $j++) {
            try {
                if (Test-CidrOverlap $Subnets[$i].Cidr $Subnets[$j].Cidr) {
                    Add-Finding -Severity FAIL -Code 'SUBNET_OVERLAP' -Message "Subnet '$($Subnets[$i].Name)' ($($Subnets[$i].Cidr)) overlaps '$($Subnets[$j].Name)' ($($Subnets[$j].Cidr))."
                }
            } catch { } # Invalid CIDRs are reported by Test-SubnetRange.
        }
    }
}

function Test-LocalCidrSanity {
    param([hashtable]$P)
    if (-not (ConvertTo-Bool $P['networkIsolation'])) { return }
    $selection = @(Get-SubnetSelection -P $P)
    $active = @($selection | Where-Object { $_.Managed -or $_.Required })
    $byo = ConvertTo-Bool $P['useExistingVNet']
    $vnetPrefixes = if ($P.ContainsKey('vnetAddressPrefixes')) { @(Get-ArrayValue $P['vnetAddressPrefixes']) } else { @('192.168.0.0/21') }
    # BYO containment uses actual Azure address space, never greenfield defaults.
    if ($byo) { $vnetPrefixes = @() }
    elseif (-not (Test-VnetPrefixes -Prefixes $vnetPrefixes)) { $vnetPrefixes = @() }
    foreach ($s in $active) {
        if ($s.Name -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,78}[a-zA-Z0-9_]$' -and $s.Name -notmatch '^[a-zA-Z0-9]$') {
            Add-Finding -Severity FAIL -Code 'SUBNET_NAME_INVALID' -Message "Parameter '$($s.NameKey)' must be a non-empty Azure subnet name of 1-80 characters, ending in an alphanumeric or underscore."
        }
        $reservedName = switch ($s.Flag) {
            'deployGatewaySubnet' { 'GatewaySubnet' }
            'deployAzureBastionSubnet' { 'AzureBastionSubnet' }
            'deployAzureFirewallSubnet' { 'AzureFirewallSubnet' }
        }
        if (($reservedName -and $s.Name -cne $reservedName) -or
            (-not $reservedName -and $s.Name -in 'GatewaySubnet', 'AzureBastionSubnet', 'AzureFirewallSubnet', 'AzureFirewallManagementSubnet', 'RouteServerSubnet')) {
            Add-Finding -Severity FAIL -Code 'SUBNET_RESERVED_NAME' -Message "Subnet '$($s.NameKey)' uses an invalid reserved name '$($s.Name)'; required reserved name: '$reservedName'."
        }
        if (@($active | Where-Object { $_.Name -ieq $s.Name }).Count -gt 1) {
            Add-Finding -Severity FAIL -Code 'SUBNET_NAME_DUPLICATE' -Message "Subnet name '$($s.Name)' is assigned to more than one subnet purpose."
        }
        if (-not $byo -and $s.Required -and -not $s.Managed) {
            Add-Finding -Severity FAIL -Code 'SUBNET_REQUIRED_NOT_MANAGED' -Message "Enabled consumers require subnet '$($s.Name)' but it will not be created in the new VNet. Enable $($s.Flag) and deploySubnets, reuse a VNet, or disable the consumers."
        }
        # Required reuse validates actual properties live, but explicit malformed
        # requested prefixes must still fail rather than silently default.
        $containment = if ($s.Managed) { $vnetPrefixes } else { @() }
        Test-SubnetRange -Subnet $s -Cidr $s.Cidr -VnetPrefixes $containment -P $P
    }
    Test-SubnetOverlaps -Subnets @($active | Where-Object Managed)
    if (@($selection | Where-Object { $_.Managed -and $_.Flag -eq 'deployAiGatewaySubnet' }).Count -and
        -not (Resolve-DeployFlag -P $P -Key 'deployNsgs' -Default $true)) {
        Add-Finding -Severity FAIL -Code 'AI_GATEWAY_NSG_REQUIRED' -Message 'AI Gateway integration requires an associated NSG allowing outbound HTTPS to Azure Key Vault. Enable deployNsgs or reuse an externally managed subnet with verified controls.'
    }
}

function Test-FoundryIqConfiguration {
    param([hashtable]$P)

    $backend = (Get-StringValue $P['retrievalBackend']).Trim()
    if ([string]::IsNullOrWhiteSpace($backend)) { $backend = 'ai_search' }
    if ($backend -notin @('ai_search', 'foundry_iq')) {
        Add-Finding -Severity FAIL -Code 'FOUNDRYIQ_BACKEND_INVALID' `
            -Message "retrievalBackend must be 'ai_search' or 'foundry_iq'; got '$backend'." `
            -Hint "Set RETRIEVAL_BACKEND to ai_search for existing deployments or foundry_iq for Foundry IQ-backed deployments."
        return
    }
    if ($backend -ne 'foundry_iq') { return }

    $deployAiFoundry = ConvertTo-Bool $P['deployAiFoundry']
    $deploySearchRaw = Get-StringValue $P['deploySearchService']
    $deploySearch = if ([string]::IsNullOrWhiteSpace($deploySearchRaw)) { $true } else { ConvertTo-Bool $deploySearchRaw }
    if (-not $deployAiFoundry) {
        Add-Finding -Severity FAIL -Code 'FOUNDRYIQ_FOUNDRY_REQUIRED' `
            -Message "retrievalBackend is foundry_iq but deployAiFoundry is false." `
            -Hint "Enable deployAiFoundry or keep RETRIEVAL_BACKEND=ai_search until a Foundry project and knowledge base exist."
    }
    if (-not $deploySearch) {
        Add-Finding -Severity FAIL -Code 'FOUNDRYIQ_SEARCH_REQUIRED' `
            -Message "retrievalBackend is foundry_iq but deploySearchService is false." `
            -Hint "Pattern B requires the GPT-RAG Azure AI Search service. If you use an external knowledge base, stamp KNOWLEDGE_BASE_* values outside this landing-zone module."
    }

    $pattern = (Get-StringValue $P['foundryIqPattern']).Trim()
    if ([string]::IsNullOrWhiteSpace($pattern)) { $pattern = 'azureBlob' }
    if ($pattern -notin @('azureBlob', 'managed', 'searchIndex')) {
        Add-Finding -Severity FAIL -Code 'FOUNDRYIQ_PATTERN_INVALID' `
            -Message "foundryIqPattern must be 'azureBlob', 'managed', or 'searchIndex'; got '$pattern'."
    }

    $sourceKind = (Get-StringValue $P['foundryIqKnowledgeSourceKind']).Trim()
    if ([string]::IsNullOrWhiteSpace($sourceKind)) { $sourceKind = if ($pattern -eq 'searchIndex') { 'searchIndex' } else { 'azureBlob' } }
    if ($sourceKind -notin @('azureBlob', 'searchIndex')) {
        Add-Finding -Severity FAIL -Code 'FOUNDRYIQ_SOURCE_KIND_INVALID' `
            -Message "foundryIqKnowledgeSourceKind must be 'azureBlob' or 'searchIndex'; got '$sourceKind'."
    }
    elseif (($pattern -eq 'searchIndex' -and $sourceKind -ne 'searchIndex') -or ($pattern -ne 'searchIndex' -and $sourceKind -ne 'azureBlob')) {
        Add-Finding -Severity FAIL -Code 'FOUNDRYIQ_SOURCE_KIND_CONFLICT' `
            -Message "foundryIqKnowledgeSourceKind '$sourceKind' conflicts with foundryIqPattern '$pattern'." `
            -Hint "Use FOUNDRY_IQ_PATTERN=azureBlob with FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND=azureBlob for native Blob, or set both to searchIndex for Pattern B."
    }

    $permissionOptionsJson = (Get-StringValue $P['foundryIqIngestionPermissionOptionsJson']).Trim()
    if (-not [string]::IsNullOrWhiteSpace($permissionOptionsJson)) {
        try {
            $permissionOptions = $permissionOptionsJson | ConvertFrom-Json -NoEnumerate
            if ($null -eq $permissionOptions -or $permissionOptions -isnot [array]) {
                Add-Finding -Severity FAIL -Code 'FOUNDRYIQ_PERMISSION_OPTIONS_INVALID' `
                    -Message "foundryIqIngestionPermissionOptionsJson must be a JSON array; got '$permissionOptionsJson'."
            }
        }
        catch {
            Add-Finding -Severity FAIL -Code 'FOUNDRYIQ_PERMISSION_OPTIONS_INVALID' `
                -Message "foundryIqIngestionPermissionOptionsJson must be valid JSON; got '$permissionOptionsJson'."
        }
    }

    $apiVersion = (Get-StringValue $P['foundryIqApiVersion']).Trim()
    $filterAddOn = ConvertTo-Bool $P['foundryIqFilterAddOnEnabled']
    if ($filterAddOn -and $apiVersion -ne '2026-05-01-preview') {
        Add-Finding -Severity FAIL -Code 'FOUNDRYIQ_FILTERADDON_API_VERSION' `
            -Message "FOUNDRY_IQ_FILTER_ADD_ON_ENABLED requires foundryIqApiVersion 2026-05-01-preview; got '$apiVersion'." `
            -Hint "Use 2026-05-01-preview when Pattern B query-time security trimming is enabled."
    }

    $billingPlan = (Get-StringValue $P['foundryIqKnowledgeRetrievalBillingPlan']).Trim()
    if ([string]::IsNullOrWhiteSpace($billingPlan)) { $billingPlan = 'free' }
    if ($billingPlan -notin @('free', 'standard')) {
        Add-Finding -Severity FAIL -Code 'FOUNDRYIQ_BILLING_PLAN_INVALID' `
            -Message "foundryIqKnowledgeRetrievalBillingPlan must be 'free' or 'standard'; got '$billingPlan'."
    }
    elseif ($billingPlan -eq 'free') {
        Add-Finding -Severity INFO -Code 'FOUNDRYIQ_BILLING_FREE' `
            -Message "Foundry IQ knowledgeRetrieval billing plan is free. Retrieval calls can fail after the included monthly allowance is exhausted." `
            -Hint "Set FOUNDRY_IQ_KNOWLEDGE_RETRIEVAL_BILLING_PLAN=standard to opt in to pay-as-you-go agentic retrieval billing."
    }

    $knowledgeBaseName = (Get-StringValue $P['knowledgeBaseName']).Trim()
    if ([string]::IsNullOrWhiteSpace($knowledgeBaseName)) {
        Add-Finding -Severity FAIL -Code 'FOUNDRYIQ_KB_NAME_REQUIRED' `
            -Message "retrievalBackend is foundry_iq but knowledgeBaseName is empty."
    }

    if ($pattern -eq 'searchIndex') {
        foreach ($requiredName in @('foundryIqKnowledgeSourceName', 'foundryIqSearchIndexName', 'foundryIqSemanticConfigurationName', 'foundryIqSecurityFieldName')) {
            $value = (Get-StringValue $P[$requiredName]).Trim()
            if ([string]::IsNullOrWhiteSpace($value)) {
                Add-Finding -Severity FAIL -Code "FOUNDRYIQ_$($requiredName.ToUpperInvariant())_REQUIRED" `
                    -Message "Pattern B requires parameter '$requiredName' to be set."
            }
        }
        Add-Finding -Severity INFO -Code 'FOUNDRYIQ_PATTERN_B_SELECTED' `
            -Message "Foundry IQ Pattern B selected: the existing GPT-RAG Azure AI Search index will be used as a searchIndex knowledge source." `
            -Hint "Create or update the knowledge source/knowledge base after provisioning with scripts/Configure-FoundryIQKnowledgeBase.ps1; Bicep stamps runtime config and the dedicated connection ID."
    }
    else {
        Add-Finding -Severity WARN -Code 'FOUNDRYIQ_PATTERN_A_NATIVE_LIMITATION' `
            -Message "Foundry IQ Pattern A selected. Plain Blob sources provide container-level RBAC only; per-document trimming requires ADLS Gen2 ACLs, Purview, SharePoint, OneLake/Fabric, or Pattern B." `
            -Hint "Do not claim per-document security for plain Blob managed ingestion."
    }
}

# --------------------------------------------------------------------------
# Azure lookups (live, optional)
# --------------------------------------------------------------------------

function Invoke-AzCli {
    param([string[]]$Arguments)
    try {
        $out = & az @Arguments 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            return ($out -join "`n" | ConvertFrom-Json)
        }
        return $null
    }
    catch {
        return $null
    }
}

function Test-AzureContext {
    if ($SkipAzureLookups) { return $null }
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) { return $null }
    $ctx = Invoke-AzCli -Arguments @('account', 'show', '-o', 'json')
    if (-not $ctx) {
        Add-Finding -Severity WARN -Code 'AZ_NOT_LOGGED_IN' `
            -Message "Could not determine the current Azure context — Azure resource lookups will be skipped." `
            -Hint "Run 'az login' before deploying."
        return $null
    }
    if ($SubscriptionId -and $ctx.id -ne $SubscriptionId) {
        Add-Finding -Severity WARN -Code 'AZ_SUB_MISMATCH' `
            -Message "Pre-flight is using subscription '$SubscriptionId' but the default az context is '$($ctx.id)'." `
            -Hint "Run 'az account set --subscription $SubscriptionId'."
    }
    return $ctx
}

function Get-AzureProperties {
    # Azure CLI network commands flatten ARM properties; generic REST/resource
    # responses may retain them. Accept both without inventing missing facts.
    param($Resource)
    if ($null -ne $Resource.properties) { return $Resource.properties }
    return $Resource
}

function Get-ExistingSubnetPrefixes {
    param($Subnet)
    $properties = Get-AzureProperties $Subnet
    if ($properties.addressPrefixes) { return @($properties.addressPrefixes) }
    if ($properties.addressPrefix) { return @($properties.addressPrefix) }
    return @()
}

function Test-NsgKeyVaultHttps {
    # Prove a broad outbound TCP/443 NSG path to Azure Key Vault, respecting
    # priority. A destination-IP/ASG-specific policy cannot be certified from
    # subnet metadata alone; reject it as unverifiable, never assume an allow.
    param($Nsg, [string[]]$SubnetPrefixes)
    $properties = Get-AzureProperties $Nsg
    $rules = @($properties.securityRules) + @($properties.defaultSecurityRules)
    foreach ($rule in @($rules | Where-Object { $null -ne $_ } | Sort-Object { (Get-AzureProperties $_).priority })) {
        $r = Get-AzureProperties $rule
        if ($r.direction -ine 'Outbound' -or $r.protocol -notin '*', 'Tcp') { continue }
        $ports = @($r.destinationPortRange) + @($r.destinationPortRanges)
        $https = @($ports | Where-Object {
            $_ -eq '*' -or $_ -eq '443' -or ($_ -match '^(\d+)-(\d+)$' -and [int]$matches[1] -le 443 -and [int]$matches[2] -ge 443)
        }).Count -gt 0
        if (-not $https) { continue }
        $destinations = @($r.destinationAddressPrefix) + @($r.destinationAddressPrefixes)
        $broadDestination = @($destinations | Where-Object { $_ -in '*', 'Internet', 'AzureCloud', 'AzureKeyVault', '0.0.0.0/0' }).Count -gt 0
        # An earlier deny with a specific destination may block some Key Vault
        # addresses. Do not claim success based on a later broad allow.
        if ($r.access -ieq 'Deny') { return $false }
        if (-not $broadDestination -or $r.access -ine 'Allow') { continue }
        $sources = @($r.sourceAddressPrefix) + @($r.sourceAddressPrefixes)
        $sourceCovered = @($sources | Where-Object { $_ -in '*', 'VirtualNetwork', '0.0.0.0/0' }).Count -gt 0
        if (-not $sourceCovered) {
            $sourceCovered = $SubnetPrefixes.Count -gt 0
            foreach ($prefix in $SubnetPrefixes) {
                $covered = $false
                foreach ($source in $sources) {
                    try { if (Test-CidrContains $source $prefix) { $covered = $true } } catch { }
                }
                $sourceCovered = $sourceCovered -and $covered
            }
        }
        $sourcePorts = @($r.sourcePortRange) + @($r.sourcePortRanges)
        if ($sourceCovered -and $sourcePorts -contains '*') { return $true }
    }
    return $false
}

function Test-ReusedSubnetProperties {
    param($Definition, $Subnet)
    $properties = Get-AzureProperties $Subnet
    $delegations = @($properties.delegations | Where-Object { $null -ne $_ } | ForEach-Object { (Get-AzureProperties $_).serviceName })
    if (($Definition.Delegation -and ($delegations.Count -ne 1 -or $delegations[0] -cne $Definition.Delegation)) -or
        (-not $Definition.Delegation -and $delegations.Count -gt 0)) {
        $code = if ($Definition.Flag -eq 'deployAcaEnvironmentSubnet') { 'ACA_SUBNET_NO_DELEGATION' } else { 'BYO_SUBNET_DELEGATION_INVALID' }
        Add-Finding -Severity FAIL -Code $code -Message "Reused subnet '$($Definition.Name)' must have exactly the intended delegation '$($Definition.Delegation)' (none for an undelegated subnet)."
    }
    if ($Definition.Flag -eq 'deployAcaEnvironmentSubnet' -and @($properties.serviceEndpoints).Count -gt 0) {
        Add-Finding -Severity WARN -Code 'ACA_SUBNET_HAS_SE' -Message "Reused ACA subnet '$($Definition.Name)' has service endpoints. Review their effect on private endpoint routing."
    }
    $gateway = $Definition.Flag -eq 'deployGatewaySubnet'
    $aiGateway = $Definition.Flag -eq 'deployAiGatewaySubnet'
    if ($gateway -and $properties.networkSecurityGroup.id) {
        Add-Finding -Severity FAIL -Code 'GATEWAY_SUBNET_NSG_FORBIDDEN' -Message 'GatewaySubnet must never have an NSG attached.'
    }
    if ($aiGateway) {
        $nsgId = Get-StringValue $properties.networkSecurityGroup.id
        if ([string]::IsNullOrWhiteSpace($nsgId)) {
            Add-Finding -Severity FAIL -Code 'AI_GATEWAY_NSG_REQUIRED' -Message "Reused AI Gateway subnet '$($Definition.Name)' requires an NSG with outbound HTTPS to Azure Key Vault."
        } else {
            $nsg = Invoke-AzCli -Arguments @('network', 'nsg', 'show', '--ids', $nsgId, '-o', 'json')
            if (-not $nsg -or -not (Test-NsgKeyVaultHttps -Nsg $nsg -SubnetPrefixes @(Get-ExistingSubnetPrefixes $Subnet))) {
                Add-Finding -Severity FAIL -Code 'AI_GATEWAY_KEYVAULT_HTTPS_NOT_VERIFIED' -Message "Could not verify an allowed outbound TCP/443 NSG path to Azure Key Vault for subnet '$($Definition.Name)'. Review NSG priorities, source coverage, and destination rules."
            }
        }
        if (@($properties.privateEndpoints | Where-Object { $null -ne $_ }).Count) {
            Add-Finding -Severity FAIL -Code 'AI_GATEWAY_PRIVATE_ENDPOINT_FORBIDDEN' -Message 'Private endpoints must not use the delegated AI Gateway integration subnet.'
        }
    }
    if (($gateway -or $aiGateway) -and $properties.routeTable.id) {
        $routeTable = Invoke-AzCli -Arguments @('network', 'route-table', 'show', '--ids', $properties.routeTable.id, '-o', 'json')
        if (-not $routeTable -or $null -eq (Get-AzureProperties $routeTable).routes) {
            Add-Finding -Severity FAIL -Code 'BYO_SUBNET_ROUTES_NOT_VERIFIED' -Message "Could not read the route table on subnet '$($Definition.Name)'; required route restrictions cannot be verified."
        } else {
            $defaults = @((Get-AzureProperties $routeTable).routes | Where-Object { (Get-AzureProperties $_).addressPrefix -eq '0.0.0.0/0' })
            if ($gateway -and $defaults.Count) {
                Add-Finding -Severity FAIL -Code 'GATEWAY_SUBNET_DEFAULT_ROUTE_FORBIDDEN' -Message 'GatewaySubnet must never have a default-route UDR.'
            }
            if ($aiGateway -and @($defaults | Where-Object { (Get-AzureProperties $_).nextHopType -ine 'Internet' }).Count) {
                Add-Finding -Severity FAIL -Code 'AI_GATEWAY_KEYVAULT_HTTPS_NOT_VERIFIED' -Message 'AI Gateway default-route UDR redirects or blocks egress; the Key Vault HTTPS path through that next hop cannot be verified by preflight.'
            }
        }
    }
}

function Test-ExistingVnetSubnets {
    param([hashtable]$P)
    if (-not (ConvertTo-Bool $P['networkIsolation']) -or -not (ConvertTo-Bool $P['useExistingVNet'])) { return $null }
    $vnetId = Get-StringValue $P['existingVnetResourceId']
    if ($vnetId -notmatch '^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.Network/virtualNetworks/[^/]+$') {
        Add-Finding -Severity FAIL -Code 'BYO_VNET_NO_ID' -Message 'useExistingVNet=true requires a full existingVnetResourceId.'
        return $null
    }
    if ($SkipAzureLookups) {
        Add-Finding -Severity FAIL -Code 'BYO_NETWORK_NOT_VERIFIED' -Message 'BYO address space, existing overlaps, and required reused subnet properties cannot be verified with -SkipAzureLookups. Run live read-only preflight before provisioning.'
        return $null
    }
    $vnet = Invoke-AzCli -Arguments @('network', 'vnet', 'show', '--ids', $vnetId, '-o', 'json')
    if (-not $vnet) {
        Add-Finding -Severity FAIL -Code 'BYO_VNET_LOOKUP_FAILED' -Message 'Could not read the selected existing VNet. Address space and required reused subnets are not verified; check the ID, login, and scoped Reader access.'
        return $null
    }
    $properties = Get-AzureProperties $vnet
    $prefixes = @($properties.addressSpace.addressPrefixes)
    if (-not (Test-VnetPrefixes -Prefixes $prefixes)) { return $null }
    if ($null -eq $properties.subnets) {
        Add-Finding -Severity FAIL -Code 'BYO_NETWORK_NOT_VERIFIED' -Message 'The selected VNet response omitted its subnet collection; existing overlap and reuse checks cannot be completed.'
        return $null
    }
    $selection = @(Get-SubnetSelection -P $P)
    $ranges = [System.Collections.Generic.List[object]]::new()
    foreach ($s in @($selection | Where-Object Managed)) {
        Test-SubnetRange -Subnet $s -Cidr $s.Cidr -VnetPrefixes $prefixes -P $P
        $ranges.Add([pscustomobject]@{ Name = $s.Name; Cidr = $s.Cidr })
    }
    # Managed names use the requested range; required reused names use the
    # explicit lookup below. All other retained ranges use the VNet listing,
    # even when an unused subnet happens to share a configured optional name.
    foreach ($existing in @($properties.subnets)) {
        if (@($selection | Where-Object { ($_.Managed -or $_.Required) -and $_.Name -ieq $existing.name }).Count) { continue }
        $existingPrefixes = @(Get-ExistingSubnetPrefixes $existing)
        if ($existingPrefixes.Count -eq 0) {
            Add-Finding -Severity FAIL -Code 'BYO_NETWORK_NOT_VERIFIED' -Message "Existing subnet '$($existing.name)' has no readable address prefixes."
        }
        foreach ($prefix in $existingPrefixes) {
            try { Get-CidrRange -Cidr $prefix -RequireAligned | Out-Null }
            catch { Add-Finding -Severity FAIL -Code 'SUBNET_CIDR_BAD' -Message "Existing subnet '$($existing.name)' has invalid IPv4 CIDR '$prefix'."; continue }
            $ranges.Add([pscustomobject]@{ Name = $existing.name; Cidr = $prefix })
        }
    }
    foreach ($s in @($selection | Where-Object { $_.Required -and -not $_.Managed })) {
        $existing = @($properties.subnets | Where-Object { $_.name -ieq $s.Name })
        if ($existing.Count -eq 0) {
            Add-Finding -Severity FAIL -Code 'BYO_SUBNET_MISSING' -Message "Enabled consumers require reused subnet '$($s.Name)' ($($s.NameKey)), but it does not exist in the selected VNet. Enable its creation or disable those consumers."
            continue
        }
        # Explicit per-subnet read ensures required properties are available;
        # never equate a name in a partial VNet listing with verified reuse.
        $subnet = Invoke-AzCli -Arguments @('network', 'vnet', 'subnet', 'show', '--ids', "$vnetId/subnets/$($s.Name)", '-o', 'json')
        if (-not $subnet) {
            Add-Finding -Severity FAIL -Code 'BYO_SUBNET_LOOKUP_FAILED' -Message "Could not verify reused subnet '$($s.Name)' in the selected VNet."
            continue
        }
        $actualPrefixes = @(Get-ExistingSubnetPrefixes $subnet)
        if ($actualPrefixes.Count -eq 0) {
            Add-Finding -Severity FAIL -Code 'BYO_NETWORK_NOT_VERIFIED' -Message "Reused subnet '$($s.Name)' has no readable address prefixes."
        }
        foreach ($prefix in $actualPrefixes) {
            Test-SubnetRange -Subnet $s -Cidr $prefix -VnetPrefixes $prefixes -P $P
            $ranges.Add([pscustomobject]@{ Name = $s.Name; Cidr = $prefix })
        }
        Test-ReusedSubnetProperties -Definition $s -Subnet $subnet
    }
    Test-SubnetOverlaps -Subnets @($ranges.ToArray())
    return $vnet
}

function Test-AzureResources {
    param([hashtable]$P)

    # Network requirements fail closed even when login/context/lookup is absent.
    # Other legacy BYO checks retain their existing warning behavior.
    $selectedVnet = Test-ExistingVnetSubnets -P $P
    if ($SkipAzureLookups) {
        Add-Finding -Severity INFO -Code 'AZURE_SKIPPED' -Message "Azure resource lookups skipped (-SkipAzureLookups)."
        return
    }
    $ctx = Test-AzureContext
    if (-not $ctx) { return }

    # BYO Private DNS zones — validate naming
    $expectedZoneName = @{
        'existingPrivateDnsZoneCogSvcsResourceId'         = 'privatelink.cognitiveservices.azure.com'
        'existingPrivateDnsZoneOpenAiResourceId'          = 'privatelink.openai.azure.com'
        'existingPrivateDnsZoneAiServicesResourceId'      = 'privatelink.services.ai.azure.com'
        'existingPrivateDnsZoneSearchResourceId'          = 'privatelink.search.windows.net'
        'existingPrivateDnsZoneCosmosResourceId'          = 'privatelink.documents.azure.com'
        # blob/containerApps/acr zones include region/suffix tokens — match by prefix
        'existingPrivateDnsZoneBlobResourceId'            = 'privatelink.blob.'
        'existingPrivateDnsZoneKeyVaultResourceId'        = 'privatelink.vaultcore.azure.net'
        'existingPrivateDnsZoneAppConfigResourceId'       = 'privatelink.azconfig.io'
        'existingPrivateDnsZoneContainerAppsResourceId'   = 'privatelink.'
        'existingPrivateDnsZoneAcrResourceId'             = 'privatelink.'
        'existingPrivateDnsZoneAzureMonitorResourceId'    = 'privatelink.monitor.azure.com'
        'existingPrivateDnsZoneOmsOpsInsightsResourceId'  = 'privatelink.oms.opinsights.azure.com'
        'existingPrivateDnsZoneOdsOpsInsightsResourceId'  = 'privatelink.ods.opinsights.azure.com'
        'existingPrivateDnsZoneAzureAutomationResourceId' = 'privatelink.agentsvc.azure.automation.net'
        'existingPrivateDnsZoneAppInsightsResourceId'     = 'privatelink.applicationinsights.io'
    }
    foreach ($entry in $expectedZoneName.GetEnumerator()) {
        $rid = Get-StringValue $P[$entry.Key]
        if ([string]::IsNullOrEmpty($rid)) { continue }
        $segs = $rid.Trim('/').Split('/')
        if ($segs.Count -lt 8) {
            Add-Finding -Severity FAIL -Code 'DNS_ZONE_RID_BAD' -Message "'$($entry.Key)' value '$rid' is not a valid Private DNS zone resource ID."
            continue
        }
        $zoneName = $segs[-1]
        $expected = $entry.Value
        if ($expected.EndsWith('.')) {
            if (-not $zoneName.StartsWith($expected)) {
                Add-Finding -Severity FAIL -Code 'DNS_ZONE_NAME_MISMATCH' `
                    -Message "'$($entry.Key)' points at zone '$zoneName' but the parameter expects a zone whose name starts with '$expected'." `
                    -Hint "Verify the resource ID points at the correct Private DNS zone."
            }
        }
        else {
            if ($zoneName -ne $expected) {
                Add-Finding -Severity FAIL -Code 'DNS_ZONE_NAME_MISMATCH' `
                    -Message "'$($entry.Key)' points at zone '$zoneName' but the parameter expects '$expected'." `
                    -Hint "Verify the resource ID points at the correct Private DNS zone."
            }
        }
        # Existence check (read-only)
        $zone = Invoke-AzCli -Arguments @('network', 'private-dns', 'zone', 'show', '--ids', $rid, '-o', 'json')
        if (-not $zone) {
            Add-Finding -Severity WARN -Code 'DNS_ZONE_LOOKUP_FAILED' `
                -Message "Could not read Private DNS zone '$rid' — the deployment will fail later if this zone does not exist." `
                -Hint "Verify the ID and that the current identity has Reader on the zone."
        }
    }

    # Existing LAW / App Insights / Route Table / Hub VNet
    foreach ($pair in @(
            @{ Key = 'existingLogAnalyticsWorkspaceResourceId'; Code = 'LAW_LOOKUP_FAILED'; Kind = 'Log Analytics workspace' },
            @{ Key = 'existingApplicationInsightsResourceId'; Code = 'APPI_LOOKUP_FAILED'; Kind = 'Application Insights' },
            @{ Key = 'hubIntegrationExistingRouteTableResourceId'; Code = 'RT_LOOKUP_FAILED'; Kind = 'route table' },
            @{ Key = 'existingBastionResourceId'; Code = 'BASTION_LOOKUP_FAILED'; Kind = 'Bastion host' },
            @{ Key = 'existingNatGatewayResourceId'; Code = 'NATGW_LOOKUP_FAILED'; Kind = 'NAT Gateway' }
        )) {
        $rid = Get-StringValue $P[$pair.Key]
        if ([string]::IsNullOrEmpty($rid)) { continue }
        $resource = Invoke-AzCli -Arguments @('resource', 'show', '--ids', $rid, '-o', 'json')
        if (-not $resource) {
            Add-Finding -Severity WARN -Code $pair.Code `
                -Message "Could not read existing $($pair.Kind) at '$rid' — the deployment will fail later if it does not exist." `
                -Hint "Verify the ID and that the current identity has Reader on the resource."
        }
    }

    # Hub VNet address-space overlap
    $hubRid = Get-StringValue $P['hubIntegrationHubVnetResourceId']
    if (-not [string]::IsNullOrEmpty($hubRid)) {
        $hubVnet = Invoke-AzCli -Arguments @('network', 'vnet', 'show', '--ids', $hubRid, '-o', 'json')
        if (-not $hubVnet) {
            Add-Finding -Severity WARN -Code 'HUB_VNET_LOOKUP_FAILED' `
                -Message "Could not read hub VNet '$hubRid' — address-space overlap detection will be skipped." `
                -Hint "Verify the ID and that the current identity has Reader on the hub VNet's resource group."
        }
        else {
            $spokePrefixes = if ($selectedVnet) { @((Get-AzureProperties $selectedVnet).addressSpace.addressPrefixes) }
                elseif (ConvertTo-Bool $P['useExistingVNet']) { @() }
                elseif ($P.ContainsKey('vnetAddressPrefixes')) { @(Get-ArrayValue $P['vnetAddressPrefixes']) }
                else { @('192.168.0.0/21') }
            $hubPrefixes = @($hubVnet.addressSpace.addressPrefixes)
            foreach ($sp in $spokePrefixes) {
                foreach ($hp in $hubPrefixes) {
                    try {
                        if (Test-CidrOverlap -A $sp -B $hp) {
                            Add-Finding -Severity FAIL -Code 'HUB_SPOKE_OVERLAP' `
                                -Message "Spoke VNet prefix '$sp' overlaps hub VNet prefix '$hp'. Peering will fail." `
                                -Hint "Pick a non-overlapping VNET_ADDRESS_PREFIXES range for the spoke."
                        }
                    }
                    catch { }
                }
            }
        }
    }
}

# --------------------------------------------------------------------------
# Resource-provider registration check. Discovers the Azure resource provider
# namespaces referenced by `resource 'Microsoft.X/...'` declarations across all
# of the repo's *.bicep files (excluding tests/), then verifies each is
# Registered. Providers are classified as "selected" or "optional" against the
# effective feature flags: an unregistered provider only FAILs preflight when
# its resource is actually selected by the current parameters; providers for
# feature-flagged-off resources are reported as a non-blocking WARN. Read-only —
# does not attempt to register providers.
# --------------------------------------------------------------------------

function Get-RequiredResourceProviders {
    # Friendly descriptions for known namespaces. The actual *list* of
    # namespaces is derived from the Bicep tree below so it stays in sync with
    # main.bicep / modules as resources are added or removed. Unknown
    # namespaces (e.g. a future addition) still get checked — they just show
    # a generic reason and are treated as optional (WARN, never FAIL).
    param([hashtable]$P = @{})
    $reasonByNamespace = @{
        'Microsoft.Resources'            = 'Always required (resource group, deployments)'
        'Microsoft.Authorization'        = 'Role assignments and role definitions'
        'Microsoft.Network'              = 'VNet, NSGs, Private DNS, Private Endpoints, Bastion, NAT Gateway, Firewall, App Gateway'
        'Microsoft.ManagedIdentity'      = 'User-assigned managed identities'
        'Microsoft.Compute'              = 'Jumpbox VM and VM extensions'
        'Microsoft.Storage'              = 'Storage accounts (workload + AI Foundry)'
        'Microsoft.KeyVault'             = 'Key Vault'
        'Microsoft.AppConfiguration'     = 'App Configuration store'
        'Microsoft.OperationalInsights'  = 'Log Analytics workspace'
        'Microsoft.Insights'             = 'Application Insights, diagnostic settings, AMPLS'
        'Microsoft.OperationsManagement' = 'Log Analytics solutions'
        'Microsoft.AlertsManagement'     = 'Smart detector alerts on Application Insights'
        'Microsoft.App'                  = 'Container Apps + managed environment'
        'Microsoft.ContainerRegistry'    = 'Azure Container Registry + ACR Tasks agent pool'
        'Microsoft.CognitiveServices'    = 'AI Foundry account/project, AI Services, Speech'
        'Microsoft.Search'               = 'Azure AI Search'
        'Microsoft.DocumentDB'           = 'Cosmos DB workload account + AI Foundry-bundled Cosmos'
        'Microsoft.Bing'                 = 'Bing grounding'
        'Microsoft.PowerPlatform'        = 'Power Platform subnet delegation'
        'Microsoft.Web'                  = 'AI Gateway outbound integration subnet delegation'
    }

    # Always-required providers used implicitly at deploy time (LA workspace
    # solutions, smart-detector alerts attached to App Insights, the resource
    # group/deployment plumbing itself). These never appear as `resource`
    # declarations in the Bicep tree so we add them unconditionally.
    $implicitNamespaces = @('Microsoft.Resources', 'Microsoft.OperationsManagement', 'Microsoft.AlertsManagement')

    # Discover provider namespaces from `resource 'Microsoft.X/...'` declarations
    # across the repo's Bicep files. Skips tests/ (not part of azd provision).
    $repoRoot = if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { '' } else { Split-Path -Parent $PSScriptRoot }
    $discovered = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $resourceRegex = [regex]::new("^\s*resource\s+\w+\s+'(Microsoft\.[^/']+)/", [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)

    if (-not [string]::IsNullOrWhiteSpace($repoRoot) -and (Test-Path -LiteralPath $repoRoot)) {
        Get-ChildItem -Path $repoRoot -Recurse -Filter *.bicep -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch '[\\/]tests[\\/]' } |
            ForEach-Object {
                foreach ($line in (Get-Content -Path $_.FullName -ErrorAction SilentlyContinue)) {
                    $m = $resourceRegex.Match($line)
                    if ($m.Success) { [void]$discovered.Add($m.Groups[1].Value) }
                }
            }
    }

    # Canonicalize casing against the known-namespace map (Bicep accepts
    # 'microsoft.insights' lowercase too; az provider expects the canonical
    # 'Microsoft.Insights').
    $canonical = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($ns in $discovered) {
        $known = @($reasonByNamespace.Keys | Where-Object { $_ -ieq $ns } | Select-Object -First 1)
        if ($known.Count -gt 0) { [void]$canonical.Add($known[0]) } else { [void]$canonical.Add($ns) }
    }
    foreach ($ns in $implicitNamespaces) { [void]$canonical.Add($ns) }

    # Fallback: if Bicep discovery returned nothing (e.g. script run from an
    # unusual location), fall back to the full known-namespace list so the
    # check still has coverage.
    if ($canonical.Count -le $implicitNamespaces.Count) {
        foreach ($ns in $reasonByNamespace.Keys) { [void]$canonical.Add($ns) }
    }

    # Map each namespace to whether the current parameters actually select it.
    # Mirrors the feature-flag resolution used elsewhere (Test-RegionalReadiness)
    # and the default-on/off semantics in main.parameters.json. Providers not in
    # this map default to optional ($false) so unknown discoveries never hard-fail.
    $deployAiFoundry         = Resolve-DeployFlag -P $P -Key 'deployAiFoundry'         -Default $true
    $deploySpeech            = Resolve-DeployFlag -P $P -Key 'deploySpeechService'     -Default $false
    $deployCosmos            = Resolve-DeployFlag -P $P -Key 'deployCosmosDb'          -Default $true
    $deploySearch            = Resolve-DeployFlag -P $P -Key 'deploySearchService'     -Default $true
    $deployBing              = Resolve-DeployFlag -P $P -Key 'deployGroundingWithBing' -Default $false
    $deployKeyVault          = Resolve-DeployFlag -P $P -Key 'deployKeyVault'          -Default $true
    $deployStorage           = Resolve-DeployFlag -P $P -Key 'deployStorageAccount'    -Default $true
    $deployAppConfig         = Resolve-DeployFlag -P $P -Key 'deployAppConfig'         -Default $true
    $deployContainerApps     = Resolve-DeployFlag -P $P -Key 'deployContainerApps'     -Default $true
    $deployContainerEnv      = Resolve-DeployFlag -P $P -Key 'deployContainerEnv'      -Default $true
    $deployContainerRegistry = Resolve-DeployFlag -P $P -Key 'deployContainerRegistry' -Default $true
    $deployLogAnalytics      = Resolve-DeployFlag -P $P -Key 'deployLogAnalytics'      -Default $true
    $deployJump              = Resolve-DeployJumpbox $P

    $selectionByNamespace = @{
        'Microsoft.Resources'            = $true
        'Microsoft.Authorization'        = $true
        'Microsoft.ManagedIdentity'      = $true
        'Microsoft.Insights'             = $true
        'Microsoft.OperationsManagement' = $true
        'Microsoft.AlertsManagement'     = $true
        'Microsoft.Network'              = $true
        'Microsoft.OperationalInsights'  = $deployLogAnalytics
        'Microsoft.Compute'              = $deployJump
        'Microsoft.Storage'              = ($deployStorage -or $deployAiFoundry)
        'Microsoft.KeyVault'             = $deployKeyVault
        'Microsoft.AppConfiguration'     = $deployAppConfig
        'Microsoft.App'                  = ($deployContainerApps -or $deployContainerEnv)
        'Microsoft.ContainerRegistry'    = $deployContainerRegistry
        'Microsoft.CognitiveServices'    = ($deployAiFoundry -or $deploySpeech)
        'Microsoft.Search'               = $deploySearch
        'Microsoft.DocumentDB'           = ($deployCosmos -or $deployAiFoundry)
        'Microsoft.Bing'                 = $deployBing
    }

    $subnetProviders = @(Get-SubnetSelection -P $P | Where-Object { $_.Managed -and $_.Delegation } |
        ForEach-Object { ($_.Delegation -split '/')[0] } | Sort-Object -Unique)
    foreach ($ns in $subnetProviders) { [void]$canonical.Add($ns) }
    $networkSubscription = $SubscriptionId
    if ((ConvertTo-Bool $P['useExistingVNet']) -and
        (Get-StringValue $P['existingVnetResourceId']) -match '^/subscriptions/([^/]+)/') {
        $networkSubscription = $matches[1]
    }
    $canonical | Sort-Object | ForEach-Object {
        $ns = $_
        $reason = if ($reasonByNamespace.ContainsKey($ns)) { $reasonByNamespace[$ns] } else { 'Discovered in repository Bicep files' }
        $selected = if ($selectionByNamespace.ContainsKey($ns)) { [bool]$selectionByNamespace[$ns] } else { $false }
        # Delegation-only namespaces must be checked in the VNet subscription,
        # not implicitly in the application's current CLI subscription.
        if ($ns -in 'Microsoft.PowerPlatform', 'Microsoft.Web') {
            if ($subnetProviders -contains $ns) {
                @{ Namespace = $ns; Reason = $reason; Selected = $true; SubscriptionId = $networkSubscription; SubnetPrerequisite = $true }
            }
        } else {
            @{ Namespace = $ns; Reason = $reason; Selected = $selected; SubscriptionId = $SubscriptionId }
        }
    }
    if ($subnetProviders -contains 'Microsoft.App') {
        @{ Namespace = 'Microsoft.App'; Reason = 'Agent/ACA subnet delegation'; Selected = $true; SubscriptionId = $networkSubscription; SubnetPrerequisite = $true }
    }
}

function Get-VmSkuInfo {
    # Single source of truth for VM-SKU facts: queries Azure for the SKU's
    # availability, vCPU count, family (quota counter), and any restrictions
    # active in the target region/subscription. Returns $null when the SKU is
    # not offered in the region.
    param(
        [Parameter(Mandatory)] [string]$Location,
        [Parameter(Mandatory)] [string]$VmSize
    )
    if ([string]::IsNullOrWhiteSpace($Location) -or [string]::IsNullOrWhiteSpace($VmSize)) { return $null }
    $skus = Invoke-AzCliRaw -Arguments @('vm', 'list-skus', '--location', $Location, '--size', $VmSize, '--resource-type', 'virtualMachines', '--all', '-o', 'json')
    if (-not $skus) { return $null }
    $match = @($skus | Where-Object { $_.name -eq $VmSize -and $_.resourceType -eq 'virtualMachines' } | Select-Object -First 1)
    if (-not $match) { return $null }

    $vCpus = 0
    if ($match.capabilities) {
        $cap = @($match.capabilities | Where-Object { $_.name -eq 'vCPUs' -or $_.name -eq 'vCPUsAvailable' } | Select-Object -First 1)
        if ($cap) { $vCpus = [int]$cap.value }
    }
    $restrictions = @()
    if ($match.PSObject.Properties.Name -contains 'restrictions' -and $match.restrictions) {
        $restrictions = @($match.restrictions | Where-Object { $_ })
    }
    [pscustomobject]@{
        Name         = [string]$match.name
        Family       = [string]$match.family
        VCpus        = $vCpus
        Restrictions = $restrictions
    }
}

function Test-ResourceProviders {
    param([hashtable]$P = @{})
    if ($SkipAzureLookups) { return }
    $providers = @(Get-RequiredResourceProviders -P $P)
    if (-not (Invoke-AzCli -Arguments @('account', 'show', '-o', 'json'))) {
        if (@($providers | Where-Object SubnetPrerequisite).Count) {
            Add-Finding -Severity FAIL -Code 'RP_LOOKUP_FAILED' -Message 'Selected subnet delegation provider prerequisites could not be verified. Log in and rerun read-only preflight.'
        }
        return
    }
    foreach ($entry in $providers) {
        $ns = $entry.Namespace
        $arguments = @('provider', 'show', '--namespace', $ns, '-o', 'json')
        if ($entry.SubscriptionId) { $arguments += @('--subscription', $entry.SubscriptionId) }
        $provider = Invoke-AzCli -Arguments $arguments
        $state = Get-StringValue $provider.registrationState
        $severity = if ($entry.Selected) { 'FAIL' } else { 'WARN' }
        if ([string]::IsNullOrWhiteSpace($state)) {
            Add-Finding -Severity $severity -Code 'RP_LOOKUP_FAILED' `
                -Message "Could not read registration state for provider '$ns' ($($entry.Reason))." `
                -Hint "Run: az provider show --namespace $ns --query registrationState -o tsv"
            continue
        }
        $state = $state.Trim()
        if ($state -eq 'Registered') { continue }
        if ($state -eq 'Registering') {
            Add-Finding -Severity $severity -Code 'RP_REGISTERING' `
                -Message "Provider '$ns' is currently '$state' — wait until it reaches 'Registered' before deploying." `
                -Hint "Re-run preflight in a minute, or block on it with: az provider register --namespace $ns --wait"
        }
        elseif ($entry.Selected) {
            Add-Finding -Severity FAIL -Code 'RP_NOT_REGISTERED' `
                -Message "Provider '$ns' is '$state', not 'Registered'. Used for: $($entry.Reason)." `
                -Hint "Run: az provider register --namespace $ns --wait"
        }
        else {
            # Provider is referenced somewhere in the Bicep tree but the resource
            # is not selected by the current parameters (feature-flagged off, or a
            # namespace this script doesn't map). Surface it as advisory only so
            # minimal/subset deployments (e.g. gpt-rag with Search/Cosmos/Bing
            # disabled) don't fail preflight on providers they never deploy.
            Add-Finding -Severity WARN -Code 'RP_NOT_REGISTERED_OPTIONAL' `
                -Message "Provider '$ns' is '$state', not 'Registered'. Only needed if you enable: $($entry.Reason). Not selected by the current parameters, so not blocking." `
                -Hint "If you plan to enable this feature, run: az provider register --namespace $ns --wait"
        }
    }
}

# --------------------------------------------------------------------------
# Regional readiness (live, optional) — issue #72
# --------------------------------------------------------------------------
#
# Validates that the target region(s) and subscription can actually host the
# resources the landing zone is about to provision. Catches the "azd up returns
# an opaque ARM error 25 minutes in" class of failures by surfacing them as
# pre-flight findings:
#
#   * Subscription drift — `az` CLI default subscription does not match the
#     subscription recorded in the azd environment. Only fires when run from a
#     `preprovision` hook (i.e. an azd env is present).
#   * Provider/location support — for each resource type the landing zone
#     provisions, confirm the provider lists the chosen region as supported.
#   * Jumpbox VM SKU availability — when a jumpbox is requested, confirm the
#     requested VM size is offered (and not restricted) in the region for the
#     current subscription.
#   * AI model quota — for each entry in `modelDeploymentList`, call
#     `az cognitiveservices usage list --location <region>` and verify the
#     requested capacity fits in the available quota.
#
# Everything in this block is **read-only** and **non-blocking on WARN**. The
# whole block is skipped when `-SkipRegional`, `-SkipAzureLookups`, or
# `$env:LZ_PREFLIGHT_REGIONAL_SKIP=true` is set.
# --------------------------------------------------------------------------

function Get-NormalizedLocation {
    param([string]$Location)
    if ([string]::IsNullOrWhiteSpace($Location)) { return '' }
    return (($Location -replace '[^A-Za-z0-9]', '').ToLowerInvariant())
}

function Invoke-AzCliRaw {
    # Like Invoke-AzCli, but accepts callers that append their own '-o json' and
    # tolerates az subcommands that print warnings to stderr.
    param([string[]]$Arguments)
    try {
        $out = & az @Arguments 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            return ($out -join "`n" | ConvertFrom-Json)
        }
        return $null
    }
    catch {
        return $null
    }
}

function Test-ProviderLocation {
    param(
        [Parameter(Mandatory)] [string]$ProviderNamespace,
        [Parameter(Mandatory)] [string]$ResourceType,
        [Parameter(Mandatory)] [string]$Location,
        [Parameter(Mandatory)] [string]$DisplayName,
        [Parameter(Mandatory)] [string]$CodePrefix
    )
    if ([string]::IsNullOrWhiteSpace($Location)) {
        Add-Finding -Severity WARN -Code "${CodePrefix}_NO_LOCATION" `
            -Message "$DisplayName provider/location check skipped: no location resolved from parameters."
        return
    }
    $provider = Invoke-AzCliRaw -Arguments @('provider', 'show', '--namespace', $ProviderNamespace, '-o', 'json')
    if (-not $provider) {
        Add-Finding -Severity WARN -Code "${CodePrefix}_PROVIDER_LOOKUP" `
            -Message "Could not query provider $ProviderNamespace for $DisplayName." `
            -Hint "Ensure 'az' is logged in and the provider is registered (az provider register --namespace $ProviderNamespace)."
        return
    }
    if ($provider.registrationState -and $provider.registrationState -ne 'Registered') {
        Add-Finding -Severity FAIL -Code "${CodePrefix}_PROVIDER_UNREG" `
            -Message "Provider $ProviderNamespace ($DisplayName) is '$($provider.registrationState)', not 'Registered'." `
            -Hint "Run: az provider register --namespace $ProviderNamespace"
        return
    }
    $rt = @($provider.resourceTypes | Where-Object { $_.resourceType -eq $ResourceType } | Select-Object -First 1)
    if (-not $rt) {
        Add-Finding -Severity WARN -Code "${CodePrefix}_RT_MISSING" `
            -Message "Provider $ProviderNamespace did not report resource type $ResourceType."
        return
    }
    $target = Get-NormalizedLocation $Location
    $supported = @($rt.locations | ForEach-Object { Get-NormalizedLocation $_ }) -contains $target
    if (-not $supported) {
        Add-Finding -Severity FAIL -Code "${CodePrefix}_NOT_IN_REGION" `
            -Message "$DisplayName is not listed as supported in region '$Location' for this subscription." `
            -Hint "Pick a supported region or remove this resource from the deployment."
    }
}

function Test-VmSku {
    # Validates SKU availability + restrictions for the target region. Accepts
    # a pre-fetched VmSkuInfo (from Get-VmSkuInfo) to avoid a second
    # `az vm list-skus` round-trip when Test-RegionalVcpuQuota also needs it.
    param(
        [Parameter(Mandatory)] [string]$Location,
        [Parameter(Mandatory)] [string]$VmSize,
        $VmSkuInfo
    )
    if ([string]::IsNullOrWhiteSpace($Location) -or [string]::IsNullOrWhiteSpace($VmSize)) { return }
    if (-not $VmSkuInfo) { $VmSkuInfo = Get-VmSkuInfo -Location $Location -VmSize $VmSize }
    if (-not $VmSkuInfo) {
        Add-Finding -Severity FAIL -Code 'JUMPBOX_VM_NOT_FOUND' `
            -Message "Jumpbox VM size '$VmSize' is not offered in region '$Location'." `
            -Hint "Pick a different vmSize (AZURE_VM_SIZE) or a region that offers this SKU."
        return
    }
    if ($VmSkuInfo.Restrictions.Count -gt 0) {
        $msgs = $VmSkuInfo.Restrictions | ForEach-Object {
            $reason = if ($_.reasonCode) { $_.reasonCode } else { 'Restricted' }
            "$reason ($($_.type): $($_.values -join ','))"
        }
        Add-Finding -Severity FAIL -Code 'JUMPBOX_VM_RESTRICTED' `
            -Message "Jumpbox VM size '$VmSize' is restricted in '${Location}': $($msgs -join '; ')." `
            -Hint "Pick a different vmSize or request a quota increase."
    }
}

function Test-ModelQuota {
    param(
        [Parameter(Mandatory)] $ModelDeployments,
        [Parameter(Mandatory)] [string]$Location
    )
    if ([string]::IsNullOrWhiteSpace($Location)) { return }
    $deployments = @($ModelDeployments | Where-Object { $_ -ne $null })
    if ($deployments.Count -eq 0) { return }

    $selectedSubscription = if ($SubscriptionId) { $SubscriptionId } else { $env:AZURE_SUBSCRIPTION_ID }
    $usageArguments = @('cognitiveservices', 'usage', 'list', '--location', $Location, '-o', 'json')
    if ($selectedSubscription) { $usageArguments += @('--subscription', $selectedSubscription) }
    $usage = Invoke-AzCliRaw -Arguments $usageArguments
    if (-not $usage) {
        Add-Finding -Severity WARN -Code 'MODEL_QUOTA_LOOKUP' `
            -Message "Could not read Cognitive Services usage/quota for '$Location'." `
            -Hint "Run 'az cognitiveservices usage list --location $Location' and verify Microsoft.CognitiveServices is registered."
        return
    }

    $deployments = @($deployments | Where-Object { $_.model.format -eq 'OpenAI' })
    if ($deployments.Count -eq 0) { return }
    $selectedEnvironment = Get-AzdEnvValues
    $foundryGroup = Get-FoundryResourceGroup -ApplicationResourceGroup $selectedEnvironment['AZURE_RESOURCE_GROUP'] `
        -FoundryResourceGroup $selectedEnvironment['AZURE_FOUNDRY_RESOURCE_GROUP']
    $existing = @(Get-ExistingModelDeployments -Location $Location -SubscriptionId $selectedSubscription `
        -ProjectResourceId $selectedEnvironment['AZURE_AI_PROJECT_RESOURCE_ID'] `
        -ResourceGroup $foundryGroup -ReadAzureJson {
        param([string[]]$Arguments)
        Invoke-AzCliRaw -Arguments ($Arguments + @('-o', 'json'))
    } -OnWarning {
        param([string]$Message)
        Add-Finding -Severity WARN -Code 'MODEL_QUOTA_EXISTING_TARGET' -Message $Message
    })
    try {
        $requests = @(Get-ModelQuotaRequirements -Models $deployments -ExistingDeployments $existing)
    } catch {
        Add-Finding -Severity FAIL -Code 'MODEL_QUOTA_INVALID' -Message $_.Exception.Message
        return
    }
    $failures = @()
    foreach ($request in $requests) {
        $quotaName = $request.QuotaName
        $quota = @($usage | Where-Object { $_.name.value -eq $quotaName } | Select-Object -First 1)
        if (-not $quota) {
            $failures += "No quota entry '$quotaName' in $Location."
            continue
        }
        $available = [double]$quota[0].limit - [double]$quota[0].currentValue
        $message = "$quotaName desired $($request.DesiredCapacity), verified existing credit $($request.ExistingCredit), additional allocation $($request.AdditionalCapacity); $available available."
        if ($request.AdditionalCapacity -gt 0 -and $available -lt $request.AdditionalCapacity) {
            $failures += $message
        } else {
            Add-Finding -Severity PASS -Code 'MODEL_QUOTA_SUFFICIENT' -Message $message
        }
    }

    if ($failures.Count -gt 0) {
        Add-Finding -Severity FAIL -Code 'MODEL_QUOTA_INSUFFICIENT' `
            -Message ("Insufficient AI model quota in '${Location}': " + ($failures -join ' ')) `
            -Hint "Request a quota increase (https://aka.ms/oai/quotaincrease), reduce sku.capacity in modelDeploymentList, or set AZURE_AI_FOUNDRY_LOCATION to a region with available quota."
    }
}

# --------------------------------------------------------------------------
# Regional capacity sub-checks folded in from
# pipelines/tools/azure_region_capacity_checker.ps1. Same Azure APIs, scoped
# to the single region the deployment will use rather than scoring a whole
# region set. All read-only.
# --------------------------------------------------------------------------

function Get-CurrentAzureSubscriptionId {
    $acct = Invoke-AzCliRaw -Arguments @('account', 'show', '-o', 'json')
    if ($acct -and $acct.id) { return [string]$acct.id }
    return $null
}

function Test-RegionalVcpuQuota {
    # Checks vCPU quota for the SKU about to be deployed. Prefers the
    # SKU-family quota counter (e.g. standardDSv5Family) because that's the
    # bucket Azure actually debits, and falls back to 'Total Regional vCPUs'
    # when no family info is supplied. RequiredHeadroom should be the SKU's
    # vCPU count (from VmSkuInfo.VCpus) so the comparison reflects what the
    # deployment will consume.
    param(
        [Parameter(Mandatory)] [string]$Location,
        [Parameter(Mandatory)] [int]$RequiredHeadroom,
        [string]$Family
    )
    if ([string]::IsNullOrWhiteSpace($Location)) { return }
    $usage = Invoke-AzCliRaw -Arguments @('vm', 'list-usage', '--location', $Location, '-o', 'json')
    if (-not $usage) {
        Add-Finding -Severity WARN -Code 'VCPU_QUOTA_LOOKUP' `
            -Message "Could not read regional vCPU quota for '$Location'." `
            -Hint "Run: az vm list-usage --location $Location"
        return
    }

    $target = $null
    $scopeLabel = 'Total Regional vCPUs'
    if (-not [string]::IsNullOrWhiteSpace($Family)) {
        $target = @($usage | Where-Object { $_.name -and $_.name.value -eq $Family } | Select-Object -First 1)
        if ($target) { $scopeLabel = "$Family quota" }
    }
    if (-not $target) {
        $target = @($usage | Where-Object {
            ($_.name -and $_.name.localizedValue -eq 'Total Regional vCPUs') -or ($_.localName -eq 'Total Regional vCPUs')
        } | Select-Object -First 1)
    }
    if (-not $target) {
        Add-Finding -Severity WARN -Code 'VCPU_QUOTA_MISSING' `
            -Message "No matching vCPU quota entry (family='$Family') found for '$Location'."
        return
    }

    $available = [int]$target.limit - [int]$target.currentValue
    if ($available -le 0) {
        Add-Finding -Severity FAIL -Code 'VCPU_QUOTA_EXHAUSTED' `
            -Message "$scopeLabel exhausted in '$Location' (used $($target.currentValue) of $($target.limit))." `
            -Hint "Request a quota increase or pick a different region."
    }
    elseif ($available -lt $RequiredHeadroom) {
        Add-Finding -Severity WARN -Code 'VCPU_QUOTA_LOW' `
            -Message "$scopeLabel headroom in '$Location' is $available (need >= $RequiredHeadroom)." `
            -Hint "Reduce VM/container demand, request a quota increase, or pick another region."
    }
}

function Test-CognitiveServicesQuotaHeadroom {
    param(
        [Parameter(Mandatory)] [string]$SubscriptionId,
        [Parameter(Mandatory)] [string]$Location
    )
    if ([string]::IsNullOrWhiteSpace($Location) -or [string]::IsNullOrWhiteSpace($SubscriptionId)) { return }
    $url = "https://management.azure.com/subscriptions/$SubscriptionId/providers/Microsoft.CognitiveServices/locations/$Location/usages?api-version=2023-05-01"
    $payload = Invoke-AzCliRaw -Arguments @('rest', '--method', 'get', '--url', $url)
    if (-not $payload) {
        Add-Finding -Severity WARN -Code 'CS_QUOTA_LOOKUP' `
            -Message "Could not read Cognitive Services usage for '$Location'." `
            -Hint "Verify Microsoft.CognitiveServices is registered and the current identity has Reader on the subscription."
        return
    }
    $items = @($payload.value)
    if ($items.Count -eq 0) { return }
    $hasHeadroom = $false
    $nearLimit = $false
    foreach ($item in $items) {
        $current = [double]$item.currentValue
        $limit = [double]$item.limit
        if ($limit -gt $current) { $hasHeadroom = $true }
        if ($limit -gt 0 -and (($limit - $current) / $limit) -lt 0.1) { $nearLimit = $true }
    }
    if (-not $hasHeadroom) {
        Add-Finding -Severity FAIL -Code 'CS_QUOTA_AT_LIMIT' `
            -Message "Cognitive Services quota in '$Location' is fully consumed across all reported metrics." `
            -Hint "Request a quota increase (https://aka.ms/oai/quotaincrease) or pick a different region for AI Foundry."
    }
    elseif ($nearLimit) {
        Add-Finding -Severity WARN -Code 'CS_QUOTA_TIGHT' `
            -Message "Cognitive Services quota in '$Location' is within 10% of the limit on at least one metric."
    }
}

function Test-AzureSearchSkuQuota {
    param(
        [Parameter(Mandatory)] [string]$SubscriptionId,
        [Parameter(Mandatory)] [string]$Location,
        [Parameter(Mandatory)] [string]$Sku,
        [ValidateRange(1, 2)] [int]$RequiredHeadroom = 1
    )
    if ([string]::IsNullOrWhiteSpace($Location) -or [string]::IsNullOrWhiteSpace($SubscriptionId)) { return }
    $url = "https://management.azure.com/subscriptions/$SubscriptionId/providers/Microsoft.Search/locations/$Location/usages?api-version=2025-05-01"
    $payload = Invoke-AzCliRaw -Arguments @('rest', '--method', 'get', '--url', $url)
    if (-not $payload) {
        Add-Finding -Severity WARN -Code 'SEARCH_QUOTA_LOOKUP' `
            -Message "Could not read Azure Search usage for '$Location'."
        return
    }
    $skuCanonical = $Sku.ToLowerInvariant()
    $target = @($payload.value | Where-Object { $_.name -and ([string]$_.name.value).ToLowerInvariant() -eq $skuCanonical } | Select-Object -First 1)
    if (-not $target) {
        Add-Finding -Severity WARN -Code 'SEARCH_SKU_UNAVAILABLE' `
            -Message "Azure Search SKU '$Sku' is not listed for '$Location'." `
            -Hint "Pick a supported SKU or region (see https://azure.github.io/AI-Landing-Zones/bicep/regional-considerations/)."
        return
    }
    $available = [int]$target.limit - [int]$target.currentValue
    if ([int]$target.limit -le 0 -or $available -le 0) {
        Add-Finding -Severity FAIL -Code 'SEARCH_QUOTA_AT_LIMIT' `
            -Message "Azure Search SKU '$Sku' quota in '$Location' is exhausted (used $($target.currentValue) of $($target.limit))." `
            -Hint "Request a quota increase or pick another region/SKU."
    }
    elseif ($available -lt $RequiredHeadroom) {
        Add-Finding -Severity FAIL -Code 'SEARCH_QUOTA_INSUFFICIENT' `
            -Message "Azure Search SKU '$Sku' headroom in '$Location' is $available (need >= $RequiredHeadroom)." `
            -Hint "Request a quota increase or pick another region/SKU."
    }
    elseif (([double]$available / [double]$target.limit) -lt 0.1) {
        Add-Finding -Severity WARN -Code 'SEARCH_QUOTA_TIGHT' `
            -Message "Azure Search SKU '$Sku' quota in '$Location' is nearly exhausted ($available of $($target.limit) available)."
    }
}

function Test-CosmosAvailabilityZone {
    param(
        [Parameter(Mandatory)] [string]$Location
    )
    if ([string]::IsNullOrWhiteSpace($Location)) { return }
    $query = '{online:properties.status, az:properties.isSubscriptionRegionAccessAllowedForAz, regular:properties.isSubscriptionRegionAccessAllowedForRegular, supportsAz:properties.supportsAvailabilityZone}'
    $info = Invoke-AzCliRaw -Arguments @('cosmosdb', 'locations', 'show', '--location', $Location, '--query', $query, '-o', 'json')
    if (-not $info) {
        Add-Finding -Severity WARN -Code 'COSMOS_LOC_LOOKUP' `
            -Message "Could not read Cosmos DB region metadata for '$Location'."
        return
    }
    if ($info.online -and $info.online -ne 'Online') {
        Add-Finding -Severity FAIL -Code 'COSMOS_NOT_ONLINE' `
            -Message "Cosmos DB region '$Location' status is '$($info.online)', not 'Online'." `
            -Hint "Pick a different region for cosmosLocation."
        return
    }
    if (-not [bool]$info.az) {
        Add-Finding -Severity WARN -Code 'COSMOS_NO_AZ' `
            -Message "Cosmos DB Availability-Zone support is not enabled for your subscription in '$Location'." `
            -Hint "Pick a region with AZ support if zonal redundancy is required."
    }
}

# --------------------------------------------------------------------------
# Cosmos analytical storage region eligibility
#
# Azure rejects Cosmos DB account creation when `enableAnalyticalStorage=true`
# is requested against a region/subscription combination that has not been
# allow-listed for Synapse Link, with the literal error: "Enabling analytical
# storage on account creation is not supported in this subscription/region.
# Please disable analytical storage on the account creation request and try
# again." The flag cannot be toggled after the account is created, so a
# failed provision requires deleting the account before retrying. Eligibility
# can change without notice, so this is a WARN, not a FAIL. See issue #93.
# --------------------------------------------------------------------------
$script:CosmosAnalyticalRestrictiveRegions = @(
    'swedencentral'
)

function Test-CosmosAnalyticalStorageRegionSupport {
    param([hashtable]$P)

    $enableAnalytical = ConvertTo-Bool $P['enableCosmosAnalyticalStorage']
    if (-not $enableAnalytical) { return }

    $deployCosmos = ConvertTo-Bool $(if ($null -ne $P['deployCosmosDb']) { $P['deployCosmosDb'] } else { $true })
    if (-not $deployCosmos) { return }

    $location = Get-StringValue $P['location']
    $cosmosLocation = Get-StringValue $P['cosmosLocation']
    if ([string]::IsNullOrWhiteSpace($cosmosLocation)) { $cosmosLocation = $location }
    if ([string]::IsNullOrWhiteSpace($cosmosLocation)) { return }

    $normalized = Get-NormalizedLocation $cosmosLocation
    $restrictive = @($script:CosmosAnalyticalRestrictiveRegions | ForEach-Object { Get-NormalizedLocation $_ })
    if ($restrictive -notcontains $normalized) { return }

    Add-Finding -Severity WARN -Code 'COSMOS_ANALYTICAL_REGION' `
        -Message "enableCosmosAnalyticalStorage=true and cosmosLocation='$cosmosLocation' is on the known-restrictive list. Azure has been observed to reject Cosmos DB account creation in this region/subscription combination with: 'Enabling analytical storage on account creation is not supported in this subscription/region. Please disable analytical storage on the account creation request and try again.' This flag cannot be toggled after the account is created, so a failed provision requires deleting the account before retrying." `
        -Hint "If you do not actively consume Synapse Link or Fabric Mirroring, set enableCosmosAnalyticalStorage=false (or unset ENABLE_COSMOS_ANALYTICAL_STORAGE) and re-run preflight. If you have confirmed your subscription is allow-listed for analytical storage in '$cosmosLocation',         you can ignore this WARN. See https://github.com/Azure/bicep-ptn-aiml-landing-zone/issues/93."
        }

function Test-RegionalReadiness {
    param([hashtable]$P)

    if ($SkipAzureLookups) { return }
    if ($SkipRegional -or $env:LZ_PREFLIGHT_REGIONAL_SKIP -eq 'true' -or $env:LZ_PREFLIGHT_REGIONAL_SKIP -eq '1') {
        Add-Finding -Severity INFO -Code 'REGIONAL_SKIPPED' `
            -Message "Regional readiness checks skipped (LZ_PREFLIGHT_REGIONAL_SKIP=true)."
        return
    }
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) { return }

    # Subscription consistency: only when invoked from an azd context where the
    # azd env recorded a subscription. When run standalone (no azd env, or no
    # AZURE_SUBSCRIPTION_ID in it), skip without complaint.
    $envValues = Get-AzdEnvValues
    $azdSubId = if ($envValues.ContainsKey('AZURE_SUBSCRIPTION_ID')) { $envValues['AZURE_SUBSCRIPTION_ID'] } else { '' }
    if (-not [string]::IsNullOrWhiteSpace($azdSubId)) {
        $account = Invoke-AzCliRaw -Arguments @('account', 'show', '-o', 'json')
        if (-not $account) {
            Add-Finding -Severity FAIL -Code 'AZ_LOGIN_REQUIRED' `
                -Message "Azure CLI is not logged in." `
                -Hint "Run 'az login' (and 'az account set --subscription $azdSubId') before deploying."
        }
        elseif ($account.id -ne $azdSubId) {
            Add-Finding -Severity FAIL -Code 'AZ_SUB_DRIFT' `
                -Message "Azure CLI is using subscription '$($account.id)' but the azd environment expects '$azdSubId'." `
                -Hint "Run: az account set --subscription $azdSubId"
        }
    }

    # Resolve locations from the effective parameter set, falling back to the
    # primary `location` when service-specific overrides are empty.
    $location = Get-StringValue $P['location']
    $aiFoundryLocation = Get-StringValue $P['aiFoundryLocation']
    $cosmosLocation = Get-StringValue $P['cosmosLocation']
    $searchLocation = Get-StringValue $P['searchServiceLocation']
    if ([string]::IsNullOrWhiteSpace($aiFoundryLocation)) { $aiFoundryLocation = $location }
    if ([string]::IsNullOrWhiteSpace($cosmosLocation)) { $cosmosLocation = $location }
    if ([string]::IsNullOrWhiteSpace($searchLocation)) { $searchLocation = $location }

    if ([string]::IsNullOrWhiteSpace($location)) {
        Add-Finding -Severity WARN -Code 'REGIONAL_NO_LOCATION' `
            -Message "Regional readiness checks skipped: 'location' is empty." `
            -Hint "Set AZURE_LOCATION in the azd environment (azd env set AZURE_LOCATION <region>)."
        return
    }

    # Feature-flag resolution. Default-on flags follow main.parameters.json:
    # deployAiFoundry/deployCosmosDb/deployContainerApps/deployContainerEnv default true.
    # deploySearchService is gated by an env var; treat empty as true (matches the file default).
    # Note: PowerShell does not accept `if` as an expression inside `(...)` when
    # used as a command/function argument — the parser treats `if` as a command
    # name and fails with "The term 'if' is not recognized...". Wrap with the
    # subexpression operator `$(...)` so the if-expression is evaluated first.
    $deployAiFoundry = ConvertTo-Bool $(if ($null -ne $P['deployAiFoundry']) { $P['deployAiFoundry'] } else { $true })
    $deployCosmos = ConvertTo-Bool $(if ($null -ne $P['deployCosmosDb']) { $P['deployCosmosDb'] } else { $true })
    $deployContainerApps = ConvertTo-Bool $(if ($null -ne $P['deployContainerApps']) { $P['deployContainerApps'] } else { $true })
    $deployContainerEnv = ConvertTo-Bool $(if ($null -ne $P['deployContainerEnv']) { $P['deployContainerEnv'] } else { $true })
    $searchRaw = Get-StringValue $P['deploySearchService']
    $deploySearch = if ([string]::IsNullOrWhiteSpace($searchRaw)) { $true } else { ConvertTo-Bool $searchRaw }
    $deployFoundrySearch = $deployAiFoundry -and
        (Resolve-DeployFlag -P $P -Key 'deployAAfAgentSvc' -Default $true) -and
        [string]::IsNullOrWhiteSpace((Get-StringValue $P['aiSearchResourceId']))
    $searchServiceCount = [int]$deploySearch + [int]$deployFoundrySearch
    $deployKeyVault = ConvertTo-Bool $(if ($null -ne $P['deployKeyVault']) { $P['deployKeyVault'] } else { $true })
    $deployStorage = ConvertTo-Bool $(if ($null -ne $P['deployStorageAccount']) { $P['deployStorageAccount'] } else { $true })
    $deployAppConfig = ConvertTo-Bool $(if ($null -ne $P['deployAppConfig']) { $P['deployAppConfig'] } else { $true })
    $deployLogAnalytics = ConvertTo-Bool $(if ($null -ne $P['deployLogAnalytics']) { $P['deployLogAnalytics'] } else { $true })

    # Provider/location support
    if ($searchServiceCount -gt 0) {
        Test-ProviderLocation -ProviderNamespace 'Microsoft.Search' -ResourceType 'searchServices' `
            -Location $searchLocation -DisplayName 'Azure AI Search' -CodePrefix 'SEARCH'
    }
    if ($deployCosmos) {
        Test-ProviderLocation -ProviderNamespace 'Microsoft.DocumentDB' -ResourceType 'databaseAccounts' `
            -Location $cosmosLocation -DisplayName 'Azure Cosmos DB' -CodePrefix 'COSMOS'
    }
    if ($deployContainerApps -or $deployContainerEnv) {
        Test-ProviderLocation -ProviderNamespace 'Microsoft.App' -ResourceType 'managedEnvironments' `
            -Location $location -DisplayName 'Azure Container Apps Environment' -CodePrefix 'ACA'
    }
    if ($deployAiFoundry) {
        Test-ProviderLocation -ProviderNamespace 'Microsoft.CognitiveServices' -ResourceType 'accounts' `
            -Location $aiFoundryLocation -DisplayName 'Azure AI Foundry / Cognitive Services' -CodePrefix 'AIFOUNDRY'
    }
    if ($deployKeyVault) {
        Test-ProviderLocation -ProviderNamespace 'Microsoft.KeyVault' -ResourceType 'vaults' `
            -Location $location -DisplayName 'Azure Key Vault' -CodePrefix 'KV'
    }
    if ($deployStorage) {
        Test-ProviderLocation -ProviderNamespace 'Microsoft.Storage' -ResourceType 'storageAccounts' `
            -Location $location -DisplayName 'Azure Storage' -CodePrefix 'STORAGE'
    }
    if ($deployAppConfig) {
        Test-ProviderLocation -ProviderNamespace 'Microsoft.AppConfiguration' -ResourceType 'configurationStores' `
            -Location $location -DisplayName 'Azure App Configuration' -CodePrefix 'APPCONFIG'
    }
    if ($deployLogAnalytics) {
        Test-ProviderLocation -ProviderNamespace 'Microsoft.OperationalInsights' -ResourceType 'workspaces' `
            -Location $location -DisplayName 'Log Analytics' -CodePrefix 'LAW'
        Test-ProviderLocation -ProviderNamespace 'Microsoft.Insights' -ResourceType 'components' `
            -Location $location -DisplayName 'Application Insights' -CodePrefix 'APPI'
    }

    # Jumpbox VM SKU. Resolve-DeployJumpbox mirrors main.bicep `_deployJumpbox`
    # so the SKU + quota checks run whenever the deployment will actually create
    # a jumpbox (including the common case where deployJumpbox is unset and
    # networkIsolation=true defaults it to true).
    $deployJump = Resolve-DeployJumpbox $P
    $vmSkuInfo = $null
    if ($deployJump) {
        $vmSize = Get-StringValue $P['vmSize']
        if (-not [string]::IsNullOrWhiteSpace($vmSize)) {
            # Single Azure lookup serves both the SKU-availability check and
            # the family-specific vCPU quota check below.
            $vmSkuInfo = Get-VmSkuInfo -Location $location -VmSize $vmSize
            Test-VmSku -Location $location -VmSize $vmSize -VmSkuInfo $vmSkuInfo
        }
    }

    # Model quota
    if ($deployAiFoundry) {
        $models = $P['modelDeploymentList']
        if ($models) {
            Test-ModelQuota -ModelDeployments $models -Location $aiFoundryLocation
        }
    }

    # Regional capacity sub-checks (folded in from
    # pipelines/tools/azure_region_capacity_checker.ps1).
    if ($deployJump -and $vmSkuInfo) {
        if ($vmSkuInfo.VCpus -gt 0) {
            # Headroom requirement = the SKU's vCPU count, against the SKU's
            # family-specific quota counter (the bucket Azure actually debits).
            Test-RegionalVcpuQuota -Location $location -RequiredHeadroom $vmSkuInfo.VCpus -Family $vmSkuInfo.Family
        }
        else {
            # Get-VmSkuInfo couldn't read the SKU's vCPU capability, so we can't
            # size the headroom requirement. Don't silently skip the quota check:
            # warn that headroom can't be verified, and still run the check with a
            # zero requirement so an already-exhausted family quota (available
            # <= 0) is surfaced rather than masked.
            Add-Finding -Severity WARN -Code 'VCPU_SKU_UNKNOWN' `
                -Message "Could not determine the vCPU count for VM SKU '$($vmSkuInfo.Name)' in '$location'; vCPU headroom cannot be verified." `
                -Hint "Confirm the SKU is offered in the region and re-run, or check family quota manually with: az vm list-usage --location $location"
            Test-RegionalVcpuQuota -Location $location -RequiredHeadroom 0 -Family $vmSkuInfo.Family
        }
    }

    # The Cognitive Services and Azure Search REST usage APIs need an explicit
    # subscription ID. Resolve once and reuse for both calls.
    $resolvedSubId = Get-CurrentAzureSubscriptionId
    if (-not [string]::IsNullOrWhiteSpace($resolvedSubId)) {
        if ($deployAiFoundry) {
            Test-CognitiveServicesQuotaHeadroom -SubscriptionId $resolvedSubId -Location $aiFoundryLocation
        }
        if ($searchServiceCount -gt 0) {
            # main.bicep hardcodes the Search SKU to 'standard'; mirror that here.
            Test-AzureSearchSkuQuota -SubscriptionId $resolvedSubId -Location $searchLocation -Sku 'standard' -RequiredHeadroom $searchServiceCount
        }
    }

    if ($deployCosmos) {
        Test-CosmosAvailabilityZone -Location $cosmosLocation
    }
}

# --------------------------------------------------------------------------

function Write-FindingsReport {
    $byCode = $script:Findings | Group-Object -Property Code | ForEach-Object { $_.Group | Select-Object -First 1 }  # one row per code
    $failCount = @($script:Findings | Where-Object Severity -eq 'FAIL').Count
    $warnCount = @($script:Findings | Where-Object Severity -eq 'WARN').Count
    $infoCount = @($script:Findings | Where-Object Severity -eq 'INFO').Count

    Write-Host ''
    Write-Host '================================================================' -ForegroundColor Cyan
    Write-Host '  AI Landing Zone — Pre-Flight Check' -ForegroundColor Cyan
    Write-Host '================================================================' -ForegroundColor Cyan

    if ($script:Findings.Count -eq 0) {
        Write-Host '  All checks passed.' -ForegroundColor Green
    }
    else {
        foreach ($f in $script:Findings) {
            $color = switch ($f.Severity) { 'FAIL' { 'Red' } 'WARN' { 'Yellow' } 'INFO' { 'Cyan' } default { 'Gray' } }
            Write-Host ("  [{0,-4}] {1,-30} {2}" -f $f.Severity, $f.Code, $f.Message) -ForegroundColor $color
            if ($f.Hint) {
                Write-Host ("         hint: {0}" -f $f.Hint) -ForegroundColor DarkGray
            }
        }
    }
    Write-Host '----------------------------------------------------------------'
    Write-Host ("  Summary: {0} fail, {1} warn, {2} info" -f $failCount, $warnCount, $infoCount)
    Write-Host '================================================================' -ForegroundColor Cyan
    Write-Host ''

    if ($failCount -gt 0) { return 1 }
    if ($Strict -and $warnCount -gt 0) { return 2 }
    return 0
}

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

if (-not $ParametersFile) {
    $ParametersFile = Join-Path -Path (Split-Path -Parent $PSScriptRoot) -ChildPath 'main.parameters.json'
}

Write-Host "[preflight] Parameters file: $ParametersFile"
if ($AzdEnv) { Write-Host "[preflight] azd environment: $AzdEnv" }
if ($SkipAzureLookups) { Write-Host "[preflight] Azure lookups: SKIPPED" -ForegroundColor Yellow }

Test-Tooling

$effective = Get-EffectiveParameters -Path $ParametersFile
if ($effective.Count -eq 0) {
    $code = Write-FindingsReport
    exit $code
}

Test-BooleanParameterValues -P $effective
Test-Topology -P $effective
Test-HostedAgentConfiguration -P $effective
Test-AllowedIpRanges -P $effective
Test-LocalCidrSanity -P $effective
Test-FoundryIqConfiguration -P $effective
Test-AzureResources -P $effective
Test-ResourceProviders -P $effective
Test-CosmosAnalyticalStorageRegionSupport -P $effective
Test-RegionalReadiness -P $effective

$exitCode = Write-FindingsReport
exit $exitCode
