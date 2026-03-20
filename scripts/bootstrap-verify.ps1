param(
    [string]$RootPath = ".",
    [string]$VenvPath = ".venv",
    [int]$MinJavaMajor = 11,
    [switch]$SkipPyLauncherCheck,
    [switch]$SkipVenvCheck,
    [switch]$SkipJavaCheck,
    [string]$JsonOutPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Add-CheckResult {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][bool]$Passed,
        [Parameter(Mandatory = $true)][string]$Detail
    )
    return [ordered]@{
        name = $Name
        passed = $Passed
        detail = $Detail
    }
}

function Get-JavaMajorVersion {
    $line = (& java -version 2>&1 | Select-Object -First 1)
    if (-not $line) {
        return [ordered]@{ ok = $false; major = 0; detail = "java -version did not return output." }
    }
    $text = [string]$line
    if ($text -match '"(?<version>[0-9]+(\.[0-9]+)*)') {
        $version = [string]$Matches["version"]
        if ($version.StartsWith("1.")) {
            $parts = $version.Split(".")
            if ($parts.Length -gt 1) {
                return [ordered]@{ ok = $true; major = [int]$parts[1]; detail = $text }
            }
        }
        $majorToken = $version.Split(".")[0]
        return [ordered]@{ ok = $true; major = [int]$majorToken; detail = $text }
    }
    return [ordered]@{ ok = $false; major = 0; detail = "Unable to parse java version line: $text" }
}

$resolvedRoot = (Resolve-Path $RootPath).Path
$checks = @()

$pwshVersion = $PSVersionTable.PSVersion.ToString()
$checks += Add-CheckResult -Name "powershell_available" -Passed $true -Detail "pwsh $pwshVersion"

if ($SkipPyLauncherCheck) {
    $checks += Add-CheckResult -Name "py_launcher" -Passed $true -Detail "skipped"
}
else {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($null -eq $pyCmd) {
        $checks += Add-CheckResult -Name "py_launcher" -Passed $false -Detail "py launcher not found on PATH."
    }
    else {
        $pyVersion = (& py --version 2>&1 | Select-Object -First 1)
        $checks += Add-CheckResult -Name "py_launcher" -Passed $true -Detail ([string]$pyVersion)
    }
}

if ($SkipVenvCheck) {
    $checks += Add-CheckResult -Name "project_venv" -Passed $true -Detail "skipped"
}
else {
    $venvBase = if ([IO.Path]::IsPathRooted($VenvPath)) {
        $VenvPath
    }
    else {
        Join-Path $resolvedRoot $VenvPath
    }
    $venvPython = $venvBase
    $venvPython = Join-Path $venvPython "Scripts/python.exe"
    if (-not (Test-Path $venvPython)) {
        $checks += Add-CheckResult -Name "project_venv" -Passed $false -Detail "Missing expected venv interpreter: $venvPython"
    }
    else {
        $venvVersion = (& $venvPython --version 2>&1 | Select-Object -First 1)
        $checks += Add-CheckResult -Name "project_venv" -Passed $true -Detail ([string]$venvVersion)
    }
}

if ($SkipJavaCheck) {
    $checks += Add-CheckResult -Name "java_runtime" -Passed $true -Detail "skipped"
}
else {
    $javaCmd = Get-Command java -ErrorAction SilentlyContinue
    if ($null -eq $javaCmd) {
        $checks += Add-CheckResult -Name "java_runtime" -Passed $false -Detail "java not found on PATH."
    }
    else {
        $versionInfo = Get-JavaMajorVersion
        if (-not $versionInfo.ok) {
            $checks += Add-CheckResult -Name "java_runtime" -Passed $false -Detail $versionInfo.detail
        }
        elseif ([int]$versionInfo.major -lt $MinJavaMajor) {
            $checks += Add-CheckResult -Name "java_runtime" -Passed $false -Detail "Java major version $($versionInfo.major) is below required minimum $MinJavaMajor. $($versionInfo.detail)"
        }
        else {
            $checks += Add-CheckResult -Name "java_runtime" -Passed $true -Detail $versionInfo.detail
        }
    }
}

$result = [ordered]@{
    schema_version = "bootstrap-verify.v1"
    root = $resolvedRoot
    checks = $checks
    overall_status = if ((@($checks | Where-Object { -not $_.passed })).Count -eq 0) { "passed" } else { "failed" }
}

if ($JsonOutPath) {
    $outDir = Split-Path -Parent $JsonOutPath
    if ($outDir) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }
    $result | ConvertTo-Json -Depth 5 | Set-Content -Path $JsonOutPath -Encoding utf8
}

foreach ($check in $checks) {
    $status = if ($check.passed) { "passed" } else { "failed" }
    Write-Host ("[{0}] {1}: {2}" -f $status, $check.name, $check.detail)
}

if ($result.overall_status -ne "passed") {
    $failures = @($checks | Where-Object { -not $_.passed } | ForEach-Object { " - $($_.name): $($_.detail)" })
    throw ("Bootstrap verification failed:`n" + ($failures -join [Environment]::NewLine))
}

Write-Host "Bootstrap verification passed."
