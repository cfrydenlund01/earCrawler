param(
    [ValidateSet("install", "uninstall", "start", "stop", "restart", "status", "health", "render-config")]
    [string]$Action = "status",
    [string]$ServiceName = "EarCrawler-Fuseki",
    [string]$NssmPath = "C:\tools\nssm\nssm.exe",
    [string]$FusekiHome = "C:\Program Files\Apache\Jena-Fuseki-5.3.0",
    [string]$ProgramDataRoot = "C:\ProgramData\EarCrawler\fuseki",
    [string]$ConfigRoot = "",
    [string]$DatabaseRoot = "",
    [string]$LuceneRoot = "",
    [string]$LogRoot = "",
    [string]$ConfigPath = "",
    [string]$FusekiHost = "127.0.0.1",
    [int]$FusekiPort = 3030,
    [string]$DatasetName = "ear",
    [switch]$EnableTextIndexValidation,
    [string]$TextProbeQuery = "__earcrawler_text_probe__",
    [switch]$AllowUnsupportedHost,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-ContractBanner {
    Write-Host "Support contract: one Windows host, one read-only Fuseki instance, one EarCrawler API instance."
    Write-Host "Quarantined Fuseki-backed search and KG expansion are not enabled by this script."
    if ($EnableTextIndexValidation) {
        Write-Host "Optional validation mode: renders a text-index-enabled Fuseki config for quarantined search/KG promotion evidence only."
    }
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

function Get-JavaMajorVersion {
    $javaCmd = Get-Command "java" -ErrorAction SilentlyContinue
    if (-not $javaCmd) {
        throw "Java runtime not found on PATH. Java 17 or newer is required for supported Fuseki operations."
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

function Assert-Java17Runtime {
    param([Parameter(Mandatory = $true)][string]$OperationName)

    $majorVersion = Get-JavaMajorVersion
    if ($majorVersion -lt 17) {
        throw "Java 17 or newer is required to $OperationName Fuseki service operations (found Java $majorVersion). Ensure JAVA_HOME/PATH resolve to Java 17+."
    }
}

function Get-ListeningPortOwners {
    param([int]$LocalPort)

    $netTcpCommand = Get-Command "Get-NetTCPConnection" -ErrorAction SilentlyContinue
    if (-not $netTcpCommand) {
        throw "Get-NetTCPConnection is unavailable; cannot validate port ownership for port $LocalPort."
    }

    $connections = Get-NetTCPConnection -State Listen -LocalPort $LocalPort -ErrorAction SilentlyContinue
    if ($null -eq $connections) {
        return @()
    }

    $owners = New-Object System.Collections.Generic.List[object]
    foreach ($group in ($connections | Group-Object -Property OwningProcess)) {
        $pidValue = [int]$group.Name
        $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        $processName = if ($proc) { [string]$proc.ProcessName } else { "" }
        $owners.Add([ordered]@{
            pid = $pidValue
            process_name = $processName
        })
    }

    return @($owners | Sort-Object -Property pid)
}

function Get-ServiceProcessId {
    param([Parameter(Mandatory = $true)][string]$TargetServiceName)

    $escapedName = $TargetServiceName.Replace("'", "''")
    $svc = Get-CimInstance Win32_Service -Filter ("Name='{0}'" -f $escapedName) -ErrorAction SilentlyContinue
    if ($null -eq $svc) {
        return 0
    }
    return [int]$svc.ProcessId
}

function Assert-FusekiPortStartOwnership {
    param(
        [Parameter(Mandatory = $true)][string]$TargetServiceName,
        [Parameter(Mandatory = $true)][int]$TargetPort
    )

    $owners = Get-ListeningPortOwners -LocalPort $TargetPort
    if (@($owners).Count -eq 0) {
        return [ordered]@{
            status = "free"
            owners = @()
        }
    }

    $servicePid = Get-ServiceProcessId -TargetServiceName $TargetServiceName
    if ($servicePid -gt 0) {
        $foreignOwners = @($owners | Where-Object { [int]$_.pid -ne $servicePid })
        if (@($foreignOwners).Count -eq 0) {
            return [ordered]@{
                status = "owned_by_service"
                owners = @($owners)
                service_pid = $servicePid
            }
        }
    }

    $ownerSummary = @($owners | ForEach-Object { "pid=$($_.pid) process=$($_.process_name)" }) -join "; "
    throw "Fuseki port $TargetPort is already occupied by a non-service process. $ownerSummary"
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
    return $resolved.Replace('\', '/')
}

function Write-FusekiAssembler {
    param(
        [Parameter(Mandatory = $true)][string]$OutPath,
        [Parameter(Mandatory = $true)][string]$TdbLocation,
        [Parameter(Mandatory = $true)][string]$ServiceDatasetName,
        [string]$LuceneLocation = "",
        [switch]$TextIndexValidationMode,
        [switch]$DryRunMode
    )

    $datasetUri = Convert-ToFileUri -Path $TdbLocation
    if ($TextIndexValidationMode) {
        if (-not $LuceneLocation) {
            throw "LuceneLocation is required when TextIndexValidationMode is enabled."
        }
        $luceneUri = Convert-ToFileUri -Path $LuceneLocation
        $content = @"
@prefix : <#> .
@prefix fuseki: <http://jena.apache.org/fuseki#> .
@prefix tdb2: <http://jena.apache.org/2016/tdb#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix text: <http://jena.apache.org/text#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

[] rdf:type fuseki:Server ;
   fuseki:services (
      [ rdf:type fuseki:Service ;
        fuseki:name "$ServiceDatasetName" ;
        fuseki:serviceQuery "query" ;
        fuseki:serviceUpdate "update" ;
        fuseki:serviceReadGraphStore "get" ;
        fuseki:serviceReadQuads "quads" ;
        fuseki:dataset :dataset ;
        fuseki:status "validation_text_index"
      ]
   ) .

:dataset rdf:type text:TextDataset ;
    text:dataset :tdb_dataset ;
    text:index :text_index .

:tdb_dataset rdf:type tdb2:DatasetTDB2 ;
    tdb2:location "$datasetUri" ;
    tdb2:unionDefaultGraph true ;
    tdb2:requireWritePermission true .

:text_index rdf:type text:TextIndexLucene ;
    text:directory "$luceneUri" ;
    text:entityMap :entity_map .

:entity_map rdf:type text:EntityMap ;
    text:entityField "entity" ;
    text:defaultField "label" ;
    text:map (
        [ text:field "label" ;
          text:predicate rdfs:label ]
    ) .
"@
    }
    else {
        $content = @"
@prefix : <#> .
@prefix fuseki: <http://jena.apache.org/fuseki#> .
@prefix tdb2: <http://jena.apache.org/2016/tdb#> .
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
    }

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
    $DatabaseRoot = if ($EnableTextIndexValidation) {
        Join-Path $ProgramDataRoot "databases\tdb2-text"
    } else {
        Join-Path $ProgramDataRoot "databases\tdb2"
    }
}
if (-not $LuceneRoot) {
    $LuceneRoot = if ($EnableTextIndexValidation) {
        Join-Path $ProgramDataRoot "databases\lucene"
    } else {
        ""
    }
}
if (-not $LogRoot) {
    $LogRoot = Join-Path $ProgramDataRoot "logs"
}
if (-not $ConfigPath) {
    $ConfigPath = if ($EnableTextIndexValidation) {
        Join-Path $ConfigRoot "tdb2-text-validation-query.ttl"
    } else {
        Join-Path $ConfigRoot "tdb2-readonly-query.ttl"
    }
}

$endpointUrl = "http://{0}:{1}/{2}/query" -f $FusekiHost, $FusekiPort, $DatasetName
$healthScript = Join-Path $PSScriptRoot "..\health\fuseki-probe.ps1"

switch ($Action) {
    "render-config" {
        Ensure-Directory -Path $ConfigRoot -DryRunMode:$DryRun
        Ensure-Directory -Path $DatabaseRoot -DryRunMode:$DryRun
        if ($EnableTextIndexValidation) {
            Ensure-Directory -Path $LuceneRoot -DryRunMode:$DryRun
        }
        Write-FusekiAssembler `
            -OutPath $ConfigPath `
            -TdbLocation $DatabaseRoot `
            -ServiceDatasetName $DatasetName `
            -LuceneLocation $LuceneRoot `
            -TextIndexValidationMode:$EnableTextIndexValidation `
            -DryRunMode:$DryRun
    }
    "install" {
        Assert-Java17Runtime -OperationName "install"
        $fusekiExe = if ($DryRun) { Join-Path $FusekiHome "fuseki-server.bat" } else { Get-FusekiExecutable -Home $FusekiHome }
        Ensure-Directory -Path $ConfigRoot -DryRunMode:$DryRun
        Ensure-Directory -Path $DatabaseRoot -DryRunMode:$DryRun
        if ($EnableTextIndexValidation) {
            Ensure-Directory -Path $LuceneRoot -DryRunMode:$DryRun
        }
        Ensure-Directory -Path $LogRoot -DryRunMode:$DryRun
        Write-FusekiAssembler `
            -OutPath $ConfigPath `
            -TdbLocation $DatabaseRoot `
            -ServiceDatasetName $DatasetName `
            -LuceneLocation $LuceneRoot `
            -TextIndexValidationMode:$EnableTextIndexValidation `
            -DryRunMode:$DryRun

        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @(
            "install", $ServiceName, $fusekiExe,
            "--config=$ConfigPath",
            "--localhost",
            "--port", $FusekiPort.ToString(),
            "--ping"
        )
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "AppDirectory", $FusekiHome)
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "AppStdout", (Join-Path $LogRoot "fuseki-service.log"))
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "AppStderr", (Join-Path $LogRoot "fuseki-service.log"))
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "Start", "SERVICE_AUTO_START")
        $description = if ($EnableTextIndexValidation) {
            "EarCrawler Fuseki (single-host text-index validation service for quarantined search/KG evidence)"
        } else {
            "EarCrawler Fuseki (supported single-host read-only graph service)"
        }
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("set", $ServiceName, "Description", $description)
    }
    "uninstall" {
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("remove", $ServiceName, "confirm")
    }
    "start" {
        Assert-Java17Runtime -OperationName "start"
        $portState = Assert-FusekiPortStartOwnership -TargetServiceName $ServiceName -TargetPort $FusekiPort
        if ($portState.status -eq "owned_by_service") {
            Write-Host "Fuseki service already owns port $FusekiPort; no start action needed."
            break
        }
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("start", $ServiceName)
    }
    "stop" {
        Invoke-Nssm -Executable $NssmPath -DryRunMode:$DryRun -Arguments @("stop", $ServiceName)
    }
    "restart" {
        Assert-Java17Runtime -OperationName "restart"
        [void](Assert-FusekiPortStartOwnership -TargetServiceName $ServiceName -TargetPort $FusekiPort)
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
            lucene_root = $LuceneRoot
            text_index_validation_enabled = [bool]$EnableTextIndexValidation
        } | ConvertTo-Json -Depth 4
    }
    "health" {
        if ($DryRun) {
            $dryRunCmd = "pwsh $healthScript -FusekiUrl $endpointUrl"
            if ($EnableTextIndexValidation) {
                $dryRunCmd += " -RequireTextQuery -TextQuery `"$TextProbeQuery`""
            }
            Write-Host "[DRY-RUN] $dryRunCmd"
            break
        }
        if (-not (Test-Path $healthScript)) {
            throw "Health script not found: $healthScript"
        }
        $healthArgs = @{
            FusekiUrl = $endpointUrl
        }
        if ($EnableTextIndexValidation) {
            $healthArgs.RequireTextQuery = $true
            $healthArgs.TextQuery = $TextProbeQuery
        }
        & $healthScript @healthArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Fuseki health check failed for $endpointUrl."
        }
        Write-Host "Fuseki health check passed for $endpointUrl"
    }
}
