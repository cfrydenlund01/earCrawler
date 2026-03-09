param(
    [Alias('Host')]
    [string]$ApiHost = $env:EARCRAWLER_API_HOST ?? '127.0.0.1',
    [int]$Port = [int]($env:EARCRAWLER_API_PORT ?? 9001),
    [string]$EntityId = ($env:EAR_API_SMOKE_ENTITY_ID ?? 'urn:example:entity:1')
)

$ErrorActionPreference = 'Stop'
$base = "http://{0}:{1}" -f $ApiHost, $Port
$reportDir = 'kg/reports'
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$reportFile = Join-Path $reportDir 'api-smoke.txt'
$encodedEntityId = [uri]::EscapeDataString($EntityId)

$health = Invoke-WebRequest "$base/health" -UseBasicParsing
$entity = Invoke-WebRequest "$base/v1/entities/$encodedEntityId" -UseBasicParsing
$lineage = Invoke-WebRequest "$base/v1/lineage/$encodedEntityId" -UseBasicParsing
$sparqlBody = @{
    template = 'entity_by_id'
    parameters = @{
        id = $EntityId
    }
} | ConvertTo-Json -Depth 4
$sparql = Invoke-WebRequest `
    "$base/v1/sparql" `
    -Method Post `
    -Headers @{ 'Content-Type' = 'application/json' } `
    -Body $sparqlBody `
    -UseBasicParsing

@(
    "Health: $($health.StatusCode)",
    "Entity: $($entity.StatusCode)",
    "Lineage: $($lineage.StatusCode)",
    "SPARQL: $($sparql.StatusCode)"
) | Out-File -FilePath $reportFile -Encoding utf8

Write-Host "Smoke results written to $reportFile"
