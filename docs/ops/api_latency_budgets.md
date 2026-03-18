# API latency and failure budgets

This document defines the release-smoke performance contract for the
Windows-first single-host API surface.

## Scope

- `/v1/rag/query` is `Supported` and its budget is part of the supported release
  gate.
- `/v1/search` remains `Quarantined`. Its budget is enforced only as a local
  validation and regression guard; it does not change the current product
  support decision.

The machine-readable source of truth is
`perf/config/api_route_budgets.yml`.

## Budget profile

- Runtime profile: `windows_single_host`
- Request timeout budget: `5000 ms`
- Gate style: deterministic route smoke using fixture-backed API dependencies
- Enforcement point: CI `cpu` job via `scripts/api_perf_smoke.py` (supported
  routes only by default)

## Route budgets

| Route | Runtime status | P95 latency budget | Max failure rate | Timeout expectation |
|---|---|---:|---:|---|
| `/v1/rag/query` | Supported | 400 ms | 0% | Must return `504` when work exceeds the 5 s request timeout; timeout response must arrive within 4.5-5.5 s |
| `/v1/search` | Quarantined | 250 ms | 0% | Must return `504` when work exceeds the 5 s request timeout; timeout response must arrive within 4.5-5.5 s |

Default gate routing is controlled in `perf/config/api_route_budgets.yml` using
`include_in_default_gate`. Quarantined routes like `/v1/search` are excluded
from the default release gate and can be run explicitly for local validation:

```powershell
py scripts/api_perf_smoke.py --include-quarantined
```

## What this gate accomplishes

- Detects route-level latency regressions before release.
- Blocks unexpected non-200 behavior on the supported retrieval path.
- Proves timeout middleware still cuts off slow requests instead of hanging.
- Keeps the quarantined search route bounded for local validation without
  claiming it as a supported production feature.

## Interpretation

- These are release-smoke budgets, not full throughput SLOs.
- The budgets are intentionally conservative and deterministic so they can run
  on `windows-latest` in CI.
- If operators or maintainers change the request timeout, route orchestration,
  or fixture-backed API behavior, this document and
  `perf/config/api_route_budgets.yml` must be updated together.
