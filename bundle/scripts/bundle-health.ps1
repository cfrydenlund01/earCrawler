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

$baseBuilder = [System.UriBuilder]::new()
$baseBuilder.Scheme = 'http'
$baseBuilder.Host = $fusekiHost
$baseBuilder.Port = $port
$baseUri = $baseBuilder.Uri

$pingBuilder = [System.UriBuilder]::new($baseUri)
$pingBuilder.Path = '$/ping'
$pingBuilder.Query = ''
$pingUri = $pingBuilder.Uri

$serviceBuilder = [System.UriBuilder]::new($baseUri)
$serviceBuilder.Path = 'ds/sparql'
$serviceBuilder.Query = ''
$serviceUri = $serviceBuilder.Uri
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
$handler.UseProxy = $false
$client = [System.Net.Http.HttpClient]::new($handler)

try {
    $pingOk = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $cts = [System.Threading.CancellationTokenSource]::new()
            $cts.CancelAfter([TimeSpan]::FromSeconds(10))
            try {
                $resp = $client.GetAsync($pingUri, $cts.Token).GetAwaiter().GetResult()
                try {
                    if ($resp.StatusCode -eq [System.Net.HttpStatusCode]::OK) {
                        $pingOk = $true
                        break
                    }
                } finally {
                    $resp.Dispose()
                }
            } finally {
                $cts.Dispose()
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }

    if (-not $pingOk) {
        Write-Error "Fuseki ping endpoint unavailable at $($pingUri.AbsoluteUri)"
        exit 1
    }

    $client.DefaultRequestHeaders.Accept.Clear()
    $client.DefaultRequestHeaders.Accept.Add([System.Net.Http.Headers.MediaTypeWithQualityHeaderValue]::new('application/sparql-results+json'))

    $encodedQuery = [System.Uri]::EscapeDataString($query)
    try {
        $cts = [System.Threading.CancellationTokenSource]::new()
        $cts.CancelAfter([TimeSpan]::FromSeconds([Math]::Max(1, [Math]::Min($TimeoutSeconds, 30))))
        try {
            $serviceQueryBuilder = [System.UriBuilder]::new($serviceUri)
            $serviceQueryBuilder.Query = "query=$encodedQuery"
            $serviceQueryUri = $serviceQueryBuilder.Uri
            $resp = $client.GetAsync($serviceQueryUri, $cts.Token).GetAwaiter().GetResult()
            try {
                if (-not $resp.IsSuccessStatusCode) {
                    Write-Error "SPARQL query failed with status $([int]$resp.StatusCode)"
                    exit 1
                }
            } finally {
                $resp.Dispose()
            }
        } finally {
            $cts.Dispose()
        }
    } catch {
        $message = $_.Exception.Message
        if (-not $message) {
            $message = $_.ToString()
        }
        Write-Error "Failed to execute SPARQL query against $($serviceUri.AbsoluteUri)`n$message"
        exit 1
    }
} finally {
    $client.Dispose()
    $handler.Dispose()
}

if (-not $Quiet) {
    Write-Host "Fuseki service healthy at $($serviceUri.AbsoluteUri)"
}
