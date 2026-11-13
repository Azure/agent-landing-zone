# ADR-0041: exact inverse of the approved producer-only output migration.
# Historical fixtures are immutable. Fingerprints cover the entire new output
# (all gates, scopes, identities and children), not merely its membership.
function ConvertTo-PreDeploymentMetadataGraph {
    param([Parameter(Mandatory)] $Template)
    $copy = ConvertTo-Json -InputObject $Template -Depth 100 -Compress |
        ConvertFrom-Json -AsHashtable -Depth 100
    $fixture = Get-Content (Join-Path $PSScriptRoot 'fixtures\deployment-metadata-normalization.json') -Raw |
        ConvertFrom-Json -AsHashtable
    if ($copy.outputs.Count -ne 64 -or
        $copy.outputs.Contains('OBSERVABILITY_MIXED_WORKSPACES_ALLOWED') -or
        -not $copy.outputs.Contains('DEPLOYMENT_METADATA')) {
        throw 'SCOPED: unapproved deployment metadata output membership.'
    }
    foreach ($entry in @(
        @{ Value = $copy.outputs.DEPLOYMENT_METADATA; Digest = $fixture.outputSha256; Path = '/outputs/DEPLOYMENT_METADATA' },
        @{ Value = $copy.variables._deploymentMetadataModels; Digest = $fixture.modelsSha256; Path = '/variables/_deploymentMetadataModels' }
    )) {
        $json = ConvertTo-Json -InputObject (ConvertTo-ScopedComparable $entry.Value) -Depth 100 -Compress
        $digest = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($json))).ToLowerInvariant()
        if ($digest -cne $entry.Digest) { throw "SCOPED: unreviewed deployment metadata delta at $($entry.Path)." }
    }
    Assert-ScopedValue $copy.parameters.applicationId $fixture.applicationIdParameter '/parameters/applicationId'
    Assert-ScopedValue $copy.resources.aiFoundry.properties.parameters.aiModelDeployments `
        @{ value = "[variables('_deploymentMetadataModels')]" } '/resources/aiFoundry/sharedModelSelection'
    # The single shared native fallback is identical to the already reviewed
    # selection; only its factoring changed. Preserve the old exact expression.
    $copy.resources.aiFoundry.properties.parameters.aiModelDeployments =
        (Get-EmbeddingDefaultProjection).changes.resources.changes.aiFoundry.changes.properties.changes.parameters.changes.aiModelDeployments.after
    $null = $copy.variables.Remove('_deploymentMetadataModels')
    $null = $copy.parameters.Remove('applicationId')
    $null = $copy.outputs.Remove('DEPLOYMENT_METADATA')
    $copy.outputs.OBSERVABILITY_MIXED_WORKSPACES_ALLOWED = $fixture.retiredOutput
    return $copy
}
