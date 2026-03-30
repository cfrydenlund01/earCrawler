param(
    [Alias('Host')]
    [string]$ApiHost = $env:EARCRAWLER_API_HOST ?? '127.0.0.1',
    [int]$Port = [int]($env:EARCRAWLER_API_PORT ?? 9001),
    [string]$ReportPath = 'kg/reports/search-kg-prodlike-smoke.json',
    [string]$FusekiHost = '127.0.0.1',
    [int]$FusekiPort = 3040,
    [string]$DatasetName = 'ear',
    [int]$TimeoutSeconds = 90
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

function Resolve-PwshExecutable {
    $cmd = Get-Command "pwsh" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    throw "pwsh executable not found on PATH."
}

function Get-JavaMajorVersionFromExecutable {
    param([string]$JavaExecutable)

    if (-not $JavaExecutable -or -not (Test-Path $JavaExecutable)) {
        return $null
    }
    try {
        $versionOutput = & $JavaExecutable -version 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        $text = [string]($versionOutput -join "`n")
        $match = [regex]::Match($text, 'version "(?<version>[^"]+)"')
        if (-not $match.Success) {
            return $null
        }
        $raw = $match.Groups["version"].Value
        if ($raw.StartsWith("1.")) {
            return [int]$raw.Split(".")[1]
        }
        return [int]$raw.Split(".")[0]
    } catch {
        return $null
    }
}

function Find-Java17Home {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    $candidateHomes = New-Object System.Collections.Generic.List[string]
    if ($env:JAVA_HOME) {
        [void]$candidateHomes.Add($env:JAVA_HOME)
    }
    $javaCmd = Get-Command "java" -ErrorAction SilentlyContinue
    if ($javaCmd) {
        $candidateFromPath = Split-Path -Parent (Split-Path -Parent $javaCmd.Source)
        if ($candidateFromPath) {
            [void]$candidateHomes.Add($candidateFromPath)
        }
    }

    $searchRoots = @(
        (Join-Path $RepoRoot 'tools\jdk17'),
        (Join-Path $env:ProgramFiles 'Eclipse Adoptium'),
        (Join-Path $env:ProgramFiles 'Java'),
        (Join-Path $env:ProgramFiles 'Microsoft')
    ) | Where-Object { $_ -and (Test-Path $_) }

    foreach ($root in $searchRoots) {
        foreach ($candidate in Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue) {
            [void]$candidateHomes.Add($candidate.FullName)
        }
    }

    foreach ($candidateHome in ($candidateHomes | Select-Object -Unique)) {
        $javaExe = Join-Path $candidateHome 'bin\java.exe'
        $major = Get-JavaMajorVersionFromExecutable -JavaExecutable $javaExe
        if ($major -ge 17) {
            return $candidateHome
        }
    }
    return $null
}

function Ensure-Java17Runtime {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    $currentJava = Get-Command "java" -ErrorAction SilentlyContinue
    if ($currentJava) {
        $major = Get-JavaMajorVersionFromExecutable -JavaExecutable $currentJava.Source
        if ($major -ge 17) {
            return
        }
    }

    $javaHome = Find-Java17Home -RepoRoot $RepoRoot
    if (-not $javaHome) {
        throw "Java 17 or newer is required for the search/KG production-like smoke."
    }

    $env:JAVA_HOME = $javaHome
    $javaBin = Join-Path $javaHome 'bin'
    if (-not (($env:PATH -split ';') | Where-Object { $_ -eq $javaBin })) {
        $env:PATH = "$javaBin;$env:PATH"
    }
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
    return [ordered]@{
        jena_home = [string]$payload.jena_home
        fuseki_home = [string]$payload.fuseki_home
    }
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

function Get-ChildProcessIds {
    param([int]$ParentProcessId)

    if ($ParentProcessId -le 0) {
        return @()
    }
    $children = Get-CimInstance Win32_Process -Filter ("ParentProcessId = {0}" -f $ParentProcessId) -ErrorAction SilentlyContinue
    if ($null -eq $children) {
        return @()
    }
    return @($children | Select-Object -ExpandProperty ProcessId)
}

function Stop-ProcessTree {
    param(
        [int]$RootProcessId,
        [string]$Label
    )

    if ($RootProcessId -le 0) {
        return
    }

    $queue = New-Object System.Collections.Generic.Queue[int]
    $visited = New-Object System.Collections.Generic.HashSet[int]
    $discovered = New-Object System.Collections.Generic.List[int]
    $queue.Enqueue($RootProcessId)

    while ($queue.Count -gt 0) {
        $candidateId = $queue.Dequeue()
        if (-not $visited.Add($candidateId)) {
            continue
        }
        [void]$discovered.Add($candidateId)
        foreach ($childId in (Get-ChildProcessIds -ParentProcessId $candidateId)) {
            if (-not $visited.Contains($childId)) {
                $queue.Enqueue([int]$childId)
            }
        }
    }

    $orderedIds = @($discovered.ToArray())
    [Array]::Reverse($orderedIds)
    foreach ($targetId in $orderedIds) {
        try {
            $proc = Get-Process -Id $targetId -ErrorAction SilentlyContinue
            if ($null -eq $proc) {
                continue
            }
            Stop-Process -Id $targetId -Force -ErrorAction Stop
        } catch {
            Write-Warning ("Unable to stop {0} process {1}: {2}" -f $Label, $targetId, $_.Exception.Message)
        }
    }
}

function Stop-SmokeApi {
    param([Parameter(Mandatory = $true)][string]$ApiStopScript)

    try {
        & $ApiStopScript
    } catch {
        Write-Warning ("API stop helper raised an error: {0}" -f $_.Exception.Message)
    }
}

function Wait-ForFusekiHealth {
    param(
        [Parameter(Mandatory = $true)][string]$PwshExecutable,
        [Parameter(Mandatory = $true)][string]$ProbeScript,
        [Parameter(Mandatory = $true)][string]$FusekiEndpoint,
        [Parameter(Mandatory = $true)][string]$HealthReportPath,
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process,
        [string]$StdOutPath = "",
        [string]$StdErrPath = "",
        [switch]$RequireTextQuery,
        [string]$TextQuery = "",
        [int]$DeadlineSeconds = 90
    )

    $deadline = (Get-Date).AddSeconds($DeadlineSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $args = @('-File', $ProbeScript, '-FusekiUrl', $FusekiEndpoint, '-ReportPath', $HealthReportPath)
            if ($RequireTextQuery) {
                $args += @('-RequireTextQuery', '-TextQuery', $TextQuery)
            }
            Invoke-CheckedCommand $PwshExecutable @args
            return
        } catch {
            if ($Process.HasExited) {
                $stderrTail = if ($StdErrPath -and (Test-Path $StdErrPath)) {
                    (Get-Content $StdErrPath -Tail 80) -join "`n"
                } else {
                    ""
                }
                $stdoutTail = if ($StdOutPath -and (Test-Path $StdOutPath)) {
                    (Get-Content $StdOutPath -Tail 80) -join "`n"
                } else {
                    ""
                }
                throw "Fuseki process exited before health checks passed. stderr tail:`n$stderrTail`nstdout tail:`n$stdoutTail"
            }
            Start-Sleep -Milliseconds 750
        }
    }
    throw "Timed out waiting for Fuseki health checks to pass."
}

function Invoke-HttpJson {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [string]$Method = 'GET',
        [string]$Body = '',
        [string]$ContentType = 'application/json'
    )

    $headers = @{}
    if ($ContentType) {
        $headers['Content-Type'] = $ContentType
    }
    $response = if ($Body) {
        Invoke-WebRequest -Uri $Uri -Method $Method -Headers $headers -Body $Body -UseBasicParsing -SkipHttpErrorCheck -TimeoutSec 20
    } else {
        Invoke-WebRequest -Uri $Uri -Method $Method -Headers $headers -UseBasicParsing -SkipHttpErrorCheck -TimeoutSec 20
    }
    $json = $null
    if ($response.Content) {
        $json = $response.Content | ConvertFrom-Json
    }
    return [ordered]@{
        status_code = [int]$response.StatusCode
        json = $json
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Resolve-PythonInterpreter
$pwshExe = Resolve-PwshExecutable
$tools = Resolve-JenaFusekiHomes -PythonExecutable $python -RepoRoot $repoRoot
$apiStartScript = Join-Path $PSScriptRoot "api-start.ps1"
$apiStopScript = Join-Path $PSScriptRoot "api-stop.ps1"
$fusekiServiceScript = Join-Path $repoRoot "scripts\ops\windows-fuseki-service.ps1"
$fusekiProbeScript = Join-Path $repoRoot "scripts\health\fuseki-probe.ps1"

Ensure-Java17Runtime -RepoRoot $repoRoot

$runtimeRoot = Join-Path $env:TEMP ("earcrawler-search-kg-prodlike-" + [guid]::NewGuid().ToString("N"))
$programDataRoot = Join-Path $runtimeRoot "fuseki"
$configRoot = Join-Path $programDataRoot "config"
$databaseRoot = Join-Path $programDataRoot "databases\tdb2-text"
$luceneRoot = Join-Path $programDataRoot "databases\lucene"
$logRoot = Join-Path $programDataRoot "logs"
$configPath = Join-Path $configRoot "tdb2-text-validation-query.ttl"
$healthReportPath = Join-Path $logRoot "health-fuseki.txt"
$stdoutPath = Join-Path $logRoot "fuseki.out.log"
$stderrPath = Join-Path $logRoot "fuseki.err.log"
$fusekiUrl = "http://{0}:{1}/{2}/query" -f $FusekiHost, $FusekiPort, $DatasetName
$fusekiUpdateUrl = "http://{0}:{1}/{2}/update" -f $FusekiHost, $FusekiPort, $DatasetName
$baseUrl = "http://{0}:{1}" -f $ApiHost, $Port

$savedEnv = @{
    EARCRAWLER_API_ENABLE_SEARCH = $env:EARCRAWLER_API_ENABLE_SEARCH
    EARCRAWLER_ENABLE_KG_EXPANSION = $env:EARCRAWLER_ENABLE_KG_EXPANSION
    EARCRAWLER_KG_EXPANSION_PROVIDER = $env:EARCRAWLER_KG_EXPANSION_PROVIDER
    EARCRAWLER_KG_EXPANSION_FAILURE_POLICY = $env:EARCRAWLER_KG_EXPANSION_FAILURE_POLICY
    EARCRAWLER_KG_EXPANSION_MODE = $env:EARCRAWLER_KG_EXPANSION_MODE
    EARCRAWLER_KG_EXPANSION_FUSEKI_HEALTHCHECK = $env:EARCRAWLER_KG_EXPANSION_FUSEKI_HEALTHCHECK
    EARCRAWLER_FUSEKI_URL = $env:EARCRAWLER_FUSEKI_URL
}

$fusekiProcess = $null
$report = [ordered]@{
    schema_version = 'search-kg-prodlike-smoke.v1'
    generated_utc = (Get-Date).ToUniversalTime().ToString('o')
    runtime_shape = [ordered]@{
        api_base_url = $baseUrl
        fuseki_query_url = $fusekiUrl
        fuseki_update_url = $fusekiUpdateUrl
        config_path = $configPath
        database_root = $databaseRoot
        lucene_root = $luceneRoot
    }
    fuseki_health = [ordered]@{}
    search = [ordered]@{}
    kg_expansion = [ordered]@{}
    overall_status = 'failed'
    error = ''
}
$failure = ''

try {
    New-Item -ItemType Directory -Force -Path $configRoot, $databaseRoot, $luceneRoot, $logRoot | Out-Null

    & $fusekiServiceScript `
        -Action render-config `
        -ProgramDataRoot $programDataRoot `
        -ConfigRoot $configRoot `
        -DatabaseRoot $databaseRoot `
        -LuceneRoot $luceneRoot `
        -ConfigPath $configPath `
        -FusekiHost $FusekiHost `
        -FusekiPort $FusekiPort `
        -DatasetName $DatasetName `
        -EnableTextIndexValidation
    if ($LASTEXITCODE -ne 0) {
        throw "Fuseki validation config render failed."
    }

    $fusekiExe = Resolve-FusekiServerExecutable -FusekiHome ([string]$tools.fuseki_home)
    $fusekiProcess = Start-Process `
        -FilePath $fusekiExe `
        -ArgumentList @("--config=$configPath", "--localhost", "--port", $FusekiPort.ToString(), "--ping") `
        -WorkingDirectory ([string]$tools.fuseki_home) `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath

    Wait-ForFusekiHealth `
        -PwshExecutable $pwshExe `
        -ProbeScript $fusekiProbeScript `
        -FusekiEndpoint $fusekiUrl `
        -HealthReportPath $healthReportPath `
        -Process $fusekiProcess `
        -StdOutPath $stdoutPath `
        -StdErrPath $stderrPath `
        -DeadlineSeconds $TimeoutSeconds

    $validationGraph = @"
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dcterms: <http://purl.org/dc/terms/>

INSERT DATA {
  GRAPH <https://ear.example.org/graph/kg/validation-smoke> {
    <urn:ear:entity:validation-search-1> rdfs:label "Export Validation Entity" .

    <https://ear.example.org/resource/ear/section/EAR-736.2%28b%29>
      dcterms:identifier "EAR-736.2(b)" ;
      rdfs:label "Validation General Prohibitions" ;
      <https://ear.example.org/schema#mentions> <https://ear.example.org/resource/ear/section/EAR-740.1> .

    <https://ear.example.org/resource/ear/section/EAR-740.1>
      dcterms:identifier "EAR-740.1" ;
      rdfs:label "Validation License Exceptions" .
  }
}
"@
    $updateResponse = Invoke-WebRequest `
        -Uri $fusekiUpdateUrl `
        -Method Post `
        -Body $validationGraph `
        -ContentType 'application/sparql-update' `
        -UseBasicParsing `
        -SkipHttpErrorCheck `
        -TimeoutSec 20
    if ([int]$updateResponse.StatusCode -lt 200 -or [int]$updateResponse.StatusCode -ge 300) {
        throw "Fuseki validation graph seed failed with status $([int]$updateResponse.StatusCode)."
    }

    Wait-ForFusekiHealth `
        -PwshExecutable $pwshExe `
        -ProbeScript $fusekiProbeScript `
        -FusekiEndpoint $fusekiUrl `
        -HealthReportPath $healthReportPath `
        -Process $fusekiProcess `
        -StdOutPath $stdoutPath `
        -StdErrPath $stderrPath `
        -RequireTextQuery `
        -TextQuery 'Export Validation Entity' `
        -DeadlineSeconds $TimeoutSeconds

    $report.fuseki_health = [ordered]@{
        status = 'passed'
        report_path = $healthReportPath
        text_query = 'Export Validation Entity'
    }

    $env:EARCRAWLER_FUSEKI_URL = $fusekiUrl
    $env:EARCRAWLER_API_ENABLE_SEARCH = '1'
    $env:EARCRAWLER_ENABLE_KG_EXPANSION = '1'
    $env:EARCRAWLER_KG_EXPANSION_PROVIDER = 'fuseki'
    $env:EARCRAWLER_KG_EXPANSION_FAILURE_POLICY = 'error'
    $env:EARCRAWLER_KG_EXPANSION_MODE = 'always_on'
    $env:EARCRAWLER_KG_EXPANSION_FUSEKI_HEALTHCHECK = '1'

    & $apiStartScript -Host $ApiHost -Port $Port -FusekiUrl $fusekiUrl
    $searchResponse = Invoke-HttpJson -Uri "$baseUrl/v1/search?q=$([uri]::EscapeDataString('Export Validation Entity'))&limit=5"
    $searchIds = @()
    if ($searchResponse.json -and $searchResponse.json.results) {
        $searchIds = @($searchResponse.json.results | ForEach-Object { [string]$_.id })
    }
    $searchPassed = ($searchResponse.status_code -eq 200) -and ($searchIds -contains 'urn:ear:entity:validation-search-1')
    $report.search = [ordered]@{
        status = if ($searchPassed) { 'passed' } else { 'failed' }
        status_code = $searchResponse.status_code
        query = 'Export Validation Entity'
        expected_id = 'urn:ear:entity:validation-search-1'
        result_ids = $searchIds
        total = if ($searchResponse.json) { [int]($searchResponse.json.total ?? 0) } else { 0 }
    }

    $kgProbe = @"
import json
from earCrawler.rag.retrieval_runtime import expand_with_kg

rows = expand_with_kg(["EAR-736.2(b)"])
payload = {
    "rows": len(rows),
    "path_counts": [len(item.paths) for item in rows],
    "related_sections": [item.related_sections for item in rows],
}
print(json.dumps(payload))
"@
    $kgProbeRaw = & $python -c $kgProbe
    if ($LASTEXITCODE -ne 0) {
        throw "KG expansion success probe failed."
    }
    $kgPayload = $kgProbeRaw | ConvertFrom-Json
    $kgPassed = ([int]$kgPayload.rows -ge 1)
    $report.kg_expansion = [ordered]@{
        status = if ($kgPassed) { 'passed' } else { 'failed' }
        section_id = 'EAR-736.2(b)'
        rows = [int]$kgPayload.rows
        path_counts = @($kgPayload.path_counts)
        related_sections = @($kgPayload.related_sections)
    }

    if (-not $searchPassed -or -not $kgPassed) {
        throw "One or more search/KG production-like checks failed."
    }
    $report.overall_status = 'passed'
}
catch {
    $failure = $_.Exception.Message
}
finally {
    Stop-SmokeApi -ApiStopScript $apiStopScript
    if ($fusekiProcess -and -not $fusekiProcess.HasExited) {
        Stop-ProcessTree -RootProcessId $fusekiProcess.Id -Label 'search/kg prodlike Fuseki'
    }
    foreach ($entry in $savedEnv.GetEnumerator()) {
        if ($null -eq $entry.Value) {
            Remove-Item "Env:$($entry.Key)" -ErrorAction SilentlyContinue
        } else {
            Set-Item "Env:$($entry.Key)" $entry.Value
        }
    }

    if ($failure) {
        $report.overall_status = 'failed'
        $report.error = $failure
    }

    $reportDir = Split-Path -Parent $ReportPath
    if ($reportDir) {
        New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -Path $ReportPath -Encoding UTF8

    Remove-Item -Recurse -Force $runtimeRoot -ErrorAction SilentlyContinue
}

if ($failure) {
    throw "Search/KG production-like smoke failed: $failure. See $ReportPath."
}

Write-Host "Search/KG production-like smoke report written to $ReportPath"
