param(
    [string]$Path = $(Split-Path -Parent $PSScriptRoot),
    [switch]$NoWait
)

$ErrorActionPreference = 'Stop'
$bundleRoot = (Resolve-Path $Path).Path
$configPath = Join-Path $bundleRoot 'config/bundle_config.yml'
if (-not (Test-Path $configPath)) {
    throw "Missing bundle_config.yml"
}
. (Join-Path $PSScriptRoot 'bundle-config.ps1')
$config = Import-BundleConfig -Path $configPath
$host = $config.fuseki.host
$port = $config.fuseki.port
$timeout = $config.fuseki.timeout_seconds
$jvmOpts = $config.fuseki.jvm_opts
$logDirRel = $config.fuseki.log_dir
if (-not $host) { $host = '127.0.0.1' }
if (-not $port) { $port = 3030 }
if (-not $timeout) { $timeout = 120 }
if (-not $logDirRel) { $logDirRel = 'fuseki/logs' }

$logDir = Join-Path $bundleRoot $logDirRel
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$pidFile = Join-Path $bundleRoot 'fuseki/server.pid'
if (Test-Path $pidFile) {
    throw "Existing Fuseki PID file detected at $pidFile"
}

$assembler = Join-Path $bundleRoot $config.dataset.assembler
if (-not (Test-Path $assembler)) {
    throw "Assembler not found: $assembler"
}

$env:FUSEKI_BASE = Join-Path $bundleRoot 'fuseki'
$env:FUSEKI_HOME = $env:FUSEKI_BASE

function Start-FusekiProcess {
    param(
        [string]$Executable,
        [string[]]$Arguments
    )
    $startInfo = @{
        FilePath = $Executable
        ArgumentList = $Arguments
        WorkingDirectory = $bundleRoot
        PassThru = $true
        RedirectStandardOutput = Join-Path $logDir 'fuseki.out.log'
        RedirectStandardError = Join-Path $logDir 'fuseki.err.log'
    }
    return Start-Process @startInfo
}

$exe = $null
$args = @()
if ($env:EAR_BUNDLE_FUSEKI_CMD) {
    $exe = $env:EAR_BUNDLE_FUSEKI_CMD
    if ($env:EAR_BUNDLE_FUSEKI_ARGS) {
        try {
            $parsedArgs = $env:EAR_BUNDLE_FUSEKI_ARGS | ConvertFrom-Json
            if ($parsedArgs -is [System.Collections.IEnumerable]) {
                $args = @($parsedArgs | ForEach-Object { [string]$_ })
            } else {
                $args = @([string]$parsedArgs)
            }
        } catch {
            $args = $env:EAR_BUNDLE_FUSEKI_ARGS -split '\s+'
        }
    }
} else {
    $fusekiCandidates = @(
        (Join-Path $bundleRoot 'tools/fuseki/fuseki-server.bat'),
        (Join-Path $bundleRoot 'tools/fuseki/fuseki-server')
    )
    foreach ($candidate in $fusekiCandidates) {
        if (Test-Path $candidate) {
            $exe = $candidate
            break
        }
    }
    if (-not $exe) {
        throw 'Fuseki server script not found under tools/fuseki'
    }
    $args = @('--config', $assembler, '--port', $port, '--localhost')
    if ($jvmOpts) {
        $env:FUSEKI_JVM_ARGS = $jvmOpts
    }
}

$process = Start-FusekiProcess -Executable $exe -Arguments $args
$process.Id | Out-File -FilePath $pidFile -Encoding ascii -NoNewline

if (-not $NoWait) {
    $health = Join-Path $bundleRoot 'scripts/bundle-health.ps1'
    try {
        & $health -Path $bundleRoot -TimeoutSeconds $timeout -Quiet
    } catch {
        Write-Error "Fuseki failed to become healthy"
        & (Join-Path $bundleRoot 'scripts/bundle-stop.ps1') -Path $bundleRoot | Out-Null
        exit 1
    }
    Write-Host "Fuseki ready at http://$host:$port/ds"
}
