Param(
  [Parameter(Mandatory = $false)]
  [string]$SnapshotId = "",

  [Parameter(Mandatory = $false)]
  [string]$SnapshotPath = "",

  [Parameter(Mandatory = $false)]
  [double]$MaxMissingRate = 0.35,

  [Parameter(Mandatory = $false)]
  [int]$MultihopMaxItems = 10,

  [Parameter(Mandatory = $false)]
  [int]$BundleEvalMaxItems = 25,

  [Parameter(Mandatory = $false)]
  [switch]$AllowDirty,

  [Parameter(Mandatory = $false)]
  [switch]$SkipIdCheck,

  [Parameter(Mandatory = $false)]
  [switch]$SkipMultihop,

  [Parameter(Mandatory = $false)]
  [switch]$SkipBundle,

  [Parameter(Mandatory = $false)]
  [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

function Resolve-PythonExe([string]$Value) {
  if ($Value -and $Value.Trim()) {
    return $Value
  }
  if (Test-Path ".venv\\Scripts\\python.exe") {
    return ".venv\\Scripts\\python.exe"
  }
  if (Get-Command py -ErrorAction SilentlyContinue) {
    return "py"
  }
  return "python"
}

function Require-ExitCode([string]$Label) {
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed (exit $LASTEXITCODE)."
  }
}

function Require-CleanGit() {
  $status = (git status --porcelain 2>$null)
  if ($LASTEXITCODE -ne 0) {
    throw "git status failed; ensure git is installed and the repo is initialized."
  }
  if ($status -and $status.Trim()) {
    throw ("Working tree not clean. Commit/stash changes or re-run with -AllowDirty.`n" + $status)
  }
}

function Resolve-Snapshot([string]$Id, [string]$PathValue) {
  if ($PathValue -and $PathValue.Trim()) {
    return @{ SnapshotId = $Id; SnapshotPath = $PathValue }
  }
  $resolvedId = $Id
  if (-not ($resolvedId -and $resolvedId.Trim())) {
    $latest = Get-ChildItem "snapshots\\offline" -Directory -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 1
    if (-not $latest) {
      throw "No snapshots found under snapshots/offline. Provide -SnapshotId or -SnapshotPath."
    }
    $resolvedId = $latest.Name
  }
  $resolvedPath = Join-Path (Join-Path "snapshots\\offline" $resolvedId) "snapshot.jsonl"
  return @{ SnapshotId = $resolvedId; SnapshotPath = $resolvedPath }
}

$py = Resolve-PythonExe -Value $PythonExe
Write-Host ("python=" + $py)

if (-not $AllowDirty) {
  Require-CleanGit
}

$snap = Resolve-Snapshot -Id $SnapshotId -PathValue $SnapshotPath
$SnapshotId = $snap.SnapshotId
$SnapshotPath = $snap.SnapshotPath

if (-not (Test-Path $SnapshotPath)) {
  throw "Snapshot payload not found: $SnapshotPath"
}

Write-Host ""
Write-Host "1) Validate offline snapshot + manifest"
& $py -m earCrawler.cli rag-index validate-snapshot --snapshot $SnapshotPath
Require-ExitCode "snapshot validation"

Write-Host ""
Write-Host "2) Validate eval datasets (schema + references)"
& $py -m eval.validate_datasets --manifest (Join-Path "eval" "manifest.json")
Require-ExitCode "dataset validation"

Write-Host ""
Write-Host "3) Run v2 fr-coverage gate (phase 1)"
pwsh scripts\\run_phase1_coverage.ps1 -MaxMissingRate $MaxMissingRate -PythonExe $py
Require-ExitCode "phase1 fr-coverage"

if (-not $SkipIdCheck) {
  Write-Host ""
  Write-Host "4) ID consistency check (datasets vs corpus vs optional KG)"
  New-Item -ItemType Directory -Force -Path dist\\checks | Out-Null
  & $py scripts\\eval\\check_id_consistency.py `
    --manifest (Join-Path "eval" "manifest.json") `
    --corpus (Join-Path "data" "faiss" "retrieval_corpus.jsonl") `
    --dataset-id all `
    --out-json (Join-Path "dist" "checks" "id_consistency.json") `
    --out-md (Join-Path "dist" "checks" "id_consistency.md")
  Require-ExitCode "id consistency"
}

if (-not $SkipMultihop) {
  Write-Host ""
  Write-Host "5) Multihop ablation compare (offline stubbed)"
  & $py scripts\\eval\\run_multihop_ablation_compare_stubbed.py --max-items $MultihopMaxItems
  Require-ExitCode "multihop ablation compare"
}

if (-not $SkipBundle) {
  Write-Host ""
  Write-Host "6) Build results bundle (archival + diff-friendly scorecard)"
  & $py scripts\\reporting\\build_results_bundle.py `
    --snapshot-id $SnapshotId `
    --index-meta (Join-Path "data" "faiss" "index.meta.json") `
    --corpus (Join-Path "data" "faiss" "retrieval_corpus.jsonl") `
    --max-missing-rate $MaxMissingRate `
    --eval-mode golden_offline `
    --eval-dataset-id golden_phase2.v1 `
    --eval-max-items $BundleEvalMaxItems `
    --require-eval
  Require-ExitCode "results bundle build"
}

Write-Host ""
Write-Host "DONE-DONE: PASS"
exit 0
