$ErrorActionPreference = 'Stop'

python -m earCrawler.cli.reconcile_cmd run

$summaryPath = 'kg/reports/reconcile-summary.json'
if (!(Test-Path $summaryPath)) { throw 'summary missing' }
$summary = Get-Content $summaryPath | ConvertFrom-Json

$maxReview = [int]($env:MAX_REVIEW ? $env:MAX_REVIEW : 0)
if ($summary.counts.review -gt $maxReview) { throw "review count $($summary.counts.review) exceeds limit" }

'OK' | Set-Content 'kg/reports/reconcile-ci.txt'
