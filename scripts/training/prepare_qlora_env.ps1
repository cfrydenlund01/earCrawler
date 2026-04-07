param(
    [string]$RootPath = ".",
    [string]$VenvPath = ".venv",
    [string]$PythonLauncher = "py",
    [string]$PythonVersion = "3.11",
    [ValidateSet("auto", "cuda", "cpu", "manual")]
    [string]$TorchMode = "auto",
    [string]$TorchVersion = "2.4.1",
    [string]$CudaWheelTag = "cu121",
    [switch]$SkipBaseInstall,
    [switch]$SkipEditableInstall,
    [switch]$SkipTrainingExtrasInstall,
    [switch]$SkipTorchInstall,
    [switch]$CheckOnly,
    [string]$JsonOutPath = "dist/training/qlora_env_report.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Step
    )
    Write-Host ("[{0}] {1} {2}" -f $Step, $Executable, ($Arguments -join " "))
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw ("Command failed during step '{0}' (exit {1})." -f $Step, $LASTEXITCODE)
    }
}

function Resolve-VenvPythonPath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Venv
    )
    $venvBase = if ([IO.Path]::IsPathRooted($Venv)) {
        $Venv
    }
    else {
        Join-Path $Root $Venv
    }
    return [ordered]@{
        venv_base = $venvBase
        python = (Join-Path $venvBase "Scripts/python.exe")
    }
}

function Ensure-Venv {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Venv,
        [Parameter(Mandatory = $true)][string]$Launcher,
        [Parameter(Mandatory = $true)][string]$Version
    )
    $paths = Resolve-VenvPythonPath -Root $Root -Venv $Venv
    if (Test-Path $paths.python) {
        return $paths
    }

    $versionArgs = @()
    if ($Version) {
        $versionArgs = @("-$Version")
    }

    $created = $false
    if ($versionArgs.Count -gt 0) {
        try {
            Invoke-CheckedCommand -Executable $Launcher -Arguments ($versionArgs + @("-m", "venv", $paths.venv_base)) -Step "create-venv-versioned"
            $created = $true
        }
        catch {
            Write-Warning ("Python launcher version selector -{0} failed; falling back to default launcher resolution." -f $Version)
        }
    }

    if (-not $created) {
        Invoke-CheckedCommand -Executable $Launcher -Arguments @("-m", "venv", $paths.venv_base) -Step "create-venv-default"
    }

    if (-not (Test-Path $paths.python)) {
        throw "Expected venv interpreter was not created: $($paths.python)"
    }

    return $paths
}

function Probe-GpuPresence {
    $smi = Get-Command "nvidia-smi" -ErrorAction SilentlyContinue
    if ($null -eq $smi) {
        return [ordered]@{
            has_gpu = $false
            source = "nvidia-smi-not-found"
            gpu_names = @()
        }
    }
    $gpuNames = @(& $smi.Source --query-gpu=name --format=csv,noheader 2>$null)
    if ($LASTEXITCODE -ne 0) {
        return [ordered]@{
            has_gpu = $false
            source = "nvidia-smi-query-failed"
            gpu_names = @()
        }
    }
    $names = @($gpuNames | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
    return [ordered]@{
        has_gpu = ($names.Count -gt 0)
        source = "nvidia-smi"
        gpu_names = $names
    }
}

function Get-TorchRuntimeProbe {
    param([Parameter(Mandatory = $true)][string]$PythonPath)
    $probeScript = @'
import importlib.util
import json
import sys

result = {
    "python_executable": sys.executable,
    "python_version": sys.version,
}
try:
    import torch
    result["torch_version"] = getattr(torch, "__version__", "unknown")
    result["torch_cuda_is_available"] = bool(torch.cuda.is_available())
    result["torch_cuda_device_count"] = int(torch.cuda.device_count()) if torch.cuda.is_available() else 0
except Exception as exc:
    result["torch_import_error"] = str(exc)

for package in ("bitsandbytes", "transformers", "peft", "accelerate", "trl"):
    result[f"{package}_importable"] = importlib.util.find_spec(package) is not None

print(json.dumps(result, ensure_ascii=True))
'@
    $probeJson = & $PythonPath -c $probeScript
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to execute torch runtime probe."
    }
    return ($probeJson | ConvertFrom-Json)
}

function Get-OptionalFieldValue {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $false)]$DefaultValue = $null
    )
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) {
        return $DefaultValue
    }
    return $prop.Value
}

$repoRoot = (Resolve-Path $RootPath).Path
Set-Location $repoRoot

$gpuProbe = Probe-GpuPresence
$venvPaths = if ($CheckOnly) {
    Resolve-VenvPythonPath -Root $repoRoot -Venv $VenvPath
}
else {
    Ensure-Venv -Root $repoRoot -Venv $VenvPath -Launcher $PythonLauncher -Version $PythonVersion
}
$venvPython = $venvPaths.python

if (-not (Test-Path $venvPython)) {
    throw "Venv python not found: $venvPython"
}

$effectiveTorchMode = $TorchMode
if ($TorchMode -eq "auto") {
    $effectiveTorchMode = if ($gpuProbe.has_gpu) { "cuda" } else { "cpu" }
}

$installSummary = [ordered]@{
    base = "skipped"
    editable = "skipped"
    torch = "skipped"
    training_extras = "skipped"
}

if (-not $CheckOnly) {
    Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip") -Step "pip-upgrade"

    if (-not $SkipBaseInstall) {
        Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "pip", "install", "-r", "requirements.txt") -Step "install-base-requirements"
        $installSummary.base = "installed"
    }

    if (-not $SkipEditableInstall) {
        Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "pip", "install", "-e", ".") -Step "install-editable-package"
        $installSummary.editable = "installed"
    }

    if (-not $SkipTorchInstall) {
        $torchSpec = "torch==$TorchVersion"
        if ($effectiveTorchMode -eq "cuda") {
            Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "--index-url", "https://download.pytorch.org/whl/$CudaWheelTag", $torchSpec) -Step "install-torch-cuda"
            $installSummary.torch = "installed-cuda"
        }
        elseif ($effectiveTorchMode -eq "cpu") {
            Invoke-CheckedCommand -Executable $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "--index-url", "https://download.pytorch.org/whl/cpu", $torchSpec) -Step "install-torch-cpu"
            $installSummary.torch = "installed-cpu"
        }
        else {
            $installSummary.torch = "manual"
        }
    }

    if (-not $SkipTrainingExtrasInstall) {
        Invoke-CheckedCommand -Executable $venvPython -Arguments @(
            "-m",
            "pip",
            "install",
            "--upgrade",
            "transformers==5.5.0",
            "peft==0.18.1",
            "accelerate==1.13.0",
            "huggingface_hub==1.9.1",
            "trl==1.0.0",
            "bitsandbytes==0.49.2"
        ) -Step "install-qlora-training-extras"
        $installSummary.training_extras = "installed"
    }
}

$runtimeProbe = Get-TorchRuntimeProbe -PythonPath $venvPython

$report = [ordered]@{
    schema_version = "qlora-env-prepare.v1"
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    repo_root = $repoRoot
    venv_python = $venvPython
    torch_mode_requested = $TorchMode
    torch_mode_effective = $effectiveTorchMode
    gpu_probe = $gpuProbe
    install_summary = $installSummary
    runtime_probe = $runtimeProbe
}

if ($JsonOutPath) {
    $outPath = if ([IO.Path]::IsPathRooted($JsonOutPath)) {
        $JsonOutPath
    }
    else {
        Join-Path $repoRoot $JsonOutPath
    }
    $outDir = Split-Path -Parent $outPath
    if ($outDir) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -Path $outPath -Encoding utf8
Write-Host ("Wrote QLoRA env report: {0}" -f $outPath)
}

$torchVersion = Get-OptionalFieldValue -Object $runtimeProbe -Name "torch_version" -DefaultValue "not importable"
$cudaIsAvailable = [bool](Get-OptionalFieldValue -Object $runtimeProbe -Name "torch_cuda_is_available" -DefaultValue $false)
$cudaDeviceCount = [int](Get-OptionalFieldValue -Object $runtimeProbe -Name "torch_cuda_device_count" -DefaultValue 0)
$bitsandbytesImportable = [bool](Get-OptionalFieldValue -Object $runtimeProbe -Name "bitsandbytes_importable" -DefaultValue $false)
$transformersImportable = [bool](Get-OptionalFieldValue -Object $runtimeProbe -Name "transformers_importable" -DefaultValue $false)
$peftImportable = [bool](Get-OptionalFieldValue -Object $runtimeProbe -Name "peft_importable" -DefaultValue $false)
$accelerateImportable = [bool](Get-OptionalFieldValue -Object $runtimeProbe -Name "accelerate_importable" -DefaultValue $false)
$trlImportable = [bool](Get-OptionalFieldValue -Object $runtimeProbe -Name "trl_importable" -DefaultValue $false)

Write-Host ("Venv python: {0}" -f $venvPython)
Write-Host ("GPU detected: {0}" -f $gpuProbe.has_gpu)
Write-Host ("Torch version: {0}" -f $torchVersion)
Write-Host ("torch.cuda.is_available(): {0}" -f $cudaIsAvailable)
Write-Host ("torch.cuda.device_count(): {0}" -f $cudaDeviceCount)
Write-Host ("bitsandbytes importable: {0}" -f $bitsandbytesImportable)
Write-Host ("transformers importable: {0}" -f $transformersImportable)
Write-Host ("peft importable: {0}" -f $peftImportable)
Write-Host ("accelerate importable: {0}" -f $accelerateImportable)
Write-Host ("trl importable: {0}" -f $trlImportable)

if ($TorchMode -eq "manual" -or $effectiveTorchMode -eq "manual") {
    Write-Host "Manual torch install commands:"
    Write-Host ("  CUDA: {0} -m pip install --upgrade --index-url https://download.pytorch.org/whl/{1} torch=={2}" -f $venvPython, $CudaWheelTag, $TorchVersion)
    Write-Host ("  CPU : {0} -m pip install --upgrade --index-url https://download.pytorch.org/whl/cpu torch=={1}" -f $venvPython, $TorchVersion)
}
