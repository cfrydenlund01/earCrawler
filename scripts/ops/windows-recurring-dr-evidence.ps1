param(
    [string]$RunId = "",
    [string]$ProgramDataRoot = "C:\ProgramData\EarCrawler",
    [string]$RuntimeRoot = "C:\Program Files\EarCrawler\runtime",
    [string]$ApiBackupRoot = "",
    [string]$FusekiProgramDataRoot = "C:\ProgramData\EarCrawler\fuseki",
    [string]$FusekiHome = "C:\Program Files\Apache\Jena-Fuseki-5.3.0",
    [string]$FusekiBackupRoot = "",
    [string]$EvidenceRoot = "",
    [int]$RetentionRuns = 30,
    [switch]$SkipServiceControl,
    [switch]$SkipFuseki,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $RunId) {
    $RunId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
}
if (-not $ApiBackupRoot) {
    $ApiBackupRoot = Join-Path $ProgramDataRoot "backups"
}
if (-not $FusekiBackupRoot) {
    $FusekiBackupRoot = "C:\ProgramData\EarCrawler\backups\fuseki"
}
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path $ApiBackupRoot "recurring-evidence"
}
if ($RetentionRuns -lt 1) {
    throw "RetentionRuns must be >= 1."
}

$scriptRoot = $PSScriptRoot
$apiBackupScript = Join-Path $scriptRoot "windows-single-host-backup.ps1"
$apiRestoreScript = Join-Path $scriptRoot "windows-single-host-restore-drill.ps1"
$fusekiBackupScript = Join-Path $scriptRoot "windows-fuseki-backup.ps1"
$fusekiRestoreScript = Join-Path $scriptRoot "windows-fuseki-restore-drill.ps1"

$runStartedUtc = (Get-Date).ToUniversalTime().ToString("o")
$apiBackupId = "$RunId-api"
$fusekiBackupId = "$RunId-fuseki"

Write-Host "Support contract: one Windows host, one EarCrawler API instance, and one local read-only Fuseki instance."
Write-Host "Starting recurring DR evidence run: $RunId"

$apiSnapshotPath = Join-Path $ApiBackupRoot $apiBackupId
$apiDrillRoot = Join-Path (Join-Path $ApiBackupRoot "drills") $apiBackupId

$fusekiSnapshotPath = Join-Path $FusekiBackupRoot $fusekiBackupId
$fusekiDrillRoot = Join-Path (Join-Path $FusekiBackupRoot "drills") $fusekiBackupId

$apiStatus = "pending"
$apiError = ""
$fusekiStatus = if ($SkipFuseki) { "skipped" } else { "pending" }
$fusekiError = ""

try {
    $apiBackupParams = @{
        ProgramDataRoot = $ProgramDataRoot
        RuntimeRoot = $RuntimeRoot
        BackupRoot = $ApiBackupRoot
        BackupId = $apiBackupId
    }
    if ($SkipServiceControl) { $apiBackupParams.SkipServiceControl = $true }
    if ($DryRun) { $apiBackupParams.DryRun = $true }
    & $apiBackupScript @apiBackupParams

    if ($DryRun) {
        $apiStatus = "skipped_dry_run"
    }
    else {
        $apiRestoreParams = @{
            SnapshotPath = $apiSnapshotPath
            DrillRoot = $apiDrillRoot
        }
        & $apiRestoreScript @apiRestoreParams
        $apiStatus = "pass"
    }
}
catch {
    $apiStatus = "fail"
    $apiError = $_.Exception.Message
}

if (-not $SkipFuseki) {
    try {
        $fusekiBackupParams = @{
            ProgramDataRoot = $FusekiProgramDataRoot
            FusekiHome = $FusekiHome
            BackupRoot = $FusekiBackupRoot
            BackupId = $fusekiBackupId
        }
        if ($SkipServiceControl) { $fusekiBackupParams.SkipServiceControl = $true }
        if ($DryRun) { $fusekiBackupParams.DryRun = $true }
        & $fusekiBackupScript @fusekiBackupParams

        if ($DryRun) {
            $fusekiStatus = "skipped_dry_run"
        }
        else {
            $fusekiRestoreParams = @{
                SnapshotPath = $fusekiSnapshotPath
                DrillRoot = $fusekiDrillRoot
            }
            & $fusekiRestoreScript @fusekiRestoreParams
            $fusekiStatus = "pass"
        }
    }
    catch {
        $fusekiStatus = "fail"
        $fusekiError = $_.Exception.Message
    }
}

$overallStatus = "pass"
if ($apiStatus -eq "fail" -or $fusekiStatus -eq "fail") {
    $overallStatus = "fail"
}

$report = [ordered]@{
    schema_version = "windows-recurring-dr-evidence.v1"
    run_id = $RunId
    started_utc = $runStartedUtc
    completed_utc = (Get-Date).ToUniversalTime().ToString("o")
    single_host_contract = "one_windows_host_one_api_service_instance_one_readonly_fuseki_instance"
    dry_run = $DryRun.IsPresent
    overall_status = $overallStatus
    api = [ordered]@{
        status = $apiStatus
        backup_id = $apiBackupId
        snapshot_path = $apiSnapshotPath
        snapshot_manifest_path = Join-Path $apiSnapshotPath "snapshot_manifest.json"
        checksums_path = Join-Path $apiSnapshotPath "checksums.sha256"
        drill_root = $apiDrillRoot
        drill_report_path = Join-Path $apiDrillRoot "restore_drill_report.json"
        error = $apiError
    }
    fuseki = [ordered]@{
        enabled = (-not $SkipFuseki)
        status = $fusekiStatus
        backup_id = $fusekiBackupId
        snapshot_path = $fusekiSnapshotPath
        snapshot_manifest_path = Join-Path $fusekiSnapshotPath "snapshot_manifest.json"
        checksums_path = Join-Path $fusekiSnapshotPath "checksums.sha256"
        drill_root = $fusekiDrillRoot
        drill_report_path = Join-Path $fusekiDrillRoot "restore_drill_report.json"
        error = $fusekiError
    }
}

if (-not $DryRun) {
    New-Item -ItemType Directory -Force -Path $EvidenceRoot | Out-Null
    $reportPath = Join-Path $EvidenceRoot ("dr-evidence-run-{0}.json" -f $RunId)
    $report | ConvertTo-Json -Depth 8 | Set-Content -Path $reportPath -Encoding utf8

    $indexPath = Join-Path $EvidenceRoot "dr-evidence-index.json"
    $existingRuns = @()
    if (Test-Path $indexPath) {
        try {
            $existingIndex = Get-Content -Path $indexPath -Raw | ConvertFrom-Json
            $existingRuns = @($existingIndex.runs)
        }
        catch {
            Write-Warning "Unable to parse existing DR evidence index. Rebuilding index from current run only."
        }
    }

    $runEntry = [ordered]@{
        run_id = $RunId
        completed_utc = $report.completed_utc
        overall_status = $overallStatus
        report_path = $reportPath
        api_status = $apiStatus
        fuseki_status = $fusekiStatus
    }

    $combinedRuns = @($runEntry)
    foreach ($entry in $existingRuns) {
        if ([string]$entry.run_id -ne $RunId) {
            $combinedRuns += $entry
        }
    }
    $retainedRuns = @($combinedRuns | Select-Object -First $RetentionRuns)

    $index = [ordered]@{
        schema_version = "windows-recurring-dr-evidence-index.v1"
        generated_utc = (Get-Date).ToUniversalTime().ToString("o")
        retention_runs = $RetentionRuns
        evidence_root = $EvidenceRoot
        runs = $retainedRuns
    }
    $index | ConvertTo-Json -Depth 8 | Set-Content -Path $indexPath -Encoding utf8

    Write-Host "DR evidence run report written: $reportPath"
    Write-Host "DR evidence index written: $indexPath"
}
else {
    Write-Host "[DRY-RUN] Recurring DR evidence report:"
    $report | ConvertTo-Json -Depth 8
}

if ($overallStatus -ne "pass") {
    throw "Recurring DR evidence run failed. API status: $apiStatus. Fuseki status: $fusekiStatus."
}

Write-Host "Recurring DR evidence run completed with status: $overallStatus"
