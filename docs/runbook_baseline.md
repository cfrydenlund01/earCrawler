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
