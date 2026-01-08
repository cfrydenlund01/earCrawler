# Research Decision Log


## 2025-11-07T21:27:12Z — Immediate Next Steps prompt pack — pass
Generated Phase A hardening, Phase B baseline, API+RAG touchpoint, Packaging & Ops prompts
Artifacts:
- Research/prompts/immediate_phase_a_hardening_prompt.txt (exists)
- Research/prompts/immediate_phase_b_baseline_prompt.txt (exists)
- Research/prompts/immediate_api_rag_touchpoint_prompt.txt (exists)
- Research/prompts/immediate_packaging_ops_prompt.txt (exists)
Env: {"dal": "false", "platform": "nt", "system": "Windows_NT", "tacc": "false", "windows": "true"}

## 2025-11-07T22:10:13Z — Phase A hardening — fail
Corpus produced, validated, snapshotted
Artifacts:
- data/ear_corpus.jsonl (exists)
- data/manifest.json (exists)

## 2025-11-07T22:10:51Z — Phase A hardening — pass
Corpus produced, validated, snapshotted
Artifacts:
- data/ear_corpus.jsonl (exists)
- data/manifest.json (exists)

## 2025-11-10T16:33:21Z — Phase B baseline — fail
Schema frozen; exports hashed; perf budgets warmed
Artifacts:
- kg/ear_export_manifest.json (exists)

## 2025-11-10T16:36:30Z — Phase B baseline — fail
Schema frozen; exports hashed; perf budgets warmed
Artifacts:
- kg/ear_export_manifest.json (exists)

## 2025-11-10T16:39:07Z — Phase B baseline — fail
Schema frozen; exports hashed; perf budgets warmed
Artifacts:
- kg/ear_export_manifest.json (exists)

## 2025-11-10T16:49:37Z — Phase B baseline — fail
Schema frozen; exports hashed; perf budgets warmed
Artifacts:
- kg/ear_export_manifest.json (exists)

## 2025-11-10T16:52:27Z — Phase B baseline — pass
Schema frozen; exports hashed; perf budgets warmed
Artifacts:
- kg/ear_export_manifest.json (exists)

## 2025-11-10T19:18:02Z - API + RAG touchpoint - pass
RAG endpoint stubbed with lineage + cache
Artifacts:
- service/openapi/openapi.yaml (exists)

## 2025-11-10T20:23:47Z - Packaging/Ops dry-run - partial pass
Wheel and EXE built; checksums and SBOM generated; installer skipped due to missing Inno Setup (no choco/winget), signing skipped due to absent cert secrets.
Artifacts:
- dist/earcrawler-0.2.5-py3-none-any.whl (exists)
- dist/earctl-0.2.5-win64.exe (exists)
- dist/checksums.sha256 (exists)
- dist/sbom.spdx.json (exists)
- dist/sbom.cdx.json (exists)
Notes:
- Updated scripts for Windows-first robustness: `scripts/build-exe.ps1`, `scripts/build-wheel.ps1`, `scripts/sbom.ps1`, `scripts/sbom-cyclonedx.ps1`, and `packaging/earctl.spec` (path and icon handling).
- `scripts/make-installer.ps1` requires Inno Setup (`iscc.exe`). Install Inno Setup to enable installer builds.

## 2025-11-10T21:04:02Z - Packaging/Ops dry-run - pass
Installer built via winget-installed Inno Setup; checksums and SBOM refreshed to include installer. Signing still skipped (no cert secrets); verify steps remain valid when secrets are provided.
Artifacts:
- dist/earcrawler-0.2.5-py3-none-any.whl (exists)
- dist/earctl-0.2.5-win64.exe (exists)
- dist/earcrawler-setup-0.2.5.exe (exists)
- dist/checksums.sha256 (exists)
- dist/sbom.spdx.json (exists)
- dist/sbom.cdx.json (exists)
Notes:
- Added winget fallback flow (session PATH injection) and adjusted `installer/earcrawler.iss` paths (`OutputDir`, file sources) and optional icon.

## 2025-11-11T19:31:00Z - Packaging refresh - pass
Rebuilt CLI wheel, PyInstaller EXE, and Inno Setup installer after latest code changes. Re-generated checksums and SBOM artifacts with updated script to skip self-hashing.
Artifacts:
- dist/earcrawler-0.2.5-py3-none-any.whl (exists)
- dist/earctl-0.2.5-win64.exe (exists)
- dist/earcrawler-setup-0.2.5.exe (exists)
- dist/checksums.sha256 (exists)
- dist/sbom.spdx.json (exists)
- dist/sbom.cdx.json (exists)

## 2025-11-11T19:44:00Z - API SDK alignment - pass
EarCrawlerApiClient now mirrors the facade contract: X-Api-Key auth, lineage and SPARQL helpers, and the RAG endpoint. Added regression tests and docs snippet for downstream integrators.
Artifacts:
- api_clients/ear_api_client.py (updated)
- tests/clients/test_ear_api_client.py (new)
- docs/api/readme.md (updated)
- scripts/checksums.ps1 (updated)

## 2025-12-10T21:22:52Z - Phase E baseline (tiny-gpt2) - pass
Baseline eval runs for ear_compliance.v1, entity_obligations.v1, and unanswerable.v1 using sshleifer/tiny-gpt2; metrics and summaries emitted under dist/eval/.
Artifacts:
- dist/eval/ear_compliance.v1.baseline.tiny-gpt2.json (exists)
- dist/eval/ear_compliance.v1.baseline.tiny-gpt2.md (exists)
- dist/eval/entity_obligations.v1.baseline.tiny-gpt2.json (exists)
- dist/eval/entity_obligations.v1.baseline.tiny-gpt2.md (exists)
- dist/eval/unanswerable.v1.baseline.tiny-gpt2.json (exists)
- dist/eval/unanswerable.v1.baseline.tiny-gpt2.md (exists)
Notes:
- Eval summaries:
  - [2025-12-10T21:22:04.853044+00:00] dataset=ear_compliance.v1 task=ear_compliance model=sshleifer/tiny-gpt2 accuracy=0.0000 label_accuracy=0.0000 unanswerable_accuracy=0.0000 kg_digest=9c42fa4e9fc2ebfe8a206d0d03a9d100da08e1ddc0c012f7969eac3c0ad06cff file=dist\\eval\\ear_compliance.v1.baseline.tiny-gpt2.json
  - [2025-12-10T21:22:18.086624+00:00] dataset=entity_obligations.v1 task=entity_obligation model=sshleifer/tiny-gpt2 accuracy=0.0000 label_accuracy=0.0000 unanswerable_accuracy=0.0000 kg_digest=9c42fa4e9fc2ebfe8a206d0d03a9d100da08e1ddc0c012f7969eac3c0ad06cff file=dist\\eval\\entity_obligations.v1.baseline.tiny-gpt2.json
  - [2025-12-10T21:22:30.054252+00:00] dataset=unanswerable.v1 task=unanswerable model=sshleifer/tiny-gpt2 accuracy=0.0000 label_accuracy=0.0000 unanswerable_accuracy=0.0000 kg_digest=9c42fa4e9fc2ebfe8a206d0d03a9d100da08e1ddc0c012f7969eac3c0ad06cff file=dist\\eval\\unanswerable.v1.baseline.tiny-gpt2.json
## 2026-01-07T22:38:18Z — Offline bundle build automation — pass
Updated scripts/build-offline-bundle.ps1 to accept canonical KG directories that contain dataset.nq (or dataset.ttl) without requiring provenance.json; verified by building a bundle to dist/offline_bundle_test.
Artifacts:
- scripts/build-offline-bundle.ps1 (exists)
- dist/offline_bundle_test/manifest.json (exists)
- dist/offline_bundle_test/checksums.sha256 (exists)
Env: {"dal": "false", "platform": "nt", "system": "Windows_NT", "tacc": "false", "windows": "true"}

## 2026-01-07T22:40:21Z - Phase B baseline drift gate - pass
Verified baseline rebuild is stable: ran pwsh kg/scripts/phase-b-freeze.ps1 and confirmed no content diff vs tracked kg/baseline.
Artifacts:
- kg/scripts/phase-b-freeze.ps1 (exists)
- kg/baseline/manifest.json (exists)
- kg/baseline/checksums.sha256 (exists)
- kg/baseline/dataset.nq (exists)
Env: {"dal": "false", "platform": "nt", "system": "Windows_NT", "tacc": "false", "windows": "true"}

## 2026-01-08T16:38:13Z - Refetch 736/740/742/744/746 FR corpus + rebuild retrieval artifacts - pass
Refetched Federal Register passages for 736.2(b), 740.1, 740.9(a)(2), 742.4(a)(1), 744.6(b)(3), 746.4(a) into data/fr_sections.jsonl (18 records, per-page=3). Evidence gate now passes (0 missing) and kg_expansion.json regenerated; FAISS index rebuilt from the refreshed corpus.
Artifacts:
- data/fr_sections.jsonl (exists)
- dist/eval/evidence_report.json (exists)
- data/kg_expansion.json (exists)
- data/faiss/index.faiss (exists)
- data/faiss/index.pkl (exists)
Env: {"dal": "false", "platform": "nt", "system": "Windows_NT", "tacc": "false", "windows": "true"}

## 2026-01-08T17:06:32Z - RAG eval CLI smoke (ear_compliance.v1, max-items=5) - degraded
Quick validation + smoke run for `earctl eval run-rag` on a single dataset. The CLI path is functional but the remote LLM provider is not configured on this machine, so all scored items failed (metrics are therefore 0.0000 across the board).

Validation:
- `python eval/validate_datasets.py` -> `All evaluation datasets validated successfully.`
- `pytest -q` -> fails during collection because Java 17+ is required for inference/KG/SHACL-related tests (4 collection errors).

RAG smoke:
- Command: `earctl eval run-rag --dataset-id ear_compliance.v1 --max-items 5`
- Provider/model: groq / llama-3.3-70b-versatile (default)
- Items: 3 (from `dist/eval/ear_compliance.v1.rag.groq.llama-3.3-70b-versatile.md`)
- Results: 3/3 failed with `GROQ_API_KEY is not configured` (remote LLM enabled via `EARCRAWLER_ENABLE_REMOTE_LLM=1`)
- Metrics: accuracy=0.0000, label_accuracy=0.0000, unanswerable_accuracy=0.0000, grounded_rate=0.0000, semantic_accuracy=0.0000, avg_latency=6.1701s
Artifacts:
- dist/eval/ear_compliance.v1.rag.groq.llama-3.3-70b-versatile.json (exists, 3 failed items)
- dist/eval/ear_compliance.v1.rag.groq.llama-3.3-70b-versatile.md (exists)

Code fix (to unblock the CLI import path):
- `earctl eval run-rag` previously failed with `No module named 'scripts.eval'` when running from an installed console script (repo root not on `sys.path`).
- Updated packaging config to ship the `scripts` package so `from scripts.eval import ...` works when `earctl` is installed.
Artifacts:
- pyproject.toml (updated: include `scripts*` in setuptools package discovery)

Additional steps before implementing a 100-QA (50 true / 50 untrue) CLI test:
- Decide “untrue” contract: unanswerable vs explicitly false, and required CLI behavior (e.g., abstain + cite evidence vs label false).
- Provision deterministic test infra: stable KG/corpus snapshot (record KG digest), stable retrieval params, and fixed model/provider/version.
- Ensure the eval path is runnable in automation: configure `config/llm_secrets.env` (or Windows Credential Store) with `GROQ_API_KEY`/`NVIDIA_NIM_API_KEY`, and set `EARCRAWLER_ENABLE_REMOTE_LLM=1` for the test job.
- Add a dataset format for QA prompts with expected outcomes and a scoring rubric (exact label match + evidence/groundedness checks); wire it into `earctl eval` so it can run in CI with a single command.

## 2026-01-08T19:26:06Z - Validation + RAG smoke rerun (ear_compliance.v1, max-items=5) - degraded
Ran the requested quick validation pass and re-ran the RAG smoke on `ear_compliance.v1`. Unit/integration tests are now green locally (Java/tooling issues addressed), but the RAG eval still cannot generate answers because the Groq API key is not configured.

Validation:
- `python eval/validate_datasets.py` -> `All evaluation datasets validated successfully.`
- `pytest -q` -> 217 passed, 5 skipped (Java 17+ available; network-restricted tests skipped as designed).

RAG smoke:
- Command: `earctl eval run-rag --dataset-id ear_compliance.v1 --max-items 5`
- Provider/model: groq / llama-3.3-70b-versatile (default)
- Items: 3, top_k=5
- Results: 3/3 failed with `GROQ_API_KEY is not configured` (remote LLM enabled via `EARCRAWLER_ENABLE_REMOTE_LLM=1`)
- Metrics (dist/eval/ear_compliance.v1.rag.groq.llama-3.3-70b-versatile.md): accuracy=0.0000, label_accuracy=0.0000, unanswerable_accuracy=0.0000, grounded_rate=0.0000, semantic_accuracy=0.0000, avg_latency=32.0657s
- KG digest: 9c42fa4e9fc2ebfe8a206d0d03a9d100da08e1ddc0c012f7969eac3c0ad06cff
Artifacts:
- dist/eval/ear_compliance.v1.rag.groq.llama-3.3-70b-versatile.json (exists)
- dist/eval/ear_compliance.v1.rag.groq.llama-3.3-70b-versatile.md (exists)

Next steps before a 100-QA (50 true / 50 untrue) CLI test:
- Wire secrets for the eval job: set `GROQ_API_KEY` (or configure `NVIDIA_NIM_*`) and keep `EARCRAWLER_ENABLE_REMOTE_LLM=1`; decide how/where secrets are injected (env vs Windows Credential Store vs CI secrets).
- Define the “untrue” contract precisely (unanswerable vs explicitly false vs “insufficient evidence”), and enforce a consistent CLI output schema (label + rationale + citations).
- Make the run deterministic enough to be actionable: pin model/provider, snapshot KG/corpus (record digest), fix retrieval params, and capture tool/model versions in emitted metadata.
- Add/confirm scoring + failure modes: label accuracy, abstention correctness, citation/groundedness checks, and clear handling for API failures/timeouts (distinguish infra errors vs model mistakes).
- Create the QA dataset in `eval/datasets/` with a stable manifest entry, and add a CI target that runs `earctl eval run-rag` (or a QA-specific command) end-to-end on the 100 items and emits a summary file for gating.

## 2026-01-08T19:41:46Z - RAG smoke with Groq key configured (ear_compliance.v1, max-items=5) - pass (quality low)
Re-ran the same RAG smoke after configuring `GROQ_API_KEY` via `config/llm_secrets.env` (git-ignored). The eval ran end-to-end with remote LLM calls and produced metrics, but answer scoring is strict (exact string match), so “accuracy” remains 0.0 even though labels and semantic similarity are high.

RAG smoke:
- Command: `earctl eval run-rag --dataset-id ear_compliance.v1 --max-items 5`
- Provider/model: groq / llama-3.3-70b-versatile
- Items: 3, top_k=5
- Errors: 0/3 (remote LLM calls succeeded)
- Metrics (dist/eval/ear_compliance.v1.rag.groq.llama-3.3-70b-versatile.md):
  - accuracy=0.0000 (exact-match vs ground_truth_answer)
  - label_accuracy=1.0000
  - grounded_rate=0.3333
  - semantic_accuracy=1.0000 (SequenceMatcher >=0.6)
  - avg_latency=29.5083s
- KG digest: 9c42fa4e9fc2ebfe8a206d0d03a9d100da08e1ddc0c012f7969eac3c0ad06cff
Artifacts:
- dist/eval/ear_compliance.v1.rag.groq.llama-3.3-70b-versatile.json (exists)
- dist/eval/ear_compliance.v1.rag.groq.llama-3.3-70b-versatile.md (exists)

Implications / next steps before a 100-QA CLI test:
- Decide the primary score: if QA is about compliance labels, gate on `label_accuracy` (+ groundedness) rather than exact answer-string equality, or add an answer normalization/semantic judge mode for “accuracy”.
- Tighten grounding: for “true/untrue” QA, require citations that include the expected section span(s); measure and gate on grounded_rate and/or evidence overlap.
- Add timeouts + retry policy for remote calls and classify failures separately from model errors (so “API outage” doesn’t look like “model wrong”).
- Freeze the evaluation contract: pin provider/model, retrieval params, and dataset/KG digest; store these in the emitted metadata and in the CI job output.

