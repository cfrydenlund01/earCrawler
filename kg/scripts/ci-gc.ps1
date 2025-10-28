$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path "$PSScriptRoot/../.."
Set-Location $repoRoot
New-Item -ItemType Directory -Force -Path 'kg/reports' | Out-Null
function Resolve-KgPython {
    if ($env:EARCTL_PYTHON) { return $env:EARCTL_PYTHON }
    if (Get-Command py -ErrorAction SilentlyContinue) { return 'py' }
    if (Get-Command python -ErrorAction SilentlyContinue) { return 'python' }
    throw 'Python interpreter not found. Set EARCTL_PYTHON or ensure py/python is on PATH.'
}
$python = Resolve-KgPython
$args = @('-m','earCrawler.cli','gc','--dry-run','--target','all')
& $python @args | Out-Null
if (-not (Test-Path 'kg/reports/gc-report.json')) {
    Write-Error 'gc-report.json missing'
}
$report = Get-Content 'kg/reports/gc-report.json' | ConvertFrom-Json
if ($report.errors.Count -gt 0) {
    Write-Error "GC errors: $($report.errors -join ', ')"
}
$allowed = @(
    (Resolve-Path 'kg').Path,
    (Resolve-Path '.cache/api').Path,
    "$Env:APPDATA\EarCrawler\spool",
    "$Env:PROGRAMDATA\EarCrawler\spool"
)
foreach ($cand in $report.candidates) {
    $p = [System.IO.Path]::GetFullPath($cand.path)
    $ok = $false
    foreach ($root in $allowed) {
        if ($p.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
            $ok = $true
            break
        }
    }
    if (-not $ok) {
        Write-Error "Path outside whitelist: $($cand.path)"
    }
}
