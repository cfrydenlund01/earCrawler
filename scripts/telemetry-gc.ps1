param([string]$Spool)
if (-not $Spool) {
  $cfgPath = Join-Path $env:APPDATA 'EarCrawler/telemetry.json'
  if (Test-Path $cfgPath) {
    $cfg = Get-Content $cfgPath | ConvertFrom-Json
    $Spool = $cfg.spool_dir
  } else {
    exit 0
  }
}
if (-not (Test-Path $Spool)) { exit 0 }
Get-ChildItem $Spool -Filter 'events-*.jsonl.gz' | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } | Remove-Item -ErrorAction SilentlyContinue
