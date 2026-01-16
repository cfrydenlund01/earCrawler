# Deletion Plan (2026-01) — repo hygiene

This plan lists cleanup candidates with evidence. No deletions should occur until this plan exists.

## Generated artifacts accidentally committed

### Delete
- `.cache/java/fuseki-5.3.0.zip`
  - Evidence: `.gitignore` already ignores `.cache/`, indicating this path should be runtime cache only.
  - Evidence: `scripts/verify-java-tools.ps1` downloads `fuseki-<version>.zip` into `.cache/java/` on demand (not a required repo input).
- `.cache/java/jena-5.3.0.zip`
  - Evidence: `.gitignore` already ignores `.cache/`, indicating this path should be runtime cache only.
  - Evidence: `scripts/verify-java-tools.ps1` downloads `jena-<version>.zip` into `.cache/java/` on demand (not a required repo input).

## Deprecated / duplicate packaging scaffolding

### Delete
- `setup.py`
  - Evidence: No references from CI workflows, scripts, or docs (`rg` only finds it inside itself).
  - Evidence: Metadata conflicts with `pyproject.toml` (version and console script name differ).
- `earCrawler/requirements.txt`
  - Evidence: Not referenced by CI/scripts; repo dependency sources are `pyproject.toml` + `requirements*.txt` at the repo root.
  - Evidence: Pin set is stale (does not match current runtime deps in `pyproject.toml`).
- `earCrawler/CHANGELOG.md`
  - Evidence: Stale single-entry changelog; repo changelog lives at `CHANGELOG.md`.
  - Evidence: Not referenced by release workflow/scripts.
- `earCrawler/README.md`
  - Evidence: Duplicates and defers to root `README.md`.
  - Evidence: Not referenced by tooling; does not participate in packaging metadata.
- `scaffold.ps1`
  - Evidence: One-time project bootstrap script that writes the stale `earCrawler/requirements.txt`, `earCrawler/README.md`, `earCrawler/CHANGELOG.md`.
  - Evidence: Not referenced by CI/scripts/docs.

## Internal planning artifacts (keep, but move out of the root)

### Archive (git-tracked)
- `prompt.txt`
  - Evidence: Not referenced by CI/scripts/docs; appears to be internal prompt scaffolding.
- `next_prompt.txt`
  - Evidence: Not referenced by CI/scripts/docs; appears to be internal prompt scaffolding.
- `Short Roadmap.docx`
  - Evidence: Not referenced by CI/scripts/docs; only referenced from `prompt.txt`.
- `title-15.json`
  - Evidence: Not referenced by CI/scripts/docs (`rg` finds no references).

