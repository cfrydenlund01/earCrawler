# Architecture & Roadmap

## End-to-End Flow

```
Federal Register / Trade.gov APIs
        │
        ▼
earctl crawl ──► JSONL corpus (data/*.jsonl)
        │
        ▼
earctl kg-emit ──► RDF/Turtle (data/kg/*.ttl)
        │
        ├──► earctl kg-load ──► Apache Jena TDB2 (db/)
        │                        │
        │                        ▼
        │                 Fuseki service (kg-serve)
        │                        │
        │                        ├─► FastAPI facade (`service/api_server`)
        │                        │       │
        │                        │       └─► EarCrawlerApiClient /
        │                        │           earctl api commands
        ▼                        │
earctl bundle export-profiles    │
        │                        │
        └──► RAG stack (FAISS retriever + remote LLM provider)
```

The `scripts/demo-end-to-end.ps1` helper automates the boxed path using
deterministic fixtures: crawl → emit TTL → load TDB2 → produce bundles →
generate summary analytics.

## Component Responsibilities
- **CLI (`earctl`)**: Operator entry point wrapping ingestion, KG operations,
  telemetry, and admin utilities.
- **Apache Jena Fuseki**: Hosts the read-only SPARQL endpoint; warmed via
  `perf/warmers` queries and guarded by SHACL/OWL smoke tests (`tests/test_*`).
- **FastAPI facade**: Templates curated SPARQL queries, enforces RBAC and rate
  limits, and exposes the contract consumed by downstream applications.
- **RAG Layer**: FAISS retriever + remote LLM provider (Groq/NVIDIA NIM) providing
  contextualised answers for EAR QA.

## Footprint & Performance (Single-node Windows Testbed)

| Workload                    | CPU (vCPU) | RAM (GB) | Disk (GB) | Notes |
|-----------------------------|-----------:|---------:|----------:|-------|
| `earctl crawl` (fixtures)   | 2          | 1.0      | <0.1      | Deterministic mode, no live HTTP. |
| `earctl kg-emit`            | 2          | 0.5      | <0.1      | Produces ~15 KB Turtle from fixtures. |
| `earctl kg-load`            | 2          | 1.5      | 0.5       | TDB2 load via embedded Jena binaries. |
| `earctl kg-serve`           | 2          | 2.0      | 1.0       | Fuseki idle footprint; add 1 GB for caches. |
| FastAPI facade (`uvicorn`)  | 1          | 0.3      | <0.1      | Concurrency limit default 32. |
| RAG inference (remote LLM)  | 2          | 1.0      | <0.1      | Latency dominated by network/provider rate limits. |

Sizing increases linearly with live data volume; bump Fuseki heap (`--java-opts`)
once KG surpasses 4 GB on disk.

## Roadmap (Next 3 Iterations)
1. **Iteration A – Demo Hardening**
   - Ship `scripts/demo-end-to-end.ps1` + Windows service docs.
   - Align version metadata and packaging (completed in this branch).
   - Produce signed wheel/EXE via `scripts/build-release.ps1`.
2. **Iteration B – API & Client**
   - Lock OpenAPI contract (`/openapi.json`) and publish `EarCrawlerApiClient`.
   - Stand up public docs + sample Postman collection.
   - Add CI smoke hitting `/health`, `/v1/search`, and SPARQL templates.
3. **Iteration C – Production Readiness**
   - Finalise evaluation datasets & metrics (tracked separately).
   - Wire continuous export to governance storage with provenance ledger.
   - Integrate SLO canaries with alerting & dashboards (`docs/proposal/observability.md`).
