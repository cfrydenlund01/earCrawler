# Review Pass 7 Step 9.1 Readiness Note

Prepared: March 12, 2026

Scope: quarantined [`/v1/search`](../service/api_server/routers/search.py) and "KG-backed hybrid retrieval" as currently represented in the repository.

Constraint: this note uses only the current repository contents. It does not make a promote/defer recommendation.

## Executive snapshot

| Surface | What is implemented now | Current gate posture | Readiness snapshot |
| --- | --- | --- | --- |
| `/v1/search` | Real FastAPI route, real SPARQL template, schema/docs/client surface, local text-search smoke script | Quarantine is documentary, not runtime-disabled | Partially implemented but not supportable as a supported operator feature today |
| "KG-backed hybrid retrieval" | Real dense+BM25 hybrid mode in the retriever, real KG expansion adapters in the pipeline/eval stack | Quarantine/experimental posture in docs; no single supported runtime contract | Implemented in pieces, but the operator-facing feature boundary is still ambiguous |

## `/v1/search`

### What exists now

- A real API route is mounted unconditionally in [`service/api_server/routers/__init__.py`](../service/api_server/routers/__init__.py) and implemented in [`service/api_server/routers/search.py`](../service/api_server/routers/search.py).
- The route executes a real allowlisted SPARQL template, [`service/templates/search_entities.rq`](../service/templates/search_entities.rq), via the shared Fuseki gateway.
- The route is published in API-facing artifacts:
  - [`service/openapi/openapi.yaml`](../service/openapi/openapi.yaml)
  - [`docs/api/openapi.json`](api/openapi.json)
  - [`docs/api/postman_collection.json`](api/postman_collection.json)
  - [`api_clients/ear_api_client.py`](../api_clients/ear_api_client.py)
- Basic route coverage exists:
  - contract tests in [`tests/api/test_route_contracts.py`](../tests/api/test_route_contracts.py)
  - rate-limit/security-header coverage in [`tests/api/test_rate_limits.py`](../tests/api/test_rate_limits.py) and [`tests/api/test_security_headers.py`](../tests/api/test_security_headers.py)
  - a Windows-only real Fuseki text-search smoke in [`tests/test_text_search_smoke.py`](../tests/test_text_search_smoke.py) using [`kg/scripts/ci-text-search-smoke.ps1`](../kg/scripts/ci-text-search-smoke.ps1)
- The route has a machine-readable latency budget in [`perf/config/api_route_budgets.yml`](../perf/config/api_route_budgets.yml), and the docs correctly describe that budget as quarantined/local-validation-only in [`docs/ops/api_latency_budgets.md`](ops/api_latency_budgets.md).

### What is missing

- No runtime feature flag or kill-switch disables `/v1/search` in deployed API instances. The route is reachable whenever `service.api_server` starts.
- The authoritative supported API smoke path excludes `/v1/search`:
  - CI starts the API and runs [`scripts/api-smoke.ps1`](../scripts/api-smoke.ps1), which checks `/health`, `/v1/entities/{id}`, `/v1/lineage/{id}`, and `/v1/sparql`, but not `/v1/search`
  - [`tests/tooling/test_runtime_service_surface.py`](../tests/tooling/test_runtime_service_surface.py) explicitly asserts that supported API smoke does not include `/v1/search`
- The authoritative Windows operator guide, [`docs/ops/windows_single_host_operator.md`](ops/windows_single_host_operator.md), assumes an existing read-only Fuseki query endpoint and does not document provisioning, validating, or rolling back a text-enabled Fuseki dataset/Lucene index.
- There is no release-gated clean-room or installed-wheel proof for the text-indexed search stack itself. The real text-search smoke is local and conditional on Jena/Fuseki tool availability.
- No repository-owned supported install flow provisions the Jena text index configuration used by the smoke script.

### Risky or ambiguous

- Quarantine is primarily documentary. The route remains mounted, published in OpenAPI/Postman, and exposed through the typed API client.
- Observability material still treats `/v1/search` as an operational probe target:
  - [`scripts/health/api-probe.ps1`](../scripts/health/api-probe.ps1)
  - [`scripts/canary/run-canaries.ps1`](../scripts/canary/run-canaries.ps1)
  - [`canary/config.yml`](../canary/config.yml)
  - [`docs/ops/observability.md`](ops/observability.md)
  This conflicts with the narrower supported-path smoke and operator story.
- Failure behavior for "Fuseki present but not text-index-enabled" is not defined as a supported contract. The route delegates directly to Fuseki; there is no route-specific degraded-mode behavior.

### What would block supportability today

- No supported operator workflow to install or verify the text-index-backed Fuseki surface.
- No release-gated end-to-end proof in the same runtime shape operators are expected to use.
- No explicit rollback/troubleshooting contract for text search in the authoritative operator docs.
- No hard runtime gate separating "implemented for local validation" from "available in production API instances".

## "KG-backed hybrid retrieval"

### Repository reality today

The repository does not expose one single runtime feature literally named "KG-backed hybrid retrieval". It currently splits into two separate mechanisms:

1. Hybrid retrieval mode in the retriever:
   - implemented in [`earCrawler/rag/retriever.py`](../earCrawler/rag/retriever.py)
   - controlled by `EARCRAWLER_RETRIEVAL_MODE=dense|hybrid`
   - hybrid means dense + BM25 fusion over retrieval metadata rows, not Fuseki/KG traversal
2. KG expansion as an optional augmentation layer:
   - implemented through [`earCrawler/rag/retrieval_runtime.py`](../earCrawler/rag/retrieval_runtime.py), [`earCrawler/rag/pipeline.py`](../earCrawler/rag/pipeline.py), and [`earCrawler/rag/kg_expansion_fuseki.py`](../earCrawler/rag/kg_expansion_fuseki.py)
   - controlled by `EARCRAWLER_ENABLE_KG_EXPANSION`, `EARCRAWLER_KG_EXPANSION_PROVIDER`, `EARCRAWLER_KG_EXPANSION_MODE`, and related env vars

That split is important because the current repo does not present one clear operator-facing product contract that combines them.

### What exists now

- Real hybrid retrieval is implemented in the retriever:
  - dense/`hybrid` mode resolution in [`earCrawler/rag/retriever.py`](../earCrawler/rag/retriever.py)
  - BM25 state, reciprocal-rank fusion, and config reporting are all real code
  - targeted tests exist in [`tests/rag/test_retriever.py`](../tests/rag/test_retriever.py)
- Real KG expansion exists:
  - provider selection and failure policy in [`earCrawler/rag/retrieval_runtime.py`](../earCrawler/rag/retrieval_runtime.py)
  - deterministic Fuseki traversal adapter in [`earCrawler/rag/kg_expansion_fuseki.py`](../earCrawler/rag/kg_expansion_fuseki.py)
  - pipeline integration in [`earCrawler/rag/pipeline.py`](../earCrawler/rag/pipeline.py)
  - tests in [`tests/rag/test_pipeline_expansion.py`](../tests/rag/test_pipeline_expansion.py), [`tests/rag/test_pipeline_kg_expansion.py`](../tests/rag/test_pipeline_kg_expansion.py), [`tests/rag/test_kg_expansion_fuseki.py`](../tests/rag/test_kg_expansion_fuseki.py), and [`tests/rag/test_retrieval_runtime.py`](../tests/rag/test_retrieval_runtime.py)
- Eval surfaces exist for dense-vs-hybrid comparison and provenance capture:
  - [`earCrawler/cli/eval_commands.py`](../earCrawler/cli/eval_commands.py)
  - [`earCrawler/cli/eval_workflows.py`](../earCrawler/cli/eval_workflows.py)
  - [`scripts/eval/eval_rag_llm.py`](../scripts/eval/eval_rag_llm.py)
  - [`tests/eval/test_retrieval_compare.py`](../tests/eval/test_retrieval_compare.py)
  - [`docs/hybrid_retrieval_design.md`](hybrid_retrieval_design.md)
- The shared API retriever loader in [`service/api_server/rag_support.py`](../service/api_server/rag_support.py) will pick up `EARCRAWLER_RETRIEVAL_MODE`, so hybrid ranking can affect `/v1/rag/query` and `/v1/rag/answer` whenever RAG is enabled.

### What is missing

- No single supported API contract exposes KG expansion output. [`service/api_server/schemas/rag.py`](../service/api_server/schemas/rag.py) returns retrieved documents, lineage, and generated answers, but not KG expansion snippets or paths.
- The service API path does not call the full pipeline KG-expansion flow. [`service/api_server/rag_service.py`](../service/api_server/rag_service.py) uses retrieval plus prompt/generation helpers, not `pipeline.answer_with_rag(...)`.
- The authoritative operator guide, [`docs/ops/windows_single_host_operator.md`](ops/windows_single_host_operator.md), does not document enabling hybrid retrieval or KG expansion on the installed wheel path.
- There is no dedicated release-gated end-to-end smoke that proves hybrid retrieval plus live KG expansion through the supported runtime shape.
- The package-data configuration appears incomplete for the Fuseki KG-expansion template:
  - the runtime adapter reads [`earCrawler/sparql/kg_expand_by_section_id.rq`](../earCrawler/sparql/kg_expand_by_section_id.rq)
  - [`pyproject.toml`](../pyproject.toml) packages `earCrawler.sparql` as `["*.sparql"]`, not `["*.rq"]`
  - the clean-room wheel smoke, [`scripts/package-wheel-smoke.ps1`](../scripts/package-wheel-smoke.ps1), checks `prefixes.sparql` but not `kg_expand_by_section_id.rq`
  This is a concrete supportability gap for installed-wheel KG expansion.

### Risky or ambiguous

- "Hybrid retrieval" and "KG-backed retrieval" are not the same implementation today, but some docs discuss them together under the quarantine umbrella. The product boundary is therefore underspecified.
- Hybrid retrieval is effectively env-reachable anywhere the shared retriever is used, even though docs describe KG-dependent hybrid behavior as quarantined.
- KG expansion has a documented soft-fail mode (`EARCRAWLER_KG_EXPANSION_FAILURE_POLICY=disable`) that can silently disable the augmentation path at runtime. That may be acceptable for experiments, but it is not framed as a supported operator contract.
- The default KG expansion mode is `always_on` once expansion is otherwise enabled, which increases the need for a very explicit operator story before support claims are widened.

### What would block supportability today

- The repo does not define one exact operator-facing feature that would graduate: retriever hybrid mode, KG expansion, or both together.
- No installed-artifact proof that live Fuseki-backed KG expansion works from the wheel-based runtime.
- No authoritative operator docs for configuration, health checks, rollback, or failure handling of hybrid/KG retrieval on the supported deployment path.
- No dedicated release gate for the exact runtime shape being claimed.
- A likely packaging defect exists for the Fuseki KG-expansion SPARQL template, which would block clean-room supportability even before broader promotion questions are answered.

## Bottom line for Step 9.1

The repository shows real implementation work for both surfaces, but the evidence is uneven:

- `/v1/search` is a real shipped route with local-validation evidence, not a support-ready operator feature.
- "KG-backed hybrid retrieval" is not one coherent runtime surface yet; it is a mix of a real hybrid retriever mode and a separate optional KG expansion layer.
- The main blockers are not "missing code" so much as missing runtime gating, missing operator-ready install/rollback guidance, missing release-shaped end-to-end evidence, and one likely clean-room packaging gap for KG expansion.
