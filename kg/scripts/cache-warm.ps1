param(
  [string]$QuerySet = "perf/warmers/warm_queries.json",
  [string]$Endpoint = "http://localhost:3030/ds"
)
$warmers = Get-Content $QuerySet | ConvertFrom-Json
foreach ($w in $warmers) {
  for ($i = 0; $i -lt $w.repeat; $i++) {
    try {
      Invoke-WebRequest -Uri "$Endpoint?query=$(Get-Content $w.file -Raw)" -UseBasicParsing -TimeoutSec 30 | Out-Null
    } catch {
      Write-Warning "warm query failed: $($w.file)" }
    Start-Sleep -Milliseconds 100
  }
}
$report = "kg/reports/cache-warm.txt"
"cache warm complete" | Out-File -FilePath $report -Encoding utf8
