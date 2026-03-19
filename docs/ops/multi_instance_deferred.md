# Multi-Instance Design Is Deferred

EarCrawler does not currently claim multi-instance correctness for the supported
runtime surface.

Today the supported contract is:

- one Windows host
- one EarCrawler API service instance
- one `runtime_state` owner for process-local limits and caches

Why support stops there today:

- API rate limiting is enforced by the process-local `runtime_state`, not through shared distributed state.
- The API concurrency limiter is process-local.
- The RAG query cache is an in-memory per-process cache owned by that same runtime state boundary.
- Repo-local operational guidance, rollback steps, and health checks assume one
  host and one service instance under operator control.

That means adding a second API instance behind a load balancer would change
runtime behavior immediately. The current docs therefore do not claim:

- aggregated rate-limit correctness across instances
- shared cache behavior across instances
- active-active failover semantics
- load-balanced session or request-routing guarantees

Before multi-instance support can be claimed, the project needs a separate
design and implementation pass that defines at least:

1. Shared or intentionally disabled cross-instance rate-limit state.
2. Shared cache strategy or an explicit no-cache stance for scaled deployments.
3. Health, rollout, rollback, and failure-domain behavior across more than one
   host or process.
4. Operator documentation for load balancers, service discovery, and instance
   replacement.
5. Validation and regression tests that prove multi-instance behavior, rather
   than inferring it from the current single-host path.

Until that work exists and is documented, the supported deployment target
remains the Windows-first single-host path described in
`docs/ops/windows_single_host_operator.md`.
