Performance and Memory Review

Issue: Async client recreated per request
Location: service/api_server/fuseki.py:22
Impact: performance
Why it matters: Creating a new httpx.AsyncClient for every query prevents connection pooling and TLS/session reuse; under load this adds per-request setup/teardown overhead and increases latency.
Evidence: query() used `async with httpx.AsyncClient(...): await client.post(...)` per call.
Remediation: Reuse a single AsyncClient across requests and close it on app shutdown; register a shutdown hook to `aclose()`.
Severity: high, confidence: high

Issue: Inference without no_grad/eval
Location: earCrawler/agent/long_context_pipeline.py:68, 100, 138, 188
Impact: performance, memory
Why it matters: Generating without torch.no_grad()/inference_mode() and leaving models in train mode keeps autograd graphs and dropout active, increasing memory usage and reducing throughput.
Evidence: Calls to `.generate()` lacked inference context; models were not set to `.eval()` after load.
Remediation: Set models to `.eval()` after loading and wrap generation in `torch.inference_mode()` (or `no_grad()` fallback).
Severity: high, confidence: high

Issue: Requests sessions not explicitly closed
Location: api_clients/ear_api_client.py:36; api_clients/tradegov_client.py:48; api_clients/federalregister_client.py:48; api_clients/ori_client.py:18; earCrawler/kg/sparql.py:20
Impact: resource lifetime
Why it matters: Long‑lived processes that create Sessions without closing can retain open connection pools/file descriptors longer than necessary, risking descriptor exhaustion in edge cases.
Evidence: Clients constructed `requests.Session()` and did not provide `close()` or context manager.
Remediation: Track session ownership; add `.close()` and optional context manager; close only when the client owns the session.
Severity: medium, confidence: high

Issue: File cache can grow unbounded
Location: earCrawler/utils/http_cache.py:32
Impact: storage growth
Why it matters: Cache writes a file per distinct URL/params/headers without eviction, which can grow indefinitely on long‑running systems, causing disk pressure and slower directory scans.
Evidence: HTTPCache writes `{digest}.json` with no TTL/limit; only `clear()` exists.
Remediation: Add max entries/TTL policy and periodic eviction; consider size‑bounded LRU by deleting least‑recently‑used cache files.
Severity: medium, confidence: medium

Issue: Potential deep recursion in summary reduction
Location: earCrawler/agent/long_context_pipeline.py:160
Impact: performance, stability
Why it matters: `_reduce_summaries` recurses until the merged text fits; extremely long documents could cause deep recursion and stack growth.
Evidence: Recursive call `return self._reduce_summaries(condensed)`.
Remediation: Convert to an iterative reduction loop to avoid deep Python recursion.
Severity: low, confidence: medium

Issue: Blocking sleeps in HTTP telemetry sink
Location: earCrawler/telemetry/sink_http.py:33
Impact: performance, async compatibility
Why it matters: `time.sleep` in retry loop blocks the calling thread; if used in an async context, it can stall the event loop.
Evidence: `time.sleep(self.backoff + random.random())` inside send loop.
Remediation: If used in async flows, replace with an async transport or run in a background thread/executor; otherwise ensure it’s invoked from CLI/sync contexts only.
Severity: low, confidence: medium

