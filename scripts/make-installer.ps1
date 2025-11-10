param()
if (-not (Get-Command iscc.exe -ErrorAction SilentlyContinue)) {
  choco install innosetup --no-progress -y | Out-Null
}
$version = & py -c "from earCrawler import __version__; print(__version__)" 2>$null
if (-not $version) {
  $version = & python -c "from earCrawler import __version__; print(__version__)"
}
$version = $version.Trim()
$env:EARCRAWLER_VERSION = $version
iscc.exe installer/earcrawler.iss
