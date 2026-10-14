function Get-ExistingModelDeployments {
    param(
        [Parameter(Mandatory = $true)][string]$Location,
        [AllowEmptyString()][string]$SubscriptionId,
        [AllowEmptyString()][string]$ProjectResourceId = $env:AZURE_AI_PROJECT_RESOURCE_ID,
        [AllowEmptyString()][string]$ResourceGroup = $env:AZURE_RESOURCE_GROUP,
        [Parameter(Mandatory = $true)][scriptblock]$ReadAzureJson,
        [Parameter(Mandatory = $true)][scriptblock]$OnWarning
    )

    $projectId = $ProjectResourceId
    if ([string]::IsNullOrWhiteSpace($projectId)) {
        if ([string]::IsNullOrWhiteSpace($ResourceGroup) -or [string]::IsNullOrWhiteSpace($SubscriptionId)) {
            return @()
        }
        # Older classic/custom foundations emitted no project output.
        $projects = & $ReadAzureJson @(
            'resource', 'list', '--resource-group', $ResourceGroup,
            '--resource-type', 'Microsoft.CognitiveServices/accounts/projects',
            '--subscription', $SubscriptionId, '--query', '[].{id:id}'
        )
        if ($null -eq $projects -or ($projects -is [hashtable] -and $projects.failed)) {
            & $OnWarning 'Could not discover an existing project; full requested allocation will be checked.' | Out-Null
            return @()
        }
        $candidates = @($projects)
        if ($candidates.Count -eq 0) { return @() }
        if ($candidates.Count -ne 1) {
            & $OnWarning 'Existing project discovery is ambiguous; no allocation credit applied. Set the selected project resource ID.' | Out-Null
            return @()
        }
        $projectId = [string]$candidates[0].id
    }
    $target = [regex]::Match($projectId, '^/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft\.CognitiveServices/accounts/([^/]+)/projects/[^/]+/?$', 'IgnoreCase')
    if (-not $target.Success -or $target.Groups[1].Value -ne $SubscriptionId -or
        [string]::IsNullOrWhiteSpace($resourceGroup) -or $target.Groups[2].Value -ne $resourceGroup) {
        & $OnWarning 'Existing project output does not match the selected subscription/resource group; no allocation credit applied.' | Out-Null
        return @()
    }

    $accountName = $target.Groups[3].Value
    $expectedId = $projectId -replace '/projects/[^/]+/?$', ''
    $account = & $ReadAzureJson @('resource', 'show', '--ids', $expectedId, '--subscription', $SubscriptionId, '--query', '{id:id,location:location}')
    if ($null -eq $account -or ($account -is [hashtable] -and $account.failed)) {
        & $OnWarning 'Could not verify the existing account; full requested allocation will be checked.' | Out-Null
        return @()
    }
    $actualLocation = ([string]$account.location -replace '\s+', '').ToLowerInvariant()
    $desiredLocation = ($Location -replace '\s+', '').ToLowerInvariant()
    if ($account.id -ne $expectedId -or $actualLocation -ne $desiredLocation) {
        & $OnWarning 'Account identity/location does not match the target; no allocation credit applied.' | Out-Null
        return @()
    }
    $deployments = & $ReadAzureJson @('cognitiveservices', 'account', 'deployment', 'list', '--name', $accountName, '--resource-group', $resourceGroup, '--subscription', $SubscriptionId)
    if ($deployments -is [hashtable] -and $deployments.failed) {
        & $OnWarning 'Could not verify existing deployments; full requested allocation will be checked.' | Out-Null
        return @()
    }
    return @($deployments)
}

function Get-ModelQuotaRequirements {
    param(
        [Parameter(Mandatory = $true)]$Models,
        [AllowEmptyCollection()][object[]]$ExistingDeployments = @()
    )

    $requests = @{}
    $seenNames = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($deployment in @($Models)) {
        $model = $deployment.model
        $capacity = [double]$deployment.sku.capacity
        if ($capacity -le 0 -or [double]::IsNaN($capacity) -or [double]::IsInfinity($capacity)) {
            throw 'Deployment capacity must be positive and finite.'
        }
        $nameProperty = $deployment.PSObject.Properties['name']
        $deploymentName = if ($null -ne $nameProperty) { [string]$nameProperty.Value } else { '' }
        if (-not [string]::IsNullOrWhiteSpace($deploymentName) -and -not $seenNames.Add($deploymentName)) {
            throw "Duplicate deployment name '$deploymentName'; allocation credit cannot be reused."
        }
        $quotaName = "OpenAI.$($deployment.sku.name).$($model.name)"
        $credit = 0.0
        if (-not [string]::IsNullOrWhiteSpace($deploymentName)) {
            $matching = @($ExistingDeployments | Where-Object { $null -ne $_ -and $_.name -eq $deploymentName })
            if ($matching.Count -eq 1) {
                $current = $matching[0]
                $desiredFormat = $model.PSObject.Properties['format']
                $currentModel = $current.properties.model
                $currentFormat = $currentModel.PSObject.Properties['format']
                if ($null -ne $desiredFormat -and $null -ne $currentFormat -and
                    $desiredFormat.Value -eq $currentFormat.Value -and
                    $currentModel.name -eq $model.name -and $currentModel.version -eq $model.version -and
                    $current.sku.name -eq $deployment.sku.name -and
                    $current.properties.provisioningState -eq 'Succeeded') {
                    $currentCapacity = [double]$current.sku.capacity
                    if ($currentCapacity -gt 0 -and -not [double]::IsNaN($currentCapacity) -and -not [double]::IsInfinity($currentCapacity)) {
                        $credit = [Math]::Min($capacity, $currentCapacity)
                    }
                }
            }
        }
        if (-not $requests.ContainsKey($quotaName)) {
            $requests[$quotaName] = @{ desired = 0.0; credit = 0.0 }
        }
        $requests[$quotaName].desired += $capacity
        $requests[$quotaName].credit += $credit
    }
    foreach ($quotaName in $requests.Keys) {
        [pscustomobject]@{
            QuotaName = $quotaName
            DesiredCapacity = $requests[$quotaName].desired
            ExistingCredit = $requests[$quotaName].credit
            AdditionalCapacity = $requests[$quotaName].desired - $requests[$quotaName].credit
        }
    }
}
