# Read-only API Surface

The EarCrawler API exposes curated read-only access to the KG. Endpoints mirror
the allowlisted SPARQL templates stored under `service/templates/`. All
responses are validated against Pydantic schemas and must complete within the
configured latency budget.

## Endpoints

| Path | Description |
| ---- | ----------- |
| `/health` | Liveness and readiness probe. |
| `/v1/entities/{entity_id}` | Curated entity projection (labels, provenance, sameAs). |
| `/v1/search` | Label search against text indexes. |
| `/v1/sparql` | Proxy for allowlisted SPARQL templates only. |
| `/v1/lineage/{entity_id}` | PROV-O lineage graph. |

Refer to `service/openapi/openapi.yaml` for exhaustive schemas and examples.

## SDK usage

```python
from api_clients.ear_api_client import EarCrawlerApiClient

with EarCrawlerApiClient("http://localhost:9001", api_key="dev-token") as client:
    print(client.health())
    search = client.search_entities("export controls", limit=5)
    entity = client.get_entity(search["results"][0]["id"])
    lineage = client.get_lineage(entity["id"])
    sparql = client.run_template("search_entities", parameters={"q": "example"})
    rag = client.rag_query("What changed in part 734?", include_lineage=True)
```

`EarCrawlerApiClient` automatically sets the `X-Api-Key` header when a token is
provided and returns parsed JSON dictionaries for each call.

## Budgets and Limits

* Request body limit: **32 KB**
* Per-request timeout: **5 seconds**
* Concurrency ceiling: **16** in-flight requests
* Rate limits:
  * Anonymous (`ip:*`): **30 requests/min**, burst 10
  * Authenticated (`X-Api-Key`): **120 requests/min**, burst 20
* Fuseki endpoint must be read-only. Queries outside of `registry.json` are
denied with `400`.

Rate-limit state is surfaced via the `X-RateLimit-*` headers and `Retry-After`.

## Authentication

API keys are optional. Provide them via the `X-Api-Key` header. Keys are loaded
from the Windows Credential Manager (`EarCrawler-API` service name) or the
`EARCRAWLER_API_KEYS` environment variable (semicolon-separated
`label=value` pairs). Anonymous access is allowed with lower quotas.

## Windows Service

Use the placeholder guides in `service/windows/` to install the API via NSSM.
Scripts under `scripts/api-*.ps1` provide local orchestration and smoke tests.
Run the CLI helper: `earctl api start|stop|smoke` (requires operator or
maintainer role).

## Logs and Redaction

Structured JSON logs emit `event`, `trace_id`, `identity`, and rate-limit
counters. Payloads follow B.13 redaction rules. Combine with Windows Event Log
forwarding for centralized monitoring.
