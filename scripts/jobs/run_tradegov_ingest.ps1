param(
    [switch]$DryRun,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptRoot '..')
$python = "$repoRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python interpreter not found at $python. Activate the venv first."
}

$args = @('-m', 'earCrawler.cli', 'jobs', 'run', 'tradegov')
if ($DryRun) { $args += '--dry-run' }
if ($Quiet) { $args += '--quiet' }

& $python @args
if ($LASTEXITCODE -ne 0) {
    throw "Job execution failed with exit code $LASTEXITCODE"
}
