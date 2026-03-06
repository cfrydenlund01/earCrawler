param()

$ErrorActionPreference = "Stop"

function Resolve-PythonInterpreter {
  if ($env:EARCTL_PYTHON -and (Test-Path $env:EARCTL_PYTHON)) {
    return $env:EARCTL_PYTHON
  }
  if ($env:pythonLocation) {
    $candidate = Join-Path $env:pythonLocation "python.exe"
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  foreach ($name in "python", "python.exe", "python3", "py") {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
      return $cmd.Source
    }
  }
  throw "Python interpreter not found on PATH."
}

$python = Resolve-PythonInterpreter

& $python -m pip install --disable-pip-version-check --upgrade build | Out-Null
& $python -m build --wheel

$wheel = Get-ChildItem dist -Filter "*.whl" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

if (-not $wheel) {
  throw "Wheel build failed: no wheel found in dist/."
}

$smokeRoot = Join-Path $env:TEMP ("earcrawler-wheel-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null

try {
  & $python -m venv (Join-Path $smokeRoot ".venv")

  $venvPython = Join-Path $smokeRoot ".venv\Scripts\python.exe"
  $venvScripts = Join-Path $smokeRoot ".venv\Scripts"
  $earctl = Join-Path $venvScripts "earctl.exe"
  $kgValidate = Join-Path $venvScripts "kg-validate.exe"

  if (-not (Test-Path $venvPython)) {
    throw "Virtualenv bootstrap failed: python executable not found."
  }

  & $venvPython -m pip install --disable-pip-version-check --upgrade pip | Out-Null
  & $venvPython -m pip install --disable-pip-version-check $wheel.FullName

  if (-not (Test-Path $earctl)) {
    throw "Packaging smoke failed: earctl entrypoint was not installed."
  }
  if (-not (Test-Path $kgValidate)) {
    throw "Packaging smoke failed: kg-validate entrypoint was not installed."
  }

  & $earctl --version
  & $kgValidate --help | Out-Null
  & $venvPython -m earCrawler.cli --version
}
finally {
  Remove-Item -Recurse -Force $smokeRoot -ErrorAction SilentlyContinue
}
