# KG Unquarantine Plan

Status: planning and checklist document for Phase 2 Task 2.1. This document does not unquarantine any feature by itself.

As of March 9, 2026, KG-backed runtime behavior remains `Quarantined`. The current normative go/no-go gate is [docs/kg_quarantine_exit_gate.md](kg_quarantine_exit_gate.md). This plan translates that gate plus the Pass 6 execution analysis into a concrete preconditions and evidence checklist for any future graduation decision.

## Scope

This plan applies to any change that would move any of the following from `Quarantined` to `Supported`:

- `/v1/search`
- text-index-backed Fuseki search
- `kg-load`
- `kg-serve`
- `kg-query`
- KG expansion used as a supported runtime dependency
- any retrieval/runtime feature that requires live KG-backed behavior as part
  of its support claim

This plan does not govern:

- dense + BM25 hybrid ranking selected by `EARCRAWLER_RETRIEVAL_MODE=hybrid`
- local-adapter serving selected by `LLM_PROVIDER=local_adapter`

Those capability tracks are defined in
`docs/capability_graduation_boundaries.md`.

Task 2.2 remains a separate decision. This document only defines what must be true before that decision can be made safely.

## Decision posture

Default posture: keep KG-backed runtime features quarantined until every precondition below is satisfied with current evidence.

The analysis-driven reason is simple:

- the supported runtime surface is intentionally narrow: `earctl` plus `service.api_server`
- the repo must prove the real corpus -> KG -> validation -> API -> offline RAG path
- operator docs must make the support boundary explicit before any KG-backed runtime claim is expanded

## Preconditions

All preconditions are mandatory.

| ID | Preconditions before any unquarantine decision | Current repo evidence | Status to record |
| --- | --- | --- | --- |
| P1 | Supported capability matrix is unified across repo docs. | [README.md](../README.md), [RUNBOOK.md](../RUNBOOK.md), [docs/api/readme.md](api/readme.md), [service/docs/index.md](../service/docs/index.md), [service/openapi/openapi.yaml](../service/openapi/openapi.yaml) all mark `/v1/search` as `Quarantined`. | Implemented in repo; re-verify before decision |
| P2 | The real supported corpus -> KG CI gate exists. | [.github/workflows/ci.yml](../.github/workflows/ci.yml) runs `corpus build`, `corpus validate`, `kg-emit`, KG semantic gate (SHACL + selected SPARQL blocking checks), API smoke, and no-network RAG smoke. [docs/ci.md](ci.md) documents the same order. | Implemented in repo; requires latest green run evidence |
| P3 | SHACL plus selected semantic validation are part of the supported path. | [.github/workflows/ci.yml](../.github/workflows/ci.yml) includes the `Supported KG semantic gate`. [docs/kg_semantic_blocking_checks.md](kg_semantic_blocking_checks.md) records the release-blocking SPARQL checks and rationale. | Implemented in repo; requires latest green run evidence |
| P4 | Supported API smoke and no-network RAG smoke are stable. | [.github/workflows/ci.yml](../.github/workflows/ci.yml), [README.md](../README.md), [RUNBOOK.md](../RUNBOOK.md), and [tests/golden/test_phase2_golden_gate.py](../tests/golden/test_phase2_golden_gate.py). | Implemented in repo; stability must be demonstrated from recent CI history, not inferred from file presence |
| P5 | Operator docs clearly distinguish supported vs optional KG behavior. | [README.md](../README.md), [RUNBOOK.md](../RUNBOOK.md), [docs/runtime_research_boundary.md](runtime_research_boundary.md), and [docs/kg_quarantine_exit_gate.md](kg_quarantine_exit_gate.md). | Implemented in repo; re-verify after any graduation edits |

Preconditions above are the minimum required by the Pass 6 analysis. They are not sufficient on their own to graduate KG. The exit gate in [docs/kg_quarantine_exit_gate.md](kg_quarantine_exit_gate.md) still applies in full.

## Evidence required for a graduation decision

The approver package for Task 2.2 should contain all of the following:

1. A dated capability snapshot showing the exact surfaces proposed to move from `Quarantined` to `Supported`.
2. A green run of the supported CI path proving:
   - `corpus build`
   - `corpus validate`
   - `kg-emit`
   - SHACL + supported blocking semantic checks
   - supported API smoke
   - no-network RAG smoke
3. Evidence that the claimed KG-backed runtime behavior works through supported entrypoints only:
   - `earctl` or `py -m earCrawler.cli ...`
   - `service.api_server`
4. A production-like smoke run against the actual claimed KG-backed surface, not only stubs.
5. Operator-facing instructions for install, configuration, health checks, shutdown, troubleshooting, and rollback for the exact graduated feature set.
6. Failure-mode evidence showing what happens when Fuseki, graph validation, or KG-backed retrieval dependencies fail.
7. A dated decision record naming:
   - the exact features graduating
   - the evidence links
   - the approver
   - the rollback owner

## Pre-graduation checklist

Use this checklist immediately before Task 2.2:

- Confirm the capability matrix still matches the code and operator docs.
- Confirm the latest `main` or release-candidate CI run passed the supported evidence path without manual exceptions.
- Confirm `/v1/search` and any other target feature have explicit tests for the runtime shape operators will use.
- Confirm no doc still implies that legacy services are supported deployment paths.
- Confirm the supported failure mode is documented and tested.
- Confirm the release artifact or installation path required by operators does not depend on a source checkout.
- Confirm the exact supported scope is narrow and enumerated; do not graduate vague "KG support" as a bundle.

If any checklist item fails, the unquarantine decision is `No-Go`.

## Post-graduation obligations

If any KG-backed runtime surface is graduated, all of the following become mandatory release obligations:

1. Update the canonical capability matrix in [README.md](../README.md).
2. Update [RUNBOOK.md](../RUNBOOK.md) with install, run, health, shutdown, troubleshooting, and rollback steps for the graduated KG path.
3. Update API-facing docs in [docs/api/readme.md](api/readme.md), [service/docs/index.md](../service/docs/index.md), [service/openapi/openapi.yaml](../service/openapi/openapi.yaml), and generated OpenAPI artifacts.
4. Add or retain release-gated tests for every newly supported KG-backed route or command.
5. Record the graduation decision in a dated ADR, release note, or equivalent decision log.
6. State explicitly whether support remains single-host only. Do not imply multi-instance correctness unless separately implemented and documented.
7. Define owner-facing observability for the graduated feature: health checks, logs, expected failure signatures, and alert thresholds where applicable.

## Rollback conditions

Any graduated KG-backed feature should be re-quarantined if one or more of the following occurs:

- the supported CI path stops proving the real corpus -> KG -> SHACL -> API -> no-network RAG chain
- a supported KG-backed route or command requires a source checkout, hidden script, or undocumented operator knowledge
- operator docs drift and no longer match the implemented behavior
- failure behavior becomes ambiguous, silent, or routes through unsupported fallbacks
- the production-like KG smoke test becomes flaky or cannot be run in release validation
- lineage, identifier, namespace, or provenance regressions appear in supported KG-backed behavior

## Rollback actions

If rollback is triggered:

1. Change the affected surface back to `Quarantined` in the canonical capability matrix and all mirrored docs.
2. Remove any production-support language for that feature from operator docs and API docs.
3. Restore the previous signed release artifact or prior stable tag using the rollback path in [RUNBOOK.md](../RUNBOOK.md).
4. Record the rollback date, trigger, impacted features, and required corrective work.
5. Do not re-graduate the feature until the failure cause has a new evidence package and a fresh decision record.

## Record template

Use this minimal record when Task 2.2 is executed:

| Field | Value |
| --- | --- |
| Decision date |  |
| Decision | `Graduate` or `Keep Quarantined` |
| Features in scope |  |
| Preconditions P1-P5 satisfied | Yes / No |
| Exit gate evidence attached | Yes / No |
| Approver |  |
| Rollback owner |  |
| Notes |  |

## Current conclusion

Current conclusion: the repo has a concrete KG unquarantine checklist and
explicit no-go/current-boundary records. See
`docs/kg_search_status_decision_2026-03-10.md` (Task 2.2 no-go),
`docs/search_kg_quarantine_decision_package_2026-03-19.md` (March evidence
package), and `docs/search_kg_capability_decision_2026-03-27.md` (Step 5.3
decision: keep quarantined). Search- and KG-dependent runtime behavior remains
`Quarantined` unless a later decision is backed by a fresh evidence package and
an exit-gate pass record.
