param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
function Resolve-KgPython {
    if ($env:EARCTL_PYTHON) {
        return $env:EARCTL_PYTHON
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return 'py'
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return 'python'
    }
    throw 'Python interpreter not found. Set EARCTL_PYTHON or ensure py/python is on PATH.'
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
$jena = Join-Path $repoRoot 'tools/jena'
$batDir = Join-Path $jena 'bat'
$env:PATH = "$batDir;$env:PATH"

$kgDir = Join-Path $repoRoot 'kg'
$provDir = Join-Path $kgDir 'prov'
$reportsDir = Join-Path $kgDir 'reports'
New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null

$provTtl = Join-Path $provDir 'prov.ttl'
if (-not (Test-Path $provTtl)) { throw 'provenance TTL missing' }
& (Join-Path $batDir 'riot.bat') --validate $provTtl
if ($LASTEXITCODE -ne 0) { throw 'RIOT validation failed' }

$tdbDir = Join-Path $kgDir 'target/prov-tdb'
if (Test-Path $tdbDir) { Remove-Item $tdbDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $tdbDir | Out-Null
$loader = Join-Path $batDir 'tdb2_tdbloader.bat'
if (-not (Test-Path $loader)) { $loader = Join-Path $batDir 'tdb2.tdbloader.bat' }
$query = Join-Path $batDir 'tdb2_tdbquery.bat'
if (-not (Test-Path $query)) { $query = Join-Path $batDir 'tdb2.tdbquery.bat' }

$domainTtl = Join-Path $kgDir 'ear_triples.ttl'
foreach ($ttl in @($domainTtl, $provTtl)) {
    & (Join-Path $batDir 'riot.bat') --validate $ttl
    if ($LASTEXITCODE -ne 0) { throw "RIOT validation failed for $ttl" }
    & $loader "--loc=$tdbDir" $ttl
    if ($LASTEXITCODE -ne 0) { throw "TDB2 load failed for $ttl" }
}

$queries = @(
    @{ name = 'lineage-min-required'; file = Join-Path $kgDir 'queries/lineage_min_required.rq'; type = 'count'; },
    @{ name = 'lineage-activity-integrity'; file = Join-Path $kgDir 'queries/lineage_activity_integrity.rq'; type = 'ask'; },
    @{ name = 'lineage-source-consistency'; file = Join-Path $kgDir 'queries/lineage_source_consistency.rq'; type = 'select'; }
)

foreach ($q in $queries) {
    $out = Join-Path $reportsDir ($q.name + '.srj')
    & $query "--loc=$tdbDir" "--results=JSON" "--query=$($q.file)" | Out-File -FilePath $out -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "Query failed for $($q.name)" }
    if ($q.type -eq 'count') {
        $info = Get-Content $out | ConvertFrom-Json
        $cnt = [int]$info.results.bindings[0].cnt.value
        Set-Content -Path (Join-Path $reportsDir ($q.name + '.txt')) -Value $cnt
        if ($cnt -ne 0) { throw 'Provenance minimum check failed' }
    } elseif ($q.type -eq 'ask') {
        $info = Get-Content $out | ConvertFrom-Json
        $bool = [bool]$info.boolean
        Set-Content -Path (Join-Path $reportsDir ($q.name + '.txt')) -Value $bool
        if ($bool) { throw 'Activity integrity check failed' }
    }
}

Write-Host 'Provenance checks succeeded'
exit 0
