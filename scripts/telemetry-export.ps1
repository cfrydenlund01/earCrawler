param([int]$Last = 100)
$cfgPath = Join-Path $env:APPDATA 'EarCrawler/telemetry.json'
if (!(Test-Path $cfgPath)) { exit 1 }
$cfg = Get-Content $cfgPath | ConvertFrom-Json
$spool = $cfg.spool_dir
$out = 'dist/telemetry_bundle.jsonl.gz'
New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null
$events = Get-Content (Join-Path $spool 'current.jsonl') -ErrorAction SilentlyContinue | Select-Object -Last $Last
$events | Compress-Archive -DestinationPath $out -Force
Write-Output $out
