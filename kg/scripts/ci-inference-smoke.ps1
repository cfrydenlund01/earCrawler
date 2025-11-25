param(
    [ValidateSet('rdfs','owlmini')]
    [string]$Mode = 'rdfs',
    [string]$AssemblerPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
 
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
function Resolve-KgPython {
    if ($env:EARCTL_PYTHON -and (Test-Path $env:EARCTL_PYTHON)) {
        return (Resolve-Path $env:EARCTL_PYTHON).Path
    }
    foreach ($name in 'python', 'python.exe', 'python3', 'python3.exe') {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    $launcher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $exe = & $launcher.Source -3 -c "import sys; print(sys.executable)"
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch {}
    }
    if ($env:VIRTUAL_ENV) {
        $candidate = Join-Path $env:VIRTUAL_ENV 'Scripts/python.exe'
        if (Test-Path $candidate) { return $candidate }
        $candidate = Join-Path $env:VIRTUAL_ENV 'bin/python3'
        if (Test-Path $candidate) { return $candidate }
    }
    throw 'Python interpreter not found. Set EARCTL_PYTHON or ensure python is on PATH.'
}
$python = Resolve-KgPython
$args = @('-m', 'earCrawler.pipelines.inference_smoke', '--mode', $Mode)
$process = & $python @args 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Inference pipeline failed`n$process"
    exit 1
}
Write-Host "Inference $Mode smoke succeeded"
exit 0
