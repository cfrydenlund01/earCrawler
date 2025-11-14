param()

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
  foreach ($name in 'python', 'python.exe', 'python3', 'py') {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
      return $cmd.Source
    }
  }
  throw "Python interpreter not found on PATH."
}

$python = Resolve-PythonInterpreter
$env:EARCTL_PYTHON = $python

Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
$version = & $python -c "from earCrawler import __version__; print(__version__)"
$version = $version.Trim()
& $python -m PyInstaller --noconfirm --clean packaging/earctl.spec
$src1 = Join-Path "dist" "earctl.exe"
$src2 = Join-Path "dist/earctl" "earctl.exe"
$dest = Join-Path "dist" ("earctl-{0}-win64.exe" -f $version)
if (Test-Path $src1) {
  Copy-Item $src1 $dest -Force
  Remove-Item $src1 -Force
} elseif (Test-Path $src2) {
  Copy-Item $src2 $dest -Force
} else {
  Write-Warning "PyInstaller output not found at expected paths."
}
