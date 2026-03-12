param(
    [string]$ServiceName = "EarCrawler-API",
    [string]$NssmPath = "C:\tools\nssm\nssm.exe",
    [string]$ProgramDataRoot = "C:\ProgramData\EarCrawler",
    [string]$RuntimeRoot = "C:\Program Files\EarCrawler\runtime",
    [string]$BackupRoot = "",
    [string]$BackupId = "",
    [switch]$SkipServiceControl,
    [switch]$RestartServiceAfterBackup,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $BackupRoot) {
    $BackupRoot = Join-Path $ProgramDataRoot "backups"
}

if (-not $BackupId) {
    $BackupId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
}

$backupPath = Join-Path $BackupRoot $BackupId
$copiedPaths = @()
$missingPaths = @()
$createdUtc = (Get-Date).ToUniversalTime().ToString("o")

function Invoke-Nssm {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$DryRunMode
    )

    if ($DryRunMode) {
        $argsText = ($Arguments | ForEach-Object { if ($_ -match "\s") { "`"$_`"" } else { $_ } }) -join " "
        Write-Host "[DRY-RUN] $Executable $argsText"
        return
    }
    if (-not (Test-Path $Executable)) {
        throw "NSSM executable not found: $Executable"
    }
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "NSSM command failed with exit code $LASTEXITCODE."
    }
}

function Try-CaptureCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Description,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )

    try {
        & $Command
    }
    catch {
        Write-Warning "$Description failed: $($_.Exception.Message)"
    }
}

Write-Host "Support contract: one Windows host and one EarCrawler API service instance."
Write-Host "Creating backup snapshot '$BackupId' under '$BackupRoot'."

if (-not $SkipServiceControl) {
    Invoke-Nssm -Executable $NssmPath -Arguments @("stop", $ServiceName) -DryRunMode:$DryRun
}

if ($DryRun) {
    Write-Host "[DRY-RUN] New-Item -ItemType Directory -Force -Path $backupPath"
}
else {
    New-Item -ItemType Directory -Force -Path $backupPath | Out-Null
}

$snapshotRoots = @("config", "logs", "workspace", "audit", "spool")
foreach ($relative in $snapshotRoots) {
    $source = Join-Path $ProgramDataRoot $relative
    $destination = Join-Path $backupPath $relative
    if (Test-Path $source) {
        if ($DryRun) {
            Write-Host "[DRY-RUN] Copy-Item $source -> $destination"
        }
        else {
            Copy-Item $source $destination -Recurse -Force
        }
        $copiedPaths += $relative
    }
    else {
        $missingPaths += $relative
        Write-Warning "Path not found, skipping: $source"
    }
}

$venvPython = Join-Path $RuntimeRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    if ($DryRun) {
        Write-Host "[DRY-RUN] $venvPython -m pip show earCrawler > pip-show.txt"
    }
    else {
        Try-CaptureCommand -Description "pip show capture" -Command {
            & $venvPython -m pip show earCrawler | Set-Content -Path (Join-Path $backupPath "pip-show.txt") -Encoding utf8
        }
    }
}
else {
    Write-Warning "Runtime python not found; skipping pip-show capture: $venvPython"
}

if (-not $DryRun) {
    Try-CaptureCommand -Description "machine environment export" -Command {
        reg export "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" (Join-Path $backupPath "machine-env.reg") /y | Out-Null
    }
    Try-CaptureCommand -Description "service qc capture" -Command {
        sc.exe qc $ServiceName > (Join-Path $backupPath "service-qc.txt")
    }
    Try-CaptureCommand -Description "service failure-policy capture" -Command {
        sc.exe qfailure $ServiceName > (Join-Path $backupPath "service-failure.txt")
    }
}

if ($RestartServiceAfterBackup -and -not $SkipServiceControl) {
    Invoke-Nssm -Executable $NssmPath -Arguments @("start", $ServiceName) -DryRunMode:$DryRun
}

if ($DryRun) {
    Write-Host "[DRY-RUN] Backup complete."
    return
}

$excluded = @("snapshot_manifest.json", "checksums.sha256")
$entries = Get-ChildItem -Path $backupPath -Recurse -File |
    Where-Object { $excluded -notcontains $_.Name } |
    Sort-Object FullName |
    ForEach-Object {
        $relativePath = [IO.Path]::GetRelativePath($backupPath, $_.FullName).Replace("\", "/")
        $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        [ordered]@{
            path = $relativePath
            size = $_.Length
            sha256 = $hash
        }
    }

$manifest = [ordered]@{
    schema_version = "windows-single-host-backup.v1"
    backup_id = $BackupId
    created_utc = $createdUtc
    service_name = $ServiceName
    single_host_contract = "one_windows_host_one_service_instance"
    program_data_root = $ProgramDataRoot
    runtime_root = $RuntimeRoot
    copied_paths = $copiedPaths
    missing_paths = $missingPaths
    files = $entries
}

$manifestPath = Join-Path $backupPath "snapshot_manifest.json"
$checksumsPath = Join-Path $backupPath "checksums.sha256"

$manifest | ConvertTo-Json -Depth 8 | Set-Content -Path $manifestPath -Encoding utf8
$entries |
    ForEach-Object { "{0}  {1}" -f $_.sha256, $_.path } |
    Set-Content -Path $checksumsPath -Encoding utf8

Write-Host "Backup snapshot complete: $backupPath"
Write-Host "Wrote: $manifestPath"
Write-Host "Wrote: $checksumsPath"
