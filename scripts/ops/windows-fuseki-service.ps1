param(
    [ValidateSet("install", "uninstall", "start", "stop", "restart", "status", "health", "render-config")]
    [string]$Action = "status",
    [string]$ServiceName = "EarCrawler-Fuseki",
    [string]$NssmPath = "C:\tools\nssm\nssm.exe",
    [string]$FusekiHome = "C:\Program Files\Apache\Jena-Fuseki-5.3.0",
    [string]$ProgramDataRoot = "C:\ProgramData\EarCrawler\fuseki",
    [string]$ConfigRoot = "",
    [string]$DatabaseRoot = "",
    [string]$LogRoot = "",
    [string]$ConfigPath = "",
    [string]$FusekiHost = "127.0.0.1",
    [int]$FusekiPort = 3030,
    [string]$DatasetName = "ear",
    [switch]$AllowUnsupportedHost,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-ContractBanner {
    Write-Host "Support contract: one Windows host, one read-only Fuseki instance, one EarCrawler API instance."
    Write-Host "Quarantined Fuseki-backed search and KG expansion are not enabled by this script."
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

function Ensure-Directory {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$DryRunMode
    )

    if ($DryRunMode) {
        Write-Host "[DRY-RUN] New-Item -ItemType Directory -Force -Path $Path"
        return
    }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Convert-ToFileUri {
    param([Parameter(Mandatory = $true)][string]$Path)

    $resolved = [System.IO.Path]::GetFullPath($Path)
    return ([System.Uri]([System.IO.DirectoryInfo]::new($resolved).FullName)).AbsoluteUri
}

function Write-ReadonlyAssembler {
    param(
        [Parameter(Mandatory = $true)][string]$OutPath,
        [Parameter(Mandatory = $true)][string]$TdbLocation,
        [Parameter(Mandatory = $true)][string]$ServiceDatasetName,
        [switch]$DryRunMode
    )

    $datasetUri = Convert-ToFileUri -Path $TdbLocation
    $content = @"
@prefix : <#> .
@prefix fuseki: <http://jena.apache.org/fuseki#> .
@prefix tdb2: <http://jena.hpl.hp.com/2008/tdb#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

[] rdf:type fuseki:Server ;
   fuseki:services (
      [ rdf:type fuseki:Service ;
        fuseki:name "$ServiceDatasetName" ;
        fuseki:serviceQuery "query" ;
        fuseki:serviceReadGraphStore "get" ;
        fuseki:serviceReadQuads "quads" ;
        fuseki:dataset :dataset ;
        fuseki:status "readonly"
      ]
   ) .

:dataset rdf:type tdb2:DatasetTDB2 ;
    tdb2:location "$datasetUri" ;
    tdb2:unionDefaultGraph true ;
    tdb2:requireWritePermission true .
"@

    if ($DryRunMode) {
        Write-Host "[DRY-RUN] Write read-only Fuseki assembler to $OutPath"
        Write-Host $content
        return
    }

    $parent = Split-Path -Parent $OutPath
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $content | Set-Content -Path $OutPath -Encoding ascii
}

function Get-FusekiExecutable {
    param([Parameter(Mandatory = $true)][string]$Home)

    $candidates = @(
        (Join-Path $Home "fuseki-server.bat"),
        (Join-Path $Home "fuseki-server.cmd"),
        (Join-Path $Home "fuseki-server")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    throw "Fuseki launcher not found under $Home"
}

Write-ContractBanner
Ensure-SingleHostBinding -HostName $FusekiHost -AllowUnsupported:$AllowUnsupportedHost

if (-not $ConfigRoot) {
    $ConfigRoot = Join-Path $ProgramDataRoot "config"
}
if (-not $DatabaseRoot) {
    $DatabaseRoot = Join-Path $ProgramDataRoot "databases\tdb2"
}
if (-not $LogRoot) {
    $LogRoot = Join-Path $ProgramDataRoot "logs"
}
if (-not $ConfigPath) {
    $ConfigPath = Join-Path $ConfigRoot "tdb2-readonly-query.ttl"
}

$endpointUrl = "http://{0}:{1}/{2}/query" -f $FusekiHost, $FusekiPort, $DatasetName
$healthScript = Join-Path $PSScriptRoot "..\health\fuseki-probe.ps1"

switch ($Action) {
    "render-config" {
        Ensure-Directory -Path $ConfigRoot -DryRunMode:$DryRun
        Ensure-Directory -Path $DatabaseRoot -DryRunMode:$DryRun
        Write-ReadonlyAssembler -OutPath $ConfigPath -TdbLocation $DatabaseRoot -ServiceDatasetName $DatasetName -DryRunMode:$DryRun
    }
    "install" {
        $fusekiExe = if ($DryRun) { Join-Path $FusekiHome "fuseki-server.bat" } else { Get-FusekiExecutable -Home $FusekiHome }
        Ensure-Directory -Path $ConfigRoot -DryRunMode:$DryRun
        Ensure-Directory -Path $DatabaseRoot -DryRunMode:$DryRun
        Ensure-Directory -Path $LogRoot -DryRunMode:$DryRun
        Write-ReadonlyAssembler -OutPath $ConfigPath -TdbLocation $DatabaseRoot -ServiceDatasetName $DatasetName -DryRunMode:$DryRun

        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @(
            "install", $ServiceName, $fusekiExe,
            "--config", $ConfigPath,
            "--localhost",
            "--port", $FusekiPort.ToString()
        )
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "AppDirectory", $FusekiHome)
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "AppStdout", (Join-Path $LogRoot "fuseki-service.log"))
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "AppStderr", (Join-Path $LogRoot "fuseki-service.log"))
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "Start", "SERVICE_AUTO_START")
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "Description", "EarCrawler Fuseki (supported single-host read-only graph service)")
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
            endpoint = $endpointUrl
            config_path = $ConfigPath
            database_root = $DatabaseRoot
        } | ConvertTo-Json -Depth 4
    }
    "health" {
        if ($DryRun) {
            Write-Host "[DRY-RUN] pwsh $healthScript -FusekiUrl $endpointUrl"
            break
        }
        if (-not (Test-Path $healthScript)) {
            throw "Health script not found: $healthScript"
        }
        & $healthScript -FusekiUrl $endpointUrl
        if ($LASTEXITCODE -ne 0) {
            throw "Fuseki health check failed for $endpointUrl."
        }
        Write-Host "Fuseki health check passed for $endpointUrl"
    }
}
