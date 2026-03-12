# Production Candidate Scope Pass 7

Prepared: March 11, 2026

Status: Active scope lock for the next completion milestone.

## Purpose

This memo defines the narrowest credible production-candidate target supported by the current repository contents. The goal is to finish the strongest, best-evidenced path first and avoid widening the support contract before the repo proves it.

## Production-Candidate Definition

The production candidate is:

- one Windows host
- one EarCrawler API service instance
- one read-only Fuseki query endpoint already provisioned by the operator
- one deterministic artifact pipeline from supported corpus inputs through KG artifacts and validation
- one supported FastAPI facade at `service.api_server`
- one supported operator surface through the installed `earctl` CLI and the wheel-based Windows service flow

This milestone does not require every implemented feature to graduate. It requires the supported path to be internally consistent, release-gated, and operator-ready.

## In Scope

The next completion milestone includes only the following surfaces.

### Supported operator/runtime surfaces

- `earctl` / `py -m earCrawler.cli ...` for supported CLI workflows
- `service.api_server` as the only supported API service runtime
- wheel-based Windows single-host deployment via the documented virtualenv + NSSM flow
- operator docs under `README.md`, `RUNBOOK.md`, `docs/api/`, and `docs/ops/`

### Supported deterministic data path

- corpus build for supported sources
- corpus validation
- KG emission from supported corpus outputs
- KG validation for supported artifacts
- API smoke and offline verification for the supported runtime path

### Supported API contract

These routes are part of the supported production candidate:

- `/health`
- `/v1/entities/{entity_id}`
- `/v1/lineage/{entity_id}`
- `/v1/sparql`
- `/v1/rag/query`

### Optional but non-blocking surfaces

These may remain available without blocking the base production candidate:

- `/v1/rag/answer`
- remote OpenAI-compatible answer generation
- local adapter runtime for `/v1/rag/answer`
- GPU and model-serving extras required only for the optional answer-generation path

These remain optional because the repo explicitly treats them as enablement-dependent and the benchmark plan is still planning-only.

## Explicitly Out of Scope for This Milestone

The following are not part of the production-candidate support contract for this milestone and must not be described as such.

- `/v1/search`
- text-index-backed Fuseki search
- KG-backed runtime search behavior
- hybrid retrieval modes that depend on quarantined KG runtime behavior
- `kg-load`, `kg-serve`, and `kg-query` as supported production-runtime claims
- multi-instance deployment or any load-balanced API topology
- container runtime or image-based deployment
- legacy service entrypoints such as `earCrawler.service.sparql_service` and `earCrawler.service.legacy.kg_service`
- legacy placeholder ingestion through `earCrawler.ingestion.ingest`
- research, proposal, training, and benchmark-planning materials as operator commitments
- automated Fuseki provisioning by EarCrawler
- source-checkout hosting paths, PyInstaller `earctl.exe`, and installer-based API hosting as the authoritative deployment path

## Release-Blocking Gaps

The following gaps block the production-candidate milestone because they affect the supported contract directly.

### 1. NSF corpus-to-KG entity contract drift

Why blocking:

- it causes silent loss of real NSF entity names in emitted TTL
- it weakens lineage quality and downstream reasoning on a supported path
- it undercuts confidence in the corpus-to-KG contract

Required closure:

- one shared supported entity shape
- emitter compatibility with the real built-corpus structure
- regression coverage from supported corpus build output into KG emission

### 2. SHACL-only KG gating

Why blocking:

- structurally valid but semantically incomplete KG artifacts can pass today
- the supported artifact pipeline is supposed to be validation-heavy and deterministic

Required closure:

- promote a small, defensible semantic sanity-check set into blocking validation
- or add a documented waiver mechanism with explicit rationale for any non-blocking checks

### 3. Missing supported-path semantic end-to-end guard

Why blocking:

- the repo has strong test breadth, but the supported build -> validate -> emit -> semantic-check path still needs one direct regression guard
- without it, contract drift can recur across boundaries even when unit tests pass

Required closure:

- one practical CI-suitable supported-path semantic contract test

### 4. Operator-facing auth documentation mismatch

Why blocking:

- the current docs overstate bearer-token role behavior
- operator documentation is part of the supported contract and must not imply a security model the implementation does not provide

Required closure:

- narrow the docs to the implemented model, or finish a clearly auditable token-to-role path if it is already nearly complete

This is a smaller blocker than the first two, but it still needs resolution before calling the milestone production-candidate ready.

## Non-Blocking Gaps for This Milestone

These items matter, but they do not block the base production candidate defined here.

- local-adapter benchmark runner for `/v1/rag/answer`
- promotion decision for KG-backed search
- hybrid retrieval graduation
- large-module refactors in RAG, CLI, and eval orchestration
- multi-instance architecture work

These remain after the milestone unless the team deliberately widens scope.

## Release Acceptance Checklist

The milestone is complete only when all of the following are true.

### Scope and documentation

- `README.md`, `RUNBOOK.md`, `docs/api/readme.md`, and `docs/ops/windows_single_host_operator.md` agree on the same supported, optional, and quarantined surfaces
- single-host support is stated consistently
- out-of-scope surfaces are not described as production-ready

### Supported artifact pipeline

- supported corpus build succeeds on the documented path
- corpus validation succeeds
- KG emission succeeds from supported corpus outputs
- KG validation fails on the agreed blocking semantic defects, not just SHACL violations
- NSF entity information is preserved through the supported corpus-to-KG path

### Supported runtime verification

- supported API smoke passes for the supported routes
- the supported offline test suite passes
- the supported runtime still works with a read-only Fuseki endpoint and without claiming quarantined search behavior

### Operator readiness

- the wheel remains the authoritative deployment artifact for the API service path
- the Windows single-host install, upgrade, backup, restore, rollback, and secret-rotation story is documented and internally consistent
- the supported deployment contract does not imply multi-instance correctness

## Required Release Evidence

The release candidate should carry the following evidence package.

- passing `py -m pytest -q` on the supported offline path
- a passing supported-path corpus -> validate -> KG emit -> KG validate run
- proof that the supported semantic KG gate is active
- a passing supported API smoke run for the supported routes
- a wheel validation result for the supported Windows service path
- updated operator docs with no capability overclaims

## Decision Rule for Optional and Quarantined Features

If an item requires extra enablement, special hardware, training artifacts, or additional operator assumptions, it is not part of the base production candidate unless the repo already documents it as `Supported`.

Apply that rule to:

- `/v1/rag/answer`: optional, not release-blocking for the base production candidate
- local adapter benchmarking: useful release evidence for the optional path, not a blocker for the base production candidate
- `/v1/search` and KG-backed hybrid retrieval: quarantined until a later explicit graduation decision with current evidence
- multi-instance deployment: deferred until a separate shared-state design and validation pass exists

## Immediate Next Actions

The next work should stay tightly aligned to this scope lock:

1. Fix the NSF corpus-to-KG entity contract and add real supported-path regression coverage.
2. Promote the minimum semantic KG sanity checks into blocking validation.
3. Add one supported-path end-to-end semantic contract test.
4. Correct the access-control docs so the operator contract matches implementation.

No later task should widen the support boundary until those four items are closed.
