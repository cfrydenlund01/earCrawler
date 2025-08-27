param(
    [ValidateSet('rdfs','owlmini')]
    [string]$Mode = 'rdfs',
    [string]$AssemblerPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
 
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
& python -c "import pathlib, importlib.util; repo = pathlib.Path(r'$repoRoot'); spec = importlib.util.spec_from_file_location('jena_tools', repo / 'earCrawler/utils/jena_tools.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); mod.ensure_jena(); mod.ensure_fuseki()" | Out-Null
$jena = Join-Path $repoRoot 'tools/jena'
$fuseki = Join-Path $repoRoot 'tools/fuseki'
if (-not (Test-Path $jena)) { throw 'Jena not found at tools/jena' }
if (-not (Test-Path $fuseki)) { throw 'Fuseki not found at tools/fuseki' }
$env:JENA_HOME = $jena
$env:FUSEKI_HOME = $fuseki
$batDir = Join-Path $jena 'bat'
$env:PATH = "$batDir;$env:PATH"

$tdbLoader = Join-Path $batDir 'tdb2_tdbloader.bat'
if (-not (Test-Path $tdbLoader)) { $tdbLoader = Join-Path $batDir 'tdb2.tdbloader.bat' }
if (-not (Test-Path $tdbLoader)) { throw 'TDB2 loader script not found' }

$kgDir = Join-Path $repoRoot 'kg'
$targetDir = Join-Path $kgDir 'target'
$tdbDir = Join-Path $targetDir 'tdb2'
if (Test-Path $targetDir) { Remove-Item $targetDir -Recurse -Force }
New-Item -ItemType Directory -Path $tdbDir | Out-Null

$ttlFiles = Get-ChildItem -Path $kgDir -Filter *.ttl | Where-Object { $_.Name -ne 'shapes.ttl' }
$fixture = Join-Path $kgDir 'testdata/reasoner_smoke.ttl'
$allTtls = $ttlFiles.FullName + $fixture
foreach ($ttl in $allTtls) {
    & $tdbLoader --loc $tdbDir $ttl
    if ($LASTEXITCODE -ne 0) { throw "TDB2 load failed for $ttl" }
}

if ($AssemblerPath) {
    $assembler = $AssemblerPath
} else {
    $assembler = if ($Mode -eq 'rdfs') { Join-Path $kgDir 'assembler/tdb2-inference-rdfs.ttl' } else { Join-Path $kgDir 'assembler/tdb2-inference-owlmini.ttl' }
}
$assembler = Resolve-Path $assembler

$reportsDir = Join-Path $kgDir 'reports'
New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null

$server = Start-Process -FilePath (Join-Path $fuseki 'fuseki-server.bat') -ArgumentList @('--config', $assembler) -PassThru -WindowStyle Hidden
$ready = $false
for ($i=0; $i -lt 30; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing http://localhost:3030/\$/ping | Out-Null
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force }
    Write-Error 'Fuseki server failed to start'
    exit 1
}

$endpoint = 'http://localhost:3030/ds-inf/sparql'
$arq = Join-Path $batDir 'arq.bat'
$queries = @(
    @{ name = 'subclass'; file = Join-Path $kgDir 'queries/infer_subclass_ask.rq'; details = 'Subclass inference via rdfs:subClassOf'; },
    @{ name = 'domain-range'; file = Join-Path $kgDir 'queries/infer_domain_range_ask.rq'; details = 'Domain and range infer types'; },
    @{ name = 'equivalence'; file = Join-Path $kgDir 'queries/infer_equivalence_ask.rq'; details = 'Equivalent classes propagate type'; }
)

$results = @()
$fail = $false
foreach ($q in $queries) {
    $out = & $arq --query $q.file --service $endpoint --results=JSON 2>$null
    if ($LASTEXITCODE -ne 0) {
        $passed = $false
        $details = 'query failed'
    } else {
        $json = $out | ConvertFrom-Json
        $passed = [bool]$json.boolean
        $details = $q.details
    }
    $results += [pscustomobject]@{ name = $q.name; passed = $passed; details = $details }
    if (-not $passed) { $fail = $true }
}

$results | ConvertTo-Json | Set-Content (Join-Path $reportsDir "inference-$Mode.json")
$results | ForEach-Object { "$($_.name): $($_.passed)" } | Set-Content (Join-Path $reportsDir "inference-$Mode.txt")

$selectQuery = Join-Path $kgDir 'queries/infer_report_select.rq'
$selectOut = & $arq --query $selectQuery --service $endpoint --results=JSON 2>$null
$selectPath = Join-Path $reportsDir "inference-$Mode-select.srj"
$selectOut | Out-File -FilePath $selectPath -Encoding utf8

if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force }

if ($fail) {
    Write-Error 'Inference ASK checks failed'
    exit 1
}
Write-Host 'Inference smoke succeeded'
exit 0
