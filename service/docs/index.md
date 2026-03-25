# EarCrawler Read-only API

`service/api_server` is the only supported service runtime surface in this repository. The legacy modules `earCrawler.service.sparql_service` and `earCrawler.service.legacy.kg_service` are quarantined and should not be used for operator deployments.
Machine-readable capability state lives in `service/docs/capability_registry.json`
and is published with the API contract artifacts at
`docs/api/capability_registry.json`.

Capability status follows the registry plus `README.md` and
`docs/capability_graduation_boundaries.md`: `/health`,
`/v1/entities/{entity_id}`, `/v1/lineage/{entity_id}`, `/v1/sparql`, and
`/v1/rag/query` are `Supported`; `/v1/rag/answer`,
`EARCRAWLER_RETRIEVAL_MODE=hybrid`, and local-adapter serving are `Optional`;
`/v1/search` and KG expansion remain `Quarantined` until
`docs/kg_quarantine_exit_gate.md` is passed and recorded.
The dated maintenance-boundary decision for the current production-beta target
is `docs/search_kg_quarantine_decision_package_2026-03-19.md`: preserve the
explicit quarantine boundary instead of treating these features as active
promotion work.
Generated answers remain advisory-only for the production-beta target and must
not be treated as autonomous legal or regulatory determinations. See
`docs/answer_generation_posture.md`.
The quarantined `/v1/search` route is disabled by default and requires
`EARCRAWLER_API_ENABLE_SEARCH=1` for local validation workflows.
Default OpenAPI contract artifacts exclude `/v1/search`.

The EarCrawler API exposes a curated read-only surface for SPARQL datasets. All
queries execute against allowlisted templates and are constrained by size,
latency and rate-limit budgets. Use the `/openapi.yaml` document for schema
details.

Supported deployment semantics are single-host only. Current rate limits,
concurrency controls, the RAG cache, retriever caches, and retriever warmup
state are process-local, so this document does not claim multi-instance
correctness. Deferred future-work note: `docs/ops/multi_instance_deferred.md`.
The API now routes runtime-owned state through the
`service/api_server/runtime_state.py` boundary so the supported single-host
assumption is explicit in one place rather than being implied by scattered
`app.state` wiring. Architecture note:
`docs/single_host_runtime_state_boundary.md`.
The `/health` payload reports this contract under `runtime_contract`, including
the capability snapshot consumed from the registry, so release and operator
checks can validate the deployment shape directly.

## Try it (PowerShell)

```powershell
# Health probe
curl.exe -s http://localhost:9001/health | ConvertFrom-Json

# Quarantined text-index search surface (explicit opt-in)
$env:EARCRAWLER_API_ENABLE_SEARCH = '1'
$headers = @{ 'Accept' = 'application/json' }
curl.exe -s -H @headers "http://localhost:9001/v1/search?q=export&limit=5"

# Fetch a single entity view
curl.exe -s "http://localhost:9001/v1/entities/urn:example:entity:1"
```

## Rate limits

* Anonymous clients: 30 requests/minute with bursts of 10.
* Authenticated API keys: 120 requests/minute with bursts of 20.
* Request body limit: 32 KB.
* Upstream timeout: 5 seconds.
* These budgets are enforced per process; this page does not claim aggregated
  multi-instance budgets.

## Errors

Errors conform to [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) style
problem details. Every response includes a `trace_id` that can be correlated
with structured JSON logs emitted by the service.
