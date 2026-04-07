# Local-Adapter Capability Decision

Decision date: April 6, 2026

Outcome: `Remain Optional`

Scope:

- `runtime.local_adapter_serving`
- `/v1/rag/answer` when operated with:
  - `LLM_PROVIDER=local_adapter`
  - `EARCRAWLER_ENABLE_LOCAL_LLM=1`
  - a named `dist/training/<run_id>/adapter` artifact

## Decision

The Step 8.1 decision is to keep local-adapter serving `Optional`.

Capability state after this decision:

- `runtime.local_adapter_serving`: `optional`
- `/v1/rag/answer`: remains `optional` and operator-controlled

The supported Windows single-host production-beta baseline is unchanged:

- baseline supported retrieval remains `/v1/rag/query`
- generated answers remain advisory-only and must preserve abstention-first
  behavior
- local-adapter serving remains default-off and outside the baseline release
  path

## Current evidence reviewed

- `dist/training/gemma4-e4b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1/release_evidence_manifest.json`
- `dist/benchmarks/benchmark_gemma4-e4b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1_primary/benchmark_summary.json`
- `dist/benchmarks/benchmark_gemma4-e4b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1_primary/benchmark_manifest.json`
- `kg/reports/local-adapter-smoke.json`
- `docs/local_adapter_release_evidence.md`
- `docs/answer_generation_posture.md`
- `docs/ops/windows_single_host_operator.md`

## Why the result is `Remain Optional`

The current candidate is reviewable, but it is rejected by the active evidence
contract rather than passing to formal promotion review.

Current reviewed result from
`dist/training/gemma4-e4b-ear-2026-04-01-snapshot-ecfr_current_20260210_1627_parts_736_740_742_744_746-v1/release_evidence_manifest.json`:

- `decision = "reject_candidate"`
- `candidate_review_status = "rejected"`
- `evidence_status = "complete"`

The reviewed bundle keeps local-adapter serving out of promotion review because
it misses multiple required thresholds:

- `local_adapter.answer_accuracy = 0.0000` against minimum `0.6500`
- `local_adapter.label_accuracy = 0.0909` against minimum `0.8000`
- `local_adapter.unanswerable_accuracy = 0.0909` against minimum `0.9000`
- `local_adapter.latency_ms.p95 = 20488.7375` against maximum `15000.0000`

The result is stronger than the earlier March placeholder state because the
candidate is now machine-checkably reviewable. It is not strong enough to move
the capability into formal promotion review.

## Operational consequence

- keep `runtime.local_adapter_serving` as `optional` in the capability registry
- keep `/v1/rag/answer` as an operator-controlled advisory draft path only
- do not add local-adapter obligations to the supported baseline release path
- keep the reviewed candidate as rejection evidence, not promotion evidence

## Rollback ownership

Rollback owner: the Windows single-host operator for the host where
local-adapter serving is enabled.

Rollback action if local-adapter validation is active:

1. Unset `LLM_PROVIDER`.
2. Unset `EARCRAWLER_ENABLE_LOCAL_LLM`.
3. Unset `EARCRAWLER_LOCAL_LLM_BASE_MODEL`.
4. Unset `EARCRAWLER_LOCAL_LLM_ADAPTER_DIR`.
5. Unset `EARCRAWLER_LOCAL_LLM_MODEL_ID`.
6. Restart the API service.
7. Re-run `/health` and the supported API smoke to confirm the host is back on
   the baseline non-local-adapter path.

The authoritative rollback references remain:

- `docs/local_adapter_release_evidence.md`
- `docs/ops/windows_single_host_operator.md`

## What would reopen promotion work

Promotion review should reopen only after a later candidate produces:

- `ready_for_formal_promotion_review` from
  `scripts.eval.validate_local_adapter_release_bundle`
- passing threshold results under
  `config/local_adapter_release_evidence.example.json`
- a passing optional-runtime smoke using `-LocalAdapterRunDir <run_dir>`
- a dated follow-on decision that explicitly revisits the advisory-only answer
  boundary

