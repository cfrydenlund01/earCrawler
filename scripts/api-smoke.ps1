param(
    [Alias('Host')]
    [string]$ApiHost = $env:EARCRAWLER_API_HOST ?? '127.0.0.1',
    [int]$Port = [int]($env:EARCRAWLER_API_PORT ?? 9001),
    [string]$EntityId = ($env:EAR_API_SMOKE_ENTITY_ID ?? 'urn:example:entity:1'),
    [string]$ReportPath = 'kg/reports/api-smoke.json',
    [string]$LegacyTextReportPath = 'kg/reports/api-smoke.txt'
)

$ErrorActionPreference = 'Stop'
$base = "http://{0}:{1}" -f $ApiHost, $Port
$encodedEntityId = [uri]::EscapeDataString($EntityId)

function Invoke-SmokeCheck {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Uri,
        [string]$Method = 'GET',
        [string]$Body = '',
        [string]$ContentType = 'application/json'
    )

    $headers = @{}
    if ($Body) {
        $headers['Content-Type'] = $ContentType
    }

    $response = if ($Body) {
        Invoke-WebRequest -Uri $Uri -Method $Method -Headers $headers -Body $Body -UseBasicParsing -TimeoutSec 10
    } else {
        Invoke-WebRequest -Uri $Uri -Method $Method -Headers $headers -UseBasicParsing -TimeoutSec 10
    }

    return [ordered]@{
        name = $Name
        uri = $Uri
        method = $Method
        status_code = [int]$response.StatusCode
        status = if ([int]$response.StatusCode -eq 200) { 'passed' } else { 'failed' }
    }
}

$reportDir = Split-Path -Parent $ReportPath
if ($reportDir) {
    New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
}
$legacyReportDir = Split-Path -Parent $LegacyTextReportPath
if ($legacyReportDir) {
    New-Item -ItemType Directory -Force -Path $legacyReportDir | Out-Null
}

$health = Invoke-SmokeCheck -Name 'health' -Uri "$base/health"
$entity = Invoke-SmokeCheck -Name 'entity' -Uri "$base/v1/entities/$encodedEntityId"
$lineage = Invoke-SmokeCheck -Name 'lineage' -Uri "$base/v1/lineage/$encodedEntityId"
$sparqlBody = @{
    template = 'entity_by_id'
    parameters = @{
        id = $EntityId
    }
} | ConvertTo-Json -Depth 4
$sparql = Invoke-SmokeCheck `
    -Name 'sparql' `
    -Uri "$base/v1/sparql" `
    -Method Post `
    -Body $sparqlBody

$checks = @($health, $entity, $lineage, $sparql)
$overallStatus = if (($checks | Where-Object { $_.status -ne 'passed' } | Measure-Object).Count -eq 0) {
    'passed'
} else {
    'failed'
}

$report = [ordered]@{
    schema_version = 'supported-api-smoke.v1'
    generated_utc = (Get-Date).ToUniversalTime().ToString('o')
    base_url = $base
    checks = $checks
    overall_status = $overallStatus
}

$report | ConvertTo-Json -Depth 6 | Set-Content -Path $ReportPath -Encoding UTF8

@(
    "Health: $($health.status_code)",
    "Entity: $($entity.status_code)",
    "Lineage: $($lineage.status_code)",
    "SPARQL: $($sparql.status_code)"
) | Out-File -FilePath $LegacyTextReportPath -Encoding utf8

Write-Host "Supported API smoke report written to $ReportPath"
Write-Host "Legacy smoke summary written to $LegacyTextReportPath"

if ($overallStatus -ne 'passed') {
    throw "Supported API smoke failed. See $ReportPath."
}
