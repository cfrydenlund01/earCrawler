param()
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
& py -m pip install --upgrade build > $null
& py -m build --wheel
