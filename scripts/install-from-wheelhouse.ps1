param([string]$LockFile = "requirements-win-lock.txt")

$repoRoot = (Resolve-Path "$PSScriptRoot/..").ProviderPath
$candidateDirs = @(
    Join-Path $repoRoot ".wheelhouse",
    Join-Path $repoRoot "hermetic-artifacts/.wheelhouse"
)

$wheelDir = $null
foreach ($candidate in $candidateDirs) {
    if (Test-Path $candidate) {
        $wheelDir = $candidate
        break
    }
}

if (-not $wheelDir) {
    $archive = Join-Path $repoRoot "hermetic-artifacts.zip"
    if (Test-Path $archive) {
        Expand-Archive -Path $archive -DestinationPath $repoRoot -Force
        foreach ($candidate in $candidateDirs) {
            if (Test-Path $candidate) {
                $wheelDir = $candidate
                break
            }
        }
    }
}

if (-not $wheelDir) {
    $expected = ($candidateDirs -join ", ")
    throw "Wheelhouse directory not found (looked in: $expected). Download hermetic-artifacts before installing."
}

pip install --no-index --find-links $wheelDir --require-hashes -r $LockFile
