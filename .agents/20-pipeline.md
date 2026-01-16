# Pipeline Map

## Main entrypoints
- CLI (primary): `earctl` (console script) -> `earCrawler.cli:main` (also `py -m earCrawler.cli`)
- KG smoke tools: `kg-validate` (console script) -> `cli.kg_validate:main`; emit via `python -m cli.kg_emit`
- API facade: driven via CLI (`py -m earCrawler.cli api start|stop|smoke`) and the `service/api_server` FastAPI app

## CI / quality (see `.github/workflows/ci.yml`)
- Format/lint: `black --check .` and `flake8 .`
- Tests: `pytest -q` (default marker excludes network)
- Determinism + KG gates (examples):
  - `pwsh scripts/ci-corpus-determinism.ps1`
  - `python -m earCrawler.pipelines.build_ttl`
  - `python -m earCrawler.validation.validate_shapes`
  - `scripts/rebuild-compare.ps1`
  - `python eval/validate_datasets.py`
  - `py -m earCrawler.cli eval-benchmark --dataset-id <id> ...`

## Release (see `.github/workflows/release.yml`)
- Builds wheel/exe/installer via `scripts/build-wheel.ps1`, `scripts/build-exe.ps1`, `scripts/make-installer.ps1` and signing/SBOM scripts.

## Monitoring (see `.github/workflows/monitor.yml`)
- Scheduled job runs:
  - `scripts/monitor-deltas.ps1`
  - `scripts/refresh-cassettes.ps1`
  - `scripts/auto-pr.ps1`

## Research helpers (optional)
- Workflow and context rules: `.agents/70-research.md`
- Index/caches: `py scripts/research_index.py` (writes `Research/index.json`, `Research/knowledge_cache.json`)
- Decision log: `Research/decision_log.md`
