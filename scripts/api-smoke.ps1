param(
    [Alias('Host')]
    [string]$ApiHost = $env:EARCRAWLER_API_HOST ?? '127.0.0.1',
    [int]$Port = [int]($env:EARCRAWLER_API_PORT ?? 9001)
)

$ErrorActionPreference = 'Stop'
$base = "http://{0}:{1}" -f $ApiHost, $Port
$reportDir = 'kg/reports'
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$reportFile = Join-Path $reportDir 'api-smoke.txt'

$health = Invoke-WebRequest "$base/health" -UseBasicParsing
$search = Invoke-WebRequest "$base/v1/search?q=export&limit=1" -UseBasicParsing
$entity = Invoke-WebRequest "$base/v1/entities/urn:example:entity:1" -UseBasicParsing -ErrorAction SilentlyContinue

@(
    "Health: $($health.StatusCode)",
    "Search: $($search.StatusCode)",
    "Entity: $($entity.StatusCode)"
) | Out-File -FilePath $reportFile -Encoding utf8

Write-Host "Smoke results written to $reportFile"
