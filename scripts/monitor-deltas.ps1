param(
    [string]$WatchlistPath = 'monitor/watchlist.json',
    [string]$StatePath = 'monitor/state.json'
)

$ErrorActionPreference = 'Stop'
$python = 'python'
$watch = Get-Content $WatchlistPath -Raw | ConvertFrom-Json
$items = @{}
foreach ($w in $watch.tradegov) {
    $raw = & $python earCrawler/cli/fetch_tradegov.py $w.query --limit 1
    $items[$w.id] = ($raw | ConvertFrom-Json)
}
foreach ($w in $watch.federalregister) {
    $raw = & $python earCrawler/cli/fetch_federalregister.py $w.term --per-page 1
    $items[$w.term] = ($raw | ConvertFrom-Json)
}
$jsonItems = $items | ConvertTo-Json -Depth 5
$py = @'
import json, sys
from pathlib import Path
from earCrawler.monitor.state import update_state_and_write_delta
items = json.loads(sys.stdin.read())
update_state_and_write_delta(items, Path(sys.argv[1]), Path('monitor'))
'@
$jsonItems | & $python -c $py $StatePath
