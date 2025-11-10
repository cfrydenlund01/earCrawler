param()
if (!(Test-Path dist)) { New-Item -ItemType Directory -Path dist | Out-Null }
& py -m pip install --quiet pip-licenses | Out-Null
& py -m piplicenses --format json --output-file dist/sbom.spdx.json
