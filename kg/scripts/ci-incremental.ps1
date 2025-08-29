$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path "$PSScriptRoot/../.."
$manifestDir = Join-Path $repoRoot 'kg/.kgstate'
$reportDir = Join-Path $repoRoot 'kg/reports'
New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

$manifestPath = Join-Path $manifestDir 'manifest.json'
$statusPath = Join-Path $reportDir 'incremental-status.json'

python -m earCrawler.utils.kg_state --root $repoRoot --manifest $manifestPath --status $statusPath | Out-Null
$status = Get-Content $statusPath | ConvertFrom-Json
if (-not $status.changed) {
    'No changes detected' | Set-Content -Path (Join-Path $reportDir 'incremental-noop.txt')
    exit 0
}

# Changes detected: optionally run standard pipeline
if ($env:INCREMENTAL_SCAN_ONLY -ne '1') {
    & "$repoRoot/kg/scripts/ci-roundtrip.ps1"
    & "$repoRoot/kg/scripts/ci-shacl-owl.ps1"
    & "$repoRoot/kg/scripts/ci-inference-smoke.ps1" -Mode rdfs
    & "$repoRoot/kg/scripts/ci-inference-smoke.ps1" -Mode owlmini
    & "$repoRoot/kg/scripts/ci-provenance.ps1"

    # Canonicalize current KG
    $canonicalPrev = Join-Path $manifestDir 'canonical-prev.nq'
    $canonicalNow  = Join-Path $manifestDir 'canonical-now.nq'
    & "$repoRoot/kg/tools/canonicalize.ps1" -Input (Join-Path $repoRoot 'kg/ear.ttl') -Output $canonicalNow
    if (Test-Path $canonicalPrev) {
        $diffTxt = Join-Path $reportDir 'canonical-diff.txt'
        $diffJson = Join-Path $reportDir 'canonical-diff.json'
        python -m earCrawler.utils.diff_reports --left $canonicalPrev --right $canonicalNow --txt $diffTxt --json $diffJson | Out-Null
    }
    Copy-Item $canonicalNow $canonicalPrev -Force

    # Diff SPARQL snapshots
    $diffs = @()
    $snapshotDir = Join-Path $repoRoot 'kg/snapshots'
    Get-ChildItem $snapshotDir -Filter '*.srj' | ForEach-Object {
        $prev = "$($_.FullName).prev"
        if (Test-Path $prev) {
            $txt = Join-Path $reportDir "$($_.BaseName)-diff.txt"
            $json = Join-Path $reportDir "$($_.BaseName)-diff.json"
            python -m earCrawler.utils.diff_reports --left $prev --right $_.FullName --srj --txt $txt --json $json | Out-Null
            $r = Get-Content $json | ConvertFrom-Json
            $diffs += [pscustomobject]@{name=$_.Name; changed=$r.changed}
        }
        Copy-Item $_.FullName $prev -Force
    }

    $summaryJson = Join-Path $reportDir 'diff-summary.json'
    $summaryTxt  = Join-Path $reportDir 'diff-summary.txt'
    $diffs | ConvertTo-Json -Depth 5 | Set-Content $summaryJson
    $diffs | ForEach-Object { "$($_.name): $($_.changed)" } | Set-Content $summaryTxt

    if ($env:STRICT_SNAPSHOT -eq '1') {
        if ($diffs | Where-Object { $_.changed }) {
            Write-Error 'Snapshot diffs detected'
            exit 1
        }
    }
}
