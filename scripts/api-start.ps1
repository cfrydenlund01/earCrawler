param(
    [Alias('Host')]
    [string]$ApiHost = $env:EARCRAWLER_API_HOST,
    [int]$Port,
    [string]$FusekiUrl = $env:EARCRAWLER_FUSEKI_URL
)

$ErrorActionPreference = 'Stop'

if (-not $ApiHost) { $ApiHost = '127.0.0.1' }

if (-not $PSBoundParameters.ContainsKey('Port')) {
    if ($env:EARCRAWLER_API_PORT) {
        $Port = [int]$env:EARCRAWLER_API_PORT
    } else {
        $Port = 9001
    }
}

$env:EARCRAWLER_API_HOST = $ApiHost
$env:EARCRAWLER_API_PORT = $Port
if ($FusekiUrl) {
    $env:EARCRAWLER_FUSEKI_URL = $FusekiUrl
} else {
    Remove-Item Env:EARCRAWLER_FUSEKI_URL -ErrorAction SilentlyContinue
}
$env:EARCRAWLER_API_EMBEDDED_FIXTURE = '1'

function Resolve-EarPython {
    param()

    if ($env:EARCTL_PYTHON -and (Test-Path $env:EARCTL_PYTHON)) {
        return $env:EARCTL_PYTHON
    }

    foreach ($name in 'python', 'python.exe', 'python3', 'python3.exe') {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }

    $pyLauncher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $probe = & $pyLauncher.Source -3 -c "import sys; print(sys.executable)"
            if ($LASTEXITCODE -eq 0 -and $probe) {
                return $probe.Trim()
            }
        } catch {
        }
    }

    if ($env:VIRTUAL_ENV) {
        $candidate = Join-Path $env:VIRTUAL_ENV 'Scripts/python.exe'
        if (Test-Path $candidate) { return $candidate }
        $candidate = Join-Path $env:VIRTUAL_ENV 'bin/python3'
        if (Test-Path $candidate) { return $candidate }
    }

    throw 'Unable to locate a Python interpreter. Set EARCTL_PYTHON or ensure python is on PATH.'
}

$python = Resolve-EarPython
$pidFile = Join-Path -Path 'kg/reports' -ChildPath 'api.pid'
New-Item -ItemType Directory -Force -Path (Split-Path $pidFile) | Out-Null

Write-Host ("Starting EarCrawler API on {0}:{1}" -f $ApiHost, $Port)
$process = Start-Process -FilePath $python -ArgumentList '-m','uvicorn','service.api_server.server:app','--host',$ApiHost,'--port',$Port -PassThru -WindowStyle Hidden
$process.Id | Out-File -FilePath $pidFile -Encoding ascii

$healthUrl = "http://{0}:{1}/health" -f $ApiHost, $Port
$deadline = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $deadline) {
    try {
        $res = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
        if ($res.StatusCode -eq 200) {
            Write-Host "API healthy"
            return
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}
throw "API failed to start before deadline"
