param(
    [Alias('Host')]
    [string]$ApiHost = $env:EARCRAWLER_API_HOST ?? '127.0.0.1',
    [int]$Port = [int]($env:EARCRAWLER_API_PORT ?? 9001),
    [string]$LocalAdapterRunDir = "",
    [switch]$SkipLocalAdapter,
    [string]$ReportPath = 'kg/reports/optional-runtime-smoke.json'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-PythonInterpreter {
    if ($env:EARCTL_PYTHON -and (Test-Path $env:EARCTL_PYTHON)) {
        return $env:EARCTL_PYTHON
    }
    if ($env:pythonLocation) {
        $candidate = Join-Path $env:pythonLocation "python.exe"
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    foreach ($name in "python", "python.exe", "python3", "py") {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }
    throw "Python interpreter not found on PATH."
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        $joined = $Arguments -join " "
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable $joined"
    }
}

function Invoke-HttpProbe {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [string]$Method = "GET",
        [string]$Body = ""
    )

    $headers = @{}
    if ($Body) {
        $headers["Content-Type"] = "application/json"
    }
    $response = if ($Body) {
        Invoke-WebRequest -Uri $Uri -Method $Method -Headers $headers -Body $Body -UseBasicParsing -SkipHttpErrorCheck -TimeoutSec 10
    } else {
        Invoke-WebRequest -Uri $Uri -Method $Method -Headers $headers -UseBasicParsing -SkipHttpErrorCheck -TimeoutSec 10
    }

    $jsonBody = $null
    if ($response.Content) {
        try {
            $jsonBody = $response.Content | ConvertFrom-Json
        } catch {
            $jsonBody = $null
        }
    }
    return [ordered]@{
        uri = $Uri
        status_code = [int]$response.StatusCode
        ok_2xx = ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 300)
        json = $jsonBody
    }
}

function Stop-SmokeApi {
    param(
        [Parameter(Mandatory = $true)][string]$ApiStopScript
    )

    try {
        & $ApiStopScript
    } catch {
        Write-Warning ("API stop helper raised an error: {0}" -f $_.Exception.Message)
    }
}

function Invoke-SearchPhase {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][bool]$EnableSearch,
        [Parameter(Mandatory = $true)][int]$ExpectedSearchStatus,
        [Parameter(Mandatory = $true)][string]$ApiStartScript,
        [Parameter(Mandatory = $true)][string]$ApiStopScript,
        [Parameter(Mandatory = $true)][string]$BaseUrl,
        [Parameter(Mandatory = $true)][string]$ApiHostValue,
        [Parameter(Mandatory = $true)][int]$PortValue
    )

    if ($EnableSearch) {
        $env:EARCRAWLER_API_ENABLE_SEARCH = '1'
    } else {
        $env:EARCRAWLER_API_ENABLE_SEARCH = '0'
    }

    & $ApiStartScript -Host $ApiHostValue -Port $PortValue
    try {
        $health = Invoke-HttpProbe -Uri "$BaseUrl/health"
        $search = Invoke-HttpProbe -Uri "$BaseUrl/v1/search?q=export&limit=1"
        $passed = ($health.status_code -eq 200) -and ($search.status_code -eq $ExpectedSearchStatus)
        return [ordered]@{
            name = $Name
            enable_search = $EnableSearch
            expected_search_status = $ExpectedSearchStatus
            health = $health
            search = $search
            status = if ($passed) { "passed" } else { "failed" }
        }
    } finally {
        Stop-SmokeApi -ApiStopScript $ApiStopScript
    }
}

$baseUrl = "http://{0}:{1}" -f $ApiHost, $Port
$apiStartScript = Join-Path $PSScriptRoot "api-start.ps1"
$apiStopScript = Join-Path $PSScriptRoot "api-stop.ps1"
$localAdapterSmokeScript = Join-Path $PSScriptRoot "local_adapter_smoke.ps1"
$python = Resolve-PythonInterpreter

$savedEnv = @{
    EARCRAWLER_API_ENABLE_SEARCH = $env:EARCRAWLER_API_ENABLE_SEARCH
    EARCRAWLER_ENABLE_KG_EXPANSION = $env:EARCRAWLER_ENABLE_KG_EXPANSION
    EARCRAWLER_KG_EXPANSION_PROVIDER = $env:EARCRAWLER_KG_EXPANSION_PROVIDER
    EARCRAWLER_KG_EXPANSION_FAILURE_POLICY = $env:EARCRAWLER_KG_EXPANSION_FAILURE_POLICY
    EARCRAWLER_KG_EXPANSION_MODE = $env:EARCRAWLER_KG_EXPANSION_MODE
    EARCRAWLER_KG_EXPANSION_PATH = $env:EARCRAWLER_KG_EXPANSION_PATH
    EARCRAWLER_FUSEKI_URL = $env:EARCRAWLER_FUSEKI_URL
    LLM_PROVIDER = $env:LLM_PROVIDER
    EARCRAWLER_ENABLE_LOCAL_LLM = $env:EARCRAWLER_ENABLE_LOCAL_LLM
    EARCRAWLER_LOCAL_LLM_BASE_MODEL = $env:EARCRAWLER_LOCAL_LLM_BASE_MODEL
    EARCRAWLER_LOCAL_LLM_ADAPTER_DIR = $env:EARCRAWLER_LOCAL_LLM_ADAPTER_DIR
    EARCRAWLER_LOCAL_LLM_MODEL_ID = $env:EARCRAWLER_LOCAL_LLM_MODEL_ID
}

try {
    $searchPhases = @()
    $searchPhases += Invoke-SearchPhase `
        -Name "search_default_off" `
        -EnableSearch:$false `
        -ExpectedSearchStatus 404 `
        -ApiStartScript $apiStartScript `
        -ApiStopScript $apiStopScript `
        -BaseUrl $baseUrl `
        -ApiHostValue $ApiHost `
        -PortValue $Port
    $searchPhases += Invoke-SearchPhase `
        -Name "search_opt_in_on" `
        -EnableSearch:$true `
        -ExpectedSearchStatus 200 `
        -ApiStartScript $apiStartScript `
        -ApiStopScript $apiStopScript `
        -BaseUrl $baseUrl `
        -ApiHostValue $ApiHost `
        -PortValue $Port
    $searchPhases += Invoke-SearchPhase `
        -Name "search_rollback_off" `
        -EnableSearch:$false `
        -ExpectedSearchStatus 404 `
        -ApiStartScript $apiStartScript `
        -ApiStopScript $apiStopScript `
        -BaseUrl $baseUrl `
        -ApiHostValue $ApiHost `
        -PortValue $Port

    $kgProbeScript = @"
import json
import os
import tempfile
from pathlib import Path

from earCrawler.rag.retrieval_runtime import expand_with_kg

keys = [
    "EARCRAWLER_ENABLE_KG_EXPANSION",
    "EARCRAWLER_KG_EXPANSION_PROVIDER",
    "EARCRAWLER_KG_EXPANSION_FAILURE_POLICY",
    "EARCRAWLER_KG_EXPANSION_MODE",
    "EARCRAWLER_KG_EXPANSION_PATH",
    "EARCRAWLER_FUSEKI_URL",
]
saved = {key: os.environ.get(key) for key in keys}
result = {}
try:
    os.environ["EARCRAWLER_ENABLE_KG_EXPANSION"] = "1"
    os.environ["EARCRAWLER_KG_EXPANSION_PROVIDER"] = "fuseki"
    os.environ["EARCRAWLER_KG_EXPANSION_MODE"] = "always_on"
    os.environ.pop("EARCRAWLER_FUSEKI_URL", None)

    os.environ["EARCRAWLER_KG_EXPANSION_FAILURE_POLICY"] = "disable"
    disable_rows = expand_with_kg(["EAR-740.1"])
    result["disable_missing_fuseki"] = {
        "status": "passed",
        "rows": len(disable_rows),
    }

    os.environ["EARCRAWLER_KG_EXPANSION_FAILURE_POLICY"] = "error"
    try:
        expand_with_kg(["EAR-740.1"])
    except RuntimeError as exc:
        result["error_missing_fuseki"] = {
            "status": "passed",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    else:
        result["error_missing_fuseki"] = {
            "status": "failed",
            "error": "Expected RuntimeError when failure_policy=error and EARCRAWLER_FUSEKI_URL is unset.",
        }

    with tempfile.TemporaryDirectory(prefix="earcrawler-kg-jsonstub-") as tmp:
        mapping_path = Path(tmp) / "kg_map.json"
        mapping_path.write_text(
            json.dumps(
                {
                    "EAR-740.1": {
                        "text": "Stub KG note",
                        "source": "json_stub",
                        "related_sections": ["EAR-736.2"],
                    }
                }
            ),
            encoding="utf-8",
        )
        os.environ["EARCRAWLER_KG_EXPANSION_PROVIDER"] = "json_stub"
        os.environ["EARCRAWLER_KG_EXPANSION_PATH"] = str(mapping_path)
        os.environ["EARCRAWLER_KG_EXPANSION_FAILURE_POLICY"] = "error"
        stub_rows = expand_with_kg(["EAR-740.1"])
        result["json_stub_expansion"] = {
            "status": "passed" if len(stub_rows) >= 1 else "failed",
            "rows": len(stub_rows),
        }
finally:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

overall = all(entry.get("status") == "passed" for entry in result.values())
print(json.dumps({"status": "passed" if overall else "failed", "checks": result}))
"@
    $kgProbePath = Join-Path $env:TEMP ("earcrawler-kg-probe-" + [guid]::NewGuid().ToString("N") + ".py")
    Set-Content -Path $kgProbePath -Value $kgProbeScript -Encoding UTF8
    try {
        $kgProbeRaw = & $python $kgProbePath
        if ($LASTEXITCODE -ne 0) {
            throw "KG failure-policy probe command failed."
        }
        $kgProbe = $kgProbeRaw | ConvertFrom-Json
    } finally {
        Remove-Item $kgProbePath -ErrorAction SilentlyContinue
    }

    $localAdapterResult = [ordered]@{
        status = "skipped"
        reason = "no run artifact provided"
    }
    if (-not $SkipLocalAdapter -and $LocalAdapterRunDir) {
        if (-not (Test-Path $LocalAdapterRunDir)) {
            $localAdapterResult = [ordered]@{
                status = "failed"
                reason = "run_dir_not_found"
                run_dir = $LocalAdapterRunDir
            }
        } else {
            try {
                $runDirResolved = (Resolve-Path $LocalAdapterRunDir).Path
                $smokePayload = Get-Content (Join-Path $runDirResolved "inference_smoke.json") -Raw | ConvertFrom-Json
                $baseModel = [string]$smokePayload.base_model
                if (-not $baseModel) {
                    throw "inference_smoke.json is missing base_model."
                }
                $env:LLM_PROVIDER = "local_adapter"
                $env:EARCRAWLER_ENABLE_LOCAL_LLM = "1"
                $env:EARCRAWLER_LOCAL_LLM_BASE_MODEL = $baseModel
                $env:EARCRAWLER_LOCAL_LLM_ADAPTER_DIR = (Join-Path $runDirResolved "adapter")
                $env:EARCRAWLER_LOCAL_LLM_MODEL_ID = (Split-Path $runDirResolved -Leaf)

                & $apiStartScript -Host $ApiHost -Port $Port
                try {
                    & $localAdapterSmokeScript -RunDir $runDirResolved -Host $ApiHost -Port $Port
                    $localReport = Get-Content 'kg/reports/local-adapter-smoke.json' -Raw | ConvertFrom-Json
                    $localAdapterResult = [ordered]@{
                        status = "passed"
                        run_dir = $runDirResolved
                        report = $localReport
                    }
                } finally {
                    Stop-SmokeApi -ApiStopScript $apiStopScript
                }
            } catch {
                $localAdapterResult = [ordered]@{
                    status = "failed"
                    run_dir = $LocalAdapterRunDir
                    error = $_.Exception.Message
                }
            }
        }
    }

    $searchPassed = ($searchPhases | Where-Object { $_.status -ne "passed" } | Measure-Object).Count -eq 0
    $kgPassed = ([string]$kgProbe.status -eq "passed")
    $localAdapterPassed = ([string]$localAdapterResult.status -in @("passed", "skipped"))
    $overallPassed = $searchPassed -and $kgPassed -and $localAdapterPassed

    $report = [ordered]@{
        schema_version = "optional-runtime-smoke.v1"
        generated_utc = (Get-Date).ToUniversalTime().ToString("o")
        base_url = $baseUrl
        search_mode_checks = $searchPhases
        kg_expansion_failure_policy_checks = $kgProbe
        local_adapter_check = $localAdapterResult
        overall_status = if ($overallPassed) { "passed" } else { "failed" }
    }

    $reportDir = Split-Path -Parent $ReportPath
    if ($reportDir) {
        New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
    }
    $report | ConvertTo-Json -Depth 10 | Set-Content -Path $ReportPath -Encoding UTF8
    Write-Host "Optional runtime smoke report written to $ReportPath"
    if (-not $overallPassed) {
        throw "Optional runtime smoke failed. See $ReportPath."
    }
}
finally {
    Stop-SmokeApi -ApiStopScript $apiStopScript
    foreach ($entry in $savedEnv.GetEnumerator()) {
        if ($null -eq $entry.Value) {
            Remove-Item "Env:$($entry.Key)" -ErrorAction SilentlyContinue
        } else {
            Set-Item "Env:$($entry.Key)" $entry.Value
        }
    }
}
