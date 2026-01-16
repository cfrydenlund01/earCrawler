# AGENTS (canonical)

This is the single source of truth for agent instructions in this repo.

## Context budget (read-order rules)
1) Read only `AGENTS.md` and `.agents/00-index.md` first.
2) Then open the smallest relevant doc(s) under `.agents/` for the task at hand.
3) Prefer targeted search (`rg`) before opening files; when you do open a file, read only the smallest slice needed (for example: first ~200 lines or a specific symbol block).
4) Maintain a short "Working Set" list of paths currently in context; keep it small (aim ≤ 12) and prune it continuously (summarize each opened file in 1-3 bullets, then move on).
5) Avoid opening binaries (DOCX/PDF) or dumping large file contents by default; for research tasks use the indexed workflow in `.agents/70-research.md`.

## Safety
- Never print secret values (tokens, API keys, `.env`, credential exports). If you find secret-like material, propose remediation (gitignore + template + rotation guidance) without exposing values.

## Research / experimentation (when applicable)
- Follow `.agents/70-research.md` (run `py scripts/research_index.py` first; record outcomes in `Research/decision_log.md`).

## Docs
- Index: `.agents/00-index.md`
- Repo overview: `.agents/10-repo-overview.md`
- Pipeline/entrypoints: `.agents/20-pipeline.md`
- Conventions for changes: `.agents/30-conventions.md`
- Testing/quality: `.agents/40-testing-and-quality.md`
- Env/secrets: `.agents/50-env-and-secrets.md`
- Cleanup policy: `.agents/60-cleanup-policy.md`
- Research workflow: `.agents/70-research.md`
