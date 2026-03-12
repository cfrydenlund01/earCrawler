<#
.SYNOPSIS
    Invoke EarCrawler facade endpoints using curl with environment-driven configuration.

.DESCRIPTION
    Loads settings from a .env file and/or environment variables, then issues sample
    requests (health, entity, lineage, SPARQL template, RAG) via curl.exe.
    API keys default to EAR_API_KEY, falling back to TRADEGOV_API_KEY so operators
    can reuse their Trade.gov credential. The quarantined /v1/search route is opt-in
    through -IncludeQuarantinedSearch and is excluded from default supported-path calls.

.PARAMETER EnvFile
    Optional dotenv-style file (KEY=VALUE) used to seed settings. Defaults to .env.

.PARAMETER BaseUrl
    Facade base URL. Defaults to http://localhost:9001.

.PARAMETER ApiKey
    API key for the X-Api-Key header. Defaults to EAR_API_KEY or TRADEGOV_API_KEY.

.PARAMETER EntityId
    Knowledge-graph entity identifier. When omitted the script falls back to
    urn:ear:entity:demo.

.PARAMETER SearchQuery
    Query string used only when -IncludeQuarantinedSearch is set.
    Defaults to "export controls".

.PARAMETER IncludeQuarantinedSearch
    Include the quarantined /v1/search call for local validation workflows.

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
    [string]$SearchQuery,
    [switch]$IncludeQuarantinedSearch
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

if (-not $EntityId) {
    $EntityId = "urn:ear:entity:demo"
}

Invoke-Curl -Method "GET" -Path "/health" -Description "Health probe"
if ($IncludeQuarantinedSearch) {
    Invoke-Curl -Method "GET" -Path "/v1/search?q=$([Uri]::EscapeDataString($SearchQuery))&limit=5" -Description "Quarantined search entities"
} else {
    Write-Host "== GET /v1/search (Quarantined search entities)"
    Write-Host "Skipped by default. Use -IncludeQuarantinedSearch for local validation." -ForegroundColor DarkGray
    Write-Host ""
}
Invoke-Curl -Method "GET" -Path "/v1/entities/$([Uri]::EscapeDataString($EntityId))" -Description "Entity projection"
Invoke-Curl -Method "GET" -Path "/v1/lineage/$([Uri]::EscapeDataString($EntityId))" -Description "Lineage graph"
Invoke-Curl -Method "POST" -Path "/v1/sparql" -Description "SPARQL template execution" -Body @{
    template   = "entity_by_id"
    parameters = @{
        id = $EntityId
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
