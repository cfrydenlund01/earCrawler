# Local-Adapter Track Reactivation Note

Date: March 27, 2026

Status: active Step 6.1 note for `docs/ExecutionPlan11.5.md`

## Decision

Reactivate the local-adapter track for real candidate work under Phases 6
through 8.

This reactivation is operational, not promotional.

What it does mean:

- proceed with Step 6.2 and later training-candidate preparation work
- use the current Phase 3 artifact index and training contract as the only
  authoritative training input path
- treat the work as optional-candidate evidence generation, not baseline
  release work

What it does not mean:

- `runtime.local_adapter_serving` is still `optional`, not `supported`
- the supported Windows single-host production-beta baseline is unchanged
- the normal release checklist does not gain local-adapter obligations
- no answer-generation claim is widened beyond the existing advisory-only
  posture

## Why the baseline is now stable enough

The repository baseline is now stable enough that local-adapter candidate work
is no longer building on untrustworthy release or runtime facts.

Current baseline evidence from Phases 1 through 5:

- release trust restored:
  - `scripts/release-evidence-preflight.ps1 -AllowEmptyDist` passes
  - `scripts/verify-release.ps1 -RequireCompleteEvidence` passes
- supported host/runtime proof restored:
  - `scripts/bootstrap-verify.ps1` passes on the active host
  - installed runtime smoke, supported API smoke, optional runtime smoke, and
    observability probe are all passing
- authoritative corpus and snapshot chain refreshed:
  - live corpus build, validation, and snapshot recording are complete
- KG technical/runtime proof completed:
  - current corpus -> KG emit/validate passes
  - local TDB2/Fuseki load -> serve -> query proof passes
- KG support-boundary decision is current:
  - `docs/search_kg_capability_decision_2026-03-27.md` keeps search/KG runtime
    features quarantined, so model work is not waiting on KG promotion
- baseline verification blocker closed:
  - `py -3 -m pytest -q` now passes (`532 passed, 7 skipped`)

This is the threshold Step 6.1 needed. The repo can now test whether a real
local-adapter candidate is reviewable without conflating that work with the
baseline release decision.

## Operational guardrails

- Use `google/gemma-4-E4B-it` as the intended base model for the first real
  candidate.
- Keep training inputs pinned to the approved snapshot and retrieval-corpus
  chain recorded in the current Phase 3 artifact index.
- Keep KG runtime promotion out of scope; `docs/model_training_contract.md`
  already defines KG as optional metadata for this first pass, not a hard
  prerequisite.
- If Step 6.2 config preparation or Step 6.3 prepare-only packaging fails,
  stop and fix that evidence path before any full training run.
- Even with a successful candidate, a later dated decision is still required
  before any capability or answer-posture promotion.

## Immediate next step

Proceed to Step 6.2 only.

