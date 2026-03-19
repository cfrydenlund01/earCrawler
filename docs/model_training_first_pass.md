# Model Training First Pass (Task 5.3)

Status: Phase 5 Task 5.3 implementation guide. This workflow is intentionally
opt-in and does not expand the supported runtime surface by itself.

## Goal

Run the first production-oriented fine-tuning pass for
`Qwen/Qwen2.5-7B-Instruct` using the Task 5.2 input contract, then save
artifacts and run metadata in a deterministic layout.

## Inputs

- Base model selection:
  - `config/training_model_selection.example.env`
- Training input contract:
  - `docs/model_training_contract.md`
  - `config/training_input_contract.example.json`
- Run config template:
  - `config/training_first_pass.example.json`
- Approved offline snapshot manifest:
  - `snapshots/offline/<snapshot_id>/manifest.json` (local)
- Authoritative retrieval corpus + FAISS metadata:
  - `data/faiss/retrieval_corpus.jsonl`
  - `data/faiss/index.meta.json`
- Experimental six-record derivative corpus (not authoritative for training):
  - `data/experimental/retrieval_corpus_6_record_fr_sections.jsonl`

## Repeatable commands

PowerShell wrapper:

```powershell
pwsh .\scripts\training\run_phase5_finetune.ps1 `
  -ConfigPath config/training_first_pass.example.json
```

Direct Python invocation:

```powershell
py scripts/training/run_phase5_finetune.py `
  --config config/training_first_pass.example.json `
  --snapshot-manifest snapshots/offline/<snapshot_id>/manifest.json `
  --retrieval-corpus data/faiss/retrieval_corpus.jsonl
```

Prepare-only package generation (no training):

```powershell
py scripts/training/run_phase5_finetune.py `
  --config config/training_first_pass.example.json `
  --prepare-only
```

Standalone inference smoke for a previously produced adapter:

```powershell
py scripts/training/inference_smoke.py `
  --base-model Qwen/Qwen2.5-7B-Instruct `
  --adapter-dir dist/training/<run_id>/adapter `
  --out dist/training/<run_id>/inference_smoke.rerun.json
```

API local-adapter smoke through `/v1/rag/answer`:

```powershell
pwsh .\scripts\local_adapter_smoke.ps1 `
  -RunDir dist/training/<run_id>
```

Release-evidence bundle validation:

```powershell
py -m scripts.eval.validate_local_adapter_release_bundle `
  --run-dir dist/training/<run_id> `
  --benchmark-summary dist/benchmarks/<benchmark_run_id>/benchmark_summary.json `
  --smoke-report kg/reports/local-adapter-smoke.json
```

## Runtime expectations

- `--prepare-only` is CPU-safe and only builds deterministic package artifacts.
- The runner performs a preflight before packaging/training and fails when the
  configured corpus path does not match the training input contract, or when
  corpus digest/document count do not match `data/faiss/index.meta.json`.
- Full fine-tuning for a 7B model is expected to run on a CUDA-capable host.
- `--use-4bit` is optional and can reduce memory pressure when the environment
  supports bitsandbytes/quantized loading.
- The runner defaults to `use_safetensors=True`. Only use `--allow-pt-bin` if
  you intentionally need legacy `.bin` weights.

## Artifact and version naming

Default run-id pattern:

- `<model_slug>-ear-<YYYY-MM-DD>-snapshot-<snapshot_id>-v<package_version>`

Example:

- `qwen25-7b-ear-2026-03-11-snapshot-ecfr-title15-2026-02-28-v1`

Output layout:

- `dist/training/<run_id>/examples.jsonl`
- `dist/training/<run_id>/manifest.json`
- `dist/training/<run_id>/run_config.json`
- `dist/training/<run_id>/run_metadata.json`
- `dist/training/<run_id>/adapter/` (LoRA artifact)
- `dist/training/<run_id>/inference_smoke.json`
- `dist/training/<run_id>/release_evidence_manifest.json` (created only when the
  optional release bundle is validated)

## Metadata contract (Task 5.3)

`manifest.json` records:

- base model, snapshot id/hash, retrieval corpus path/hash
- example schema version and example count
- package output hashes
- excluded globs for eval/benchmark separation

`run_metadata.json` records:

- start/end timestamps
- git HEAD (when available)
- python interpreter/version
- status (`prepare_only`, `completed`, or `smoke_failed`)
- adapter artifact location
- training metrics
- inference smoke report path

`inference_smoke.json` records at least:

- `base_model`
- `adapter_dir`
- smoke prompt and generated completion
- pass/fail result

## Notes

- This workflow is a Phase 5 training workflow, not an operator runtime command.
- Task 5.4 can load the resulting adapter through `/v1/rag/answer`, but only
  when all of the following are set explicitly:
  - `LLM_PROVIDER=local_adapter`
  - `EARCRAWLER_ENABLE_LOCAL_LLM=1`
  - `EARCRAWLER_LOCAL_LLM_BASE_MODEL=<base-model-id>`
  - `EARCRAWLER_LOCAL_LLM_ADAPTER_DIR=dist/training/<run_id>/adapter`
- The Task 5.4 runtime path also requires `run_metadata.json` and
  `inference_smoke.json` from the same `dist/training/<run_id>/` directory
  before it will serve the adapter.
- Use `scripts/local_adapter_smoke.ps1` to verify the configured API path still
  enforces strict output/schema and egress expectations in local-adapter mode.
- Use `docs/local_adapter_release_evidence.md` and
  `config/local_adapter_release_evidence.example.json` to decide whether a
  concrete run artifact has enough evidence to stay `Optional` or move to a
  formal promotion review.
- A real end-to-end local-adapter smoke still requires a concrete
  `dist/training/<run_id>/` artifact from Task 5.3. If that artifact is not
  present in the current checkout, the smoke remains a documented prerequisite,
  not an executed result.
