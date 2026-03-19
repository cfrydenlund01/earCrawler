# Continuous Integration

The workflow in `.github/workflows/ci.yml` runs on:

- every push to any branch
- every pull request
- every tag matching `v*`

## Jobs

- `cpu`
  Runs on `windows-latest` for pushes, pull requests, and tags. It checks out the repo, validates pinned versions, sets up Python 3.11, caches pip, installs `requirements.txt` plus the editable package, runs `scripts/package-wheel-smoke.ps1` (clean-room wheel install/entrypoint/resource validation in an isolated temp venv), checks formatting/lint with Black and Flake8, then runs `scripts/security-baseline.ps1` to produce security evidence:
  - dependency audit via `pip-audit` against `requirements-win-lock.txt` (with temporary ignore list `security/pip_audit_ignore.txt`)
  - static analysis via Bandit (`high-severity`, `high-confidence`)
  - secret-pattern scanning via `scripts/security_secret_scan.py`

  Security outputs are written under `dist/security/` and uploaded as the `security-baseline` artifact. The CPU job then erases any stale `.coverage` data and runs `pytest -q --disable-warnings --maxfail=1 --cov --cov-report=xml:dist/coverage/coverage.xml --cov-report=term-missing:skip-covered`. Coverage is collected for `earCrawler`, `api_clients`, `service`, and `cli`, and the build fails if total coverage drops below 75%. It then runs the API latency/failure budget gate from `perf/config/api_route_budgets.yml`, writing `dist/perf/api_perf_smoke.json`. The default gate enforces route-level p95 latency, zero-failure expectations, and timeout behavior for supported routes (currently `/v1/rag/query`). Quarantined `/v1/search` coverage remains available only as explicit opt-in local validation via `py scripts/api_perf_smoke.py --include-quarantined`. The job uploads `dist/coverage/coverage.xml` as the `coverage-xml` artifact, executes the offline corpus determinism gate, then validates the supported evidence path in this order: corpus build, corpus validate, KG emit, KG semantic gate (`--fail-on supported` with release-blocking checks `orphan_paragraphs` and `entity_mentions_without_type`), supported-route API smoke, optional runtime smoke (`scripts/optional-runtime-smoke.ps1` with `-SkipLocalAdapter`), and no-network RAG smoke. After that it enforces the Phase B baseline drift and determinism gates, validates eval datasets, and uploads `dist/eval` as an artifact when present.

- `gpu`
  Runs only on pushes to `main`, on `ubuntu-latest`, with `continue-on-error: true`. It sets up Python 3.11, installs `requirements-gpu.txt`, caches the Hugging Face model directory, and runs `pytest -m gpu`.

- `benchmark`
  Runs only on pushes to `main`, on `windows-gpu-t4`, after `cpu`, with `continue-on-error: true`. It installs `requirements-gpu.txt`, runs `eval/collect_benchmark.sh`, and uploads `benchmark.md` as an artifact.

- `release`
  Runs only for tag refs after `cpu` passes, on `windows-latest`. It builds release artifacts, runs clean-room wheel smoke, runs `scripts/security-baseline.ps1` to generate release security evidence under `dist/security/`, packages `dist/hermetic-artifacts.zip`, signs and checksums distributables, then runs installed-runtime smoke from the same release bundle shape operators receive (`scripts/installed-runtime-smoke.ps1 -HermeticBundleZipPath dist/hermetic-artifacts.zip -ReleaseChecksumsPath dist/checksums.sha256`). While supported API smoke is running, it also runs `scripts/health/api-probe.ps1` and writes observability evidence to `dist/observability/api_probe.json`. Publication is gated by `scripts/verify-release.ps1`, which now requires passing functional smoke, security baseline summary, and observability probe evidence in addition to artifact/signature checks.

## Secrets

The workflow exposes these repository secrets to jobs that declare them:

- `TRADEGOV_API_KEY`
- `FEDREG_API_KEY`

Define them under GitHub repository **Secrets and variables -> Actions**.

## Notes

- The CPU job includes the packaging smoke gate; `docs/ci.md` should be updated if that script or its position in the workflow changes.
- The coverage floor is enforced from `pyproject.toml` via Coverage.py (`fail_under = 75`), keeping the CI gate aligned with the repo's `codecov.yml` target.
- API route latency/failure budgets are defined in `perf/config/api_route_budgets.yml` and explained in `docs/ops/api_latency_budgets.md`.
- Local rerun of the CI security baseline:
  - `pwsh scripts/security-baseline.ps1 -Python py -RequirementsLock requirements-win-lock.txt -PipAuditIgnoreFile security/pip_audit_ignore.txt -OutputDir dist/security`
  - outputs: `dist/security/pip_audit.json`, `dist/security/bandit.json`, `dist/security/secret_scan.json`, `dist/security/security_scan_summary.json`
- The GPU and benchmark jobs are non-blocking because both are marked `continue-on-error: true`.

