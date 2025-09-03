# Hermetic toolchain

The repository uses a checksum-verified toolchain for Java and Python.

## Versions and checksums

`tools/versions.json` holds pinned versions and SHA512 checksums for the
Apache Jena and Fuseki archives as well as the paths to the Python lockfiles.
These hashes are verified before extraction by `ensure_jena` and
`ensure_fuseki`.

## Wheelhouse

Windows builds use `scripts/build-wheelhouse.ps1` to download the pinned
packages defined in `requirements-win-lock.txt` and store wheels under
`.wheelhouse/`. Each wheel's SHA256 is checked against the lockfile and the
verified filenames and hashes are written to `.wheelhouse/manifest.json`.

Packages are installed without network access using
`scripts/install-from-wheelhouse.ps1` which invokes
`pip install --no-index --find-links .\.wheelhouse --require-hashes`.

## SBOM

`scripts/sbom-cyclonedx.ps1` emits a CycloneDX JSON SBOM to
`dist/sbom.cdx.json`. `scripts/attest-sbom.ps1` uploads the SBOM and performs a
no-op attestation when not running on GitHub Actions.
