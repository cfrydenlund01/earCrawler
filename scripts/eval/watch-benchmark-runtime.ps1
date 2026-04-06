param(
    [int]$BenchmarkPid = 0,
    [int]$ApiPid = 0,
    [string]$RunId = '',
    [string]$OutDir = '',
    [string]$ApiStatePath = 'kg/reports/api.process.json',
    [string]$ApiBaseUrl = 'http://127.0.0.1:9001',
    [int]$SampleIntervalSeconds = 2,
    [int]$MaxSamples = 0,
    [bool]$StopWhenBenchmarkExits = $true,
    [string]$LogPath = '',
    [string]$StatePath = ''
)

$ErrorActionPreference = 'Stop'

function Get-UtcIsoNow {
    return (Get-Date).ToUniversalTime().ToString('o')
}

function ConvertTo-JsonLine {
    param([Parameter(Mandatory = $true)]$Payload)

    return ($Payload | ConvertTo-Json -Depth 10 -Compress)
}

function Append-JsonLine {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Payload
    )

    $dir = Split-Path -Parent $Path
    if ($dir) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    Add-Content -Path $Path -Value (ConvertTo-JsonLine -Payload $Payload) -Encoding utf8
}

function Write-JsonState {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Payload
    )

    $dir = Split-Path -Parent $Path
    if ($dir) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    ($Payload | ConvertTo-Json -Depth 10) | Set-Content -Path $Path -Encoding utf8
}

function Read-ApiState {
    param([string]$Path)

    if (-not $Path -or -not (Test-Path $Path)) {
        return $null
    }
    try {
        return Get-Content -Path $Path -Raw | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Get-ChildProcessIds {
    param([int]$ParentProcessId)

    if ($ParentProcessId -le 0) {
        return @()
    }

    $children = Get-CimInstance Win32_Process -Filter ("ParentProcessId = {0}" -f $ParentProcessId) -ErrorAction SilentlyContinue
    if ($null -eq $children) {
        return @()
    }
    return @($children | Select-Object -ExpandProperty ProcessId)
}

function Get-ProcessTreeIds {
    param([int]$RootProcessId)

    if ($RootProcessId -le 0) {
        return @()
    }

    $root = Get-Process -Id $RootProcessId -ErrorAction SilentlyContinue
    if ($null -eq $root) {
        return @()
    }

    $queue = New-Object System.Collections.Generic.Queue[int]
    $visited = New-Object System.Collections.Generic.HashSet[int]
    $ordered = New-Object System.Collections.Generic.List[int]
    $queue.Enqueue($RootProcessId)

    while ($queue.Count -gt 0) {
        $candidateId = $queue.Dequeue()
        if (-not $visited.Add($candidateId)) {
            continue
        }
        [void]$ordered.Add($candidateId)
        foreach ($childId in (Get-ChildProcessIds -ParentProcessId $candidateId)) {
            if (-not $visited.Contains($childId)) {
                $queue.Enqueue([int]$childId)
            }
        }
    }

    return @($ordered.ToArray())
}

function Get-ProcessSnapshot {
    param([int]$ProcessId)

    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    $cim = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $ProcessId) -ErrorAction SilentlyContinue

    if ($null -eq $proc -and $null -eq $cim) {
        return [ordered]@{
            pid = $ProcessId
            exists = $false
        }
    }

    return [ordered]@{
        pid = $ProcessId
        exists = $true
        parent_pid = if ($cim) { [int]$cim.ParentProcessId } else { $null }
        name = if ($proc) { [string]$proc.ProcessName } elseif ($cim) { [string]$cim.Name } else { '' }
        path = if ($proc) { [string]$proc.Path } elseif ($cim) { [string]$cim.ExecutablePath } else { '' }
        command_line = if ($cim) { [string]$cim.CommandLine } else { '' }
        started_local = if ($proc) { $proc.StartTime.ToString('o') } else { $null }
        threads = if ($proc) { [int]$proc.Threads.Count } else { $null }
        handles = if ($proc) { [int]$proc.HandleCount } else { $null }
        cpu_seconds = if ($proc) { [double]$proc.CPU } else { $null }
        working_set_bytes = if ($proc) { [int64]$proc.WorkingSet64 } elseif ($cim) { [int64]$cim.WorkingSetSize } else { $null }
        peak_working_set_bytes = if ($proc) { [int64]$proc.PeakWorkingSet64 } else { $null }
        virtual_memory_bytes = if ($proc) { [int64]$proc.VirtualMemorySize64 } elseif ($cim) { [int64]$cim.VirtualSize } else { $null }
        paged_memory_bytes = if ($proc) { [int64]$proc.PagedMemorySize64 } else { $null }
        private_memory_bytes = if ($cim) { [int64]$cim.PrivatePageCount } else { $null }
        page_file_bytes = if ($cim) { [int64]$cim.PageFileUsage } else { $null }
        peak_page_file_bytes = if ($cim) { [int64]$cim.PeakPageFileUsage } else { $null }
        read_transfer_bytes = if ($cim) { [int64]$cim.ReadTransferCount } else { $null }
        write_transfer_bytes = if ($cim) { [int64]$cim.WriteTransferCount } else { $null }
        other_transfer_bytes = if ($cim) { [int64]$cim.OtherTransferCount } else { $null }
        page_faults = if ($cim) { [int64]$cim.PageFaults } else { $null }
        user_mode_ticks = if ($cim) { [int64]$cim.UserModeTime } else { $null }
        kernel_mode_ticks = if ($cim) { [int64]$cim.KernelModeTime } else { $null }
    }
}

function Get-NetworkSnapshot {
    param([int[]]$OwningProcesses)

    $pidSet = @($OwningProcesses | Where-Object { $_ -gt 0 } | Select-Object -Unique)
    if (@($pidSet).Count -eq 0) {
        return [ordered]@{
            tcp = @()
            udp = @()
        }
    }

    $tcp = @()
    $udp = @()

    if (Get-Command 'Get-NetTCPConnection' -ErrorAction SilentlyContinue) {
        $tcp = @(
            Get-NetTCPConnection -ErrorAction SilentlyContinue |
                Where-Object { $pidSet -contains $_.OwningProcess } |
                ForEach-Object {
                    [ordered]@{
                        state = [string]$_.State
                        local_address = [string]$_.LocalAddress
                        local_port = [int]$_.LocalPort
                        remote_address = [string]$_.RemoteAddress
                        remote_port = [int]$_.RemotePort
                        owning_process = [int]$_.OwningProcess
                    }
                }
        )
    }

    if (Get-Command 'Get-NetUDPEndpoint' -ErrorAction SilentlyContinue) {
        $udp = @(
            Get-NetUDPEndpoint -ErrorAction SilentlyContinue |
                Where-Object { $pidSet -contains $_.OwningProcess } |
                ForEach-Object {
                    [ordered]@{
                        local_address = [string]$_.LocalAddress
                        local_port = [int]$_.LocalPort
                        owning_process = [int]$_.OwningProcess
                    }
                }
        )
    }

    return [ordered]@{
        tcp = $tcp
        udp = $udp
    }
}

function Get-DirectorySnapshot {
    param([string]$Path)

    if (-not $Path -or -not (Test-Path $Path)) {
        return [ordered]@{
            exists = $false
            file_count = 0
            total_bytes = 0
            files = @()
        }
    }

    $root = (Resolve-Path $Path).Path
    $files = @(
        Get-ChildItem -Path $root -Recurse -File -Force -ErrorAction SilentlyContinue |
            Sort-Object FullName |
            ForEach-Object {
                [ordered]@{
                    path = $_.FullName
                    relative_path = $_.FullName.Substring($root.Length).TrimStart('\')
                    length = [int64]$_.Length
                    last_write_time = $_.LastWriteTime.ToString('o')
                    extension = [string]$_.Extension
                }
            }
    )

    $totalBytes = 0
    foreach ($entry in $files) {
        $totalBytes += [int64]$entry.length
    }

    return [ordered]@{
        exists = $true
        root = $root
        file_count = @($files).Count
        total_bytes = [int64]$totalBytes
        files = $files
    }
}

function Get-ApiHealthSnapshot {
    param([string]$BaseUrl)

    if (-not $BaseUrl) {
        return [ordered]@{
            attempted = $false
        }
    }

    $healthUrl = "{0}/health" -f $BaseUrl.TrimEnd('/')
    $started = Get-Date
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
        $latencyMs = ((Get-Date) - $started).TotalMilliseconds
        return [ordered]@{
            attempted = $true
            ok = ($response.StatusCode -eq 200)
            status_code = [int]$response.StatusCode
            latency_ms = [math]::Round($latencyMs, 3)
            error = $null
        }
    }
    catch {
        $latencyMs = ((Get-Date) - $started).TotalMilliseconds
        return [ordered]@{
            attempted = $true
            ok = $false
            status_code = $null
            latency_ms = [math]::Round($latencyMs, 3)
            error = $_.Exception.Message
        }
    }
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$safeRunId = if ($RunId) { ($RunId -replace '[^A-Za-z0-9_.-]', '_') } else { 'unknown-run' }
if (-not $LogPath) {
    $LogPath = Join-Path 'kg/reports/runtime-watch' ("{0}-{1}.jsonl" -f $timestamp, $safeRunId)
}
if (-not $StatePath) {
    $StatePath = Join-Path 'kg/reports/runtime-watch' ("{0}-{1}.state.json" -f $timestamp, $safeRunId)
}

$sessionMetadata = [ordered]@{
    schema_version = 'benchmark-runtime-watch-session.v1'
    started_at_utc = Get-UtcIsoNow
    host = $env:COMPUTERNAME
    user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    pwd = (Get-Location).Path
    benchmark_pid = $BenchmarkPid
    api_pid = $ApiPid
    run_id = $RunId
    out_dir = $OutDir
    api_state_path = $ApiStatePath
    api_base_url = $ApiBaseUrl
    sample_interval_seconds = $SampleIntervalSeconds
    max_samples = $MaxSamples
    stop_when_benchmark_exits = $StopWhenBenchmarkExits
}

Append-JsonLine -Path $LogPath -Payload ([ordered]@{
    schema_version = 'benchmark-runtime-watch.v1'
    ts_utc = Get-UtcIsoNow
    ts_local = (Get-Date).ToString('o')
    event = 'watch_started'
    session = $sessionMetadata
})

$sampleIndex = 0
while ($true) {
    $apiState = Read-ApiState -Path $ApiStatePath
    if (($ApiPid -le 0) -and $apiState -and ($apiState.PSObject.Properties.Name -contains 'pid')) {
        try {
            $ApiPid = [int]$apiState.pid
        }
        catch {
        }
    }

    $benchmarkTree = @(Get-ProcessTreeIds -RootProcessId $BenchmarkPid)
    $apiTree = @(Get-ProcessTreeIds -RootProcessId $ApiPid)
    $allPids = @($benchmarkTree + $apiTree | Where-Object { $_ -gt 0 } | Select-Object -Unique)
    $processSnapshots = @($allPids | ForEach-Object { Get-ProcessSnapshot -ProcessId $_ })
    $network = Get-NetworkSnapshot -OwningProcesses $allPids
    $directorySnapshot = Get-DirectorySnapshot -Path $OutDir
    $health = Get-ApiHealthSnapshot -BaseUrl $ApiBaseUrl

    $snapshot = [ordered]@{
        schema_version = 'benchmark-runtime-watch.v1'
        ts_utc = Get-UtcIsoNow
        ts_local = (Get-Date).ToString('o')
        event = 'sample'
        sample_index = $sampleIndex
        run_id = $RunId
        benchmark_pid = $BenchmarkPid
        benchmark_tree = $benchmarkTree
        benchmark_root_exists = @($benchmarkTree).Count -gt 0
        api_pid = $ApiPid
        api_tree = $apiTree
        api_root_exists = @($apiTree).Count -gt 0
        api_state = $apiState
        processes = $processSnapshots
        network = $network
        api_health = $health
        out_dir_snapshot = $directorySnapshot
    }

    Append-JsonLine -Path $LogPath -Payload $snapshot
    Write-JsonState -Path $StatePath -Payload $snapshot

    if ($StopWhenBenchmarkExits -and $BenchmarkPid -gt 0 -and @($benchmarkTree).Count -eq 0) {
        Append-JsonLine -Path $LogPath -Payload ([ordered]@{
            schema_version = 'benchmark-runtime-watch.v1'
            ts_utc = Get-UtcIsoNow
            ts_local = (Get-Date).ToString('o')
            event = 'watch_stopped'
            reason = 'benchmark_exited'
            benchmark_pid = $BenchmarkPid
            run_id = $RunId
        })
        break
    }

    $sampleIndex += 1
    if ($MaxSamples -gt 0 -and $sampleIndex -ge $MaxSamples) {
        Append-JsonLine -Path $LogPath -Payload ([ordered]@{
            schema_version = 'benchmark-runtime-watch.v1'
            ts_utc = Get-UtcIsoNow
            ts_local = (Get-Date).ToString('o')
            event = 'watch_stopped'
            reason = 'max_samples_reached'
            benchmark_pid = $BenchmarkPid
            run_id = $RunId
            max_samples = $MaxSamples
        })
        break
    }

    Start-Sleep -Seconds ([Math]::Max(1, $SampleIntervalSeconds))
}
