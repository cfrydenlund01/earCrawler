[CmdletBinding()]
param(
    [string]$Host = '127.0.0.1',
    [int]$Port = 9001,
    [string]$ConfigPath = 'service/config/observability.yml',
    [string]$ReportPath = 'kg/reports/health-api.txt'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$yamlLib = Join-Path $PSScriptRoot '../lib/import_yaml.ps1' | Resolve-Path
. $yamlLib

if (-not (Test-Path $ConfigPath)) {
    throw "Observability config not found at $ConfigPath"
}

$cfg = Import-YamlDocument -Path $ConfigPath
$budgets = $cfg.health
$apiBudget = [int]$budgets.api_timeout_ms

$baseUrl = "http://{0}:{1}" -f $Host, $Port
$report = @("API base URL: $baseUrl")

function Invoke-Probe($Uri, $Method = 'GET', $ExpectStatus = 200, $Body = $null) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        if ($Body) {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec ([Math]::Ceiling($apiBudget / 1000.0)) -Method $Method -Body $Body -ContentType 'application/json'
        } else {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec ([Math]::Ceiling($apiBudget / 1000.0)) -Method $Method
        }
    } catch {
        $sw.Stop()
        return [PSCustomObject]@{
            StatusCode = 0
            DurationMs = [math]::Round($sw.Elapsed.TotalMilliseconds, 2)
            Error = $_.Exception.Message
            Body = $null
        }
    }
    $sw.Stop()
    $content = $null
    if ($response.Content) {
        try {
            $content = $response.Content | ConvertFrom-Json -ErrorAction Stop
        } catch {
            $content = $null
        }
    }
    return [PSCustomObject]@{
        StatusCode = $response.StatusCode
        DurationMs = [math]::Round($sw.Elapsed.TotalMilliseconds, 2)
        Error = $null
        Body = $content
        Headers = $response.Headers
    }
}

$healthUri = "$baseUrl/health"
$health = Invoke-Probe -Uri $healthUri
$report += "Health status: $($health.StatusCode) in $($health.DurationMs) ms"
if ($health.Error) { $report += "Health error: $($health.Error)" }
$ready = $false
if ($health.Body -and $health.Body.readiness) {
    $ready = ($health.Body.readiness.status -eq 'pass')
}

$searchUri = "$baseUrl/v1/search?q=health&limit=1"
$search = Invoke-Probe -Uri $searchUri
$report += "Search status: $($search.StatusCode) in $($search.DurationMs) ms"
if ($search.Error) { $report += "Search error: $($search.Error)" }
$rows = 0
if ($search.Body -and $search.Body.results) {
    $rows = ($search.Body.results | Measure-Object).Count
}
$headersOk = $false
if ($search.Headers) {
    $headersOk = $search.Headers['X-Request-Id'] -and $search.Headers['X-RateLimit-Limit']
}

$overall = ($health.StatusCode -eq 200) -and $ready -and ($search.StatusCode -eq 200) -and ($search.DurationMs -le $apiBudget) -and $headersOk
$report += "Results returned: $rows"
$report += "Headers OK: $(if ($headersOk) { 'yes' } else { 'no' })"
$report += "Overall: $(if ($overall) { 'pass' } else { 'fail' })"

$reportDir = Split-Path -Parent $ReportPath
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$report | Out-File -FilePath $ReportPath -Encoding utf8

if (-not $overall) {
    exit 1
}
