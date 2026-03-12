param(
    [ValidateSet("install", "uninstall", "start", "stop", "restart", "status", "health")]
    [string]$Action = "status",
    [string]$ServiceName = "EarCrawler-API",
    [string]$NssmPath = "C:\tools\nssm\nssm.exe",
    [string]$RuntimeRoot = "C:\Program Files\EarCrawler\runtime",
    [string]$WorkspaceRoot = "C:\ProgramData\EarCrawler\workspace",
    [string]$LogRoot = "C:\ProgramData\EarCrawler\logs",
    [string]$ApiHost = "127.0.0.1",
    [int]$ApiPort = 9001,
    [string]$HealthUrl = "",
    [switch]$AllowUnsupportedHost,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-ContractBanner {
    Write-Host "Support contract: one Windows host and one EarCrawler API service instance."
}

function Test-IsLoopbackHost {
    param([Parameter(Mandatory = $true)][string]$HostName)
    $candidate = $HostName.Trim().ToLowerInvariant()
    return $candidate -in @("127.0.0.1", "localhost", "::1")
}

function Ensure-SingleHostBinding {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [switch]$AllowUnsupported
    )

    if (Test-IsLoopbackHost -HostName $HostName) {
        return
    }
    if ($AllowUnsupported) {
        Write-Warning "Using non-loopback bind '$HostName'. This is outside the supported single-host contract."
        return
    }
    throw "Refusing non-loopback bind '$HostName'. Use -AllowUnsupportedHost only for local experiments."
}

function Invoke-Nssm {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$DryRunMode
    )

    $quoted = $Arguments | ForEach-Object {
        if ($_ -match "\s") { "`"$_`"" } else { $_ }
    }
    $cmdLine = "$Executable " + ($quoted -join " ")
    if ($DryRunMode) {
        Write-Host "[DRY-RUN] $cmdLine"
        return
    }
    if (-not (Test-Path $Executable)) {
        throw "NSSM executable not found: $Executable"
    }
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "NSSM command failed ($LASTEXITCODE): $cmdLine"
    }
}

function Get-VenvPythonPath {
    param([Parameter(Mandatory = $true)][string]$Root)
    return Join-Path $Root ".venv\Scripts\python.exe"
}

Write-ContractBanner

switch ($Action) {
    "install" {
        Ensure-SingleHostBinding -HostName $ApiHost -AllowUnsupported:$AllowUnsupportedHost
        $venvPython = Get-VenvPythonPath -Root $RuntimeRoot
        if (-not $DryRun -and -not (Test-Path $venvPython)) {
            throw "Runtime python not found: $venvPython"
        }

        if ($DryRun) {
            Write-Host "[DRY-RUN] Ensure directories: $WorkspaceRoot, $LogRoot"
        }
        else {
            New-Item -ItemType Directory -Force -Path $WorkspaceRoot, $LogRoot | Out-Null
        }

        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @(
            "install", $ServiceName, $venvPython,
            "-m", "uvicorn", "service.api_server.server:app",
            "--host", $ApiHost, "--port", $ApiPort.ToString()
        )
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "AppDirectory", $WorkspaceRoot)
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "AppStdout", (Join-Path $LogRoot "api-service.log"))
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "AppStderr", (Join-Path $LogRoot "api-service.log"))
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "Start", "SERVICE_AUTO_START")
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "Description", "EarCrawler API (supported single-host runtime)")
    }
    "uninstall" {
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("remove", $ServiceName, "confirm")
    }
    "start" {
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("start", $ServiceName)
    }
    "stop" {
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("stop", $ServiceName)
    }
    "restart" {
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("restart", $ServiceName)
    }
    "status" {
        if ($DryRun) {
            Write-Host "[DRY-RUN] Get-Service -Name $ServiceName"
            break
        }
        $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($null -eq $svc) {
            throw "Service '$ServiceName' was not found."
        }
        [ordered]@{
            service_name = $svc.Name
            display_name = $svc.DisplayName
            status = $svc.Status.ToString()
        } | ConvertTo-Json -Depth 3
    }
    "health" {
        Ensure-SingleHostBinding -HostName $ApiHost -AllowUnsupported:$AllowUnsupportedHost
        if (-not $HealthUrl) {
            $HealthUrl = "http://{0}:{1}/health" -f $ApiHost, $ApiPort
        }
        if ($DryRun) {
            Write-Host "[DRY-RUN] Invoke-WebRequest $HealthUrl"
            break
        }
        $res = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 10
        if ($res.StatusCode -ne 200) {
            throw "Health check failed for $HealthUrl (HTTP $($res.StatusCode))."
        }
        Write-Host "Health check passed for $HealthUrl"
    }
}
