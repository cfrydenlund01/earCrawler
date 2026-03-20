[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,
    [string]$HealthPath = "/health",
    [string]$QuarantinedPath = "/v1/search?q=health&limit=1",
    [string]$UnpublishedPath = "/docs",
    [int]$TimeoutSec = 10,
    [string]$ReportPath = "kg/reports/iis-front-door-smoke.txt",
    [string]$JsonReportPath = "",
    [switch]$UseDefaultCredentials,
    [string]$ExpectedSubject = "",
    [int]$ExpectedHealthStatus = 200,
    [int]$ExpectedDeniedStatus = 404
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Probe {
    param(
        [Parameter(Mandatory = $true)][string]$Uri
    )

    $invokeParams = @{
        Uri = $Uri
        Method = "GET"
        UseBasicParsing = $true
        TimeoutSec = $TimeoutSec
    }
    if ($UseDefaultCredentials) {
        $invokeParams["UseDefaultCredentials"] = $true
    }

    try {
        $response = Invoke-WebRequest @invokeParams
        return [PSCustomObject]@{
            status_code = [int]$response.StatusCode
            headers = $response.Headers
            body = [string]$response.Content
            error = ""
        }
    }
    catch {
        $statusCode = 0
        $headers = @{}
        $body = ""
        $errorText = $_.Exception.Message

        $response = $null
        if ($_.Exception.PSObject.Properties.Name -contains "Response") {
            $response = $_.Exception.Response
        }

        if ($response) {
            try {
                $statusCode = [int]$response.StatusCode
            }
            catch {
                $statusCode = 0
            }
            try {
                $headers = $response.Headers
            }
            catch {
                $headers = @{}
            }
        }

        return [PSCustomObject]@{
            status_code = $statusCode
            headers = $headers
            body = $body
            error = [string]$errorText
        }
    }
}

function Join-BaseUrl {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )
    if ($Root.EndsWith("/")) {
        return "{0}{1}" -f $Root.TrimEnd("/"), $Path
    }
    return "{0}{1}" -f $Root, $Path
}

$normalizedBaseUrl = $BaseUrl.TrimEnd("/")
$healthUri = Join-BaseUrl -Root $normalizedBaseUrl -Path $HealthPath
$quarantinedUri = Join-BaseUrl -Root $normalizedBaseUrl -Path $QuarantinedPath
$unpublishedUri = Join-BaseUrl -Root $normalizedBaseUrl -Path $UnpublishedPath

$health = Invoke-Probe -Uri $healthUri
$quarantined = Invoke-Probe -Uri $quarantinedUri
$unpublished = Invoke-Probe -Uri $unpublishedUri

$requestIdHeader = ""
$subjectHeader = ""
if ($health.headers) {
    $requestIdHeader = [string]$health.headers["X-Request-Id"]
    $subjectHeader = [string]$health.headers["X-Subject"]
}

$healthOk = ($health.status_code -eq $ExpectedHealthStatus)
$requestIdOk = -not [string]::IsNullOrWhiteSpace($requestIdHeader)
$subjectOk = $true
if ($ExpectedSubject) {
    $subjectOk = ($subjectHeader -eq $ExpectedSubject)
}
$quarantinedOk = ($quarantined.status_code -eq $ExpectedDeniedStatus)
$unpublishedOk = ($unpublished.status_code -eq $ExpectedDeniedStatus)

$overall = $healthOk -and $requestIdOk -and $subjectOk -and $quarantinedOk -and $unpublishedOk

$textReport = @(
    "IIS front-door smoke"
    "Base URL: $normalizedBaseUrl"
    "Health URI: $healthUri"
    "Health status: $($health.status_code)"
    "Health request id present: $(if ($requestIdOk) { 'yes' } else { 'no' })"
    "Health subject: $subjectHeader"
    "Quarantined path URI: $quarantinedUri"
    "Quarantined path status: $($quarantined.status_code)"
    "Unpublished path URI: $unpublishedUri"
    "Unpublished path status: $($unpublished.status_code)"
    "Overall: $(if ($overall) { 'pass' } else { 'fail' })"
)

$reportDir = Split-Path -Parent $ReportPath
if ($reportDir) {
    New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
}
$textReport | Set-Content -Path $ReportPath -Encoding utf8

if ($JsonReportPath) {
    $jsonPayload = [ordered]@{
        schema_version = "iis-front-door-smoke.v1"
        generated_utc = (Get-Date).ToUniversalTime().ToString("o")
        base_url = $normalizedBaseUrl
        used_default_credentials = [bool]$UseDefaultCredentials
        expected_subject = $ExpectedSubject
        health = [ordered]@{
            path = $HealthPath
            status_code = [int]$health.status_code
            request_id_present = $requestIdOk
            request_id = $requestIdHeader
            subject = $subjectHeader
            subject_ok = $subjectOk
            error = $health.error
        }
        quarantined_path = [ordered]@{
            path = $QuarantinedPath
            status_code = [int]$quarantined.status_code
            denied_ok = $quarantinedOk
            error = $quarantined.error
        }
        unpublished_path = [ordered]@{
            path = $UnpublishedPath
            status_code = [int]$unpublished.status_code
            denied_ok = $unpublishedOk
            error = $unpublished.error
        }
        overall_status = if ($overall) { "passed" } else { "failed" }
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
