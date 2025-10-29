Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptRoot '..')
$tests = @(
    @{ Name = 'TradeGov'; Path = Join-Path $repoRoot 'scripts/jobs/run_tradegov_ingest.ps1' },
    @{ Name = 'FederalRegister'; Path = Join-Path $repoRoot 'scripts/jobs/run_federalregister_anchor.ps1' }
)

foreach ($job in $tests) {
    Write-Host "Testing $($job.Name) job in dry-run..."
    pwsh -NoProfile -File $job.Path -DryRun -Quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Dry-run failed for $($job.Name)"
    }
}

Write-Host 'All job scripts completed dry-run successfully.'
