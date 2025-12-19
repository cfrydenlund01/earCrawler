param(
    [string]$FixturesDir = "tests/fixtures",
    [string]$SourceDateEpoch = "946684800"
)

$ErrorActionPreference = 'Stop'
$WarningPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$env:EARCTL_USER = $env:EARCTL_USER ?? 'test_operator'
$env:SOURCE_DATE_EPOCH = $SourceDateEpoch

function Get-TreeDigest {
    param(
        [Parameter(Mandatory = $true)][string]$Root
    )

    $rootPath = (Resolve-Path $Root).Path
    $items = Get-ChildItem -Path $rootPath -Recurse -File | Sort-Object FullName
    $lines = foreach ($item in $items) {
        $rel = [IO.Path]::GetRelativePath($rootPath, $item.FullName).Replace('\', '/')
        $hash = (Get-FileHash -Algorithm SHA256 -Path $item.FullName).Hash.ToLower()
        "$hash  $rel"
    }
    $text = ($lines -join "`n") + "`n"
    $bytes = [Text.Encoding]::UTF8.GetBytes($text)
    $sha = [Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    -join ($sha | ForEach-Object { $_.ToString('x2') })
}

function Invoke-CorpusRun {
    param(
        [Parameter(Mandatory = $true)][string]$RunRoot
    )

    if (Test-Path $RunRoot) { Remove-Item -Recurse -Force $RunRoot }
    New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null

    $dataDir = Join-Path $RunRoot 'data'
    $snapBase = Join-Path $RunRoot 'snapshots'
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    New-Item -ItemType Directory -Force -Path $snapBase | Out-Null

    python -W error -m earCrawler.cli corpus build --out $dataDir --fixtures $FixturesDir
    python -W error -m earCrawler.cli corpus validate --dir $dataDir
    python -W error -m earCrawler.cli corpus snapshot --dir $dataDir --out $snapBase | Out-Host

    $snapDirs = Get-ChildItem -Path $snapBase -Directory | Sort-Object Name
    if ($snapDirs.Count -ne 1) {
        throw "Expected exactly 1 snapshot directory under $snapBase, found $($snapDirs.Count)."
    }

    [PSCustomObject]@{
        DataDigest = Get-TreeDigest -Root $dataDir
        SnapshotDigest = Get-TreeDigest -Root $snapDirs[0].FullName
        SnapshotPath = $snapDirs[0].FullName
    }
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) 'earcrawler-corpus-determinism'
$run1 = Join-Path $tempRoot 'run1'
$run2 = Join-Path $tempRoot 'run2'

$r1 = Invoke-CorpusRun -RunRoot $run1
$r2 = Invoke-CorpusRun -RunRoot $run2

if ($r1.DataDigest -ne $r2.DataDigest) {
    throw "Corpus build outputs are not deterministic. run1=$($r1.DataDigest) run2=$($r2.DataDigest)"
}
if ($r1.SnapshotDigest -ne $r2.SnapshotDigest) {
    throw "Corpus snapshot outputs are not deterministic. run1=$($r1.SnapshotDigest) run2=$($r2.SnapshotDigest)"
}

Write-Host "Corpus determinism confirmed (data=$($r1.DataDigest), snapshot=$($r1.SnapshotDigest))"
