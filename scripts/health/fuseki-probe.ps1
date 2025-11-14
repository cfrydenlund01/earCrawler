[CmdletBinding()]
param(
    [string]$FusekiUrl = $env:EARCRAWLER_FUSEKI_URL,
    [string]$ConfigPath = 'service/config/observability.yml',
    [string]$ReportPath = 'kg/reports/health-fuseki.txt'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$yamlLib = Join-Path $PSScriptRoot '../lib/import_yaml.ps1' | Resolve-Path
. $yamlLib

if (-not $FusekiUrl) {
    throw 'Fuseki endpoint URL is required. Set EARCRAWLER_FUSEKI_URL or pass -FusekiUrl.'
}

if (-not (Test-Path $ConfigPath)) {
    throw "Observability config not found at $ConfigPath"
}

$cfg = Import-YamlDocument -Path $ConfigPath
$budgets = $cfg.health
$pingBudget = [int]$budgets.fuseki_ping_ms
$selectBudget = [int]$budgets.fuseki_select_ms

$reportLines = @()
$reportLines += "Fuseki endpoint: $FusekiUrl"

$pingUri = ($FusekiUrl.TrimEnd('/') + '/$/ping')
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$pingOk = $false
try {
    $pingResponse = Invoke-WebRequest -Uri $pingUri -UseBasicParsing -TimeoutSec ([Math]::Ceiling($pingBudget / 1000.0))
    $sw.Stop()
    $pingMs = [math]::Round($sw.Elapsed.TotalMilliseconds, 2)
    $pingOk = ($pingResponse.StatusCode -eq 200) -and ($pingMs -le $pingBudget)
    $reportLines += "Ping latency: $pingMs ms (budget $pingBudget ms)"
    $reportLines += "Ping status: $($pingResponse.StatusCode)"
} catch {
    $sw.Stop()
    $pingMs = [math]::Round($sw.Elapsed.TotalMilliseconds, 2)
    $reportLines += "Ping error: $($_.Exception.Message)"
}

$query = 'SELECT (1 AS ?ok) WHERE { } LIMIT 1'
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$selectOk = $false
try {
$selectResponse = Invoke-WebRequest -Uri $FusekiUrl -UseBasicParsing -TimeoutSec ([Math]::Ceiling($selectBudget / 1000.0)) -Method Post -Body $query -ContentType 'application/sparql-query'
$sw.Stop()
$selectMs = [math]::Round($sw.Elapsed.TotalMilliseconds, 2)
$reportLines += "Select latency: $selectMs ms (budget $selectBudget ms)"
$selectOk = ($selectResponse.StatusCode -eq 200) -and ($selectMs -le $selectBudget)
try {
    $raw = $selectResponse.Content
    if ($raw -is [byte[]]) {
        $raw = [System.Text.Encoding]::UTF8.GetString($raw)
    }
    $json = $raw | ConvertFrom-Json
    $rows = ($json.results.bindings | Measure-Object).Count
    $reportLines += "Rows returned: $rows"
    if ($rows -lt 0) { $selectOk = $false }
} catch {
    $reportLines += "Failed to parse select response: $($_.Exception.Message)"
        $selectOk = $false
    }
} catch {
    $sw.Stop()
    $selectMs = [math]::Round($sw.Elapsed.TotalMilliseconds, 2)
    $reportLines += "Select error: $($_.Exception.Message)"
}

$overall = $pingOk -and $selectOk
$reportLines += "Overall: $(if ($overall) { 'pass' } else { 'fail' })"

$reportDir = Split-Path -Parent $ReportPath
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$reportLines | Out-File -FilePath $ReportPath -Encoding utf8

if (-not $overall) {
    exit 1
}
