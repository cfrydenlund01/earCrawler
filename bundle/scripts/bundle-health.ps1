param(
    [string]$Path = $(Split-Path -Parent $PSScriptRoot),
    [int]$TimeoutSeconds = 60,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$bundleRoot = (Resolve-Path $Path).Path
$configPath = Join-Path $bundleRoot 'config/bundle_config.yml'
if (-not (Test-Path $configPath)) {
    throw "Missing bundle_config.yml"
}
. (Join-Path $PSScriptRoot 'bundle-config.ps1')
$config = Import-BundleConfig -Path $configPath
$fusekiHost = $config.fuseki.host
$port = $config.fuseki.port
$query = $config.fuseki.health_query
if (-not $fusekiHost) { $fusekiHost = '127.0.0.1' }
if (-not $port) { $port = 3030 }
if (-not $query) { $query = 'SELECT * WHERE { ?s ?p ?o } LIMIT 1' }

$base = "http://${fusekiHost}:${port}"
$ping = "$base/$/ping"
$service = "$base/ds/sparql"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$pingOk = $false
while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-WebRequest -Uri $ping -UseBasicParsing -TimeoutSec 10
        if ($resp.StatusCode -eq 200) {
            $pingOk = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $pingOk) {
    Write-Error "Fuseki ping endpoint unavailable at $ping"
    exit 1
}

$encodedQuery = [System.Uri]::EscapeDataString($query)
try {
    $resp = Invoke-WebRequest -Uri "$service?query=$encodedQuery" -UseBasicParsing -TimeoutSec 30
    if ($resp.StatusCode -ne 200) {
        Write-Error "SPARQL query failed with status $($resp.StatusCode)"
        exit 1
    }
} catch {
    Write-Error "Failed to execute SPARQL query against $service"
    exit 1
}

if (-not $Quiet) {
    Write-Host "Fuseki service healthy at $service"
}
