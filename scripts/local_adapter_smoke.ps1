param(
    [string]$RunDir,
    [Alias('Host')]
    [string]$ApiHost = $env:EARCRAWLER_API_HOST ?? '127.0.0.1',
    [int]$Port = [int]($env:EARCRAWLER_API_PORT ?? 9001),
    [string]$Query = 'Do laptops to France need a license?',
    [int]$TopK = 3
)

$ErrorActionPreference = 'Stop'

if (-not $RunDir) {
    throw "RunDir is required. Pass a Task 5.3 run directory (dist/training/<run_id>)."
}

$runPath = (Resolve-Path $RunDir).Path
$adapterDir = Join-Path $runPath 'adapter'
$metadataPath = Join-Path $runPath 'run_metadata.json'
$smokePath = Join-Path $runPath 'inference_smoke.json'

foreach ($requiredPath in @($adapterDir, $metadataPath, $smokePath)) {
    if (-not (Test-Path $requiredPath)) {
        throw "Missing required Task 5.3 artifact: $requiredPath"
    }
}

$smoke = Get-Content $smokePath -Raw | ConvertFrom-Json
$baseModel = [string]$smoke.base_model
if (-not $baseModel) {
    throw "inference_smoke.json is missing base_model."
}

$runId = Split-Path $runPath -Leaf
$base = "http://{0}:{1}" -f $ApiHost, $Port
$reportDir = 'kg/reports'
$reportFile = Join-Path $reportDir 'local-adapter-smoke.json'
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

$originalEnv = @{
    LLM_PROVIDER = $env:LLM_PROVIDER
    EARCRAWLER_ENABLE_LOCAL_LLM = $env:EARCRAWLER_ENABLE_LOCAL_LLM
    EARCRAWLER_LOCAL_LLM_BASE_MODEL = $env:EARCRAWLER_LOCAL_LLM_BASE_MODEL
    EARCRAWLER_LOCAL_LLM_ADAPTER_DIR = $env:EARCRAWLER_LOCAL_LLM_ADAPTER_DIR
    EARCRAWLER_LOCAL_LLM_MODEL_ID = $env:EARCRAWLER_LOCAL_LLM_MODEL_ID
}

try {
    $env:LLM_PROVIDER = 'local_adapter'
    $env:EARCRAWLER_ENABLE_LOCAL_LLM = '1'
    $env:EARCRAWLER_LOCAL_LLM_BASE_MODEL = $baseModel
    $env:EARCRAWLER_LOCAL_LLM_ADAPTER_DIR = $adapterDir
    $env:EARCRAWLER_LOCAL_LLM_MODEL_ID = $runId

    $payload = @{
        query = $Query
        top_k = $TopK
    } | ConvertTo-Json

    $response = Invoke-WebRequest `
        -Uri "$base/v1/rag/answer" `
        -Method Post `
        -Headers @{ 'Content-Type' = 'application/json' } `
        -Body $payload `
        -TimeoutSec 180 `
        -UseBasicParsing

    $result = $response.Content | ConvertFrom-Json
    if ($response.StatusCode -ne 200) {
        throw "Unexpected status code from /v1/rag/answer: $($response.StatusCode)"
    }
    if (-not $result.output_ok) {
        throw "LLM output failed strict schema checks."
    }
    if ([string]$result.provider -ne 'local_adapter') {
        throw "Expected provider=local_adapter, got provider=$($result.provider)"
    }
    if ($result.egress.remote_enabled -ne $false) {
        throw "Expected egress.remote_enabled=false for local adapter mode."
    }

    $report = [ordered]@{
        status = 'passed'
        endpoint = "$base/v1/rag/answer"
        run_dir = $runPath
        adapter_dir = $adapterDir
        base_model = $baseModel
        model = $result.model
        provider = $result.provider
        trace_id = $result.trace_id
        output_ok = $result.output_ok
        retrieval_empty = $result.retrieval_empty
        egress_remote_enabled = $result.egress.remote_enabled
        label = $result.label
    } | ConvertTo-Json -Depth 6

    $report | Out-File -FilePath $reportFile -Encoding utf8
    Write-Host "Local adapter smoke passed. Report written to $reportFile"
}
finally {
    foreach ($entry in $originalEnv.GetEnumerator()) {
        if ($null -eq $entry.Value) {
            Remove-Item "Env:$($entry.Key)" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item "Env:$($entry.Key)" $entry.Value
        }
    }
}
