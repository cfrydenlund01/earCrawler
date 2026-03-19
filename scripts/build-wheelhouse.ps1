param([string]$LockFile = "requirements-win-lock.txt")

function Resolve-PythonInterpreter {
    foreach ($name in @("python", "python.exe", "py")) {
        $candidate = Get-Command $name -ErrorAction SilentlyContinue
        if ($candidate) {
            return $candidate.Source
        }
    }
    throw "Python interpreter not found on PATH."
}

$repoRoot = Resolve-Path "$PSScriptRoot/.."
$wheelDir = Join-Path $repoRoot ".wheelhouse"
Remove-Item -Recurse -Force -ErrorAction Ignore $wheelDir
New-Item -ItemType Directory -Force -Path $wheelDir | Out-Null

$python = Resolve-PythonInterpreter
& $python -m pip download -r $LockFile -d $wheelDir | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "pip download failed with exit code ${LASTEXITCODE}."
}

$hashes = @{}
$pattern = '--hash=sha256:([0-9a-f]{64})'
Get-Content $LockFile | ForEach-Object {
    if ($_ -match $pattern) { $hashes[$matches[1].ToLower()] = $true }
}

$manifest = @{}
Get-ChildItem $wheelDir -Filter *.whl | ForEach-Object {
    $sha = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    if (-not $hashes.ContainsKey($sha)) {
        throw "Wheel $($_.Name) SHA256 $sha not present in lockfile"
    }
    $manifest[$_.Name] = $sha
}

$manifestPath = Join-Path $wheelDir 'manifest.json'
$manifest | ConvertTo-Json | Set-Content $manifestPath -Encoding UTF8
