param(
    [string]$SnapshotDir = "kg/snapshots",
    [string]$BaselineDir = "kg/baseline",
    [string]$SourceDateEpoch
)

$ErrorActionPreference = 'Stop'
$WarningPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if (-not $SourceDateEpoch) {
    $SourceDateEpoch = $env:SOURCE_DATE_EPOCH
}
if (-not $SourceDateEpoch) {
    $SourceDateEpoch = '946684800'
}
$env:SOURCE_DATE_EPOCH = $SourceDateEpoch

if (Test-Path $BaselineDir) {
    Remove-Item -Recurse -Force $BaselineDir
}
New-Item -ItemType Directory -Force -Path $BaselineDir | Out-Null

kg/scripts/canonical-freeze.ps1 -SnapshotDir $SnapshotDir -OutputDir $BaselineDir
scripts/make-manifest.ps1 -CanonicalDir $BaselineDir -DistDir ""
scripts/verify-release.ps1 -ManifestPath (Join-Path $BaselineDir 'manifest.json') -BaseDir "."

$required = @('dataset.nq', 'versions.json', 'manifest.json', 'checksums.sha256')
foreach ($name in $required) {
    $path = Join-Path $BaselineDir $name
    if (-not (Test-Path $path)) {
        throw "Missing required baseline artifact: $path"
    }
}

$snapDir = Join-Path $BaselineDir 'snapshots'
$snapshots = Get-ChildItem -Path $snapDir -Filter *.srj -File -ErrorAction SilentlyContinue
if (-not $snapshots) {
    throw "No snapshot SRJ files found under $snapDir"
}

Write-Host "Phase B baseline frozen at $BaselineDir using SOURCE_DATE_EPOCH=$SourceDateEpoch"
