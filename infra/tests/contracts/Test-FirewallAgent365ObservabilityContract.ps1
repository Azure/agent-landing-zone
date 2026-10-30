<#
.SYNOPSIS
    Validates the Foundry Agent Service Agent365 observability firewall rule.

.DESCRIPTION
    Regression test for a defect proved by live Azure validation of a
    network-isolated deployment: Azure Firewall's default-deny blocked the
    Microsoft Foundry Agent Service's `agent365.svc.cloud.microsoft`
    observability/telemetry endpoint. The capability host provisioned
    successfully and the firewall/subnet/DNS topology were otherwise correct,
    but hosted-agent requests failed *after* the runtime had already started
    because the post-startup observability call had no allow rule.

    This test compiles main.bicep and asserts, independent of the hosted-agent
    hash fixture, that:
      - `_firewallEssentialPlatformFqdns` (the FQDN set behind the default
        Application Rule Collection Group's `AllowContainerAppsPlatform` rule,
        source `*`, so it already covers the AI Foundry Agents subnet)
        contains the exact FQDN `agent365.svc.cloud.microsoft`.
      - The `AllowContainerAppsPlatform` rule still targets that variable over
        HTTPS (443) only — no new rule, resource, or feature flag was added.
      - The default rule collection group remains gated only by the existing
        `deployAzureFirewall && networkIsolation` condition.
#>

[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'bicep/main.bicep')
)

$ErrorActionPreference = 'Stop'
$failures = [System.Collections.Generic.List[string]]::new()
$compiledFile = Join-Path ([System.IO.Path]::GetTempPath()) "firewall-agent365-observability-contract-$([guid]::NewGuid()).json"

function Add-Failure {
    param([Parameter(Mandatory)] [string]$Message)
    $failures.Add($Message) | Out-Null
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Add-Pass {
    param([Parameter(Mandatory)] [string]$Message)
    Write-Host "  [PASS] $Message" -ForegroundColor Green
}

try {
    if (Get-Command az -ErrorAction SilentlyContinue) {
        $env:PYTHONIOENCODING = 'utf-8'
        & az bicep build --file $MainFile --outfile $compiledFile
    }
    elseif (Get-Command bicep -ErrorAction SilentlyContinue) {
        & bicep build $MainFile --outfile $compiledFile
    }
    else {
        throw 'Neither bicep nor az is available on PATH.'
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Bicep compilation failed with exit code $LASTEXITCODE."
    }
    $template = Get-Content -LiteralPath $compiledFile -Raw | ConvertFrom-Json -Depth 100

    Write-Host 'Firewall Agent365 observability contract' -ForegroundColor Cyan

    $firewallModule = $template.resources.firewall
    if ($null -eq $firewallModule) {
        Add-Failure "Symbolic resource 'firewall' not found in the compiled template."
    }
    else {
        $nestedVariables = $firewallModule.properties.template.variables
        $nestedResources = $firewallModule.properties.template.resources

        $platformFqdns = @($nestedVariables._firewallEssentialPlatformFqdns)
        if ('agent365.svc.cloud.microsoft' -notin $platformFqdns) {
            Add-Failure "'_firewallEssentialPlatformFqdns' does not contain the required 'agent365.svc.cloud.microsoft' FQDN. Found: $($platformFqdns -join ', ')."
        }
        else {
            Add-Pass "'_firewallEssentialPlatformFqdns' contains the required 'agent365.svc.cloud.microsoft' FQDN."
        }

        $defaultRulesExpr = [string]$nestedVariables._firewallDefaultApplicationRules
        if ($defaultRulesExpr -notmatch "'name', 'AllowContainerAppsPlatform'[^)]*'protocols', createArray\(createObject\('protocolType', 'Https', 'port', 443\)\)[^)]*'targetFqdns', variables\('_firewallEssentialPlatformFqdns'\)") {
            Add-Failure "'AllowContainerAppsPlatform' no longer targets '_firewallEssentialPlatformFqdns' over HTTPS (443) only."
        }
        else {
            Add-Pass "'AllowContainerAppsPlatform' targets '_firewallEssentialPlatformFqdns' over HTTPS (443) only — no new rule was introduced."
        }

        $ruleCollectionGroup = $nestedResources.firewallPolicyDefaultRuleCollectionGroup
        if ($null -eq $ruleCollectionGroup) {
            Add-Failure "Resource 'firewallPolicyDefaultRuleCollectionGroup' is missing from the firewall module."
        }
        else {
            $condition = [string]$ruleCollectionGroup.condition
            $requiredConditionTokens = @(
                "parameters('deployAzureFirewall')",
                "parameters('networkIsolation')"
            )
            $missingConditionTokens = @($requiredConditionTokens | Where-Object { -not $condition.Contains($_) })
            if ($missingConditionTokens.Count -gt 0) {
                Add-Failure "Default rule collection group condition is missing required gating on: $($missingConditionTokens -join ', ')."
            }
            else {
                Add-Pass 'Default rule collection group remains gated on deployAzureFirewall and networkIsolation; no new flag was introduced.'
            }
        }
    }

    $firewallSourceFile = Join-Path (Split-Path -Parent $MainFile) 'modules\networking\azure-firewall.bicep'
    $firewallSource = Get-Content -LiteralPath $firewallSourceFile -Raw
    if (-not $firewallSource.Contains("'agent365.svc.cloud.microsoft'")) {
        Add-Failure "modules/networking/azure-firewall.bicep no longer declares the literal 'agent365.svc.cloud.microsoft' FQDN."
    }
    else {
        Add-Pass "modules/networking/azure-firewall.bicep declares the literal 'agent365.svc.cloud.microsoft' FQDN (no typo/rename)."
    }
}
finally {
    Remove-Item -LiteralPath $compiledFile -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    Write-Host "`n$($failures.Count) firewall Agent365 observability contract check(s) failed." -ForegroundColor Red
    exit 1
}

Write-Host "`nFirewall Agent365 observability contract checks passed." -ForegroundColor Green
exit 0
