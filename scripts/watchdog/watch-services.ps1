[CmdletBinding()]
param(
    [string]$ReportDir = 'kg/reports',
    [string]$ApiPidPath = 'kg/reports/api.pid',
    [string]$FusekiPidPath = 'kg/reports/fuseki.pid'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ProcessStatus([string]$PidPath) {
    if (-not (Test-Path $PidPath)) { return $false }
    $pid = Get-Content $PidPath -ErrorAction Stop | Select-Object -First 1
    if (-not $pid) { return $false }
    try {
        $proc = Get-Process -Id ([int]$pid) -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Read-Tail([string]$Path, [int]$Lines = 40) {
    if (-not (Test-Path $Path)) { return @() }
    return Get-Content -Path $Path -Tail $Lines -ErrorAction SilentlyContinue
}

$processes = @{}
$processes.api = @{
    running = (Get-ProcessStatus $ApiPidPath)
    log_tail = Read-Tail 'kg/reports/api.log'
    restart = @('pwsh','-File','scripts/api-start.ps1')
}
$processes.fuseki = @{
    running = (Get-ProcessStatus $FusekiPidPath)
    log_tail = Read-Tail 'kg/reports/fuseki.log'
    restart = @('pwsh','-File','kg/scripts/ci-roundtrip.ps1')
}

$payload = @{ processes = $processes; report_dir = $ReportDir } | ConvertTo-Json -Depth 6
$python = $env:EARCTL_PYTHON
if (-not $python) { $python = 'python' }
$script = @'
import json, sys
from pathlib import Path
from earCrawler.observability.watchdog import create_watchdog_plan

payload = json.loads(sys.stdin.read())
plan = create_watchdog_plan(payload["processes"], report_dir=Path(payload["report_dir"]))
print(json.dumps({"report_path": str(plan.report_path), "missing": plan.missing, "restart": plan.restart_commands}))
'@
$planJson = $payload | & $python -c $script
$plan = $planJson | ConvertFrom-Json

if ($plan.missing.Count -gt 0) {
    Write-Warning ("Watchdog detected offline services: {0}" -f ($plan.missing -join ', '))
    foreach ($cmd in $plan.restart) {
        if ($cmd.Length -gt 0) {
            Write-Host "Restarting with: $($cmd -join ' ')"
            try {
                if ($cmd.Length -gt 1) {
                    & $cmd[0] @($cmd[1..($cmd.Length-1)])
                } else {
                    & $cmd[0]
                }
            } catch {
                Write-Warning "Failed to execute restart command $($cmd -join ' '): $($_.Exception.Message)"
            }
        }
    }
    $eventScript = "from earCrawler.utils.eventlog import write_event_log; write_event_log('Watchdog restarted: {0}', level='ERROR')" -f (($plan.missing -join ', '))
    & $python -c $eventScript
}

Write-Host "Watchdog report: $($plan.report_path)"
