# Cleanup Policy

## Non-negotiables for removals
- Do not delete tracked files until a “Deletion Plan” exists with evidence per item.
- Prefer moving uncertain items to `archive/YYYY-MM/` (git-tracked) with a short README over deleting.
- Add/adjust `.gitignore` for generated artifacts when appropriate.

## Evidence expectations
Use multiple signals:
- `rg` references (imports/paths/config/scripts/workflows)
- CI/workflow usage (`.github/workflows/*.yml`)
- Runtime/config usage (env vars read vs defined; config files referenced by entrypoints)
- Git history (old/obsolete naming + never referenced)

## After cleanup
- Run the repo’s standard format/lint/test/build commands (see `.agents/40-testing-and-quality.md` and `.agents/20-pipeline.md`).
- Fix failures caused by the cleanup; do not expand scope to unrelated issues.

