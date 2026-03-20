# Execution Plan From RunPass11

Source: `docs/RunPass11.md`

Purpose: execute the remediation, hardening, cleanup, and capability-decision work identified in `RunPass11` while preserving the repo's current strengths and working toward a defensible production-ready beta for the supported Windows single-host baseline.

Prepared: March 19, 2026

## Model Guidance

Working rule for this repository in Windows VS Code:

- Use `GPT-5.3-Codex` for code changes, tests, scripts, CI, packaging, and targeted refactors.
- Use `GPT-5.4` for architecture decisions, policy docs, capability-boundary decisions, and whole-repo synthesis.
- Use `medium` when the task is bounded, implementation-shaped, and the end state is already clear.
- Use `high` when the task crosses multiple modules, changes release or operator behavior, or needs careful architectural restraint.
- Use `xhigh` only for a genuinely non-decomposable repository-wide judgment.

This plan intentionally keeps `xhigh` to one final synthesis step. Everything else below is decomposable and should stay at `medium` or `high`.

## Global Guardrails

- Preserve the strengths identified in `RunPass11`: explicit support boundaries, deterministic artifacts, cautious AI/RAG behavior, strong evidence discipline, and the supported Windows single-host operator path.
- Do not silently promote optional or quarantined capabilities.
- Keep the supported product claim narrow unless a step explicitly widens it with evidence.
- Prefer hermetic, reproducible workflows over workspace-dependent convenience.
- Distinguish authored source from generated state in code, docs, tests, and release logic.
- End each step with a concrete summary of what changed, what was verified, and what remains unresolved.

## Phase A - Workspace Integrity And Release Signal Restoration

Goal: make the workspace trustworthy again by eliminating mutable-evidence drift, unsupported leftovers, and environment ambiguity before deeper hardening work begins.

### Step A.1 - Restore Release Artifact Integrity And Hermetic Verification
Purpose: remove the current checksum-drift failure and make release verification resilient to mutable shared `dist/` state.

Model: `GPT-5.3-Codex`
VS Code reasoning: `high`
Why this level: the work spans release scripts, tests, evidence files, and workflow assumptions, but it is still a bounded implementation and verification problem rather than a whole-repo design exercise.

Prompt:
```text
Use docs/RunPass11.md as the governing context. Repair the current release-integrity failure where dist/earcrawler-kg-dev-20260319-snapshot.zip no longer matches dist/checksums.sha256, and then harden the release-verification path so it is hermetic against mutable shared dist state. Start with tests/release/test_verify_script.py, scripts/verify-release.ps1, dist/checksums.sha256, the dist manifest and evidence files, and any release scripts that assume a stable workspace dist directory.

Your goals are:
1. restore the repository to a green, trustworthy release-verification state,
2. ensure future verification runs do not silently trust stale or manually mutated dist artifacts,
3. preserve the current deterministic release-evidence story rather than weakening it.

Prefer the smallest defensible design: for example, isolate verification inputs, regenerate expected checksums from authoritative artifacts when appropriate, or fail early when the verification target is not a controlled release bundle. Do not bypass integrity checks. Update only the narrowest relevant docs. Run targeted verification, including the failing release test and any closely related checks, and finish with a short explanation of the new hermetic boundary and any remaining operator assumptions.
```

### Step A.2 - Separate Authored Source From Generated And Ghost Workspace State
Purpose: stop cache-only directories and stale build outputs from masquerading as supported source or active capability.

Model: `GPT-5.3-Codex`
VS Code reasoning: `medium`
Why this level: the task is operationally important, but it is bounded to cleanup tooling, ignore policy, and documentation alignment rather than deep architectural work.

Prompt:
```text
Use docs/RunPass11.md as the governing context. Add the smallest practical workflow that distinguishes authored source from generated or unsupported workspace leftovers, with explicit attention to build/, dist/, .pytest_tmp*, .venv*, and ghost directories such as earCrawler/agent, earCrawler/models/legalbert, earCrawler/quant, tests/agent, and tests/models when those surfaces are not tracked source. The goal is to reduce maintainer confusion without deleting legitimate evidence or widening support claims.

Implement a pragmatic solution that may include a cleanup script, a verification script, .gitignore tightening where appropriate, and maintainer documentation that states which directories are authoritative source, generated evidence, quarantined capability, or disposable workspace state. Do not convert local leftovers into supported features. Run the narrowest useful verification and summarize how a maintainer can now tell whether a path is real source, generated output, or unsupported residue.
```

### Step A.3 - Define Dependency Source Of Truth And Add Bootstrap Verification
Purpose: eliminate ambiguity between `pyproject.toml`, `requirements.in`, lockfiles, and local shell assumptions so new maintainers can bootstrap the repo consistently.

Model: `GPT-5.3-Codex`
VS Code reasoning: `medium`
Why this level: this is a bounded repo-hygiene task with some cross-file coordination, but it does not require architectural synthesis.

Prompt:
```text
Use docs/RunPass11.md as the governing context. Reconcile and document the repository's dependency source of truth across pyproject.toml, requirements.in, requirements-dev.txt, lockfiles, and any packaging or wheelhouse scripts. Choose and document one authoritative model for dependency declaration versus pinned resolution, then add lightweight verification so maintainers can detect drift early.

At the same time, add a small bootstrap verifier for this Windows-first repo that checks the actual expected entrypoints and prerequisites, such as py, the project .venv, PowerShell availability, and any critical runtime dependencies like Java where the supported operator flow depends on them. Keep the implementation pragmatic: no large environment manager, just enough automation and documentation to make setup failure obvious. Run targeted verification and summarize the final dependency policy plus the bootstrap checks now available to maintainers.
```

### Step A.4 - Block Mutable-Evidence Regressions In CI And Local Preflight
Purpose: prevent the workspace from drifting back into a state where release tests depend on stale shared artifacts.

Model: `GPT-5.3-Codex`
VS Code reasoning: `medium`
Why this level: the task is a standard CI and local-script hardening change with clear inputs and outputs.

Prompt:
```text
Use docs/RunPass11.md as the governing context. Add a narrow CI and local preflight guard that detects release-evidence drift before deeper test or publication steps run. The guard should specifically protect against mutated dist artifacts, missing checksum or signature dependencies, and verification runs that target uncontrolled workspace outputs instead of authoritative release bundles.

Reuse the repository's existing workflow shape. Keep the new guard small, explainable, and easy to rerun locally. Update only the minimum documentation needed to explain when the guard runs, what it checks, and how a maintainer restores a clean state. Run the narrowest useful verification and summarize the failure semantics of the new guard.
```

## Phase B - Supported Baseline Hardening

Goal: turn the supported single-host baseline into a fully reproducible operator story with explicit degraded-state behavior and a clearer deployment promotion path.

### Step B.1 - Prove The Full Clean-Host Windows Baseline
Purpose: close the gap between repo-local success and a real supported deployment by validating the API, Fuseki dependency, and operator workflow on a clean host shape.

Model: `GPT-5.3-Codex`
VS Code reasoning: `high`
Why this level: this step cuts across packaging, scripts, docs, smoke validation, and operator assumptions, but it remains a bounded baseline-hardening task.

Prompt:
```text
Use docs/RunPass11.md, docs/ops/windows_single_host_operator.md, docs/security.md, and the current release scripts and smoke evidence as the governing context. Extend the repo so the supported Windows single-host baseline is proven in the actual field shape: one Windows host, one EarCrawler API service instance, and one local read-only Fuseki dependency. The current goal is not broader deployment; it is reproducible clean-host validation for the supported baseline.

Focus on provisioning, install, start, health checks, rollback, and evidence capture. Reuse the current installed-runtime and release-evidence machinery where possible, but close any remaining gap between source-checkout success and clean-host operator success. If a script, manifest, or smoke adjustment is needed, keep it narrow and operator-oriented. Finish by summarizing exactly what is now proven on a clean host and what still requires a real environment-specific assumption outside the repo.
```

### Step B.2 - Prove The Approved External Front-Door Pattern
Purpose: move the documented IIS or reverse-proxy pattern from theory to one reproducible validated reference shape.

Model: `GPT-5.4`
VS Code reasoning: `medium`
Why this level: the task is architecture- and operator-doc-sensitive, but the implementation scope should stay narrow and documentation-led.

Prompt:
```text
Use docs/RunPass11.md and docs/ops/external_auth_front_door.md as the governing context. Produce one validated, reproducible reference deployment pattern for broader-than-loopback access that still preserves the supported single-host baseline and the app's current internal auth assumptions. Favor the existing Windows-friendly IIS or reverse-proxy path rather than inventing a new deployment architecture.

Your output should make the approved boundary operationally concrete: reverse-proxy config shape, identity expectations, secret handling, request attribution, health checks, rollback posture, and the exact conditions under which direct app exposure remains unsupported. If a small example config or smoke probe is needed, add it. Do not redesign the app's auth model. Finish with a clear statement of the approved front-door pattern and the evidence that now backs it.
```

### Step B.3 - Make Upstream Failure Propagation And Operator Health Explicit
Purpose: ensure callers, operators, and release evidence can distinguish no-data cases from degraded upstream behavior without reading source code.

Model: `GPT-5.3-Codex`
VS Code reasoning: `high`
Why this level: the task crosses upstream clients, their callers, health or manifest surfaces, and tests, but remains a contained behavior-hardening change.

Prompt:
```text
Use docs/RunPass11.md as the governing context. Implement or tighten explicit typed failure propagation for upstream integrations so callers and operators can distinguish no_results, missing_credentials, upstream_unavailable, invalid_response, retry_exhausted, and any other materially different supported states. Start with api_clients/tradegov_client.py, api_clients/federalregister_client.py, api_clients/ori_client.py, and the narrowest set of direct callers and health/report surfaces.

The goal is to remove remaining ambiguity, not to redesign the whole client stack. Surface degraded-state information where operators can actually observe it, such as health output, manifests, logs, or smoke evidence, and keep the public support boundary narrow. Add focused tests and run targeted verification. End with a clear summary of the new failure taxonomy, where it is exposed, and any intentionally lossy behavior that still remains.
```

### Step B.4 - Add Release Promotion And Evidence Retention Automation
Purpose: move from artifact creation to an explicit promotion workflow with retained evidence for each stage.

Model: `GPT-5.3-Codex`
VS Code reasoning: `high`
Why this level: this changes release workflow semantics and evidence handling across multiple scripts and docs, but it is still decomposable implementation work.

Prompt:
```text
Use docs/RunPass11.md, the current GitHub Actions workflows, release scripts, and release evidence files as the governing context. Add the smallest practical promotion workflow that separates build, validation, and promotion stages for the supported baseline. The workflow should retain the evidence that justified promotion, rather than leaving release trust dependent on mutable local context.

Keep scope tight. This is not a full enterprise CD platform. Reuse the existing workflow structure and evidence artifacts where possible. Add only the gating logic, manifest retention, and documentation needed to make promotion history understandable and auditable. Run the narrowest useful verification and summarize the final promotion stages, retained evidence, and remaining manual checkpoints.
```

## Phase C - Architecture Simplification And Maintainer Handoff

Goal: reduce takeover risk by clarifying the supported architecture, isolating single-host assumptions, and shrinking the documentation surface to a smaller authoritative set.

### Step C.1 - Make The Single-Host Runtime-State Boundary Explicit
Purpose: keep the current process-local design safe and understandable without making unsupported scale-out claims.

Model: `GPT-5.4`
VS Code reasoning: `high`
Why this level: the task is architecture-sensitive and affects long-term topology choices, but it is still bounded by the existing single-host contract.

Prompt:
```text
Use docs/RunPass11.md as the governing context. Introduce the smallest practical abstraction and documentation boundary around process-local runtime state, especially rate limiting, caches, retriever warm state, and any other stateful service assumptions. Preserve the supported topology as single-host and single-instance. Do not add distributed infrastructure and do not imply that the system is ready for horizontal scale.

The deliverable should make the current design explicit and safer to maintain: code boundaries where needed, targeted tests, and a short architecture note that explains what remains process-local by design and what would have to change before any shared-state or multi-instance claim could be made. Keep the implementation minimal and finish with a precise summary of the boundary you established.
```

### Step C.2 - Create An Authoritative Maintainer Start-Here And Architecture Handoff Set
Purpose: reduce onboarding friction caused by documentation sprawl and make the supported source, generated evidence, optional capability, and quarantined surfaces easy to understand.

Model: `GPT-5.4`
VS Code reasoning: `medium`
Why this level: this is a synthesis-heavy documentation task, but the outputs are bounded and do not require whole-repo `xhigh` reasoning.

Prompt:
```text
Use docs/RunPass11.md as the governing context. Create or tighten a small authoritative maintainer handoff set that a new developer can actually use. At minimum, clarify: the supported runtime entrypoints, the main module boundaries, the difference between authored source and generated artifacts, the optional versus quarantined capability split, the authoritative operator docs, and the normal release-validation path.

Prefer consolidation over adding more scattered documentation. Update existing docs when practical instead of creating many new ones. The result should reduce ambiguity, not add prose. If one new docs/maintainer_start_here.md or a short architecture handoff file is justified, create it and cross-link it from the narrowest relevant places. Finish by listing the small set of docs that now form the authoritative maintainer path.
```

### Step C.3 - Rationalize Support-Boundary Documentation And Capability Hygiene
Purpose: reduce long-term maintenance cost from source-visible but unsupported surfaces.

Model: `GPT-5.4`
VS Code reasoning: `medium`
Why this level: the work is mostly about precise policy and documentation alignment, with only narrow implementation changes if needed.

Prompt:
```text
Use docs/RunPass11.md, docs/capability_graduation_boundaries.md, docs/runtime_research_boundary.md, docs/repository_status_index.md, and docs/start_here_supported_paths.md as the governing context. Tighten the support-boundary story so optional, quarantined, legacy, and unsupported workspace-only surfaces are described consistently across docs, runtime contract, and repo structure.

The goal is to lower maintenance burden and maintainer confusion. Prefer small documentation and capability-registry alignment changes over code redesign. If a tiny verification script or doc consistency check would materially help keep these boundaries aligned, add it. Do not unquarantine anything. Finish with a concise statement of the supported baseline and the exact categories used for everything else.
```

## Phase D - Capability Resolution And Product Scope Closure

Goal: force clear decisions on optional AI features, quarantined KG/search behavior, and any claimed legal-answering posture so the production-beta target remains credible.

### Step D.1 - Define The Supported Answer-Generation Posture
Purpose: decide what kind of generated answer behavior is actually supportable for production beta, including abstention and human-review boundaries.

Model: `GPT-5.4`
VS Code reasoning: `high`
Why this level: this is a product, architecture, and evidence-boundary decision that spans evaluation, runtime behavior, and operational claims, but it is still decomposable from the final repo-wide go or no-go review.

Prompt:
```text
Use docs/RunPass11.md, docs/local_adapter_release_evidence.md, docs/model_training_surface_adr.md, the current RAG and groundedness modules, and the evidence under dist/training and dist/benchmarks as the governing context. Define the supported answer-generation posture for production beta. Be explicit about whether generated regulatory or legal-style answers are supported, when the system must abstain, what evidence threshold is required for any supported model path, and whether a human review boundary is required for higher-risk interpretations.

Do not broaden the current product claim without evidence. If the correct decision is to keep generated answers optional or heavily constrained, document that explicitly. If a short policy or evaluation-contract update is needed, make it. Finish with a decision-oriented summary of the supported answer path, the unsupported answer path, and the human-review or abstention rules required to keep the product claim defensible.
```

### Step D.2 - Either Produce A Reviewable Local-Adapter Path Or Formally Deprioritize It
Purpose: stop the local-adapter track from lingering in an ambiguous near-production state.

Model: `GPT-5.4`
VS Code reasoning: `high`
Why this level: this requires cross-checking technical evidence, evaluation policy, and roadmap scope, but it is still a bounded capability decision rather than a repo-wide synthesis.

Prompt:
```text
Use docs/RunPass11.md, docs/local_adapter_release_evidence.md, docs/model_training_surface_adr.md, scripts/training/*, scripts/eval/*, and the current evidence bundles under dist/training and dist/benchmarks as the governing context. Determine the smallest credible path forward for the local-adapter track: either produce the repository changes needed so the workflow can generate a truly reviewable candidate bundle, or formally deprioritize the track so maintainers stop treating it as near-term production work.

Do not claim the local-adapter path is ready unless the evidence genuinely supports it. Prefer clarity over optimism. If workflow cleanup, validator improvements, or documentation narrowing are needed, keep them tightly scoped. End with one explicit outcome: reviewable-optional path improved, or formally deprioritized for this production-beta target.
```

### Step D.3 - Reduce Quarantined Search And KG Maintenance Burden
Purpose: keep `/v1/search` and runtime KG expansion quarantined without letting them continue to create ambiguity or hidden support cost.

Model: `GPT-5.4`
VS Code reasoning: `high`
Why this level: this is a cross-document and capability-governance task with some implementation implications, but it does not justify `xhigh`.

Prompt:
```text
Use docs/RunPass11.md, docs/kg_quarantine_exit_gate.md, docs/search_kg_quarantine_decision_package_2026-03-19.md, docs/capability_graduation_boundaries.md, service/docs/capability_registry.json, and the current optional-runtime code paths as the governing context. Reduce the maintenance burden of quarantined search and KG-backed runtime behavior while keeping those capabilities clearly out of the supported production-beta path unless current evidence truly satisfies the exit gate.

Favor explicit boundary tightening: cleaner docs, capability-registry alignment, smoke or verification changes that confirm the quarantine state, and removal of misleading near-production language. If a tiny code or test adjustment is needed to make the quarantine status harder to violate accidentally, make it. End with a clear statement of what remains quarantined, why, and what exact evidence would be required before reconsideration.
```

## Phase E - Final Production-Beta Decision

Goal: perform one deliberate full-repository synthesis after the remediation and hardening work is complete and decide whether the project now qualifies as a production-ready beta for its supported baseline.

### Step E.1 - Comprehensive Production-Ready Beta Review
Purpose: make the one repository-wide judgment that should not be decomposed into smaller implementation tasks.

Model: `GPT-5.4`
VS Code reasoning: `xhigh`
Why this level: this is the only step that genuinely requires whole-repo synthesis across source, docs, release evidence, tests, operator workflow, and capability posture. `high` is not enough for this final go or no-go judgment.

Prompt:
```text
Use docs/ExecutionPlanRunPass11.md, docs/RunPass11.md, and the completed outputs from all prior steps as the governing context. Perform a fresh, comprehensive repository and workspace review with the explicit goal of determining whether earCrawler now qualifies as a production-ready beta for its supported Windows single-host baseline.

Evaluate all of the following:
1. whether the strengths identified in RunPass11 were preserved,
2. whether every weakness and missing component named in RunPass11 was actually resolved, constrained, or explicitly deferred,
3. whether authored source, generated evidence, optional capability, and quarantined capability are now clearly separated,
4. whether the release, deployment, and operator story is now reproducible and trustworthy,
5. whether the supported answer-generation posture is evidence-backed and operationally safe,
6. whether any remaining risks are acceptable for a production-ready beta label.

Be precise about residual blockers, scope limits, and unsupported claims. Produce a decision-oriented review document that ends with one of:
- Production-ready beta
- Production-ready beta with named constraints
- Not production-ready beta

Justify the result with concrete repository evidence, not aspiration.
```

## Recommended Execution Order

1. Complete Phase A in order.
2. Start Phase B only after Phase A is complete.
3. Start Phase C after Step B.1 is complete.
4. Start Phase D after Phase B is stable enough that capability decisions can be made against the supported baseline.
5. Run Phase E only after all intended implementation, documentation, and evidence work is complete.

## Notes On Reasoning Discipline

- Do not escalate a step from `high` to `xhigh` just because it touches multiple files.
- In this repo, `xhigh` is reserved for the final production-beta judgment or an equally non-decomposable architecture decision.
- For nearly all implementation work here, the right tradeoff is `GPT-5.3-Codex` or `GPT-5.4` with `medium` or `high`, plus tight prompts and narrow verification.
