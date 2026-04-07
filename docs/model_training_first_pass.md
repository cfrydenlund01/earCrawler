# Model Training First Pass (Task 5.3)

Status: Phase 5 Task 5.3 implementation guide. This workflow is intentionally
opt-in and does not expand the supported runtime surface by itself.

## Goal

Run the first production-oriented fine-tuning pass for
`google/gemma-4-E4B-it` using the Task 5.2 input contract, then save
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

Step 7.1 environment prep (no training):

```powershell
pwsh .\scripts\training\prepare_qlora_env.ps1 `
  -TorchMode auto
```

PowerShell wrapper:

```powershell
pwsh .\scripts\training\run_phase5_finetune.ps1 `
  -ConfigPath config/training_first_pass.example.json
```

Direct Python invocation:

```powershell
.venv\Scripts\python.exe scripts/training/run_phase5_finetune.py `
  --config config/training_first_pass.example.json `
  --snapshot-manifest snapshots/offline/<snapshot_id>/manifest.json `
  --retrieval-corpus data/faiss/retrieval_corpus.jsonl `
  --use-4bit `
  --require-qlora-4bit
```

Prepare-only package generation (no training):

```powershell
.venv\Scripts\python.exe scripts/training/run_phase5_finetune.py `
  --config config/training_first_pass.example.json `
  --prepare-only
```

Standalone inference smoke for a previously produced adapter:

```powershell
.venv\Scripts\python.exe scripts/training/inference_smoke.py `
  --base-model google/gemma-4-E4B-it `
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
.venv\Scripts\python.exe -m scripts.eval.validate_local_adapter_release_bundle `
  --run-dir dist/training/<run_id> `
  --benchmark-summary dist/benchmarks/<benchmark_run_id>/benchmark_summary.json `
  --smoke-report kg/reports/local-adapter-smoke.json
```

Reviewable candidate bundle assembly:

```powershell
.venv\Scripts\python.exe -m scripts.eval.build_local_adapter_candidate_bundle `
  --run-dir dist/training/<run_id> `
  --benchmark-summary dist/benchmarks/<benchmark_run_id>/benchmark_summary.json `
  --smoke-report kg/reports/local-adapter-smoke.json
```

## Runtime expectations

- `--prepare-only` is CPU-safe and only builds deterministic package artifacts.
- `scripts/training/prepare_qlora_env.ps1` can auto-detect NVIDIA GPUs and apply
  a CUDA torch build (`-TorchMode auto`), or print manual torch commands
  (`-TorchMode manual`).
- The runner performs a preflight before packaging/training and fails when the
  configured corpus path does not match the training input contract, or when
  corpus digest/document count do not match `data/faiss/index.meta.json`.
- For the first 7B production-candidate path, QLoRA is required
  (`require_qlora_4bit=true` and `use_4bit=true`).
- QLoRA runtime preflight (`torch.cuda.is_available()==true` and at least one
  CUDA device) is enforced for non-`--prepare-only` runs before training starts.
- Full fine-tuning for a 7B model is expected to run on a CUDA-capable host.
- The runner records machine-checkable QLoRA evidence in
  `run_metadata.json` (`qlora.required`, `qlora.requested_use_4bit`,
  `qlora.effective_use_4bit`).
- The runner defaults to `use_safetensors=True`. Only use `--allow-pt-bin` if
  you intentionally need legacy `.bin` weights.

## Artifact and version naming

Default run-id pattern:

- `<model_slug>-ear-<YYYY-MM-DD>-snapshot-<snapshot_id>-v<package_version>`

Example:

- `gemma4-e4b-ear-2026-03-11-snapshot-ecfr-title15-2026-02-28-v1`

Output layout:

- `dist/training/<run_id>/examples.jsonl`
- `dist/training/<run_id>/manifest.json`
- `dist/training/<run_id>/run_config.json`
- `dist/training/<run_id>/run_metadata.json`
- `dist/training/<run_id>/adapter/` (LoRA artifact)
- `dist/training/<run_id>/inference_smoke.json`
- `dist/training/<run_id>/release_evidence_manifest.json` (created only when the
  optional release bundle is validated)
- `dist/reviewable_candidates/<bundle_id>/bundle_manifest.json` (created only
  when the candidate evidence is complete enough to assemble a review bundle)

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
- QLoRA evidence (`required`, requested 4-bit flag, and effective 4-bit result)
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
  concrete run artifact stays `Optional` due to incomplete evidence, is
  `Rejected` as a reviewed candidate, or is `Ready for formal promotion review`.
- Use `scripts/eval/build_local_adapter_candidate_bundle.py` only after the
  release-evidence contract is reviewable. It assembles the run artifacts,
  benchmark bundle, reviewed smoke, and rollback docs into a deterministic
  `dist/reviewable_candidates/<bundle_id>/` package for maintainer review.
- A real end-to-end local-adapter smoke still requires a concrete
  `dist/training/<run_id>/` artifact from Task 5.3. If that artifact is not
  present in the current checkout, the smoke remains a documented prerequisite,
  not an executed result.

