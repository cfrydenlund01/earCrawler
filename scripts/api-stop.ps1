param(
    [int]$Port = 0,
    [string]$LifecycleReportPath = ''
)

$ErrorActionPreference = 'Stop'
$pidFile = Join-Path -Path 'kg/reports' -ChildPath 'api.pid'
$stateFile = Join-Path -Path 'kg/reports' -ChildPath 'api.process.json'
$defaultLifecycleReportPath = Join-Path -Path 'kg/reports' -ChildPath 'api-stop.last.json'
$lifecyclePaths = @($defaultLifecycleReportPath)
if ($LifecycleReportPath) {
    $lifecyclePaths += $LifecycleReportPath
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
        } catch {
            Write-Warning ("Unable to stop {0} process {1}: {2}" -f $Label, $targetId, $_.Exception.Message)
        }
    }
}

function Get-ListeningPortOwners {
    param([int]$LocalPort)

    $netTcpCommand = Get-Command 'Get-NetTCPConnection' -ErrorAction SilentlyContinue
    if (-not $netTcpCommand) {
        return @()
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
        $owners.Add([ordered]@{
            pid = $pidValue
            process_name = $processName
            command_line = $commandLine
        })
    }
    return @($owners | Sort-Object -Property pid)
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
    } catch {
        return $null
    }
}

function Read-ManagedApiState {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return $null
    }
    try {
        return Get-Content -Path $Path -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Test-IsRecoverableApiPortOwner {
    param([string]$CommandLine)

    if (-not $CommandLine) {
        return $false
    }

    return [bool]($CommandLine -match 'service\.api_server\.server:app')
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

function Remove-ApiStateArtifacts {
    param(
        [string]$PidPath,
        [string]$StatePath
    )
    Remove-Item -Path $PidPath -ErrorAction SilentlyContinue
    Remove-Item -Path $StatePath -ErrorAction SilentlyContinue
}

$state = Read-ManagedApiState -Path $stateFile
$legacyPid = Read-LegacyPidValue -Path $pidFile
$portValue = $null
if ($Port -gt 0) {
    $portValue = [int]$Port
}
elseif ($state -and $state.PSObject.Properties.Name -contains 'port') {
    try {
        $portValue = [int]$state.port
    } catch {
        $portValue = $null
    }
}

$lifecycle = [ordered]@{
    schema_version = 'api-stop-lifecycle.v1'
    generated_utc = (Get-Date).ToUniversalTime().ToString('o')
    pid_file = $pidFile
    state_file = $stateFile
    status = 'pending'
    requested_port = if ($portValue) { $portValue } else { 0 }
    candidate_pids = @()
    stopped_pids = @()
    remaining_port_owners = @()
    error = ''
}

$candidatePids = New-Object System.Collections.Generic.List[int]
if ($legacyPid) {
    [void]$candidatePids.Add([int]$legacyPid)
}
if ($state -and ($state.PSObject.Properties.Name -contains 'pid')) {
    try {
        [void]$candidatePids.Add([int]$state.pid)
    } catch {
    }
}
$targetPids = @($candidatePids | Select-Object -Unique)
$lifecycle.candidate_pids = @($targetPids)

if (
    @($targetPids).Count -eq 0 `
    -and -not (Test-Path $pidFile) `
    -and -not (Test-Path $stateFile) `
    -and -not $portValue
) {
    $lifecycle.status = 'not_running'
    Write-Host "API facade is not running (no managed PID or state files found)."
    Write-ApiLifecycleReport -Payload $lifecycle -OutputPaths $lifecyclePaths
    return
}

foreach ($targetPid in $targetPids) {
    $proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
    if ($null -eq $proc) {
        continue
    }
    Stop-ProcessTree -RootProcessId $targetPid -Label 'managed API'
    $lifecycle.stopped_pids += [int]$targetPid
}

Remove-ApiStateArtifacts -PidPath $pidFile -StatePath $stateFile

if ($portValue) {
    $owners = Get-ListeningPortOwners -LocalPort $portValue
    $recoverablePortOwners = @(
        $owners | Where-Object {
            Test-IsRecoverableApiPortOwner -CommandLine ([string]$_.command_line)
        }
    )
    foreach ($owner in $recoverablePortOwners) {
        $ownerPid = [int]$owner.pid
        Stop-ProcessTree -RootProcessId $ownerPid -Label 'recoverable API port owner'
        if ($lifecycle.stopped_pids -notcontains $ownerPid) {
            $lifecycle.stopped_pids += $ownerPid
        }
    }
    if (@($recoverablePortOwners).Count -gt 0) {
        $deadline = (Get-Date).AddSeconds(10)
        do {
            $owners = Get-ListeningPortOwners -LocalPort $portValue
            if (@($owners).Count -eq 0) {
                break
            }
            Start-Sleep -Milliseconds 300
        } while ((Get-Date) -lt $deadline)
    }
    $lifecycle.remaining_port_owners = @($owners)
}

if (@($lifecycle.remaining_port_owners).Count -gt 0) {
    $lifecycle.status = 'port_still_occupied'
    $ownerSummary = @($lifecycle.remaining_port_owners | ForEach-Object { "pid=$($_.pid) process=$($_.process_name)" }) -join '; '
    $lifecycle.error = "Port $portValue is still occupied after API stop. $ownerSummary"
    Write-ApiLifecycleReport -Payload $lifecycle -OutputPaths $lifecyclePaths
    throw "API stop completed for managed process ids, but port $portValue remains occupied. $ownerSummary"
}

$lifecycle.status = if (@($lifecycle.stopped_pids).Count -gt 0) { 'stopped' } else { 'stale_state_removed' }
Write-ApiLifecycleReport -Payload $lifecycle -OutputPaths $lifecyclePaths

if (@($lifecycle.stopped_pids).Count -gt 0) {
    Write-Host ("Stopped API process ids: {0}" -f (($lifecycle.stopped_pids -join ', ')))
} else {
    Write-Host "Removed stale API state files; no running managed API process was found."
}
