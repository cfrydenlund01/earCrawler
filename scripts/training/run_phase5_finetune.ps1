Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
    [string]$ConfigPath = "config/training_first_pass.example.json",
    [switch]$PrepareOnly,
    [string]$PythonExecutable = ""
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repoRoot

function Resolve-PythonCommand {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $false)][string]$ExplicitPython
    )
    if ($ExplicitPython) {
        return $ExplicitPython
    }
    if ($env:EARCTL_PYTHON) {
        return $env:EARCTL_PYTHON
    }
    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    return "py"
}

$python = Resolve-PythonCommand -RepoRoot $repoRoot -ExplicitPython $PythonExecutable
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
