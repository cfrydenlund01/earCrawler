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
| `/v1/rag/query` | Cached RAG answer surface with lineage metadata. |

Refer to `service/openapi/openapi.yaml` for exhaustive schemas and examples.

## Contract Artifacts

- Canonical spec: `service/openapi/openapi.yaml` (source of truth, reviewed in CI).
- Machine-readable docs: `docs/api/openapi.json` (generated from the YAML for easy import into tooling).
- Postman collection: `docs/api/postman_collection.json` (pre-wired requests for each public endpoint).
- Release-ready bundle: run `pwsh scripts/api/package_contract.ps1` to zip the JSON + Postman artifacts with versioned release notes under `dist/api-contract-<version>.zip`.

Import the Postman collection, then edit the collection variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `base_url` | Target FastAPI facade (include scheme + port). | `http://localhost:9001` |
| `api_key` | Optional X-Api-Key header. Leave blank for anonymous quotas. | _(blank)_ |
| `entity_id` | Sample KG entity to drive `/entities` and `/lineage`. | `urn:ear:entity:demo` |
| `search_query` | Default `/v1/search` and SPARQL template query string. | `export controls` |

The collection attaches `X-Api-Key` automatically when the variable is populated.

## Refreshing JSON + Postman Outputs

Run the exporter whenever the canonical YAML changes so downstream consumers stay in sync:

```powershell
# From the repo root
py scripts/api/export_contract.py `
  --openapi-yaml service/openapi/openapi.yaml `
  --json-out docs/api/openapi.json `
  --postman-out docs/api/postman_collection.json `
  --base-url http://localhost:9001
```

The script validates that the YAML is loadable, writes the JSON artifact used by SDK consumers, and regenerates the Postman collection with the latest routes. Update the `--base-url` flag if you want the collection to default to a remote deployment.

To share the artifacts externally, package them (plus release notes) before uploading with the installer/wheel:

```powershell
pwsh scripts/api/package_contract.ps1
# => dist\api-contract-0.2.5.zip (uses pyproject version + CHANGELOG.md excerpt)
```

Pass `-Version` or `-ReleaseNotesPath` to override the defaults (for example, to point at a curated release notes document).

## Env-Based `curl` Workflow

Use the dotenv-driven helper when you want to verify the endpoints without installing Postman:

1. Copy `.env.example` to `.env` and set values as needed. Leave `EAR_API_KEY` blank to reuse the existing `TRADEGOV_API_KEY` environment variable.
2. Start the facade (`earctl api start`) so `http://localhost:9001` is reachable, or edit `EAR_BASE_URL` for remote hosts.
3. Run `pwsh scripts/api/curl_facade.ps1 [-EnvFile .env.local] [-BaseUrl ...] [-EntityId ...]`.

The script issues curl calls for `/health`, `/v1/search`, `/v1/entities/{entity_id}`, `/v1/lineage/{entity_id}`, `/v1/sparql`, and `/v1/rag/query`. When `EAR_ENTITY_ID` is empty it auto-discovers a live identifier by asking `/v1/search`, then falls back to the deterministic fixture `urn:ear:entity:demo`. This keeps the workflow useful for both local fixture runs and real deployments.

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
