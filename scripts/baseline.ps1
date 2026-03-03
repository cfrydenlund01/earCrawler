param(
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-PythonExe([string]$Value) {
    if ($Value -and $Value.Trim()) {
        return $Value
    }
    if (Test-Path ".venv\Scripts\python.exe") {
        return ".venv\Scripts\python.exe"
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }
    return "python"
}

function Get-RepoRoot {
    $root = git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $root) {
        throw "This script must be run from inside a git repository."
    }
    return $root.Trim()
}

function Get-NextBaselineNames([string]$Timestamp) {
    $suffix = 0
    while ($true) {
        $candidate = $Timestamp
        if ($suffix -gt 0) {
            $candidate = "{0}_{1:D2}" -f $Timestamp, $suffix
        }

        $branchName = "baseline/$candidate"
        $tagName = "baseline-$candidate"

        git show-ref --verify --quiet "refs/heads/$branchName"
        $branchExists = ($LASTEXITCODE -eq 0)
        git show-ref --verify --quiet "refs/tags/$tagName"
        $tagExists = ($LASTEXITCODE -eq 0)

        if (-not $branchExists -and -not $tagExists) {
            return @{
                Branch = $branchName
                Tag = $tagName
            }
        }

        $suffix += 1
    }
}

function Write-LogFile([string]$Path, [object[]]$Content) {
    $normalized = @()
    if ($null -ne $Content) {
        $normalized = @($Content | ForEach-Object { "$_" })
    }
    Set-Content -Path $Path -Value $normalized -Encoding utf8
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

$python = Resolve-PythonExe -Value $PythonExe
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = Join-Path $repoRoot (Join-Path "runs" $timestamp)

if (Test-Path $runDir) {
    throw "Run directory already exists: $runDir"
}

New-Item -ItemType Directory -Path $runDir | Out-Null

$commit = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $commit) {
    throw "Unable to resolve HEAD commit."
}

$refNames = Get-NextBaselineNames -Timestamp $timestamp
$baselineBranch = $refNames.Branch
$baselineTag = $refNames.Tag

git branch $baselineBranch $commit | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create branch $baselineBranch"
}

git tag $baselineTag $commit | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create tag $baselineTag"
}

$pythonVersionPath = Join-Path $runDir "python_version.txt"
$envFreezePath = Join-Path $runDir "env_freeze.txt"
$pytestPath = Join-Path $runDir "pytest.txt"

$pythonVersionOutput = & $python -V 2>&1
Write-LogFile -Path $pythonVersionPath -Content $pythonVersionOutput

$envFreezeOutput = & $python -m pip freeze 2>&1
$freezeExit = $LASTEXITCODE
Write-LogFile -Path $envFreezePath -Content $envFreezeOutput
if ($freezeExit -ne 0) {
    throw "pip freeze failed (exit $freezeExit)."
}

$pytestOutput = & $python -m pytest -q --disable-warnings --maxfail=1 2>&1
$pytestExit = $LASTEXITCODE
Write-LogFile -Path $pytestPath -Content $pytestOutput

$status = if ($pytestExit -eq 0) { "PASS" } else { "FAIL" }

Write-Host ("commit: {0}" -f $commit)
Write-Host ("branch: {0}" -f $baselineBranch)
Write-Host ("tag: {0}" -f $baselineTag)
Write-Host ("status: {0}" -f $status)
Write-Host ("run_dir: {0}" -f $runDir)

if ($pytestExit -ne 0) {
    exit $pytestExit
}

exit 0
