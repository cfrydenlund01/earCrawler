# Baseline Verification Runbook

## Purpose
Record a repeatable baseline run with:
- unit tests,
- FR coverage report generation,
- Phase 2 golden gate.

Store run outputs under `dist/baseline/<timestamp>/`.

## Preconditions
- Run from repository root.
- Use the project virtualenv interpreter: `.venv\Scripts\python.exe`.
- Offline/default test mode (no network-marked tests).
- FR corpus file exists: `data/fr_sections.jsonl`.
- FAISS artifacts available for FR coverage (default path `data/faiss/index.faiss`).
- Offline snapshot provenance is known:
  - `snapshots/offline/<snapshot_id>/manifest.json`
  - `snapshots/offline/<snapshot_id>/snapshot.jsonl` (not committed; external)
- If `py` resolves to Windows Store Python and fails with `WinError 126` on Torch DLLs, do not use `py` for baseline commands.

## Environment Variables
Required:
- None for offline baseline.

Optional (only when overriding defaults):
- `EARCRAWLER_FAISS_INDEX` (custom FAISS index path)
- `EARCRAWLER_FAISS_MODEL` (custom embedding model for retriever metadata)

## Canonical Commands
0. Snapshot provenance (fail fast + record the authoritative manifest/hash):
```powershell
.venv\Scripts\python.exe -m earCrawler.cli rag-index validate-snapshot `
  --snapshot snapshots/offline/<snapshot_id>/snapshot.jsonl `
  | Tee-Object -FilePath dist/baseline/<timestamp>/snapshot_validation.log
```

0.1 FAISS index provenance (record corpus digest + snapshot id/hash if present):
```powershell
Copy-Item data/faiss/index.meta.json dist/baseline/<timestamp>/index.meta.json
```

0.2 Deterministic retrieval corpus rebuild from approved snapshot:
```powershell
.venv\Scripts\python.exe -m earCrawler.cli rag-index rebuild-corpus `
  --snapshot snapshots/offline/<snapshot_id>/snapshot.jsonl `
  --out-base dist/corpus `
  --dataset-manifest eval/manifest.json
```
Artifacts are written to `dist/corpus/<snapshot_id>/`:
- `retrieval_corpus.jsonl` (canonical JSONL, contract-validated)
- `build_log.json` (corpus digest/SHA256, snapshot provenance, metadata coverage, smoke-check result)

To confirm determinism, run the same command twice and verify `build_log.json` reports the same `corpus.digest`.

0.3 Rebuild FAISS index + sidecar from canonical corpus:
```powershell
.venv\Scripts\python.exe -m earCrawler.cli rag-index rebuild-index `
  --corpus dist/corpus/<snapshot_id>/retrieval_corpus.jsonl `
  --out-base dist/index `
  --model-name all-MiniLM-L12-v2 `
  --smoke-query "General prohibitions" `
  --expect-section EAR-736.2
```
Artifacts are written to `dist/index/<snapshot_id>/`:
- `index.faiss`
- `index.meta.json` (embedding model, corpus digest, build timestamp, doc count)
- `index_build_log.json` (wiring/smoke verification)
- `runtime.env` and `runtime_env.ps1` (pipeline env vars)

0.4 Trace-pack provenance spot check (single-item eval):
```powershell
.venv\Scripts\python.exe -m scripts.eval.eval_rag_llm `
  --dataset-id golden_phase2.v1 `
  --manifest eval/manifest.json `
  --max-items 1 `
  --out-json dist/baseline/<timestamp>/trace_eval.json `
  --out-md dist/baseline/<timestamp>/trace_eval.md
```
Inspect `dist/baseline/<timestamp>/trace_eval/trace_packs/<dataset_id>/*.trace.json` and verify:
- `run_provenance.snapshot_id`, `run_provenance.snapshot_sha256`
- `run_provenance.corpus_digest`, `run_provenance.index_path`, `run_provenance.embedding_model`
- `provenance_hash` is present and stable for repeat runs on the same snapshot/index.

1. Unit tests:
```powershell
.venv\Scripts\python.exe -m pytest -q
```

2. FR coverage (all datasets):
```powershell
.venv\Scripts\python.exe -m earCrawler.cli eval fr-coverage `
  --manifest eval/manifest.json `
  --corpus data/fr_sections.jsonl `
  --dataset-id all `
  --retrieval-k 10 `
  --out dist/baseline/<timestamp>/fr_coverage_report.json `
  --summary-out dist/baseline/<timestamp>/fr_coverage_summary.json `
  --no-fail
```

3. Golden gate:
```powershell
.venv\Scripts\python.exe -m pytest -q tests/golden/test_phase2_golden_gate.py
```

## Required Outputs
- `snapshot_validation.log` (snapshot_id/manifest + counts + bytes)
- `index.meta.json` (FAISS metadata: corpus_digest, embedding_model, snapshot info if present)
- `index_build_log.json` (build timestamp + env wiring + smoke query outcome)
- `unit_pytest.log`
- `fr_coverage.log`
- `fr_coverage_report.json`
- `fr_coverage_summary.json`
- `golden_gate.log`
- `baseline_summary.json` (commit hash + command exit codes + snapshot_id/hash used)

## Reproducibility Notes
- Capture `git rev-parse HEAD` and `git status --porcelain` in `baseline_summary.json`.
- Include snapshot provenance in `baseline_summary.json`:
  - `snapshot_id` and `payload.sha256` from `snapshots/offline/<snapshot_id>/manifest.json`
  - `corpus_digest` from `dist/baseline/<timestamp>/index.meta.json`
- If the working tree is dirty, treat the baseline as provisional and re-run after committing.
