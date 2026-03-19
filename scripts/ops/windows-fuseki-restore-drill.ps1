param(
    [Parameter(Mandatory = $true)]
    [string]$SnapshotPath,
    [string]$DrillRoot = "",
    [switch]$SkipChecksumVerification,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$snapshot = (Resolve-Path $SnapshotPath).Path
$manifestPath = Join-Path $snapshot "snapshot_manifest.json"
$checksumsPath = Join-Path $snapshot "checksums.sha256"
$startedUtc = (Get-Date).ToUniversalTime().ToString("o")

if (-not (Test-Path $manifestPath)) {
    throw "Snapshot manifest not found: $manifestPath"
}
if (-not (Test-Path $checksumsPath)) {
    throw "Snapshot checksums not found: $checksumsPath"
}

if (-not $DrillRoot) {
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $DrillRoot = Join-Path $snapshot "drill-$stamp"
}

$stagedRoot = Join-Path $DrillRoot "restore_preview"
$missing = @()
$mismatched = @()
$verifiedCount = 0
$stagedPaths = @()

function Parse-Checksums {
    param([Parameter(Mandatory = $true)][string]$Path)

    return Get-Content $Path | Where-Object { $_.Trim() } | ForEach-Object {
        if ($_ -notmatch "^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$") {
            throw "Malformed checksum line: $_"
        }
        [ordered]@{
            sha256 = $Matches[1].ToLowerInvariant()
            path = $Matches[2]
        }
    }
}

Write-Host "Support contract: one Windows host and one read-only Fuseki instance."
Write-Host "Running non-destructive Fuseki restore drill for snapshot: $snapshot"

$entries = Parse-Checksums -Path $checksumsPath

if (-not $SkipChecksumVerification) {
    foreach ($entry in $entries) {
        $candidate = Join-Path $snapshot $entry.path
        if (-not (Test-Path $candidate)) {
            $missing += $entry.path
            continue
        }
        if (-not $DryRun) {
            $actual = (Get-FileHash $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne $entry.sha256) {
                $mismatched += $entry.path
                continue
            }
        }
        $verifiedCount += 1
    }
}

$restoreCandidates = @("config", "databases")
if ($DryRun) {
    Write-Host "[DRY-RUN] New-Item -ItemType Directory -Force -Path $stagedRoot"
}
else {
    New-Item -ItemType Directory -Force -Path $stagedRoot | Out-Null
}

foreach ($relative in $restoreCandidates) {
    $source = Join-Path $snapshot $relative
    if (-not (Test-Path $source)) {
        continue
    }
    $destination = Join-Path $stagedRoot $relative
    if ($DryRun) {
        Write-Host "[DRY-RUN] Copy-Item $source -> $destination"
    }
    else {
        Copy-Item $source $destination -Recurse -Force
    }
    $stagedPaths += $relative
}

$status = if ($missing.Count -eq 0 -and $mismatched.Count -eq 0) { "pass" } else { "fail" }

$report = [ordered]@{
    schema_version = "windows-fuseki-restore-drill.v1"
    snapshot_path = $snapshot
    drill_root = $DrillRoot
    staged_root = $stagedRoot
    started_utc = $startedUtc
    completed_utc = (Get-Date).ToUniversalTime().ToString("o")
    checksum_verification = [ordered]@{
        enabled = (-not $SkipChecksumVerification)
        verified_files = $verifiedCount
        missing_files = $missing
        mismatched_files = $mismatched
    }
    staged_paths = $stagedPaths
    status = $status
}

if ($DryRun) {
    Write-Host "[DRY-RUN] Restore drill report:"
    $report | ConvertTo-Json -Depth 6
    return
}

New-Item -ItemType Directory -Force -Path $DrillRoot | Out-Null
$reportPath = Join-Path $DrillRoot "restore_drill_report.json"
$report | ConvertTo-Json -Depth 6 | Set-Content -Path $reportPath -Encoding utf8
Write-Host "Fuseki restore drill report written: $reportPath"

if ($status -ne "pass") {
    throw "Fuseki restore drill failed. Missing files: $($missing.Count); mismatched files: $($mismatched.Count)."
}
