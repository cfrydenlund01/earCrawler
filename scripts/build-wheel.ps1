param()
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
python -m pip install --upgrade build > $null
python -m build --wheel
