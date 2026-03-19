# Search/KG Quarantine Review

Decision date: March 19, 2026

Recommendation: `Keep Quarantined`

Inputs:

- `docs/RunPass9.md`
- `docs/kg_quarantine_exit_gate.md`
- `docs/kg_unquarantine_plan.md`
- `docs/capability_graduation_boundaries.md`
- `dist/search_kg_evidence/search_kg_evidence_bundle.json`
- `dist/search_kg_evidence/search_kg_evidence_bundle.md`

## Scope

This review covers only the quarantined runtime surfaces named by the existing
gate:

- `/v1/search`
- text-index-backed Fuseki search
- KG expansion used as a runtime dependency

It does not change support status by itself.

## Current capability snapshot

- `api.search`: `quarantined`
- `kg.expansion`: `quarantined`

That snapshot still matches the machine-readable capability registry and the
current operator baseline.

## Fresh evidence used for this review

The Step 5.3 bundle was produced from current workspace artifacts on March 19,
2026 and captures:

- capability state from `service/docs/capability_registry.json`
- optional runtime smoke proving search default-off, search opt-in, search
  rollback, and KG failure-policy behavior
- installed runtime smoke proving the release-shaped runtime contract still
  reports search and KG expansion as `quarantined`
- current release validation evidence status

## Why the recommendation remains Keep Quarantined

The fresh bundle improves evidence quality, but it does not satisfy the
quarantine exit gate end to end. The specific blockers remain:

1. No operator-owned text-index-enabled Fuseki provisioning and rollback proof
   is attached for `/v1/search`.
2. No production-like smoke artifact is attached for `/v1/search` against a
   real text-index-backed Fuseki runtime path.
3. No production-like smoke artifact is attached for KG expansion success
   through the supported runtime shape.
4. The release validation evidence in this workspace remains incomplete for the
   full distributable-artifact publication gate.
5. There is still no dated pass record showing that exit-gate criteria 1
   through 7 are all satisfied with current evidence.

## Practical conclusion

The repo is in the correct posture:

- search and KG-backed runtime behavior remain implemented and locally
  testable
- optional smoke now provides a cleaner evidence input for future review
- the operator baseline still correctly excludes these surfaces

Within RunPass9 scope, the right decision is still `Keep Quarantined`.
