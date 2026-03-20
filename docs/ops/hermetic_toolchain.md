# Hermetic toolchain

The repository uses a checksum-verified toolchain for Java and Python.

## Dependency sources

`requirements.in` is the authoritative dependency input for this repository
across runtime and development workflows.

`pyproject.toml` remains the authoritative packaging metadata file, but its
runtime dependency list is treated as a publish-time subset contract that must
remain represented in `requirements.in`.

There is intentionally no separate `requirements-dev.txt`; development and test
dependencies are also declared in `requirements.in` and pinned through the same
lockfile pipeline.

Derived files are:

- `requirements.txt` (wrapper used by standard installs/CI)
- `requirements-lock.txt` (hash-locked output from `requirements.in`)
- `requirements-win-lock.txt` (hash-locked output from `requirements-win.in`)

Regenerate lockfiles after changing `requirements.in`:

```powershell
py -m piptools compile --generate-hashes --output-file=requirements-lock.txt requirements.in
py -m piptools compile --generate-hashes --output-file=requirements-win-lock.txt requirements-win.in
```

Validate dependency-policy consistency (wrappers, lock headers, and
`pyproject.toml` runtime subset alignment):

```powershell
py scripts/verify-dependency-policy.py
```

## Bootstrap verification

Use one command to verify Windows-first prerequisites for source-checkout work:

```powershell
pwsh scripts/bootstrap-verify.ps1
```

Default checks validate:

- `pwsh` availability
- `py` launcher availability
- project `.venv\Scripts\python.exe`
- Java runtime on `PATH` with major version >= 11

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
For release-grade host install, pass the release wheel and checksums file so the
same script verifies the wheel digest before offline install:

```powershell
pwsh scripts/install-from-wheelhouse.ps1 `
  -LockFile requirements-win-lock.txt `
  -WheelhousePath .wheelhouse `
  -WheelPath dist/earcrawler-<version>-py3-none-any.whl `
  -ChecksumsPath dist/checksums.sha256
```

Release packaging publishes the same payload as `dist/hermetic-artifacts.zip`
(`requirements-win-lock.txt`, `.wheelhouse/`, and `scripts/install-from-wheelhouse.ps1`).

## SBOM

`scripts/sbom-cyclonedx.ps1` emits a CycloneDX JSON SBOM to
`dist/sbom.cdx.json`. `scripts/attest-sbom.ps1` uploads the SBOM and performs a
no-op attestation when not running on GitHub Actions.
