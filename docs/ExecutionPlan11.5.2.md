# Execution Plan 11.5.2

Source guidance:

- `docs/ExecutionPlan11.5.md` as structure/template only
- `docs/ExecutionPlan11.5_log.md`
- `scripts/eval/run_local_adapter_benchmark.py`
- `service/api_server/routers/rag.py`
- `service/api_server/rag_service.py`
- `service/api_server/config.py`
- `service/api_server/limits.py`
- `earCrawler/rag/local_adapter_runtime.py`
- `docs/local_adapter_release_evidence.md`

Prepared: April 1, 2026

## Purpose

This document is a focused debug plan for the specific failures blocking a clean
pass of Step `7.3` for the current local-adapter candidate.

The finish line is not "more investigation." The finish line is:

1. every Step `7.3` run emits verbose, durable server and benchmark evidence,
2. the warmup query no longer alternates between `422`, `500`, connection reset,
   or process death,
3. the retrieval-only control no longer fails due to benchmark-session side
   effects such as process-local rate limiting,
4. Step `7.3.a` passes cleanly,
5. Step `7.3.b` passes cleanly,
6. the exact commands, outcomes, and artifact paths are recorded in
   `docs/ExecutionPlan11.5.2_log.md`.

## Target Under Test

Working target for this debug plan:

- `run_id`: `qwen25-7b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1`
- `run_dir`: `dist/training/qwen25-7b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1`
- benchmark API base URL: `http://127.0.0.1:9001`
- benchmark manifest: `eval/manifest.json`
- runtime smoke precondition: `kg/reports/local-adapter-smoke.json`

If a later candidate run replaces this one, update this section first before
executing later phases.

## Model Guidance

Working rule:

- Use `GPT-5.3-Codex` for runtime debugging, scripts, tests, logging changes,
  and benchmark/workflow repair.
- Use `GPT-5.4` only if a support-boundary decision is required for benchmark
  identity, rate limiting, or operator-visible runtime behavior.
- Use `GPT-5.4-Mini` only for narrow execution-log maintenance.
- Use `medium` when reproducing one failure mode with a known artifact target.
- Use `high` when fixing one identified failure class across API/runtime/script
  boundaries.

## Non-Negotiable Strengths To Preserve

- Do not weaken the `7.3` gate by hiding or ignoring warmup, schema, transport,
  or retrieval-only failures.
- Do not silently broaden the supported product claim or relax the single-host
  runtime boundary.
- Do not silently disable strict-output validation for benchmark scoring.
- Do not turn off rate limiting globally as a shortcut; if benchmark traffic
  requires an explicit carve-out, make it narrow, test-covered, and documented.
- Preserve the requirement that the benchmark exercises the supported API route,
  not direct model calls.

## Execution Rules

- Every step in this plan is single-purpose. Do not combine multiple failure
  classes in one debugging step.
- Verbose logging is mandatory until both `7.3.a` and `7.3.b` pass.
- Every API start used for `7.3` debugging must capture stdout and stderr to
  durable files under `kg/reports/`.
- Every benchmark run must write either `benchmark_summary.json` or
  `benchmark_failure.json` under `dist/benchmarks/<benchmark_run_id>/`.
- After every step, append one terse result line to
  `docs/ExecutionPlan11.5.2_log.md` with date/time, exact command or prompt
  scope, pass/fail, and artifact path.
- If a step fails, stop and resolve that exact blocker before moving to the next
  step.
- Do not resume the original `ExecutionPlan11.5.md` Step `7.3.c` or later until
  this plan has closed the `7.3.a` and `7.3.b` gate.

## Phase 0 - Lock The Debug Workspace

Goal: create one dedicated debug ledger and one repeatable verbose runtime
session for Step `7.3`.

### Step 0.1 - Create The ExecutionPlan11.5.2 Tracking Log
Explanation: all debug work for this plan must land in one ledger, not in
scattered comments or partial artifact checks.

Type: `Prompt`

Model: `GPT-5.4-Mini`
Reasoning: `medium`

Prompt:
```text
Use docs/ExecutionPlan11.5.2_log.md as the execution log for this debug plan. Keep it terse and operational: date/time, step id, command or prompt scope, pass/fail, artifact path, and next blocker. Do not create a new review. If the file already exists, preserve prior entries and append only the current run state.
```

### Step 0.2 - Start A Single Verbose API Session For Debug Runs
Explanation: all `7.3` debugging must happen against one explicitly managed API
session with durable stdout/stderr capture.

Type: `Code`

```powershell
$env:EARCTL_PYTHON='.venv\Scripts\python.exe'
$env:EARCRAWLER_API_ENABLE_RAG='1'
$env:EARCRAWLER_API_TIMEOUT='300'
$env:EARCRAWLER_ALLOW_WEAK_EVIDENCE='1'
$env:EARCRAWLER_LOCAL_LLM_MAX_NEW_TOKENS='64'
$env:EARCRAWLER_LOCAL_LLM_MAX_TIME_SECONDS='20'
$env:LLM_PROVIDER='local_adapter'
$env:EARCRAWLER_ENABLE_LOCAL_LLM='1'
$env:EARCRAWLER_LOCAL_LLM_BASE_MODEL='Qwen/Qwen2.5-7B-Instruct'
$env:EARCRAWLER_LOCAL_LLM_ADAPTER_DIR='dist/training/qwen25-7b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1/adapter'
$env:EARCRAWLER_LOCAL_LLM_MODEL_ID='qwen25-7b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1'
pwsh scripts/api-stop.ps1
Remove-Item kg/reports/api-debug.out.log,kg/reports/api-debug.err.log -ErrorAction SilentlyContinue
Start-Process -FilePath '.venv\Scripts\python.exe' `
  -ArgumentList '-m','uvicorn','service.api_server.server:app','--host','127.0.0.1','--port','9001' `
  -PassThru `
  -WindowStyle Hidden `
  -RedirectStandardOutput 'kg/reports/api-debug.out.log' `
  -RedirectStandardError 'kg/reports/api-debug.err.log'
curl.exe -s -o NUL -w '%{http_code}' http://127.0.0.1:9001/health
```

Expected evidence:

- `kg/reports/api-debug.out.log`
- `kg/reports/api-debug.err.log`
- healthy `200` response from `/health`

Phase gate:

- one serving API process exists
- stdout/stderr logs are present on disk

Contingency if gate fails:

- stop and fix process ownership, startup race, or port binding before any
  benchmark rerun

## Phase 1 - Reproduce One Warmup Failure Cleanly

Goal: capture the warmup query outcome and its server-side evidence before
scoring starts.

### Step 1.1 - Replay The Warmup Query By Itself
Explanation: isolate the exact warmup request the benchmark uses before any
benchmark loop or retrieval-only control muddies the evidence.

Type: `Code`

```powershell
curl.exe -s `
  -o dist/benchmarks/_warmup_probe_response.json `
  -w '%{http_code}' `
  -H 'Content-Type: application/json' `
  -d '{"query":"Do laptops to France need a license?","top_k":3,"generate":true}' `
  http://127.0.0.1:9001/v1/rag/answer
```

Expected evidence:

- `dist/benchmarks/_warmup_probe_response.json`
- updated `kg/reports/api-debug.err.log`

Phase gate:

- one concrete warmup outcome is captured as exactly one of:
  - `200`
  - `422`
  - `500`
  - transport failure / dead API

Contingency if gate fails:

- if no durable artifact is written, repair logging first and repeat Step `1.1`

### Step 1.2 - Record The Warmup Failure Class And Exact Cause
Explanation: do not fix anything yet; classify the warmup result from the
captured response and server logs.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `medium`

Prompt:
```text
Use only the current warmup probe response, kg/reports/api-debug.err.log, kg/reports/api-debug.out.log, and the current benchmark failure artifacts. Classify the warmup failure as exactly one of: invalid_json_422, app_error_500, process_exit_transport_failure, startup_race, or other. Name the concrete evidence for that classification in one short paragraph and identify the single code path that should be debugged next. Do not propose a broad rewrite.
```

Phase gate:

- one named warmup failure class exists with one primary code path to inspect

Contingency if gate fails:

- rerun only Step `1.1` until the failure class is unambiguous

## Phase 2 - Remove Warmup Blockers One At A Time

Goal: eliminate warmup instability before touching the scored benchmark loop.

### Step 2.1 - Debug The `422 invalid_json` Path Until Warmup Stops Returning Truncated JSON
Explanation: if Step `1.2` classified the warmup failure as `invalid_json_422`,
fix only the local-adapter structured-output failure path and rerun the same
warmup query until it no longer returns invalid JSON.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use the current warmup probe response, kg/reports/api-debug logs, earCrawler/rag/local_adapter_runtime.py, earCrawler/rag/llm_runtime.py, service/api_server/routers/rag.py, and any directly affected tests as governing context. Fix only the structured-output failure causing the warmup query to return 422 invalid_json or truncated JSON. Keep scope narrow, preserve strict-output validation, add focused tests, and rerun only the warmup query plus the narrowest relevant tests until the warmup no longer returns invalid_json.
```

### Step 2.2 - Debug The `500` Warmup Path Until The Warmup Query No Longer Returns Server Errors
Explanation: if Step `1.2` classified the warmup failure as `app_error_500`,
fix only the server-side exception path behind that warmup request and rerun the
same warmup query until it no longer returns `500`.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use the current warmup probe response, kg/reports/api-debug logs, service/api_server/routers/rag.py, service/api_server/rag_service.py, earCrawler/rag/local_adapter_runtime.py, and any directly affected tests as governing context. Fix only the application-level failure causing the warmup query to return HTTP 500. Keep the API contract intact, add focused regression coverage, and rerun only the warmup query plus the narrowest relevant tests until the warmup no longer returns 500.
```

### Step 2.3 - Debug The Process-Exit / Connection-Reset Path Until The API Survives Repeated Warmup Calls
Explanation: if Step `1.2` classified the warmup failure as
`process_exit_transport_failure` or `startup_race`, fix only the API/session
stability problem and rerun repeated warmup calls until the API remains healthy.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use the current benchmark failure artifacts, kg/reports/api-debug logs, scripts/api-start.ps1, scripts/api-stop.ps1, earCrawler/rag/local_adapter_runtime.py, service/api_server/server.py, and any directly affected tests as governing context. Fix only the process-stability or startup-race failure causing warmup requests to end in connection_reset, connection_refused, or dead /health probes. Keep the single-host support boundary intact, add focused regression coverage where possible, and rerun repeated warmup queries until the API survives at least three consecutive warmup calls.
```

Phase gate:

- the isolated warmup query succeeds without `422`, `500`, connection reset,
  connection refused, or API death

Contingency if gate fails:

- repeat only the matching Step `2.x` for the active failure class

## Phase 3 - Remove Retrieval-Only Control Side Effects

Goal: make the retrieval-only control honest and stable after the local-adapter
pass.

### Step 3.1 - Run Retrieval-Only Control Alone On The Same API Session
Explanation: prove whether the retrieval-only condition is intrinsically stable
before rerunning `7.3.b`.

Type: `Code`

```powershell
.venv\Scripts\python.exe -m scripts.eval.run_local_adapter_benchmark `
  --run-dir dist/training/qwen25-7b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1 `
  --manifest eval/manifest.json `
  --dataset-id ear_compliance.v2 `
  --run-id benchmark_qwen25-7b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1_retrieval_only_probe `
  --smoke-report kg/reports/local-adapter-smoke.json `
  --timeout-seconds 120 `
  --max-consecutive-transport-failures 3 `
  --overwrite
```

Expected evidence:

- `dist/benchmarks/benchmark_qwen25-7b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1_retrieval_only_probe/benchmark_summary.json`
  or `benchmark_failure.json`

### Step 3.2 - Debug Retrieval-Only `429` Or Session-Contamination Failures Until Control Passes Cleanly
Explanation: if the retrieval-only probe or the full benchmark still fails due
to `429` or benchmark-session contamination, fix only that identity/rate-limit
interaction and rerun the control until it is clean.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use the current retrieval-only benchmark artifacts, service/api_server/config.py, service/api_server/limits.py, the benchmark runner, and any directly affected tests as governing context. Fix only the retrieval-only control failure mode caused by process-local rate limiting or benchmark-session contamination. Do not silently weaken production defaults. If a benchmark-only identity or explicit local carve-out is required, make it narrow, explicit, test-covered, and documented. Rerun only the retrieval-only control and the narrowest relevant tests until the control passes cleanly.
```

Phase gate:

- retrieval-only control no longer fails due to `429`, startup race, or prior
  local-adapter session side effects

Contingency if gate fails:

- do not rerun `7.3.a`/`7.3.b` again until the retrieval-only control is clean

## Phase 4 - Re-Run The Gate Cleanly

Goal: pass the actual `7.3.a` and `7.3.b` commands under the now-stable debug
session.

### Step 4.1 - Re-Run Step `7.3.a` Until The Preflight Passes Cleanly
Explanation: rerun the exact preflight command only after Phase 2 and Phase 3
gates are closed.

Type: `Code`

```powershell
.venv\Scripts\python.exe -m scripts.eval.run_local_adapter_benchmark `
  --run-dir dist/training/qwen25-7b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1 `
  --manifest eval/manifest.json `
  --dataset-id ear_compliance.v2 `
  --max-items 5 `
  --run-id benchmark_qwen25-7b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1_preflight `
  --smoke-report kg/reports/local-adapter-smoke.json `
  --timeout-seconds 120 `
  --max-consecutive-transport-failures 3 `
  --overwrite
```

Phase gate:

- `benchmark_summary.json` exists
- no warmup failure
- `local_adapter.transport_failure_rate == 0`
- no repeated `status_code=0`

Contingency if gate fails:

- return only to the upstream phase matching the observed failure class

### Step 4.2 - Re-Run Step `7.3.b` Until The Full `ear_compliance.v2` Benchmark Passes Cleanly
Explanation: rerun the exact full benchmark command only after `7.3.a` passes
cleanly in the current session.

Type: `Code`

```powershell
.venv\Scripts\python.exe -m scripts.eval.run_local_adapter_benchmark `
  --run-dir dist/training/qwen25-7b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1 `
  --manifest eval/manifest.json `
  --dataset-id ear_compliance.v2 `
  --run-id benchmark_qwen25-7b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1_ear_compliance_v2 `
  --smoke-report kg/reports/local-adapter-smoke.json `
  --timeout-seconds 120 `
  --max-consecutive-transport-failures 3 `
  --overwrite
```

Phase gate:

- `benchmark_summary.json` exists
- no warmup failure
- no `local_adapter` transport failures
- no retrieval-only `429` contamination

Contingency if gate fails:

- return only to Phase 2 or Phase 3 depending on whether the failure is warmup
  instability or retrieval-only contamination

## Completion Condition

- `docs/ExecutionPlan11.5.2_log.md` contains the full step ledger
- `7.3.a` passes cleanly
- `7.3.b` passes cleanly
- the original `docs/ExecutionPlan11.5_log.md` can then be refreshed from the
  final passing artifacts instead of partial failure snapshots
