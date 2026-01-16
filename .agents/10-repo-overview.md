# Repo Overview

`earCrawler` is a Python 3.11+ project providing a deterministic ingestion + KG pipeline, a Click-based CLI, and a small FastAPI facade.

## Key directories
- `earCrawler/`: primary Python package (CLI, pipelines, KG, validation, service helpers).
- `api_clients/`: Trade.gov + Federal Register clients and shared HTTP caching.
- `cli/`: lightweight KG emit/validate helpers used by CI smoke steps (`python -m cli.kg_emit`, `kg-validate`).
- `service/`: FastAPI app + OpenAPI artifacts and deployment helpers.
- `scripts/`: PowerShell + Python automation (CI gates, release tooling, monitoring, research helpers).
- `kg/`: knowledge-graph artifacts, scripts, and baseline/determinism tooling.
- `eval/`: evaluation datasets + validation scripts.
- `tests/`: unit/integration tests.

## “Local-only” / generated paths
Common runtime/build outputs are gitignored (examples: `.venv/`, `.cache/`, `build/`, `dist/`, `kg/reports/`, local Fuseki/db folders). Treat these as non-source unless explicitly required by a pipeline step.

## Research artifacts
Only a small subset under `Research/` is versioned (decision log + repo quiz). Most DOCX/caches under `Research/` are intentionally local/ignored.

