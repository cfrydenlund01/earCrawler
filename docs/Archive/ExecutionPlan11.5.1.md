# Execution Plan 11.5.1

Source guidance:

- `docs/review11.5.1.md`
- `docs/ExecutionPlan11.5.md` as structure/template only
- `docs/ExecutionPlan11.5_log.md` for completed state, current blockers, and
  explicit no-go boundaries only
- `docs/search_kg_capability_decision_2026-03-27.md`
- `docs/ops/windows_single_host_operator.md`
- `docs/ops/windows_fuseki_operator.md`
- `docs/runbook_baseline.md`

Prepared: March 30, 2026

## Purpose

This document turns the open, still-actionable issues in
`docs/review11.5.1.md` into one bounded remediation path.

It does not reopen completed decisions from Execution Plan 11.5, and it does
not advance blocked CUDA-dependent training work.

The finish line is:

1. fixed-port service startup and shutdown behavior is deterministic,
2. previously fixed Fuseki runtime correctness bugs are protected by stronger
   regression guards,
3. upstream HTTP failure semantics are explicit across the remaining client and
   caller surfaces, and
4. one follow-on execution log records findings, results, and residual risks.

## Model Guidance

Working rule:

- Use `GPT-5.3-Codex` for scripts, tests, client behavior, and runtime repair.
- Use `GPT-5.4` only when a step changes support-boundary or operator-facing
  decision text.
- Use `GPT-5.4-Mini` for bounded log refreshes, evidence-index alignment, or
  other small documentation maintenance.
- Use `medium` when the step stays inside one subsystem.
- Use `high` when a step spans script plus tests, or client plus caller plus
  health/reporting behavior.
- Keep prompts conservative: one subsystem per step, one verification goal per
  prompt, no repo-wide synthesis prompts.
- Do not use `extra high` anywhere in this plan.

## Non-Negotiable Strengths To Preserve

- Keep the supported product claim narrow: one Windows host, one API instance,
  one local read-only Fuseki dependency.
- Keep `api.search` and `kg.expansion` quarantined unless a later dated
  decision explicitly changes that state.
- Do not start Execution Plan 11.5 Phase 7 or later work from this plan.
- Do not consume CUDA, GPU, or local-adapter candidate context beyond what is
  needed to restate the current blocker.
- Preserve release evidence discipline and existing checksum/signature rules.
- Preserve the explicit Java 17+ requirement for the supported Fuseki
  auto-provision path.
- Do not broaden fixed localhost assumptions into multi-instance or
  conflict-tolerant product claims.

## Execution Rules

- Use `docs/ExecutionPlan11.5.1_log.md` as the only log for this follow-on
  plan.
- Do not reopen completed Execution Plan 11.5 phases unless a regression named
  in `docs/review11.5.1.md` requires the narrowest possible repair.
- Every prompt step must end with updated artifacts, targeted verification, and
  a brief log update.
- If a step touches search/KG runtime scripts, preserve the current quarantine
  boundary and do not create new promotion evidence work.
- If a step discovers that the fix depends on blocked CUDA training work or on
  fresh installed-artifact promotion proof for search/KG, stop, log it as
  blocked, and do not continue into that area.

## Phase 0 - Scope Lock And Tracking

Goal: translate the review into one execution ledger and lock explicit
non-goals before changing code.

### Step 0.1 - Create A Single Tracking Record For ExecutionPlan11.5.1
Explanation: create one follow-on log so the review findings, exclusions, and
later outcomes stay in one place.

Type: `Prompt`

Model: `GPT-5.4-Mini`
Reasoning: `medium`

Prompt:
```text
Use docs/review11.5.1.md, docs/ExecutionPlan11.5.md, and docs/ExecutionPlan11.5_log.md as governing context. Create or refresh docs/ExecutionPlan11.5.1_log.md as the only log for this follow-on plan. Record only:

1. the still-actionable findings from review11.5.1,
2. the explicit non-goals and blocked items that must not be touched,
3. the ordered workstreams this plan will execute next.

Keep the log short and operational. Do not create another review, roadmap, or decision record.
```

Phase gate:

- one log file exists at `docs/ExecutionPlan11.5.1_log.md`
- the log names the active workstreams and the blocked work to avoid

Contingency if gate fails:

- if the log starts drifting into another narrative review, replace it with a
  terse ledger before continuing

## Phase 1 - Service Lifecycle And Port Ownership

Goal: remove ambiguity from fixed-port local service behavior before touching
broader network semantics.

### Step 1.1 - Harden Port Preflight, Ownership, And Recovery Behavior
Explanation: the review identifies fixed localhost ports as the most immediate
open operational risk across API and Fuseki scripts.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use docs/review11.5.1.md, docs/ExecutionPlan11.5_log.md, docs/ops/windows_single_host_operator.md, docs/ops/windows_fuseki_operator.md, and these code surfaces as governing context:

- scripts/api-start.ps1
- scripts/api-stop.ps1
- scripts/installed-runtime-smoke.ps1
- scripts/optional-runtime-smoke.ps1
- scripts/ops/windows-fuseki-service.ps1
- scripts/health/api-probe.ps1
- scripts/health/fuseki-probe.ps1

Implement the smallest defensible change set that makes fixed-port behavior deterministic on a reused workstation:

1. explicit preflight for occupied ports,
2. clear distinction between a process this repo started versus a foreign/stale owner,
3. deterministic fail-fast or owned-process cleanup behavior,
4. machine-readable evidence where the scripts already emit reports.

Do not broaden the support claim beyond one Windows host and one API instance. Do not add promotion work for quarantined search/KG features. End by running the narrowest verification needed and summarize the final service-lifecycle contract.
```

### Step 1.2 - Add Regression Coverage For Port Collision And Cleanup Paths
Explanation: the risk should not remain script-only; it needs focused tests or
smoke assertions that catch regressions.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `medium`

Prompt:
```text
Use the service-lifecycle changes from Step 1.1 as governing context. Add the smallest focused regression coverage needed so fixed-port collision and cleanup behavior cannot silently drift. Prefer existing release/runtime test surfaces over new frameworks. Keep the coverage local to supported single-host behavior only.
```

### Step 1.3 - Re-Run The Supported Single-Host Lifecycle Proof
Explanation: after the script and test hardening, re-prove the supported
service start, probe, and stop flow.

Type: `Code`

```powershell
pwsh scripts/installed-runtime-smoke.ps1 `
  -WheelPath dist/earcrawler-*.whl `
  -UseHermeticWheelhouse `
  -HermeticBundleZipPath dist/hermetic-artifacts.zip `
  -ReleaseChecksumsPath dist/checksums.sha256 `
  -UseLiveFuseki `
  -AutoProvisionFuseki `
  -RequireFullBaseline `
  -Host 127.0.0.1 `
  -Port 9001 `
  -ReportPath dist/installed_runtime_smoke.json

pwsh scripts/api-start.ps1 -Host 127.0.0.1 -Port 9001
pwsh scripts/health/api-probe.ps1 -Host 127.0.0.1 -Port 9001 -ReportPath dist/observability/health-api.txt -JsonReportPath dist/observability/api_probe.json
pwsh scripts/api-stop.ps1

pwsh scripts/optional-runtime-smoke.ps1 -Host 127.0.0.1 -Port 9001 -SkipLocalAdapter -ReportPath dist/optional_runtime_smoke.json
py -3 -m pytest -q tests/release/test_installed_runtime_smoke_options.py tests/release/test_optional_runtime_smoke.py tests/kg/test_fuseki.py
```

Phase gate:

- supported start/probe/stop flows pass on the fixed-port baseline
- script evidence now distinguishes occupied-port handling from normal startup
- targeted regression tests pass

Contingency if gate fails:

- if deterministic fail-fast is achievable before safe auto-recovery, prefer
  fail-fast and explicit operator guidance over broader cleanup heuristics

## Phase 2 - Fuseki Runtime Regression Guardrails

Goal: preserve the local network/runtime fixes already closed in 11.5 and make
them harder to regress.

### Step 2.1 - Re-Harden The Known Fuseki Correctness Surfaces
Explanation: the reviewed documents show that the Fuseki path had real bugs
even when the service appeared healthy.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use docs/review11.5.1.md, the completed Step 4.3 and Step 5.1 entries in docs/ExecutionPlan11.5_log.md, and these code surfaces as governing context:

- earCrawler/kg/fuseki.py
- earCrawler/cli/kg_commands.py
- scripts/installed-runtime-smoke.ps1
- scripts/ops/windows-fuseki-service.ps1
- tests/kg/test_fuseki.py
- tests/cli/test_kg_emit_cli.py
- tests/rag/test_kg_expansion_fuseki.py

Reinspect and harden the smallest set of guards around these already-fixed regression surfaces:

1. TDB2 startup flag and storage layout correctness,
2. kg load versus kg serve dataset-path alignment,
3. named-graph fixture behavior under unionDefaultGraph assumptions,
4. Java-resolution behavior across the supported PowerShell entry points.

Preserve the current quarantine boundary. Do not reopen promotion work for /v1/search or KG expansion. End by running the narrowest targeted verification needed and summarize what is now guarded versus what remains only an operational assumption.
```

### Step 2.2 - Re-Execute The KG Runtime Mechanics Proof
Explanation: after the guardrail work, rerun the real load/serve/query path to
confirm the previously fixed runtime shape still holds.

Type: `Code`

```powershell
$env:JAVA_HOME='tools\jdk17\jdk-17.0.18+8'
$env:PATH="$env:JAVA_HOME\bin;$env:PATH"
$env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES='1'
$env:EARCTL_USER='test_operator'

py -m earCrawler.cli kg emit -s ear -s nsf -i data -o data\kg
py -m earCrawler.cli kg load --ttl data\kg\ear.ttl --db db
py -m earCrawler.cli kg serve --db db --dataset /ear --no-wait
py -m earCrawler.cli kg query --endpoint http://localhost:3030/ear/sparql --sparql "SELECT * WHERE { ?s ?p ?o } LIMIT 5" --out dist/kg_query_results.json

py -3 -m pytest -q tests/kg/test_fuseki.py tests/cli/test_kg_emit_cli.py tests/rag/test_kg_expansion_fuseki.py tests/toolchain/test_fuseki_checksum.py
```

Phase gate:

- the real KG load/serve/query path passes again against the current corpus
- targeted Fuseki and CLI regression tests pass
- no step changes `api.search` or `kg.expansion` capability state

Contingency if gate fails:

- if the fix starts requiring new promotion evidence or expanded runtime
  support claims, stop and keep the capability state unchanged

## Phase 3 - Upstream HTTP Failure Semantics

Goal: close the remaining document-identified ambiguity in live-source client
and caller behavior.

### Step 3.1 - Audit And Repair Failure Taxonomy Across Remaining Clients
Explanation: Federal Register and ORI were fixed in 11.5, but the review still
flags broader client/caller failure semantics, especially around Trade.gov and
caller-visible degraded states.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use docs/review11.5.1.md, the Step 3.2 remediation notes in docs/ExecutionPlan11.5_log.md, and these code surfaces as governing context:

- api_clients/federalregister_client.py
- api_clients/ori_client.py
- api_clients/tradegov_client.py
- earCrawler/corpus/sources.py
- any direct live-source caller or health/reporting surface that publishes source state

Audit the remaining upstream HTTP failure taxonomy and implement the smallest defensible repair set so covered failure modes do not collapse into misleading empty-success behavior. Focus on:

1. typed degraded versus empty versus hard-fail outcomes,
2. caller behavior when an upstream client returns degraded state,
3. Trade.gov parity with the more fully documented FR and ORI behavior,
4. focused regression tests for the repaired behavior.

Keep scope narrow. Do not redesign the ingestion architecture, add new sources, or create another review note.
```

### Step 3.2 - Re-Run Live-Source Readiness And Client Regression Checks
Explanation: re-run the bounded live-source readiness path and targeted client
tests after the repair.

Type: `Code`

```powershell
$env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES='1'
$env:EARCTL_USER='test_operator'

py -3 -m pytest -q tests/clients/test_federalregister_client.py tests/clients/test_ori_client.py tests/clients/test_tradegov_client.py tests/test_tradegov_client.py tests/api/test_federalregister_client_html_guard.py tests/obs/test_health_contracts.py
py -m earCrawler.cli jobs run tradegov --dry-run
py -m earCrawler.cli jobs run federalregister --dry-run
```

Phase gate:

- targeted client and health/reporting tests pass
- bounded live-source readiness commands still pass
- covered upstream failures are represented explicitly instead of disappearing
  into ambiguous empty results

Contingency if gate fails:

- if a client still cannot express degraded state cleanly, prefer explicit
  degraded reporting over silent fallback to empty-success behavior

## Phase 4 - Bounded Closure And Handoff

Goal: close the follow-on work without reopening blocked areas or generating
another review loop.

### Step 4.1 - Refresh The ExecutionPlan11.5.1 Log With Results And Residual Risk
Explanation: keep one concise execution ledger that captures what changed and
what remains deliberately out of scope.

Type: `Prompt`

Model: `GPT-5.4-Mini`
Reasoning: `medium`

Prompt:
```text
Use docs/ExecutionPlan11.5.1_log.md as the only log and refresh it from the completed Phase 1 through Phase 3 work. For each completed step, record:

- date
- command or test run
- pass/fail
- artifact path if any
- files touched if code changed
- remaining risk or next blocker

End with a short conclusion that states:

1. which review11.5.1 findings were closed,
2. which risks remain open but bounded,
3. which blocked items were intentionally not touched.

Do not create another review, new roadmap, or promotion decision.
```

Phase gate:

- one log file contains the plan findings, execution results, and conclusions
- blocked work remains explicitly untouched:
  - Execution Plan 11.5 Step 7.1 and later CUDA-dependent work
  - search/KG unquarantine or promotion work beyond the current boundary

Contingency if gate fails:

- collapse the log back to a terse operational ledger and remove narrative
  repetition before closing the plan

## Recommended Execution Order

1. Finish Phase 0 before changing code.
2. Finish Phase 1 before rerunning any broader runtime or KG proofs.
3. Finish Phase 2 before touching remaining upstream client semantics.
4. Finish Phase 3 before writing final conclusions into the follow-on log.
5. Stop immediately if any step tries to pull in blocked CUDA work or new
   search/KG promotion evidence.

## Notes On Scope Discipline

- Do not convert this follow-on plan into a replacement for Execution Plan
  11.5.
- Do not reopen the dated `Keep Quarantined` search/KG decision from
  `2026-03-27`.
- Do not advance local-adapter training, benchmark, or release-candidate work
  from this plan.
- If a risk is real but not fixable without blocked work, record it in
  `docs/ExecutionPlan11.5.1_log.md` and stop there.
