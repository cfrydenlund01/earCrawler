param(
    [string]$Path = $(Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$bundleRoot = (Resolve-Path $Path).Path
$pidFile = Join-Path $bundleRoot 'fuseki/server.pid'
if (-not (Test-Path $pidFile)) {
    Write-Warning 'Fuseki PID file not found; server may not be running.'
    return
}
$pidText = (Get-Content -Path $pidFile -Raw).Trim()
$pidValue = 0
if (-not [int]::TryParse($pidText, [ref]$pidValue)) {
    Remove-Item -Path $pidFile -Force
    throw "Invalid PID value: $pidText"
}
$fusekiPid = $pidValue
try {
    $proc = Get-Process -Id $fusekiPid -ErrorAction Stop
    Stop-Process -Id $fusekiPid -ErrorAction Stop
    $proc.WaitForExit()
} catch {
    Write-Warning "Process $fusekiPid not running"
}
Remove-Item -Path $pidFile -Force
Write-Host "Fuseki stopped"
