$ErrorActionPreference = 'Stop'
$pidFile = Join-Path -Path 'kg/reports' -ChildPath 'api.pid'
if (-not (Test-Path $pidFile)) {
    Write-Warning "PID file not found: $pidFile"
    return
}
$apiPid = Get-Content $pidFile | Select-Object -First 1
if ($apiPid) {
    try {
        $pidValue = [int]$apiPid
        Stop-Process -Id $pidValue -Force -ErrorAction Stop
        Write-Host "Stopped API process $pidValue"
    } catch {
        $message = $_
        Write-Warning ("Unable to stop process {0}: {1}" -f $apiPid, $message)
    }
}
Remove-Item $pidFile -ErrorAction SilentlyContinue
