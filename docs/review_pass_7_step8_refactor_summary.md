# Review Pass 7 - Step 8 Refactor Summary

Status: complete

This pass refactors the largest RAG, CLI, and eval modules behind stable boundaries while preserving supported behavior.

## New boundaries introduced

- `earCrawler/rag/retriever_citation_policy.py`
  - Extracts prompt/citation policy from retriever execution flow.
  - `earCrawler.rag.retriever` keeps compatibility aliases:
    - `_extract_ear_section_targets`
    - `_apply_citation_boost`
    - `_canonical_section_id` (internal use)

- `earCrawler/cli/rag_workflows.py`
  - Extracts `rag-index` workflow execution from Click command definitions.
  - `earCrawler/cli/rag_commands.py` remains the command/rendering surface.

- `earCrawler/cli/eval_workflows.py`
  - Extracts `eval run-rag` and `eval fr-coverage` orchestration and summary-line generation.
  - `earCrawler/cli/eval_commands.py` remains the command/rendering surface.

- `scripts/eval/eval_rag_metrics.py`
  - Extracts citation aggregation and ablation/retrieval comparison metrics builders.
  - `scripts/eval/eval_rag_llm.py` keeps compatibility wrappers:
    - `_evaluate_citation_quality`
    - `_finalize_citation_metrics`
    - `_aggregate_citation_scores`
    - `_ablation_metrics`
    - `_build_ablation_summary`
    - `_build_retrieval_compare_summary`

- `scripts/eval/eval_rag_reporting.py`
  - Extracts markdown summary construction from `evaluate_dataset`.

## Module-size report (line counts)

Threshold used for hotspot tracking: `> 600` lines.

| Module | Before | After |
|---|---:|---:|
| `scripts/eval/eval_rag_llm.py` | 2244 | 2076 |
| `earCrawler/rag/retriever.py` | 1126 | 990 |
| `earCrawler/cli/rag_commands.py` | 691 | 679 |
| `earCrawler/cli/eval_commands.py` | 687 | 560 |

New extracted modules:

- `scripts/eval/eval_rag_metrics.py`: 243
- `scripts/eval/eval_rag_reporting.py`: 98
- `earCrawler/rag/retriever_citation_policy.py`: 137
- `earCrawler/cli/rag_workflows.py`: 115
- `earCrawler/cli/eval_workflows.py`: 210

## Behavior-preservation evidence

Targeted regression suites run after extraction:

- `py -m pytest -q tests/rag/test_retriever_citation_boost.py tests/cli/test_rag_index_rebuild_index.py tests/cli/test_rag_index_snapshot_validation.py tests/cli/test_eval_cli.py tests/eval/test_answer_scoring_modes.py tests/eval/test_retrieval_compare.py`
  - Result: `22 passed`

- `py -m pytest -q tests/golden/test_eval_artifacts.py tests/golden/test_citation_regressions.py tests/audit/test_required_events_and_integrity.py`
  - Result: `8 passed`

- `py -m pytest -q tests/rag/test_retriever.py tests/rag/test_index_builder.py`
  - Result: `18 passed`
