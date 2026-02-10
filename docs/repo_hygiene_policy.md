# Repo Hygiene Policy

## Objective
Keep the working tree predictable by clearly separating:
- source artifacts that must be committed,
- transient artifacts that must be ignored and periodically deleted.

## Current Untracked Classification (from `git status --porcelain`)

`keep+ignore`:
- `.pytest_tmp/` (pytest scratch artifacts; safe to delete anytime)
- `docs/Archive/` (local planning office documents, not source of truth)

`keep+commit`:
- `docs/kg_boundary_and_iri_strategy.md`
- `docs/kg_namespace_migration_plan.md`
- `docs/repo_hygiene_policy.md`
- `docs/runbook_baseline.md`
- `earCrawler/audit/hitl_events.py`
- `earCrawler/kg/iri.py`
- `earCrawler/kg/namespaces.py`
- `earCrawler/kg/paths.py`
- `earCrawler/rag/kg_expansion_fuseki.py`
- `earCrawler/sparql/kg_expand_by_section_id.rq`
- `earCrawler/trace/`
- `eval/multihop_slice.v1.jsonl`
- `scripts/kg/`
- `tests/audit/test_hitl_ingest.py`
- `tests/eval/test_dataset_namespace_refs.py`
- `tests/golden/test_multihop_ablation.py`
- `tests/kg/test_namespaces.py`
- `tests/rag/test_kg_expansion_fuseki.py`
- `tests/rag/test_pipeline_kg_expansion.py`
- `tests/trace/`

`delete`:
- None currently outside transient caches.

## Ignore Rules
The repository intentionally ignores:
- `.pytest_tmp/`
- `.pytest_cache/`
- `dist/` and `build/` outputs
- `docs/Archive/*.docx`
- `docs/Archive/*.xlsx`

## Cleanup Commands
```powershell
Remove-Item -Recurse -Force .pytest_tmp,.pytest_cache -ErrorAction SilentlyContinue
git status --porcelain
```

## Baseline Artifact Location
Baseline run artifacts are written to:
- `dist/baseline/<timestamp>/`

These are intentionally untracked. Persist durable summaries in `docs/` when needed.
