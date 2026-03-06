# Review Pass 5 Action Plan

Source: `docs/review_pass_5.docx`  
Prepared: March 6, 2026

## Scope

This plan converts the concerns, quick wins, and long-term improvements from the review report into ordered single tasks.

It intentionally excludes work that is already documented as completed, operationalized, or already gated elsewhere in the repo.

## Guardrails

- Keep KG-related runtime work quarantined until the KG is part of the supported production CLI path.
- Do not re-plan work already covered by existing accepted docs, gates, or runbooks unless the review report identifies a real defect or drift.
- Prefer changes that tighten the supported runtime surface (`service/api_server`, CLI, corpus pipeline, packaging) before adding new research features.

## Already Covered; Do Not Re-Plan

The following are already represented by existing docs, gates, or operational material and should not be duplicated in the next work passes unless a specific defect is found:

- Offline snapshot validation and baseline runbook flows in `RUNBOOK.md`, `docs/runbook_baseline.md`, and `docs/offline_snapshot_spec.md`.
- Golden groundedness gate, dataset validation, and citation/trace-pack checks described in `RUNBOOK.md` and `docs/done_done_checklist.md`.
- Audit ledger minimum-event and integrity requirements in `docs/audit_event_requirements.md`.
- Identifier and canonical KG namespace policy in `docs/identifier_policy.md` and `docs/kg_boundary_and_iri_strategy.md`.
- Existing KG freeze, integrity, export, provenance, and incremental-build controls already documented in `RUNBOOK.md`.

## Ordered Tasks

### Task 1: Fix `bundle build` repo-root resolution

Summary: Restore the documented operator path by correcting repo-root discovery in the bundle CLI and locking it with a real end-to-end CLI test.

Prompt:

```text
Model: GPT-5.3-codex
Reasoning: medium

Repair the broken `bundle build` command identified in `docs/review_pass_5.docx`.

Goals:
- Fix repo-root resolution in `earCrawler/cli/bundle.py`.
- Prefer a shared repo-root helper if one already exists; otherwise add a minimal reusable helper instead of hardcoding multiple path rules.
- Add a real CLI integration test that exercises the command end to end and would fail on the current bug.

Constraints:
- Do not broaden scope beyond the bundle CLI path and its immediate helper/test coverage.
- Preserve existing operator-facing behavior unless the current behavior is clearly broken.
- Use Windows-friendly path handling.

Deliverables:
- Code fix.
- Regression test.
- Brief note in test names/comments describing the failure mode being prevented.

Acceptance:
- `bundle build` resolves paths correctly from the supported repo layout.
- The new test fails before the fix and passes after it.
```

### Task 2: Repair live EAR loader field normalization

Summary: Fix live ingestion under-production by normalizing the client response fields the loader actually receives.

Prompt:

```text
Model: GPT-5.3-codex
Reasoning: medium

Fix the live EAR ingestion defect from `docs/review_pass_5.docx` where the loader expects `detail["html"]` but the client returns `body_html` / `body_text`.

Goals:
- Normalize the response contract inside the EAR loader path.
- Make the loader robust to the currently observed field names without hiding malformed payloads.
- Add targeted tests for the live-path normalization behavior.

Constraints:
- Do not redesign the client API unless required for correctness.
- Preserve deterministic fixture behavior for offline tests.
- Fail clearly if none of the expected content fields are present.

Deliverables:
- Loader fix.
- Unit tests covering `body_html`, `body_text`, and missing-content behavior.

Acceptance:
- Live-path code consumes the actual client payload shape.
- Tests protect against future field drift.
```

### Task 3: Make packaging metadata single-source-of-truth

Summary: Remove the split-brain between `setup.py`, `pyproject.toml`, and dependency declarations so releases and installs are coherent.

Prompt:

```text
Model: GPT-5.3-codex
Reasoning: high

Resolve the packaging metadata inconsistency called out in `docs/review_pass_5.docx`.

Goals:
- Make `pyproject.toml` the sole source of truth for package metadata and entrypoints, or fully align any remaining legacy packaging file if removal is unsafe.
- Eliminate contradictory version, dependency, and entrypoint declarations.
- Add or update a clean-environment packaging smoke test.

Constraints:
- Prefer deleting stale packaging metadata over keeping duplicate declarations.
- Do not change supported install surfaces unless needed to remove inconsistency.
- Keep the result compatible with the repo's existing release flow in `RUNBOOK.md`.

Deliverables:
- Packaging metadata cleanup.
- Smoke test or CI check that verifies install/build entrypoints from a clean environment.
- Any minimal doc updates required to keep packaging instructions accurate.

Acceptance:
- There is one authoritative metadata path.
- A clean install/build smoke test passes and would catch future drift.
```

### Task 4: Correct keyring-backed API auth semantics

Summary: Replace label-existence authentication with actual secret verification and regression coverage.

Prompt:

```text
Model: GPT-5.3-codex
Reasoning: high

Fix the API key authentication flaw described in `docs/review_pass_5.docx` for keyring-backed auth.

Goals:
- Ensure presented credentials are verified against stored secrets, not merely against key presence.
- Use constant-time comparison for secret checks.
- Add focused tests for valid key, invalid key, wrong label, and missing key cases.

Constraints:
- Preserve conservative security defaults.
- Avoid leaking secrets in logs, exceptions, or test fixtures.
- Keep the interface understandable for operators using the current secret-management flow.

Deliverables:
- Auth fix in the supported API auth path.
- Regression tests covering the corrected semantics.

Acceptance:
- Authentication succeeds only when the presented secret matches the stored secret.
- Tests would fail on the previous label-existence behavior.
```

### Task 5: Make rate limiting actually thread-safe

Summary: Close the token-consumption race so concurrency does not bypass the intended limit.

Prompt:

```text
Model: GPT-5.3-codex
Reasoning: high

Repair the rate-limiter race identified in `docs/review_pass_5.docx`.

Goals:
- Keep refill and token consumption within one correct critical section, or replace the local implementation with an equally small but correct alternative.
- Add concurrency-oriented tests that would expose the current race.

Constraints:
- Do not introduce distributed infrastructure in this task.
- Preserve the existing single-node deployment assumptions unless required for correctness.
- Keep the implementation easy to reason about under Windows-hosted service execution.

Deliverables:
- Corrected limiter implementation.
- Regression tests exercising concurrent access.

Acceptance:
- Concurrent requests cannot over-consume tokens because of the old unlocked path.
- Tests are deterministic enough for CI.
```

### Task 6: Offload sync RAG work from async API handlers

Summary: Stop blocking the event loop by moving synchronous retrieval/generation off the async request path.

Prompt:

```text
Model: GPT-5.3-codex
Reasoning: high

Fix the async blocking problem in the RAG API handlers described in `docs/review_pass_5.docx`.

Goals:
- Identify synchronous retrieval/generation work still being called directly from async handlers.
- Move that work behind `asyncio.to_thread`, a bounded worker strategy, or another minimal safe offload mechanism.
- Preserve request/response behavior and existing strict-output/grounding controls.
- Add targeted tests for handler behavior and any new helper boundary.

Constraints:
- Do not redesign the whole RAG architecture in this task.
- Keep KG quarantine intact; this task is about async correctness, not feature expansion.
- Avoid unbounded background work or hidden thread proliferation.

Deliverables:
- Async-safe handler changes.
- Tests that cover the new offload boundary.
- Short implementation notes in code comments only where the concurrency behavior would otherwise be unclear.

Acceptance:
- Async handlers no longer execute the known heavy sync path inline.
- Existing API behavior remains stable.
```

### Task 7: Resolve telemetry RBAC and CI-doc drift together

Summary: Decide the intended access policy for telemetry status, then align code, tests, and `docs/ci.md` to the actual behavior.

Prompt:

```text
Model: GPT-5.4
Reasoning: high

Address the test/document drift reported in `docs/review_pass_5.docx`.

Goals:
- Decide whether telemetry status is reader-safe or operator-only.
- Implement that policy consistently in CLI code and tests.
- Update `docs/ci.md` so it matches the actual workflow behavior instead of aspirational behavior.

Constraints:
- Keep the decision conservative if there is any ambiguity about information exposure.
- Do not leave policy inferences hidden in tests; make the intended behavior explicit in code and docs.
- Scope this task to telemetry-status RBAC and CI-doc accuracy only.

Deliverables:
- Policy decision implemented in code.
- Tests updated to match the intended behavior.
- `docs/ci.md` corrected.

Acceptance:
- The telemetry CLI tests pass under the chosen policy.
- CI documentation matches the workflow that actually runs.
```

### Task 8: Quarantine unsupported runtime surfaces

Summary: Make the supported runtime boundary explicit by retiring, documenting, or warning on legacy service paths that should not be used.

Prompt:

```text
Model: GPT-5.4
Reasoning: high

Use the review findings to tighten the runtime boundary without adding new features.

Goals:
- Identify unsupported legacy runtime surfaces called out in `docs/review_pass_5.docx`.
- Quarantine them by deprecation warnings, documentation changes, or removal when safe.
- Make `service/api_server` and the supported CLI/operator paths the only clearly documented runtime surface.

Constraints:
- Do not remove code that is still required by current tests or supported workflows without providing a safe migration path.
- Keep KG work quarantined; this task is about boundary clarity, not enabling more KG runtime paths.
- Prefer explicit docs and warnings over large deletions if usage is uncertain.

Deliverables:
- Boundary-tightening changes.
- Doc updates showing supported versus legacy paths.
- Any minimal tests needed to lock the supported path.

Acceptance:
- A new contributor can tell which runtime surfaces are supported and which are not.
- Unsupported paths are no longer silently implied as production-ready.
```

### Task 9: Replace fragile resource loading and raw SPARQL substitution

Summary: Remove repo-relative file assumptions and injection-prone string substitution in loaders and related resource access.

Prompt:

```text
Model: GPT-5.3-codex
Reasoning: high

Fix the resource-loading and SPARQL-construction issues called out in `docs/review_pass_5.docx`.

Goals:
- Replace repo-relative resource access with packaged-resource access where appropriate.
- Remove raw string substitution for SPARQL literals and use safe escaping or a parameterized construction approach.
- Add focused tests around the updated resource and query-loading behavior.

Constraints:
- Limit scope to the affected loaders and the smallest shared helper surface needed.
- Preserve current query behavior while tightening safety and packaging robustness.
- Do not start a broad query framework rewrite in this task.

Deliverables:
- Safer resource-loading path.
- Safer SPARQL construction path.
- Regression tests.

Acceptance:
- The affected code works from packaged/resource-based execution contexts.
- User-controlled literals no longer pass through raw string replacement.
```

### Task 10: Redesign corpus identity to preserve provenance across duplicate text

Summary: Stop collapsing distinct records that share paragraph text by moving to a stable source-aware identity scheme.

Prompt:

```text
Model: GPT-5.4
Reasoning: extra high

Design and implement a source-aware corpus identity/provenance scheme to replace text-hash-only identity, as recommended in `docs/review_pass_5.docx`.

Goals:
- Define a canonical identity strategy that uses source + stable identifier + content fingerprint as needed.
- Preserve or explicitly model multi-provenance when identical text appears across sections or sources.
- Update downstream corpus/KG/eval references only where necessary to keep lineage correct.
- Provide a migration plan for existing artifacts and tests.

Constraints:
- Do not break canonical citation identifiers already governed by `docs/identifier_policy.md` and `docs/kg_boundary_and_iri_strategy.md`.
- Keep KG quarantined from production enablement; this task may update KG emitters/artifacts for correctness, but it must not make KG a supported production dependency.
- Minimize churn in stable public IDs unless correctness requires it.

Deliverables:
- Design note or ADR for the new identity scheme.
- Implementation in the affected corpus path.
- Required downstream updates and migration/backfill logic if needed.
- Regression coverage proving duplicate text no longer collapses provenance.

Acceptance:
- Distinct source records with identical text remain distinct in lineage.
- The identity scheme is documented and test-protected.
```

### Task 11: Add clean-room install and release smoke tests

Summary: Prove the packaging story from outside a source checkout so release artifacts match the documented support model.

Prompt:

```text
Model: GPT-5.3-codex
Reasoning: high

Add clean-room packaging/install smoke coverage based on the gaps identified in `docs/review_pass_5.docx`.

Goals:
- Verify wheel/install/entrypoint behavior from a clean environment.
- Exercise the minimum supported operator workflow without assuming a source checkout.
- Integrate the smoke test into CI or release validation at the smallest reliable point.

Constraints:
- Reuse the existing Windows-first release flow from `RUNBOOK.md`.
- Keep this task focused on validation; do not redesign installers or bundle formats here.
- Fail fast on missing packaged resources or entrypoint drift.

Deliverables:
- Clean-room smoke test automation.
- Minimal workflow integration or documented release gate.

Acceptance:
- Release validation catches missing resources, bad entrypoints, or source-checkout assumptions before shipping.
```

### Task 12: Define the KG quarantine exit gate

Summary: Write the explicit criteria that must be met before KG-backed features can leave quarantine and join the supported production CLI path.

Prompt:

```text
Model: GPT-5.4
Reasoning: high

Create a short design/operations document that formalizes the KG quarantine exit gate, using `docs/review_pass_5.docx` plus the existing KG policy docs.

Goals:
- Define what "KG is part of the production CLI" means in operational terms.
- List the technical, testing, packaging, and operator prerequisites required before unquarantining KG-backed runtime features.
- State what remains explicitly out of scope until those prerequisites are met.

Constraints:
- Do not unquarantine any feature in this task.
- Align with `docs/kg_boundary_and_iri_strategy.md` and current runbook expectations.
- Keep the output actionable and audit-friendly, not aspirational.

Deliverables:
- A concise document under `docs/` describing the exit criteria and decision gate.

Acceptance:
- Future KG-related work has a clear go/no-go gate.
- The repository no longer relies on implicit assumptions about when KG is production-ready.
```

### Task 13: Provision real Jena text search only after the KG exit gate passes

Summary: Add the missing Jena text-indexed search path and an end-to-end smoke test, but only after KG quarantine is formally lifted.

Prompt:

```text
Model: GPT-5.3-codex
Reasoning: high

This task is blocked on completion of the KG quarantine exit gate.

After that gate passes, implement the missing Jena text search support identified in `docs/review_pass_5.docx`.

Goals:
- Configure the required Jena text index in the supported assembler/runtime path.
- Ensure the search template path works against a real dataset, not only stubs.
- Add an end-to-end smoke test for text-backed entity search.

Constraints:
- Do not ship this behind an implicit or partially supported runtime path.
- Keep the runtime/documentation boundary explicit.

Deliverables:
- Assembler/runtime configuration updates.
- Search smoke test against a real indexed dataset.
- Minimal operator documentation for the supported setup.

Acceptance:
- Search works on a real text-enabled Fuseki dataset.
- The feature is only considered supported once its runtime path is documented and tested.
```

### Task 14: Implement hybrid retrieval behind the same gate

Summary: Add BM25+dense retrieval and evaluation once the supported KG/CLI runtime boundary is settled.

Prompt:

```text
Model: GPT-5.4
Reasoning: extra high

This task is blocked on completion of the KG quarantine exit gate and the stabilization tasks above.

Design and implement the hybrid retrieval layer requested by `docs/review_pass_5.docx`.

Goals:
- Define the hybrid retrieval architecture (BM25 + dense retrieval + fusion/reranking as justified).
- Integrate it into the supported retrieval/RAG path without weakening existing grounding and strict-output controls.
- Extend evaluation so gains are measured against the current offline gates and production-like runs.

Constraints:
- Preserve deterministic/offline evaluation modes.
- Do not entangle this work with model-training ambitions.
- Keep KG optional until KG-backed runtime is fully supported.

Deliverables:
- Design note.
- Implementation.
- Evaluation additions and comparative benchmarks.

Acceptance:
- Hybrid retrieval is measurable, tested, and justified by evaluation rather than implied by docs alone.
```

### Task 15: Add temporal/effective-date reasoning

Summary: Introduce date-aware regulatory applicability after core runtime correctness and retrieval stabilization are complete.

Prompt:

```text
Model: GPT-5.4
Reasoning: extra high

This task is blocked on completion of the stabilization tasks and should follow retrieval architecture hardening.

Implement temporal/effective-date reasoning as a first-class feature, based on the gap identified in `docs/review_pass_5.docx`.

Goals:
- Define how effective dates, versions, and applicability windows enter corpus/KG/retrieval decisions.
- Implement date-aware answer selection or refusal behavior where evidence is temporally ambiguous.
- Add evaluation coverage for time-sensitive questions.

Constraints:
- Do not approximate with undocumented heuristics.
- Preserve current deterministic/offline testability as much as possible.
- Keep public behavior conservative when temporal evidence is incomplete.

Deliverables:
- Design note for temporal semantics.
- Implementation in the minimum necessary runtime path.
- Evaluation/test additions for temporally sensitive cases.

Acceptance:
- Time-sensitive questions are answered or refused based on explicit temporal logic rather than latest-only assumptions.
```

### Task 16: Resolve the model-training/scaffolding ambiguity

Summary: Either build a real experimentation stack or remove misleading empty scaffolding so the repo stops overstating its capabilities.

Prompt:

```text
Model: GPT-5.4
Reasoning: high

Address the mismatch between research aspirations and shipped capabilities noted in `docs/review_pass_5.docx`.

Goals:
- Evaluate whether `agent/`, `models/legalbert/`, `quant/`, and related scaffolding should become a supported experimentation path or be explicitly demoted/removed.
- Produce a concrete recommendation and implement the smallest correct follow-through.

Constraints:
- Prefer honesty of repository surface area over aspirational placeholders.
- Do not start a large training program unless the repo is ready to support it operationally.

Deliverables:
- Recommendation memo or ADR.
- Corresponding cleanup or initial experimentation framework work.

Acceptance:
- The repo no longer implies a training capability that does not actually exist.
```

### Task 17: Formalize the runtime-versus-research boundary

Summary: Reduce onboarding ambiguity by making the supported core runtime and experimental areas explicit in repo docs and structure.

Prompt:

```text
Model: GPT-5.4
Reasoning: high

Use the findings from `docs/review_pass_5.docx` to formalize the boundary between supported runtime code and research/experimental material.

Goals:
- Define what belongs to the supported product/runtime surface versus research or exploratory work.
- Update top-level docs and any minimal repo metadata needed to reflect that boundary.
- Reduce the chance that contributors mistake experimental artifacts for production commitments.

Constraints:
- Avoid a disruptive repo split in this task unless the benefits are overwhelming and migration is clearly justified.
- Keep the result compatible with current Windows-first operator workflows.

Deliverables:
- Boundary documentation updates.
- Any light-touch structural markers needed to make that boundary obvious.

Acceptance:
- A new contributor can distinguish supported runtime components from research scaffolding without reading the full codebase.
```

## Recommended Execution Sequence

Run Tasks 1 through 7 first as the stabilization tranche.  
Run Tasks 8 through 11 next as the architecture-hardening tranche.  
Complete Task 12 before starting any KG-unquarantine or KG-runtime expansion work.  
Treat Tasks 13 through 17 as explicitly blocked follow-on work, not current production commitments.
