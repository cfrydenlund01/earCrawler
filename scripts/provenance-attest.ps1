param(
    [string]$ManifestPath = "kg/canonical/manifest.json",
    [string]$OutPath = "kg/canonical/provenance.json"
)

$manifestHash = (Get-FileHash $ManifestPath -Algorithm SHA256).Hash.ToLower()
$commit = (git rev-parse HEAD).Trim()
$runId = $env:GITHUB_RUN_ID
$runner = $env:RUNNER_OS
$timestamp = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')
$toolsHash = (Get-FileHash 'tools/versions.json' -Algorithm SHA256).Hash.ToLower()

$prov = [ordered]@{
    git_commit = $commit
    manifest_sha256 = $manifestHash
    run_id = $runId
    runner_os = $runner
    tool_versions_sha256 = $toolsHash
    build_timestamp = $timestamp
}
$prov | ConvertTo-Json -Depth 5 | Set-Content -Path $OutPath -Encoding utf8
