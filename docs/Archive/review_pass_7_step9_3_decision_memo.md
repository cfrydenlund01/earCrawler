# Review Pass 7 Step 9.3 Decision Memo

Prepared: March 12, 2026

Inputs:

- [`docs/review_pass_7_step9_1_readiness_note.md`](review_pass_7_step9_1_readiness_note.md)
- [`docs/review_pass_7_step9_2_support_burden_analysis.md`](review_pass_7_step9_2_support_burden_analysis.md)
- [`docs/production_candidate_scope_pass7.md`](production_candidate_scope_pass7.md)
- [`docs/kg_quarantine_exit_gate.md`](kg_quarantine_exit_gate.md)
- current repository contents only

## Decision

Recommendation: keep `/v1/search` quarantined and defer promotion of KG-backed hybrid retrieval for the next release cycle.

Scope effect:

- `/v1/search` remains `Quarantined`.
- Text-index-backed Fuseki search remains outside the supported production boundary.
- KG-dependent retrieval behavior remains `Quarantined`.
- The existing opt-in `hybrid` dense+BM25 retriever mode may remain implemented for local validation and eval work, but it is not promoted to supported status by this memo.

This reaffirms the March 10, 2026 no-go decision in [`docs/kg_search_status_decision_2026-03-10.md`](kg_search_status_decision_2026-03-10.md) and extends the same posture to the broader "KG-backed hybrid retrieval" bundle described in Step 9.1.

## Path Evaluation

### Path A: Promote now

Decision: reject for this release cycle.

Why:

- The current pass 7 production-candidate scope explicitly keeps `/v1/search` and KG-dependent hybrid retrieval out of the supported milestone.
- `/v1/search` is implemented, but it still lacks the operator-owned text-index install story, release-gated runtime-shape proof, and explicit runtime boundary expected by the quarantine exit gate.
- "KG-backed hybrid retrieval" is not one clear supported feature today. The repo currently splits it between:
  - opt-in dense+BM25 fusion in the retriever
  - separate optional KG expansion logic
- The Step 9.1 note identified a likely installed-wheel packaging gap for [`earCrawler/sparql/kg_expand_by_section_id.rq`](../earCrawler/sparql/kg_expand_by_section_id.rq), which is disqualifying for a support claim on the wheel-based runtime path.
- Step 9.2 shows that promotion would mostly add support burden now: new release gates, operator runbooks, observability alignment, incident handling, and installed-artifact validation.

Bottom line: promotion would widen the support contract faster than the repo's current evidence supports.

### Path B: Keep quarantined/deferred for one more release cycle

Decision: accept.

Why:

- It preserves the pass 7 scope lock around the strongest supported path: Windows single-host deterministic corpus -> KG -> API verification.
- It keeps the support contract aligned with what CI, operator docs, and wheel validation already prove.
- It allows targeted hardening work without making operators own text-indexed Fuseki behavior or KG-expansion failure modes yet.
- It avoids promoting an ambiguous combined feature before the repo defines what exactly would be supported.

Bottom line: deferral keeps the supported boundary credible while still allowing the repo to retain implementation and local-validation coverage for future work.

## Rationale

The deciding factor is not whether code exists. It does. The deciding factor is whether the current repository proves a supportable operator contract in the runtime shape the project already claims to support.

That proof is incomplete in both areas:

- `/v1/search` is a real route, but its quarantine is still mostly documentary. The route is mounted and published, while the supported smoke path, operator guide, and release evidence still exclude it.
- KG-backed hybrid retrieval has implementation substance, but not a single coherent product boundary. The API service does not expose one exact supported KG-augmented contract, and the wheel/runtime proof for live KG expansion is incomplete.

Given the current production-candidate boundary, promotion would mostly create new obligations rather than formalize an already-proven supported feature.

## Non-Goals for the Next Release Cycle

- Do not claim `/v1/search` as a supported API route.
- Do not claim text-index-backed Fuseki provisioning or rollback as part of the supported Windows single-host operator workflow.
- Do not claim one supported feature called "KG-backed hybrid retrieval" until the repo defines whether that means:
  - dense+BM25 hybrid ranking only
  - KG expansion only
  - or a combined retrieval+expansion runtime feature
- Do not make live KG expansion a required dependency of the supported RAG runtime this cycle.
- Do not treat existing search probes, canaries, or local smoke scripts as sufficient release evidence by themselves.

## Continued Quarantine Expectations

- Keep supported-path docs aligned with the current boundary in [`docs/production_candidate_scope_pass7.md`](production_candidate_scope_pass7.md), [`README.md`](../README.md), and [`RUNBOOK.md`](../RUNBOOK.md).
- Keep `/v1/search` and KG-dependent retrieval surfaces clearly labeled as quarantined, optional, or experimental wherever they are mentioned.
- Preserve local-validation and eval tooling where useful, but do not let those surfaces imply supported status.
- Use Step 9.4 to remove or tighten any remaining repo ambiguity between "implemented", "observable", and "supported".

## Reconsideration Criteria

Reconsider promotion only after the repo carries current evidence that passes the existing gate in [`docs/kg_quarantine_exit_gate.md`](kg_quarantine_exit_gate.md).

### `/v1/search`

Before reconsideration, the repo should prove all of the following:

- an explicit runtime boundary: either release-gated and supported, or hard-disabled outside local validation
- a wheel-based or otherwise operator-owned workflow for text-index-enabled Fuseki setup
- release-gated end-to-end smoke in the same runtime shape operators use
- authoritative operator docs for install, verification, rollback, troubleshooting, and failure handling
- observability and canary behavior that matches the final support claim

### KG-backed hybrid retrieval

Before reconsideration, the repo should prove all of the following:

- one exact feature definition to graduate, not an ambiguous bundle
- installed-artifact correctness for any packaged SPARQL/templates and runtime dependencies
- release-gated end-to-end proof for the exact supported runtime path
- an explicit failure contract for KG expansion availability and degradation behavior
- operator docs for enablement, verification, rollback, and incident/debug flow
- API/runtime behavior that makes the promoted feature visible and testable in the supported service surface

Recommendation for the next review: split the decision into separate graduation tracks for `/v1/search` and for retrieval behavior. Do not revisit them only as one bundled "KG-backed hybrid retrieval" question again.

## Final Recommendation

Keep `/v1/search` quarantined and keep KG-backed hybrid retrieval deferred for the next release cycle.

Rationale: the pass 7 production candidate is strongest when it stays inside the already-proven single-host deterministic path. Current evidence supports continued implementation and local validation of these features, but it does not yet support widening the operator contract.
