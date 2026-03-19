# Local-Adapter Release Evidence Bundle

Status: active Phase 5 evidence contract for the optional
`LLM_PROVIDER=local_adapter` runtime path.

This document defines the minimum evidence bundle required before a Task 5.3
adapter artifact can be treated as a real release candidate for the optional
local-adapter serving path. It does not change the supported baseline runtime,
and it does not promote the capability by itself.

Use this document together with:

- `config/local_adapter_release_evidence.example.json`
- `docs/model_training_first_pass.md`
- `docs/production_candidate_benchmark_plan.md`
- `docs/capability_graduation_boundaries.md`
- `docs/ops/windows_single_host_operator.md`

## Goal

Make local-adapter release claims artifact-backed and reproducible.

The minimum bundle must prove all of the following for one named
`dist/training/<run_id>/` candidate:

- which adapter artifact is under review
- which snapshot and retrieval corpus produced it
- which benchmark outputs were used to judge it
- whether the supported optional runtime path still works through
  `/v1/rag/answer`
- how to roll the host back if the candidate is rejected

## Required bundle contents

For a candidate run directory `dist/training/<run_id>/`, the minimum bundle is:

1. Adapter artifact and Task 5.3 run metadata
   - `dist/training/<run_id>/adapter/`
   - `dist/training/<run_id>/manifest.json`
   - `dist/training/<run_id>/run_config.json`
   - `dist/training/<run_id>/run_metadata.json`
   - `dist/training/<run_id>/inference_smoke.json`
2. Provenance manifest for the release review
   - `dist/training/<run_id>/release_evidence_manifest.json`
   - Produced by `py -m scripts.eval.validate_local_adapter_release_bundle ...`
   - This manifest records file hashes, corpus digest, benchmark references,
     threshold results, and the final decision label
3. Runtime smoke
   - `kg/reports/local-adapter-smoke.json` from
     `pwsh .\scripts\local_adapter_smoke.ps1 -RunDir dist/training/<run_id>`
4. Benchmark bundle
   - `dist/benchmarks/<benchmark_run_id>/benchmark_manifest.json`
   - `dist/benchmarks/<benchmark_run_id>/benchmark_summary.json`
   - `dist/benchmarks/<benchmark_run_id>/benchmark_summary.md`
   - `dist/benchmarks/<benchmark_run_id>/benchmark_artifacts.json`
5. Rollback instructions
   - this document
   - `docs/capability_graduation_boundaries.md`
   - `docs/ops/windows_single_host_operator.md`

If any item above is missing, the evidence is insufficient and the capability
stays `Optional`.

## Provenance requirements

The candidate bundle must preserve the same authoritative text-and-retrieval
truth chain already used elsewhere in the repo.

`dist/training/<run_id>/manifest.json` must record at least:

- `run_id`
- `base_model`
- `snapshot_id`
- `snapshot_sha256`
- `retrieval_corpus_path`
- `retrieval_corpus_digest`
- `retrieval_corpus_doc_count`
- `training_input_contract_path`
- `index_meta_path`

The release-evidence validator copies these facts into
`release_evidence_manifest.json` and adds SHA-256 hashes for the benchmark
summary and smoke report so the review bundle can be archived and compared
later.

## Benchmark requirements

Use the benchmark runner from `docs/production_candidate_benchmark_plan.md`:

```powershell
py -m scripts.eval.run_local_adapter_benchmark `
  --run-dir dist/training/<run_id> `
  --manifest eval/manifest.json `
  --dataset-id ear_compliance.v2 `
  --dataset-id entity_obligations.v2 `
  --dataset-id unanswerable.v2 `
  --smoke-report kg/reports/local-adapter-smoke.json
```

The benchmark bundle must include:

- aggregate `local_adapter` metrics
- aggregate `retrieval_only` control metrics
- all three primary datasets:
  - `ear_compliance.v2`
  - `entity_obligations.v2`
  - `unanswerable.v2`

## Minimum thresholds

The contract threshold file is `config/local_adapter_release_evidence.example.json`.

The current minimum benchmark thresholds for the `local_adapter` aggregate are:

- `answer_accuracy >= 0.65`
- `label_accuracy >= 0.80`
- `unanswerable_accuracy >= 0.90`
- `valid_citation_rate >= 0.95`
- `supported_rate >= 0.90`
- `overclaim_rate <= 0.05`
- `strict_output_failure_rate == 0.0`
- `request_422_rate == 0.0`
- `request_503_rate == 0.0`
- `latency_ms.p95 <= 15000`

The release bundle must also carry a retrieval-only control, and the
`local_adapter` condition must:

- meet or exceed retrieval-only `answer_accuracy`
- meet or exceed retrieval-only `supported_rate`
- not exceed retrieval-only `overclaim_rate`

These thresholds are intentionally strict enough to block a candidate that is
artifact-complete but still operationally weak.

## Runtime smoke requirements

Two smoke layers are required:

1. `inference_smoke.json`
   - proves the Task 5.3 adapter can still load against the named base model
2. `kg/reports/local-adapter-smoke.json`
   - proves the supported optional `/v1/rag/answer` runtime path still works
   - proves `provider=local_adapter`
   - proves remote egress remains disabled in local-adapter mode

If either smoke report is missing or non-passing, the evidence is insufficient.

## Rollback expectation

The rollback story for local-adapter release candidates is intentionally small:

1. Remove or clear the local-adapter env on the host:
   - `LLM_PROVIDER`
   - `EARCRAWLER_ENABLE_LOCAL_LLM`
   - `EARCRAWLER_LOCAL_LLM_BASE_MODEL`
   - `EARCRAWLER_LOCAL_LLM_ADAPTER_DIR`
   - `EARCRAWLER_LOCAL_LLM_MODEL_ID`
2. Restart the API service.
3. Re-run `/health` plus supported API smoke.
4. Confirm the host capability posture is back to the baseline default:
   - search `Quarantined`
   - KG expansion `Quarantined`
   - retrieval mode `dense`
   - no active local-adapter env

If a wheel or host config change accompanied the candidate, use the broader host
rollback procedure in `docs/ops/windows_single_host_operator.md`.

## Validation command

Validate the minimum release bundle with:

```powershell
py -m scripts.eval.validate_local_adapter_release_bundle `
  --run-dir dist/training/<run_id> `
  --benchmark-summary dist/benchmarks/<benchmark_run_id>/benchmark_summary.json `
  --smoke-report kg/reports/local-adapter-smoke.json
```

Default behavior:

- reads `config/local_adapter_release_evidence.example.json`
- writes `dist/training/<run_id>/release_evidence_manifest.json`
- exits non-zero when evidence is incomplete or thresholds fail

## Decision rule

The decision rule is exact:

- `Keep Optional`
  - if any required artifact is missing
  - if any smoke report fails
  - if any required dataset is missing from the benchmark bundle
  - if any threshold fails
  - if the candidate underperforms the retrieval-only control on a required
    comparison rule
- `Ready for formal promotion review`
  - only when the full bundle exists and all checks pass

Passing this contract does not directly change the capability state to
`Supported`. Promotion still requires a dated decision record plus updates to
the capability registry and operator docs.

## What counts as insufficient evidence

Examples of insufficient evidence:

- adapter files exist, but no benchmark bundle exists
- benchmark bundle exists, but `retrieval_only` control data is missing
- `manifest.json` is missing `retrieval_corpus_digest`
- `local-adapter-smoke.json` is missing or non-passing
- citation/support metrics pass, but overclaim exceeds the max threshold
- metrics are acceptable, but rollback docs are not named and archived

Any of the above means the local-adapter path may remain implemented in source,
but it is not ready to be promoted beyond the current `Optional` state.
