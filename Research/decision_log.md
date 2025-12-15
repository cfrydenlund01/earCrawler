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
