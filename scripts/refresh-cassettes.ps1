param(
    [string]$WatchlistPath = 'monitor/watchlist.json'
)

if ($Env:ALLOW_RECORD -ne '1') {
    Write-Host 'Recording disabled.'
    exit 0
}
$python = 'python'
$watch = Get-Content $WatchlistPath -Raw | ConvertFrom-Json
foreach ($w in $watch.tradegov) {
    $Env:VCR_RECORD_MODE = 'once'
    & $python earCrawler/cli/fetch_tradegov.py $w.query --limit 1 > $null
    $Env:VCR_RECORD_MODE = 'none'
    & $python earCrawler/cli/fetch_tradegov.py $w.query --limit 1 > $null
}
foreach ($w in $watch.federalregister) {
    $Env:VCR_RECORD_MODE = 'once'
    & $python earCrawler/cli/fetch_federalregister.py $w.term --per-page 1 > $null
    $Env:VCR_RECORD_MODE = 'none'
    & $python earCrawler/cli/fetch_federalregister.py $w.term --per-page 1 > $null
}
