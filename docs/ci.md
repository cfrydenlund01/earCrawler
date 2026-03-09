# Continuous Integration

The workflow in `.github/workflows/ci.yml` runs on:

- every push to any branch
- every pull request
- every tag matching `v*`

## Jobs

- `cpu`
  Runs on `windows-latest` for pushes, pull requests, and tags. It checks out the repo, validates pinned versions, sets up Python 3.11, caches pip, installs `requirements.txt` plus the editable package, runs `scripts/package-wheel-smoke.ps1` (clean-room wheel install/entrypoint/resource validation in an isolated temp venv), checks formatting/lint with Black and Flake8, runs `pytest -q --disable-warnings --maxfail=1`, executes the offline corpus determinism gate, then validates the supported evidence path in this order: corpus build, corpus validate, KG emit, SHACL-only KG validation, supported-route API smoke, and no-network RAG smoke. After that it enforces the Phase B baseline drift and determinism gates, validates eval datasets, and uploads `dist/eval` as an artifact when present.

- `gpu`
  Runs only on pushes to `main`, on `ubuntu-latest`, with `continue-on-error: true`. It sets up Python 3.11, installs `requirements-gpu.txt`, caches the Hugging Face model directory, and runs `pytest -m gpu`.

- `benchmark`
  Runs only on pushes to `main`, on `windows-gpu-t4`, after `cpu`, with `continue-on-error: true`. It installs `requirements-gpu.txt`, runs `eval/collect_benchmark.sh`, and uploads `benchmark.md` as an artifact.

- `release`
  Runs only for tag refs after `cpu` passes, on `windows-latest`. It performs the staging monitor check via `monitor.ps1`.

## Secrets

The workflow exposes these repository secrets to jobs that declare them:

- `TRADEGOV_API_KEY`
- `FEDREG_API_KEY`

Define them under GitHub repository **Secrets and variables -> Actions**.

## Notes

- The CPU job includes the packaging smoke gate; `docs/ci.md` should be updated if that script or its position in the workflow changes.
- The workflow does not currently upload coverage to Codecov.
- The GPU and benchmark jobs are non-blocking because both are marked `continue-on-error: true`.
