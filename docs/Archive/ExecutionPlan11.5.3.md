# Execution Plan 11.5.3

Source guidance:

- `docs/ExecutionPlan11.5.md` as structure/template only
- `docs/ExecutionPlan11.5_log.md`
- `docs/ExecutionPlan11.5.2.md`
- `docs/ExecutionPlan11.5.2_log.md`
- `service/api_server/config.py`
- `service/api_server/limits.py`
- `service/api_server/health.py`
- `service/api_server/runtime_state.py`
- `service/api_server/routers/rag.py`
- `docs/ops/observability.md`
- `docs/ops/windows_single_host_operator.md`
- `docs/ops/multi_instance_deferred.md`

Prepared: April 6, 2026

## Purpose

This document is a focused execution plan for adaptive rate-limit evidence and
recommendation work on the supported Windows single-host API baseline.

The finish line is not "auto-tuning in principle." The finish line is:

1. the repo can measure API-host request cost using current single-host facts,
2. rate-limit recommendations are derived from host-side evidence rather than
   client guesswork,
3. the current fixed env vars remain authoritative unless an operator
   explicitly opts into the recommendation output,
4. the recommendation path is documented, bounded, and test-covered,
5. every step is logged in `docs/ExecutionPlan11.5.3_log.md`.

## Scope

In scope:

- authenticated and anonymous API request-limit recommendation for the
  single-host Python API service
- host-side telemetry for route latency, error pressure, and concurrency
  saturation
- a conservative recommendation algorithm for
  `EARCRAWLER_API_AUTH_PER_MIN` and `EARCRAWLER_API_ANON_PER_MIN`
- operator-visible reporting only, unless a later dated decision explicitly
  authorizes automatic application

Out of scope:

- multi-instance or distributed rate limiting
- autoscaling infrastructure
- changing the supported single-host product boundary
- brute-force startup probing that intentionally drives the API into failure

## Non-Negotiable Strengths To Preserve

- keep the supported topology single-host and process-local
- do not silently weaken current rate limiting defaults
- do not let client benchmark behavior masquerade as server capacity evidence
- distinguish recommendation from automatic configuration changes
- keep operator override and rollback paths explicit

## Execution Rules

- each step must update `docs/ExecutionPlan11.5.3_log.md`
- each implementation step must produce one concrete artifact, test result, or
  file citation
- recommendation logic must be bounded by explicit min/max clamps
- no startup self-benchmark may be introduced without a later dated decision
- if recommendation output is added to `/health`, it must remain informational
  and backward-compatible

## Phase 0 - Lock The Workstream

Goal: create one dedicated plan/log pair and fix the target under test.

### Step 0.1 - Create The Execution Ledger
Explanation: use one log for all work in this plan.

Type: `Prompt`

Model: `GPT-5.4-Mini`
Reasoning: `medium`

Prompt:
```text
Use docs/ExecutionPlan11.5.3_log.md as the single execution ledger for this plan. Keep it terse and operational: date/time, step id, command or prompt scope, pass/fail, artifact path, and next blocker. Preserve append-only behavior after the header.
```

### Step 0.2 - Record The Current Rate-Limit Baseline
Explanation: capture the fixed current defaults and the exact runtime surfaces
that enforce them before adding any recommendation path.

Type: `Code`

```powershell
py -3 -m json.tool service/docs/capability_registry.json > $null
rg -n "EARCRAWLER_API_AUTH_PER_MIN|EARCRAWLER_API_ANON_PER_MIN|authenticated_burst|anonymous_burst" service/api_server
rg -n "RateLimiter|enforce_rate_limits|429" service/api_server
```

Expected evidence:

- file citations in the execution log for the current config and enforcement
  points

### Step 0.3 - Normalize Historical Model-Size Wording
Explanation: align remaining historical docs so superseded references use
`4B-class` wording instead of stale `7B` wording, while preserving archive
status and dated context.

Type: `Code`

```powershell
rg -n "7B|7b" docs/Archive docs/ExecutionPlan11.5*.md
```

Expected evidence:

- an execution-log entry listing affected historical files
- wording updates recorded as documentation cleanup only (no runtime behavior
  change)

Phase gate:

- one exact baseline is recorded for config, enforcement, and observability

## Phase 1 - Define The Recommendation Contract

Goal: make recommendation semantics explicit before implementing telemetry.

### Step 1.1 - Write The Recommendation Design Note
Explanation: document what signals are allowed to influence the recommended
limits and what signals are not.

Type: `Prompt`

Model: `GPT-5.4`
Reasoning: `high`

Prompt:
```text
Use service/api_server/config.py, service/api_server/limits.py, service/api_server/health.py, docs/ops/observability.md, and docs/ops/multi_instance_deferred.md as governing context. Write one short dated design note for adaptive single-host API rate-limit recommendation. Keep it concrete: host-side telemetry inputs, bounded recommendation math, min/max clamps, route-class distinctions if needed, why requestor-side throughput is insufficient, and why startup brute-force probing is intentionally out of scope. Do not authorize automatic config mutation.
```

### Step 1.2 - Define The Recommendation Artifact Shape
Explanation: choose one machine-oriented output structure before wiring code.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `medium`

Prompt:
```text
Use the current API health and runtime-state shapes as governing context. Define the smallest machine-readable recommendation artifact for single-host rate-limit advice: schema version, observation window, route-class metrics, capacity inputs, computed recommendations, clamp reasons, and operator override note. Update the minimum docs or examples needed so later implementation has an explicit target.
```

Phase gate:

- one dated design note exists
- one explicit recommendation artifact shape exists

## Phase 2 - Capture Host-Side Capacity Signals

Goal: measure the API host behavior that should drive recommendations.

### Step 2.1 - Add Runtime Counters For Recommendation Inputs
Explanation: expose the smallest additional host-side telemetry needed for
recommendation without changing API semantics.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use service/api_server/config.py, service/api_server/limits.py, service/api_server/runtime_state.py, service/api_server/health.py, and any directly affected tests as governing context. Add the smallest host-side telemetry required for bounded rate-limit recommendation: route-class request counts, latency observations, 429/503 pressure, and concurrency saturation signals. Keep the implementation single-host and process-local. Do not add auto-tuning and do not weaken existing enforcement. Add focused tests.
```

### Step 2.2 - Surface Recommendation Inputs In An Operator-Visible Report
Explanation: make the new measurements inspectable before computing limits.

Type: `Code`

```powershell
py -3 -m pytest -q tests/service
pwsh scripts/health/api-probe.ps1 -Host 127.0.0.1 -Port 9001 -JsonReportPath dist/observability/api_probe.rate_limit_inputs.json
```

Expected evidence:

- passing focused tests
- one operator-visible artifact or health payload showing the new inputs

Phase gate:

- host-side recommendation inputs are observable and test-covered

## Phase 3 - Compute Conservative Recommendations

Goal: turn observed host behavior into bounded advice without automatic
mutation.

### Step 3.1 - Implement The Recommendation Calculator
Explanation: compute recommended anonymous/authenticated limits from observed
host capacity with explicit safety factors and clamps.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `high`

Prompt:
```text
Use the Phase 1 artifact contract, the new host-side telemetry, service/api_server/config.py, and the current single-host support boundary as governing context. Implement a conservative recommendation calculator for EARCRAWLER_API_AUTH_PER_MIN and EARCRAWLER_API_ANON_PER_MIN. Keep it informational only. The output must include the source metrics, safety factor, min/max clamp behavior, and an explicit note that operator-set env vars remain authoritative. Add focused tests that prove bounded output under low-capacity, nominal, and high-capacity observations.
```

### Step 3.2 - Add Health Or Report Exposure For The Recommendation
Explanation: make the recommendation visible without breaking existing health
consumers.

Type: `Prompt`

Model: `GPT-5.3-Codex`
Reasoning: `medium`

Prompt:
```text
Use service/api_server/health.py, docs/ops/observability.md, and the recommendation artifact contract as governing context. Expose the recommendation in the smallest backward-compatible way, either in health details or a closely related operator report. Keep it informational only and document how operators should interpret it.
```

Phase gate:

- one machine-readable recommendation is produced from host-side observations
- the output is visible to operators without automatic application

## Phase 4 - Operator Control And Rollback

Goal: document how operators use or ignore the recommendation safely.

### Step 4.1 - Document Operator Use And Override Rules
Explanation: the operator must be able to tell the difference between current
defaults, observed recommendations, and explicit overrides.

Type: `Prompt`

Model: `GPT-5.4`
Reasoning: `medium`

Prompt:
```text
Use docs/ops/windows_single_host_operator.md, docs/ops/observability.md, and the implemented recommendation output as governing context. Add the minimum operator-facing guidance needed to explain: fixed defaults, informational recommendation output, when to raise or lower EARCRAWLER_API_AUTH_PER_MIN and EARCRAWLER_API_ANON_PER_MIN, and how to roll back to explicit manual values. Do not broaden the support boundary and do not imply automatic tuning is enabled.
```

### Step 4.2 - Validate The Informational-Only Boundary
Explanation: verify that recommendation output does not mutate runtime config.

Type: `Code`

```powershell
py -3 -m pytest -q tests/service tests/api
```

Phase gate:

- operator docs explain the recommendation path
- tests prove recommendation output does not change configured limits by itself

## Completion Condition

- `docs/ExecutionPlan11.5.3_log.md` contains the step ledger
- one dated design note exists for adaptive single-host rate-limit
  recommendation
- host-side telemetry and bounded recommendation output are implemented and
  test-covered
- operator docs explain use, override, and rollback
- the result remains informational only unless a later dated decision widens
  scope
