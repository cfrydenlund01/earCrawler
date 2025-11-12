<#
.SYNOPSIS
    Invoke EarCrawler facade endpoints using curl with environment-driven configuration.

.DESCRIPTION
    Loads settings from a .env file and/or environment variables, then issues sample
    requests (health, search, entity, lineage, SPARQL template, RAG) via curl.exe.
    API keys default to EAR_API_KEY, falling back to TRADEGOV_API_KEY so operators
    can reuse their Trade.gov credential. When no entity identifier is specified,
    the script performs a search to discover one automatically, keeping the workflow
    valid for both fixture-based tests and real deployments.

.PARAMETER EnvFile
    Optional dotenv-style file (KEY=VALUE) used to seed settings. Defaults to .env.

.PARAMETER BaseUrl
    Facade base URL. Defaults to http://localhost:9001.

.PARAMETER ApiKey
    API key for the X-Api-Key header. Defaults to EAR_API_KEY or TRADEGOV_API_KEY.

.PARAMETER EntityId
    Knowledge-graph entity identifier. When omitted the script uses the first
    search hit; falls back to urn:ear:entity:demo when no results are returned.

.PARAMETER SearchQuery
    Query string used for the search + SPARQL examples. Defaults to "export controls".

.EXAMPLE
    pwsh scripts/api/curl_facade.ps1

.EXAMPLE
    pwsh scripts/api/curl_facade.ps1 -EnvFile .env.local -BaseUrl https://ear.example.com -Verbose
#>
[CmdletBinding()]
param(
    [string]$EnvFile = ".env",
    [string]$BaseUrl,
    [string]$ApiKey,
    [string]$EntityId,
    [string]$SearchQuery
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Import-EnvFile {
    param([string]$Path)
    $result = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $result
    }
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $parts = $line.Split("=", 2)
        if ($parts.Count -eq 2) {
            $result[$parts[0].Trim()] = $parts[1].Trim()
        }
    }
    return $result
}

$envData = Import-EnvFile -Path $EnvFile

function Resolve-Setting {
    param(
        [string]$Explicit,
        [string]$Key,
        [string]$Default = $null
    )
    if ($Explicit) { return $Explicit }
    if ($envData.ContainsKey($Key) -and $envData[$Key]) { return $envData[$Key] }
    $envValue = [Environment]::GetEnvironmentVariable($Key)
    if ($envValue) { return $envValue }
    return $Default
}

$BaseUrl = Resolve-Setting -Explicit $BaseUrl -Key "EAR_BASE_URL" -Default "http://localhost:9001"
try {
    $uri = [Uri]$BaseUrl
} catch {
    throw "BaseUrl '$BaseUrl' is not a valid URI."
}
if ($uri.Port -eq -1) {
    $uriBuilder = [UriBuilder]$uri
    $uriBuilder.Port = 9001
    $uri = $uriBuilder.Uri
}
$BaseUrl = $uri.AbsoluteUri.TrimEnd("/")

$SearchQuery = Resolve-Setting -Explicit $SearchQuery -Key "EAR_SEARCH_QUERY" -Default "export controls"
$ApiKey = Resolve-Setting -Explicit $ApiKey -Key "EAR_API_KEY"
$apiKeySource = "EAR_API_KEY"
if (-not $ApiKey) {
    $ApiKey = [Environment]::GetEnvironmentVariable("TRADEGOV_API_KEY")
    $apiKeySource = "TRADEGOV_API_KEY"
}
if (-not $ApiKey) {
    $apiKeySource = "anonymous"
}
$EntityId = Resolve-Setting -Explicit $EntityId -Key "EAR_ENTITY_ID"

$curlExe = (Get-Command -Name "curl.exe" -ErrorAction Stop).Source
$commonHeaders = @("--header", "Accept: application/json")
if ($ApiKey) {
    $commonHeaders += @("--header", "X-Api-Key: $ApiKey")
}

function Invoke-Curl {
    param(
        [string]$Method,
        [string]$Path,
        [string]$Description,
        [object]$Body
    )

    $headers = @($commonHeaders)
    $args = @("--silent", "--show-error", "--fail", "--request", $Method)
    $args += $headers
    $url = "$BaseUrl$Path"
    $args += $url
    if ($Body) {
        $json = $Body | ConvertTo-Json -Depth 10 -Compress
        $args += @("--header", "Content-Type: application/json", "--data", $json)
    }
    Write-Host "== $Method $Path ($Description)"
    Write-Host "curl $($args -join ' ')" -ForegroundColor DarkGray
    try {
        & $curlExe @args
        Write-Host ""
    } catch {
        Write-Warning "Request failed: $_"
    }
}

function Discover-EntityId {
    param(
        [string]$Query,
        [string]$ApiKeyValue
    )
    $encoded = [Uri]::EscapeDataString($Query)
    $searchUrl = "$BaseUrl/v1/search?q=$encoded&limit=1"
    $headers = @{}
    if ($ApiKeyValue) {
        $headers["X-Api-Key"] = $ApiKeyValue
    }
    try {
        $response = Invoke-RestMethod -Uri $searchUrl -Headers $headers -Method Get -TimeoutSec 30
        if ($response.results -and $response.results.Count -gt 0) {
            return $response.results[0].id
        }
    } catch {
        Write-Warning "Unable to auto-discover entity id: $_"
    }
    return "urn:ear:entity:demo"
}

if (-not $EntityId) {
    $EntityId = Discover-EntityId -Query $SearchQuery -ApiKeyValue $ApiKey
}

Invoke-Curl -Method "GET" -Path "/health" -Description "Health probe"
Invoke-Curl -Method "GET" -Path "/v1/search?q=$([Uri]::EscapeDataString($SearchQuery))&limit=5" -Description "Search entities"
Invoke-Curl -Method "GET" -Path "/v1/entities/$([Uri]::EscapeDataString($EntityId))" -Description "Entity projection"
Invoke-Curl -Method "GET" -Path "/v1/lineage/$([Uri]::EscapeDataString($EntityId))" -Description "Lineage graph"
Invoke-Curl -Method "POST" -Path "/v1/sparql" -Description "SPARQL template execution" -Body @{
    template   = "search_entities"
    parameters = @{
        q     = $SearchQuery
        limit = 5
    }
}
Invoke-Curl -Method "POST" -Path "/v1/rag/query" -Description "RAG cache lookup" -Body @{
    query            = "What changed in Part 734?"
    top_k            = 3
    include_lineage  = $true
}

Write-Host ""
Write-Host "Base URL: $BaseUrl"
Write-Host "Entity ID: $EntityId"
Write-Host "API key source: $apiKeySource"
