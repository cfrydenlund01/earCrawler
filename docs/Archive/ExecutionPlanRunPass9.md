# Execution Plan From RunPass9

Source: `docs/RunPass9.md` only.

Purpose: preserve the current strengths of the repository while improving the weaknesses and missing components identified in Run Pass 9, with phased execution prompts sized to the actual reasoning required.

## Execution Status (March 19, 2026)

- Phase 1: complete
- Phase 2: complete
- Phase 3: complete
- Phase 4: complete
- Phase 5.1: complete
- Phase 5.2: complete (real candidate validated at
  `dist/training/step52-real-candidate-gpt2b-20260319/`; decision:
  `keep_optional`)
- Phase 5.3: complete (dated search/KG evidence bundle generated on March 19,
  2026; recommendation: `Keep Quarantined`)

Reasoning-level guidance:
- Prefer `medium` for bounded code or documentation alignment work.
- Prefer `high` for cross-file implementation, architecture alignment, or evidence-package work.
- Use `extra high` only for a final whole-repo synthesis or a true go/no-go review that cannot be safely decomposed further.
- Keep the supported single-host baseline as the source of truth unless a step explicitly says otherwise.
- KG/search unquarantine work is conditional. Within the scope of Run Pass 9, only build evidence and perform a dated go/no-go review; do not promote quarantined KG-backed runtime behavior unless the existing gate is actually satisfied.

## Phase 1 - Stabilize the Supported Baseline

Goal: remove known deterministic failures and align supported-path code, tests, and training inputs with the documented default runtime.

### Step 1.1 - Fix the `/v1/search` performance gate mismatch
Description: align the budget gate with the actual default service shape so supported-path CI and local validation stop reporting false failures.
Model: `GPT-5.4-codex`
Reasoning: `medium`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Inspect only the files needed to resolve the deterministic failure in tests/perf/test_api_budget_gate.py::test_api_budget_gate_passes. Treat the documented default runtime shape as authoritative: `/v1/search` is quarantined and disabled by default unless the repo already proves otherwise. Update the perf harness, config, tests, and any nearby docs so the supported default budget gate measures the real default API surface. If there is a good reason to keep benchmark coverage for `/v1/search`, keep it explicitly separated as quarantined or optional coverage rather than part of the default gate. Preserve the current strengths called out in RunPass9, especially the narrow API boundary, explicit capability gating, and broad automated validation. Run only targeted verification for this change and summarize the final supported-vs-quarantined perf behavior.
```

### Step 1.2 - Unify the training corpus contract
Description: make one retrieval corpus path authoritative across code, config, and docs, then refuse inconsistent training inputs.
Model: `GPT-5.4-codex`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Implement the authoritative training corpus contract across the repository. Treat the indexed retrieval corpus path and metadata as authoritative unless the code shows a stronger current contract. Update the training runner, example configs, and training docs so they consistently point to the same corpus. Add a preflight that fails clearly when the configured corpus path, corpus digest, or document count does not match the related FAISS metadata or contract expectations. Preserve deterministic artifact behavior and avoid broad refactors. Add focused tests for the preflight and run the narrowest useful verification. Summarize the contract that is now enforced and any remaining intentionally experimental paths.
```

### Step 1.3 - Relabel or relocate the six-record derivative corpus
Description: remove the risk that a tiny experimental dataset is mistaken for the production corpus.
Model: `GPT-5.4-codex`
Reasoning: `medium`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Inspect the references to data/retrieval_corpus.jsonl and determine the smallest safe change that prevents it from being mistaken for the authoritative training corpus. If it is still useful, move it under an explicitly experimental or scratch location and update only the references that should continue to use it. If it is not useful, remove it from supported-path documentation and defaults. Preserve reproducibility and do not break legitimate research workflows without replacing them with a clearly documented alternative. Add or update targeted tests or docs checks if appropriate, then summarize the new data hygiene rule.
```

### Step 1.4 - Publish a repository status index
Description: give maintainers a single map of supported, optional, quarantined, generated, and archival surfaces.
Model: `GPT-5.4`
Reasoning: `medium`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Produce a concise repository status index that labels major top-level directories and important surfaces as supported, optional, quarantined, generated, or archival. Update the smallest set of onboarding documents needed so a new developer can find this index quickly. Keep the writeup factual and operational rather than aspirational. Preserve the current strengths around explicit support boundaries and Windows-focused operator clarity. Summarize what should now be treated as the default path for contributors.
```

## Phase 2 - Codify Existing Strengths as Invariants

Goal: preserve the best qualities of the repo by turning them into machine-checkable or operator-visible rules rather than relying on convention.

### Step 2.1 - Introduce a machine-readable capability registry
Description: centralize capability state so docs, tests, and packaging stop drifting.
Model: `GPT-5.4`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Design and implement the smallest practical machine-readable capability registry that records whether a feature is supported, optional, quarantined, legacy, generated, or archival as appropriate. Start with the capabilities and boundaries that RunPass9 identifies as most important: the default API surface, `/v1/search`, KG expansion, local-adapter serving, hybrid retrieval, and any other surface where support-state drift is already causing confusion. Wire this registry into the narrowest set of docs, tests, scripts, or contract-generation steps that materially reduce drift without creating a large framework. Preserve the current explicit support boundary, narrow API surface, and cautious default security posture. Add focused validation that proves the registry is being consumed correctly and summarize the new source of truth.
```

### Step 2.2 - Strengthen supported-path operator documentation
Description: make the current single-host, guarded, read-only posture even clearer and more operationally complete.
Model: `GPT-5.4`
Reasoning: `medium`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Tighten the supported-path operator documentation so it reinforces the repository’s existing strengths: single-host honesty, cautious default security, deterministic artifacts, explicit support boundaries, observability, and read-only API scope. Update only the docs that materially improve operator understanding of the supported baseline. Make sure the documentation distinguishes what is baseline, what is optional, and what is quarantined, and ensure the wording matches the implemented runtime behavior. Summarize the operator contract after your edits and note any still-missing operational evidence that must be produced later.
```

## Phase 3 - Reduce Architectural and Scalability Risk

Goal: improve the parts of the implementation that will become operationally expensive or confusing if left unchanged.

### Step 3.1 - Implement blocked KG reconciliation
Description: replace the all-pairs reconciliation path with blocking-based candidate generation and benchmark the result.
Model: `GPT-5.4-codex`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Improve earCrawler/kg/reconcile.py so reconciliation no longer relies on naive all-pairs comparison when blocking-key helpers already exist. Implement a real blocked candidate-generation path, preserve correctness as much as possible, and add focused benchmarks or tests that report candidate reduction, runtime improvement, and any precision or recall tradeoffs visible in the existing test fixtures. Keep the change set scoped to reconciliation and its verification surface. Summarize the algorithmic change, the measured effect, and any residual scale risks that still remain.
```

### Step 3.2 - Simplify or clearly deprecate overlapping CLI surfaces
Description: reduce onboarding confusion by clarifying ownership of CLI entrypoints.
Model: `GPT-5.4`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Inspect the overlapping CLI surfaces in the repository and determine the smallest safe path to reduce ambiguity: either consolidate remaining production-useful commands under the main supported CLI or clearly deprecate and document the legacy/top-level CLI surface. Do not do a broad rewrite. Prefer changes that make ownership and support status explicit while preserving the current supported workflow. Update the minimum necessary docs and tests, then summarize which CLI entrypoints are authoritative, which are legacy, and how the repo now communicates that boundary.
```

### Step 3.3 - Create a formal data artifact inventory
Description: document which runtime and training artifacts are authoritative versus experimental.
Model: `GPT-5.4`
Reasoning: `medium`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Create a practical data artifact inventory for the repository. Identify the major runtime, corpus, FAISS, evaluation, and training artifacts that contributors are likely to touch; record whether each one is authoritative, derived, experimental, generated, or archival; and link each artifact to the workflows that depend on it. Keep the output concise and operational. If a small generated manifest or helper script would materially improve maintainability, add it, but avoid building a large subsystem. Summarize the artifact truth model you established.
```

## Phase 4 - Close Deployment and Release Gaps

Goal: make the supported baseline easier to provision, verify, recover, and ship on its real target platform.

### Step 4.1 - Build a Fuseki provisioning and disaster-recovery package
Description: turn the graph dependency from an implied prerequisite into a repeatable operator workflow.
Model: `GPT-5.4`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Produce a concrete Fuseki provisioning and disaster-recovery package for the supported deployment model. Treat the current single-host Windows-focused operator path as authoritative. Document the pinned version, install layout, startup order, health checks, backup procedure, restore procedure, upgrade procedure, and failure signatures that operators should expect. If the repository already contains scripts that can be safely reused, prefer them; otherwise keep additions minimal and pragmatic. Preserve the repo’s strengths around cautious support claims and operational clarity. Summarize what is now proven, what is only documented, and what still requires future automation.
```

### Step 4.2 - Add release-shaped smoke tests for installed artifacts
Description: validate the supported runtime in the same shape operators will actually receive it.
Model: `GPT-5.4-codex`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Add release-shaped smoke coverage for the supported baseline so packaging and release validation prove the same runtime contract the docs describe. Focus on clean install or installed-artifact behavior, the supported read-only API surface, the declared single-host runtime contract, and any deterministic corpus or KG prerequisites that the release process already claims to support. Do not widen the supported contract. Reuse existing CI or release scripts where possible, add only the tests and script adjustments that materially close the current evidence gap, and run the targeted verification available in this workspace. Summarize the release proof that now exists and any still-unproven clean-room assumptions.
```

### Step 4.3 - Define the stronger external-auth integration pattern
Description: keep the single-host secret model for now, but document the approved front-door for any broader exposure.
Model: `GPT-5.4`
Reasoning: `medium`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Define the approved external-auth integration pattern for any deployment broader than the current trusted single-host model. Do not replace the existing baseline auth model unless the repo already safely supports more. Instead, document the reverse-proxy or external front-door pattern, identity expectations, secret rotation approach, request attribution expectations, and the line beyond which the current static shared-secret model is no longer sufficient. Keep the output aligned with the repo’s current scope and security posture. Summarize the resulting guidance and the boundary between supported single-host auth and future broader deployments.
```

## Phase 5 - Produce Evidence for Optional and Research Surfaces

Goal: make optional capabilities evidence-driven, reproducible, and clearly bounded instead of source-visible but operationally ambiguous.

### Step 5.1 - Define the local-model release evidence bundle
Description: make the local-adapter path promotable only when artifact-backed evidence exists.
Model: `GPT-5.4`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass9.md as the governing context. Define the minimum release evidence bundle for the local-adapter path. The bundle should cover the adapter artifact, provenance manifest, corpus digest, benchmark outputs, evaluation thresholds, runtime smoke, rollback instructions, and the exact decision rule for keeping the capability optional versus promoting it further. Keep the baseline supported runtime unchanged. Update only the documentation, config templates, or lightweight validation hooks needed to make this bundle actionable. Summarize the evidence contract and what would count as insufficient evidence.
```

### Step 5.2 - Make the local training and benchmark path release-usable
Description: align training, artifact packaging, and evaluation so a real local-adapter candidate can be assessed.
Model: `GPT-5.4-codex`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass9.md and the newly clarified training corpus contract as the governing context. Improve the local training and benchmark workflow so it can produce a release-usable evaluation package for a local-adapter candidate. Keep scope tight: focus on artifact naming, manifesting, benchmark outputs, and any preflight or packaging gaps that block a credible candidate from being reviewed. Do not claim the capability is production-ready unless the evidence actually exists. Add or update targeted tests and verification where feasible, then summarize what the workflow can now produce and what still requires real model runs outside this coding change.
```

### Step 5.3 - Conditional search/KG evidence package and go/no-go decision
Description: within RunPass9 scope, prepare the exact evidence needed to decide whether search or KG-backed runtime behavior can move at all.
Model: `GPT-5.4`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass9.md, docs/kg_quarantine_exit_gate.md, docs/kg_unquarantine_plan.md, and docs/capability_graduation_boundaries.md as the governing context. Treat `/v1/search` and KG-backed runtime behavior as quarantined unless current evidence proves the gate is passed. Produce the smallest actionable search/KG evidence package for a fresh go/no-go decision: capability snapshot, required smoke coverage, operator workflow requirements, rollback requirements, failure-mode expectations, and the specific gaps that still block promotion. If any low-risk tests, docs, or scripts can be added now to improve future evidence quality, add them, but do not silently unquarantine anything. End with a dated recommendation of either `Keep Quarantined` or `Ready for formal promotion review`, and make that recommendation depend only on current evidence.
```

## Phase 6 - Final Production-Beta Readiness Review

Goal: perform one broad, deliberate synthesis after the stabilization, evidence, and release-hardening work is complete.

### Step 6.1 - Comprehensive repo review for production-beta readiness
Description: run the next full-pass review with the explicit intent of deciding whether the repo is ready to be treated as a production beta baseline.
Model: `GPT-5.4`
Reasoning: `extra high`
Prompt:
```text
Use docs/ExecutionPlanRunPass9.md and the completed outputs from each prior phase as the governing context. Perform a fresh, comprehensive repository review with the explicit goal of determining whether EAR AI / earCrawler now qualifies as a production beta baseline. Evaluate whether the repo preserved the strengths identified in RunPass9, whether the listed weaknesses and missing components were actually resolved or only partially addressed, whether supported-vs-optional-vs-quarantined boundaries are now consistent across code, tests, docs, packaging, and operator workflow, and whether the remaining risks are acceptable for a production beta designation. Be precise about current maturity, release blockers, residual technical debt, operator gaps, and any capabilities that must remain optional or quarantined. Produce a decision-oriented review document that ends with one of: `Production beta ready`, `Production beta ready with named constraints`, or `Not production beta ready`, and justify that result with concrete evidence.
```

