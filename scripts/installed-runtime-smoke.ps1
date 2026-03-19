param(
  [string]$WheelPath = "",
  [Alias('Host')]
  [string]$ApiHost = '127.0.0.1',
  [int]$Port = 9001,
  [string]$ReportPath = 'dist/installed_runtime_smoke.json'
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

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

function Stop-ApiProcess {
  param([System.Diagnostics.Process]$Process)

  if ($null -eq $Process) {
    return
  }
  if ($Process.HasExited) {
    return
  }

  try {
    Stop-Process -Id $Process.Id -Force -ErrorAction Stop
  }
  catch {
    Write-Warning ("Unable to stop installed-runtime API process {0}: {1}" -f $Process.Id, $_.Exception.Message)
  }
}

$python = Resolve-PythonInterpreter

if ($WheelPath) {
  if (-not (Test-Path $WheelPath)) {
    throw "Requested wheel does not exist: $WheelPath"
  }
  $wheel = Get-Item $WheelPath
}
else {
  Invoke-CheckedCommand $python -m pip install --disable-pip-version-check --upgrade build
  Invoke-CheckedCommand $python -m build --wheel
  $wheel = Get-ChildItem dist -Filter "*.whl" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
}

if (-not $wheel) {
  throw "Wheel build failed: no wheel found in dist/."
}

$smokeRoot = Join-Path $env:TEMP ("earcrawler-installed-runtime-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null

$report = [ordered]@{
  schema_version = "installed-runtime-smoke.v1"
  generated_utc = (Get-Date).ToUniversalTime().ToString("o")
  wheel_path = $wheel.FullName
  api_base_url = "http://{0}:{1}" -f $ApiHost, $Port
  checks = @()
  api_smoke = [ordered]@{}
  runtime_contract = [ordered]@{}
  overall_status = "fail"
  error = ""
}

$apiProcess = $null
$smokeFailure = ""

$savedEnv = @{
  EARCRAWLER_API_HOST = $env:EARCRAWLER_API_HOST
  EARCRAWLER_API_PORT = $env:EARCRAWLER_API_PORT
  EARCRAWLER_API_INSTANCE_COUNT = $env:EARCRAWLER_API_INSTANCE_COUNT
  EARCRAWLER_ALLOW_UNSUPPORTED_MULTI_INSTANCE = $env:EARCRAWLER_ALLOW_UNSUPPORTED_MULTI_INSTANCE
  EARCRAWLER_API_EMBEDDED_FIXTURE = $env:EARCRAWLER_API_EMBEDDED_FIXTURE
  EARCRAWLER_FUSEKI_URL = $env:EARCRAWLER_FUSEKI_URL
  EARCRAWLER_API_ENABLE_SEARCH = $env:EARCRAWLER_API_ENABLE_SEARCH
  EARCRAWLER_ENABLE_KG_EXPANSION = $env:EARCRAWLER_ENABLE_KG_EXPANSION
  EARCRAWLER_WHEEL_SMOKE_REPO_ROOT = $env:EARCRAWLER_WHEEL_SMOKE_REPO_ROOT
}

try {
  Invoke-CheckedCommand $python -m venv (Join-Path $smokeRoot ".venv")

  $venvPython = Join-Path $smokeRoot ".venv\Scripts\python.exe"
  if (-not (Test-Path $venvPython)) {
    throw "Virtualenv bootstrap failed: python executable not found."
  }

  Invoke-CheckedCommand $venvPython -m pip install --disable-pip-version-check --upgrade pip
  Invoke-CheckedCommand $venvPython -m pip install --disable-pip-version-check $wheel.FullName

  $workspace = Join-Path $smokeRoot "workspace"
  New-Item -ItemType Directory -Force -Path $workspace | Out-Null

  $env:EARCRAWLER_WHEEL_SMOKE_REPO_ROOT = $repoRoot
  $importCheck = @"
from pathlib import Path
import os
import earCrawler

repo_root = Path(os.getenv("EARCRAWLER_WHEEL_SMOKE_REPO_ROOT", "")).resolve()
module_path = Path(earCrawler.__file__).resolve()
if str(module_path).lower().startswith(str(repo_root).lower()):
    raise SystemExit(f"installed-runtime smoke failed: imported earCrawler from source checkout ({module_path})")
"@
  $importCheckPath = Join-Path $workspace "import_check.py"
  Set-Content -Path $importCheckPath -Value $importCheck -Encoding ascii
  Invoke-CheckedCommand $venvPython $importCheckPath

  $env:EARCRAWLER_API_HOST = $ApiHost
  $env:EARCRAWLER_API_PORT = [string]$Port
  $env:EARCRAWLER_API_INSTANCE_COUNT = "1"
  $env:EARCRAWLER_API_EMBEDDED_FIXTURE = "1"
  $env:EARCRAWLER_API_ENABLE_SEARCH = "0"
  $env:EARCRAWLER_ENABLE_KG_EXPANSION = "0"
  Remove-Item Env:EARCRAWLER_FUSEKI_URL -ErrorAction SilentlyContinue
  Remove-Item Env:EARCRAWLER_ALLOW_UNSUPPORTED_MULTI_INSTANCE -ErrorAction SilentlyContinue

  $apiProcess = Start-Process -FilePath $venvPython -ArgumentList @('-m', 'uvicorn', 'service.api_server.server:app', '--host', $ApiHost, '--port', $Port) -WorkingDirectory $workspace -PassThru -WindowStyle Hidden

  $baseUrl = "http://{0}:{1}" -f $ApiHost, $Port
  $healthUrl = "$baseUrl/health"
  $deadline = (Get-Date).AddSeconds(30)
  $healthResponse = $null
  while ((Get-Date) -lt $deadline) {
    try {
      $candidate = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
      if ([int]$candidate.StatusCode -eq 200) {
        $healthResponse = $candidate
        break
      }
    }
    catch {
      Start-Sleep -Milliseconds 500
    }
  }

  if ($null -eq $healthResponse) {
    throw "Installed-wheel API failed to reach healthy state before timeout."
  }

  $healthJson = $healthResponse.Content | ConvertFrom-Json
  $runtimeContract = $healthJson.runtime_contract
  $capabilities = $runtimeContract.capabilities

  $apiSmokeReportPath = Join-Path $smokeRoot "api_smoke.json"
  $apiSmokeScript = Join-Path $repoRoot "scripts\api-smoke.ps1"
  & $apiSmokeScript -Host $ApiHost -Port $Port -ReportPath $apiSmokeReportPath
  if ($LASTEXITCODE -ne 0) {
    throw "Supported API smoke failed for installed-wheel runtime."
  }
  $apiSmokePayload = Get-Content -Path $apiSmokeReportPath -Raw | ConvertFrom-Json

  $checkList = @(
    [ordered]@{ name = "health_http_200"; passed = ([int]$healthResponse.StatusCode -eq 200); expected = "200"; actual = [string]$healthResponse.StatusCode },
    [ordered]@{ name = "supported_api_smoke"; passed = ([string]$apiSmokePayload.schema_version -eq "supported-api-smoke.v1" -and [string]$apiSmokePayload.overall_status -eq "passed"); expected = "supported-api-smoke.v1 + passed"; actual = ("{0} + {1}" -f [string]$apiSmokePayload.schema_version, [string]$apiSmokePayload.overall_status) },
    [ordered]@{ name = "runtime_contract_topology"; passed = ([string]$runtimeContract.topology -eq "single_host"); expected = "single_host"; actual = [string]$runtimeContract.topology },
    [ordered]@{ name = "runtime_contract_declared_instance_count"; passed = ([int]$runtimeContract.declared_instance_count -eq 1); expected = "1"; actual = [string]$runtimeContract.declared_instance_count },
    [ordered]@{ name = "runtime_contract_capability_registry_schema"; passed = ([string]$runtimeContract.capability_registry_schema -eq "capability-registry.v1"); expected = "capability-registry.v1"; actual = [string]$runtimeContract.capability_registry_schema },
    [ordered]@{ name = "runtime_contract_api_default_surface"; passed = ([string]$capabilities.'api.default_surface'.status -eq "supported"); expected = "supported"; actual = [string]$capabilities.'api.default_surface'.status },
    [ordered]@{ name = "runtime_contract_api_search"; passed = ([string]$capabilities.'api.search'.status -eq "quarantined"); expected = "quarantined"; actual = [string]$capabilities.'api.search'.status },
    [ordered]@{ name = "runtime_contract_kg_expansion"; passed = ([string]$capabilities.'kg.expansion'.status -eq "quarantined"); expected = "quarantined"; actual = [string]$capabilities.'kg.expansion'.status }
  )

  $report.checks = $checkList
  $report.api_smoke = [ordered]@{
    path = $apiSmokeReportPath
    schema_version = [string]$apiSmokePayload.schema_version
    overall_status = [string]$apiSmokePayload.overall_status
  }
  $report.runtime_contract = [ordered]@{
    topology = [string]$runtimeContract.topology
    declared_instance_count = [int]$runtimeContract.declared_instance_count
    capability_registry_schema = [string]$runtimeContract.capability_registry_schema
    capabilities = [ordered]@{
      api_default_surface = [string]$capabilities.'api.default_surface'.status
      api_search = [string]$capabilities.'api.search'.status
      kg_expansion = [string]$capabilities.'kg.expansion'.status
    }
  }

  $hasFailure = ($checkList | Where-Object { -not $_.passed } | Measure-Object).Count -gt 0
  if ($hasFailure) {
    $smokeFailure = "One or more installed-runtime checks failed."
  }
  else {
    $report.overall_status = "passed"
  }
}
catch {
  $smokeFailure = $_.Exception.Message
}
finally {
  Stop-ApiProcess -Process $apiProcess

  foreach ($key in $savedEnv.Keys) {
    $value = $savedEnv[$key]
    if ($null -eq $value -or $value -eq "") {
      Remove-Item ("Env:{0}" -f $key) -ErrorAction SilentlyContinue
    }
    else {
      Set-Item ("Env:{0}" -f $key) -Value $value
    }
  }

  if ($smokeFailure) {
    $report.overall_status = "failed"
    $report.error = $smokeFailure
  }

  $reportDir = Split-Path -Parent $ReportPath
  if ($reportDir) {
    New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
  }
  $report | ConvertTo-Json -Depth 10 | Set-Content -Path $ReportPath -Encoding utf8

  Remove-Item -Recurse -Force $smokeRoot -ErrorAction SilentlyContinue
}

if ($smokeFailure) {
  throw "Installed runtime smoke failed: $smokeFailure. See $ReportPath."
}

Write-Host "Installed runtime smoke report written: $ReportPath"
Write-Host "Installed runtime smoke passed."
