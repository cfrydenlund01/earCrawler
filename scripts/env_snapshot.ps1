<#
.SYNOPSIS
Creates an environment snapshot in the latest runs\<timestamp>\ directory.

.EXAMPLE
pwsh .\scripts\env_snapshot.ps1
#>

param(
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-PythonExe([string]$Value) {
    if ($Value -and $Value.Trim()) {
        return $Value
    }
    if (Test-Path ".venv\Scripts\python.exe") {
        return ".venv\Scripts\python.exe"
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }
    return "python"
}

function Get-RepoRoot {
    $root = git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $root) {
        throw "This script must be run from inside a git repository."
    }
    return $root.Trim()
}

function Get-LatestRunDir([string]$RepoRoot) {
    $runsRoot = Join-Path $RepoRoot "runs"
    if (-not (Test-Path $runsRoot)) {
        return $null
    }
    return Get-ChildItem $runsRoot -Directory |
        Sort-Object Name -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}

function Get-NextArtifactPath([string]$Directory, [string]$BaseName) {
    $candidate = Join-Path $Directory $BaseName
    if (-not (Test-Path $candidate)) {
        return $candidate
    }

    $stem = [System.IO.Path]::GetFileNameWithoutExtension($BaseName)
    $ext = [System.IO.Path]::GetExtension($BaseName)
    $suffix = 1
    while ($true) {
        $next = Join-Path $Directory ("{0}_{1:D2}{2}" -f $stem, $suffix, $ext)
        if (-not (Test-Path $next)) {
            return $next
        }
        $suffix += 1
    }
}

function Write-LogFile([string]$Path, [object[]]$Content) {
    $normalized = @()
    if ($null -ne $Content) {
        $normalized = @($Content | ForEach-Object { "$_" })
    }
    Set-Content -Path $Path -Value $normalized -Encoding utf8
}

function Get-WindowsPlatform {
    $caption = $null
    $version = $null
    $build = $null

    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $caption = $os.Caption
        $version = $os.Version
        $build = $os.BuildNumber
    } catch {
        $versionInfo = [System.Environment]::OSVersion.Version
        $caption = "Windows"
        $version = $versionInfo.ToString()
        $build = "$($versionInfo.Build)"
    }

    return [ordered]@{
        name = $caption
        version = $version
        build = $build
    }
}

function Is-SecretName([string]$Name) {
    return $Name -match 'KEY|TOKEN|SECRET|PASSWORD'
}

function Get-ProjectEnvSnapshot {
    $prefixes = @(
        "EARCRAWLER_",
        "EAR_",
        "RAG_",
        "KG_",
        "OPENAI_",
        "AZURE_",
        "HF_",
        "TRANSFORMERS_",
        "SENTENCE_TRANSFORMERS_",
        "TOKENIZERS_"
    )

    $selected = [ordered]@{}
    foreach ($item in Get-ChildItem Env:) {
        $name = $item.Name
        $matchesPrefix = $false
        foreach ($prefix in $prefixes) {
            if ($name.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                $matchesPrefix = $true
                break
            }
        }

        if (-not $matchesPrefix -and $name -notin @("PYTHONPATH", "SOURCE_DATE_EPOCH")) {
            continue
        }

        if (Is-SecretName $name) {
            $selected[$name] = "[REDACTED]"
        } else {
            $selected[$name] = $item.Value
        }
    }

    return $selected
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

$runDir = Get-LatestRunDir -RepoRoot $repoRoot
if (-not $runDir) {
    Write-Error "No runs/<timestamp>/ directory found."
    exit 1
}

$python = Resolve-PythonExe -Value $PythonExe
$pythonVersionPath = Join-Path $runDir "python_version.txt"
$envFreezePath = Join-Path $runDir "env_freeze.txt"
$envSnapshotPath = Get-NextArtifactPath -Directory $runDir -BaseName "env_snapshot.json"

if (-not (Test-Path $pythonVersionPath)) {
    $pythonVersionOutput = & $python -V 2>&1
    Write-LogFile -Path $pythonVersionPath -Content $pythonVersionOutput
}

if (-not (Test-Path $envFreezePath)) {
    $envFreezeOutput = & $python -m pip freeze 2>&1
    $freezeExit = $LASTEXITCODE
    Write-LogFile -Path $envFreezePath -Content $envFreezeOutput
    if ($freezeExit -ne 0) {
        throw "pip freeze failed (exit $freezeExit)."
    }
}

$pythonMetaJson = & $python -c "import json, os, sys; print(json.dumps({'executable': sys.executable, 'version': sys.version, 'prefix': sys.prefix, 'base_prefix': getattr(sys, 'base_prefix', sys.prefix), 'venv_active': sys.prefix != getattr(sys, 'base_prefix', sys.prefix), 'virtual_env': os.getenv('VIRTUAL_ENV'), 'conda_prefix': os.getenv('CONDA_PREFIX')}))"
if ($LASTEXITCODE -ne 0 -or -not $pythonMetaJson) {
    throw "Failed to query Python runtime metadata."
}
$pythonMeta = $pythonMetaJson | ConvertFrom-Json

$commit = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $commit) {
    throw "Unable to resolve HEAD commit."
}

$branch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to resolve current branch."
}

$gitStatusLines = @(git status --porcelain)
if ($LASTEXITCODE -ne 0) {
    throw "git status failed."
}

$pathEntries = @()
if ($env:PATH) {
    $pathEntries = @($env:PATH -split ';' | Where-Object { $_ -and $_.Trim() })
}

$snapshot = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    run_dir = $runDir
    os = [ordered]@{
        platform = Get-WindowsPlatform
        shell = [ordered]@{
            name = if ($PSVersionTable.PSEdition) { "PowerShell $($PSVersionTable.PSEdition)" } else { "PowerShell" }
            version = $PSVersionTable.PSVersion.ToString()
        }
        user = $env:USERNAME
        cwd = (Get-Location).Path
    }
    python = [ordered]@{
        executable = $pythonMeta.executable
        sys_version = $pythonMeta.version
        virtual_env = $pythonMeta.virtual_env
        conda_prefix = $pythonMeta.conda_prefix
        venv_active = [bool]$pythonMeta.venv_active
        sys_prefix = $pythonMeta.prefix
        sys_base_prefix = $pythonMeta.base_prefix
    }
    repo = [ordered]@{
        git_commit = $commit
        active_branch = $branch
        working_tree_dirty = ($gitStatusLines.Count -gt 0)
        git_status_porcelain = $gitStatusLines
    }
    env = [ordered]@{
        vars = Get-ProjectEnvSnapshot
        PATH = [ordered]@{
            first_entries = @($pathEntries | Select-Object -First 3)
            total_entries = $pathEntries.Count
        }
    }
}

$snapshot | ConvertTo-Json -Depth 8 | Set-Content -Path $envSnapshotPath -Encoding utf8

Write-Host ("run_dir: {0}" -f $runDir)
Write-Host ("env_snapshot: {0}" -f $envSnapshotPath)
Write-Host ("python_version: {0}" -f $pythonVersionPath)
Write-Host ("env_freeze: {0}" -f $envFreezePath)

exit 0
