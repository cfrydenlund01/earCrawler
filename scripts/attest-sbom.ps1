$repoRoot = Resolve-Path "$PSScriptRoot/.."
$sbom = Join-Path $repoRoot 'dist/sbom.cdx.json'
if (-not (Test-Path $sbom)) {
    Write-Output "SBOM not found; skipping"
    exit 0
}
if ($env:GITHUB_ACTIONS -ne 'true') {
    Write-Output "Not running on GitHub Actions; no-op"
    exit 0
}
Write-Output "Attesting SBOM via GitHub provenance"
# Placeholder for `gh attestation` or similar
