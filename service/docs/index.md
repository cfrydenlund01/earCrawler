# EarCrawler Read-only API

`service/api_server` is the only supported service runtime surface in this repository. The legacy modules `earCrawler.service.sparql_service` and `earCrawler.service.legacy.kg_service` are quarantined and should not be used for operator deployments.

Capability status follows `README.md` and
`docs/capability_graduation_boundaries.md`: `/health`,
`/v1/entities/{entity_id}`, `/v1/lineage/{entity_id}`, `/v1/sparql`, and
`/v1/rag/query` are `Supported`; `/v1/rag/answer`,
`EARCRAWLER_RETRIEVAL_MODE=hybrid`, and local-adapter serving are `Optional`;
`/v1/search` and KG expansion remain `Quarantined` until
`docs/kg_quarantine_exit_gate.md` is passed and recorded.
The quarantined `/v1/search` route is disabled by default and requires
`EARCRAWLER_API_ENABLE_SEARCH=1` for local validation workflows.
Default OpenAPI contract artifacts exclude `/v1/search`.

The EarCrawler API exposes a curated read-only surface for SPARQL datasets. All
queries execute against allowlisted templates and are constrained by size,
latency and rate-limit budgets. Use the `/openapi.yaml` document for schema
details.

Supported deployment semantics are single-host only. Current rate limits,
concurrency controls, and the RAG cache are process-local, so this document
does not claim multi-instance correctness. Deferred future-work note:
`docs/ops/multi_instance_deferred.md`.
The `/health` payload reports this contract under `runtime_contract` so release
and operator checks can validate the deployment shape directly.

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
