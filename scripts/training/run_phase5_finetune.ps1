Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
    [string]$ConfigPath = "config/training_first_pass.example.json",
    [switch]$PrepareOnly
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repoRoot

$python = if ($env:EARCTL_PYTHON) { $env:EARCTL_PYTHON } else { "py" }
$cmd = @(
    "scripts/training/run_phase5_finetune.py",
    "--config", $ConfigPath
)

if ($PrepareOnly) {
    $cmd += "--prepare-only"
}

& $python @cmd
if ($LASTEXITCODE -ne 0) {
    throw "Phase 5.3 training run failed (exit $LASTEXITCODE)."
}
