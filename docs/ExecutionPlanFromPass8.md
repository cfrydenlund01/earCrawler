# Execution Plan From RunPass8

Source: `docs/RunPass8.md` only.

Reasoning-level guidance:
- Prefer `high` over `extra high` unless a single step requires broad architecture synthesis that cannot be split.
- For this plan, no step requires `extra high` if executed in sequence.

1. P0 Hard-gate quarantined `/v1/search`
Description: Make the unsupported search route impossible to use by default at runtime.
Model: `GPT-5.3-Codex`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass8.md as the governing context. Inspect only the files needed for this task. Implement a hard runtime gate for quarantined `/v1/search` so it is disabled by default. Add an explicit feature flag/config setting, ensure the router is not mounted when disabled, make the default supported runtime consistent with the document, add focused tests, and run only the targeted verification needed for this change. Summarize the code change, tests run, and any follow-up gaps.
```

2. P0 Align client, OpenAPI, and docs with the search gate
Description: Remove default exposure drift so supported behavior matches runtime, client, and API contract.
Model: `GPT-5.3-Codex`
Reasoning: `medium`
Prompt:
```text
Use docs/RunPass8.md as the governing context. Starting from the new `/v1/search` runtime gate, update the API client surface, OpenAPI artifacts, and any API docs touched by this capability so search is not presented as supported by default. Keep the gate behavior consistent across runtime, client, and contract artifacts. Add or update targeted tests that prove capability exposure matches the supported boundary. Summarize what changed and what remains intentionally quarantined.
```

3. P0 Fix KG expansion packaging and installed-wheel proof
Description: Close the gap where `.rq` resources may work from source but fail from an installed wheel.
Model: `GPT-5.3-Codex`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass8.md as the governing context. Inspect only the packaging, smoke-test, and KG resource files needed to fix the installed-artifact gap for KG expansion. Ensure `earCrawler.sparql` packages required `*.rq` files, extend wheel smoke or equivalent installed-artifact validation to assert the KG expansion resource is present, and add a focused regression test for clean-room behavior. Run targeted verification and report exactly what was proven.
```

4. P1 Clean repo hygiene and fail releases that ship placeholders
Description: Remove ambiguous placeholder surfaces and stop incomplete release artifacts from passing validation.
Model: `GPT-5.3-Codex`
Reasoning: `medium`
Prompt:
```text
Use docs/RunPass8.md as the governing context. Address two hygiene issues with minimal scope: remove or explicitly document empty placeholder package directories that misrepresent supported capability, and add release validation that fails if placeholder bundle/signing artifacts survive into distributable outputs. Update only the necessary scripts, docs, and tests. Run targeted checks and summarize the enforced release rule.
```

5. P1 Design the shared RAG orchestration layer
Description: Produce the narrowest viable architecture to eliminate drift between pipeline and API orchestration.
Model: `GPT-5.4`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass8.md as the governing context. Analyze only the files directly involved in RAG orchestration across the pipeline and API service. Design a single reusable orchestration layer for retrieval, policy/refusal handling, prompt preparation, generation, and response shaping. Keep the design minimal, preserve current supported behavior, identify the extraction seam, list the concrete file changes you recommend, and call out migration risks and parity requirements. Do not implement yet unless the design is trivial.
```

6. P1 Implement shared RAG orchestration and parity tests
Description: Apply the approved design with thin adapters so API and non-API flows stop drifting.
Model: `GPT-5.3-Codex`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass8.md and the approved shared-RAG design as the governing context. Implement the shared orchestration layer with thin API and pipeline adapters. Preserve supported behavior, keep the change set as small as practical, and add parity-focused tests that prove API and pipeline paths make the same decisions for retrieval, refusal, output shaping, and any guarded KG-related behavior. Run targeted tests and summarize residual drift risks.
```

7. P2 Continue hotspot refactors after RAG consolidation
Description: Reduce maintenance risk in the largest modules without changing behavior.
Model: `GPT-5.3-Codex`
Reasoning: `medium`
Prompt:
```text
Use docs/RunPass8.md as the governing context. Inspect only the largest maintainability hotspots called out there and choose one bounded extraction that materially improves readability without changing behavior. Prefer separating workflow orchestration, backend adapters, metrics/reporting, or CLI rendering into smaller modules while keeping public behavior stable. Add targeted tests if needed, run focused verification, and explain why this extraction was the best next cut.
```

8. P1/P2 Define graduation boundaries for optional capabilities
Description: Turn broad optional/quarantined language into explicit capability states, evidence requirements, and operator controls.
Model: `GPT-5.4`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass8.md as the governing context. Create a concrete graduation plan that separates four concerns: text search, hybrid ranking, KG expansion, and local-adapter serving. For each one, define whether it should remain quarantined, optional, or supported; specify the runtime gate, packaging proof, smoke coverage, rollback expectations, and operator documentation required for promotion. Update the relevant docs and, where low-risk, codify any obvious capability-state checks in tests or config. Keep the output actionable rather than aspirational.
```

9. P2 Add release-shaped smokes and operator playbooks for optional features
Description: Make optional runtime modes operable and testable in the same shape operators will use.
Model: `GPT-5.3-Codex`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass8.md and the capability/graduation decisions already made as the governing context. Add release-shaped smoke coverage and operator playbook updates for the optional features that remain in scope, especially KG expansion, search-related modes, and local-adapter validation if artifacts are available. Focus on enable/disable steps, rollback behavior, failure modes, and clean-room validation. Run only the targeted proofs you can execute in this workspace and clearly label anything still unproven.
```

10. P2 Enforce single-host runtime contract and tighten release promotion criteria
Description: Match deployment reality to the documented architecture and stop overclaiming scale or release readiness.
Model: `GPT-5.4`
Reasoning: `high`
Prompt:
```text
Use docs/RunPass8.md as the governing context. Treat the documented single-host deployment as the current source of truth unless the code already safely supports more. Implement the smallest safe hardening needed to enforce or clearly signal single-instance assumptions around process-local cache/rate-limit behavior, and tighten release promotion criteria so publication requires complete evidence, no placeholders, signature validation, and supported-path smoke parity. Update the necessary docs, config, scripts, and tests, then summarize the operational contract that now exists.
```
