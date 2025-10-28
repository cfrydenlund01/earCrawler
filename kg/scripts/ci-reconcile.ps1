$ErrorActionPreference = 'Stop'

function Resolve-KgPython {
    if ($env:EARCTL_PYTHON) { return $env:EARCTL_PYTHON }
    if (Get-Command py -ErrorAction SilentlyContinue) { return 'py' }
    if (Get-Command python -ErrorAction SilentlyContinue) { return 'python' }
    throw 'Python interpreter not found. Set EARCTL_PYTHON or ensure py/python is on PATH.'
}
$python = Resolve-KgPython
& $python -m earCrawler.cli.reconcile_cmd run

$summaryPath = 'kg/reports/reconcile-summary.json'
if (!(Test-Path $summaryPath)) { throw 'summary missing' }
$summary = Get-Content $summaryPath | ConvertFrom-Json

$maxReview = [int]($env:MAX_REVIEW ? $env:MAX_REVIEW : 0)
if ($summary.counts.review -gt $maxReview) { throw "review count $($summary.counts.review) exceeds limit" }

'OK' | Set-Content 'kg/reports/reconcile-ci.txt'
