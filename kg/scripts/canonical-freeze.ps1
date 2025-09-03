param(
    [string]$SnapshotDir = "kg/snapshots",
    [string]$OutputDir = "kg/canonical"
)

# Ensure output directory
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $OutputDir 'snapshots') | Out-Null

# Convert Unix epoch to DateTime
if ($env:SOURCE_DATE_EPOCH) {
    $epoch = [int64]$env:SOURCE_DATE_EPOCH
    $fixedTime = [DateTimeOffset]::FromUnixTimeSeconds($epoch).UtcDateTime
} else {
    $fixedTime = [DateTime]::SpecifyKind([DateTime]::Parse('2000-01-01T00:00:00Z'), 'Utc')
}

function ConvertTo-CanonicalJson($obj) {
    if ($obj -is [System.Collections.IDictionary]) {
        $ordered = [ordered]@{}
        foreach ($key in ($obj.Keys | Sort-Object)) {
            $ordered[$key] = ConvertTo-CanonicalJson $obj[$key]
        }
        return $ordered
    } elseif ($obj -is [System.Collections.IEnumerable] -and $obj -isnot [string]) {
        return @($obj | ForEach-Object { ConvertTo-CanonicalJson $_ })
    } else {
        return $obj
    }
}

# Sort dataset.nq if present
$datasetSrc = Join-Path $SnapshotDir 'dataset.nq'
if (Test-Path $datasetSrc) {
    $lines = Get-Content $datasetSrc | Sort-Object
    $datasetDest = Join-Path $OutputDir 'dataset.nq'
    $lines | Set-Content -Path $datasetDest -Encoding utf8
}

# Normalize JSON snapshots
Get-ChildItem -Path $SnapshotDir -Filter *.srj -Recurse | ForEach-Object {
    $rel = [IO.Path]::GetRelativePath($SnapshotDir, $_.FullName)
    $dest = Join-Path $OutputDir 'snapshots'
    $dest = Join-Path $dest $rel
    $destDir = Split-Path $dest -Parent
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    $json = Get-Content $_.FullName -Raw | ConvertFrom-Json -AsHashtable
    $canon = ConvertTo-CanonicalJson $json
    $canon | ConvertTo-Json -Depth 100 | Set-Content -Path $dest -Encoding utf8
}

# versions.json with tool hash
$toolsPath = 'tools/versions.json'
if (Test-Path $toolsPath) {
    $hash = (Get-FileHash $toolsPath -Algorithm SHA256).Hash.ToLower()
    $tools = Get-Content $toolsPath -Raw | ConvertFrom-Json
    $versions = [ordered]@{ tools = $tools; tools_sha256 = $hash }
    $versions | ConvertTo-Json -Depth 10 | Set-Content -Path (Join-Path $OutputDir 'versions.json') -Encoding utf8
}

# Set fixed timestamps
Get-ChildItem -Path $OutputDir -Recurse | Where-Object { -not $_.PSIsContainer } | ForEach-Object {
    $_.LastWriteTimeUtc = $fixedTime
}
