# Maintainer Start Here

Prepared: March 25, 2026

Use this page first when you are taking over the repository or returning after a
long gap. It is the shortest authoritative path through the supported runtime,
repo structure, operator docs, and release-validation flow.

## Authoritative Maintainer Path

Read these in order:

1. `README.md`
   - product boundary, supported runtime entrypoints, capability states
2. `docs/repository_status_index.md`
   - which top-level paths are supported, optional, quarantined, generated, or archival
3. `docs/data_artifact_inventory.md`
   - which runtime/eval/training artifacts are source of truth versus generated evidence
4. `docs/single_host_runtime_state_boundary.md`
   - the explicit single-host runtime-state contract behind `/health`
5. `docs/api/readme.md`
   - supported API surface and route-level optional/quarantine status
6. `docs/ops/windows_fuseki_operator.md` and `docs/ops/windows_single_host_operator.md`
   - authoritative deployed-host operator path
7. `docs/ops/release_process.md`
   - the normal release-validation and promotion evidence path

`RUNBOOK.md` remains the source-checkout and release-engineering companion once
you already know the boundaries above.

## Supported Runtime Entrypoints

Treat these as the supported runtime entrypoints:

- `earctl` / `py -m earCrawler.cli ...`
- `py -m uvicorn service.api_server.server:app --host 127.0.0.1 --port 9001`
- the installed-wheel Windows service path documented in `docs/ops/windows_single_host_operator.md`

Do not treat these as supported runtime entrypoints:

- top-level `cli/` compatibility wrappers
- `earCrawler.service.sparql_service`
- `earCrawler.service.legacy.kg_service`
- `earCrawler.ingestion.ingest`
- repo-local `scripts/api-*.ps1` helpers as the authoritative deployed-host path

## Main Module Boundaries

| Path | Boundary |
| --- | --- |
| `earCrawler/` | Main application package for CLI registration, corpus, KG, RAG, security, telemetry, and supporting domain logic. |
| `service/api_server/` | Supported FastAPI runtime, runtime contract, middleware, health checks, and route wiring. |
| `api_clients/` | Maintained wrappers for upstream dependencies and the EarCrawler API client. |
| `scripts/` | Build, smoke, packaging, security, release, and operator automation. |
| `tests/` | Validation for supported, optional, and quarantine-boundary behavior. |
| `docs/ops/` | Authoritative deployed-host lifecycle, front-door, backup/restore, and release-operator docs. |

If a task touches a surface outside that set, verify its support status in
`docs/repository_status_index.md` before treating it as active source of truth.

## Authored Source Versus Generated State

Use this rule first:

- authored source lives under tracked code/docs/config/test paths and the
  canonical contracts they point to
- generated state lives under `build/`, `dist/`, `run/`, `runs/`, `.venv*`,
  `.pytest_*`, and other environment-specific outputs

When in doubt:

- use `docs/repository_status_index.md` for path-level status
- use `docs/data_artifact_inventory.md` for artifact-level truth
- use `pwsh scripts/workspace-state.ps1 -Mode report` before trusting an unfamiliar path

## Capability Boundary

- `Supported`: `earctl`, `service.api_server`, `/health`, `/v1/entities/{entity_id}`, `/v1/lineage/{entity_id}`, `/v1/sparql`, `/v1/rag/query`
- `Optional`: `/v1/rag/answer`, hybrid retrieval, local-adapter serving
- `Quarantined`: `/v1/search`, KG-backed runtime expansion, legacy service surfaces kept only for controlled local validation or historical compatibility
- `Legacy`: compatibility-only or historical module surfaces that are not current supported entrypoints
- `Generated`: build, release, and local environment outputs such as `dist/`, `build/`, `run/`, `runs/`, `.venv*`
- `Archival`: historical review and plan records under `docs/Archive/`
- `Proposal-only`: planning or research surfaces such as `Research/` and `docs/proposal/`

Workspace-only ghost residue is not a support category. Treat it as
unsupported local leftover state and verify it with
`pwsh scripts/workspace-state.ps1`.

The machine-readable source of truth for runtime capability state is
`service/docs/capability_registry.json`, published at
`docs/api/capability_registry.json`.

## Operator Docs

For deployed hosts, use these docs as authoritative:

- `docs/ops/windows_fuseki_operator.md`
- `docs/ops/windows_single_host_operator.md`
- `docs/ops/external_auth_front_door.md` only when deployment goes beyond loopback/single-host access

## Normal Release-Validation Path

The normal release-validation path is:

1. `scripts/release-evidence-preflight.ps1`
2. `scripts/installed-runtime-smoke.ps1`
3. `scripts/api-smoke.ps1`
4. `scripts/optional-runtime-smoke.ps1`
5. `scripts/verify-release.ps1`

Use `docs/ops/release_process.md` for the exact commands, retained evidence,
and promotion-stage expectations.
