param(
    [string]$LockFile = "requirements-win-lock.txt",
    [string]$WheelhousePath = "",
    [string]$PythonExecutable = "",
    [string]$WheelPath = "",
    [string]$ChecksumsPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path "$PSScriptRoot/..").ProviderPath

function Resolve-PythonInterpreter {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (-not (Test-Path $ExplicitPath)) {
            throw "Requested Python executable does not exist: $ExplicitPath"
        }
        return (Resolve-Path $ExplicitPath).ProviderPath
    }
    if ($env:EARCTL_PYTHON -and (Test-Path $env:EARCTL_PYTHON)) {
        return (Resolve-Path $env:EARCTL_PYTHON).ProviderPath
    }
    foreach ($name in @("python", "python.exe", "python3", "py")) {
        $candidate = Get-Command $name -ErrorAction SilentlyContinue
        if ($candidate) {
            return $candidate.Source
        }
    }
    throw "Python interpreter not found on PATH."
}

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

function Resolve-ExistingPath {
    param(
        [Parameter(Mandatory = $true)][string]$PathValue,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $candidate = $PathValue
    if (-not [IO.Path]::IsPathRooted($candidate)) {
        $candidate = Join-Path -Path $repoRoot -ChildPath $candidate
    }
    if (-not (Test-Path $candidate)) {
        throw "$Label not found: $PathValue"
    }
    return (Resolve-Path $candidate).ProviderPath
}

function Resolve-WheelhouseDirectory {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        return Resolve-ExistingPath -PathValue $ExplicitPath -Label "Wheelhouse directory"
    }

    $candidateDirs = @(
        (Join-Path -Path $repoRoot -ChildPath ".wheelhouse"),
        (Join-Path -Path $repoRoot -ChildPath "hermetic-artifacts/.wheelhouse")
    )

    foreach ($candidate in $candidateDirs) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).ProviderPath
        }
    }

    $archive = Join-Path $repoRoot "hermetic-artifacts.zip"
    if (Test-Path $archive) {
        Expand-Archive -Path $archive -DestinationPath $repoRoot -Force
        foreach ($candidate in $candidateDirs) {
            if (Test-Path $candidate) {
                return (Resolve-Path $candidate).ProviderPath
            }
        }
    }

    $expected = ($candidateDirs -join ", ")
    throw "Wheelhouse directory not found (looked in: $expected). Download hermetic-artifacts before installing."
}

function Resolve-ExpectedWheelHash {
    param(
        [Parameter(Mandatory = $true)][string]$ChecksumsFile,
        [Parameter(Mandatory = $true)][string]$WheelFile
    )

    $wheelLeaf = (Split-Path -Leaf $WheelFile).ToLowerInvariant()
    $checksumsDir = Split-Path -Parent $ChecksumsFile
    $pattern = "^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$"

    foreach ($line in Get-Content -Path $ChecksumsFile) {
        if (-not $line.Trim()) {
            continue
        }
        if ($line -notmatch $pattern) {
            throw "Malformed checksum line in $ChecksumsFile: $line"
        }
        $hash = $Matches[1].ToLowerInvariant()
        $entryPath = $Matches[2]
        $entryLeaf = (Split-Path -Leaf $entryPath).ToLowerInvariant()
        if ($entryLeaf -eq $wheelLeaf) {
            return $hash
        }

        $entryAbsolute = Join-Path -Path $checksumsDir -ChildPath $entryPath
        if (Test-Path $entryAbsolute) {
            $resolvedEntry = (Resolve-Path $entryAbsolute).ProviderPath
            if ($resolvedEntry -eq $WheelFile) {
                return $hash
            }
        }
    }

    throw "Wheel checksum entry not found in $ChecksumsFile for wheel $(Split-Path -Leaf $WheelFile)."
}

$python = Resolve-PythonInterpreter -ExplicitPath $PythonExecutable
$wheelDir = Resolve-WheelhouseDirectory -ExplicitPath $WheelhousePath
$lockFilePath = Resolve-ExistingPath -PathValue $LockFile -Label "Lockfile"

Invoke-CheckedCommand $python -m pip install --disable-pip-version-check --no-index --find-links $wheelDir --require-hashes -r $lockFilePath

if ($WheelPath) {
    $wheelFilePath = Resolve-ExistingPath -PathValue $WheelPath -Label "Wheel path"
    if ($ChecksumsPath) {
        $checksumsFilePath = Resolve-ExistingPath -PathValue $ChecksumsPath -Label "Checksums file"
        $expectedWheelHash = Resolve-ExpectedWheelHash -ChecksumsFile $checksumsFilePath -WheelFile $wheelFilePath
        $actualWheelHash = (Get-FileHash -Path $wheelFilePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualWheelHash -ne $expectedWheelHash) {
            throw "Wheel checksum mismatch for $(Split-Path -Leaf $wheelFilePath): expected $expectedWheelHash, got $actualWheelHash."
        }
    }

    Invoke-CheckedCommand $python -m pip install --disable-pip-version-check --no-index --find-links $wheelDir --no-deps $wheelFilePath
}
