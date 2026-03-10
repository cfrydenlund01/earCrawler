# KG-Backed Search Status Decision

Decision date: March 10, 2026

Decision: keep KG-backed search `Quarantined`.

Scope:

- `/v1/search`
- text-index-backed Fuseki search
- any operator/runtime claim that treats KG-backed search as part of the supported production path

## Decision

Task 2.2 of the Pass 6 execution plan is resolved as `No-Go for graduation`.

KG-backed search does not graduate in Phase 2 at this point. The supported production/runtime boundary remains:

- `earctl` / `py -m earCrawler.cli ...`
- `service.api_server`

Within that boundary, the supported API routes remain:

- `/health`
- `/v1/entities/{entity_id}`
- `/v1/lineage/{entity_id}`
- `/v1/sparql`
- `/v1/rag/query`

`/v1/search` remains implemented for local validation and research workflows, but it is not part of the supported production contract.

## Why the decision is to keep it quarantined

The Pass 6 plan says to keep KG-backed search quarantined until Tasks 1.1 through 2.1 are complete and stable, then graduate it only if the supported gate proves the real path cleanly.

That clean graduation proof is still incomplete for KG-backed search specifically. The repo has the broad supported gate in place, but this decision record treats the following as still required before graduation:

1. Current dated evidence, not just file presence, that the supported corpus -> KG -> SHACL -> API smoke -> no-network RAG path is green and stable.
2. Production-like smoke coverage for the actual KG-backed search surface being claimed as supported, not only general API smoke or local validation behavior.
3. Release-gated tests for every KG-backed search capability that would move into the supported operator contract.
4. Operator docs that explain install, health, failure handling, and rollback for the exact KG-backed search surface under consideration.
5. A fresh go/no-go review showing the exit gate in `docs/kg_quarantine_exit_gate.md` is passed with current evidence.

Until those are complete, graduating KG-backed search would widen the support contract faster than the evidence supports.

## Effect on Phase 2 continuity

This decision keeps continuity with the rest of Phase 2:

- Task 2.1 created the unquarantine checklist in `docs/kg_unquarantine_plan.md`.
- Task 2.2 now records the product decision explicitly: keep KG-backed search quarantined.
- Tasks 2.3 and 2.4 remain blocked unless a later decision reverses this one with new evidence.

## Revisit conditions

Revisit this decision only when all of the following are true:

- the supported gate is passing on current code and current release candidate inputs
- KG-backed search has production-like smoke coverage in the supported runtime shape
- the operator story is documented end to end
- the evidence package required by `docs/kg_unquarantine_plan.md` is complete

Until then, docs, code comments, and operational guidance should continue to describe KG-backed search as `Quarantined`.
