param([string]$LockFile = "requirements-win-lock.txt")

$repoRoot = Resolve-Path "$PSScriptRoot/.."
$wheelDir = Join-Path $repoRoot ".wheelhouse"

pip install --no-index --find-links $wheelDir --require-hashes -r $LockFile
