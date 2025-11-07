# Research AGENTS Guidelines

Scope
- This file governs agent behavior for the `Research/` directory and all subpaths.

Intent
- Make the agent “aware” of research documents and able to: analyze DOCX files, recognize completion endpoints, summarize conclusions, and advance to the next experimental steps. The priority remains project completion.

Required Startup Routine
1) Build/update the research index and caches:
   - Command: `py scripts/research_index.py`
   - Outputs:
     - `Research/index.json` — inventory of research DOCX files (paths, sizes, modified, headings, section-presence flags).
     - `Research/knowledge_cache.json` — lightweight extracted sections from redlined/summary docs for quick lookups (Current Alignment, Gaps, Milestones, etc.).
2) Skim `Research/index.json` before planning work; prefer listed docs rather than ad‑hoc scans.
3) When proposing or executing research steps, append to `Research/decision_log.md` (timestamp, summary, links).

Document Conventions
- Redlined proposal: `Research/EAR_AI_Training_Proposal_redlined.docx`
  - Contains the canonical sections: Current Alignment, Phase‑by‑Phase Gaps & Next Steps, Cross‑Cutting, Immediate Next Steps, Milestones.
- Strategic roadmap: `Research/Explainable Regulatory LLMs_ Current Landscape and Strategic Roadmap.docx`
- Venue outlines and risk variants live alongside summary docs; follow links in `Research_Manuscript_Outlines.docx`.

Definition: Endpoint
- A research endpoint is when a milestone or immediate step has verifiable artifacts in the repo (tests passing, generated bundles, updated docs).
- The agent should:
  - Detect target endpoints from the redlined/summary docs.
  - Check file system signals (e.g., produced data, bundles, reports) to verify completion.
  - Summarize conclusions and immediately propose next experiments from the variant outlines.

Workflow
- Analyze → Verify → Summarize → Advance:
  1. Parse relevant DOCX via `python-docx`.
  2. Verify artifacts (files, test results) that correspond to the targeted step.
  3. Summarize interim conclusions concisely into `Research/decision_log.md`.
  4. Choose the next experimental step from risk/venue outlines; prepare a concrete GPT‑5 prompt using the provided prompt scaffold.

Do/Don’t
- Do prioritize minimal, deterministic changes to the codebase and tests.
- Do track decisions and artifacts in `Research/decision_log.md`.
- Don’t duplicate content across DOCX — link via “Related Documents” sections instead.
- Don’t break public contracts (CLI, API, file formats) when implementing research steps.

Validation
- After any research step, run a focused test subset and update the decision log with pass/fail and pointers to artifacts.
