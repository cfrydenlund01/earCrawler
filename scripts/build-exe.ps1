param()
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
$version = & py -c "from earCrawler import __version__; print(__version__)" 2>$null
if (-not $version) {
  $version = & python -c "from earCrawler import __version__; print(__version__)"
}
$version = $version.Trim()
& py -m PyInstaller --noconfirm --clean packaging/earctl.spec
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
