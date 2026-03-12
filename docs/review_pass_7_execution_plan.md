# Review Pass 7 Execution Plan

Source basis: `docs/Run Pass 7.rtf` only.

This plan keeps the current project strength intact: a clear supported single-host path with deterministic artifacts, explicit feature gating, and strong existing test coverage. The ordering below prioritizes defects and gaps that affect the supported product boundary first, then adds release evidence, then resolves deferred scope decisions.

## Step 1: Lock the Production-Candidate Scope

Explanation: The review shows the supported single-host deterministic path is the closest thing to completion, while KG-backed search, hybrid retrieval, and multi-instance behavior are still gated or deferred. Freeze the completion target around the supported path first so the remaining work does not expand unnecessarily.

Preferred model: `GPT-5.4`

Reasoning level: `high`

Why this level: this is a product-boundary and release-definition task with meaningful tradeoffs, but it does not require the broader architectural synthesis that would justify `extra high`.

Prompt:

```text
Use only the current repository contents and produce a production-candidate scope memo for earCrawler that defines exactly what is in scope, out of scope, and release-blocking for the next completion milestone.

Requirements:
- Treat the supported target as the Windows single-host deterministic pipeline and supported FastAPI read facade.
- Explicitly mark `/v1/search`, KG-backed hybrid retrieval, and multi-instance deployment as either deferred or non-blocking unless the codebase already proves they are ready.
- Convert the review findings into a concise acceptance checklist with release-blocking evidence.
- Output a markdown document in docs/ named `production_candidate_scope_pass7.md`.
- Do not invent capabilities that are not implemented.
- Keep the document operational and decision-oriented, not aspirational.
```

## Step 2: Repair the NSF Corpus-to-KG Entity Contract

Explanation: The review identifies this as the highest-risk implementation defect because entity names are lost on a supported KG path. Fixing the contract drift first removes silent data loss and stabilizes later validation, search, lineage, and benchmark work.

Preferred model: `GPR-5.3-codex`

Reasoning level: `high`

Why this level: the defect is concrete and cross-file, with clear expected behavior and test implications; `high` is sufficient and `extra high` would be unnecessary overhead.

Prompt:

```text
Inspect only the files needed to fix the NSF entity contract drift between corpus build output, KG emission, and tests.

Goals:
- Introduce or reuse one shared typed entity schema for the NSF path.
- Make the KG emitter accept the real built-corpus shape instead of a legacy assumption.
- Update or replace tests so they validate the current supported shape.
- Add at least one integration-style regression test that starts from real `corpus build` output and verifies the emitted TTL preserves NSF entity names.

Constraints:
- Keep the change limited to the supported path.
- Do not broaden scope into search or retrieval.
- Preserve existing supported behavior outside the defect.

After making changes, run the smallest relevant test subset and report the results.
```

## Step 3: Promote Semantic KG Checks into Release Gates

Explanation: The review shows SHACL-only gating allows semantically incomplete KG artifacts to pass. Tightening this gate directly builds on the project’s validation-heavy strengths and prevents the supported path from shipping structurally valid but incomplete artifacts.

Preferred model: `GPR-5.3-codex`

Reasoning level: `high`

Why this level: this is a targeted code-and-CI change with some policy judgment, but it is still bounded enough that `high` is the right level.

Prompt:

```text
Update the KG validation and CI flow so the supported release path fails on the minimum necessary semantic sanity checks, not just SHACL.

Tasks:
- Identify the existing sanity checks that should be release-blocking for the supported path.
- Promote those checks into the blocking validation flow, or create an explicit allowlist/waiver mechanism with recorded rationale if a check must remain non-blocking.
- Update CI and any relevant smoke/integration tests accordingly.
- Prefer a small, defensible initial blocking set over a large speculative one.

Deliverables:
- Code changes
- Test updates
- A short markdown note in docs/ explaining which semantic checks are blocking and why

Run the relevant validation/test commands and summarize the outcome.
```

## Step 4: Add a Supported-Path End-to-End Semantic Contract Test

Explanation: The review calls out the absence of an end-to-end contract test that starts from supported corpus output and verifies semantic KG expectations. This step converts current strengths in determinism and testing breadth into a single regression guard for the core product path.

Preferred model: `GPR-5.3-codex`

Reasoning level: `high`

Why this level: the implementation spans multiple layers but remains mechanically test-focused and well-bounded by the supported flow.

Prompt:

```text
Create one supported-path end-to-end semantic contract test for earCrawler.

Test shape:
- Start from the supported corpus build path.
- Run corpus validation.
- Emit KG artifacts.
- Run the semantic assertions that matter for the supported path.

Requirements:
- Reuse real supported commands, fixtures, or builders where possible.
- Assert more than schema validity; include at least one semantic expectation that would catch the defects described in the review.
- Keep runtime practical for CI.
- Place the test in the most appropriate existing test area and name it clearly.

After implementation, run the relevant test target and report whether the test passes.
```

## Step 5: Align Access-Control Documentation with Actual Behavior

Explanation: The review shows the docs currently overstate bearer-token role behavior. The safest path toward completion is to correct the docs immediately unless the implementation already contains a small, auditable token-role mechanism that can be finished without expanding the security surface.

Preferred model: `GPT-5.4`

Reasoning level: `medium`

Why this level: the primary task is policy and documentation alignment; deeper reasoning is useful, but this does not warrant `high` unless the code strongly suggests finishing token-role mapping now.

Prompt:

```text
Review the current access-control documentation and implementation, then resolve the mismatch with the least risky change.

Decision rule:
- If bearer tokens do not actually grant roles in the current supported implementation, narrow the documentation immediately and add any missing tests or notes needed to prevent future confusion.
- Only implement token-to-role resolution if the codebase already has a near-complete, auditable design that can be finished cleanly without widening scope.

Deliverables:
- Updated docs
- Any necessary tests or small code changes
- A short note summarizing the final supported security behavior for operators

Stay strictly within the supported security model.
```

## Step 6: Formalize Versioned Data Contracts Across Core Artifacts

Explanation: The NSF drift issue is a symptom of a broader contract-management gap. Formalizing versioned contracts for corpus records, KG inputs, retrieval documents, and evaluation artifacts reduces future drift and makes later refactors safer.

Preferred model: `GPT-5.4`

Reasoning level: `high`

Why this level: this requires cross-cutting design judgment across multiple artifact surfaces, but it is still a contract-definition problem rather than a full architecture rewrite, so `extra high` is not necessary.

Prompt:

```text
Design a versioned contract strategy for earCrawler's core artifacts and write it as an implementation-ready markdown design in docs/.

Scope:
- Corpus records
- KG emitter inputs
- Retrieval documents
- Evaluation artifacts

Requirements:
- Use the existing supported-path architecture as the baseline.
- Propose explicit versioning, ownership boundaries, validation points, and migration rules.
- Show how the strategy would have prevented the NSF entity drift found in the review.
- Keep the design practical for incremental adoption, not a greenfield rewrite.
- Include a recommended implementation sequence that follows after the current P0 fixes.

Output a markdown file in docs/ with a focused, actionable design.
```

## Step 7: Implement the Local-Adapter Benchmark Runner and Release Evidence Path

Explanation: The review says the intended production benchmark plan exists but lacks an execution runner for the supported `/v1/rag/answer` path. This step creates the release evidence needed to decide whether the optional local-adapter mode is promotable or should remain non-blocking.

Preferred model: `GPR-5.3-codex`

Reasoning level: `high`

Why this level: the work is concrete and implementation-heavy, but depends on prior contract and validation cleanup more than on unusually deep reasoning.

Prompt:

```text
Implement the missing local-adapter benchmark runner for the supported `/v1/rag/answer` path.

Requirements:
- Reuse the existing benchmark plan and supported API path.
- Produce reproducible benchmark artifacts and metrics.
- Make outputs suitable for release evidence, not just ad hoc experimentation.
- Add the smallest useful CLI or script surface needed to run the benchmark repeatably.
- Wire the results into existing eval or release reporting if the repository already has a clear place for that.
- Add tests around the runner where practical.

Do not expand into unsupported search or hybrid retrieval behavior.

After implementation, run the benchmark in the smallest reasonable mode or a dry-run/test mode and summarize the results.
```

## Step 8: Refactor the Largest RAG, CLI, and Eval Modules Behind Stable Contracts

Status: complete on 2026-03-12. Implementation summary: `docs/review_pass_7_step8_refactor_summary.md`.

Explanation: The review points to concentrated complexity in a small number of large modules. This should happen after the key supported-path contracts and gates are stable, so the refactor reduces maintenance risk without destabilizing the release candidate.

Preferred model: `GPR-5.3-codex`

Reasoning level: `high`

Why this level: this is a multi-file refactor with real dependency management, but the contracts from prior steps should make `high` sufficient.

Prompt:

```text
Refactor the largest RAG, CLI, and eval modules into smaller units while preserving current supported behavior.

Refactor goals:
- Separate orchestration from provider adapters
- Separate prompt/policy logic from execution flow
- Separate metrics/reporting from command rendering
- Add or preserve contract tests around extracted boundaries

Constraints:
- Use the stabilized contracts and supported-path decisions from earlier work.
- Prefer incremental refactors with passing tests after each logical slice.
- Avoid behavior changes unless required to remove ambiguity or dead code.

At the end, summarize which modules were split, what boundaries were introduced, and what tests prove behavior was preserved.
```

## Step 9: Decide the Fate of Quarantined Search and Hybrid Retrieval

Explanation: The review is clear that `/v1/search` and KG-backed hybrid retrieval are not yet part of the credible supported product. This work is easier to execute and verify if the decision is split into repository-readiness assessment, support-impact analysis, recommendation drafting, and final documentation changes.

### Step 9.1: Inventory Actual Readiness of Quarantined Search and Hybrid Retrieval

Explanation: Before making a product decision, establish what is really implemented, tested, gated, and documented today for `/v1/search` and KG-backed hybrid retrieval.

Preferred model: `GPT-5.4`

Reasoning level: `high`

Why this level: this is primarily a repository-readiness assessment with some product-boundary judgment, but it does not yet require the full tradeoff synthesis of the final decision.

Prompt:

```text
Assess the actual repository readiness of quarantined `/v1/search` and KG-backed hybrid retrieval in earCrawler.

Requirements:
- Use only the current repository contents.
- Identify the real implementation surfaces, feature gates, tests, docs, and operational assumptions.
- Distinguish clearly between code that exists, code that is gated/quarantined, and code that is only described in docs.
- Produce a concise markdown readiness note in docs/ that lists:
  - what exists now
  - what is missing
  - what is risky or ambiguous
  - what would block supportability today

Do not make a promote/defer recommendation yet. Focus on evidence gathering.
```

### Step 9.2: Analyze Support, Validation, and Observability Burden

Explanation: Even if the features appear partially implemented, they should not be promoted unless the support, validation, and operator burden is understood explicitly.

Preferred model: `GPT-5.4`

Reasoning level: `high`

Why this level: this step is a structured operational analysis across testing, observability, and support expectations rather than a pure implementation review.

Prompt:

```text
Using the current repository and the Step 9.1 readiness note, analyze the support burden of promoting quarantined `/v1/search` and KG-backed hybrid retrieval.

Requirements:
- Evaluate what validation, CI, observability, operator documentation, and incident/debug tooling would be required for supported status.
- Identify which of those requirements already exist and which do not.
- Separate minimum supportability requirements from nice-to-have improvements.
- Produce a short markdown analysis in docs/ that compares:
  - support burden if promoted now
  - support burden if kept quarantined for the next release cycle

Do not make the final recommendation yet. Make the operational tradeoffs explicit.
```

### Step 9.3: Produce the Promotion-vs-Deferral Decision Memo

Status: complete on 2026-03-12. Decision memo: `docs/review_pass_7_step9_3_decision_memo.md`.

Explanation: Once implementation readiness and support burden are explicit, make the actual product decision with concrete exit criteria or concrete non-goals.

Preferred model: `GPT-5.4`

Reasoning level: `extra high`

Why this level: this is the highest-tradeoff part of the work because it combines product scope, technical readiness, support burden, validation needs, and operator expectations.

Prompt:

```text
Produce a decision memo for the future of quarantined `/v1/search` and KG-backed hybrid retrieval in earCrawler.

Inputs:
- the current repository
- the Step 9.1 readiness note
- the Step 9.2 support-burden analysis

Evaluate two paths:
- Promote them toward supported status
- Keep them quarantined/deferred for the next release cycle

Requirements:
- Base the decision on actual repository readiness, tests, operational implications, and the current supported product boundary.
- If promotion is recommended, define explicit exit criteria, required validation gates, and operator-facing prerequisites.
- If deferral is recommended, define explicit non-goals, continued quarantine expectations, and what would need to change before reconsideration.
- End with a clear recommendation and rationale.

Output a concise markdown memo in docs/ with a clear recommendation.
```

### Step 9.4: Apply the Decision to Docs, Gates, and Scope Notes

Status: complete on 2026-03-12. Alignment summary: `docs/review_pass_7_step9_4_alignment_summary.md`.

Explanation: The decision is only useful if the repository documentation and feature-boundary notes are updated so operators and future contributors are not left with ambiguous expectations.

Preferred model: `GPR-5.3-codex`

Reasoning level: `high`

Why this level: after the decision is made, this becomes a bounded implementation and documentation-alignment task rather than a broad strategic synthesis exercise.

Prompt:

```text
Apply the Step 9.3 decision to earCrawler's docs and any small gating/config surfaces that define the supported product boundary.

Requirements:
- Update the relevant docs, quarantine notes, and scope memos so they match the final decision exactly.
- If the decision is deferral, make sure supported-path docs do not imply `/v1/search` or KG-backed hybrid retrieval are supported.
- If the decision is promotion, update the docs to describe the supported boundary, required evidence, and operator expectations precisely.
- Make only the smallest code or config changes needed to keep the repository aligned with the written decision.

After changes, summarize which docs or gating surfaces were updated and why.
```

## Step 10: Harden Single-Host Operations and Release Packaging

Status: complete on 2026-03-12. Hardening summary: `docs/review_pass_7_step10_hardening_summary.md`.

Explanation: Once the supported product path and optional feature boundaries are settled, the final completion work is operational hardening for the single-host deployment model the review already considers credible. This step turns the current beta-like path into a production candidate with explicit lifecycle, backup, restore, and release-validation procedures.

Preferred model: `GPR-5.3-codex`

Reasoning level: `high`

Why this level: this is broad implementation work across scripts, packaging, and docs, but it follows established scope and does not need the deeper synthesis reserved for `extra high`.

Prompt:

```text
Harden earCrawler's supported Windows single-host deployment and release path.

Goals:
- Enforce the single-host support contract clearly in packaging and ops guidance.
- Add or tighten service lifecycle automation where it is currently incomplete.
- Add backup and restore procedures or drills for the supported deployment.
- Strengthen release validation evidence, including any signed or integrity-checked artifacts already supported by the repository patterns.
- Update operator docs so they match the implemented deployment story exactly.

Constraints:
- Do not design multi-instance support in this step.
- Keep the work focused on the supported production-candidate path.

After changes, run the most relevant validation steps and summarize what evidence now exists for single-host operations readiness.
```

## Deferred Step: Multi-Instance Architecture Only If It Becomes a Real Requirement

Explanation: The review explicitly states multi-instance correctness is not currently supported, and the project is closer to completion on the single-host path. Treat scale-out as a separate architecture effort only if a real requirement appears after the supported release candidate is complete.

Preferred model: `GPT-5.4`

Reasoning level: `extra high`

Why this level: introducing shared state for limits, cache, and coordination is a major architectural change with operational consequences, so `extra high` is appropriate if this work is ever activated.

Prompt:

```text
Design a multi-instance support strategy for earCrawler only if the product now requires horizontal scaling.

Requirements:
- Start from the current single-host assumptions and identify every process-local behavior that breaks under scale-out.
- Propose the minimum shared-state architecture needed for correctness.
- Cover rate limiting, caches, coordination, observability, deployment topology, and failure modes.
- Define a staged migration path from supported single-host to supported multi-instance.
- Include explicit reasons to defer this work if the requirement is still not real.

Output a markdown architecture proposal in docs/ and do not implement code unless the design clearly justifies it.
```
