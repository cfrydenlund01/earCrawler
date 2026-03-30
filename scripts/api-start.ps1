param(
    [Alias('Host')]
    [string]$ApiHost = $env:EARCRAWLER_API_HOST,
    [int]$Port,
    [string]$FusekiUrl = $env:EARCRAWLER_FUSEKI_URL,
    [string]$LifecycleReportPath = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (-not $ApiHost) { $ApiHost = '127.0.0.1' }

if (-not $PSBoundParameters.ContainsKey('Port')) {
    if ($env:EARCRAWLER_API_PORT) {
        $Port = [int]$env:EARCRAWLER_API_PORT
    } else {
        $Port = 9001
    }
}

$env:EARCRAWLER_API_HOST = $ApiHost
$env:EARCRAWLER_API_PORT = $Port
if ($FusekiUrl) {
    $env:EARCRAWLER_FUSEKI_URL = $FusekiUrl
} else {
    Remove-Item Env:EARCRAWLER_FUSEKI_URL -ErrorAction SilentlyContinue
}
$env:EARCRAWLER_API_EMBEDDED_FIXTURE = '1'

function Resolve-EarPython {
    param()

    if ($env:EARCTL_PYTHON -and (Test-Path $env:EARCTL_PYTHON)) {
        return $env:EARCTL_PYTHON
    }

    foreach ($name in 'python', 'python.exe', 'python3', 'python3.exe') {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }

    $pyLauncher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $probe = & $pyLauncher.Source -3 -c "import sys; print(sys.executable)"
            if ($LASTEXITCODE -eq 0 -and $probe) {
                return $probe.Trim()
            }
        } catch {
        }
    }

    if ($env:VIRTUAL_ENV) {
        $candidate = Join-Path $env:VIRTUAL_ENV 'Scripts/python.exe'
        if (Test-Path $candidate) { return $candidate }
        $candidate = Join-Path $env:VIRTUAL_ENV 'bin/python3'
        if (Test-Path $candidate) { return $candidate }
    }

    throw 'Unable to locate a Python interpreter. Set EARCTL_PYTHON or ensure python is on PATH.'
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

function Stop-ProcessTree {
    param(
        [int]$RootProcessId,
        [string]$Label
    )

    if ($RootProcessId -le 0) {
        return
    }

    $queue = New-Object System.Collections.Generic.Queue[int]
    $visited = New-Object System.Collections.Generic.HashSet[int]
    $discovered = New-Object System.Collections.Generic.List[int]
    $queue.Enqueue($RootProcessId)

    while ($queue.Count -gt 0) {
        $candidateId = $queue.Dequeue()
        if (-not $visited.Add($candidateId)) {
            continue
        }
        [void]$discovered.Add($candidateId)
        foreach ($childId in (Get-ChildProcessIds -ParentProcessId $candidateId)) {
            if (-not $visited.Contains($childId)) {
                $queue.Enqueue([int]$childId)
            }
        }
    }

    $orderedIds = @($discovered.ToArray())
    [Array]::Reverse($orderedIds)
    foreach ($targetId in $orderedIds) {
        try {
            $proc = Get-Process -Id $targetId -ErrorAction SilentlyContinue
            if ($null -eq $proc) {
                continue
            }
            Stop-Process -Id $targetId -Force -ErrorAction Stop
        }
        catch {
            Write-Warning ("Unable to stop {0} process {1}: {2}" -f $Label, $targetId, $_.Exception.Message)
        }
    }
}

function Get-ListeningPortOwners {
    param([int]$LocalPort)

    $netTcpCommand = Get-Command 'Get-NetTCPConnection' -ErrorAction SilentlyContinue
    if (-not $netTcpCommand) {
        throw "Get-NetTCPConnection is unavailable; cannot validate port ownership for port $LocalPort."
    }

    $connections = Get-NetTCPConnection -State Listen -LocalPort $LocalPort -ErrorAction SilentlyContinue
    if ($null -eq $connections) {
        return @()
    }

    $owners = New-Object System.Collections.Generic.List[object]
    foreach ($group in ($connections | Group-Object -Property OwningProcess)) {
        $pidValue = [int]$group.Name
        $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        $processName = if ($proc) { [string]$proc.ProcessName } else { "" }
        $cim = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $pidValue) -ErrorAction SilentlyContinue
        $commandLine = if ($cim) { [string]$cim.CommandLine } else { "" }
        $localAddresses = @($group.Group | Select-Object -ExpandProperty LocalAddress -Unique)
        $owners.Add([ordered]@{
            pid = $pidValue
            process_name = $processName
            command_line = $commandLine
            local_addresses = $localAddresses
        })
    }

    return @($owners | Sort-Object -Property pid)
}

function Read-ManagedApiState {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return $null
    }

    try {
        return Get-Content -Path $Path -Raw | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Read-LegacyPidValue {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return $null
    }

    try {
        $raw = (Get-Content -Path $Path -ErrorAction Stop | Select-Object -First 1).Trim()
        if (-not $raw) {
            return $null
        }
        return [int]$raw
    }
    catch {
        return $null
    }
}

function Test-IsManagedApiOwner {
    param(
        [int]$PidValue,
        [object]$StatePayload,
        [Nullable[int]]$LegacyPid,
        [string]$CommandLine,
        [string]$RepoRootPath
    )

    if ($StatePayload -and ($StatePayload.schema_version -eq 'api-process-state.v1') -and ($StatePayload.owner -eq 'earcrawler_api_start')) {
        if ([string]$StatePayload.repo_root -eq $RepoRootPath -and [int]$StatePayload.pid -eq $PidValue) {
            return $true
        }
    }

    if ($LegacyPid.HasValue -and $LegacyPid.Value -eq $PidValue -and $CommandLine) {
        if ($CommandLine -match 'service\.api_server\.server:app') {
            return $true
        }
    }

    return $false
}

function Remove-ApiStateArtifacts {
    param(
        [string]$PidPath,
        [string]$StatePath
    )

    Remove-Item -Path $PidPath -ErrorAction SilentlyContinue
    Remove-Item -Path $StatePath -ErrorAction SilentlyContinue
}

function Write-ApiLifecycleReport {
    param(
        [Parameter(Mandatory = $true)]$Payload,
        [Parameter(Mandatory = $true)][string[]]$OutputPaths
    )

    $json = $Payload | ConvertTo-Json -Depth 8
    foreach ($path in $OutputPaths) {
        if (-not $path) {
            continue
        }
        $reportDir = Split-Path -Parent $path
        if ($reportDir) {
            New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
        }
        $json | Set-Content -Path $path -Encoding utf8
    }
}

$python = Resolve-EarPython
$pidFile = Join-Path -Path 'kg/reports' -ChildPath 'api.pid'
$stateFile = Join-Path -Path 'kg/reports' -ChildPath 'api.process.json'
$defaultLifecycleReportPath = Join-Path -Path 'kg/reports' -ChildPath 'api-start.last.json'
$lifecyclePaths = @($defaultLifecycleReportPath)
if ($LifecycleReportPath) {
    $lifecyclePaths += $LifecycleReportPath
}
New-Item -ItemType Directory -Force -Path (Split-Path $pidFile) | Out-Null

$healthUrl = "http://{0}:{1}/health" -f $ApiHost, $Port
$lifecycle = [ordered]@{
    schema_version = 'api-start-lifecycle.v1'
    generated_utc = (Get-Date).ToUniversalTime().ToString('o')
    host = $ApiHost
    port = $Port
    pid_file = $pidFile
    state_file = $stateFile
    preflight = [ordered]@{
        status = 'pending'
        occupied_port = $false
        owners = @()
        recovered_pids = @()
    }
    startup = [ordered]@{
        status = 'pending'
        pid = 0
        health_url = $healthUrl
    }
    overall_status = 'failed'
    error = ''
}

$managedState = Read-ManagedApiState -Path $stateFile
$legacyPid = Read-LegacyPidValue -Path $pidFile
$ownerRecords = Get-ListeningPortOwners -LocalPort $Port
$lifecycle.preflight.owners = @($ownerRecords)
$managedRecoveryPids = @()

if (@($ownerRecords).Count -gt 0) {
    $lifecycle.preflight.occupied_port = $true
    $managedOwners = @()
    $foreignOwners = @()

    foreach ($ownerRecord in $ownerRecords) {
        if (Test-IsManagedApiOwner -PidValue ([int]$ownerRecord.pid) -StatePayload $managedState -LegacyPid $legacyPid -CommandLine ([string]$ownerRecord.command_line) -RepoRootPath $repoRoot) {
            $managedOwners += $ownerRecord
        }
        else {
            $foreignOwners += $ownerRecord
        }
    }

    if (@($foreignOwners).Count -gt 0) {
        $lifecycle.preflight.status = 'foreign_conflict'
        $foreignSummary = @($foreignOwners | ForEach-Object {
            "pid=$($_.pid) process=$($_.process_name)"
        }) -join '; '
        $lifecycle.error = "Port $Port is already in use by a non-managed process. $foreignSummary"
        Write-ApiLifecycleReport -Payload $lifecycle -OutputPaths $lifecyclePaths
        throw "Refusing to start API on ${ApiHost}:$Port because the port is already in use by a non-managed process. $foreignSummary"
    }

    $lifecycle.preflight.status = 'managed_recovery'
    $managedRecoveryPids = @($managedOwners | ForEach-Object { [int]$_.pid })
    foreach ($managedPid in $managedRecoveryPids) {
        Stop-ProcessTree -RootProcessId $managedPid -Label 'managed API'
    }
    $lifecycle.preflight.recovered_pids = $managedRecoveryPids

    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $deadline) {
        if (@(Get-ListeningPortOwners -LocalPort $Port).Count -eq 0) {
            break
        }
        Start-Sleep -Milliseconds 300
    }
    $ownersAfterRecovery = Get-ListeningPortOwners -LocalPort $Port
    if (@($ownersAfterRecovery).Count -gt 0) {
        $lifecycle.error = "Managed recovery could not free port $Port."
        $lifecycle.preflight.owners = @($ownersAfterRecovery)
        Write-ApiLifecycleReport -Payload $lifecycle -OutputPaths $lifecyclePaths
        throw "Managed recovery could not free port $Port."
    }

    Remove-ApiStateArtifacts -PidPath $pidFile -StatePath $stateFile
}
else {
    $lifecycle.preflight.status = 'free'
}

Write-Host ("Starting EarCrawler API on {0}:{1}" -f $ApiHost, $Port)
$process = Start-Process -FilePath $python -ArgumentList '-m','uvicorn','service.api_server.server:app','--host',$ApiHost,'--port',$Port -PassThru -WindowStyle Hidden
$lifecycle.startup.pid = [int]$process.Id

try {
    $process.Id | Out-File -FilePath $pidFile -Encoding ascii
    $statePayload = [ordered]@{
        schema_version = 'api-process-state.v1'
        owner = 'earcrawler_api_start'
        repo_root = $repoRoot
        pid = [int]$process.Id
        host = $ApiHost
        port = $Port
        python_executable = $python
        started_utc = (Get-Date).ToUniversalTime().ToString('o')
        preflight_status = [string]$lifecycle.preflight.status
    }
    $statePayload | ConvertTo-Json -Depth 6 | Set-Content -Path $stateFile -Encoding utf8

    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        try {
            $res = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
            if ($res.StatusCode -eq 200) {
                $lifecycle.startup.status = 'healthy'
                $lifecycle.overall_status = 'passed'
                Write-ApiLifecycleReport -Payload $lifecycle -OutputPaths $lifecyclePaths
                Write-Host "API healthy"
                return
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }

    throw "API failed to start before deadline"
}
catch {
    $lifecycle.startup.status = 'failed'
    $lifecycle.error = $_.Exception.Message
    Stop-ProcessTree -RootProcessId $process.Id -Label 'API start failure cleanup'
    Remove-ApiStateArtifacts -PidPath $pidFile -StatePath $stateFile
    Write-ApiLifecycleReport -Payload $lifecycle -OutputPaths $lifecyclePaths
    throw
}
