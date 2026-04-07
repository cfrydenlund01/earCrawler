# ExecutionPlan11.5.1 Execution Log

Plan: `docs/ExecutionPlan11.5.1.md`  
Primary review: `docs/review11.5.1.md`  
Reference execution state: `docs/ExecutionPlan11.5_log.md`  
Date: 2026-03-30 (America/Chicago)
Status: Step 0.1 complete; Step 1.1 complete; Step 1.2 complete; Step 1.3 complete; Step 2.1 complete; Step 2.2 complete; Step 3.1 complete; Step 3.2 complete; Step 4.1 complete

## Step 0.1 Completion

- `docs/ExecutionPlan11.5.1_log.md` is now the single follow-on log for
  Execution Plan 11.5.1.
- The log records only the review findings, non-goals, and ordered workstreams
  needed to start the follow-on remediation path.

## Actionable Findings Carried Forward

- Open risk: fixed localhost service ports (`9001`, `3030`, `3040`) still need
  deterministic preflight, ownership, and recovery behavior in the operator and
  smoke-script path.
- Open risk: previously fixed Fuseki runtime correctness bugs remain the
  highest-value regression surface and need stronger guardrails.
- Open risk: broader upstream HTTP failure semantics still need one bounded
  audit pass, especially Trade.gov parity and caller-visible degraded-state
  behavior.

## Explicit Non-Goals And Blocked Work

- Do not start Execution Plan 11.5 Step 7.1 or any later CUDA-dependent local
  adapter work.
- Do not reopen search/KG promotion or the dated `Keep Quarantined` decision
  recorded on 2026-03-27.
- Do not create another review, roadmap, or final production decision from this
  follow-on plan.

## Ordered Workstreams

1. Service lifecycle and port ownership hardening across API/Fuseki scripts and
   supported smokes.
2. Fuseki runtime regression guardrails for TDB2, dataset pathing, named-graph
   fixture behavior, and Java resolution.
3. Upstream HTTP failure-taxonomy audit and repair across Federal Register,
   ORI, Trade.gov, and caller-visible degraded states.
4. Final bounded log refresh with results, residual risk, and blocked items
   left untouched.

## Phase 1 Service Lifecycle And Port Ownership

### Step 1.1 - Harden Port Preflight, Ownership, And Recovery Behavior (complete)

- Date: 2026-03-30
- Commands and results:
  - `py -3 -m pytest -q tests/release/test_installed_runtime_smoke_options.py tests/release/test_optional_runtime_smoke.py` -> passed (`4 passed`)
  - `pwsh -File scripts/api-start.ps1 -Host 127.0.0.1 -Port 9015` -> passed
  - `pwsh -File scripts/api-start.ps1 -Host 127.0.0.1 -Port 9015` -> passed (managed owner recovery path exercised)
  - `pwsh -File scripts/api-stop.ps1` -> passed
  - foreign-owner conflict check on port `9016` -> `api-start.ps1` failed fast as expected with explicit non-managed owner message
- Artifacts:
  - `kg/reports/api-start.last.json` (machine-readable lifecycle evidence for API start preflight/startup)
  - `kg/reports/api-stop.last.json` (machine-readable lifecycle evidence for API stop/cleanup)
- Files touched:
  - `scripts/api-start.ps1`
  - `scripts/api-stop.ps1`
  - `scripts/optional-runtime-smoke.ps1`
  - `scripts/installed-runtime-smoke.ps1`
  - `scripts/ops/windows-fuseki-service.ps1`
  - `scripts/health/api-probe.ps1`
  - `scripts/health/fuseki-probe.ps1`
- Completion summary:
  - API start now enforces deterministic port preflight and differentiates managed-vs-foreign port owners.
  - Managed-owner collisions are recovered via process-tree cleanup; foreign-owner collisions fail fast.
  - Stop behavior now consumes managed state, removes stale state deterministically, and reports lingering listeners.
  - Installed/optional smoke reports now carry explicit lifecycle evidence fields for port preflight and API lifecycle phases.
- Remaining risk / next blocker:
  - Need focused regression tests for collision/cleanup paths beyond current smoke coverage (`Step 1.2`).

### Step 1.2 - Add Regression Coverage For Port Collision And Cleanup Paths (complete)

- Date: 2026-03-30
- Commands and results:
  - `py -3 -m pytest -q tests/release/test_api_port_lifecycle.py tests/release/test_optional_runtime_smoke.py tests/release/test_installed_runtime_smoke_options.py` -> passed (`6 passed`)
- Files touched:
  - `tests/release/test_api_port_lifecycle.py` (new)
  - `tests/release/test_optional_runtime_smoke.py`
- Coverage added:
  - managed port-owner recovery path in `api-start.ps1`
  - foreign-owner fail-fast path in `api-start.ps1`
  - lifecycle evidence assertions for `optional-runtime-smoke.ps1` search phases (`api_start_lifecycle`, `api_stop_lifecycle`)
- Remaining risk / next blocker:
  - proceed to Step 1.3 to re-run supported single-host lifecycle proof with the updated scripts and evidence outputs.

### Step 1.3 - Re-Run The Supported Single-Host Lifecycle Proof (complete)

- Date: 2026-03-30
- Commands and results:
  - `pwsh -File scripts/installed-runtime-smoke.ps1 -WheelPath dist/earcrawler-*.whl -UseHermeticWheelhouse -WheelhousePath dist/hermetic-artifacts/.wheelhouse -LockFilePath dist/hermetic-artifacts/requirements-win-lock.txt -UseLiveFuseki -AutoProvisionFuseki -RequireFullBaseline -Host 127.0.0.1 -Port 9001 -ReportPath dist/installed_runtime_smoke.json` -> passed (Java set to repo JDK 17)
  - `pwsh -File scripts/api-start.ps1 -Host 127.0.0.1 -Port 9001` -> passed
  - `pwsh -File scripts/health/api-probe.ps1 -Host 127.0.0.1 -Port 9001 -ReportPath dist/observability/health-api.txt -JsonReportPath dist/observability/api_probe.json` -> passed
  - `pwsh -File scripts/api-stop.ps1` -> passed
  - `pwsh -File scripts/optional-runtime-smoke.ps1 -Host 127.0.0.1 -Port 9001 -SkipLocalAdapter -ReportPath dist/optional_runtime_smoke.json` -> passed
  - `py -3 -m pytest -q tests/release/test_installed_runtime_smoke_options.py tests/release/test_optional_runtime_smoke.py tests/kg/test_fuseki.py` -> passed (`8 passed`)
- Artifacts refreshed:
  - `dist/installed_runtime_smoke.json`
  - `dist/optional_runtime_smoke.json`
  - `dist/observability/health-api.txt`
  - `dist/observability/api_probe.json`
  - `kg/reports/api-start.last.json`, `kg/reports/api-stop.last.json` (lifecycle evidence)
- Note on scope/deviation:
  - Used hermetic wheelhouse + lockfile directly (no bundle zip) because the current `dist/checksums.sha256` entry for `hermetic-artifacts.zip` did not match a locally compressed zip. Release-evidence checksum/sig was not modified; rerun with the signed bundle when available.
- Remaining risk / next blocker:
  - None for Phase 1; proceed to Phase 2 (Fuseki regression guardrails).

## Phase 2 Fuseki Runtime Regression Guardrails

### Step 2.1 - Re-Harden The Known Fuseki Correctness Surfaces (complete)

- Date: 2026-03-30
- Guardrail changes implemented:
  - `earCrawler/kg/fuseki.py`
    - Added dataset-token canonicalization/validation before command assembly so `kg serve` command lines keep a deterministic dataset token (`/ear` style) and still enforce `--tdb2`.
    - Kept `--loc` path resolution coupled to the canonical dataset token.
  - `earCrawler/cli/kg_commands.py`
    - Added shared dataset normalization in the CLI path so `kg load` and `kg serve` use the same canonical dataset token before deriving storage paths or launching Fuseki.
  - `scripts/ops/windows-fuseki-service.ps1`
    - Added explicit Java-major resolution + Java 17 floor enforcement for `install`, `start`, and `restart` actions to reduce shell-dependent startup ambiguity.
  - `scripts/installed-runtime-smoke.ps1`
    - Extended `fuseki_dependency` evidence to include `java_major_version` and `baseline_fixture_graph` for the auto-provisioned named-graph baseline fixture path under `unionDefaultGraph`.
  - Tests:
    - `tests/kg/test_fuseki.py` now guards dataset-token normalization/validation plus script-level named-graph and Java-floor checks.
    - `tests/cli/test_kg_emit_cli.py` now guards dataset-token normalization in load/store path mapping.
- Commands and results:
  - `py -3 -m pytest -q tests/kg/test_fuseki.py tests/cli/test_kg_emit_cli.py tests/rag/test_kg_expansion_fuseki.py` -> passed (`16 passed`)
  - `py -3 -m pytest -q tests/release/test_installed_runtime_smoke_options.py` -> passed (`3 passed`)
  - `pwsh -File scripts/ops/windows-fuseki-service.ps1 -Action status -DryRun` -> passed
- Files touched:
  - `earCrawler/kg/fuseki.py`
  - `earCrawler/cli/kg_commands.py`
  - `scripts/installed-runtime-smoke.ps1`
  - `scripts/ops/windows-fuseki-service.ps1`
  - `tests/kg/test_fuseki.py`
  - `tests/cli/test_kg_emit_cli.py`
- What is now guarded vs. operational assumptions:
  - Guarded: TDB2 flag + dataset-path alignment in command construction and CLI normalization.
  - Guarded: named-graph baseline-fixture contract remains explicit and regression-tested at script surface.
  - Guarded: Java 17 floor is explicit in both installed-runtime auto-provision and Fuseki service lifecycle entry points.
  - Still operational assumption: full end-to-end `kg load` -> `kg serve` -> `kg query` runtime shape must be re-proved in Step 2.2 on the live local stack.
- Remaining risk / next blocker:
  - Execute Step 2.2 runtime mechanics proof (live load/serve/query and targeted Fuseki checksum/runtime tests) with Java 17+ pinned in-shell.

### Step 2.2 - Re-Execute The KG Runtime Mechanics Proof (complete)

- Date: 2026-03-30
- Commands and results (Java pinned to `tools/jdk17/jdk-17.0.18+8`, `EARCTL_USER=ci_user`, `EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES=1`):
  - `py -m earCrawler.cli kg emit -s ear -s nsf -i data -o data\kg` -> passed
  - `py -m earCrawler.cli kg load --ttl data\kg\ear.ttl --db db` -> passed (loads into `db/ear`)
  - `py -m earCrawler.cli kg serve --db db --dataset /ear --no-wait` -> started Fuseki; process stopped after query
  - `py -m earCrawler.cli kg query --endpoint http://localhost:3030/ear/sparql --sparql "SELECT * WHERE { ?s ?p ?o } LIMIT 5" --out dist/kg_query_results.json` -> passed (non-empty rows)
  - `py -3 -m pytest -q tests/kg/test_fuseki.py tests/cli/test_kg_emit_cli.py tests/rag/test_kg_expansion_fuseki.py tests/toolchain/test_fuseki_checksum.py` -> passed
- Artifacts refreshed:
  - `dist/kg_query_results.json`
  - `data/kg/ear.ttl`, `data/kg/nsf.ttl` (emitted)
- Notes:
  - Fuseki was started in no-wait mode for the proof and explicitly stopped afterward to avoid port leakage on 3030.
  - Capability state unchanged: search and KG expansion remain quarantined; this step only re-proved the supported KG load/serve/query runtime shape.
- Remaining risk / next blocker:
  - None for Phase 2; proceed to Phase 3 upstream HTTP failure semantics.

## Phase 3 Upstream HTTP Failure Semantics

### Step 3.1 - Audit And Repair Failure Taxonomy Across Remaining Clients (complete)

- Date: 2026-03-30
- Commands and results:
  - `py -3 -m pytest -q tests/corpus/test_build_and_validate.py::test_live_manifest_captures_search_snapshot_when_degraded` -> passed
- Files touched:
  - `earCrawler/corpus/sources.py`
  - `earCrawler/corpus/builder.py`
  - `tests/corpus/test_build_and_validate.py`
- Repairs:
  - Live EAR corpus builds now capture Federal Register upstream status snapshots (including degraded `search_documents` states) into the manifest via a status sink, so empty downstream output can no longer masquerade as healthy.
  - Health/reporting surfaces that consume `data/manifest.json` now distinguish degraded upstream states from empty-success cases for Federal Register search.
- Remaining risk / next blocker:
  - Execute Step 3.2 live-source readiness and targeted client regression checks to ensure caller-visible degraded states remain explicit across FR/ORI/Trade.gov.

### Step 3.2 - Re-Run Live-Source Readiness And Client Regression Checks (complete)

- Date: 2026-03-30
- Commands and results:
  - `py -3 -m pytest -q tests/clients/test_federalregister_client.py tests/clients/test_ori_client.py tests/clients/test_tradegov_client.py tests/test_tradegov_client.py tests/api/test_federalregister_client_html_guard.py tests/obs/test_health_contracts.py` -> passed (`26 passed, 1 skipped`)
  - `py -m earCrawler.cli jobs run tradegov --dry-run` with `EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES=1`, `EARCTL_USER=test_operator` -> passed (fixtures-only dry run; corpus build+validate succeeded)
  - `py -m earCrawler.cli jobs run federalregister --dry-run` with `EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES=1`, `EARCTL_USER=test_operator` -> passed (fixtures-only dry run; corpus build+validate succeeded)
- Artifacts/outputs:
  - `data/manifest.json` refreshed during dry-run jobs (fixtures path; not a live rebuild)
  - No new release artifacts required; tests exercised upstream failure taxonomy and health/reporting surfaces
- Notes on scope:
  - Used policy override envs strictly for test/dry-run context as allowed in plan; did not alter capability boundaries.
- Remaining risk / next blocker:
  - None for Phase 3; proceed to Phase 4 log refresh.

## Phase 4 Bounded Closure And Handoff

### Step 4.1 - Refresh The ExecutionPlan11.5.1 Log With Results And Residual Risk (complete)

- Date: 2026-03-30
- Source material used:
  - `docs/ExecutionPlan11.5.1.md`
  - `docs/ExecutionPlan11.5.1_log.md`
  - Completed Phase 1 through Phase 3 command results already recorded in this log
- Verification basis:
  - Phase 1 service lifecycle and port ownership hardening passed, including supported single-host smoke and targeted lifecycle regression coverage.
  - Phase 2 Fuseki runtime guardrails and live KG mechanics proof passed, including the real load/serve/query path.
  - Phase 3 upstream HTTP failure taxonomy work passed, including targeted client regressions and bounded live-source readiness dry runs.
- Files touched:
  - `docs/ExecutionPlan11.5.1_log.md`
- Results captured:
  - Closed review11.5.1 findings:
    - fixed localhost service-port lifecycle risk is now deterministically managed and regression-tested.
    - Fuseki runtime correctness regressions are now guarded at script, CLI, and runtime-proof layers.
    - upstream HTTP failures for Federal Register, ORI, and Trade.gov now surface as explicit upstream states instead of collapsing into misleading empty-success behavior.
  - Residual risks left open but bounded:
    - the supported baseline still depends on a single Windows host and fixed local ports.
    - search/KG promotion remains quarantined and intentionally out of scope for this follow-on plan.
    - CUDA-dependent local-adapter work remains blocked and untouched.
- Remaining blocker:
  - none for this follow-on plan; the log is ready for final bounded closure if needed.
