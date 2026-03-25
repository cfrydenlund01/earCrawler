# Review Pass 7 Step 9.2 Support-Burden Analysis

Prepared: March 12, 2026

Inputs:

- [`docs/review_pass_7_step9_1_readiness_note.md`](review_pass_7_step9_1_readiness_note.md)
- current repository contents only

Constraint: this note does not make the final promote/defer recommendation. It makes the operational tradeoffs explicit.

## Executive summary

Promoting quarantined `/v1/search` and KG-backed hybrid retrieval now would add a meaningful support contract expansion across five areas at once:

1. release validation
2. observability and canaries
3. operator documentation
4. incident/debug tooling
5. installed-artifact correctness

The repo already has strong support scaffolding for the narrow supported path: [`/v1/rag/query`](api/readme.md), supported API smoke in [`scripts/api-smoke.ps1`](../scripts/api-smoke.ps1), release-smoke budgets in [`perf/config/api_route_budgets.yml`](../perf/config/api_route_budgets.yml), wheel validation in [`scripts/package-wheel-smoke.ps1`](../scripts/package-wheel-smoke.ps1), and a real Windows operator guide in [`docs/ops/windows_single_host_operator.md`](ops/windows_single_host_operator.md).

The burden comes from the fact that the quarantined features would need their own equivalent support package, and in a few places the current repo still mixes "implemented", "observable", and "supported" states.

## Minimum supportability requirements

These are the minimum requirements for supported status, not nice-to-have improvements.

| Area | Minimum requirement for supported status | Current evidence | Current status |
| --- | --- | --- | --- |
| Validation and CI | Release-gated end-to-end tests in the same runtime shape operators use | Supported path has this in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) and [`docs/ci.md`](ci.md), but `/v1/search` and live KG-backed hybrid retrieval do not | Missing for both promoted surfaces |
| Installed artifact correctness | Clean-room wheel/service proof that packaged resources and runtime dependencies work outside source checkout | [`scripts/package-wheel-smoke.ps1`](../scripts/package-wheel-smoke.ps1) exists for current supported runtime, but Step 9.1 identified no equivalent proof for text search and a likely packaging gap for `kg_expand_by_section_id.rq` | Missing/incomplete |
| Operator docs | Authoritative install, config, health, rollback, and troubleshooting instructions in the wheel-based operator guide | [`docs/ops/windows_single_host_operator.md`](ops/windows_single_host_operator.md) covers the supported runtime only; it does not operationalize text-indexed Fuseki, hybrid mode, or KG expansion | Missing for promoted scope |
| Observability | Health probes, canaries, logs, and failure signatures aligned with the exact supported feature set | General API/Fuseki observability exists in [`docs/ops/observability.md`](ops/observability.md), [`scripts/health/api-probe.ps1`](../scripts/health/api-probe.ps1), and [`scripts/canary/run-canaries.ps1`](../scripts/canary/run-canaries.ps1), but support-boundary alignment is incomplete | Partially present, not support-ready |
| Incident and debug tooling | Deterministic repro path and operator-facing diagnostics for common failures | Supported path has some of this through health checks, watchdogs, and smoke flows; route-specific and KG-expansion-specific failure playbooks do not exist | Missing for promoted scope |
| Product boundary clarity | One explicit, testable definition of what exactly is now supported | `/v1/search` is clear enough as a route, but "KG-backed hybrid retrieval" is split between retriever hybrid mode and separate KG expansion | Missing for hybrid/KG scope |

## Existing support scaffolding that can be reused

The repo is not starting from zero. These pieces already reduce the incremental burden:

- Supported-path CI sequencing already exists in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).
- Route-level perf budget tooling already exists in [`earCrawler/perf/api_budget_gate.py`](../earCrawler/perf/api_budget_gate.py), [`perf/config/api_route_budgets.yml`](../perf/config/api_route_budgets.yml), and [`tests/perf/test_api_budget_gate.py`](../tests/perf/test_api_budget_gate.py).
- The service already has health/readiness and structured logging infrastructure:
  - [`service/api_server/health.py`](../service/api_server/health.py)
  - [`service/api_server/logging_integration.py`](../service/api_server/logging_integration.py)
  - [`docs/ops/observability.md`](ops/observability.md)
- Wheel-based packaging and clean-room validation already exist for the supported service surface:
  - [`pyproject.toml`](../pyproject.toml)
  - [`scripts/package-wheel-smoke.ps1`](../scripts/package-wheel-smoke.ps1)
  - [`tests/tooling/test_runtime_service_surface.py`](../tests/tooling/test_runtime_service_surface.py)
- The repo already has quarantine governance artifacts that define the burden explicitly:
  - [`docs/kg_quarantine_exit_gate.md`](kg_quarantine_exit_gate.md)
  - [`docs/kg_unquarantine_plan.md`](kg_unquarantine_plan.md)
  - [`docs/kg_search_status_decision_2026-03-10.md`](kg_search_status_decision_2026-03-10.md)

This means the operational burden is mostly additive, not foundational. The cost is still non-trivial because the missing pieces are exactly the ones that make support commitments expensive.

## `/v1/search` support burden

### What already exists

- Real API route, schema, OpenAPI, client, and basic tests:
  - [`service/api_server/routers/search.py`](../service/api_server/routers/search.py)
  - [`tests/api/test_route_contracts.py`](../tests/api/test_route_contracts.py)
  - [`tests/api/test_rate_limits.py`](../tests/api/test_rate_limits.py)
- Local validation smoke against real text-enabled Fuseki:
  - [`tests/test_text_search_smoke.py`](../tests/test_text_search_smoke.py)
  - [`kg/scripts/ci-text-search-smoke.ps1`](../kg/scripts/ci-text-search-smoke.ps1)
- Observability hooks already exercise `/v1/search`:
  - [`scripts/health/api-probe.ps1`](../scripts/health/api-probe.ps1)
  - [`canary/config.yml`](../canary/config.yml)

### Minimum work still required for supported status

- Add a supported, release-gated end-to-end search smoke in the authoritative CI/release path, not only a local conditional smoke.
- Define the installed/operator contract for text-enabled Fuseki:
  - how it is provisioned
  - how it is verified
  - how rollback works
  - what "healthy but not text-enabled" means operationally
- Add an explicit runtime boundary mechanism:
  - either search is supported and release-gated
  - or it is hard-disabled outside local validation
  The current documentary-only quarantine is expensive to support because the route is still mounted.
- Align observability with the support boundary:
  - if promoted, `/v1/search` probes and canaries become normative
  - if not promoted, they remain local-validation diagnostics and should not imply support status

### Operational cost profile

Promoting `/v1/search` now is a medium support burden by itself.

Why not low:

- it widens the supported Fuseki dependency from read-only query endpoint behavior to text-indexed dataset behavior
- it adds route-specific failure modes that the current operator guide does not own
- it requires release-shaped proof, not just route existence

Why not highest:

- the route itself is small
- basic tests already exist
- local smoke and observability seeds already exist and can be upgraded rather than invented

## KG-backed hybrid retrieval support burden

### What already exists

- Real hybrid retrieval mode in [`earCrawler/rag/retriever.py`](../earCrawler/rag/retriever.py) with targeted tests in [`tests/rag/test_retriever.py`](../tests/rag/test_retriever.py).
- Real KG expansion logic and tests:
  - [`earCrawler/rag/retrieval_runtime.py`](../earCrawler/rag/retrieval_runtime.py)
  - [`earCrawler/rag/kg_expansion_fuseki.py`](../earCrawler/rag/kg_expansion_fuseki.py)
  - [`tests/rag/test_pipeline_kg_expansion.py`](../tests/rag/test_pipeline_kg_expansion.py)
  - [`tests/rag/test_kg_expansion_fuseki.py`](../tests/rag/test_kg_expansion_fuseki.py)
- Eval comparison and provenance tooling:
  - [`scripts/eval/eval_rag_llm.py`](../scripts/eval/eval_rag_llm.py)
  - [`tests/eval/test_retrieval_compare.py`](../tests/eval/test_retrieval_compare.py)
  - [`docs/hybrid_retrieval_design.md`](hybrid_retrieval_design.md)

### Minimum work still required for supported status

- First define the exact supported feature:
  - hybrid BM25+dense ranking only
  - KG expansion only
  - or a combined feature
  Without that, CI, docs, canaries, and incident runbooks cannot be scoped correctly.
- Add installed-artifact proof for live KG expansion through the wheel-based runtime.
- Fix the likely packaging gap called out in Step 9.1 for [`earCrawler/sparql/kg_expand_by_section_id.rq`](../earCrawler/sparql/kg_expand_by_section_id.rq) relative to [`pyproject.toml`](../pyproject.toml).
- Decide and document failure posture:
  - whether KG expansion failure is allowed to soft-disable in supported mode
  - whether supported hybrid mode may run without KG expansion
  - what operators should see in logs/health if the Fuseki traversal path is unavailable
- Extend the authoritative operator guide for:
  - enabling hybrid retrieval on the installed service
  - enabling KG expansion safely
  - verification steps
  - rollback steps
- Add release-gated end-to-end validation in the real runtime shape, not only unit/eval harness coverage.

### Operational cost profile

Promoting this scope now is a high support burden.

Reasons:

- the feature boundary is still ambiguous
- it crosses package/runtime/operator boundaries at the same time
- it introduces more failure modes than `/v1/search`
- part of the work is not just new tests or docs, but deciding what exactly must be supported

## Minimum requirements vs nice-to-haves

### Minimum requirements

- Release-gated end-to-end validation for every promoted surface.
- Installed-wheel proof for the exact promoted runtime behavior.
- Authoritative operator-guide coverage for install, config, health, rollback, and troubleshooting.
- Explicit failure policy and observability signals that match implementation.
- Clear product boundary naming exactly what is supported.

### Nice-to-have improvements

- Richer dashboards or alert thresholds beyond current health/canary coverage.
- More detailed compare reports for dense vs hybrid quality over time.
- Additional route-level metrics beyond present latency/failure budgets.
- Automated provisioning of text-indexed Fuseki datasets.
- More complete synthetic incident drills once the feature set is stable.

These would improve operability, but they are not the main blockers. The main blockers are the minimum support package items above.

## Support burden comparison

### If promoted now

| Surface | Burden if promoted now | Why |
| --- | --- | --- |
| `/v1/search` | Medium | Needs authoritative CI/release gate, operator-owned text-index story, runtime-boundary cleanup, and incident guidance |
| KG-backed hybrid retrieval | High | Needs feature-boundary definition, packaging correction, installed-artifact proof, operator docs, and explicit failure/observability contract |

Additional repo-wide effect:

- The supported surface area widens immediately.
- Existing observability scripts that already touch quarantined features become part of the formal support contract rather than optional/internal validation aids.
- Any future incident involving Fuseki text indexing or KG expansion becomes a product-support obligation rather than an experimental-path issue.

### If kept quarantined for the next release cycle

| Surface | Burden if kept quarantined | Why |
| --- | --- | --- |
| `/v1/search` | Low to medium | Main tasks are boundary hygiene, keeping docs honest, and maintaining local-validation guards without promoting them |
| KG-backed hybrid retrieval | Low to medium | Main tasks are clarifying scope, fixing packaging/runtime gaps, and continuing eval/research validation without widening the operator contract |

Additional repo-wide effect:

- The supported-path evidence package stays focused on the already-defined Windows single-host runtime.
- Existing local-validation tools can remain useful without being treated as release obligations.
- The team can fix ambiguity and packaging issues before converting them into operator-facing promises.

## Operational tradeoff

The tradeoff is not "implemented vs not implemented". It is "current supported path remains narrow and well-evidenced" versus "support contract expands into areas that still need operatorization".

Promoting now would mostly create support work, not unlock a large amount of already-proven operator value:

- `/v1/search` is close enough to be tempting, but its missing work is exactly the hard part of supportability: owned deployment story, release gates, and incident handling.
- KG-backed hybrid retrieval has more technical substance than operator clarity right now. The code and eval scaffolding exist, but the supported runtime contract is still underdefined.

Keeping them quarantined for one more release cycle keeps the burden mostly in repo hygiene and targeted hardening work, rather than immediate support obligations.
