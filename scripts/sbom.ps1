param()
if (!(Test-Path dist)) { New-Item -ItemType Directory -Path dist | Out-Null }
pip-licenses --format=json --output-file dist/sbom.spdx.json
