param(
    [string]$CanonicalDir = "kg/canonical",
    [string]$OutputDir = "dist/offline_bundle"
)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$canonicalPath = Join-Path $repoRoot $CanonicalDir
if (-not (Test-Path $canonicalPath)) {
    throw "Canonical directory not found: $CanonicalDir"
}

$requiredFiles = @('dataset.nq', 'dataset.ttl', 'provenance.json')
foreach ($file in $requiredFiles) {
    $path = Join-Path $canonicalPath $file
    if (-not (Test-Path $path)) {
        throw "Missing canonical artifact: $file"
    }
}

$bundleRoot = Join-Path $repoRoot $OutputDir
if (Test-Path $bundleRoot) {
    Remove-Item -Path $bundleRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $bundleRoot | Out-Null

function Copy-Tree([string]$from, [string]$to) {
    if (-not (Test-Path $from)) { return }
    New-Item -ItemType Directory -Path $to -Force | Out-Null
    Get-ChildItem -Path $from -Force | ForEach-Object {
        $destination = Join-Path $to $_.Name
        if ($_.PsIsContainer) {
            Copy-Tree -from $_.FullName -to $destination
        } else {
            Copy-Item -Path $_.FullName -Destination $destination -Force
        }
    }
}

# Copy canonical KG
Copy-Tree -from $canonicalPath -to (Join-Path $bundleRoot 'kg')

# Copy Fuseki assembler and config
$fusekiRoot = Join-Path $bundleRoot 'fuseki'
New-Item -ItemType Directory -Path $fusekiRoot -Force | Out-Null
Copy-Item -Path (Join-Path $repoRoot 'bundle/assembler/tdb2-readonly.ttl') `
    -Destination (Join-Path $fusekiRoot 'tdb2-readonly.ttl') -Force
Copy-Tree -from (Join-Path $repoRoot 'bundle/config') -to (Join-Path $bundleRoot 'config')

# Copy scripts
Copy-Tree -from (Join-Path $repoRoot 'bundle/scripts') -to (Join-Path $bundleRoot 'scripts')

# Copy static files
Copy-Tree -from (Join-Path $repoRoot 'bundle/static') -to $bundleRoot

# Ensure directories required by runtime exist
New-Item -ItemType Directory -Path (Join-Path $bundleRoot 'fuseki/databases') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $bundleRoot 'fuseki/logs') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $bundleRoot 'kg/reports') -Force | Out-Null

# Write VERSION.txt
$pyproject = Get-Content (Join-Path $repoRoot 'pyproject.toml')
$versionLine = $pyproject | Where-Object { $_ -match '^version\s*=\s*"' } | Select-Object -First 1
if (-not $versionLine) { throw 'Unable to determine project version' }
$version = ($versionLine -split '"')[1]
$commit = (git -C $repoRoot rev-parse HEAD).Trim()
$versionContent = @(
    "Version: $version",
    "Commit: $commit"
)
$versionContent | Set-Content -Path (Join-Path $bundleRoot 'VERSION.txt') -Encoding utf8

# Update SBOM component version
$sbomPath = Join-Path $bundleRoot 'SBOM.cdx.json'
if (Test-Path $sbomPath) {
    $sbom = Get-Content $sbomPath -Raw | ConvertFrom-Json
    if ($sbom.metadata -and $sbom.metadata.component) {
        $sbom.metadata.component.version = $version
    }
    $sbom | ConvertTo-Json -Depth 10 | Set-Content -Path $sbomPath -Encoding utf8
}

# Generate manifest
$sourceEpoch = $env:SOURCE_DATE_EPOCH
if (-not $sourceEpoch) { $sourceEpoch = 946684800 }
$timestamp = [DateTimeOffset]::FromUnixTimeSeconds([int64]$sourceEpoch).UtcDateTime.ToString('yyyy-MM-ddTHH:mm:ssZ')

$files = Get-ChildItem -Path $bundleRoot -Recurse -File | ForEach-Object {
    $relative = [IO.Path]::GetRelativePath($bundleRoot, $_.FullName).Replace([IO.Path]::DirectorySeparatorChar, [char]'/' )
    [pscustomobject]@{ File = $_; Relative = $relative }
} | Sort-Object -Property Relative
$manifestEntries = @()
$checksumLines = @()
foreach ($entry in $files) {
    $file = $entry.File
    $relative = $entry.Relative
    $hash = (Get-FileHash -Path $file.FullName -Algorithm SHA256).Hash.ToLower()
    $manifestEntries += [ordered]@{
        path = $relative
        size = $file.Length
        sha256 = $hash
    }
    $checksumLines += "$hash  $relative"
}

$manifest = [ordered]@{
    version = $version
    commit = $commit
    generated = $timestamp
    files = $manifestEntries
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $bundleRoot 'manifest.json') -Encoding utf8
$checksumLines | Set-Content -Path (Join-Path $bundleRoot 'checksums.sha256') -Encoding ascii

# Ensure signature placeholder exists
$signaturePath = Join-Path $bundleRoot 'manifest.sig.PLACEHOLDER.txt'
if (-not (Test-Path $signaturePath)) {
    'Placeholder for detached signature.' | Set-Content -Path $signaturePath -Encoding utf8
}

# Copy provenance explicitly (should already exist under kg/)
$provSrc = Join-Path $canonicalPath 'provenance.json'
Copy-Item -Path $provSrc -Destination (Join-Path $bundleRoot 'provenance.json') -Force

# Create smoke report placeholder if not present
$smoke = Join-Path $bundleRoot 'kg/reports/bundle-smoke.txt'
if (-not (Test-Path $smoke)) {
    "Smoke test pending" | Set-Content -Path $smoke -Encoding utf8
}

Write-Host "Offline bundle staged at $bundleRoot"
