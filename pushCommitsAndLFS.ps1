param(
    [string]$Remote = "origin",
    [string]$BaseBranch = "main",
    [string]$FeatureBranch = "",
    [int]$LfsThresholdMb = 100,
    [string]$CommitMessage = "",
    [string]$PrTitle = "",
    [string]$PrBody = "",
    [switch]$SkipPrCreation
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

    $prevErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & git @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $prevErrorAction
    }

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

$currentBranchResult = Invoke-Git -Arguments @("rev-parse", "--abbrev-ref", "HEAD", "--") -IgnoreErrors
$currentBranch = ($currentBranchResult.Output | Select-Object -First 1).Trim()
if ([string]::IsNullOrWhiteSpace($currentBranch)) {
    throw "Unable to determine current branch."
}

Write-Host "Active branch before processing: $currentBranch"
Write-Host "Remote: $Remote"
Write-Host "Base branch: $BaseBranch"

Invoke-Git -Arguments @("fetch", $Remote, $BaseBranch) | Out-Null

if ([string]::IsNullOrWhiteSpace($FeatureBranch)) {
    if ($currentBranch -eq $BaseBranch) {
        $FeatureBranch = "pr/{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss")
        Write-Host "Creating feature branch '$FeatureBranch' from '$BaseBranch'..."
        Invoke-Git -Arguments @("checkout", "-b", $FeatureBranch) | Out-Null
        $currentBranch = $FeatureBranch
    }
    else {
        $FeatureBranch = $currentBranch
        Write-Host "Using existing branch '$FeatureBranch' for pull request."
    }
}
else {
    if ($currentBranch -ne $FeatureBranch) {
        $branchCheck = Invoke-Git -Arguments @("rev-parse", "--verify", "--quiet", $FeatureBranch) -IgnoreErrors
        if ($branchCheck.ExitCode -eq 0) {
            Write-Host "Checking out existing branch '$FeatureBranch'..."
            Invoke-Git -Arguments @("checkout", $FeatureBranch) | Out-Null
        }
        else {
            Write-Host "Creating branch '$FeatureBranch' from current HEAD..."
            Invoke-Git -Arguments @("checkout", "-b", $FeatureBranch) | Out-Null
        }
        $currentBranch = $FeatureBranch
    }
    else {
        Write-Host "Already on feature branch '$FeatureBranch'."
    }
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
    Write-Host "Nothing staged for commit."
}
else {
    if ([string]::IsNullOrWhiteSpace($CommitMessage)) {
        $CommitMessage = "Automated sync on $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    }

    Write-Host "Committing staged changes..."
    Invoke-Git -Arguments @("commit", "-m", $CommitMessage) | Out-Null
}

Write-Host "Pushing branch '$currentBranch' to '$Remote'..."
Invoke-Git -Arguments @("push", "-u", $Remote, $currentBranch) | Out-Null

if ($SkipPrCreation) {
    Write-Host "Skipping pull request creation by request."
    return
}

$ghCommand = Get-Command gh -ErrorAction SilentlyContinue
if (-not $ghCommand) {
    Write-Warning "GitHub CLI ('gh') not found. Install it from https://cli.github.com/ to enable automatic PR creation."
    return
}

if ([string]::IsNullOrWhiteSpace($PrTitle)) {
    $lastCommit = Invoke-Git -Arguments @("log", "-1", "--pretty=%s") -IgnoreErrors
    $PrTitle = ($lastCommit.Output | Select-Object -First 1).Trim()
    if ([string]::IsNullOrWhiteSpace($PrTitle)) {
        $PrTitle = "Updates from $currentBranch"
    }
}

$prArgs = @("pr", "create", "--base", $BaseBranch, "--head", $currentBranch, "--title", $PrTitle)
if ([string]::IsNullOrWhiteSpace($PrBody)) {
    $prArgs += "--fill"
}
else {
    $prArgs += @("--body", $PrBody)
}

Write-Host "Creating pull request via GitHub CLI..."
$prOutput = & gh @prArgs
$prExitCode = $LASTEXITCODE

if ($prExitCode -ne 0) {
    throw "Failed to create pull request (exit code $prExitCode). Output: $prOutput"
}

Write-Host $prOutput
Write-Host "Pull request created successfully."
