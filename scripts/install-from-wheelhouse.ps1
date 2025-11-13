param([string]$LockFile = "requirements-win-lock.txt")

$repoRoot = Resolve-Path "$PSScriptRoot/.."
$wheelDir = Join-Path $repoRoot ".wheelhouse"

if (-not (Test-Path $wheelDir)) {
    throw "Wheelhouse directory not found at $wheelDir. Download hermetic-artifacts before installing."
}

pip install --no-index --find-links $wheelDir --require-hashes -r $LockFile
