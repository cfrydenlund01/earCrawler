param(
    [string]$Remote = "origin",
    [string]$Branch = "",
    [int]$LfsThresholdMb = 100,
    [string]$CommitMessage = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments,
        [switch]$IgnoreErrors
    )

    $commandText = "git {0}" -f ($Arguments -join " ")
    Write-Host "> $commandText" -ForegroundColor Cyan
    $output = & git @Arguments 2>&1
    $exitCode = $LASTEXITCODE

    foreach ($line in $output) {
        if ($null -ne $line -and $line.ToString().Length -gt 0) {
            Write-Host $line
        }
    }

    if (-not $IgnoreErrors -and $exitCode -ne 0) {
        throw "Git command failed (exit code $exitCode): $commandText"
    }

    return [pscustomobject]@{
        Output   = $output
        ExitCode = $exitCode
    }
}

$repoRootResult = Invoke-Git -Arguments @("rev-parse", "--show-toplevel") -IgnoreErrors
$repoRoot = ($repoRootResult.Output | Select-Object -First 1)
if (-not $repoRoot) {
    throw "Unable to determine git repository root. Make sure this script is run inside a git repo."
}

$repoRoot = $repoRoot.Trim()
Set-Location -Path $repoRoot
Write-Host "Repository root: $repoRoot"

if ([string]::IsNullOrWhiteSpace($Branch)) {
    $branchResult = Invoke-Git -Arguments @("rev-parse", "--abbrev-ref", "HEAD", "--") -IgnoreErrors
    $Branch = ($branchResult.Output | Select-Object -First 1).Trim()
    if ([string]::IsNullOrWhiteSpace($Branch)) {
        throw "Unable to determine current branch. Please set -Branch explicitly."
    }
}

Write-Host "Target remote: $Remote"
Write-Host "Target branch: $Branch"

$remotesResult = Invoke-Git -Arguments @("remote") -IgnoreErrors
$remoteList = $remotesResult.Output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { $_.Trim() }
if (-not ($remoteList | Where-Object { $_ -eq $Remote })) {
    throw "Remote '$Remote' does not exist. Configure the remote before running this script."
}

try {
    & git lfs --version | Out-Null
    $gitLfsAvailable = $true
}
catch {
    $gitLfsAvailable = $false
    Write-Warning "git-lfs is not installed. Large files will be committed normally."
}

$sizeLimitBytes = $LfsThresholdMb * 1MB
Write-Host "Scanning for files over $LfsThresholdMb MB..."

$largeFiles = Get-ChildItem -Path $repoRoot -File -Recurse |
    Where-Object { $_.Length -gt $sizeLimitBytes }

if ($gitLfsAvailable -and $largeFiles) {
    Write-Host "Found $($largeFiles.Count) large file(s) requiring LFS tracking."
    $extensions = $largeFiles |
        ForEach-Object { $_.Extension } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -Unique

    foreach ($ext in $extensions) {
        $pattern = "*$ext"
        Write-Host "Tracking pattern '$pattern' with Git LFS..."
        Invoke-Git -Arguments @("lfs", "track", "--", $pattern)
    }

    $filesWithoutExtension = $largeFiles | Where-Object { [string]::IsNullOrWhiteSpace($_.Extension) }
    foreach ($file in $filesWithoutExtension) {
        Write-Warning "File '$($file.FullName)' exceeds $LfsThresholdMb MB but has no extension. Track it manually if desired."
    }

    if (Test-Path ".gitattributes") {
        Invoke-Git -Arguments @("add", ".gitattributes")
    }
}
elseif ($largeFiles) {
    Write-Warning "Large files detected but git-lfs is not available; continuing without updating tracking rules."
}
else {
    Write-Host "No files exceed $LfsThresholdMb MB."
}

Write-Host "Staging all tracked changes..."
Invoke-Git -Arguments @("add", "--all") | Out-Null

$diffResult = Invoke-Git -Arguments @("diff", "--cached", "--quiet") -IgnoreErrors
if ($diffResult.ExitCode -eq 0) {
    Write-Host "Nothing to commit. Working tree is clean."
}
else {
    if ([string]::IsNullOrWhiteSpace($CommitMessage)) {
        $CommitMessage = "Automated sync on $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    }

    Write-Host "Committing staged changes..."
    Invoke-Git -Arguments @("commit", "-m", $CommitMessage) | Out-Null
}

Write-Host "Pushing to '$Remote/$Branch' with force-with-lease..."
Invoke-Git -Arguments @("push", "--force-with-lease", $Remote, $Branch) | Out-Null

Write-Host "Push complete. Current status:"
Invoke-Git -Arguments @("status", "-sb") | Out-Null
