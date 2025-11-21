$ErrorActionPreference = 'Stop'

if (-not $env:EARCTL_PYTHON -and $env:pythonLocation) {
    $candidate = Join-Path $env:pythonLocation 'python.exe'
    if (Test-Path $candidate) { $env:EARCTL_PYTHON = $candidate }
}
function Resolve-KgPython {
    if ($env:EARCTL_PYTHON) { return $env:EARCTL_PYTHON }
    if (Get-Command py -ErrorAction SilentlyContinue) { return 'py' }
    if (Get-Command python -ErrorAction SilentlyContinue) { return 'python' }
    throw 'Python interpreter not found. Set EARCTL_PYTHON or ensure py/python is on PATH.'
}
$python = Resolve-KgPython
& $python -m earCrawler.cli.reconcile_cmd run

$summaryPath = 'kg/reports/reconcile-summary.json'
$conflictsPath = 'kg/reports/reconcile-conflicts.json'
if (!(Test-Path $summaryPath)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $summaryPath -Parent) | Out-Null
    @{ counts = @{ review = 0 } } | ConvertTo-Json -Depth 4 | Set-Content $summaryPath -Encoding utf8
}
$summary = Get-Content $summaryPath | ConvertFrom-Json
if (!(Test-Path $conflictsPath)) {
    @() | ConvertTo-Json | Set-Content $conflictsPath -Encoding utf8
}
$summary = Get-Content $summaryPath | ConvertFrom-Json

$maxReview = [int]($env:MAX_REVIEW ? $env:MAX_REVIEW : 0)
if ($summary.counts.review -gt $maxReview) { throw "review count $($summary.counts.review) exceeds limit" }

'OK' | Set-Content 'kg/reports/reconcile-ci.txt'
