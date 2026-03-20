param(
    [string]$ChecksumsPath = "dist/checksums.sha256",
    [switch]$AllowEmptyDist
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Parse-Checksums {
    param([Parameter(Mandatory = $true)][string]$Path)

    return Get-Content -Path $Path | Where-Object { $_.Trim() } | ForEach-Object {
        if ($_ -notmatch "^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$") {
            throw "Malformed checksum line in ${Path}: $_"
        }
        [ordered]@{
            sha256 = $Matches[1].ToLowerInvariant()
            path = $Matches[2]
        }
    }
}

function Get-UntrackedTopLevelArtifacts {
    param(
        [Parameter(Mandatory = $true)][string]$RootDir,
        [Parameter(Mandatory = $true)]$Entries,
        [string[]]$AllowedNames
    )

    $expected = @{}
    foreach ($entry in $Entries) {
        $entryPath = [string]$entry.path
        if (-not $entryPath) {
            continue
        }
        $normalized = $entryPath.Replace("/", "\")
        $parent = [IO.Path]::GetDirectoryName($normalized)
        if (-not $parent) {
            $leaf = [IO.Path]::GetFileName($normalized)
            if ($leaf) {
                $expected[$leaf.ToLowerInvariant()] = $true
            }
        }
    }

    $allowed = @{}
    foreach ($name in $AllowedNames) {
        if (-not $name) {
            continue
        }
        $allowed[([string]$name).ToLowerInvariant()] = $true
    }

    $unexpected = @()
    Get-ChildItem -Path $RootDir -File -ErrorAction SilentlyContinue |
        Sort-Object Name |
        ForEach-Object {
            $key = $_.Name.ToLowerInvariant()
            if (-not $expected.ContainsKey($key) -and -not $allowed.ContainsKey($key)) {
                $unexpected += $_.Name
            }
        }
    return $unexpected
}

function Get-ReleaseLikeArtifacts {
    param([Parameter(Mandatory = $true)][string]$RootDir)

    $releaseExtensions = @(".whl", ".exe", ".zip", ".msi", ".tar.gz")
    $artifacts = @()
    Get-ChildItem -Path $RootDir -File -ErrorAction SilentlyContinue |
        Sort-Object Name |
        ForEach-Object {
            $name = $_.Name.ToLowerInvariant()
            foreach ($ext in $releaseExtensions) {
                if ($name.EndsWith($ext)) {
                    $artifacts += $_.Name
                    break
                }
            }
        }
    return $artifacts
}

$checksumsExists = Test-Path -LiteralPath $ChecksumsPath
if (-not $checksumsExists) {
    $candidateRoot = Split-Path -Parent $ChecksumsPath
    if (-not $candidateRoot) {
        $candidateRoot = "dist"
    }
    if (-not (Test-Path -LiteralPath $candidateRoot)) {
        if ($AllowEmptyDist) {
            Write-Host "Release evidence preflight passed: no dist workspace found yet."
            exit 0
        }
        throw "Release evidence preflight failed: checksums not found at '$ChecksumsPath' and release root '$candidateRoot' does not exist."
    }

    $releaseLike = @(Get-ReleaseLikeArtifacts -RootDir $candidateRoot)
    $checksumsSigPath = "$ChecksumsPath.sig"
    if ($releaseLike.Count -gt 0 -or (Test-Path -LiteralPath $checksumsSigPath)) {
        $details = @()
        if ($releaseLike.Count -gt 0) {
            $details += "release-like outputs present: $($releaseLike -join ', ')"
        }
        if (Test-Path -LiteralPath $checksumsSigPath) {
            $details += "checksums signature exists without checksums: $checksumsSigPath"
        }
        $detailText = $details -join "; "
        throw "Release evidence preflight failed: uncontrolled release outputs in '$candidateRoot' ($detailText). Restore a clean state or regenerate checksums/signatures."
    }

    Write-Host "Release evidence preflight passed: no release evidence bundle present yet."
    exit 0
}

$checksumsResolved = (Resolve-Path -LiteralPath $ChecksumsPath).Path
$checksumsDir = Split-Path -Parent $checksumsResolved
$checksumsSigPath = "$checksumsResolved.sig"

if (-not (Test-Path -LiteralPath $checksumsSigPath)) {
    throw "Release evidence preflight failed: missing checksums signature dependency '$checksumsSigPath'."
}

$entries = Parse-Checksums -Path $checksumsResolved
if ($entries.Count -lt 1) {
    throw "Release evidence preflight failed: checksums file has no artifact entries ($checksumsResolved)."
}

$checksumsRoot = [IO.Path]::GetFullPath($checksumsDir)
$checksumsRootPrefix = if (
    $checksumsRoot.EndsWith("\") -or
    $checksumsRoot.EndsWith("/")
) {
    $checksumsRoot
}
else {
    "$checksumsRoot\"
}

$verified = 0
foreach ($entry in $entries) {
    $candidate = Join-Path $checksumsDir $entry.path
    $candidateResolved = [IO.Path]::GetFullPath($candidate)
    if (-not $candidateResolved.StartsWith($checksumsRootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Release evidence preflight failed: checksums entry escapes release root ($($entry.path))."
    }
    if (-not (Test-Path -LiteralPath $candidateResolved)) {
        throw "Release evidence preflight failed: missing artifact listed in checksums ($($entry.path))."
    }
    $actual = (Get-FileHash -LiteralPath $candidateResolved -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne [string]$entry.sha256) {
        throw "Release evidence preflight failed: checksum mismatch for '$($entry.path)'."
    }
    $verified += 1
}

$allowedTopLevelNames = @(
    [IO.Path]::GetFileName($checksumsResolved),
    [IO.Path]::GetFileName($checksumsSigPath),
    "release_validation_evidence.json"
)
$unexpectedTopLevel = @(Get-UntrackedTopLevelArtifacts -RootDir $checksumsDir -Entries $entries -AllowedNames $allowedTopLevelNames)
if ($unexpectedTopLevel.Count -gt 0) {
    $unexpectedList = ($unexpectedTopLevel | Sort-Object | ForEach-Object { " - $_" }) -join [Environment]::NewLine
    throw "Release evidence preflight failed: uncontrolled top-level artifacts next to checksums:`n$unexpectedList"
}

Write-Host "Release evidence preflight passed: verified $verified artifacts listed in '$checksumsResolved'."
