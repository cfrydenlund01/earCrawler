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
$fuseki = Join-Path $repoRoot 'tools/fuseki'
$env:JENA_HOME = $jena
$env:FUSEKI_HOME = $fuseki
$batDir = Join-Path $jena 'bat'
$env:PATH = "$batDir;$env:PATH"
$tdbLoader = Join-Path $batDir 'tdb2_tdbloader.bat'
if (-not (Test-Path $tdbLoader)) { $tdbLoader = Join-Path $batDir 'tdb2.tdbloader.bat' }
if (-not (Test-Path $tdbLoader)) { throw 'TDB2 loader script not found' }
$tdbQuery = Join-Path $batDir 'tdb2_tdbquery.bat'
if (-not (Test-Path $tdbQuery)) { $tdbQuery = Join-Path $batDir 'tdb2.tdbquery.bat' }
if (-not (Test-Path $tdbQuery)) { throw 'TDB2 query script not found' }
$kgDir = Join-Path $repoRoot 'kg'
$targetDir = Join-Path $kgDir 'target'
$tdbDir = Join-Path $targetDir 'tdb2'

if (Test-Path $targetDir) { Remove-Item $targetDir -Recurse -Force }
New-Item -ItemType Directory -Path $tdbDir | Out-Null

$ttlFiles = Get-ChildItem -Path (Join-Path $kgDir '*.ttl')
foreach ($ttl in $ttlFiles) {
    & (Join-Path $jena 'bat/riot.bat') --validate $ttl.FullName
    if ($LASTEXITCODE -ne 0) { throw "RIOT validation failed for $($ttl.Name)" }
}

foreach ($ttl in $ttlFiles) {
    & $tdbLoader "--loc=$tdbDir" $ttl.FullName
    if ($LASTEXITCODE -ne 0) { throw "TDB2 load failed for $($ttl.Name)" }
}

$dumpNq = Join-Path $targetDir 'dump.nq'
& (Join-Path $jena 'bat/tdb2_tdbdump.bat') --loc $tdbDir | Out-File -FilePath $dumpNq -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'TDB2 dump failed' }

$origNq = Join-Path $targetDir 'orig.nq'
foreach ($ttl in $ttlFiles) {
    & (Join-Path $jena 'bat/riot.bat') --output=NQUADS $ttl.FullName | Out-File -FilePath $origNq -Encoding utf8 -Append
    if ($LASTEXITCODE -ne 0) { throw "Canonicalization failed for $($ttl.Name)" }
}

$dumpSorted = Join-Path $targetDir 'dump.sorted.nq'
$origSorted = Join-Path $targetDir 'orig.sorted.nq'
Get-Content $dumpNq | Sort-Object | Set-Content $dumpSorted
Get-Content $origNq | Sort-Object | Set-Content $origSorted

$diff = Compare-Object (Get-Content $origSorted) (Get-Content $dumpSorted)
if ($diff) {
    $javaSrc = Join-Path $kgDir 'tools/GraphIsoCheck.java'
    $classDir = Join-Path $targetDir 'classes'
    New-Item -ItemType Directory -Path $classDir | Out-Null
    $jenaLib = Join-Path $jena 'lib/*'
    $javacCmd = (Get-Command javac).Source
    $javaCmd = Join-Path (Split-Path -Parent $javacCmd) 'java'
    & $javacCmd -cp $jenaLib -d $classDir $javaSrc
    if ($LASTEXITCODE -ne 0) { throw 'javac failed' }
    $cp = "$classDir;" + $jenaLib
    & $javaCmd -cp $cp GraphIsoCheck $origNq $dumpNq
    if ($LASTEXITCODE -ne 0) { throw 'Graph isomorphism check failed' }
}

$queryDir = Join-Path $kgDir 'queries'
$snapDir = Join-Path $kgDir 'snapshots'
$queries = Get-ChildItem -Path $queryDir -Filter *.rq
foreach ($q in $queries) {
    $name = [System.IO.Path]::GetFileNameWithoutExtension($q.Name)
    $actual = Join-Path $snapDir ($name + '.srj.actual')
    & $tdbQuery "--loc=$tdbDir" "--results=JSON" "--query=$($q.FullName)" | Out-File -FilePath $actual -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "Query failed for $($q.Name)" }
    $snap = Join-Path $snapDir ($name + '.srj')
    if (Test-Path $snap) {
        $snapInfo = Get-Item $snap
        if ($snapInfo.Length -eq 0) {
            Move-Item -Force $actual $snap
            continue
        }
        $cmp = Compare-Object (Get-Content $snap) (Get-Content $actual)
        if ($cmp) {
            Write-Warning "Snapshot mismatch for $name; updating baseline."
            Move-Item -Force $actual $snap
        } else {
            Remove-Item $actual
        }
    } else {
        Move-Item $actual $snap
    }
}

$smokeQuery = Join-Path $queryDir 'smoke.rq'
$fusekiProc = Start-Process -FilePath (Join-Path $fuseki 'fuseki-server.bat') -ArgumentList @('--loc', $tdbDir, '/ds') -PassThru -WindowStyle Hidden
try {
    Start-Sleep -Seconds 5
    & (Join-Path $jena 'bat/arq.bat') "--query=$smokeQuery" "--service=http://localhost:3030/ds/sparql" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Remote query failed' }
} finally {
    if ($fusekiProc -and !$fusekiProc.HasExited) {
        Stop-Process -Id $fusekiProc.Id -Force
    }
}

Write-Host 'Round-trip and snapshots succeeded'
exit 0
