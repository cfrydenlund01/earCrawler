param(
    [int]$Port = 0,
    [int]$TimeoutSeconds = 45,
    [string]$ReportPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (-not $ReportPath) {
    $ReportPath = Join-Path $repoRoot 'kg/reports/text-search-smoke.json'
}

function Resolve-KgPython {
    if ($env:EARCTL_PYTHON -and (Test-Path $env:EARCTL_PYTHON)) {
        return (Resolve-Path $env:EARCTL_PYTHON).Path
    }
    foreach ($name in 'python', 'python.exe', 'python3', 'python3.exe') {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    $launcher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $exe = & $launcher.Source -3 -c "import sys; print(sys.executable)"
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch {}
    }
    throw 'Python interpreter not found. Set EARCTL_PYTHON or ensure python is on PATH.'
}

function Get-FreeTcpPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return $listener.LocalEndpoint.Port
    } finally {
        $listener.Stop()
    }
}

$python = Resolve-KgPython
$bootstrap = @"
import pathlib, sys
repo = pathlib.Path(r'{0}')
sys.path.insert(0, str(repo))
from earCrawler.utils import jena_tools, fuseki_tools
jena_tools.ensure_jena()
fuseki_tools.ensure_fuseki()
"@ -f $repoRoot
& $python -c $bootstrap | Out-Null

$jenaHome = Join-Path $repoRoot 'tools/jena'
$fusekiHome = Join-Path $repoRoot 'tools/fuseki'
$env:JENA_HOME = $jenaHome
$env:FUSEKI_HOME = $fusekiHome

if ($Port -le 0) {
    $Port = Get-FreeTcpPort
}

$targetDir = Join-Path $repoRoot 'kg/target/text-search-smoke'
if (Test-Path $targetDir) {
    Remove-Item -Path $targetDir -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $targetDir 'tdb2') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $targetDir 'lucene') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $targetDir 'logs') -Force | Out-Null

$assemblerPath = Join-Path $targetDir 'tdb2-text-smoke.ttl'
@'
@prefix : <#> .
@prefix fuseki: <http://jena.apache.org/fuseki#> .
@prefix tdb2: <http://jena.apache.org/2016/tdb#> .
@prefix ja: <http://jena.hpl.hp.com/2005/11/Assembler#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix text: <http://jena.apache.org/text#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

[] rdf:type fuseki:Server ;
   fuseki:services (
      [ rdf:type fuseki:Service ;
        fuseki:name              "ds" ;
        fuseki:serviceQuery      "sparql" ;
        fuseki:serviceUpdate     "update" ;
        fuseki:dataset           :dataset
      ]
   ) .

:dataset rdf:type text:TextDataset ;
    text:dataset :tdb_dataset ;
    text:index :text_index .

:tdb_dataset rdf:type tdb2:DatasetTDB2 ;
    tdb2:location "file:./kg/target/text-search-smoke/tdb2" ;
    tdb2:unionDefaultGraph true ;
    tdb2:requireWritePermission true .

:text_index rdf:type text:TextIndexLucene ;
    text:directory "file:./kg/target/text-search-smoke/lucene" ;
    text:entityMap :entity_map .

:entity_map rdf:type text:EntityMap ;
    text:entityField "entity" ;
    text:defaultField "label" ;
    text:map (
        [ text:field "label" ;
          text:predicate rdfs:label ]
    ) .
'@ | Set-Content -Path $assemblerPath -Encoding ascii

$fusekiExe = Join-Path $fusekiHome 'fuseki-server.bat'
if (-not (Test-Path $fusekiExe)) {
    $fusekiExe = Join-Path $fusekiHome 'fuseki-server'
}
if (-not (Test-Path $fusekiExe)) {
    throw 'Fuseki server launcher not found under tools/fuseki'
}

$stdoutPath = Join-Path $targetDir 'logs/fuseki.out.log'
$stderrPath = Join-Path $targetDir 'logs/fuseki.err.log'
$fusekiProc = Start-Process `
    -FilePath $fusekiExe `
    -ArgumentList @('--config', $assemblerPath, '--port', "$Port", '--localhost') `
    -WorkingDirectory $fusekiHome `
    -PassThru `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath

try {
    $base = "http://127.0.0.1:$Port"
    $pingUri = "$base/$/ping"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        if ($fusekiProc.HasExited) {
            throw "Fuseki exited early. See $stderrPath"
        }
        try {
            $resp = Invoke-WebRequest -Uri $pingUri -TimeoutSec 5
            if ($resp.StatusCode -eq 200) {
                $healthy = $true
                break
            }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    if (-not $healthy) {
        throw "Fuseki did not become healthy in ${TimeoutSeconds}s. See $stderrPath"
    }

    $update = @'
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
INSERT DATA {
  <urn:ear:entity:smoke-1> rdfs:label "Export Control Example" .
  <urn:ear:entity:smoke-2> rdfs:label "Sanctions Demo Entity" .
}
'@
    Invoke-RestMethod `
        -Uri "$base/ds/update" `
        -Method Post `
        -ContentType 'application/sparql-update' `
        -Body $update `
        -TimeoutSec 15 | Out-Null

    $apiCheck = @'
import json
import pathlib
import sys

from fastapi.testclient import TestClient

from service.api_server import create_app
from service.api_server.config import ApiSettings

endpoint = sys.argv[1]
report_path = pathlib.Path(sys.argv[2])

settings = ApiSettings(fuseki_url=endpoint)
app = create_app(settings=settings)
with TestClient(app) as client:
    response = client.get("/v1/search", params={"q": "Export", "limit": 5, "offset": 0})
    if response.status_code != 200:
        raise SystemExit(f"/v1/search returned {response.status_code}: {response.text}")
    payload = response.json()
    if payload.get("total", 0) < 1:
        raise SystemExit(f"/v1/search returned no hits: {payload}")
    ids = [row.get("id") for row in payload.get("results", [])]
    if "urn:ear:entity:smoke-1" not in ids:
        raise SystemExit(f"seeded entity not returned by /v1/search: {payload}")

report = {
    "passed": True,
    "endpoint": endpoint,
    "query": "Export",
    "payload": payload,
}
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
'@
    $sparqlEndpoint = "$base/ds/sparql"
    & $python -c $apiCheck $sparqlEndpoint $ReportPath
    if ($LASTEXITCODE -ne 0) {
        throw "API text-search smoke check failed against $sparqlEndpoint"
    }
} finally {
    if ($fusekiProc -and -not $fusekiProc.HasExited) {
        Stop-Process -Id $fusekiProc.Id -Force
    }
}

Write-Host "Text search smoke succeeded (report: $ReportPath)"
exit 0
