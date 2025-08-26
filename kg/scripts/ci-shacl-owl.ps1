param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$jena = Join-Path $repoRoot 'tools/jena'
$fuseki = Join-Path $repoRoot 'tools/fuseki'
if (-not (Test-Path $jena)) { throw 'Jena not found at tools/jena' }
if (-not (Test-Path $fuseki)) { throw 'Fuseki not found at tools/fuseki' }

$kgDir = Join-Path $repoRoot 'kg'
$reportsDir = Join-Path $kgDir 'reports'
New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null

# Ensure shapes.ttl
$shapeDest = Join-Path $kgDir 'shapes.ttl'
$shapesCopied = $false
if (-not (Test-Path $shapeDest)) {
    $shapeSrc = Join-Path $repoRoot 'earCrawler/kg/shapes.ttl'
    Copy-Item $shapeSrc $shapeDest
    $shapesCopied = $true
}

# Collect data TTLs (excluding shapes)
$ttlFiles = Get-ChildItem -Path $kgDir -Filter *.ttl | Where-Object { $_.Name -ne 'shapes.ttl' }

# --- SHACL validation ---
$shacl = Join-Path $jena 'bin/shacl.bat'
$dataArgs = @()
foreach ($ttl in $ttlFiles) { $dataArgs += @('--data', $ttl.FullName) }
$shaclTtl = Join-Path $reportsDir 'shacl-report.ttl'
$shaclJson = Join-Path $reportsDir 'shacl-report.json'
& $shacl validate --shapes $shapeDest @dataArgs --report $shaclTtl --report-json $shaclJson | Out-Null
$shaclExit = $LASTEXITCODE
$shaclInfo = Get-Content -Raw $shaclJson | ConvertFrom-Json
$conf = $shaclInfo.conforms
Set-Content -Path (Join-Path $reportsDir 'shacl-conforms.txt') -Value ($conf.ToString().ToLowerInvariant())
if ($shaclExit -ne 0 -or -not $conf) {
    if ($shapesCopied) { Remove-Item $shapeDest -Force }
    Write-Error 'SHACL validation failed'
    exit 1
}

# --- OWL smoke tests ---
$javaSrc = Join-Path $kgDir 'tools/OwlAsk.java'
$classDir = Join-Path $kgDir 'target/owlask'
if (Test-Path $classDir) { Remove-Item $classDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $classDir | Out-Null
$jenaLib = Join-Path $jena 'lib/*'
& javac -cp $jenaLib -d $classDir $javaSrc
if ($LASTEXITCODE -ne 0) {
    if ($shapesCopied) { Remove-Item $shapeDest -Force }
    throw 'javac failed'
}
$cp = "$classDir;$jenaLib"

$fixture = Join-Path $kgDir 'testdata/reasoner_smoke.ttl'
$dataFiles = $ttlFiles.FullName + $fixture

$queries = @(
    @{ name = 'subclass'; file = Join-Path $kgDir 'queries/reasoner_ask_subclass.rq'; explanation = 'Subclass inference via rdfs:subClassOf'; },
    @{ name = 'domain-range'; file = Join-Path $kgDir 'queries/reasoner_ask_domain_range.rq'; explanation = 'Domain and range infer types'; },
    @{ name = 'equivalence'; file = Join-Path $kgDir 'queries/reasoner_ask_equivalence.rq'; explanation = 'Equivalent classes propagate type'; }
)

$results = @()
$fail = $false
foreach ($q in $queries) {
    & java -cp $cp OwlAsk $q.file @dataFiles | Out-Null
    $passed = $LASTEXITCODE -eq 0
    $results += [pscustomobject]@{ name = $q.name; passed = $passed; explanation = $q.explanation }
    if (-not $passed) { $fail = $true }
}

$results | ConvertTo-Json | Set-Content (Join-Path $reportsDir 'owl-smoke.json')

if ($shapesCopied) { Remove-Item $shapeDest -Force }

if ($fail) {
    Write-Error 'OWL smoke checks failed'
    exit 1
}

Write-Host 'SHACL validation and OWL smoke checks succeeded'
exit 0
