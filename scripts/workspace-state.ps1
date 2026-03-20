param(
    [string]$RootPath = ".",
    [ValidateSet("report", "verify", "clean")]
    [string]$Mode = "report",
    [switch]$FailOnDisposable,
    [switch]$CleanDist,
    [switch]$CleanVenvs,
    [switch]$SkipGit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-Record {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Category,
        [Parameter(Mandatory = $true)][bool]$Exists,
        [Parameter(Mandatory = $true)][int]$TrackedFiles,
        [Parameter(Mandatory = $true)][string]$Note
    )
    return [ordered]@{
        path = $Path
        category = $Category
        exists = $Exists
        tracked_files = $TrackedFiles
        note = $Note
    }
}

function Get-TrackedFileCount {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)][bool]$GitEnabled
    )
    if (-not $GitEnabled) {
        return 0
    }
    $output = @(& git ls-files -- "$RelativePath")
    if ($LASTEXITCODE -ne 0) {
        return 0
    }
    return $output.Count
}

function Remove-PathIfPresent {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (Test-Path $Path) {
        Remove-Item -Recurse -Force $Path
        return $true
    }
    return $false
}

$resolvedRoot = (Resolve-Path $RootPath).Path
Push-Location $resolvedRoot
try {
    $gitEnabled = $false
    if (-not $SkipGit) {
        $null = & git rev-parse --is-inside-work-tree 2>$null
        if ($LASTEXITCODE -eq 0) {
            $gitEnabled = $true
        }
    }

    $authoredRoots = @(
        "earCrawler",
        "service",
        "api_clients",
        "scripts",
        "tests",
        "docs",
        "config",
        "security",
        "kg",
        "data",
        "eval"
    )
    $generatedRoots = @("build", "dist", "run", "runs")
    $disposablePatterns = @(".pytest_tmp*", ".venv*")
    $ghostRoots = @(
        "earCrawler/agent",
        "earCrawler/models/legalbert",
        "earCrawler/quant",
        "tests/agent",
        "tests/models"
    )

    $records = @()
    foreach ($path in $authoredRoots) {
        $exists = Test-Path $path
        $records += New-Record `
            -Path $path `
            -Category "authored_source" `
            -Exists $exists `
            -TrackedFiles (Get-TrackedFileCount -RelativePath $path -GitEnabled $gitEnabled) `
            -Note "authoritative source root"
    }
    foreach ($path in $generatedRoots) {
        $exists = Test-Path $path
        $note = if ($path -eq "dist") {
            "generated evidence/build outputs; retain intentionally"
        }
        else {
            "generated workspace output"
        }
        $records += New-Record `
            -Path $path `
            -Category "generated" `
            -Exists $exists `
            -TrackedFiles (Get-TrackedFileCount -RelativePath $path -GitEnabled $gitEnabled) `
            -Note $note
    }
    foreach ($pattern in $disposablePatterns) {
        Get-ChildItem -Path . -Directory -Filter $pattern -ErrorAction SilentlyContinue |
            Sort-Object Name |
            ForEach-Object {
                $relative = $_.FullName.Substring($resolvedRoot.Length).TrimStart('\', '/')
                $records += New-Record `
                    -Path $relative `
                    -Category "disposable_workspace_state" `
                    -Exists $true `
                    -TrackedFiles (Get-TrackedFileCount -RelativePath $relative -GitEnabled $gitEnabled) `
                    -Note "local interpreter/test cache"
            }
    }
    foreach ($path in $ghostRoots) {
        $exists = Test-Path $path
        $tracked = Get-TrackedFileCount -RelativePath $path -GitEnabled $gitEnabled
        $note = if ($exists -and $tracked -eq 0) {
            "unsupported residue; safe to remove"
        }
        elseif ($exists) {
            "path has tracked files; do not auto-remove"
        }
        else {
            "not present"
        }
        $records += New-Record `
            -Path $path `
            -Category "ghost_workspace_residue" `
            -Exists $exists `
            -TrackedFiles $tracked `
            -Note $note
    }

    $records |
        Sort-Object category, path |
        ForEach-Object {
            $exists = if ([bool]$_.exists) { "yes" } else { "no" }
            Write-Host ("[{0}] {1} exists={2} tracked={3} ({4})" -f $_.category, $_.path, $exists, $_.tracked_files, $_.note)
        }

    if ($Mode -eq "verify") {
        $errors = @()
        $ghostViolations = @(
            $records | Where-Object {
                $_.category -eq "ghost_workspace_residue" -and
                $_.exists -eq $true -and
                $_.tracked_files -eq 0
            }
        )
        if ($ghostViolations.Count -gt 0) {
            $errors += "Ghost workspace residue is present:"
            $errors += @($ghostViolations | ForEach-Object { " - $($_.path)" })
        }

        if ($FailOnDisposable) {
            $disposableViolations = @(
                $records | Where-Object {
                    $_.category -eq "disposable_workspace_state" -and $_.exists -eq $true
                }
            )
            if ($disposableViolations.Count -gt 0) {
                $errors += "Disposable workspace state is present:"
                $errors += @($disposableViolations | ForEach-Object { " - $($_.path)" })
            }
            $generatedViolations = @(
                $records | Where-Object {
                    $_.category -eq "generated" -and
                    $_.path -ne "dist" -and
                    $_.exists -eq $true
                }
            )
            if ($generatedViolations.Count -gt 0) {
                $errors += "Generated non-evidence directories are present:"
                $errors += @($generatedViolations | ForEach-Object { " - $($_.path)" })
            }
        }

        if ($errors.Count -gt 0) {
            $errorText = $errors -join [Environment]::NewLine
            throw $errorText
        }
        Write-Host "Workspace state verification passed."
        exit 0
    }

    if ($Mode -eq "clean") {
        $removed = @()

        foreach ($record in $records | Where-Object { $_.category -eq "ghost_workspace_residue" -and $_.exists -eq $true -and $_.tracked_files -eq 0 }) {
            if (Remove-PathIfPresent -Path $record.path) {
                $removed += $record.path
            }
        }
        foreach ($record in $records | Where-Object { $_.category -eq "disposable_workspace_state" -and $_.exists -eq $true }) {
            if ($record.path -like ".venv*" -and -not $CleanVenvs) {
                continue
            }
            if (Remove-PathIfPresent -Path $record.path) {
                $removed += $record.path
            }
        }
        foreach ($record in $records | Where-Object { $_.category -eq "generated" -and $_.exists -eq $true }) {
            if ($record.path -eq "dist" -and -not $CleanDist) {
                continue
            }
            if ($record.path -ne "dist" -or $CleanDist) {
                if (Remove-PathIfPresent -Path $record.path) {
                    $removed += $record.path
                }
            }
        }

        if ($removed.Count -gt 0) {
            Write-Host "Removed workspace paths:"
            $removed | Sort-Object -Unique | ForEach-Object { Write-Host " - $_" }
        }
        else {
            Write-Host "No removable workspace paths found."
        }
        if (-not $CleanDist) {
            Write-Host "dist/ was preserved. Use -CleanDist only when you intentionally want to drop generated evidence."
        }
        if (-not $CleanVenvs) {
            Write-Host ".venv* was preserved. Use -CleanVenvs only when you intentionally want to remove local environments."
        }
    }
}
finally {
    Pop-Location
}
