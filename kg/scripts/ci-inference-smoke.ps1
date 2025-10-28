param(
    [ValidateSet('rdfs','owlmini')]
    [string]$Mode = 'rdfs',
    [string]$AssemblerPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
 
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
function Resolve-KgPython {
    if ($env:EARCTL_PYTHON) {
        return $env:EARCTL_PYTHON
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return 'py'
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return 'python'
    }
    throw 'Python interpreter not found. Set EARCTL_PYTHON or ensure py/python is on PATH.'
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
