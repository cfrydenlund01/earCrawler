[CmdletBinding()]
param(
    [string]$ConfigPath = 'canary/config.yml',
    [string]$ReportDir = 'kg/reports'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$yamlLib = Join-Path $PSScriptRoot '../lib/import_yaml.ps1' | Resolve-Path
. $yamlLib

if (-not (Test-Path $ConfigPath)) {
    throw "Canary config not found at $ConfigPath"
}

$cfg = Import-YamlDocument -Path $ConfigPath
$results = New-Object System.Collections.Generic.List[object]

function Add-CanaryResult([string]$Name, [string]$Kind, [int]$StatusCode, [double]$Latency, [int]$Rows, [string]$Message, [bool]$Ok) {
    $results.Add([PSCustomObject]@{
        name = $Name
        type = $Kind
        status = if ($Ok) { 'pass' } else { 'fail' }
        latency_ms = [math]::Round($Latency, 2)
        status_code = $StatusCode
        rows = $Rows
        message = $Message
    })
}

if ($cfg.api) {
    $baseUrl = $cfg.api.base_url.TrimEnd('/')
    foreach ($check in $cfg.api.checks) {
        $uri = $baseUrl + $check.path
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $status = 0
        $rows = 0
        $message = 'within budget'
        $ok = $false
        try {
            $resp = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 5
            $sw.Stop()
            $status = $resp.StatusCode
            $lat = $sw.Elapsed.TotalMilliseconds
            $body = $null
            if ($resp.Content) {
                try { $body = $resp.Content | ConvertFrom-Json } catch { $body = $null }
            }
            if ($body -and $body.results) {
                $rows = ($body.results | Measure-Object).Count
            } elseif ($body -and $body.total) {
                $rows = [int]$body.total
            }
            $ok = ($status -eq $check.expect_status) -and ($lat -le $check.max_latency_ms) -and ($rows -ge $check.min_results)
            if (-not $ok) {
                $message = "status $status, latency $([math]::Round($lat,2)) ms, rows $rows"
            }
            Add-CanaryResult $check.name 'api' $status $lat $rows $message $ok
        } catch {
            $sw.Stop()
            $lat = $sw.Elapsed.TotalMilliseconds
            $message = $_.Exception.Message
            Add-CanaryResult $check.name 'api' 0 $lat 0 $message $false
        }
    }
}

if ($cfg.fuseki) {
    $endpoint = $cfg.fuseki.endpoint
    foreach ($check in $cfg.fuseki.checks) {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $rows = 0
        $status = 0
        $message = 'within budget'
        $ok = $false
        try {
            $resp = Invoke-WebRequest -Uri $endpoint -UseBasicParsing -TimeoutSec 5 -Method Post -Body $check.query -ContentType 'application/sparql-query'
            $sw.Stop()
            $status = $resp.StatusCode
            $lat = $sw.Elapsed.TotalMilliseconds
            if ($resp.Content) {
                try {
                    $json = $resp.Content | ConvertFrom-Json
                    $rows = ($json.results.bindings | Measure-Object).Count
                } catch {
                    $message = $_.Exception.Message
                }
            }
            $ok = ($status -eq 200) -and ($lat -le $check.max_latency_ms) -and ($rows -ge $check.expect_rows)
            if (-not $ok) {
                $message = "status $status, latency $([math]::Round($lat,2)) ms, rows $rows"
            }
            Add-CanaryResult $check.name 'fuseki' $status $lat $rows $message $ok
        } catch {
            $sw.Stop()
            $lat = $sw.Elapsed.TotalMilliseconds
            $message = $_.Exception.Message
            Add-CanaryResult $check.name 'fuseki' 0 $lat 0 $message $false
        }
    }
}

$reportDirPath = Resolve-Path -Path $ReportDir -ErrorAction SilentlyContinue
if (-not $reportDirPath) {
    New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
    $reportDirPath = Resolve-Path -Path $ReportDir
}

$summary = [PSCustomObject]@{
    timestamp = (Get-Date).ToString('o')
    results = $results
}

$summaryPath = Join-Path $reportDirPath 'canary-summary.json'
$summary | ConvertTo-Json -Depth 4 | Out-File -FilePath $summaryPath -Encoding utf8

$textPath = Join-Path $reportDirPath 'canary-summary.txt'
$lines = @()
foreach ($result in $results) {
    $lines += "[$($result.type)] $($result.name): $($result.status) ($($result.latency_ms) ms)"
    if ($result.status -eq 'fail') {
        $lines += "  -> $($result.message)"
    }
}
$lines | Out-File -FilePath $textPath -Encoding utf8

if ($results | Where-Object { $_.status -eq 'fail' }) {
    exit 1
}
