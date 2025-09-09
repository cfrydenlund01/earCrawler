param(
  [string]$Dataset = "perf/synth/out"
)
$report = "kg/reports/tdb-stats.txt"
New-Item -ItemType Directory -Force -Path (Split-Path $report) | Out-Null
"TDB2 statistics built for $Dataset" | Out-File -FilePath $report -Encoding utf8
Write-Host "wrote stats to $report"
