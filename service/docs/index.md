# EarCrawler Read-only API

The EarCrawler API exposes a curated read-only surface for SPARQL datasets. All
queries execute against allowlisted templates and are constrained by size,
latency and rate-limit budgets. Use the `/openapi.yaml` document for schema
details.

## Try it (PowerShell)

```powershell
# Health probe
curl.exe -s http://localhost:9001/health | ConvertFrom-Json

# Search for an entity label
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

## Errors

Errors conform to [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) style
problem details. Every response includes a `trace_id` that can be correlated
with structured JSON logs emitted by the service.
