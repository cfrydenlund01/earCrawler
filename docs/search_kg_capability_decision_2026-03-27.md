# Search And KG Capability Decision

Decision date: March 27, 2026

Outcome: `Keep Quarantined`

Scope:

- `api.search`:
  - `/v1/search`
  - text-index-backed Fuseki search
- `kg.expansion`:
  - KG expansion during RAG behind `EARCRAWLER_ENABLE_KG_EXPANSION=1`

## Decision

The Step 5.3 decision is to keep the scoped KG-backed runtime features
quarantined.

Capability state after this decision:

- `api.search`: `quarantined`
- `kg.expansion`: `quarantined`

The supported Windows single-host production-beta baseline remains unchanged:

- supported API surface:
  - `/health`
  - `/v1/entities/{entity_id}`
  - `/v1/lineage/{entity_id}`
  - `/v1/sparql`
  - `/v1/rag/query`
- `/v1/search` remains excluded from the default supported API contract
- KG expansion remains default-off and is not part of the supported RAG
  baseline

## Current evidence reviewed

- `dist/search_kg_evidence/search_kg_evidence_bundle.json`
- `dist/search_kg_evidence/search_kg_evidence_bundle.md`
- `dist/search_kg_evidence/search_kg_prodlike_smoke.json`
- `dist/optional_runtime_smoke.json`
- `dist/installed_runtime_smoke.json`
- `dist/release_validation_evidence.json`
- `dist/kg_query_results.json`
- `docs/ops/windows_single_host_operator.md`
- `docs/ops/windows_fuseki_operator.md`
- `docs/kg_quarantine_exit_gate.md`
- `docs/kg_unquarantine_plan.md`

## Why the result is still `Keep Quarantined`

The current evidence is materially stronger than the March 19 package:

- the real corpus -> KG emit -> validate chain is passing
- the local TDB2/Fuseki load -> serve -> query path is passing
- operator-owned text-index validation and production-like `/v1/search` plus KG
  expansion smoke now exist and pass
- rollback and failure-policy behavior are documented and exercised

That is enough to support a real Step 5.3 decision. It is not enough to record
an exit-gate pass.

The blocking gap is still exit-gate criterion 3, clean-room packaging and
install proof, for the scoped promoted features themselves:

- `dist/installed_runtime_smoke.json` and
  `dist/release_validation_evidence.json` currently prove the supported
  installed release shape with `api.search = quarantined` and
  `kg.expansion = quarantined`
- the passing search/KG success-path proof is assembled through repo-local
  validation scripts and a temporary text-index validation runtime, not through
  an installed wheel/service workflow that is already part of the signed
  release contract
- the operator docs correctly describe the text-index path as validation-only,
  not as a graduated deployed-host capability

Because the exit gate is binary, that remaining gap keeps the gate unpassed.

## Exit-gate assessment

| Criterion | Assessment |
| --- | --- |
| 1. Runtime boundary is explicit and singular | Passed |
| 2. KG correctness prerequisites are already met | Passed |
| 3. Clean-room packaging and install work | Not yet passed for the scoped search/KG success path |
| 4. End-to-end tests cover the real claimed runtime | Passed for promotion review, but still tied to validation-only workflow |
| 5. Operator readiness exists in the runbook | Passed for validation and rollback; not yet a graduated deployed-host contract |
| 6. Failure behavior is defined and conservative | Passed |
| 7. The unquarantine decision is recorded | This document records the no-go outcome |

Final gate result: `Fail`.

## Rollback ownership

Rollback owner: the Windows single-host release operator for the host where
search/KG validation was enabled.

Rollback action if the validation path is active:

1. Set `EARCRAWLER_API_ENABLE_SEARCH=0`.
2. Set `EARCRAWLER_ENABLE_KG_EXPANSION=0`.
3. Restore dense retrieval as the baseline mode.
4. Re-render or reinstall the baseline Fuseki config without
   `-EnableTextIndexValidation`.
5. Restart Fuseki, then restart the EarCrawler API service.
6. Re-run `/health` and `scripts/optional-runtime-smoke.ps1` to confirm the
   baseline capability snapshot is back to `quarantined`.

The authoritative rollback instructions remain:

- `docs/ops/windows_single_host_operator.md`
- `docs/ops/windows_fuseki_operator.md`

## What changed relative to March 19

The current no-go is narrower and more evidence-backed than the March 19
package:

- earlier blockers around operator-owned text-index validation and
  production-like smoke are now closed
- the remaining blocker is no longer "missing runtime proof"; it is "missing
  clean-room graduated install proof inside the signed release contract"

This means the next reconsideration should not start from scratch. It should
start by deciding whether the repo will actually carry installed-artifact
support obligations for these features. Until that proof exists, the correct
decision is still `Keep Quarantined`.
