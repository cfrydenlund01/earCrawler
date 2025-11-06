param(
    [string]$Python = "py",
    [switch]$SkipExe,
    [switch]$SkipInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Process {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$Title
    )

    Write-Host "==> $Title"
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $FilePath
    foreach ($arg in $Arguments) {
        $psi.ArgumentList.Add($arg)
    }
    $psi.WorkingDirectory = (Resolve-Path ".").Path
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardOutput = $true
    $psi.UseShellExecute = $false

    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    if ($stdout) { Write-Host $stdout.Trim() }
    if ($stderr) { Write-Warning $stderr.Trim() }
    if ($proc.ExitCode -ne 0) {
        throw "Command failed ($Title) with exit code $($proc.ExitCode)"
    }
}

Write-Host "Cleaning dist and build artifacts"
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
if (Test-Path build\release) { Remove-Item -Recurse -Force build\release }
New-Item -ItemType Directory -Path dist -Force | Out-Null
New-Item -ItemType Directory -Path build\release -Force | Out-Null

Invoke-Process -FilePath $Python -Arguments @(
    "-m", "pip", "install", "--upgrade", "pip", "build", "twine"
) -Title "Install build tooling"

Invoke-Process -FilePath $Python -Arguments @(
    "-m", "build", "--wheel", "--outdir", (Resolve-Path "dist").Path
) -Title "Build wheel"

if (-not $SkipExe) {
    Invoke-Process -FilePath $Python -Arguments @(
        "-m", "pip", "install", "--upgrade", "pyinstaller"
    ) -Title "Ensure PyInstaller"
    Invoke-Process -FilePath "pyinstaller" -Arguments @(
        "--clean",
        "--noconfirm",
        "--distpath", (Resolve-Path "build/release").Path,
        "--workpath", (Resolve-Path "build/pyinstaller").Path,
        "packaging/earctl.spec"
    ) -Title "Build Windows executable"
}
else {
    Write-Host "Skipping EXE build"
}

if (-not $SkipInstaller) {
    $iscc = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($null -eq $iscc) {
        Write-Warning "Inno Setup (iscc.exe) not found on PATH; skipping installer."
    }
    else {
        Invoke-Process -FilePath $iscc.Source -Arguments @(
            (Resolve-Path "installer/earcrawler.iss").Path
        ) -Title "Build Inno Setup installer"
    }
}
else {
    Write-Host "Skipping installer build"
}

$checksums = Join-Path "dist" "CHECKSUMS.sha256"
Get-ChildItem -Path dist -File | Where-Object { $_.Name -notlike "CHECKSUMS.sha256" } |
    Get-FileHash -Algorithm SHA256 |
    ForEach-Object { "{0}  {1}" -f $_.Hash, (Split-Path -Leaf $_.Path) } |
    Set-Content -Path $checksums -Encoding UTF8
Write-Host "Checksums written to $checksums"

$distFiles = Get-ChildItem -Path dist -File | Select-Object -ExpandProperty FullName
if ($distFiles.Count -gt 0) {
    $args = @("-m", "twine", "check")
    $args += $distFiles
    Invoke-Process -FilePath $Python -Arguments $args -Title "Validate artifacts with twine"
}
else {
    Write-Warning "No distribution files found for twine validation."
}

Write-Host "Release build complete."
