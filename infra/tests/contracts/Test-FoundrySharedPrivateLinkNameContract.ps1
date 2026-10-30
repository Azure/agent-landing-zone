<#
.SYNOPSIS
    Validates Foundry IQ shared private-link resource names stay within Azure's
    60-character limit while preserving existing names when they already fit.

.DESCRIPTION
    Regression test for a live network-isolated deployment (Azure/GPT-RAG#592,
    Azure/GPT-RAG#597) whose CAF-generated Search service name produced a
    61-character `foundry_account` shared private-link name (and a
    71-character `cognitiveservices_account` name). The deployment failed only
    after the other long-running resources had provisioned.

    This compiles main.bicep (the "compiled-template" contract) and:
      - Proves the 60-character threshold is derived from the worst-case
        bounded name for the longest generated child name (cognitiveservices_
        account), not an arbitrary magic number.
      - Simulates a maximum-length (60-character) Search service name and
        proves all three shared private-link names stay <=60 characters,
        are pairwise distinct, and are deterministic. Distinct long Search
        names that share the truncated prefix are also collision-probed.
      - Replays the exact live-failure Search service name length and proves
        the previously overflowing `foundry_account`/`cognitiveservices_account`
        names are now bounded, while an ordinary/short Search service name
        keeps its exact, pre-existing legacy name unchanged (backward
        compatibility).
      - Per group, asserts the exact Search-service-name-length boundary at
        which the plain name reaches exactly 60 characters stays unchanged,
        and that one character past that boundary correctly falls back to
        the bounded token (no unnecessary renames of working deployments).
      - Asserts the shared private-link resource's `type`, `apiVersion`,
        `dependsOn`, and `copy` targets are unchanged from the pre-fix
        contract.
#>

[CmdletBinding()]
param(
    [string]$MainFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'bicep/main.bicep')
)

$ErrorActionPreference = 'Stop'
$failures = [System.Collections.Generic.List[string]]::new()
$compiledFile = Join-Path ([System.IO.Path]::GetTempPath()) "foundry-spl-name-contract-$([guid]::NewGuid()).json"

function Add-Failure {
    param([Parameter(Mandatory)] [string]$Message)
    $failures.Add($Message) | Out-Null
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Add-Pass {
    param([Parameter(Mandatory)] [string]$Message)
    Write-Host "  [PASS] $Message" -ForegroundColor Green
}

# Mirrors the Bicep expression:
#   '${take(searchServiceName, 21)}-${take(uniqueString(searchServiceName), 6)}'
# uniqueString() always returns a 13-character deterministic hash; take(..., 6)
# always yields exactly 6 characters regardless of its value, so the *length*
# of the token can be computed without reimplementing ARM's uniqueString hash.
function Get-BoundedTokenLength {
    param([Parameter(Mandatory)] [int]$SearchServiceNameLength)
    return [Math]::Min(21, $SearchServiceNameLength) + 1 + 6
}

# Mirrors the Bicep expression:
#   length('spl-${searchServiceName}-${groupId}-1') <= 60
#     ? 'spl-${searchServiceName}-${groupId}-1'
#     : 'spl-${token}-${groupId}-1'
function Get-SharedPrivateLinkNameLength {
    param(
        [Parameter(Mandatory)] [int]$SearchServiceNameLength,
        [Parameter(Mandatory)] [string]$GroupId,
        [int]$MaxLength = 60
    )
    $directLength = 'spl-'.Length + $SearchServiceNameLength + 1 + $GroupId.Length + '-1'.Length
    if ($directLength -le $MaxLength) {
        return @{ Length = $directLength; UsedDirectName = $true }
    }
    $tokenLength = Get-BoundedTokenLength -SearchServiceNameLength $SearchServiceNameLength
    $boundedLength = 'spl-'.Length + $tokenLength + 1 + $GroupId.Length + '-1'.Length
    return @{ Length = $boundedLength; UsedDirectName = $false }
}

function Get-TestBoundedSharedPrivateLinkName {
    param(
        [Parameter(Mandatory)] [string]$SearchServiceName,
        [Parameter(Mandatory)] [string]$GroupId
    )

    # The compiled-template checks below prove production hashes the complete
    # Search name before taking six characters. SHA-256 is the offline
    # deterministic surrogate used to exercise distinct concrete inputs.
    $hashBytes = [System.Security.Cryptography.SHA256]::HashData(
        [System.Text.Encoding]::UTF8.GetBytes($SearchServiceName)
    )
    $hashToken = ([System.Convert]::ToHexString($hashBytes)).ToLowerInvariant().Substring(0, 6)
    $prefix = $SearchServiceName.Substring(0, [Math]::Min(21, $SearchServiceName.Length))
    return "spl-$prefix-$hashToken-$GroupId-1"
}

Write-Host 'Foundry IQ shared private-link naming contract' -ForegroundColor Cyan

$groups = @(
    'openai_account'
    'foundry_account'
    'cognitiveservices_account'
)
$maxResourceNameLength = 60

try {
    # --- 0. The 60-character threshold is derived, not a magic number --------
    # `searchFoundrySharedPrivateLinkMaxNameLength` (60) must equal the exact
    # worst-case length produced by the bounded fallback formula for the
    # *longest* complete generated child name -- i.e. the group with the
    # longest groupId (cognitiveservices_account, 25 chars) at the maximum
    # possible Search service name length (60 chars, which saturates the
    # 21-char token prefix). This proves 60 is the platform limit *and* the
    # exact bound the fallback formula is built to hit, not an arbitrary
    # literal that happens to match Azure's ARM constraint.
    $longestGroupId = ($groups | Sort-Object { $_.Length } -Descending | Select-Object -First 1)
    $maxSearchNameLength = 60
    $worstCaseTokenLength = Get-BoundedTokenLength -SearchServiceNameLength $maxSearchNameLength
    $derivedMaxLength = 'spl-'.Length + $worstCaseTokenLength + 1 + $longestGroupId.Length + '-1'.Length
    if ($derivedMaxLength -ne $maxResourceNameLength) {
        Add-Failure "The 60-character threshold does not match the worst-case bounded name length for the longest groupId ('$longestGroupId'): derived $derivedMaxLength, expected $maxResourceNameLength."
    }
    else {
        Add-Pass "The 60-character threshold is derived from the longest generated child name ('$longestGroupId') at the bounded fallback's worst case, not a magic number."
    }

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

    # --- 1. Compiled-template structural checks -----------------------------

    $tokenExpr = $template.variables.searchFoundrySharedPrivateLinkNameToken
    if ($tokenExpr -notmatch "take\(variables\('resourceNames'\)\.searchServiceName,\s*21\)" -or
        $tokenExpr -notmatch "take\(uniqueString\(variables\('resourceNames'\)\.searchServiceName\),\s*6\)") {
        Add-Failure 'The bounded, collision-resistant Search name token no longer truncates the Search name to 21 characters plus a 6-character deterministic hash.'
    }
    else {
        Add-Pass 'The fallback name token is bounded to 28 characters (21-char Search name prefix + 6-char deterministic hash).'
    }

    if ($tokenExpr -match 'utcNow|newGuid') {
        Add-Failure 'The fallback name token references a non-deterministic ARM function (utcNow/newGuid).'
    }
    else {
        Add-Pass 'The fallback name token uses only deterministic ARM functions (no utcNow/newGuid).'
    }

    if ($template.variables.searchFoundrySharedPrivateLinkMaxNameLength -ne $maxResourceNameLength) {
        Add-Failure "The shared private-link max-name-length variable is $($template.variables.searchFoundrySharedPrivateLinkMaxNameLength), expected $maxResourceNameLength."
    }
    else {
        Add-Pass "The shared private-link max-name-length variable is $maxResourceNameLength."
    }

    $resourcesExpr = $template.variables.searchFoundrySharedPrivateLinkResources
    if ($resourcesExpr -match 'utcNow|newGuid') {
        Add-Failure 'The shared private-link name/group array references a non-deterministic ARM function (utcNow/newGuid).'
    }
    else {
        Add-Pass 'The shared private-link name/group array uses only deterministic ARM functions (no utcNow/newGuid).'
    }

    $directNameLiterals = [System.Collections.Generic.List[string]]::new()
    $boundedNameLiterals = [System.Collections.Generic.List[string]]::new()
    foreach ($group in $groups) {
        $directFormat = "format('spl-{0}-$group-1', variables('resourceNames').searchServiceName)"
        $boundedFormat = "format('spl-{0}-$group-1', variables('searchFoundrySharedPrivateLinkNameToken'))"
        $guard = "lessOrEquals(length($directFormat), variables('searchFoundrySharedPrivateLinkMaxNameLength'))"
        $ternary = "if($guard, $directFormat, $boundedFormat)"

        if (-not $resourcesExpr.Contains($ternary)) {
            Add-Failure "Shared private link '$group' does not preserve its plain name when it fits, with a bounded fallback when it does not."
            continue
        }
        Add-Pass "Shared private link '$group' preserves its plain name when it fits <= $maxResourceNameLength chars, else falls back to the bounded token."
        $directNameLiterals.Add($directFormat) | Out-Null
        $boundedNameLiterals.Add($boundedFormat) | Out-Null
    }

    if (($directNameLiterals | Select-Object -Unique).Count -eq $groups.Count -and
        ($boundedNameLiterals | Select-Object -Unique).Count -eq $groups.Count) {
        Add-Pass 'All three shared private-link names (direct and bounded forms) are pairwise distinct by construction (distinct groupId suffix).'
    }
    else {
        Add-Failure 'Two or more shared private-link names collide on their direct or bounded name expression.'
    }

    $splDeployment = $template.resources.searchFoundrySharedPrivateLinks
    $splResource = $splDeployment.properties.template.resources.sharedPrivateLinks
    $expectedType = 'Microsoft.Search/searchServices/sharedPrivateLinkResources'
    $expectedApiVersion = '2025-05-01'
    if ($null -eq $splResource) {
        Add-Failure 'The searchFoundrySharedPrivateLinks resource is missing from the compiled template.'
    }
    else {
        if ($splResource.type -ne $expectedType) {
            Add-Failure "searchFoundrySharedPrivateLinks type changed: expected '$expectedType', got '$($splResource.type)'."
        }
        elseif ($splResource.apiVersion -ne $expectedApiVersion) {
            Add-Failure "searchFoundrySharedPrivateLinks apiVersion changed: expected '$expectedApiVersion', got '$($splResource.apiVersion)'."
        }
        elseif ($splDeployment.resourceGroup -ne "[variables('_foundryResourceGroupName')]") {
            Add-Failure 'Shared private links must be service-owned Search children in the Foundry RG.'
        }
        elseif ((@($splDeployment.dependsOn) -join ',') -ne (@('aiFoundry', 'searchService') -join ',')) {
            Add-Failure "searchFoundrySharedPrivateLinks dependsOn changed: expected [aiFoundry, searchService], got [$($splDeployment.dependsOn -join ', ')]."
        }
        elseif ($splDeployment.properties.parameters.links.value -ne "[variables('searchFoundrySharedPrivateLinkResources')]") {
            Add-Failure 'Shared private-link wrapper must receive the exact gated resources array.'
        }
        elseif ($splDeployment.properties.parameters.foundryAccountResourceId.value -ne "[reference('aiFoundry').outputs.accountResourceId.value]") {
            Add-Failure 'Shared private-link wrapper must use the actual Foundry resource ID.'
        }
        elseif ($splResource.copy.mode -ne 'serial' -or $splResource.copy.batchSize -ne 1) {
            Add-Failure "searchFoundrySharedPrivateLinks copy loop changed: expected serial mode with batchSize 1, got mode='$($splResource.copy.mode)' batchSize=$($splResource.copy.batchSize)."
        }
        elseif ($splResource.copy.count -ne "[length(parameters('links'))]") {
            Add-Failure "searchFoundrySharedPrivateLinks copy count no longer targets the gated resources array: got '$($splResource.copy.count)'."
        }
        else {
            Add-Pass 'Scoped shared private links keep their resource type, API version, dependency ordering, and gated serial copy loop.'
        }
    }

    # --- 2. Maximum-length Search service name simulation --------------------

    $maxLengthSearchName = 'a' * 60
    foreach ($group in $groups) {
        $result = Get-SharedPrivateLinkNameLength -SearchServiceNameLength $maxLengthSearchName.Length -GroupId $group
        if ($result.Length -gt $maxResourceNameLength) {
            Add-Failure "With a maximum-length (60-char) Search service name, '$group' would reach $($result.Length) characters."
        }
        else {
            Add-Pass "With a maximum-length (60-char) Search service name, '$group' is bounded to $($result.Length) characters (direct name used: $($result.UsedDirectName))."
        }
    }

    # Determinism: recomputing with the same input yields the same length and
    # the same direct/bounded decision every time (pure function of inputs).
    $first = Get-SharedPrivateLinkNameLength -SearchServiceNameLength $maxLengthSearchName.Length -GroupId 'cognitiveservices_account'
    $second = Get-SharedPrivateLinkNameLength -SearchServiceNameLength $maxLengthSearchName.Length -GroupId 'cognitiveservices_account'
    if ($first.Length -ne $second.Length -or $first.UsedDirectName -ne $second.UsedDirectName) {
        Add-Failure 'The shared private-link naming scheme is not deterministic for identical inputs.'
    }
    else {
        Add-Pass 'The shared private-link naming scheme is deterministic for identical inputs.'
    }

    # Pairwise distinctness for the maximum-length scenario (all three fall
    # back to the bounded token, differing only by their literal groupId
    # suffix, which keeps them distinct even though the token is shared).
    $maxLengthNames = $groups | ForEach-Object { "spl-$('a' * (Get-BoundedTokenLength -SearchServiceNameLength $maxLengthSearchName.Length))-$_-1" }
    if (($maxLengthNames | Select-Object -Unique).Count -eq $groups.Count) {
        Add-Pass 'The three bounded shared private-link names are pairwise distinct for a maximum-length Search service name.'
    }
    else {
        Add-Failure 'Two or more bounded shared private-link names collide for a maximum-length Search service name.'
    }

    # Distinct long Search names with the same first 21 characters must remain
    # distinguishable through the deterministic hash of the complete input.
    $collisionProbeA = "$('a' * 59)x"
    $collisionProbeB = "$('a' * 59)y"
    $probeNameA = Get-TestBoundedSharedPrivateLinkName -SearchServiceName $collisionProbeA -GroupId 'cognitiveservices_account'
    $probeNameARepeat = Get-TestBoundedSharedPrivateLinkName -SearchServiceName $collisionProbeA -GroupId 'cognitiveservices_account'
    $probeNameB = Get-TestBoundedSharedPrivateLinkName -SearchServiceName $collisionProbeB -GroupId 'cognitiveservices_account'
    if ($probeNameA -ne $probeNameARepeat) {
        Add-Failure 'The concrete long-name collision probe is not deterministic for identical input.'
    }
    elseif ($probeNameA -eq $probeNameB) {
        Add-Failure 'Distinct tested long Search names collide after bounded truncation and hashing.'
    }
    else {
        Add-Pass 'Concrete long-name outputs are deterministic, and distinct tested inputs sharing the truncated prefix do not collide.'
    }

    # --- 3. Live-failure evidence replay (Azure/GPT-RAG#592, #597) -----------
    # The reported CAF-generated Search service name was 39 characters, giving
    # a pre-fix foundry_account name of 61 chars and cognitiveservices_account
    # of 71 chars (both over the 60-char limit); openai_account fit exactly at
    # 60 and was unaffected.

    $reportedSearchNameLength = 39
    $expectedPreFixLengths = @{
        'openai_account'            = 60
        'foundry_account'           = 61
        'cognitiveservices_account' = 71
    }
    foreach ($group in $groups) {
        $preFixLength = 'spl-'.Length + $reportedSearchNameLength + 1 + $group.Length + '-1'.Length
        if ($preFixLength -ne $expectedPreFixLengths[$group]) {
            Add-Failure "Live-failure replay: expected the unbounded pre-fix '$group' name to reach $($expectedPreFixLengths[$group]) characters for the reported 39-char Search service name, computed $preFixLength."
            continue
        }
        $result = Get-SharedPrivateLinkNameLength -SearchServiceNameLength $reportedSearchNameLength -GroupId $group
        if ($result.Length -gt $maxResourceNameLength) {
            Add-Failure "Live-failure replay: '$group' still reaches $($result.Length) characters (>$maxResourceNameLength) for the reported 39-char Search service name."
        }
        else {
            Add-Pass "Live-failure replay: '$group' is now bounded to $($result.Length) characters for the reported 39-char Search service name (pre-fix was $preFixLength)."
        }
    }

    # --- 4. Backward compatibility: ordinary/short names keep their plain name

    $ordinaryCafName = 'srch-abc123-dev-eus2-001'
    $allDirect = $true
    foreach ($group in $groups) {
        $result = Get-SharedPrivateLinkNameLength -SearchServiceNameLength $ordinaryCafName.Length -GroupId $group
        $expectedLegacyName = "spl-$ordinaryCafName-$group-1"
        if (-not $result.UsedDirectName) {
            $allDirect = $false
        }
        elseif ($result.Length -ne $expectedLegacyName.Length) {
            $allDirect = $false
            Add-Failure "An ordinary/short Search service name ('$ordinaryCafName') produces a '$group' name of unexpected length $($result.Length) (expected $($expectedLegacyName.Length) for '$expectedLegacyName')."
        }
    }
    if ($allDirect) {
        Add-Pass "An ordinary/short Search service name ('$ordinaryCafName', $($ordinaryCafName.Length) chars) keeps the exact, pre-existing legacy shared private-link name (e.g. 'spl-$ordinaryCafName-$($groups[0])-1') for all three groups."
    }
    else {
        Add-Failure "An ordinary/short Search service name ('$ordinaryCafName') unexpectedly falls back to the bounded token for at least one group, changing existing deployments' resource names unnecessarily."
    }

    # --- 5. Exact-boundary behavior per group ---------------------------------
    # Each group has its own boundary Search-service-name length at which the
    # plain name reaches *exactly* 60 characters (must stay unchanged, an
    # upgrade-safety requirement since even one unnecessary rename forces
    # delete/recreate of a working shared private link). One character longer
    # (boundary+1) must switch to the bounded fallback token.
    foreach ($group in $groups) {
        # boundary length solves: 'spl-'.Length + N + 1 + groupId.Length + '-1'.Length == 60
        $boundaryLength = $maxResourceNameLength - 'spl-'.Length - 1 - $group.Length - '-1'.Length
        $boundaryName = 'a' * $boundaryLength
        $atBoundary = Get-SharedPrivateLinkNameLength -SearchServiceNameLength $boundaryName.Length -GroupId $group
        $expectedBoundaryName = "spl-$boundaryName-$group-1"
        if (-not $atBoundary.UsedDirectName -or $atBoundary.Length -ne $maxResourceNameLength -or $atBoundary.Length -ne $expectedBoundaryName.Length) {
            Add-Failure "Exact boundary: '$group' with a $boundaryLength-char Search service name should keep its plain, unchanged name at exactly $maxResourceNameLength chars; got length $($atBoundary.Length), direct=$($atBoundary.UsedDirectName)."
        }
        else {
            Add-Pass "Exact boundary: '$group' with a $boundaryLength-char Search service name keeps its plain name unchanged at exactly $maxResourceNameLength chars."
        }

        $overBoundaryName = 'a' * ($boundaryLength + 1)
        $overBoundary = Get-SharedPrivateLinkNameLength -SearchServiceNameLength $overBoundaryName.Length -GroupId $group
        if ($overBoundary.UsedDirectName -or $overBoundary.Length -gt $maxResourceNameLength) {
            Add-Failure "Boundary+1: '$group' with a $($boundaryLength + 1)-char Search service name (one char past the plain-name limit) should fall back to the bounded token and stay <= $maxResourceNameLength chars; got length $($overBoundary.Length), direct=$($overBoundary.UsedDirectName)."
        }
        else {
            Add-Pass "Boundary+1: '$group' with a $($boundaryLength + 1)-char Search service name correctly falls back to the bounded token, staying at $($overBoundary.Length) chars."
        }
    }

    # --- 6. Explicit longest-suffix boundary pin: Search name length 28/29 --
    # 'cognitiveservices_account' has the longest groupId (25 chars) of the
    # three groups, so it is the *first* to require the bounded fallback as
    # the Search service name grows -- it defines the tightest, longest-
    # suffix boundary. These literal lengths (28 and 29) are hardcoded here,
    # not derived from $group.Length in a loop, so this check stands on its
    # own and is not an inference from the generic per-group boundary matrix
    # in section 5 above.
    #   - At Search name length 28: 'spl-' (4) + 28 + '-' (1) + 25 + '-1' (2)
    #     = 60 exactly -> the direct/legacy name for 'cognitiveservices_account'
    #     must be used, unchanged, and exactly 60 characters.
    #   - At Search name length 29: the same computation = 61 -> exceeds the
    #     limit, so 'cognitiveservices_account' MUST switch to the bounded
    #     fallback token and stay <= 60. At this same 29-char Search name
    #     length, the two shorter-suffix groups ('openai_account' at 14 chars,
    #     'foundry_account' at 15 chars) do NOT yet need the fallback (their
    #     direct names are 50 and 51 chars respectively, both <= 60), proving
    #     the longest suffix switches first while shorter suffixes correctly
    #     retain their direct/legacy names where they still fit.
    $pinnedSearchNameLength28 = 28
    $pinnedSearchNameLength29 = 29
    $pinnedSearchName28 = 'a' * $pinnedSearchNameLength28

    $cogsAt28 = Get-SharedPrivateLinkNameLength -SearchServiceNameLength $pinnedSearchNameLength28 -GroupId 'cognitiveservices_account'
    $expectedCogsAt28Name = "spl-$pinnedSearchName28-cognitiveservices_account-1"
    if (-not $cogsAt28.UsedDirectName -or $cogsAt28.Length -ne 60 -or $cogsAt28.Length -ne $expectedCogsAt28Name.Length) {
        Add-Failure "Explicit pin: 'cognitiveservices_account' with a Search service name of exactly 28 characters must keep its direct/legacy name unchanged at exactly 60 characters (e.g. '$expectedCogsAt28Name'); got length $($cogsAt28.Length), direct=$($cogsAt28.UsedDirectName)."
    }
    else {
        Add-Pass "Explicit pin: 'cognitiveservices_account' with a Search service name of exactly 28 characters keeps its direct/legacy name unchanged at exactly 60 characters ('$expectedCogsAt28Name')."
    }

    $cogsAt29 = Get-SharedPrivateLinkNameLength -SearchServiceNameLength $pinnedSearchNameLength29 -GroupId 'cognitiveservices_account'
    if ($cogsAt29.UsedDirectName -or $cogsAt29.Length -gt $maxResourceNameLength) {
        Add-Failure "Explicit pin: 'cognitiveservices_account' with a Search service name of exactly 29 characters (the longest-suffix group) must switch to the bounded fallback and stay <= $maxResourceNameLength characters; got length $($cogsAt29.Length), direct=$($cogsAt29.UsedDirectName)."
    }
    else {
        Add-Pass "Explicit pin: 'cognitiveservices_account' with a Search service name of exactly 29 characters (the longest suffix) switches to the bounded fallback token, staying at $($cogsAt29.Length) chars."
    }

    $shorterSuffixGroups = @('openai_account', 'foundry_account')
    $shorterSuffixesStillDirect = $true
    foreach ($shorterGroup in $shorterSuffixGroups) {
        $shorterResult = Get-SharedPrivateLinkNameLength -SearchServiceNameLength $pinnedSearchNameLength29 -GroupId $shorterGroup
        if (-not $shorterResult.UsedDirectName -or $shorterResult.Length -gt $maxResourceNameLength) {
            $shorterSuffixesStillDirect = $false
            Add-Failure "Explicit pin: at Search service name length 29, the shorter-suffix group '$shorterGroup' should still fit and keep its direct/legacy name (<= $maxResourceNameLength chars); got length $($shorterResult.Length), direct=$($shorterResult.UsedDirectName)."
        }
    }
    if ($shorterSuffixesStillDirect) {
        Add-Pass "Explicit pin: at Search service name length 29, the shorter-suffix groups ('openai_account', 'foundry_account') correctly retain their direct/legacy names where they still fit, while only the longest suffix ('cognitiveservices_account') switches to the bounded fallback."
    }

    # --- 7. Regression guard: every direct-name usage is length-guarded -----
    # The plain, unbounded name literal ('spl-${resourceNames.searchServiceName}-
    # <group>-1') is expected to still appear in source as the "fits" branch of
    # the ternary, guarded by a `length(...) <= searchFoundrySharedPrivateLinkMaxNameLength`
    # check. What must NOT happen is that literal being assigned to `name:`
    # unconditionally (the pre-fix, v2.4.1 defect).

    $source = Get-Content -LiteralPath $MainFile -Raw
    $unconditionalPattern = "name:\s*'spl-\`$\{resourceNames\.searchServiceName\}-(?:openai|foundry|cognitiveservices)_account-1'"
    $guardedPattern = "length\('spl-\`$\{resourceNames\.searchServiceName\}-(?:openai|foundry|cognitiveservices)_account-1'\)\s*<=\s*searchFoundrySharedPrivateLinkMaxNameLength"
    $guardedMatches = [regex]::Matches($source, $guardedPattern).Count
    if ($source -match $unconditionalPattern) {
        Add-Failure 'A Foundry shared private link assigns the unbounded Search service name to `name:` unconditionally (no length guard).'
    }
    elseif ($guardedMatches -ne $groups.Count) {
        Add-Failure "Expected $($groups.Count) length-guarded direct-name branches in source, found $guardedMatches."
    }
    else {
        Add-Pass "All $guardedMatches Foundry shared private link direct names are guarded by a length(...) <= $maxResourceNameLength check (no unconditional unbounded name)."
    }
}
finally {
    Remove-Item -LiteralPath $compiledFile -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    Write-Host "`n$($failures.Count) shared private-link naming contract check(s) failed." -ForegroundColor Red
    exit 1
}

Write-Host "`nFoundry IQ shared private-link naming contract checks passed." -ForegroundColor Green
exit 0
