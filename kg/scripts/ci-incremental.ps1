$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path "$PSScriptRoot/../.."
$manifestDir = Join-Path $repoRoot 'kg/.kgstate'
$reportDir = Join-Path $repoRoot 'kg/reports'
New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

function Resolve-KgPython {
    if ($env:EARCTL_PYTHON -and (Test-Path $env:EARCTL_PYTHON)) {
        return $env:EARCTL_PYTHON
    }
    foreach ($name in 'python', 'python.exe', 'python3', 'python3.exe') {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    $pyLauncher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $exe = & $pyLauncher.Source -3 -c "import sys; print(sys.executable)"
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch {}
    }
    if ($env:VIRTUAL_ENV) {
        $candidate = Join-Path $env:VIRTUAL_ENV 'Scripts/python.exe'
        if (Test-Path $candidate) { return $candidate }
        $candidate = Join-Path $env:VIRTUAL_ENV 'bin/python3'
        if (Test-Path $candidate) { return $candidate }
    }
    throw 'Python interpreter not found. Set EARCTL_PYTHON or ensure python is on PATH.'
}

$python = Resolve-KgPython
$env:EARCTL_PYTHON = $python

$requirements = Join-Path $repoRoot 'requirements-win.txt'
if (($env:KG_CI_SKIP_PIP -ne '1') -and (Test-Path $requirements)) {
    Write-Host "Installing incremental dependencies from $requirements"
    & $python -m pip install --disable-pip-version-check -r $requirements
}

$manifestPath = Join-Path $manifestDir 'manifest.json'
$statusPath = Join-Path $reportDir 'incremental-status.json'

& $python -m earCrawler.utils.kg_state --root $repoRoot --manifest $manifestPath --status $statusPath | Out-Null
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
        & $python -m earCrawler.utils.diff_reports --left $canonicalPrev --right $canonicalNow --txt $diffTxt --json $diffJson | Out-Null
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
            & $python -m earCrawler.utils.diff_reports --left $prev --right $_.FullName --srj --txt $txt --json $json | Out-Null
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
