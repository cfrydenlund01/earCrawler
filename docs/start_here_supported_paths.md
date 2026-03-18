# Start Here: Supported Developer Paths

Prepared: March 10, 2026

Use this page first when you are new to the repo. It points to the supported
entrypoints and flags commonly confused legacy surfaces.

## Supported first steps

1. Build corpus inputs:
   - `py -m earCrawler.cli corpus --help`
2. Emit and validate KG artifacts from corpus outputs:
   - `py -m earCrawler.cli kg emit --help`
   - `py -m earCrawler.cli kg validate --help`
3. Run the supported API surface:
   - `py -m earCrawler.cli api start`
   - or `py -m uvicorn service.api_server.server:app --host 127.0.0.1 --port 9001`
4. Validate supported runtime behavior:
   - `py -m earCrawler.cli api smoke`
   - `py -m pytest -q`

## Canonical docs

- Repository map and support-status labels: `docs/repository_status_index.md`
- Data artifact truth model: `docs/data_artifact_inventory.md`
- Product and capability boundary: `README.md`
- Operator flow and lifecycle actions: `RUNBOOK.md`
- Deployed Windows host lifecycle and baseline contract: `docs/ops/windows_single_host_operator.md`
- API contract and route status: `docs/api/readme.md`
- Runtime vs research boundary: `docs/runtime_research_boundary.md`

## Quarantined or legacy surfaces

Do not treat these as supported runtime entrypoints:

- top-level `cli/` module wrappers such as `python -m cli.kg_emit` or
  `python -m cli.kg_validate`; use `py -m earCrawler.cli kg ...` instead
- `earCrawler.service.sparql_service`
- `earCrawler.service.legacy.kg_service`
- `earCrawler.ingestion.ingest` (legacy placeholder ingestion; gated by
  `EARCRAWLER_ENABLE_LEGACY_INGESTION=1`)
- KG-backed runtime features before `docs/kg_quarantine_exit_gate.md` is passed
  and recorded
