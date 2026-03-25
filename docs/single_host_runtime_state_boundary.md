# Single-Host Runtime-State Boundary

EarCrawler's supported API topology remains:

- one Windows host
- one EarCrawler API service instance
- one process-local runtime-state owner inside `service/api_server/runtime_state.py`

That boundary is deliberate. The supported API currently keeps the following
state inside one process:

- request rate-limit buckets
- request concurrency gate state
- RAG query cache entries
- retriever-local caches and loaded model/index state
- retriever startup warmup status

This means the current runtime contract is safe to reason about only for the
documented single-host, single-instance deployment shape. Adding another API
process or host would immediately change behavior for throttling, cache hits,
warmup, and rollout/drain semantics.

## What the runtime-state boundary does

- Keeps process-local state ownership explicit in one module instead of
  scattering it across `app.state`, middleware internals, and startup hooks.
- Exposes the current process-local contract under `/health` ->
  `runtime_contract.runtime_state`.
- Makes it clear which behaviors are runtime-local implementation details, not
  shared-service guarantees.

## What would have to change before any shared-state claim

Before EarCrawler could claim multi-instance correctness, it would need at
least:

1. A shared or intentionally disabled rate-limit design across instances.
2. A defined concurrency and request-drain model for rollout and failure
   handling across more than one process or host.
3. A documented retriever-cache strategy, including cache invalidation and warm
   startup behavior when instances are replaced.
4. Operator guidance for routing, rollout, rollback, and instance replacement in
   a multi-instance deployment.
5. Regression tests and deployment evidence that prove those behaviors.

Until that work exists, the supported deployment target remains the Windows
single-host path in `docs/ops/windows_single_host_operator.md`.
