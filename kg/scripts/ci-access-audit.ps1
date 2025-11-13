$ErrorActionPreference = 'Stop'
$env:EARCTL_USER = 'ci_user'

function Invoke-Earctl {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $exe = Get-Command earctl -ErrorAction SilentlyContinue
    if ($exe) {
        return & $exe.Source @Arguments
    }

    $pythonCmd = $null
    if ($env:EARCTL_PYTHON -and (Test-Path $env:EARCTL_PYTHON)) {
        $pythonCmd = @{ Path = $env:EARCTL_PYTHON; Args = @() }
    } else {
        foreach ($name in 'python', 'python.exe', 'python3', 'python3.exe') {
            $candidate = Get-Command $name -ErrorAction SilentlyContinue
            if ($candidate) {
                $pythonCmd = @{ Path = $candidate.Source; Args = @() }
                break
            }
        }
        if (-not $pythonCmd) {
            $launcher = Get-Command 'py' -ErrorAction SilentlyContinue
            if ($launcher) {
                $pythonCmd = @{ Path = $launcher.Source; Args = @('-3') }
            }
        }
    }

    if (-not $pythonCmd) {
        throw "earctl command not found and Python interpreter is unavailable."
    }

    $args = @()
    if ($pythonCmd.Args) { $args += $pythonCmd.Args }
    $args += @('-m', 'earCrawler.cli')
    $args += $Arguments
    return & $pythonCmd.Path @args
}

function Invoke-EarctlText {
    param([string[]]$Args)
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
