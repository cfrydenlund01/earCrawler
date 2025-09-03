param()
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
$version = python - <<'PY'
from earCrawler import __version__
print(__version__)
PY
pyinstaller --noconfirm --clean --specpath packaging packaging/earctl.spec
Rename-Item "dist/earctl.exe" "dist/earctl-$version-win64.exe"
