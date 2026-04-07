# Single-Host API Rate-Limit Recommendation Design

Design date: April 6, 2026

Status: informational-only design for single-host recommendation output. This
does not authorize automatic mutation of `EARCRAWLER_API_AUTH_PER_MIN` or
`EARCRAWLER_API_ANON_PER_MIN`.

Artifact contract: `docs/ops/rate_limit_recommendation_artifact.md`
(`api-rate-limit-recommendation.v1`).

## Scope

This design applies only to the supported API topology:

- one Windows host
- one EarCrawler API service instance
- one process-local `runtime_state` owner for rate limits, request concurrency,
  cache state, and retriever warm state

If `runtime_contract.topology != "single_host"` or
`declared_instance_count != 1`, the recommendation status should be
`unsupported_topology` and no limit advice should be produced.

## Recommendation inputs

The recommendation should use host-side telemetry collected from the running API
process over one rolling observation window. The minimum eligible window is:

- at least 15 minutes of observations, or
- at least 200 non-health requests,

whichever is later.

The minimum telemetry set is:

- route-class request counts
- route-class completion latency observations, including `p95_latency_ms`
- route-class `429` counts
- route-class `503` counts
- process-local concurrency saturation signals from the current
  `ConcurrencyGate`

Route classes should stay coarse and operational:

- `health`: `/health`; record for visibility but exclude from recommendation
  math
- `query`: supported read paths such as `/v1/rag/query` and `/v1/search` when
  enabled
- `answer`: `/v1/rag/answer` when enabled; treat as heavier than `query`
- `other`: any remaining API route that is neither health nor a primary user
  request path

If a non-health route class has fewer than 20 completed requests in the window,
that class is informational only and should not drive a recommendation.

## Recommendation math

The recommendation should estimate a conservative host minute budget from the
slowest eligible non-health route class, then convert that host budget into
per-subject advice.

For each eligible non-health route class:

1. Set `latency_seconds = max(p95_latency_ms / 1000.0, 0.25)`.
2. Compute `base_capacity_rpm = floor((EARCRAWLER_API_CONCURRENCY * 60 / latency_seconds) * 0.70)`.
3. Apply pressure penalties:
   - if `503_rate > 0`, multiply by `0.50`
   - if `concurrency_saturation_rate > 0.05`, multiply by `0.75`
   - if `p95_latency_ms >= 0.80 * request_timeout_seconds * 1000`, multiply by
     `0.50`
4. Do not treat `429` by itself as host distress. If `429_rate > 0` while
   `503_rate == 0` and concurrency saturation stays below the threshold, record
   that the current configured limiter is binding, but do not reduce capacity
   from that signal alone.

The host minute budget is the minimum penalized capacity across eligible
non-health route classes. This keeps the heaviest observed route class in
control of the recommendation.

Per-subject recommendations:

- `recommended_auth_per_min = clamp(floor(host_budget_rpm * 0.25), 40, 240)`
- `recommended_anon_per_min = clamp(floor(recommended_auth_per_min * 0.25), 10, 60)`

Clamp reasons must be reported explicitly, including:

- `insufficient_evidence`
- `unsupported_topology`
- `min_clamp`
- `max_clamp`
- `configured_limit_binding`
- `latency_pressure`
- `concurrency_pressure`
- `error_pressure`

## Why client throughput is not enough

Requestor-side throughput is not a reliable capacity signal for this system.
Client-observed requests are distorted by network conditions, current limiter
settings, request mix, cache hits, retriever warm state, and caller think time.
Those observations cannot distinguish "the host is saturated" from "the client
is slow" or "the current limiter blocked the test first." The recommendation
therefore has to come from host-side latency, `503` pressure, and concurrency
saturation recorded inside the API process.

## Explicit non-goals

- No startup brute-force probing. The API should not intentionally drive itself
  into `429`, timeout, or `503` conditions during startup just to estimate
  limits.
- No automatic config mutation. The live env vars remain authoritative until an
  operator explicitly changes them.
- No multi-instance inference. Process-local measurements from one API instance
  must not be presented as a scaled deployment recommendation.

Startup brute-force probing is intentionally out of scope because it would
distort warmup behavior, create avoidable failure noise in `/health` and logs,
and test a state the supported operator path does not require at service boot.
