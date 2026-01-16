# Research & Experimentation Workflow

Use this document only when the task is research/experimentation oriented (planning experiments, summarizing research docs, advancing milestones, or updating `Research/decision_log.md`).

## Context-minimizing startup routine (required for research tasks)
1) Update the research indexes (preferred over manual scans):
   - `py scripts/research_index.py`
2) Read *only* these two files next:
   - `Research/index.json` (inventory + headings/flags)
   - `Research/knowledge_cache.json` (extracted sections for quick lookup)
3) Decide which single doc (if any) must be opened based on the index/caches; avoid opening multiple DOCX files in one session.
4) Keep generated research indexes/caches local unless explicitly asked to commit them (the repo typically ignores most of `Research/`).

## Definition: research endpoint
A research endpoint is reached when the milestone/step has verifiable repo artifacts (tests passing, generated bundles/reports, updated docs) and those artifacts can be pointed to by path.

## Workflow (analyze → verify → summarize → advance)
1) Analyze
   - Use the index/caches to locate the most relevant source material; do not recursively browse `Research/`.
   - If a DOCX must be consulted, extract only the needed headings/sections (prefer the cached extracts from `scripts/research_index.py` over copying large excerpts).
2) Verify
   - Confirm the corresponding artifacts exist (files, reports, datasets) and run the smallest relevant test/build command(s).
3) Summarize
   - Append a short, timestamped entry to `Research/decision_log.md` including: what changed, what was verified, and links/paths to the artifacts.
4) Advance
   - Propose the next concrete experiment step with a command-level plan. Prefer using existing helper scripts (for prompts: `scripts/generate_prompts_from_outline.py`, `scripts/generate_immediate_prompts.py`).

## Do / don't
- Do use the index/caches to avoid loading large research docs into context.
- Do keep conclusions and next steps in `Research/decision_log.md` with paths to verifiable artifacts.
- Do update `Research/repo_quiz/questions.json` and `Research/repo_quiz/repo_sections.md` when repo behavior changes materially.
- Don't duplicate large content across research documents; link/point to the canonical source instead.
- Don't change CLI/API/file format contracts as part of “research” unless explicitly required and verified by tests.

## Document conventions (when present locally)
- Redlined proposal (canonical milestone mapping): `Research/EAR_AI_Training_Proposal_redlined.docx`
- Strategic roadmap: `Research/Explainable Regulatory LLMs_ Current Landscape and Strategic Roadmap.docx`
- Repo quiz artifacts (keep current when repo behavior changes):
  - `Research/repo_quiz/questions.json`
  - `Research/repo_quiz/repo_sections.md`

## Validation expectations
- After any research-driven code change, run a focused test subset and record pass/fail in `Research/decision_log.md`.

## Safety / privacy
- Treat research documents and caches as potentially sensitive; never print secret-like values or large copied excerpts.
