$ErrorActionPreference = 'Stop'
$pidFile = Join-Path -Path 'kg/reports' -ChildPath 'api.pid'
if (-not (Test-Path $pidFile)) {
    Write-Host "API facade is not running (PID file missing: $pidFile)"
    return
}
$apiPid = Get-Content $pidFile | Select-Object -First 1
if ($apiPid) {
    try {
        $pidValue = [int]$apiPid
        Stop-Process -Id $pidValue -Force -ErrorAction Stop
        Write-Host "Stopped API process $pidValue"
    } catch {
        $message = $_.Exception.Message
        if ($message -match 'Cannot find a process') {
            Write-Host ("API process {0} was not running; removing stale PID file." -f $apiPid)
        } else {
            Write-Warning ("Unable to stop process {0}: {1}" -f $apiPid, $message)
            throw
        }
    }
}
Remove-Item $pidFile -ErrorAction SilentlyContinue
