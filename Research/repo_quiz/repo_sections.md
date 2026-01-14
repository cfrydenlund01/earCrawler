# earCrawler repo map (quiz study sheet)

This document is a categorized snapshot of the repository meant to support the quiz in `Research/repo_quiz/`.

## Purpose (leveled)

### Level 1 (one sentence)
`earCrawler` is the crawling + knowledge-graph component that powers the EAR-QA system.

### Level 2 (capabilities)
- Provides lightweight clients for Trade.gov and the Federal Register.
- Runs a deterministic ingestion/corpus pipeline (fixtures-first; live mode is opt-in).
- Builds and validates RDF graphs (SHACL) and loads them into Apache Jena TDB2.
- Serves/query the KG via a local Fuseki deployment and a small FastAPI facade.
- Supports evaluation datasets and (optional) RAG / model benchmarking workflows.

### Level 3 (operational features)
- Role-based access control (RBAC) enforced in the CLI and API workflows.
- Tamper-evident audit ledger and privacy/telemetry redaction.
- Windows-first packaging (wheel, PyInstaller exe, offline bundles, installer).
- Deterministic exports, manifests, checksums, and CI gates for drift/regression.

Primary docs: `README.md`, `RUNBOOK.md`, `CHANGELOG.md`.

## Architecture (high level)

Common “offline deterministic” path:

1. **Crawl / build corpora** (fixtures by default)
2. **Transform & emit RDF** (TTL/NQ)
3. **Validate** (schema/provenance/SHACL/integrity gates)
4. **Load into TDB2** (Jena tooling)
5. **Serve/query via Fuseki** (and optionally the FastAPI facade)
6. **Evaluate** using curated JSONL datasets under `eval/`

## Key algorithms & invariants (selected)

- **Determinism by default**: many workflows are fixture-first; live fetches require explicit `--live` (see CLI help and `RUNBOOK.md`).
- **Content hashing / stable IDs**: KG IRIs and snapshots rely on deterministic hashing (e.g., paragraph IRIs derived from SHA256 digests).
- **Schema/shape enforcement**: graph/schema version pinning plus SHACL shapes gate exports and loads (e.g., `earCrawler/kg/shapes.ttl`, `earCrawler/kg/shapes_prov.ttl`, and `earCrawler.kg.ontology.KG_SCHEMA_VERSION`).
- **Access control**: commands are allowlisted by role (policy file + decorators); API has allowlisted SPARQL templates and request budgets.
- **Privacy-by-design telemetry**: telemetry is opt-in; redaction rules strip secrets/paths/tokens before writing or uploading.

## Code layout (major areas)

### Python packages
- `earCrawler/`: primary library + CLI (`earCrawler.cli`) + subsystems.
- `api_clients/`: Trade.gov / Federal Register / API clients.
- `service/`: FastAPI facade and OpenAPI contracts/templates.
- `perf/`: performance harness and budgets.

### Notable modules
- CLI entry: `earCrawler/cli/__main__.py` (console script `earctl` via `pyproject.toml`).
- Policy/RBAC: `security/policy.yml`, `earCrawler/security/policy.py`, `earCrawler/security/identity.py`.
- KG: `earCrawler/kg/` (emitters, loader, integrity, Fuseki helpers, SPARQL client).
- Telemetry: `earCrawler/telemetry/` + redaction in `docs/privacy/`.
- Audit: `earCrawler/audit/` ledger and verification.
- Evaluation: `eval/manifest.json`, `eval/schema.json`, `eval/validate_datasets.py`, `earCrawler/eval/run_eval.py`.

## Commands (selected)

Primary entrypoint:
- `earctl` (or `py -m earCrawler.cli ...`) - see `README.md` for basics.

Common workflows:
- `earctl diagnose`
- `earctl crawl ...`
- `earctl corpus build|validate|snapshot`
- `earctl kg-load`, `earctl kg-serve`, `earctl kg-query`
- `earctl api start|stop|smoke`
- `earctl integrity check <ttl>`
- `earctl telemetry enable|disable|purge`
- `earctl eval verify-evidence`
- `earctl eval run-rag`
- `earctl eval fr-coverage`
- `earctl eval check-grounding`

Eval scoring notes:
- `earctl eval run-rag` uses semantic answer scoring by default (`--answer-score-mode semantic`) so `accuracy` reflects meaning instead of exact string equality; for binary true/false QA, use `label_accuracy` as the primary metric.

Release packaging (PowerShell):
- `pwsh scripts/build-wheel.ps1`
- `pwsh scripts/build-exe.ps1`
- `pwsh scripts/make-installer.ps1`

## Research artifacts

Tracked research docs are indexed by:
- Script: `scripts/research_index.py`
- Outputs: `Research/index.json`, `Research/knowledge_cache.json`
- Decision log: `Research/decision_log.md`

## Files & directories (selected)

- `requirements*.txt`: dependency sets / lockfiles.
- `tools/`: toolchain downloads (notably `tools/jena`).
- `db/`: TDB2 store (local).
- `kg/`: KG assets, reports, assemblers, snapshots, manifests.
- `eval/`: evaluation datasets and schema/manifest.
- `tests/`: pytest suite + fixtures/cassettes (offline determinism).
