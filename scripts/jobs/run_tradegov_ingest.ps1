param(
    [switch]$DryRun,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptRoot '..')
$logDir = Join-Path $repoRoot 'run/logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = Join-Path $logDir "tradegov-job-$timestamp.log"
$summary = @{
    job = 'tradegov-ingest'
    started = (Get-Date).ToString('o')
    dryRun = [bool]$DryRun
    steps = []
}

function Write-JobLog {
    param($Message)
    $entry = "[$((Get-Date).ToString('o'))] $Message"
    Add-Content -Path $logPath -Value $entry
    if (-not $Quiet) { Write-Host $entry }
}

Write-JobLog "Starting Trade.gov ingestion job (DryRun=$DryRun)"

$python = "$repoRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python interpreter not found at $python. Activate the venv first."
}

$env:EARCTL_USER = $env:EARCTL_USER -or 'scheduler_operator'

try {
    if (-not $DryRun) {
        Write-JobLog 'Loading CSL entities from Trade.gov API'
        & $python -m earCrawler.cli crawl -s ear --out data --live | Tee-Object -FilePath (Join-Path $logDir "tradegov-ingest-$timestamp.out")
        if ($LASTEXITCODE -ne 0) {
            throw "earCrawler crawl command failed with exit code $LASTEXITCODE"
        }
        $summary.steps += @{ name = 'crawl'; status = 'ok' }
    } else {
        Write-JobLog 'DryRun: skipping live crawl'
        $summary.steps += @{ name = 'crawl'; status = 'skip' }
    }

    Write-JobLog 'Invoking CLI bundle exports in dry-run for validation'
    & $python -m earCrawler.cli bundle build --dry-run
    if ($LASTEXITCODE -ne 0) {
        throw "earCrawler bundle build failed with exit code $LASTEXITCODE"
    }
    $summary.steps += @{ name = 'bundle'; status = 'ok' }

    Write-JobLog 'Job completed successfully'
    $summary.status = 'ok'
}
catch {
    $summary.status = 'failed'
    $summary.error = $_.Exception.Message
    Write-JobLog "ERROR: $summary.error"
    throw
}
finally {
    $summary.finished = (Get-Date).ToString('o')
    $summaryPath = Join-Path $logDir "tradegov-job-$timestamp.json"
    $summary | ConvertTo-Json -Depth 4 | Set-Content -Path $summaryPath -Encoding UTF8
    Write-JobLog "Summary written to $summaryPath"
}
