$ErrorActionPreference = 'Stop'
$pidFile = Join-Path -Path 'kg/reports' -ChildPath 'api.pid'
if (-not (Test-Path $pidFile)) {
    Write-Warning "PID file not found: $pidFile"
    return
}
$pid = Get-Content $pidFile | Select-Object -First 1
if ($pid) {
    try {
        Stop-Process -Id [int]$pid -Force -ErrorAction Stop
        Write-Host "Stopped API process $pid"
    } catch {
        Write-Warning "Unable to stop process $pid: $_"
    }
}
Remove-Item $pidFile -ErrorAction SilentlyContinue
