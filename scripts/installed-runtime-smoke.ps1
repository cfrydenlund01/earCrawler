param(
  [string]$WheelPath = "",
  [Alias('Host')]
  [string]$ApiHost = '127.0.0.1',
  [int]$Port = 9001,
  [string]$ReportPath = 'dist/installed_runtime_smoke.json',
  [switch]$UseHermeticWheelhouse,
  [string]$LockFilePath = 'requirements-win-lock.txt',
  [string]$WheelhousePath = '',
  [string]$HermeticBundleZipPath = '',
  [string]$ReleaseChecksumsPath = '',
  [switch]$UseLiveFuseki,
  [switch]$AutoProvisionFuseki,
  [string]$FusekiUrl = '',
  [string]$FusekiHost = '127.0.0.1',
  [int]$FusekiPort = 3030,
  [string]$FusekiDatasetName = 'ear',
  [switch]$RequireFullBaseline
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($HermeticBundleZipPath -and -not $UseHermeticWheelhouse.IsPresent) {
  throw "-HermeticBundleZipPath requires -UseHermeticWheelhouse."
}
if ($ReleaseChecksumsPath -and -not $UseHermeticWheelhouse.IsPresent) {
  throw "-ReleaseChecksumsPath requires -UseHermeticWheelhouse."
}
if ($AutoProvisionFuseki.IsPresent -and -not $UseLiveFuseki.IsPresent) {
  throw "-AutoProvisionFuseki requires -UseLiveFuseki."
}
if ($RequireFullBaseline.IsPresent -and -not $UseLiveFuseki.IsPresent) {
  throw "-RequireFullBaseline requires -UseLiveFuseki."
}
if ($UseLiveFuseki.IsPresent -and -not $AutoProvisionFuseki.IsPresent -and -not $FusekiUrl) {
  throw "-UseLiveFuseki requires -FusekiUrl when -AutoProvisionFuseki is not set."
}
if ($UseLiveFuseki.IsPresent -and $FusekiDatasetName -notmatch '^[A-Za-z0-9._-]+$') {
  throw "FusekiDatasetName must match ^[A-Za-z0-9._-]+$."
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

function Get-JavaMajorVersion {
  $javaCmd = Get-Command "java" -ErrorAction SilentlyContinue
  if (-not $javaCmd) {
    throw "Java runtime not found on PATH. Java 17 or newer is required for Fuseki baseline provisioning."
  }

  $versionOutput = & $javaCmd.Source -version 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "Unable to execute 'java -version'."
  }

  $text = [string]($versionOutput -join "`n")
  $match = [regex]::Match($text, 'version "(?<version>[^"]+)"')
  if (-not $match.Success) {
    throw "Unable to parse Java version from: $text"
  }

  $raw = $match.Groups["version"].Value
  if ($raw.StartsWith("1.")) {
    $parts = $raw.Split(".")
    if ($parts.Length -lt 2) {
      throw "Unable to parse Java 1.x version token: $raw"
    }
    return [int]$parts[1]
  }

  $majorToken = $raw.Split(".")[0]
  return [int]$majorToken
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

function Stop-ManagedProcess {
  param(
    [System.Diagnostics.Process]$Process,
    [string]$Label
  )

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
    Write-Warning ("Unable to stop {0} process {1}: {2}" -f $Label, $Process.Id, $_.Exception.Message)
  }
}

function Resolve-PwshExecutable {
  $cmd = Get-Command "pwsh" -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }
  throw "pwsh executable not found on PATH."
}

function Resolve-JenaFusekiHomes {
  param(
    [Parameter(Mandatory = $true)][string]$PythonExecutable,
    [Parameter(Mandatory = $true)][string]$RepoRoot
  )

  $bootstrap = @"
import json
import pathlib
import sys
repo = pathlib.Path(r'{0}')
sys.path.insert(0, str(repo))
from earCrawler.utils import jena_tools, fuseki_tools
jena_home = pathlib.Path(jena_tools.ensure_jena())
fuseki_home = pathlib.Path(fuseki_tools.ensure_fuseki())
print(json.dumps({{"jena_home": str(jena_home), "fuseki_home": str(fuseki_home)}}))
"@ -f $RepoRoot

  $raw = & $PythonExecutable -c $bootstrap
  if ($LASTEXITCODE -ne 0) {
    throw "Unable to resolve Jena/Fuseki tool homes."
  }

  $payload = $raw | ConvertFrom-Json
  if (-not $payload.jena_home -or -not $payload.fuseki_home) {
    throw "Jena/Fuseki tool resolution returned incomplete data."
  }
  return [ordered]@{
    jena_home = [string]$payload.jena_home
    fuseki_home = [string]$payload.fuseki_home
  }
}

function Resolve-TdbLoaderScript {
  param([Parameter(Mandatory = $true)][string]$JenaHome)

  $batDir = Join-Path $JenaHome "bat"
  $candidates = @("tdb2_tdbloader.bat", "tdb2.tdbloader.bat")
  foreach ($candidate in $candidates) {
    $path = Join-Path $batDir $candidate
    if (Test-Path $path) {
      return $path
    }
  }
  throw "TDB2 loader script not found under $batDir."
}

function Resolve-FusekiServerExecutable {
  param([Parameter(Mandatory = $true)][string]$FusekiHome)

  $candidates = @(
    (Join-Path $FusekiHome "fuseki-server.bat"),
    (Join-Path $FusekiHome "fuseki-server.cmd"),
    (Join-Path $FusekiHome "fuseki-server")
  )
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  throw "Fuseki server launcher not found under $FusekiHome."
}

function Write-BaselineFusekiFixture {
  param([Parameter(Mandatory = $true)][string]$OutPath)

  $fixture = @"
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<urn:example:entity:1> rdfs:label "Example Entity" ;
  dcterms:description "Installed-runtime baseline fixture entity" ;
  rdf:type <http://schema.org/Thing> ;
  owl:sameAs <http://example.com/entity> ;
  dcterms:identifier "FIX-001" .

<urn:example:activity:1> prov:used <urn:example:entity:1> ;
  prov:generated <urn:example:artifact:2> ;
  prov:endedAtTime "2023-01-02T00:00:00Z" .
"@

  Set-Content -Path $OutPath -Value $fixture -Encoding ascii
}

function Wait-ForFusekiHealth {
  param(
    [Parameter(Mandatory = $true)][string]$PwshExecutable,
    [Parameter(Mandatory = $true)][string]$ProbeScript,
    [Parameter(Mandatory = $true)][string]$FusekiEndpoint,
    [Parameter(Mandatory = $true)][string]$HealthReportPath,
    [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process
  )

  $deadline = (Get-Date).AddSeconds(45)
  while ((Get-Date) -lt $deadline) {
    try {
      Invoke-CheckedCommand $PwshExecutable -File $ProbeScript -FusekiUrl $FusekiEndpoint -ReportPath $HealthReportPath
      return
    }
    catch {
      if ($Process.HasExited) {
        throw "Fuseki process exited before health checks passed."
      }
      Start-Sleep -Milliseconds 750
    }
  }
  throw "Timed out waiting for Fuseki health checks to pass."
}

$python = Resolve-PythonInterpreter
if ($AutoProvisionFuseki.IsPresent) {
  $javaMajorVersion = Get-JavaMajorVersion
  if ($javaMajorVersion -lt 17) {
    throw "Java 17 or newer is required for Fuseki baseline provisioning (found Java $javaMajorVersion)."
  }
}

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
  install_mode = if ($UseHermeticWheelhouse.IsPresent) { "hermetic_wheelhouse" } else { "direct_wheel" }
  install_source = if ($UseHermeticWheelhouse.IsPresent) { "repo_wheelhouse" } else { "direct_wheel" }
  install_details = [ordered]@{}
  fuseki_dependency = [ordered]@{
    mode = if ($UseLiveFuseki.IsPresent) { "live_fuseki" } else { "embedded_fixture" }
    endpoint = ""
    health_report_path = ""
    provisioned = $false
    status = if ($UseLiveFuseki.IsPresent) { "pending" } else { "not_required" }
  }
  checks = @()
  api_smoke = [ordered]@{}
  runtime_contract = [ordered]@{}
  overall_status = "fail"
  error = ""
}

$apiProcess = $null
$fusekiProcess = $null
$fusekiRuntimeRoot = ""
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
  JENA_HOME = $env:JENA_HOME
  FUSEKI_HOME = $env:FUSEKI_HOME
  JAVA_HOME = $env:JAVA_HOME
  EARCTL_PYTHON = $env:EARCTL_PYTHON
}

try {
  Invoke-CheckedCommand $python -m venv (Join-Path $smokeRoot ".venv")

  $venvPython = Join-Path $smokeRoot ".venv\Scripts\python.exe"
  if (-not (Test-Path $venvPython)) {
    throw "Virtualenv bootstrap failed: python executable not found."
  }

  Invoke-CheckedCommand $venvPython -m pip install --disable-pip-version-check --upgrade pip
  if ($UseHermeticWheelhouse.IsPresent) {
    $resolvedLockFilePath = $null
    $resolvedWheelhousePath = $null
    $resolvedBundleZipPath = ""
    $installScript = Join-Path $repoRoot "scripts\install-from-wheelhouse.ps1"

    if ($HermeticBundleZipPath) {
      $candidateBundlePath = $HermeticBundleZipPath
      if (-not [IO.Path]::IsPathRooted($candidateBundlePath)) {
        $candidateBundlePath = Join-Path $repoRoot $candidateBundlePath
      }
      if (-not (Test-Path $candidateBundlePath)) {
        throw "Hermetic bundle zip not found: $candidateBundlePath"
      }
      $resolvedBundleZipPath = (Resolve-Path $candidateBundlePath).Path

      $bundleExtractRoot = Join-Path $smokeRoot "hermetic-bundle"
      New-Item -ItemType Directory -Force -Path $bundleExtractRoot | Out-Null
      Expand-Archive -Path $resolvedBundleZipPath -DestinationPath $bundleExtractRoot -Force

      $bundleRoot = Join-Path $bundleExtractRoot "hermetic-artifacts"
      if (-not (Test-Path $bundleRoot)) {
        $bundleRoot = $bundleExtractRoot
      }

      $bundleLockFilePath = Join-Path $bundleRoot "requirements-win-lock.txt"
      $bundleWheelhousePath = Join-Path $bundleRoot ".wheelhouse"
      $bundleInstallScript = Join-Path $bundleRoot "scripts\install-from-wheelhouse.ps1"
      if (-not (Test-Path $bundleLockFilePath)) {
        throw "Hermetic bundle missing requirements-win-lock.txt: $resolvedBundleZipPath"
      }
      if (-not (Test-Path $bundleWheelhousePath)) {
        throw "Hermetic bundle missing .wheelhouse directory: $resolvedBundleZipPath"
      }
      if (-not (Test-Path $bundleInstallScript)) {
        throw "Hermetic bundle missing scripts/install-from-wheelhouse.ps1: $resolvedBundleZipPath"
      }

      $resolvedLockFilePath = (Resolve-Path $bundleLockFilePath).Path
      $resolvedWheelhousePath = (Resolve-Path $bundleWheelhousePath).Path
      $installScript = (Resolve-Path $bundleInstallScript).Path
      $report.install_source = "release_bundle"
    }
    else {
      $resolvedLockFilePath = $LockFilePath
      if (-not [IO.Path]::IsPathRooted($resolvedLockFilePath)) {
        $resolvedLockFilePath = Join-Path $repoRoot $resolvedLockFilePath
      }
      if (-not (Test-Path $resolvedLockFilePath)) {
        throw "Hermetic lockfile not found: $resolvedLockFilePath"
      }
      $resolvedLockFilePath = (Resolve-Path $resolvedLockFilePath).Path

      if ($WheelhousePath) {
        $candidateWheelhousePath = $WheelhousePath
        if (-not [IO.Path]::IsPathRooted($candidateWheelhousePath)) {
          $candidateWheelhousePath = Join-Path $repoRoot $candidateWheelhousePath
        }
        if (-not (Test-Path $candidateWheelhousePath)) {
          throw "Hermetic wheelhouse path not found: $candidateWheelhousePath"
        }
        $resolvedWheelhousePath = (Resolve-Path $candidateWheelhousePath).Path
      }
      else {
        $candidateWheelhousePaths = @(
          (Join-Path $repoRoot ".wheelhouse"),
          (Join-Path $repoRoot "hermetic-artifacts/.wheelhouse")
        )
        foreach ($candidatePath in $candidateWheelhousePaths) {
          if (Test-Path $candidatePath) {
            $resolvedWheelhousePath = (Resolve-Path $candidatePath).Path
            break
          }
        }
        if (-not $resolvedWheelhousePath) {
          throw "Hermetic wheelhouse directory not found under .wheelhouse or hermetic-artifacts/.wheelhouse."
        }
      }
    }

    $resolvedChecksumsPath = ""
    if ($ReleaseChecksumsPath) {
      $candidateChecksumsPath = $ReleaseChecksumsPath
      if (-not [IO.Path]::IsPathRooted($candidateChecksumsPath)) {
        $candidateChecksumsPath = Join-Path $repoRoot $candidateChecksumsPath
      }
      if (-not (Test-Path $candidateChecksumsPath)) {
        throw "Release checksums file not found: $candidateChecksumsPath"
      }
      $resolvedChecksumsPath = (Resolve-Path $candidateChecksumsPath).Path
    }

    $report.install_details = [ordered]@{
      lock_file = $resolvedLockFilePath
      wheelhouse_path = $resolvedWheelhousePath
      wheel_install_mode = "offline_no_deps"
      installer_script_path = $installScript
      release_bundle_zip = $resolvedBundleZipPath
      checksums_path = $resolvedChecksumsPath
      wheel_checksum_verified = [bool]$resolvedChecksumsPath
    }

    $installParams = @{
      LockFile = $resolvedLockFilePath
      WheelhousePath = $resolvedWheelhousePath
      PythonExecutable = $venvPython
      WheelPath = $wheel.FullName
    }
    if ($resolvedChecksumsPath) {
      $installParams.ChecksumsPath = $resolvedChecksumsPath
    }
    & $installScript @installParams
    if ($LASTEXITCODE -ne 0) {
      throw "Hermetic install script failed with exit code ${LASTEXITCODE}: $installScript"
    }
  }
  else {
    $report.install_details = [ordered]@{
      lock_file = ""
      wheelhouse_path = ""
      wheel_install_mode = "default_pip_resolve"
    }
    Invoke-CheckedCommand $venvPython -m pip install --disable-pip-version-check $wheel.FullName
  }

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

  if ($UseLiveFuseki.IsPresent -and $AutoProvisionFuseki.IsPresent) {
    $pwshExe = Resolve-PwshExecutable
    $tools = Resolve-JenaFusekiHomes -PythonExecutable $python -RepoRoot $repoRoot

    $env:JENA_HOME = [string]$tools.jena_home
    $env:FUSEKI_HOME = [string]$tools.fuseki_home

    $fusekiRuntimeRoot = Join-Path $smokeRoot "fuseki-runtime"
    $fusekiProgramData = Join-Path $fusekiRuntimeRoot "programdata"
    $fusekiConfigRoot = Join-Path $fusekiProgramData "config"
    $fusekiDatabaseRoot = Join-Path $fusekiProgramData "databases\tdb2"
    $fusekiLogRoot = Join-Path $fusekiProgramData "logs"
    $fusekiConfigPath = Join-Path $fusekiConfigRoot "tdb2-readonly-query.ttl"
    $fusekiFixturePath = Join-Path $fusekiRuntimeRoot "baseline-fixture.ttl"
    $fusekiHealthReportPath = Join-Path $fusekiLogRoot "health-fuseki.txt"

    New-Item -ItemType Directory -Force -Path $fusekiRuntimeRoot, $fusekiProgramData, $fusekiConfigRoot, $fusekiDatabaseRoot, $fusekiLogRoot | Out-Null
    Write-BaselineFusekiFixture -OutPath $fusekiFixturePath

    $fusekiServiceScript = Join-Path $repoRoot "scripts\ops\windows-fuseki-service.ps1"
    & $fusekiServiceScript `
      -Action render-config `
      -ProgramDataRoot $fusekiProgramData `
      -ConfigRoot $fusekiConfigRoot `
      -DatabaseRoot $fusekiDatabaseRoot `
      -ConfigPath $fusekiConfigPath `
      -FusekiHost $FusekiHost `
      -FusekiPort $FusekiPort `
      -DatasetName $FusekiDatasetName
    if ($LASTEXITCODE -ne 0) {
      throw "Fuseki config render failed."
    }

    $tdbLoader = Resolve-TdbLoaderScript -JenaHome ([string]$tools.jena_home)
    Invoke-CheckedCommand $tdbLoader "--loc=$fusekiDatabaseRoot" $fusekiFixturePath

    $fusekiExe = Resolve-FusekiServerExecutable -FusekiHome ([string]$tools.fuseki_home)
    $fusekiStdOut = Join-Path $fusekiLogRoot "fuseki-smoke.out.log"
    $fusekiStdErr = Join-Path $fusekiLogRoot "fuseki-smoke.err.log"
    $fusekiProcess = Start-Process `
      -FilePath $fusekiExe `
      -ArgumentList @("--config", $fusekiConfigPath, "--localhost", "--port", $FusekiPort.ToString()) `
      -WorkingDirectory ([string]$tools.fuseki_home) `
      -PassThru `
      -WindowStyle Hidden `
      -RedirectStandardOutput $fusekiStdOut `
      -RedirectStandardError $fusekiStdErr

    $FusekiUrl = "http://{0}:{1}/{2}/query" -f $FusekiHost, $FusekiPort, $FusekiDatasetName
    Wait-ForFusekiHealth `
      -PwshExecutable $pwshExe `
      -ProbeScript (Join-Path $repoRoot "scripts\health\fuseki-probe.ps1") `
      -FusekiEndpoint $FusekiUrl `
      -HealthReportPath $fusekiHealthReportPath `
      -Process $fusekiProcess

    $report.fuseki_dependency = [ordered]@{
      mode = "live_fuseki"
      endpoint = $FusekiUrl
      health_report_path = $fusekiHealthReportPath
      provisioned = $true
      status = "passed"
    }
  }
  elseif ($UseLiveFuseki.IsPresent) {
    $pwshExe = Resolve-PwshExecutable
    $fusekiHealthReportPath = Join-Path $smokeRoot "fuseki-health.txt"
    Invoke-CheckedCommand $pwshExe -File (Join-Path $repoRoot "scripts\health\fuseki-probe.ps1") -FusekiUrl $FusekiUrl -ReportPath $fusekiHealthReportPath
    $report.fuseki_dependency = [ordered]@{
      mode = "live_fuseki"
      endpoint = $FusekiUrl
      health_report_path = $fusekiHealthReportPath
      provisioned = $false
      status = "passed"
    }
  }

  $env:EARCRAWLER_API_HOST = $ApiHost
  $env:EARCRAWLER_API_PORT = [string]$Port
  $env:EARCRAWLER_API_INSTANCE_COUNT = "1"
  $env:EARCRAWLER_API_ENABLE_SEARCH = "0"
  $env:EARCRAWLER_ENABLE_KG_EXPANSION = "0"
  if ($UseLiveFuseki.IsPresent) {
    $env:EARCRAWLER_FUSEKI_URL = $FusekiUrl
    Remove-Item Env:EARCRAWLER_API_EMBEDDED_FIXTURE -ErrorAction SilentlyContinue
  }
  else {
    $env:EARCRAWLER_API_EMBEDDED_FIXTURE = "1"
    Remove-Item Env:EARCRAWLER_FUSEKI_URL -ErrorAction SilentlyContinue
  }
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

  $expectedInstallMode = if ($UseHermeticWheelhouse.IsPresent) { "hermetic_wheelhouse" } else { "direct_wheel" }
  $expectedInstallSource = if ($UseHermeticWheelhouse.IsPresent) {
    if ($HermeticBundleZipPath) { "release_bundle" } else { "repo_wheelhouse" }
  } else {
    "direct_wheel"
  }
  $baselineModeExpected = if ($RequireFullBaseline.IsPresent) { "live_fuseki" } else { [string]$report.fuseki_dependency.mode }
  $baselineStatusExpected = if ($RequireFullBaseline.IsPresent) { "passed" } else { [string]$report.fuseki_dependency.status }
  $checkList = @(
    [ordered]@{ name = "install_mode"; passed = ($report.install_mode -eq $expectedInstallMode); expected = $expectedInstallMode; actual = [string]$report.install_mode },
    [ordered]@{ name = "install_source"; passed = ([string]$report.install_source -eq $expectedInstallSource); expected = $expectedInstallSource; actual = [string]$report.install_source },
    [ordered]@{ name = "fuseki_dependency_mode"; passed = ([string]$report.fuseki_dependency.mode -eq $baselineModeExpected); expected = $baselineModeExpected; actual = [string]$report.fuseki_dependency.mode },
    [ordered]@{ name = "fuseki_dependency_health"; passed = ([string]$report.fuseki_dependency.status -eq $baselineStatusExpected); expected = $baselineStatusExpected; actual = [string]$report.fuseki_dependency.status },
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
  Stop-ManagedProcess -Process $fusekiProcess -Label "Fuseki"

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
