param(
    [string]$Python = "py",
    [string]$OutRoot = "demo",
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Title,
        [string[]]$Arguments,
        [string]$WorkingDirectory = "."
    )

    Write-Host "==> $Title"
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $Python
    foreach ($arg in $Arguments) {
        $psi.ArgumentList.Add($arg)
    }
    $psi.WorkingDirectory = (Resolve-Path $WorkingDirectory).Path
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardOutput = $true
    $psi.UseShellExecute = $false

    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    if ($stdout) { Write-Host $stdout.Trim() }
    if ($stderr) { Write-Warning $stderr.Trim() }
    if ($proc.ExitCode -ne 0) {
        throw "Command failed ($Title) with exit code $($proc.ExitCode)"
    }
}

if ($Clean -and (Test-Path $OutRoot)) {
    Write-Host "Cleaning $OutRoot"
    Remove-Item -Recurse -Force $OutRoot
}

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

$dataDir = Join-Path $OutRoot "data"
$kgDir = Join-Path $OutRoot "kg"
$dbDir = Join-Path $OutRoot "db"
$bundleDir = Join-Path $OutRoot "bundle"

$null = New-Item -ItemType Directory -Path $dataDir -Force
$null = New-Item -ItemType Directory -Path $kgDir -Force

$previousUser = $env:EARCTL_USER
$env:EARCTL_USER = "test_operator"

try {
    Invoke-Step -Title "Crawl fixtures" -Arguments @(
        "-m", "earCrawler.cli", "crawl",
        "--sources", "ear",
        "--sources", "nsf",
        "--fixtures", (Resolve-Path "tests/fixtures").Path,
        "--out", $dataDir
    )

    Copy-Item -Path "tests/fixtures/ear_corpus.jsonl" -Destination (Join-Path $dataDir "ear_corpus.jsonl") -Force
    Copy-Item -Path "tests/kg/fixtures/nsf_corpus.jsonl" -Destination (Join-Path $dataDir "nsf_corpus.jsonl") -Force

    Invoke-Step -Title "Emit RDF for demo corpora" -Arguments @(
        "-m", "earCrawler.cli", "kg-emit",
        "-s", "ear",
        "-s", "nsf",
        "--in", $dataDir,
        "--out", $kgDir
    )

    Invoke-Step -Title "Load triples into demo TDB2 store" -Arguments @(
        "-m", "earCrawler.cli", "kg-load",
        "--ttl", (Join-Path $kgDir "ear.ttl"),
        "--db", $dbDir
    )

    Invoke-Step -Title "Generate demo export bundle" -Arguments @(
        "-m", "earCrawler.cli", "bundle", "export-profiles",
        "--ttl", (Join-Path $kgDir "ear.ttl"),
        "--out", $bundleDir,
        "--stem", "demo"
    )

    Invoke-Step -Title "Show Fuseki launch command" -Arguments @(
        "-m", "earCrawler.cli", "kg-serve",
        "--db", $dbDir,
        "--dataset", "/ear",
        "--port", "3030",
        "--dry-run"
    )

    $reportName = "top_terms.json"
    Invoke-Step -Title "Summarise corpus" -Arguments @(
        "-m", "earCrawler.cli", "report",
        "--sources", "ear",
        "--sources", "nsf",
        "--type", "term-frequency",
        "--n", "5",
        "--out", $reportName
    ) -WorkingDirectory $OutRoot

    $summary = @(
        "Demo artefacts generated at $(Resolve-Path $OutRoot).",
        "  - Crawl output: $dataDir",
        "  - RDF output: $kgDir",
        "  - TDB2 store: $dbDir",
        "  - Export bundle: $bundleDir",
        "  - Term frequency report: $(Join-Path $OutRoot $reportName)"
    )
    $summaryPath = Join-Path $OutRoot "SUMMARY.txt"
    $summary | Set-Content -Path $summaryPath -Encoding UTF8
    Write-Host "Summary written to $summaryPath"
}
finally {
    if ($null -ne $previousUser) {
        $env:EARCTL_USER = $previousUser
    }
    else {
        Remove-Item Env:EARCTL_USER -ErrorAction SilentlyContinue
    }
}
