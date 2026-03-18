# Repository Status Index

Prepared: March 18, 2026

Use this page as the repository map for support status. It labels the major
top-level surfaces so contributors can tell what is part of the supported
default path versus what is optional, quarantined, generated, or archival.

Status labels:

- `Supported`: part of the default contributor and operator path.
- `Optional`: real and maintained, but requires explicit enablement or is not
  part of the baseline runtime.
- `Quarantined`: kept in-tree for local validation, research, or future
  graduation work; not part of the supported default path.
- `Generated`: build output, local state, or environment-specific artifacts.
- `Archival`: historical records kept for reference, not active source of truth.

## Top-level map

| Path | Status | Notes |
| --- | --- | --- |
| `README.md` | Supported | Primary product/runtime orientation and capability boundary. |
| `RUNBOOK.md` | Supported | Supported operator and release workflow. |
| `docs/` | Supported | Active architecture, operations, API, and support-boundary documentation. |
| `docs/Archive/` | Archival | Historical review passes and execution plans; not current source of truth. |
| `earCrawler/` | Supported | Main Python package for corpus, KG, RAG, telemetry, security, and CLI registration. |
| `service/` | Supported | Supported FastAPI runtime, OpenAPI source, and Windows service docs. |
| `api_clients/` | Supported | Maintained client wrappers aligned to the supported API boundary. |
| `config/` | Supported | Example runtime, policy, and training contract inputs used by active workflows. |
| `security/` | Supported | Policy and security configuration for supported CLI/runtime controls. |
| `tests/` | Supported | Automated validation for supported, optional, and quarantine-boundary behavior. |
| `.github/` | Supported | CI and release workflows for the supported baseline. |
| `scripts/` | Supported | Automation used by supported build, smoke, packaging, and operator workflows. Some individual scripts remain quarantined; check their paired docs. |
| `perf/` | Supported | Perf budgets and fixture-backed perf tooling for the supported baseline, with explicit optional/quarantined coverage where documented. |
| `eval/` | Supported | Held-out evaluation datasets, schema, and manifests for regression and evidence work. |
| `kg/` | Supported | KG emit/validation assets and reports used by the supported offline evidence path. Runtime KG serving and expansion remain quarantined capabilities. |
| `data/faiss/` | Supported | Authoritative retrieval corpus and FAISS metadata for the current supported training/retrieval contract. |
| `data/experimental/` | Quarantined | Small scratch or derivative data artifacts kept out of the authoritative runtime/training path. |
| `data/` | Supported | Mixed data root; use labeled subpaths and contracts, not filename guesses. `data/faiss/` is authoritative for the current retrieval corpus contract. |
| `db/` | Optional | Local graph/database assets used by validation or local workflows; not by themselves the supported deployment contract. |
| `snapshots/` | Optional | Offline snapshot inputs and manifests used by deterministic corpus/training workflows when present locally. |
| `packaging/` | Supported | Release packaging configuration for supported Windows artifacts. |
| `installer/` | Supported | Windows installer definitions used in release engineering. |
| `tools/` | Optional | Local tool dependencies such as Jena downloads; useful for local validation, not primary source. |
| `cli/` | Quarantined | Legacy top-level CLI helpers retained for compatibility; authoritative CLI surface is `earCrawler.cli`. |
| `Research/` | Quarantined | Research notes and decision logs; informative but not runtime/operator contract. |
| `demo/` | Quarantined | Demo-oriented assets, not the supported production baseline. |
| `bundle/` | Optional | Offline/export bundle helpers used by specific packaging workflows. |
| `canary/` | Optional | Canary configuration used for validation and monitoring workflows. |
| `monitor/`, `monitor.ps1` | Optional | Monitoring helpers for deployment validation. |
| `build/`, `dist/`, `run/`, `runs/`, `earCrawler.egg-info/` | Generated | Local build products, run artifacts, reports, and packaging outputs. |
| `.venv*`, `.pytest_*`, `.cache/`, `.vscode/` | Generated | Local environment and editor/test state; do not treat as maintained source. |
| `fuseki_db/` | Generated | Local Fuseki dataset state for development or validation. |

## Important surface clarifications

| Surface | Status | Notes |
| --- | --- | --- |
| `earCrawler.cli` / `earctl` | Supported | Authoritative CLI entrypoint. |
| `service.api_server` | Supported | Authoritative API runtime surface. |
| `/v1/search` and KG-backed runtime behavior | Quarantined | Disabled or excluded from the default supported contract unless explicitly enabled and documented otherwise. |
| `/v1/rag/answer`, hybrid retrieval, local-adapter runtime | Optional | Real capabilities with explicit gates; not baseline defaults. |
| `scripts/training/` and `docs/model_training_*` | Optional | Maintained phase-gated workflow for evidence generation, not the supported operator runtime by itself. |
| `earCrawler.service.sparql_service`, `earCrawler.service.legacy.kg_service`, `earCrawler.ingestion.ingest` | Quarantined | Legacy/quarantined code paths; do not treat as current supported entrypoints. |

## Default contributor path

If you are new to the repo, start here:

1. `docs/start_here_supported_paths.md`
2. `README.md`
3. `RUNBOOK.md`
4. `docs/api/readme.md`
5. `docs/runtime_research_boundary.md`

For day-to-day changes, treat `earCrawler/`, `service/`, `scripts/`,
`config/`, `tests/`, and the active docs outside `docs/Archive/` as the default
working set unless a task explicitly targets an optional or quarantined surface.
