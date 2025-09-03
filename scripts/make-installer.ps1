param()
if (-not (Get-Command iscc.exe -ErrorAction SilentlyContinue)) {
  choco install innosetup --no-progress -y | Out-Null
}
$version = python - <<'PY'
from earCrawler import __version__
print(__version__)
PY
$env:EARCRAWLER_VERSION = $version
iscc.exe installer/earcrawler.iss
