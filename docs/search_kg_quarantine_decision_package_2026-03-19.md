# Search And KG Quarantine Decision Package

Decision date: March 19, 2026

Recommendation: `Keep Quarantined`

Governing context:

- `docs/ExecutionPlanRunPass11.md`
- `docs/RunPass11.md`
- `docs/kg_quarantine_exit_gate.md`
- `docs/search_kg_quarantine_review_2026-03-19.md`
- `docs/capability_graduation_boundaries.md`
- `dist/search_kg_evidence/search_kg_evidence_bundle.json`
- `dist/search_kg_evidence/search_kg_evidence_bundle.md`
- `dist/optional_runtime_smoke.json`
- `dist/installed_runtime_smoke.json`
- `dist/release_validation_evidence.json`

## Scope

This package covers only the quarantined runtime surfaces governed by the
existing search/KG exit gate:

- `/v1/search`
- text-index-backed Fuseki search
- KG expansion used as a runtime dependency

It does not change support status by itself. It records the current evidence and
the dated recommendation required by Step 3.3.

## Capability Snapshot

Current machine-readable capability state:

- `api.search`
  - state: `quarantined`
  - default posture: disabled
  - gate: `EARCRAWLER_API_ENABLE_SEARCH=1`
  - surfaces: `/v1/search`, text-index-backed Fuseki search
- `kg.expansion`
  - state: `quarantined`
  - default posture: disabled
  - gate: `EARCRAWLER_ENABLE_KG_EXPANSION=1` plus provider-specific settings
  - surfaces: KG expansion during RAG

This still matches:

- `service/docs/capability_registry.json`
- `/health` in the installed runtime smoke
- the operator baseline in `docs/ops/windows_single_host_operator.md`

## Operator Workflow Required Before Promotion

For `/v1/search` to move from `Quarantined` to `Optional`, current policy still
requires:

1. A deployed-host, text-index-enabled Fuseki workflow in the supported Windows
   single-host operator path.
2. Release-gated smoke for `/v1/search` in the same runtime shape operators
   will use.
3. Operator docs covering enablement, health checks, failure handling, and
   rollback.

For KG expansion to move from `Quarantined` to `Optional`, current policy still
requires:

1. The runtime gate to stay explicit and default-off.
2. Release-gated smoke for both the configured success path and the declared
   failure policy.
3. Operator docs covering provider selection, health checks, latency and
   failure behavior, and rollback.

For both surfaces, the quarantine exit gate still requires the broader
end-to-end package in `docs/kg_quarantine_exit_gate.md`, including clean-room
packaging/install proof, production-like runtime smoke, operator readiness, and
a dated pass record.

## Smoke Coverage Present Today

Current evidence that does exist:

- `dist/optional_runtime_smoke.json`
  - search default-off: passed
  - search opt-in: passed
  - search rollback-off: passed
  - KG failure-policy checks (`disable`, `error`, `json_stub_expansion`):
    passed
- `dist/installed_runtime_smoke.json`
  - passed
  - confirms the installed runtime contract still reports:
    - `api.search = quarantined`
    - `kg.expansion = quarantined`
- `dist/release_validation_evidence.json`
  - present
  - not complete

This means the repo currently proves:

- the quarantine gates behave correctly in local/release-shaped validation
- the rollback-safe default contract is intact
- the declared failure policy is bounded and conservative

This does not mean the quarantined capabilities are ready for promotion.

## Rollback Expectations

Current rollback expectation remains:

- `/v1/search`
  - disable `EARCRAWLER_API_ENABLE_SEARCH`
  - restart the service
  - return to the API contract artifacts that exclude `/v1/search`
- `kg.expansion`
  - disable `EARCRAWLER_ENABLE_KG_EXPANSION`
  - return to retrieval-only RAG behavior
- deployed-host optional/quarantined validation modes
  - reset search and KG env vars to `0`
  - restart the EarCrawler API service
  - confirm `/health` returns to the baseline capability snapshot

These rollback expectations are documented and evidence-aligned, but they do
not substitute for promotion evidence.

## Failure Modes Recorded

The current workspace evidence supports these failure-mode expectations:

- `/v1/search` returns `404` when the search gate is disabled
- `/v1/search` returns `200` only when explicitly enabled for local validation
- KG expansion with `failure_policy=disable` fails closed rather than silently
  widening behavior
- KG expansion with `failure_policy=error` raises a bounded runtime error when
  Fuseki configuration is missing

This is useful evidence for maintaining quarantine safely. It is not sufficient
evidence for promotion.

## Evidence Gaps Blocking Promotion

The current blockers remain concrete and unchanged:

1. `dist/release_validation_evidence.json` is incomplete because
   `dist/checksums.sha256` was not found for the distributable-artifact proof.
2. No operator-owned text-index-enabled Fuseki provisioning and rollback
   evidence is attached for `/v1/search`.
3. No production-like smoke artifact is attached for `/v1/search` against a
   real text-index-backed Fuseki runtime path.
4. No production-like smoke artifact is attached for KG expansion success
   through the supported runtime shape.
5. No dated pass record exists showing the exit-gate criteria are fully
   satisfied with current evidence.

These gaps directly block the gate sections on:

- clean-room packaging and install work
- end-to-end tests for the real claimed runtime
- operator readiness
- the dated unquarantine decision record

## Decision

Decision for Step 3.3: `Keep Quarantined`.

Rationale:

- The current evidence is good enough to prove the baseline contract and the
  quarantine behavior.
- The current evidence is not good enough to prove operator-owned promotion of
  `/v1/search` or KG-backed runtime expansion.
- The governing gate is binary. It remains unpassed.

`Ready for formal promotion review` is not justified by current evidence.

## What Would Need To Exist Before Reconsideration

Revisit this decision only after all of the following exist in current,
archived evidence:

1. A release-shaped, operator-owned text-index-enabled Fuseki provisioning and
   rollback procedure.
2. Production-like `/v1/search` smoke against that real runtime shape.
3. Production-like KG expansion success-path smoke in the supported runtime
   shape, not only failure-policy checks.
4. Complete release validation evidence for the distributable artifacts.
5. A dated pass record linking the evidence back to every criterion in
   `docs/kg_quarantine_exit_gate.md`.

Until then, search and KG-backed runtime expansion should remain implemented,
locally testable, and explicitly quarantined.
