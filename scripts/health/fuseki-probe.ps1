[CmdletBinding()]
param(
    [string]$FusekiUrl = $env:EARCRAWLER_FUSEKI_URL,
    [string]$ConfigPath = 'service/config/observability.yml',
    [string]$ReportPath = 'kg/reports/health-fuseki.txt',
    [switch]$RequireTextQuery,
    [string]$TextQuery = '__earcrawler_text_probe__'
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

$endpointUri = [System.Uri]$FusekiUrl
$baseBuilder = [System.UriBuilder]::new($endpointUri)
$baseBuilder.Path = '/'
$baseBuilder.Query = ''
$baseUri = $baseBuilder.Uri

$pingBuilder = [System.UriBuilder]::new($baseUri)
$pingBuilder.Path = '$/ping'
$pingBuilder.Query = ''
$pingUri = $pingBuilder.Uri.AbsoluteUri

$cfg = Import-YamlDocument -Path $ConfigPath
$budgets = $cfg.health
$pingBudget = [int]$budgets.fuseki_ping_ms
$selectBudget = [int]$budgets.fuseki_select_ms

$reportLines = @()
$reportLines += "Fuseki endpoint: $FusekiUrl"
$reportLines += "Fuseki ping: $pingUri"

function Get-ListeningPortOwners {
    param([int]$LocalPort)

    $netTcpCommand = Get-Command 'Get-NetTCPConnection' -ErrorAction SilentlyContinue
    if (-not $netTcpCommand) {
        return @()
    }

    $connections = Get-NetTCPConnection -State Listen -LocalPort $LocalPort -ErrorAction SilentlyContinue
    if ($null -eq $connections) {
        return @()
    }

    $owners = New-Object System.Collections.Generic.List[object]
    foreach ($group in ($connections | Group-Object -Property OwningProcess)) {
        $pidValue = [int]$group.Name
        $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        $owners.Add([ordered]@{
            pid = $pidValue
            process_name = if ($proc) { [string]$proc.ProcessName } else { "" }
        })
    }

    return @($owners | Sort-Object -Property pid)
}

$listeners = Get-ListeningPortOwners -LocalPort $endpointUri.Port
$listenerSummary = @($listeners | ForEach-Object { "pid=$($_.pid) process=$($_.process_name)" }) -join "; "
if ($listenerSummary) {
    $reportLines += "Listener owners: $listenerSummary"
} else {
    $reportLines += "Listener owners: none detected"
}

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
    $reportLines += "Ping error: $($_.Exception.Message)"
}

$query = 'SELECT (1 AS ?ok) WHERE { } LIMIT 1'
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$selectOk = $false
try {
    $selectResponse = Invoke-WebRequest `
        -Uri $endpointUri.AbsoluteUri `
        -UseBasicParsing `
        -TimeoutSec ([Math]::Ceiling($selectBudget / 1000.0)) `
        -Method Post `
        -Body $query `
        -ContentType 'application/sparql-query' `
        -Headers @{ Accept = 'application/sparql-results+json' }
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
        if ($rows -lt 0) {
            $selectOk = $false
        }
    } catch {
        $reportLines += "Failed to parse select response: $($_.Exception.Message)"
        $selectOk = $false
    }
} catch {
    $sw.Stop()
    $reportLines += "Select error: $($_.Exception.Message)"
}

if ($RequireTextQuery) {
    $textQuerySparql = @"
PREFIX text: <http://jena.apache.org/text#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT (COUNT(*) AS ?count)
WHERE {
  (?entity ?score ?snippet) text:query (rdfs:label "$TextQuery") .
}
"@

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $textOk = $false
    try {
        $textResponse = Invoke-WebRequest `
            -Uri $endpointUri.AbsoluteUri `
            -UseBasicParsing `
            -TimeoutSec ([Math]::Ceiling($selectBudget / 1000.0)) `
            -Method Post `
            -Body $textQuerySparql `
            -ContentType 'application/sparql-query' `
            -Headers @{ Accept = 'application/sparql-results+json' }
        $sw.Stop()
        $textMs = [math]::Round($sw.Elapsed.TotalMilliseconds, 2)
        $reportLines += "Text-query latency: $textMs ms (budget $selectBudget ms)"
        $reportLines += "Text-query status: $($textResponse.StatusCode)"
        try {
            $raw = $textResponse.Content
            if ($raw -is [byte[]]) {
                $raw = [System.Text.Encoding]::UTF8.GetString($raw)
            }
            $json = $raw | ConvertFrom-Json
            $bindings = @($json.results.bindings)
            $countValue = $null
            if ($bindings.Count -gt 0 -and $bindings[0].PSObject.Properties.Name -contains 'count') {
                $countValue = $bindings[0].count.value
            }
            $reportLines += "Text-query count: $countValue"
            $textOk = ($textResponse.StatusCode -eq 200) -and ($textMs -le $selectBudget)
        } catch {
            $reportLines += "Failed to parse text-query response: $($_.Exception.Message)"
        }
    } catch {
        $sw.Stop()
        $reportLines += "Text-query error: $($_.Exception.Message)"
    }
}
else {
    $textOk = $true
}

$overall = $pingOk -and $selectOk -and $textOk
$reportLines += "Overall: $(if ($overall) { 'pass' } else { 'fail' })"

$reportDir = Split-Path -Parent $ReportPath
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$reportLines | Out-File -FilePath $ReportPath -Encoding utf8

if (-not $overall) {
    exit 1
}
