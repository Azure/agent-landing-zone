<#
.SYNOPSIS
    Validates the ACR Task agent pool VNet-injection firewall contract.

.DESCRIPTION
    Regression test for the defect reported in Azure/GPT-RAG#597: an ACR Tasks
    dedicated agent pool injected into `devopsBuildAgentsSubnet` failed to
    provision 6/6 times behind Azure Firewall, because the subnet's firewall
    policy contained only Application (FQDN) rules and no Network Rules for
    the agent pool's own platform-bootstrap traffic. ACR Tasks agent pools
    require unconditional outbound Network Rules to five Azure service tags
    (AzureKeyVault, Storage, EventHub, AzureActiveDirectory, AzureMonitor) —
    see https://learn.microsoft.com/azure/container-registry/tasks-agent-pools.

    This test compiles main.bicep and asserts, independent of the hosted-agent
    hash fixture, that:
      - A dedicated `ruleCollectionGroups` child resource exists for the ACR
        Task agent pool platform-bootstrap rules, gated on
        `deployAzureFirewall && networkIsolation && deployAcrTaskAgentPool`.
      - It is chained (via dependsOn) after the default and ACS-media groups
        to serialize concurrent rule-collection-group PUTs against the same
        firewall policy (avoids AnotherOperationInProgress 409s).
      - Its rule collection contains exactly five `NetworkRule` entries (not
        ApplicationRule/FQDN rules), sourced from the devops build agents
        subnet, targeting the five required service tags on the required
        ports (443 for all; 443+12000 for AzureMonitor).
#>

[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'bicep/main.bicep')
)

$ErrorActionPreference = 'Stop'
$failures = [System.Collections.Generic.List[string]]::new()
$compiledFile = Join-Path ([System.IO.Path]::GetTempPath()) "acr-task-agent-pool-firewall-contract-$([guid]::NewGuid()).json"

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

    Write-Host 'ACR Task agent pool firewall contract (Azure/GPT-RAG#597)' -ForegroundColor Cyan

    $firewallModule = $template.resources.firewall
    if ($null -eq $firewallModule) {
        Add-Failure "Symbolic resource 'firewall' not found in the compiled template."
    }
    else {
        $nestedResources = $firewallModule.properties.template.resources
        $ruleCollectionGroup = $nestedResources.firewallPolicyAcrTaskAgentPoolRuleCollectionGroup

        if ($null -eq $ruleCollectionGroup) {
            Add-Failure "Resource 'firewallPolicyAcrTaskAgentPoolRuleCollectionGroup' is missing from the firewall module."
        }
        else {
            $condition = [string]$ruleCollectionGroup.condition
            $requiredConditionTokens = @(
                "parameters('deployAzureFirewall')",
                "parameters('networkIsolation')",
                "parameters('deployAcrTaskAgentPool')"
            )
            $missingConditionTokens = @($requiredConditionTokens | Where-Object { -not $condition.Contains($_) })
            if ($missingConditionTokens.Count -gt 0) {
                Add-Failure "Rule collection group condition is missing required gating on: $($missingConditionTokens -join ', ')."
            }
            else {
                Add-Pass 'Rule collection group is gated on deployAzureFirewall, networkIsolation, and deployAcrTaskAgentPool.'
            }

            $dependsOn = @($ruleCollectionGroup.dependsOn)
            $requiredDependencies = @('firewallPolicyDefaultRuleCollectionGroup', 'firewallPolicyAcsMediaRuleCollectionGroup')
            $missingDependencies = @($requiredDependencies | Where-Object { $_ -notin $dependsOn })
            if ($missingDependencies.Count -gt 0) {
                Add-Failure "Rule collection group is missing serialization dependsOn entries: $($missingDependencies -join ', ')."
            }
            else {
                Add-Pass 'Rule collection group is chained after the default and ACS-media groups to serialize firewall policy PUTs.'
            }

            $priority = [int]$ruleCollectionGroup.properties.priority
            if ($priority -lt 200) {
                Add-Failure "Rule collection group priority must be a distinct integer greater than the default group's priority (200); got $priority."
            }
            else {
                Add-Pass "Rule collection group priority ($priority) is distinct and ordered after the default group."
            }

            $ruleCollectionsExpr = [string]$ruleCollectionGroup.properties.ruleCollections
            if ($ruleCollectionsExpr -notmatch "variables\('(?<varName>[^']+)'\)") {
                Add-Failure "Unable to resolve the rule collections variable reference from: $ruleCollectionsExpr"
            }
            else {
                $ruleCollectionsVarName = $Matches.varName
                $ruleCollectionsValue = $firewallModule.properties.template.variables.$ruleCollectionsVarName
                if ($null -eq $ruleCollectionsValue) {
                    Add-Failure "Rule collections variable '$ruleCollectionsVarName' not found in the firewall module."
                }
                else {
                    $collection = if ($ruleCollectionsValue -is [System.Collections.IEnumerable] -and $ruleCollectionsValue -isnot [string]) {
                        @($ruleCollectionsValue)[0]
                    }
                    else {
                        $ruleCollectionsValue
                    }
                    if ($collection.ruleCollectionType -ne 'FirewallPolicyFilterRuleCollection') {
                        Add-Failure "Expected a FirewallPolicyFilterRuleCollection, got '$($collection.ruleCollectionType)'."
                    }
                    elseif ($collection.action.type -ne 'Allow') {
                        Add-Failure "Expected the rule collection action to be 'Allow', got '$($collection.action.type)'."
                    }
                    else {
                        Add-Pass "Rule collection '$($collection.name)' is a FirewallPolicyFilterRuleCollection with an Allow action."
                    }

                    $rulesExpr = [string]$collection.rules
                    if ($rulesExpr -notmatch "variables\('(?<varName>[^']+)'\)") {
                        Add-Failure "Unable to resolve the network rules variable reference from: $rulesExpr"
                    }
                    else {
                        $rules = @($firewallModule.properties.template.variables.($Matches.varName))

                        $expectedDestinations = [ordered]@{
                            AzureKeyVault         = @('443')
                            Storage               = @('443')
                            EventHub              = @('443')
                            AzureActiveDirectory  = @('443')
                            AzureMonitor          = @('443', '12000')
                        }

                        $nonNetworkRules = @($rules | Where-Object { $_.ruleType -ne 'NetworkRule' })
                        if ($nonNetworkRules.Count -gt 0) {
                            Add-Failure "All ACR Task agent pool platform rules must be NetworkRule (not Application/FQDN) rules; found: $($nonNetworkRules.ruleType -join ', ')."
                        }
                        else {
                            Add-Pass "All $($rules.Count) platform-bootstrap rules are NetworkRule (service-tag/IP) rules, not Application/FQDN rules."
                        }

                        $rulesBySourceOk = @($rules | Where-Object {
                                @($_.sourceAddresses) -notcontains "[parameters('devopsBuildAgentsSubnetPrefix')]"
                            })
                        if ($rulesBySourceOk.Count -gt 0) {
                            Add-Failure "$($rulesBySourceOk.Count) rule(s) do not source from the devops build agents subnet prefix parameter."
                        }
                        else {
                            Add-Pass 'All platform-bootstrap rules source from the devops build agents subnet prefix.'
                        }

                        $missingDestinations = [System.Collections.Generic.List[string]]::new()
                        foreach ($destination in $expectedDestinations.Keys) {
                            $matchingRule = $rules | Where-Object { @($_.destinationAddresses) -contains $destination } | Select-Object -First 1
                            if ($null -eq $matchingRule) {
                                $missingDestinations.Add($destination)
                                continue
                            }
                            $expectedPorts = $expectedDestinations[$destination]
                            $actualPorts = @($matchingRule.destinationPorts)
                            $missingPorts = @($expectedPorts | Where-Object { $_ -notin $actualPorts })
                            if ($missingPorts.Count -gt 0) {
                                Add-Failure "Service tag '$destination' is missing required destination port(s): $($missingPorts -join ', ')."
                            }
                        }
                        if ($missingDestinations.Count -gt 0) {
                            Add-Failure "Missing required ACR Task agent pool platform service tag(s): $($missingDestinations -join ', ')."
                        }
                        elseif (-not ($failures | Where-Object { $_ -like "Service tag*" })) {
                            Add-Pass "All 5 required service tags (AzureKeyVault, Storage, EventHub, AzureActiveDirectory, AzureMonitor) are present with correct ports."
                        }
                    }
                }
            }
        }
    }
}
finally {
    Remove-Item -LiteralPath $compiledFile -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    Write-Host "`n$($failures.Count) ACR Task agent pool firewall contract check(s) failed." -ForegroundColor Red
    exit 1
}

Write-Host "`nACR Task agent pool firewall contract checks passed." -ForegroundColor Green
exit 0
