# Local-Adapter Production-Beta Scope Decision

Date: March 25, 2026

Status: active decision for the current production-beta target.
Reactivation note: `docs/local_adapter_reactivation_2026-03-27.md` reopens the
track for bounded candidate work under ExecutionPlan11.5 Step 6.1, but it does
not promote the capability or add local-adapter obligations to the supported
baseline release path.

Use this document together with:

- `docs/Archive/RunPass11.md`
- `docs/answer_generation_posture.md`
- `docs/local_adapter_release_evidence.md`
- `docs/model_training_surface_adr.md`
- `docs/production_candidate_benchmark_plan.md`

## Decision

The local-adapter track is formally deprioritized for the current
production-beta target.

The runtime path remains implemented and gated as `Optional`, but maintainers
should not treat it as near-term release or promotion work. Release, operator,
and answer-generation decisions for the supported Windows single-host baseline
should proceed without assuming a local-adapter candidate will be made
reviewable in this phase.

## Why

The current repository evidence does not support a credible near-term promotion
story:

- the reviewed candidate under
  `dist/training/step52-real-candidate-gpt2b-20260319/` uses
  `hf-internal-testing/tiny-random-gpt2`, not the planning-only future target
  `Qwen/Qwen2.5-7B-Instruct`
- `kg/reports/local-adapter-smoke.json` records `status=failed` with
  `disabled_reason = "Retriever not ready"`
- the paired benchmark bundle under
  `dist/benchmarks/step52-real-candidate-gpt2b-20260319/` was run against
  `http://127.0.0.1:9`, so it is not release-review evidence for a real hosted
  runtime
- `dist/training/step52-real-candidate-gpt2b-20260319/release_evidence_manifest.json`
  records `decision = "keep_optional"` and `candidate_review_status =
  "not_reviewable"`
- the same manifest records zero answer accuracy, zero label accuracy, zero
  unanswerable accuracy, and a strict-output failure rate of `1.0`

This is enough evidence to keep the capability optional and explicitly out of
scope for the current production-beta push. It is not enough evidence to claim
that the smallest missing step is a minor workflow cleanup.

## Consequences

- Keep `runtime.local_adapter_serving` in the capability registry as
  `optional`, not `supported`.
- Keep the evidence validator, bundle builder, and smoke scripts in the repo so
  future work has a machine-checkable restart point.
- Do not include local-adapter promotion work in the normal production-beta
  release checklist.
- Do not describe the current track as a production candidate, release
  candidate, or active promotion item.
- Treat `docs/production_candidate_benchmark_plan.md` as a retained resumption
  plan, not active release work.

## What would reopen the track

Resume local-adapter promotion work only after a new dated decision explicitly
re-activates it and all of the following are true:

- a non-placeholder Task 5.3 run artifact exists for the intended model family
- `scripts/local_adapter_smoke.ps1` passes against a real hosted
  `/v1/rag/answer` runtime with the retriever ready
- `scripts/eval/run_local_adapter_benchmark.py` is run against that real host,
  not a dummy endpoint
- `scripts/eval/validate_local_adapter_release_bundle.py` returns
  `ready_for_formal_promotion_review`
- the answer-generation posture in `docs/answer_generation_posture.md` still
  supports the narrower advisory-only claim

## Scope summary

- `Supported now`: baseline retrieval, API, release, and operator work without
  local-adapter promotion
- `Implemented but out of scope`: optional local-adapter runtime and its
  evidence workflow
- `Not supported`: any claim that local-adapter is near-production for the
  current production-beta target
