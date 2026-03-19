param(
    [string]$Python = "py",
    [string]$RequirementsLock = "requirements-win-lock.txt",
    [string]$PipAuditIgnoreFile = "security/pip_audit_ignore.txt",
    [string]$OutputDir = "dist/security"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        $joined = $Arguments -join " "
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable $joined"
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot
try {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

    $pipAuditReport = Join-Path $OutputDir "pip_audit.json"
    $banditReport = Join-Path $OutputDir "bandit.json"
    $secretScanReport = Join-Path $OutputDir "secret_scan.json"
    $summaryReport = Join-Path $OutputDir "security_scan_summary.json"

    $summary = [ordered]@{
        schema_version = "ci-security-baseline.v1"
        generated_utc = (Get-Date).ToUniversalTime().ToString("o")
        reports = [ordered]@{
            pip_audit = [ordered]@{ status = "not_run"; path = $pipAuditReport }
            bandit = [ordered]@{ status = "not_run"; path = $banditReport }
            secret_scan = [ordered]@{ status = "not_run"; path = $secretScanReport }
        }
        overall_status = "failed"
        error = ""
    }

    try {
        Invoke-CheckedCommand -Executable $Python -Arguments @(
            "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip-audit", "bandit"
        )

        $ignoreArgs = @()
        if (Test-Path $PipAuditIgnoreFile) {
            foreach ($line in Get-Content $PipAuditIgnoreFile) {
                $trimmed = $line.Trim()
                if (-not $trimmed -or $trimmed.StartsWith("#")) {
                    continue
                }
                $ignoreArgs += @("--ignore-vuln", $trimmed)
            }
        }

        $pipAuditArgs = @("-m", "pip_audit", "-r", $RequirementsLock, "--format", "json", "--output", $pipAuditReport)
        $pipAuditArgs += $ignoreArgs
        Invoke-CheckedCommand -Executable $Python -Arguments $pipAuditArgs
        $summary.reports.pip_audit.status = "passed"

        Invoke-CheckedCommand -Executable $Python -Arguments @(
            "-m", "bandit", "-r", "earCrawler", "api_clients", "service", "-q", "-lll", "-iii", "-f", "json", "-o", $banditReport
        )
        $summary.reports.bandit.status = "passed"

        Invoke-CheckedCommand -Executable $Python -Arguments @(
            "scripts/security_secret_scan.py", "--repo-root", ".", "--report-path", $secretScanReport
        )
        $summary.reports.secret_scan.status = "passed"

        $summary.overall_status = "passed"
    }
    catch {
        $summary.error = $_.Exception.Message
        throw
    }
    finally {
        $summary | ConvertTo-Json -Depth 8 | Set-Content -Path $summaryReport -Encoding utf8
    }
}
finally {
    Pop-Location
}
