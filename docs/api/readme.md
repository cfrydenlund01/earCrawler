# Read-only API Surface

This document follows the canonical capability matrix in `README.md`. Treat the
status labels here as normative for the API surface:

- `Supported`: part of the supported production API contract.
- `Optional`: supported only when explicitly enabled/configured.
- `Quarantined`: implemented or testable, but not a supported production
  commitment yet.

The EarCrawler API exposes curated read-only access to the supported service
surface. Endpoints mirror the allowlisted SPARQL templates stored under
`service/templates/`. All responses are validated against Pydantic schemas and
must complete within the configured latency budget.

Supported deployment semantics are single-host only. Current rate limits,
concurrency controls, and the RAG cache are process-local, so this document
does not claim multi-instance correctness. Deferred future-work note:
`docs/ops/multi_instance_deferred.md`.

## Endpoints

| Path | Status | Description |
| ---- | ------ | ----------- |
| `/health` | Supported | Liveness and readiness probe. |
| `/v1/entities/{entity_id}` | Supported | Curated entity projection (labels, provenance, sameAs). |
| `/v1/lineage/{entity_id}` | Supported | PROV-O lineage graph. |
| `/v1/sparql` | Supported | Proxy for allowlisted SPARQL templates only. |
| `/v1/rag/query` | Supported | Retrieval surface with lineage metadata. Route-level release-smoke latency/failure budgets are defined in `docs/ops/api_latency_budgets.md`. |
| `/v1/rag/answer` | Optional | Remote-LLM answer generation; requires explicit env enablement and provider credentials. |
| `/v1/search` | Quarantined | Text-index-backed label search. Available for local validation, but not part of the supported production contract until `docs/kg_quarantine_exit_gate.md` is passed and recorded. Its route budget remains a local validation guard only; see `docs/ops/api_latency_budgets.md`. |

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
| `search_query` | Default query string for the quarantined `/v1/search` route and SPARQL `search_entities` template. | `export controls` |

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

The script issues curl calls for `/health`, `/v1/search`, `/v1/entities/{entity_id}`, `/v1/lineage/{entity_id}`, `/v1/sparql`, and `/v1/rag/query`. Because `/v1/search` is quarantined, supported production checks should provide `EAR_ENTITY_ID` explicitly instead of relying on search-based auto-discovery. When `EAR_ENTITY_ID` is empty the helper still tries `/v1/search` first, then falls back to the deterministic fixture `urn:ear:entity:demo` for local validation workflows.

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
* `/v1/search` remains `Quarantined` and requires a text-enabled Fuseki dataset
  (Jena `text:TextDataset` over `rdfs:label`, as configured in
  `bundle/assembler/tdb2-readonly.ttl`).
* Rate-limit and concurrency budgets are per process; this document does not
  claim aggregated multi-instance budgets.

Rate-limit state is surfaced via the `X-RateLimit-*` headers and `Retry-After`.

## Authentication

API keys are optional. Provide them via the `X-Api-Key` header. Keys are loaded
from the Windows Credential Manager (`EarCrawler-API` service name) or the
`EARCRAWLER_API_KEYS` environment variable (semicolon-separated
`label=value` pairs). Anonymous access is allowed with lower quotas.

Credential formats:

- Env-backed keys: `X-Api-Key: <secret>` or `X-Api-Key: <label>:<secret>`.
- Keyring-backed keys: `X-Api-Key: <label>:<secret>`.

Keyring mode now validates the presented secret against the stored secret for
that label using constant-time comparison; presenting only a label is not
accepted.

## Windows Service

Use `docs/ops/windows_single_host_operator.md` as the authoritative Windows
service guide. That document defines the supported deployment artifact, NSSM
configuration, health checks, upgrade path, backup/restore flow, rollback, and
secret rotation.

`service/windows/` is now only a pointer back to that guide. The
`scripts/api-*.ps1` helpers and `earctl api start|stop|smoke` remain useful for
source-checkout development, but they are not the authoritative release-artifact
deployment path.

## Logs and Redaction

Structured JSON logs emit `event`, `trace_id`, `identity`, and rate-limit
counters. Payloads follow B.13 redaction rules. Combine with Windows Event Log
forwarding for centralized monitoring.
