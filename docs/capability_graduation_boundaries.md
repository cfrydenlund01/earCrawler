# Capability Graduation Boundaries

Status: active capability-state policy for Pass 8. This document replaces the
older bundled "KG-backed hybrid retrieval" framing with four separately tracked
capabilities. It does not promote or unquarantine any feature by itself.
Machine-readable current-state data lives in
`service/docs/capability_registry.json` and is published in
`docs/api/capability_registry.json`.

Use this document together with:

- `README.md`
- `RUNBOOK.md`
- `docs/kg_quarantine_exit_gate.md`
- `docs/kg_unquarantine_plan.md`
- `docs/hybrid_retrieval_design.md`
- `docs/model_training_surface_adr.md`
- `docs/local_adapter_release_evidence.md`
- `docs/answer_generation_posture.md`
- `docs/local_adapter_deprioritization_2026-03-25.md`
- `docs/ops/windows_single_host_operator.md`

## Status vocabulary

Use one vocabulary set across the repo:

- `Supported`: part of the baseline supported runtime or operator contract
- `Optional`: implemented and maintained, but explicit opt-in and not baseline
- `Quarantined`: intentionally kept out of the supported baseline until named
  evidence and operator proof exist
- `Legacy`: retained compatibility or historical code/module surface that is not
  a current supported entrypoint
- `Generated`: build, release, or local runtime output; never authored source
- `Archival`: historical review or planning material retained for reference
- `Proposal-only`: planning or research material that is not a runtime/operator
  contract by itself

Practical scope:

- the runtime capability registry is authoritative for runtime-facing states and
  currently uses `supported`, `optional`, `quarantined`, `legacy`,
  `generated`, and `archival`
- `Proposal-only` is a repo/documentation category for planning and research
  material such as `Research/` and `docs/proposal/`
- workspace-only residue such as ghost directories is not a capability state at
  all; treat it as unsupported local leftover state and classify it with
  `scripts/workspace-state.ps1`

## State summary

| Capability | Current state | Default posture | Runtime gate | Next promotion target |
| --- | --- | --- | --- | --- |
| Text search (`/v1/search`, text-index-backed Fuseki search) | `Quarantined` | Disabled by default and excluded from default API contract artifacts | `EARCRAWLER_API_ENABLE_SEARCH=1` | `Optional` |
| Hybrid ranking (dense + BM25 fusion only) | `Optional` | Dense remains the baseline retrieval mode | `EARCRAWLER_RETRIEVAL_MODE=hybrid` | `Supported` |
| KG expansion | `Quarantined` | Disabled by default | `EARCRAWLER_ENABLE_KG_EXPANSION=1` plus provider settings | `Optional` |
| Local-adapter serving (`LLM_PROVIDER=local_adapter`) | `Optional` | Off unless a recorded adapter artifact is supplied | `LLM_PROVIDER=local_adapter`, `EARCRAWLER_ENABLE_LOCAL_LLM=1`, and local-model env vars | Deferred for current production-beta target |

## 1. Text search

Current state: `Quarantined`.

Why:

- the route is hard-disabled by default
- default OpenAPI, Postman, and client artifacts exclude it
- the operator-facing text-index provisioning and rollback story is still not
  release-shaped

Current operator control:

- local validation only: set `EARCRAWLER_API_ENABLE_SEARCH=1`

Current planning rule:

- keep the capability state as `Quarantined`
- do not treat promotion of text search as active near-term work for the
  current production-beta target
- maintain only the explicit gate, default-contract exclusion, rollback-safe
  smoke coverage, and operator rollback notes until a later dated decision
  re-opens promotion work
- use `docs/search_kg_capability_decision_2026-03-27.md` as the current dated
  capability decision and
  `docs/search_kg_quarantine_decision_package_2026-03-19.md` as supporting
  evidence history for this posture

Promotion from `Quarantined` to `Optional` requires all of the following:

- keep the runtime gate explicit and default-off
- prove a wheel-based or installed-service workflow for text-index-enabled
  Fuseki setup without a source checkout
- add release-gated smoke coverage that exercises `/v1/search` in the same
  runtime shape operators will use
- define rollback as "disable the gate, restart the service, and return to the
  contract artifacts that exclude the route"
- add operator docs for enablement, health checks, failure handling, and
  rollback in `docs/ops/windows_single_host_operator.md`
- keep `scripts/optional-runtime-smoke.ps1` passing for search default/off -> on
  -> off behavior in release-shaped runs

Promotion from `Optional` to `Supported` additionally requires:

- default API contract artifacts to include `/v1/search`
- supported-path smoke and release validation to treat the route as baseline,
  not an add-on
- a dated decision record naming the route as part of the supported API surface

## 2. Hybrid ranking

Current state: `Optional`.

Scope note: this means dense + BM25 reciprocal-rank fusion only. It does not
include live KG expansion and does not require text-index-backed Fuseki.

Why:

- it is explicit opt-in and defaults to `dense`
- it uses the same retrieval metadata/index assets as dense mode rather than a
  separate packaged lexical index
- the API and pipeline now share the same RAG orchestration path, so the mode
  is one operator-visible retrieval toggle rather than a separate code path

Current operator control:

- enable by setting `EARCRAWLER_RETRIEVAL_MODE=hybrid`
- roll back by restoring `EARCRAWLER_RETRIEVAL_MODE=dense` (or unsetting the
  variable) and restarting the service

Promotion from `Optional` to `Supported` requires all of the following:

- keep dense as the rollback-safe baseline until release-shaped evidence shows
  hybrid is equally operable
- prove installed-service parity for `dense` and `hybrid` without any extra
  repo-relative assets
- add release-gated smoke that exercises RAG with `EARCRAWLER_RETRIEVAL_MODE=hybrid`
- document enable/disable and rollback steps in the Windows operator guide
- record failure expectations: hybrid must degrade by switching back to dense,
  not by silently changing retrieval behavior

## 3. KG expansion

Current state: `Quarantined`.

Why:

- it adds a live provider dependency and explicit failure-policy choices
- the packaged SPARQL template/resource proof now exists, but release-shaped
  operator proof for the live runtime is still incomplete
- the support boundary is still narrower and safer when RAG does not require KG
  expansion

Current operator control:

- local validation only: set `EARCRAWLER_ENABLE_KG_EXPANSION=1` plus the
  provider-specific environment variables

Current planning rule:

- keep the capability state as `Quarantined`
- do not treat promotion of KG expansion as active near-term work for the
  current production-beta target
- maintain only the explicit gate, failure-policy checks, rollback notes, and
  quarantine-aligned operator docs until a later dated decision re-opens
  promotion work
- use `docs/search_kg_capability_decision_2026-03-27.md` as the current dated
  capability decision and
  `docs/search_kg_quarantine_decision_package_2026-03-19.md` as supporting
  evidence history for this posture

Promotion from `Quarantined` to `Optional` requires all of the following:

- keep the runtime gate explicit and default-off
- prove packaged resource correctness for the selected provider path
- add release-gated smoke for both the configured success path and the declared
  failure policy (`error` or `disable`)
- define rollback as "disable KG expansion and return to retrieval-only RAG"
- add operator docs covering provider selection, health checks, latency/failure
  behavior, and rollback
- keep `scripts/optional-runtime-smoke.ps1` passing for KG expansion
  failure-policy checks (`disable` and `error`)

Promotion from `Optional` to `Supported` additionally requires:

- a decision that KG expansion is part of the baseline supported RAG contract
- baseline smoke and release validation to cover KG expansion continuously
- a dated decision record linking the exact supported provider/runtime shape

## 4. Local-adapter serving

Current state: `Optional`.

Why:

- it is explicitly gated and does not affect the baseline retrieval-only or
  remote-provider runtime
- the runtime already validates adapter artifacts and preserves the same output
  schema and refusal controls
- release readiness still depends on artifact-backed evidence rather than the
  feature simply existing in source
- even a promoted adapter candidate would still need to respect the advisory
  and human-review boundary in `docs/answer_generation_posture.md`
- the track is formally deprioritized for the current production-beta target by
  `docs/local_adapter_deprioritization_2026-03-25.md`

Current operator control:

- enable by setting:
  - `LLM_PROVIDER=local_adapter`
  - `EARCRAWLER_ENABLE_LOCAL_LLM=1`
  - `EARCRAWLER_LOCAL_LLM_BASE_MODEL=<base-model>`
  - `EARCRAWLER_LOCAL_LLM_ADAPTER_DIR=<run-dir>/adapter`
  - `EARCRAWLER_LOCAL_LLM_MODEL_ID=<run-id>`
- validate with `scripts/local_adapter_smoke.ps1 -RunDir <run-dir>`
- roll back by unsetting the local-adapter env vars (or restoring remote-deny
  posture) and restarting the service

Current planning rule:

- keep the capability state as `Optional`
- do not treat promotion to `Supported` as active near-term work for the
  current production-beta target
- resume promotion work only after a later dated decision explicitly re-opens
  the track

Promotion from `Optional` to `Supported` requires all of the following:

- a passing evidence bundle defined in `docs/local_adapter_release_evidence.md`
  and validated against `config/local_adapter_release_evidence.example.json`
- release-gated smoke for the installed-service runtime using that artifact
- operator docs for artifact placement, health verification, rollback, and
  troubleshooting
- a passing `scripts/optional-runtime-smoke.ps1 -LocalAdapterRunDir <run_dir>`
  report archived with release evidence
- a dated decision record stating whether support remains artifact-by-artifact
  optional or becomes part of the baseline supported deployment
- a dated decision record stating whether the capability remains limited to
  advisory answer drafting or has some narrower explicitly approved production
  use beyond that baseline

Exact evidence decision rule:

- keep the capability `Optional` when the evidence bundle is incomplete or not
  machine-checkable, including missing archived benchmark smoke preconditions
- treat a candidate as `Rejected` when the bundle is complete but runtime smoke,
  benchmark smoke, thresholds, or retrieval-only comparison rules fail
- treat the capability as `Ready for formal promotion review` only when the
  full evidence bundle passes; this still does not auto-promote the capability

## Governing split

Use these rules to avoid future drift:

- `docs/kg_quarantine_exit_gate.md` and `docs/kg_unquarantine_plan.md` govern
  only search/KG-dependent runtime behavior.
- `docs/hybrid_retrieval_design.md` governs dense + BM25 hybrid ranking.
- `docs/model_training_surface_adr.md` and the local-adapter runtime docs
  govern adapter-backed serving.
- `docs/answer_generation_posture.md` governs what answer-generation behavior is
  supportable for production beta, including abstention and human-review
  boundaries.
- `README.md` remains the canonical public capability matrix.
- `docs/repository_status_index.md` is the canonical repo-surface map for
  `Supported`, `Optional`, `Quarantined`, `Legacy`, `Generated`, `Archival`,
  and `Proposal-only`.
