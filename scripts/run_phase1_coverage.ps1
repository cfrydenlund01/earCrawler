Param(
  [Parameter(Mandatory = $false)]
  [string]$Manifest = "eval/manifest.json",

  [Parameter(Mandatory = $false)]
  [string]$Corpus = "data/faiss/retrieval_corpus.jsonl",

  [Parameter(Mandatory = $false)]
  [string]$DatasetId = "all",

  [Parameter(Mandatory = $false)]
  [int]$RetrievalK = 10,

  [Parameter(Mandatory = $false)]
  [double]$MaxMissingRate = 0.10,

  [Parameter(Mandatory = $false)]
  [string]$OutBase = "dist/eval/coverage_runs",

  [Parameter(Mandatory = $false)]
  [string]$PythonExe = "",

  [Parameter(Mandatory = $false)]
  [string]$IndexPath = "",

  [Parameter(Mandatory = $false)]
  [string]$ModelName = ""
)

$ErrorActionPreference = "Stop"

function Resolve-PythonExe([string]$Value) {
  if ($Value -and $Value.Trim()) {
    return $Value
  }
  if (Test-Path ".venv\\Scripts\\python.exe") {
    return ".venv\\Scripts\\python.exe"
  }
  return "python"
}

function New-UniqueDir([string]$BaseDir, [string]$Stamp) {
  $root = Join-Path $BaseDir $Stamp
  $candidate = $root
  $i = 1
  while (Test-Path $candidate) {
    $i++
    $candidate = "${root}_$('{0:d2}' -f $i)"
  }
  New-Item -ItemType Directory -Force -Path $candidate | Out-Null
  return $candidate
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outDir = New-UniqueDir -BaseDir $OutBase -Stamp $timestamp

$py = Resolve-PythonExe -Value $PythonExe

$reportPath = Join-Path $outDir "fr_coverage_report.json"
$summaryPath = Join-Path $outDir "fr_coverage_summary.json"
$blockerPath = Join-Path $outDir "phase1_blocker.md"
$logPath = Join-Path $outDir "fr_coverage_run.log"
$cmdHistory = Join-Path $outDir "command_history.txt"
$envFreeze = Join-Path $outDir "env_freeze.txt"

@(
  "timestamp=$timestamp"
  "outDir=$outDir"
  "python=$py"
  "manifest=$Manifest"
  "corpus=$Corpus"
  "dataset_id=$DatasetId"
  "retrieval_k=$RetrievalK"
  "max_missing_rate=$MaxMissingRate"
  "EARCRAWLER_FAISS_INDEX=$IndexPath"
  "EARCRAWLER_FAISS_MODEL=$ModelName"
) | Out-File -Encoding ascii $cmdHistory

try {
  $head = (git rev-parse HEAD 2>$null)
  if ($LASTEXITCODE -eq 0 -and $head) {
    "git_head=$head" | Out-File -Append -Encoding ascii $cmdHistory
    $status = (git status --porcelain 2>$null)
    "git_status_porcelain=" | Out-File -Append -Encoding ascii $cmdHistory
    $status | Out-File -Append -Encoding ascii $cmdHistory
  }
} catch { }

& $py -V 2>&1 | Out-File -Encoding ascii (Join-Path $outDir "python_version.txt")
& $py -m pip freeze 2>&1 | Out-File -Encoding utf8 $envFreeze

$oldIndex = $env:EARCRAWLER_FAISS_INDEX
$oldModel = $env:EARCRAWLER_FAISS_MODEL
if ($IndexPath -and $IndexPath.Trim()) {
  $env:EARCRAWLER_FAISS_INDEX = $IndexPath
}
if ($ModelName -and $ModelName.Trim()) {
  $env:EARCRAWLER_FAISS_MODEL = $ModelName
}

$args = @(
  "-m", "earCrawler.cli",
  "eval", "fr-coverage",
  "--manifest", $Manifest,
  "--corpus", $Corpus,
  "--dataset-id", $DatasetId,
  "--retrieval-k", "$RetrievalK",
  "--max-missing-rate", "$MaxMissingRate",
  "--out", $reportPath,
  "--summary-out", $summaryPath,
  "--write-blocker-note", $blockerPath
)
"command=$py $($args -join ' ')" | Out-File -Append -Encoding ascii $cmdHistory

$exitCode = 0
try {
  & $py @args 2>&1 | Tee-Object -FilePath $logPath
  $exitCode = $LASTEXITCODE
} finally {
  $env:EARCRAWLER_FAISS_INDEX = $oldIndex
  $env:EARCRAWLER_FAISS_MODEL = $oldModel
}

if ($exitCode -ne 0) {
  Write-Host ""
  Write-Host "Phase 1 coverage gate FAILED (exit $exitCode)."
  Write-Host "Artifacts: $outDir"
  Write-Host "Blocker note: $blockerPath"
  exit $exitCode
}

Write-Host ""
Write-Host "Phase 1 coverage gate PASSED."
Write-Host "Artifacts: $outDir"
exit 0

