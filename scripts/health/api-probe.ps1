[CmdletBinding()]
param(
    [Alias('Host')]
    [string]$ApiHost = '127.0.0.1',
    [int]$Port = 9001,
    [string]$ConfigPath = 'service/config/observability.yml',
    [string]$ReportPath = 'kg/reports/health-api.txt',
    [string]$JsonReportPath = '',
    [switch]$IncludeQuarantinedSearch
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

$baseUrl = "http://{0}:{1}" -f $ApiHost, $Port
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

$healthUri = "$baseUrl/health"
$health = Invoke-Probe -Uri $healthUri
$report += "Health status: $($health.StatusCode) in $($health.DurationMs) ms"
if ($health.Error) { $report += "Health error: $($health.Error)" }
$ready = $false
if ($health.Body -and $health.Body.readiness) {
    $ready = ($health.Body.readiness.status -eq 'pass')
}
$healthBudgetOk = ($health.DurationMs -le $apiBudget)
$report += "Health budget OK: $(if ($healthBudgetOk) { 'yes' } else { 'no' })"
$listeners = Get-ListeningPortOwners -LocalPort $Port
$listenerPids = @($listeners | ForEach-Object { [int]$_.pid })
$report += "API listener PIDs: $(if ($listenerPids.Count -gt 0) { $listenerPids -join ', ' } else { 'none detected' })"

$overall = ($health.StatusCode -eq 200) -and $ready -and $healthBudgetOk

if ($IncludeQuarantinedSearch) {
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
    $overall = $overall -and ($search.StatusCode -eq 200) -and ($search.DurationMs -le $apiBudget) -and $headersOk
    $report += "Results returned: $rows"
    $report += "Headers OK: $(if ($headersOk) { 'yes' } else { 'no' })"
} else {
    $report += "Quarantined search probe: skipped (use -IncludeQuarantinedSearch for local validation)"
}

$report += "Overall: $(if ($overall) { 'pass' } else { 'fail' })"

$reportDir = Split-Path -Parent $ReportPath
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$report | Out-File -FilePath $ReportPath -Encoding utf8

if ($JsonReportPath) {
    $searchDetails = $null
    if ($IncludeQuarantinedSearch) {
        $searchRows = 0
        if ($search.Body -and $search.Body.results) {
            $searchRows = ($search.Body.results | Measure-Object).Count
        }
        $searchDetails = [ordered]@{
            included = $true
            status_code = [int]$search.StatusCode
            duration_ms = [double]$search.DurationMs
            headers_ok = $headersOk
            rows = $searchRows
            error = if ($search.Error) { [string]$search.Error } else { "" }
        }
    }
    else {
        $searchDetails = [ordered]@{
            included = $false
            status_code = 0
            duration_ms = 0.0
            headers_ok = $false
            rows = 0
            error = ""
        }
    }

    $jsonPayload = [ordered]@{
        schema_version = 'api-probe-report.v1'
        generated_utc = (Get-Date).ToUniversalTime().ToString("o")
        base_url = $baseUrl
        api_timeout_budget_ms = $apiBudget
        health = [ordered]@{
            status_code = [int]$health.StatusCode
            duration_ms = [double]$health.DurationMs
            readiness_pass = $ready
            budget_ok = $healthBudgetOk
            error = if ($health.Error) { [string]$health.Error } else { "" }
        }
        listeners = [ordered]@{
            port = $Port
            owners = @($listeners)
            detected = ([bool](@($listeners).Count -gt 0))
        }
        search = $searchDetails
        overall_status = if ($overall) { 'passed' } else { 'failed' }
    }

    $jsonReportDir = Split-Path -Parent $JsonReportPath
    if ($jsonReportDir) {
        New-Item -ItemType Directory -Force -Path $jsonReportDir | Out-Null
    }
    $jsonPayload | ConvertTo-Json -Depth 8 | Set-Content -Path $JsonReportPath -Encoding utf8
}

if (-not $overall) {
    exit 1
}
