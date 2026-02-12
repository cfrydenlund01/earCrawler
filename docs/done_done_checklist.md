# Done-done checklist (exit criteria for this pass)

Use this checklist as **exit criteria** before claiming the repo is ready for the next phase.

## 0) One-command “scorecard” (recommended)
This produces an archived, diff-friendly bundle that includes snapshot + index provenance and the key offline gates.

```powershell
.\.venv\Scripts\python.exe scripts\reporting\build_results_bundle.py `
  --snapshot-id <snapshot_id> `
  --index-meta data\faiss\index.meta.json `
  --corpus data\faiss\retrieval_corpus.jsonl `
  --max-missing-rate 0.35 `
  --eval-mode golden_offline `
  --eval-dataset-id golden_phase2.v1 `
  --eval-max-items 25 `
  --require-eval
```

Pass if:
- `dist/results/<bundle>/bundle_scorecard.json` has `exit_code: 0` for `snapshot_validate`, `fr_coverage`, `pytest`, `golden_gate`, and `small_eval`.

## 1) Working tree is clean; transient artifacts ignored; baseline runbook exists
Pass if:
- `git status --porcelain` is empty.
- Transient directories are ignored (see `.gitignore` and `docs/repo_hygiene_policy.md`).
- Baseline runbooks exist: `RUNBOOK.md` and `docs/runbook_baseline.md`.

## 2) Approved offline snapshot + manifest exist and validate automatically
Pass if an approved snapshot directory contains both files:
- `snapshots/offline/<snapshot_id>/snapshot.jsonl`
- `snapshots/offline/<snapshot_id>/manifest.json`

And validation passes:
```powershell
.\.venv\Scripts\python.exe -m earCrawler.cli rag-index validate-snapshot `
  --snapshot snapshots/offline/<snapshot_id>/snapshot.jsonl
```

Reference: `docs/offline_snapshot_spec.md`.

## 3) Corpus + FAISS index build from snapshot are push-button and produce provenance
Pass if:
- Corpus build is reproducible from the snapshot (see `docs/runbook_baseline.md`).
- Index rebuild writes a provenance sidecar:
  - `data/faiss/index.meta.json` includes `corpus_digest`, `embedding_model`, and `snapshot.snapshot_id`/`snapshot.snapshot_sha256`.

## 4) v2 `fr-coverage` gate is script-driven and meets your missing-rate threshold
Run the gate script (defaults to v2-only coverage; use `-IncludeLegacy` to include v1 datasets):
```powershell
pwsh scripts/run_phase1_coverage.ps1 -MaxMissingRate 0.35
```

Pass if:
- Script exits `0`.
- `dist/eval/coverage_runs/<timestamp>/fr_coverage_summary.json` reports
  `worst_missing_in_retrieval_rate <= MaxMissingRate`.

## 5) Strict output contract is not bypassable; unanswerable cases are tested
Pass if:
- Service/CLI paths don’t expose a “disable strict output” switch.
- Tests enforcing refusal + schema constraints pass:
```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/rag/test_pipeline_strict_output.py
```

Optional static sanity check (should be empty):
```powershell
rg -n "strict_output\\s*=\\s*False" earCrawler scripts
```

## 6) Dataset validation is a hard prerequisite; golden gate includes citation traps and is deterministic
Pass if dataset validation succeeds:
```powershell
.\.venv\Scripts\python.exe -m eval.validate_datasets --manifest eval/manifest.json
```

And the offline golden gate passes:
```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/golden/test_phase2_golden_gate.py
```

## 7) Results bundles are archived with snapshot/index provenance and are diffable over time
Pass if:
- Each bundle contains: `provenance.snapshot.json`, `provenance.index.json`, `provenance.git.json`.
- A diff-friendly summary exists: `bundle_scorecard.json`.
- Bundles can be compared over time by diffing `bundle_scorecard.json` and `fr_coverage_summary.json`.

Entrypoint: `scripts/reporting/build_results_bundle.py`.

## 8) Identifier policy is documented; a consistency checker prevents citation/KG drift
Pass if:
- Policy is current: `docs/identifier_policy.md`.
- Consistency check passes:
```powershell
.\.venv\Scripts\python.exe scripts/eval/check_id_consistency.py `
  --manifest eval/manifest.json `
  --corpus data/faiss/retrieval_corpus.jsonl `
  --dataset-id all `
  --out-json dist/checks/id_consistency.json `
  --out-md dist/checks/id_consistency.md
```

Optional KG validation:
- Provide `--kg-path <triples.(ttl|nq|nt)>` (or use `--disable-kg` to skip).

## 9) Multi-hop ablation compare is reproducible; trace packs include KG paths when enabled
Offline / reproducible compare (stubbed LLM, JSON-stub KG expansion):
```powershell
.\.venv\Scripts\python.exe scripts/eval/run_multihop_ablation_compare_stubbed.py --max-items 10
```

Pass if:
- `dist/ablations/<run_id>/ablation_summary.json` is created.
- When KG expansion is enabled, trace packs include KG path fields (see `earCrawler/trace/trace_pack.py`).

Production-like run (requires Fuseki + real provider credentials):
- `scripts/eval/run_multihop_kg_prodlike.py`

## 10) Audit ledger emits minimum required events; integrity checks detect tampering
Pass if:
- Requirements are met: `docs/audit_event_requirements.md`.
- Tests pass:
```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/audit/test_required_events_and_integrity.py
```
- CLI verifies a ledger file:
```powershell
.\.venv\Scripts\python.exe -m earCrawler.cli audit verify --path <ledger.jsonl>
```

---

## Suggested final step
After the gates pass, record the snapshot id + bundle path in your phase notes and ensure the repo is clean:
```powershell
git status --porcelain
```
