$repoRoot = Resolve-Path "$PSScriptRoot/.."
$dist = Join-Path $repoRoot 'dist'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
if (-not (Get-Command cyclonedx-py -ErrorAction SilentlyContinue)) {
    pip install cyclonedx-bom | Out-Null
}
$dest = Join-Path $dist 'sbom.cdx.json'
cyclonedx-py -o $dest | Out-Null
