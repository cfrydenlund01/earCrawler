param(
    [string]$Path = $(Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$bundleRoot = (Resolve-Path $Path).Path
$scriptsDir = Join-Path $bundleRoot 'scripts'
$configPath = Join-Path $bundleRoot 'config/bundle_config.yml'
if (-not (Test-Path $configPath)) {
    throw "Missing bundle_config.yml"
}
if (-not (Get-Command ConvertFrom-Yaml -ErrorAction SilentlyContinue)) {
    throw 'PowerShell YAML support required (ConvertFrom-Yaml not available)'
}
$config = Get-Content $configPath -Raw | ConvertFrom-Yaml

Write-Host 'Running bundle verification'
& (Join-Path $scriptsDir 'bundle-verify.ps1') -Path $bundleRoot

$javaCmd = 'java'
if ($env:JAVA_HOME) {
    $candidate = Join-Path $env:JAVA_HOME 'bin/java'
    if (Test-Path $candidate) {
        $javaCmd = $candidate
    }
}
if (-not (Get-Command $javaCmd -ErrorAction SilentlyContinue)) {
    throw 'Java runtime not found. Install a JDK and ensure java.exe is on PATH.'
}

$jenaHome = Join-Path $bundleRoot 'tools/jena'
$fusekiHome = Join-Path $bundleRoot 'tools/fuseki'
if (-not (Test-Path $jenaHome)) {
    throw 'Apache Jena not found under tools/jena'
}
if (-not (Test-Path $fusekiHome)) {
    throw 'Apache Jena Fuseki not found under tools/fuseki'
}

$loaderCandidates = @(
    (Join-Path $jenaHome 'bat/tdb2_tdbloader.bat'),
    (Join-Path $jenaHome 'bat/tdb2.tdbloader.bat'),
    (Join-Path $jenaHome 'bin/tdb2_tdbloader'),
    (Join-Path $jenaHome 'bin/tdb2.tdbloader')
)
$loader = $null
foreach ($candidate in $loaderCandidates) {
    if (Test-Path $candidate) {
        $loader = $candidate
        break
    }
}
if ($env:EAR_BUNDLE_TDBLOADER) {
    $loader = $env:EAR_BUNDLE_TDBLOADER
}
if (-not $loader) {
    throw 'TDB loader script not found under tools/jena'
}

$datasetNq = Join-Path $bundleRoot $config.dataset.source.nq
$datasetTtl = Join-Path $bundleRoot $config.dataset.source.ttl
$dataset = $null
if ($config.dataset.source.nq -and (Test-Path $datasetNq)) {
    $dataset = $datasetNq
} elseif ($config.dataset.source.ttl -and (Test-Path $datasetTtl)) {
    $dataset = $datasetTtl
}
if (-not $dataset) {
    throw 'No dataset source available (expected kg/dataset.nq or dataset.ttl)'
}

$tdbDir = Join-Path $bundleRoot $config.dataset.location
New-Item -ItemType Directory -Path $tdbDir -Force | Out-Null
$marker = $config.bootstrap.first_run_marker
if (-not $marker) { $marker = 'fuseki/databases/first_run.ok' }
$markerPath = Join-Path $bundleRoot $marker
$needsLoad = -not (Test-Path $markerPath)

if ($needsLoad) {
    Write-Host 'Loading dataset into TDB2 store'
    $existing = Get-ChildItem -Path $tdbDir -Force -ErrorAction SilentlyContinue
    if ($existing) {
        foreach ($item in $existing) {
            Remove-Item -Path $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    $loaderArgs = @('--loc', $tdbDir)
    if ($dataset.ToLower().EndsWith('.nq')) {
        $loaderArgs += '--nquads'
    }
    $loaderArgs += $dataset
    if ($env:EAR_BUNDLE_TDBLOADER_ARGS) {
        try {
            $parsed = $env:EAR_BUNDLE_TDBLOADER_ARGS | ConvertFrom-Json
            if ($parsed -is [System.Collections.IEnumerable]) {
                $loaderArgs = @($parsed | ForEach-Object { [string]$_ })
            } else {
                $loaderArgs = @([string]$parsed)
            }
        } catch {
            $loaderArgs = $env:EAR_BUNDLE_TDBLOADER_ARGS -split '\s+'
        }
    }
    $proc = Start-Process -FilePath $loader -ArgumentList $loaderArgs -WorkingDirectory $bundleRoot -PassThru -Wait
    if ($proc.ExitCode -ne 0) {
        throw "TDB loader exited with code $($proc.ExitCode)"
    }
    Write-Host 'Dataset load completed'
} else {
    Write-Host 'TDB2 store already initialized; skipping load'
}

Write-Host 'Starting Fuseki for smoke test'
& (Join-Path $scriptsDir 'bundle-start.ps1') -Path $bundleRoot | Out-Null
& (Join-Path $scriptsDir 'bundle-health.ps1') -Path $bundleRoot -Quiet | Out-Null
Write-Host 'Health check succeeded; stopping Fuseki'
& (Join-Path $scriptsDir 'bundle-stop.ps1') -Path $bundleRoot | Out-Null

$timestamp = Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ'
New-Item -ItemType Directory -Path (Split-Path $markerPath) -Force | Out-Null
$timestamp | Set-Content -Path $markerPath -Encoding utf8
$reportPath = Join-Path $bundleRoot 'kg/reports/bundle-smoke.txt'
$reportLines = @(
    "timestamp=$timestamp",
    "dataset=$([IO.Path]::GetFileName($dataset))",
    "java=$javaCmd"
)
$reportLines | Set-Content -Path $reportPath -Encoding utf8
Write-Host "First run complete. Marker written to $markerPath"
