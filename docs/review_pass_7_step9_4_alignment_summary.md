# Review Pass 7 Step 9.4 Alignment Summary

Prepared: March 12, 2026

Decision applied: [`docs/review_pass_7_step9_3_decision_memo.md`](review_pass_7_step9_3_decision_memo.md)

Outcome: `/v1/search` and KG-backed hybrid retrieval remain deferred/quarantined for this release cycle, and default support-path docs/checks now avoid implying supported status.

## Updated docs and gating/config surfaces

- [`scripts/health/api-probe.ps1`](../scripts/health/api-probe.ps1)
  - Default probe now validates supported `/health` only.
  - Quarantined `/v1/search` probing is explicit opt-in via `-IncludeQuarantinedSearch`.
- [`canary/config.yml`](../canary/config.yml)
  - Removed default `/v1/search` API canary check so default canaries track supported routes only.
- [`scripts/api/curl_facade.ps1`](../scripts/api/curl_facade.ps1)
  - Default call set now stays on supported routes.
  - Quarantined `/v1/search` call is explicit opt-in via `-IncludeQuarantinedSearch`.
  - Default entity selection no longer depends on search auto-discovery.
  - SPARQL sample now uses `entity_by_id` instead of search-coupled template usage.
- [`docs/api/readme.md`](api/readme.md)
  - Updated `curl_facade.ps1` usage and behavior description to reflect supported-by-default flow.
  - Clarified that `search_query` is for optional quarantined flow only.
- [`docs/ops/observability.md`](ops/observability.md)
  - Updated probe/canary language to match the supported-by-default, quarantined-opt-in posture.
- [`.env.example`](../.env.example)
  - Clarified `EAR_SEARCH_QUERY` is only for opt-in quarantined search checks.
  - Clarified deterministic default entity ID behavior.
- [`README.md`](../README.md)
  - Capability matrix now references both the Task 2.2 no-go and Pass 7 Step 9.3 deferral memo.
  - Observability note now states default canary API checks stay on supported routes.
- [`RUNBOOK.md`](../RUNBOOK.md)
  - Quarantine decision line now references both the Task 2.2 decision and Pass 7 Step 9.3 reaffirmation.
- [`docs/kg_quarantine_exit_gate.md`](kg_quarantine_exit_gate.md)
  - Updated top-level status date and decision-record references to include Pass 7 Step 9.3.
- [`docs/kg_unquarantine_plan.md`](kg_unquarantine_plan.md)
  - Updated current-conclusion note to include Pass 7 Step 9.3 reaffirmation.

## Resulting boundary posture

- Supported-path defaults no longer depend on `/v1/search`.
- Quarantined search remains available for local validation, but only through explicit operator intent.
- Quarantine governance docs and capability matrix references are aligned with the latest deferral decision.
