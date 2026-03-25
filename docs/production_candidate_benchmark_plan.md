# Production Candidate Benchmark Plan (Task 6.1)

Prepared: March 11, 2026

Status: retained Phase 6 resumption plan. This defines how benchmarks should be
run against a real production candidate after Phase 5 if the local-adapter
track is re-activated. As of March 25, 2026, the track is formally
deprioritized for the current production-beta target by
`docs/local_adapter_deprioritization_2026-03-25.md`.

## Goal

Define the first benchmark plan for the production candidate model so evaluation
measures the actual Task 5.3 and Task 5.4 runtime path, not a placeholder or a
remote-only stand-in.

## Benchmark object under test

The benchmark target is the production candidate adapter produced by Task 5.3
and served through the supported optional `/v1/rag/answer` path introduced in
Task 5.4.

The benchmark subject is identified by:

- `dist/training/<run_id>/adapter/`
- `dist/training/<run_id>/manifest.json`
- `dist/training/<run_id>/run_metadata.json`
- `dist/training/<run_id>/inference_smoke.json`

Runtime mode for the benchmark:

- `LLM_PROVIDER=local_adapter`
- `EARCRAWLER_ENABLE_LOCAL_LLM=1`
- `EARCRAWLER_LOCAL_LLM_BASE_MODEL=<base-model-id>`
- `EARCRAWLER_LOCAL_LLM_ADAPTER_DIR=dist/training/<run_id>/adapter`

This keeps the benchmark tied to the supported serving path rather than to a
training script or notebook-only inference path.

## Entry criteria

Do not execute the benchmark plan until all of the following are true:

1. A concrete Task 5.3 run artifact exists under `dist/training/<run_id>/`.
2. `pwsh .\scripts\local_adapter_smoke.ps1 -RunDir dist/training/<run_id>`
   passes against `/v1/rag/answer`.
3. The supported retrieval/index path is ready for the same host:
   corpus, retriever config, and API service are all aligned to the supported
   single-host runtime.
4. `py -m eval.validate_datasets` passes for the committed eval manifest.

Current note for this checkout:

- a concrete `dist/training/<run_id>/` artifact does exist in the workspace,
  but the reviewed candidate is not a reviewable promotion bundle
- the recorded smoke failed (`Retriever not ready`)
- the paired benchmark evidence is not release-grade and does not reactivate
  this plan

## Primary benchmark suite

The first benchmark suite should stay inside the supported runtime boundary and
the approved eval/holdout assets.

Primary benchmark datasets:

- `ear_compliance.v2`
- `entity_obligations.v2`
- `unanswerable.v2`

These cover the three most important production-facing behaviors:

- grounded EAR compliance decisions
- entity-specific obligation decisions
- refusal behavior when evidence is missing or out of scope

## Secondary characterization suite

These datasets are useful for characterization and regression analysis but
should be reported separately from the primary release-style benchmark score.

Secondary datasets:

- `golden_phase2.v1`
- `golden_phase2.failure_modes.v1`

These are still valuable because they stress:

- citation precision
- ambiguity/refusal behavior
- adversarial citation rejection
- thin-retrieval behavior

## Deferred benchmark slices

The following slices should not be part of the initial primary benchmark report:

- `multihop_slice.v1`

Reason:

- it is more likely to be interpreted as a KG-linked or explainability-heavy
  research slice, and it should remain a secondary or deferred benchmark until
  the supported runtime story for those behaviors is explicitly settled

## Required metrics

Each primary benchmark run must report at least:

- overall answer accuracy
- label accuracy
- unanswerable accuracy
- `valid_citation_rate`
- `supported_rate`
- `overclaim_rate`
- strict-output failure count/rate
- provider/model/run identifier
- p50 and p95 request latency
- request failure rate (`422` and `503` tracked separately)

These metrics keep the benchmark grounded in the project’s evidence-first
contract instead of drifting into generic model quality scores.

## Comparison policy

The first benchmark report should compare the production candidate against:

1. Retrieval-only mode (`generate=0`) as the non-generative control.
2. The current approved remote-provider baseline, if a remote baseline is still
   useful for calibration.

Rules:

- the production candidate is the release candidate under judgment
- remote baselines are reference points, not the deployment target
- retrieval-only is a floor/control, not a competing product path

## Artifacts to keep

Each benchmark run should write a dedicated benchmark bundle under a distinct
output root such as `dist/benchmarks/<run_id>/` and include:

- benchmark manifest with `run_id`, base model, adapter path, and git revision
- per-dataset metrics JSON
- per-dataset markdown summary
- aggregate summary markdown
- the exact eval manifest digest used for the run
- local-adapter smoke result used as the run precondition

Do not reuse training output files as benchmark outputs.

## Execution surface status

The runtime benchmark surface for `local_adapter` is now implemented:

- `scripts/eval/run_local_adapter_benchmark.py`
- `scripts/eval/eval_rag_llm.py` remains the remote-provider eval surface used
  for optional baseline comparison, not the primary local-adapter run path

This runner executes benchmark requests through the supported
`/v1/rag/answer` API route (not direct pipeline calls), writes reproducible
artifacts under `dist/benchmarks/<run_id>/`, and includes retrieval-only
(`generate=0`) control metrics.

Example command:

```powershell
py -m scripts.eval.run_local_adapter_benchmark `
  --run-dir dist/training/<run_id> `
  --manifest eval/manifest.json `
  --dataset-id ear_compliance.v2 `
  --dataset-id entity_obligations.v2 `
  --dataset-id unanswerable.v2 `
  --smoke-report kg/reports/local-adapter-smoke.json
```

Current operational note:

- benchmark execution still depends on a real local adapter run directory and a
  passing `scripts/local_adapter_smoke.ps1` precondition on the host
- this plan is dormant until a dated decision re-activates the local-adapter
  track

## Exit criteria for Task 6.1

Task 6.1 is complete when:

- the benchmark target is the real production candidate, not a placeholder
- the dataset scope is explicit
- the required metrics are explicit
- the entry criteria and benchmark runner command are explicit
- the plan stays within the supported runtime boundary
