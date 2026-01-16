# Conventions (logic-safe changes)

## Defaults
- Prefer logic-correctness over refactors or style-only edits.
- Make the smallest change that fixes the issue.
- Preserve public contracts (CLI/API/file formats/signatures) unless the task explicitly requires change.

## Before finalizing a change
- Search for call sites and references (prefer `rg`) and confirm they remain correct.
- Consider boundary conditions, error paths, and state/side effects.
- If removing anything, follow `.agents/60-cleanup-policy.md` (deletion plan + evidence).

## Quick logic audit checklist
- Boundaries/indexing (off-by-one, empty inputs, missing keys)
- Conditionals/booleans (operator mistakes, inverted checks)
- Loop control/flow (early returns, missed breaks, infinite loops)
- State/side effects (mutability, shallow vs deep copies, idempotence)
- Types/data contracts (None handling, coercions, schema assumptions)
- Security logic (authz gates, input validation paths, bypassable flows)
- Execution sequencing (preconditions met before use, correct ordering)

## When behavior changes materially
- Update the relevant docs under `docs/` and agent docs under `.agents/` as needed.
- If repo behavior changes in a “major” way (new/moved CLI commands, pipeline changes), update `Research/repo_quiz/questions.json` and `Research/repo_quiz/repo_sections.md`.
