$repoRoot = Resolve-Path "$PSScriptRoot/.."
$dist = Join-Path $repoRoot 'dist'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
& py -m pip install --quiet cyclonedx-bom | Out-Null
$dest = Join-Path $dist 'sbom.cdx.json'
& py -m cyclonedx_py environment -o $dest | Out-Null
