param(
    [string]$Path = $(Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$bundleRoot = Resolve-Path $Path
$checksumFile = Join-Path $bundleRoot 'checksums.sha256'
if (-not (Test-Path $checksumFile)) {
    throw "checksums.sha256 not found in $bundleRoot"
}

$expected = [ordered]@{}
$lines = Get-Content -Path $checksumFile | Where-Object { $_.Trim() -ne '' }
foreach ($line in $lines) {
    if ($line -match '^([0-9a-f]{64})\s+(.+)$') {
        $expected[$Matches[2]] = $Matches[1].ToLower()
    } else {
        throw "Malformed checksum line: $line"
    }
}

$errors = @()
foreach ($entry in $expected.GetEnumerator()) {
    $rel = $entry.Key
    $hash = $entry.Value
    $full = Join-Path $bundleRoot $rel
    if (-not (Test-Path $full)) {
        $errors += "Missing file: $rel"
        continue
    }
    $actual = (Get-FileHash -Path $full -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $hash) {
        $errors += "Hash mismatch for $rel"
    }
}

$allFiles = Get-ChildItem -Path $bundleRoot -Recurse -File | ForEach-Object {
    [IO.Path]::GetRelativePath($bundleRoot, $_.FullName).Replace('\\', '/')
} | Sort-Object -Unique
$unexpected = @()
foreach ($file in $allFiles) {
    if (-not $expected.Contains($file)) {
        $unexpected += $file
    }
}

if ($unexpected) {
    Write-Warning ("Unexpected files detected:" + [Environment]::NewLine + ($unexpected -join [Environment]::NewLine))
}

if ($errors) {
    $errors | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host "Bundle verification OK"
