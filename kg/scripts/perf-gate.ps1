param(
  [string]$Report = 'kg/reports/perf-report.json',
  [string]$Baseline = 'perf/baselines/baseline_S.json',
  [string]$Budgets = 'perf/config/perf_budgets.yml',
  [string]$Scale = 'S'
)
$gateOut = 'kg/reports/perf-gate.txt'
python -m earCrawler.utils.perf_report gate --report $Report --baseline $Baseline --budgets $Budgets --scale $Scale --out $gateOut
if ($LASTEXITCODE -ne 0) {
  Write-Error "performance gate failed"; exit 1
}
Write-Host "performance gate passed"
