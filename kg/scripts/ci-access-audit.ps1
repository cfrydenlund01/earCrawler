$ErrorActionPreference = 'Stop'
$env:EARCTL_USER = 'ci_user'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:PythonPath = $null

function Resolve-PythonPath {
    if ($script:PythonPath) { return $script:PythonPath }
    if ($env:EARCTL_PYTHON -and (Test-Path $env:EARCTL_PYTHON)) {
        $script:PythonPath = (Resolve-Path $env:EARCTL_PYTHON).Path
        return $script:PythonPath
    }
    foreach ($name in 'python', 'python.exe', 'python3', 'python3.exe') {
        $candidate = Get-Command $name -ErrorAction SilentlyContinue
        if ($candidate) {
            $script:PythonPath = $candidate.Source
            return $script:PythonPath
        }
    }
    $launcher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $exe = & $launcher.Source -3 -c "import sys; print(sys.executable)"
            if ($LASTEXITCODE -eq 0 -and $exe) {
                $script:PythonPath = $exe.Trim()
                return $script:PythonPath
            }
        } catch {}
    }
    if ($env:VIRTUAL_ENV) {
        $cand = Join-Path $env:VIRTUAL_ENV 'Scripts/python.exe'
        if (Test-Path $cand) { $script:PythonPath = $cand; return $script:PythonPath }
        $cand = Join-Path $env:VIRTUAL_ENV 'bin/python3'
        if (Test-Path $cand) { $script:PythonPath = $cand; return $script:PythonPath }
    }
    throw 'earctl command not found and Python interpreter is unavailable.'
}

function Invoke-Python {
    param([string[]]$Arguments)
    $python = Resolve-PythonPath
    & $python @Arguments
}

$pythonPath = Resolve-PythonPath
$env:EARCTL_PYTHON = $pythonPath

$requirements = Join-Path $repoRoot 'requirements-win.txt'
if (($env:EARCTL_SKIP_PIP -ne '1') -and (Test-Path $requirements)) {
    Write-Host "Installing access audit dependencies from $requirements"
    Invoke-Python @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $requirements) | Out-Null
}

function Invoke-Earctl {
    param(
        [Parameter(Mandatory, ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    if (-not $Arguments -or $Arguments.Count -eq 0) {
        throw "Invoke-Earctl requires at least one argument."
    }

    $exe = Get-Command earctl -ErrorAction SilentlyContinue
    if ($exe) {
        return & $exe.Source @Arguments
    }

    $args = @('-m', 'earCrawler.cli')
    $args += $Arguments
    return Invoke-Python -Arguments $args
}

function Invoke-EarctlText {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Args
    )
    $output = Invoke-Earctl -Arguments $Args
    if ($null -eq $output) { return '' }
    if ($output -is [System.Array]) {
        return ($output | Out-String).Trim()
    }
    return ($output | Out-String).Trim()
}

$report = New-Object System.Collections.ArrayList
$report.Add((Invoke-EarctlText policy whoami)) | Out-Null
$report.Add((Invoke-EarctlText diagnose)) | Out-Null
try {
    Invoke-Earctl gc --dry-run | Out-Null
} catch {
    $report.Add('gc denied') | Out-Null
}
$verify = Invoke-EarctlText audit verify
$report.Add($verify) | Out-Null
New-Item -ItemType Directory -Force -Path kg/reports | Out-Null
$report | Out-File -FilePath kg/reports/access-audit.txt -Encoding utf8
