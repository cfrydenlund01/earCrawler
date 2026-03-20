param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("build", "validation", "promotion")]
    [string]$Stage,
    [string]$OutPath = "dist/promotion/stage_evidence.json",
    [string]$Tag = $env:GITHUB_REF_NAME,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$EvidenceFiles = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-GitCommit {
    try {
        return (git rev-parse HEAD).Trim()
    }
    catch {
        return ""
    }
}

function New-EvidenceEntry {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Evidence file not found: $Path"
    }

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw "Evidence path must resolve to a file: $Path"
    }

    $repoFull = [IO.Path]::GetFullPath($RepoRoot)
    $repoPrefix = if ($repoFull.EndsWith('\') -or $repoFull.EndsWith('/')) {
        $repoFull
    }
    else {
        "$repoFull\"
    }

    $displayPath = ""
    if ($resolved.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        $displayPath = [IO.Path]::GetRelativePath($repoFull, $resolved)
    }
    else {
        $displayPath = $resolved
    }

    $hash = (Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash.ToLowerInvariant()
    $item = Get-Item -LiteralPath $resolved

    return [ordered]@{
        path = $displayPath.Replace('\', '/')
        size = [int64]$item.Length
        sha256 = $hash
    }
}

$repoRoot = (Get-Location).Path
$entries = @()
$seen = @{}
foreach ($candidate in $EvidenceFiles) {
    if (-not $candidate) {
        continue
    }
    $entry = New-EvidenceEntry -Path $candidate -RepoRoot $repoRoot
    $key = [string]$entry.path
    if ($seen.ContainsKey($key)) {
        continue
    }
    $seen[$key] = $true
    $entries += $entry
}
$entries = @($entries | Sort-Object path)

$payload = [ordered]@{
    schema_version = "release-promotion-stage.v1"
    stage = $Stage
    generated_utc = (Get-Date).ToUniversalTime().ToString("o")
    git_commit = Get-GitCommit
    git_tag = if ($Tag) { [string]$Tag } else { "" }
    workflow = [ordered]@{
        run_id = [string]$env:GITHUB_RUN_ID
        run_attempt = [string]$env:GITHUB_RUN_ATTEMPT
        workflow = [string]$env:GITHUB_WORKFLOW
        job = [string]$env:GITHUB_JOB
        repository = [string]$env:GITHUB_REPOSITORY
        ref = [string]$env:GITHUB_REF
        actor = [string]$env:GITHUB_ACTOR
    }
    evidence_file_count = $entries.Count
    evidence_files = $entries
}

$outDir = Split-Path -Parent $OutPath
if ($outDir) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}
$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $OutPath -Encoding utf8

Write-Host "Wrote release stage evidence manifest: $OutPath"
