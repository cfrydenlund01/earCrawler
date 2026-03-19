# Execution Plan From RunPass10

Source: `docs/RunPass10.md` only.

Purpose: execute the highest-value remediation, hardening, and capability-decision work identified in RunPass10 using model and reasoning settings sized to the actual task complexity in Windows VS Code.

Prepared: March 19, 2026

## Model Guidance

Model-selection basis for this plan was checked on March 19, 2026 against current OpenAI model documentation:

- `GPT-5.4` is OpenAI's frontier model for complex professional work and supports reasoning levels `none`, `low`, `medium`, `high`, and `xhigh`.
- OpenAI's model catalog lists `GPT-5.3-Codex` as the most capable agentic coding model to date.
- The Codex model family guidance describes GPT-5 Codex models as optimized for agentic coding tasks in Codex or similar environments.

Working rule for this repository:

- Use `GPT-5.3-Codex` for code edits, tests, workflow automation, refactors, and release-pipeline implementation.
- Use `GPT-5.4` for architecture-sensitive decisions, evidence reviews, policy docs, and whole-repo synthesis.
- Use `medium` when the task is bounded and the desired end state is already well-defined.
- Use `high` when the task spans multiple files, affects architecture boundaries, or changes release and evidence flows.
- Use `xhigh` only when the task genuinely requires whole-repo synthesis or a non-decomposable go/no-go judgment.

This plan intentionally keeps `xhigh` rare. Nearly all implementation work below is decomposable and therefore should stay at `medium` or `high`.

OpenAI source links:

- Models overview: <https://developers.openai.com/api/docs/models>
- GPT-5.4 model page: <https://developers.openai.com/api/docs/models/gpt-5.4>
- All models catalog: <https://developers.openai.com/api/docs/models/all>
- GPT-5-Codex model family page: <https://developers.openai.com/api/docs/models/gpt-5-codex>

## Execution Status

- Phase 1: complete (2026-03-19)
- Phase 2: complete (2026-03-19)
- Phase 3: complete (2026-03-19)
- Phase 4: in progress (Steps 4.2, 4.3, and 4.4 complete on 2026-03-19)
- Phase 5: pending

## Global Guardrails

- Treat the supported Windows single-host baseline as authoritative unless a step explicitly says otherwise.
- Do not silently promote optional or quarantined capabilities.
- Prefer the smallest safe change set that materially improves evidence, reliability, or maintainability.
- Preserve current strengths identified in RunPass10: explicit support boundaries, deterministic artifacts, cautious RAG behavior, and strong release evidence.
- Run the narrowest verification that proves the intended outcome.
- End every execution step with a concrete summary of what changed, what was verified, and what remains unresolved.

## Phase 1 - Stabilization And Signal Quality

Goal: remove the most operationally expensive ambiguities first so the supported baseline becomes easier to trust, debug, and release.

### Step 1.1 - Make Upstream Failure Semantics Explicit
Purpose: stop treating upstream failures as empty data so operators and downstream code can distinguish absence of records from degraded dependencies.

Model: `GPT-5.3-Codex`
VS Code reasoning: `high`
Why this level: the task is cross-file and changes live-client behavior plus callers and tests, but it is still a bounded implementation problem rather than a whole-repo synthesis task.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Implement explicit upstream failure semantics across api_clients/federalregister_client.py, api_clients/tradegov_client.py, api_clients/ori_client.py, and the narrowest set of direct callers that currently collapse failure into empty results or log-only behavior. Distinguish at least these states where they are relevant: no_results, missing_credentials, upstream_unavailable, invalid_response, and retry_exhausted. Preserve the supported Windows single-host baseline, current API contract, and current capability boundaries; do not widen runtime scope or unquarantine anything.

Surface degraded-state information where operators can actually observe it, such as structured logs, corpus manifests, smoke reports, or health/report outputs, but avoid a broad redesign. Add focused tests for the new semantics and run the narrowest useful verification. At the end, summarize the new error taxonomy, where it is surfaced, and any remaining intentionally lossy behaviors.
```

### Step 1.2 - Add Tests For Startup And Optional-Runtime Hotspots
Purpose: raise confidence in the weakest-tested runtime branches without broadening scope into major refactors.

Model: `GPT-5.3-Codex`
VS Code reasoning: `medium`
Why this level: this is primarily a bounded test-hardening step against already-defined behavior, so `high` is unnecessary unless the implementation reveals hidden design flaws.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Add focused automated coverage for the weakest-tested startup and optional-runtime paths, starting with service/api_server/__init__.py, service/api_server/rag_support.py, earCrawler/rag/local_adapter_runtime.py, earCrawler/rag/ecfr_api_fetch.py, and api_clients/ori_client.py. Target the branches most likely to fail in real operation: app startup wiring, retriever warmup skip and timeout behavior, retriever-disabled and retriever-broken states, local-adapter validation failures, and upstream error handling.

Keep the change set test-first and avoid refactoring implementation unless a small change is required to make behavior observable and testable. Run targeted pytest selections instead of the whole suite unless the scope truly requires broader verification. Summarize which hot paths are now covered, which coverage risks remain, and whether any unexpectedly fragile logic was uncovered.
```

### Step 1.3 - Harden The Hermetic Operator Install Path
Purpose: make the release-grade Windows install path reproducible from signed artifacts and pinned dependencies instead of relying on a more permissive quick-install story.

Model: `GPT-5.3-Codex`
VS Code reasoning: `high`
Why this level: this touches docs, scripts, and release verification together, so it needs cross-file coordination but not `xhigh` repo-wide reasoning.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Harden the supported Windows operator install path so the release-grade deployment path is reproducible from signed artifacts and pinned dependencies. Compare docs/ops/windows_single_host_operator.md, scripts/install-from-wheelhouse.ps1, the current release workflow, and installed-runtime smoke coverage. Either make the hermetic wheelhouse path the authoritative hardened path or clearly separate quick install from release-grade install without ambiguity.

Keep the supported single-host API contract unchanged. Reuse existing smoke scripts where possible, add only the automation and documentation needed to align release evidence with the actual operator procedure, and run targeted verification. End by summarizing the authoritative install path, the quick-install path if one remains, and the evidence now produced for each.
```

### Step 1.4 - Add A Minimal CI Security Scanning Baseline
Purpose: bring security evidence closer to the maturity level already reached by tests, packaging, and release validation.

Model: `GPT-5.3-Codex`
VS Code reasoning: `medium`
Why this level: this is a standard bounded CI integration task, so `medium` should be sufficient unless the current workflow reveals deeper platform constraints.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Add a minimal but credible CI security-scanning baseline to the repository. Integrate dependency auditing, secret scanning, and static-analysis style checks into the existing GitHub Actions workflow in the smallest practical way. Favor tools and workflow changes that are easy for maintainers to rerun locally and easy to archive as release evidence. Keep the current Windows-first baseline and existing CI shape in mind.

Do not build a large security framework. Add only the checks, artifact outputs, and failure semantics needed to materially improve security evidence quality. Update the narrowest relevant documentation so a maintainer can understand what the new checks do, how to rerun them, and how they affect release confidence. Summarize the final CI security posture and any still-missing security evidence that remains out of scope.
```
## Phase 2 - Architecture Risk Reduction

Goal: reduce the maintenance and scaling risks that are already visible in the largest modules and the current process-local runtime design.

### Step 2.1 - Split The API App Factory Into Composable Modules
Purpose: reduce concentration of startup, middleware, telemetry, capability, and docs wiring in one large file without changing the supported runtime contract.

Model: `GPT-5.3-Codex`
VS Code reasoning: `high`
Why this level: the refactor crosses multiple responsibilities and must preserve subtle runtime behavior, but the scope is still decomposable and does not justify `xhigh`.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Refactor service/api_server/__init__.py into smaller composable modules while preserving current runtime behavior. Keep the supported API surface, middleware ordering, capability snapshot behavior, docs/openapi routes, startup and shutdown hooks, and telemetry integration unchanged unless a tightly scoped fix is clearly needed. Favor refactoring by extraction rather than redesign.

Preserve import stability where practical so downstream callers and tests do not break unnecessarily. Add focused regression tests that prove app-factory parity for the supported baseline. Run targeted verification and summarize the new module boundaries, the behavior-preservation checks you used, and any remaining reasons the API bootstrap still merits caution.
```

### Step 2.2 - Decompose The Retriever Implementation
Purpose: make retrieval behavior easier to reason about, test, and evolve without destabilizing the current RAG contract.

Model: `GPT-5.3-Codex`
VS Code reasoning: `high`
Why this level: the retriever is large and behaviorally important, so the work needs careful cross-file reasoning, but the problem can still be safely decomposed into implementation layers.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Refactor earCrawler/rag/retriever.py and the narrowest related retrieval runtime files into clearer internal components. Separate concerns such as index loading, backend selection, ranking or fusion logic, and post-filtering or metadata handling where that improves testability and maintainability. Preserve current retrieval outputs, warning semantics, and supported baseline behavior unless a small bug fix is clearly necessary.

Avoid redesigning the product surface. This is an internal maintainability refactor. Add focused tests that protect observable retrieval behavior and run only the verification needed to prove parity. At the end, summarize the new internal boundaries, any intentional behavior changes, and the residual risks that still remain in retrieval.
```

### Step 2.3 - Decompose The Corpus Builder
Purpose: lower the maintenance cost of the deterministic corpus pipeline by separating source adapters, metadata resolution, normalization, and manifest writing.

Status: complete (2026-03-19)

Model: `GPT-5.3-Codex`
VS Code reasoning: `high`
Why this level: this is a large-file refactor with determinism risk, so it needs careful reasoning, but it is still a constrained implementation task rather than a whole-repo review.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Refactor earCrawler/corpus/builder.py into smaller maintainable pieces while preserving deterministic outputs and the existing artifact contract. Separate source-specific acquisition or adaptation logic, metadata resolution, record normalization, and manifest or file-writing responsibilities where doing so improves clarity. Do not broaden the supported corpus contract or introduce new default data sources.

Preserve artifact determinism, stable IDs, content hashing, and existing supported-source behavior. Add targeted tests or determinism checks to prove the refactor did not change output semantics unintentionally. Run the narrowest useful verification and summarize the new boundaries, what stayed stable, and any remaining technical debt in the corpus path.
```

### Step 2.4 - Introduce A Runtime State Abstraction Without Claiming Scale-Out Support
Purpose: remove hidden assumptions around process-local state while keeping the officially supported topology unchanged.

Model: `GPT-5.4`
VS Code reasoning: `high`
Why this level: the step is architecture-sensitive and affects long-term topology choices, but it is still bounded by the current single-host contract and does not require `xhigh` whole-repo synthesis.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Introduce the smallest practical abstraction around runtime state that currently lives in-process, especially rate limiting and the RAG query cache. Preserve the supported topology as single-host and single-instance. Do not claim multi-instance correctness, do not add distributed infrastructure, and do not weaken current safety checks. The goal is to make the single-host default explicit while reducing hidden coupling and preparing the code for a future shared-state design if the project ever chooses to build one.

If a short architecture note or doc update is needed, add it. Keep implementation minimal and pragmatic. Add targeted tests for the abstraction boundary and summarize what is now explicit about runtime state, what remains process-local by design, and what future work would still be required before any scale-out claim could be made.
```
## Phase 3 - Optional Capability Resolution

Goal: make optional and quarantined surfaces evidence-driven and operationally explicit instead of source-visible but ambiguously supported.

### Step 3.1 - Tighten The Local-Adapter Evidence Contract
Purpose: ensure the optional local-model path stays gated by reproducible, machine-checkable evidence instead of documentation alone.

Model: `GPT-5.4`
VS Code reasoning: `high`
Why this level: this is a cross-cutting policy and evidence-definition step with technical consequences, but the scope is bounded by existing docs, scripts, and current optional status.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Tighten the local-adapter release evidence contract so a maintainer can tell unambiguously whether a candidate stays optional, is rejected, or is ready for formal promotion review. Start from the current local-adapter evidence docs, config templates, validation scripts, and real workspace artifacts under dist/training and dist/benchmarks. Preserve the current capability posture: optional means optional unless the evidence genuinely passes.

Improve the contract only where clarity, reproducibility, or machine-checkability is missing. Keep the supported baseline unchanged and avoid broad training-system redesign. If validator or config updates are needed, make the smallest practical changes and add focused verification. End with a clear statement of the final decision rule and the exact evidence bundle required for a credible candidate review.
```

### Step 3.2 - Make The Training And Benchmark Pipeline Produce Reviewable Bundles
Purpose: turn the current local training and evaluation path into a repeatable producer of reviewable candidate packages without overstating readiness.

Status: complete (2026-03-19)

Model: `GPT-5.3-Codex`
VS Code reasoning: `high`
Why this level: the step spans scripts, manifests, packaging, and validation logic, but it is still an implementation problem with explicit inputs and outputs.

Prompt:
```text
Use docs/RunPass10.md as the governing context together with the current local-adapter evidence contract. Improve the training and benchmark workflow so it can produce a reviewable candidate bundle for the optional local-adapter path. Focus on deterministic artifact naming, manifest completeness, benchmark output shape, release-evidence inputs, and preflight checks that block malformed or incomplete candidate packages. Do not claim the capability is production-ready unless the evidence truly supports it.

Keep scope tight: this is not a full training-platform buildout. Reuse existing scripts and layouts where possible, add only the packaging and validation behavior needed to make candidate review credible, and run the narrowest useful verification available in the workspace. Summarize what a maintainer can now produce and what still requires a real model run outside this coding change.
```

### Step 3.3 - Produce A Dated Search And KG Quarantine Decision Package
Purpose: decide with current evidence whether quarantined runtime search and KG expansion should remain quarantined or move to formal review.

Status: complete (2026-03-19)

Model: `GPT-5.4`
VS Code reasoning: `high`
Why this level: the task is decision-heavy and cross-document, but the inputs are explicitly bounded by gate docs and current evidence, so `xhigh` is not needed.

Prompt:
```text
Use docs/RunPass10.md, docs/kg_quarantine_exit_gate.md, docs/search_kg_quarantine_review_2026-03-19.md, docs/capability_graduation_boundaries.md, and the current evidence artifacts as the governing context. Treat /v1/search and KG-backed runtime expansion as quarantined unless the existing gate is actually satisfied by current evidence. Produce a dated decision package that records the capability snapshot, required operator workflow, required smoke coverage, rollback expectations, failure modes, and the specific evidence gaps that still block promotion.

If a low-risk script, evidence manifest, or documentation refinement would materially improve the future review process, add it, but do not silently unquarantine anything. End with a dated recommendation of either Keep Quarantined or Ready for formal promotion review, and justify that recommendation only with current evidence.
```

### Step 3.4 - Improve Live-Source Health And Freshness Reporting
Purpose: make source availability and data freshness visible enough that operators can tell whether the system is healthy, stale, or partially degraded.

Status: complete (2026-03-19)

Model: `GPT-5.3-Codex`
VS Code reasoning: `medium`
Why this level: this is a bounded visibility and reporting enhancement built on top of earlier failure-semantics work, not a major architecture redesign.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Improve operator-visible health and freshness reporting for live upstream sources. Build on the explicit failure semantics from earlier steps and expose, in the narrowest practical way, information such as source availability, missing-credential status, cache age, last successful sync or fetch, and whether the current state is healthy, stale, or degraded. Favor existing health, report, smoke, or manifest surfaces over creating a new subsystem.

Preserve the supported baseline and do not widen the public API contract unless there is already an internal or operator-facing place where this information naturally belongs. Add focused tests or smoke assertions if practical and summarize what operators can now observe that they could not before.
```

## Phase 4 - Production Hardening

Goal: turn the supported baseline into a cleaner operational story with stronger field-install, backup, auth-front-door, and release-evidence practices.

### Step 4.1 - Ship One Concrete External-Auth Reference Deployment Pattern
Purpose: keep the current shared-secret baseline for loopback use while providing one approved pattern for broader exposure.

Model: `GPT-5.4`
VS Code reasoning: `medium`
Why this level: this is primarily an architecture and operator-documentation task with limited implementation scope, so `medium` is appropriate.

Prompt:
```text
Use docs/RunPass10.md and docs/ops/external_auth_front_door.md as the governing context. Produce one concrete reference deployment pattern for broader-than-loopback access while keeping the current shared-secret model as the supported single-host baseline. Favor a Windows-friendly front door that fits the repo's operator story. Document the reverse-proxy shape, identity expectations, backend credential handling, correlation and attribution expectations, rotation guidance, and the exact line beyond which direct app exposure is no longer acceptable.

If a small reference config or script materially improves operator usability, add it, but do not broaden the app's internal auth model. Summarize the final approved pattern and how it preserves the baseline support boundary.
```

### Step 4.2 - Add Clean-Host Release Validation In The Actual Field-Install Shape
Purpose: prove that signed release artifacts can be installed and validated the way operators are actually expected to use them.

Status: complete (2026-03-19)

Model: `GPT-5.3-Codex`
VS Code reasoning: `high`
Why this level: the step spans release scripts, operator flow, and smoke evidence, so it needs careful integration but still does not require repo-wide `xhigh` reasoning.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Extend release validation so the repository proves the supported baseline in the same shape a real operator would receive it: signed artifacts, installed runtime, supported read-only API surface, and the declared single-host runtime contract. Reuse existing installed-runtime and API smoke coverage where possible, but align the validation path with the actual field-install story rather than a looser developer-install flow.

Do not widen the supported contract. Add only the workflow, script, or evidence adjustments needed to close the clean-host proof gap, and run the targeted verification available in this workspace. Summarize what is now proven end to end and which assumptions still depend on a real clean host outside the repo.
```
### Step 4.3 - Automate Recurring Backup And Restore Evidence
Purpose: make backup and restore drills part of the supported operational routine instead of one-off operator knowledge.

Status: complete (2026-03-19)

Model: `GPT-5.3-Codex`
VS Code reasoning: `medium`
Why this level: the work is operationally important but technically bounded to scripts, evidence outputs, and documentation.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Improve the supported backup and restore story so recurring evidence can be produced for the single-host baseline. Start from the existing scripts/ops backup and restore drill helpers and tighten the parts that would let operators or automation retain periodic evidence of backup validity, restore integrity, checksums, and drill success. Keep the current Windows single-host posture and local Fuseki dependency model unchanged.

Avoid a large monitoring platform build. Prefer small script or workflow improvements plus documentation alignment. Add the narrowest verification that proves the recurring evidence path works and summarize the final backup, restore, and drill evidence story.
```

### Step 4.4 - Add Security And Observability Evidence To Release Validation
Purpose: ensure release readiness depends not only on functional smoke tests but also on the presence of required security and monitoring evidence.

Status: complete (2026-03-19)

Model: `GPT-5.3-Codex`
VS Code reasoning: `high`
Why this level: the task changes release gating semantics and evidence requirements across workflows, which needs careful coordination but not whole-repo synthesis.

Prompt:
```text
Use docs/RunPass10.md as the governing context. Extend release validation so functional smoke evidence is not enough by itself. Incorporate the new CI security outputs and the most important observability or alerting evidence into the release-quality story in the smallest practical way. The goal is not to build a large compliance framework, but to ensure that a release cannot appear complete when required security scans or critical monitoring checks are missing or non-passing.

Reuse existing release verification scripts where possible. Add only the gating logic, evidence references, and documentation updates needed to make the release story more defensible. Run targeted verification and summarize the final release evidence contract after your changes.
```

## Phase 5 - Final Synthesis And Decision

Goal: perform one deliberate whole-repository review after the execution work is complete and decide whether the project has actually reached a production-beta baseline.

### Step 5.1 - Comprehensive Production-Beta Readiness Review
Purpose: do the one repo-wide synthesis pass that cannot be safely reduced to bounded implementation tasks.

Model: `GPT-5.4`
VS Code reasoning: `xhigh`
Why this level: this is the only step in the plan that genuinely requires whole-repo synthesis across architecture, code, docs, tests, release evidence, and capability posture. This is where `xhigh` is justified.

Prompt:
```text
Use docs/ExecutionPlanRunPass10.md, docs/RunPass10.md, and the completed outputs from all prior steps as the governing context. Perform a fresh, comprehensive repository review with the explicit goal of determining whether EAR AI / earCrawler now qualifies as a production-beta baseline. Evaluate whether the repo preserved the strengths identified in RunPass10, whether the named weaknesses and missing components were actually resolved or only partially addressed, whether supported-versus-optional-versus-quarantined boundaries are now consistent across code, tests, docs, packaging, and operator workflow, and whether the remaining risks are acceptable for a production-beta designation.

Be precise about current maturity, release blockers, residual technical debt, operator gaps, and any capabilities that must remain optional or quarantined. Produce a decision-oriented review document that ends with one of: Production beta ready, Production beta ready with named constraints, or Not production beta ready. Justify the result with concrete evidence from the repository and its validation outputs.
```

## Recommended Execution Order

1. Complete Phase 1 in order.
2. Start Phase 2 only after Step 1.1 and Step 1.2 are complete.
3. Start Phase 3 only after Phase 1 is complete.
4. Start Phase 4 after Step 1.3 and Step 1.4 are complete.
5. Run Phase 5 only after all intended implementation and evidence steps are complete.

## Notes On Reasoning Discipline

- If a step begins to expand beyond its stated scope, stop and split the work instead of jumping from `high` to `xhigh` by default.
- In this repository, `xhigh` should be reserved for a full-pass review, a final go/no-go decision, or a genuinely non-decomposable architecture problem.
- For almost all coding work here, the correct tradeoff is `GPT-5.3-Codex` with `medium` or `high`, not `GPT-5.4` with `xhigh`.
