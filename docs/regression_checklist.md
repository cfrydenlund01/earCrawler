# Regression checklist (fast vs full)

This repo has two levels of regression checks:
- **Fast checks**: minutes; run before pushing/merging.
- **Full checks**: longer; run before cutting a baseline or when retrieval/corpus/index logic changes.

## Agent switch profile (set before runs)

Set retrieval/refusal behavior explicitly so results are reproducible across local sessions/agents.

```powershell
# Default for parser/strict-output debugging (no forced refusal on empty retrieval)
$env:EARCRAWLER_REFUSE_ON_THIN_RETRIEVAL = "0"
Remove-Item Env:EARCRAWLER_THIN_RETRIEVAL_MIN_DOCS -ErrorAction SilentlyContinue
Remove-Item Env:EARCRAWLER_THIN_RETRIEVAL_MIN_TOP_SCORE -ErrorAction SilentlyContinue
Remove-Item Env:EARCRAWLER_THIN_RETRIEVAL_MIN_TOTAL_CHARS -ErrorAction SilentlyContinue

# Baseline/gating profile (deterministic refusal on thin retrieval)
# $env:EARCRAWLER_REFUSE_ON_THIN_RETRIEVAL = "1"
# $env:EARCRAWLER_THIN_RETRIEVAL_MIN_DOCS = "1"
# $env:EARCRAWLER_THIN_RETRIEVAL_MIN_TOP_SCORE = "0.5"
# $env:EARCRAWLER_THIN_RETRIEVAL_MIN_TOTAL_CHARS = "0"
```

## Fast checks (target: <10 minutes)

Pass/fail criteria: all commands exit `0`.

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m eval.validate_datasets --manifest eval/manifest.json
.venv\Scripts\python.exe -m pytest -q tests/golden/test_phase2_golden_gate.py
```

When to run:
- Any PR/commit that touches `earCrawler/`, `scripts/`, or `eval/`.

## Full checks (baseline / “run the world”)

Pass/fail criteria: all required gates exit `0` and the bundle is archived under `dist/results/`.

```powershell
.venv\Scripts\python.exe -m scripts.reporting.build_results_bundle
```

What it does:
- Validates the current offline snapshot (if available).
- Generates a v2 snapshot-universe coverage manifest and runs `eval fr-coverage` with a strict missing-rate gate.
- Runs unit tests and Phase 2 golden gate.
- Runs a small **offline** eval that emits citation metrics and trace packs (golden fixtures).
  - Optional: `--eval-mode remote_llm` runs the remote LLM eval harness instead (requires provider config).
- Honors whichever retrieval/refusal profile is set in the shell environment.

When to run:
- Before publishing a new “baseline” bundle.
- After changes to retrieval, corpus/index build, citation/grounding logic, or dataset contracts.
