param(
    [string]$ServiceName = "EarCrawler-Fuseki",
    [string]$NssmPath = "C:\tools\nssm\nssm.exe",
    [string]$ProgramDataRoot = "C:\ProgramData\EarCrawler\fuseki",
    [string]$FusekiHome = "C:\Program Files\Apache\Jena-Fuseki-5.3.0",
    [string]$BackupRoot = "",
    [string]$BackupId = "",
    [switch]$SkipServiceControl,
    [switch]$RestartServiceAfterBackup,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $BackupRoot) {
    $BackupRoot = "C:\ProgramData\EarCrawler\backups\fuseki"
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

Write-Host "Support contract: one Windows host and one read-only Fuseki instance."
Write-Host "Creating Fuseki backup snapshot '$BackupId' under '$BackupRoot'."

if (-not $SkipServiceControl) {
    Invoke-Nssm -Executable $NssmPath -Arguments @("stop", $ServiceName) -DryRunMode:$DryRun
}

if ($DryRun) {
    Write-Host "[DRY-RUN] New-Item -ItemType Directory -Force -Path $backupPath"
}
else {
    New-Item -ItemType Directory -Force -Path $backupPath | Out-Null
}

$snapshotRoots = @("config", "databases", "logs")
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
    Try-CaptureCommand -Description "java version capture" -Command {
        java -version 2>&1 | Set-Content -Path (Join-Path $backupPath "java-version.txt") -Encoding utf8
    }
}

if ($DryRun) {
    Write-Host "[DRY-RUN] Record Fuseki home path: $FusekiHome"
}
else {
    [ordered]@{
        fuseki_home = $FusekiHome
        program_data_root = $ProgramDataRoot
    } | ConvertTo-Json -Depth 3 | Set-Content -Path (Join-Path $backupPath "fuseki-install.json") -Encoding utf8
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
    schema_version = "windows-fuseki-backup.v1"
    backup_id = $BackupId
    created_utc = $createdUtc
    service_name = $ServiceName
    fuseki_home = $FusekiHome
    single_host_contract = "one_windows_host_one_readonly_fuseki_instance"
    program_data_root = $ProgramDataRoot
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

Write-Host "Fuseki backup snapshot complete: $backupPath"
Write-Host "Wrote: $manifestPath"
Write-Host "Wrote: $checksumsPath"
