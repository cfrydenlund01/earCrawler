# Run Pass 8

## 1. Executive Summary

`earCrawler` is a Windows-first Python monorepo for regulatory data ingestion, deterministic corpus building, RDF/knowledge-graph emission, a read-only FastAPI service, and an optional retrieval-augmented question answering stack for EAR compliance workflows. The supported product surface is intentionally narrow: `earctl`, `service/api_server`, the deterministic corpus -> KG -> API path, and the operator/release scripts and docs that support a single-host Windows deployment.

The repository is substantially more mature than a prototype. It has strong documentation, explicit runtime boundary documents, release tooling, audit/telemetry support, and a broad automated test surface. In this workspace, `py -m pytest -q` completed successfully with `404 passed, 8 skipped` on March 12, 2026, which is strong evidence that the supported path is stable and actively maintained.

The main architectural story is coherent:

- ingest or replay EAR/NSF source material into normalized JSONL corpora
- validate and snapshot those corpora
- emit deterministic RDF/Turtle and validate KG semantics
- optionally load/query Fuseki through curated SPARQL templates
- expose the supported read-only API via FastAPI
- optionally run dense/hybrid retrieval and LLM-backed grounded answers with strict output and citation validation

The main risks are not missing core code. They are boundary and supportability risks:

- some quarantined features are still runtime-reachable and client-visible
- the installed-wheel/runtime proof is weaker for KG expansion and text search than for the supported baseline
- the RAG orchestration is duplicated between core pipeline code and the API service layer
- optional local-adapter/model-serving paths are documented and implemented, but not proven in this checkout because no real training artifact is present
- release/offline-bundle placeholder artifacts remain in the tree, which is acceptable for source control but not for a finished release story

Current maturity assessment: `beta` for the documented single-host deterministic CLI/API path, `alpha` for optional local-adapter serving and quarantined KG-backed/search-related behavior.

## 2. Project Architecture Overview

### Application type

The repository is a modular monorepo containing:

- a CLI application (`earctl`)
- a read-only FastAPI service (`service/api_server`)
- ingestion/corpus/KG libraries (`earCrawler/*`)
- evaluation and benchmark tooling
- Windows deployment and release automation
- research and proposal material that is explicitly separated from the supported runtime

It is not a microservice architecture. It is a single-repository, layered application with one supported runtime service and a larger supporting toolchain.

### Plain-language architecture explanation

For a new developer, the system is easiest to understand as five layers:

1. Data acquisition
   - `api_clients/` talks to Trade.gov, the Federal Register, optional LLM providers, and the local EarCrawler API.
   - `earCrawler/core/` and `earCrawler/corpus/` normalize raw source content into deterministic JSONL corpora.
2. Knowledge representation
   - `earCrawler/kg/` and `earCrawler/transforms/` convert corpus records into RDF/Turtle, apply provenance, validate integrity, and support Jena/Fuseki workflows.
3. Runtime service
   - `service/api_server/` exposes supported HTTP routes for health, entity lookup, lineage, curated SPARQL templates, retrieval, and optional answer generation.
4. Retrieval and answer generation
   - `earCrawler/rag/` builds the retrieval corpus and index, runs dense or hybrid retrieval, applies temporal filtering and refusal policy, and validates LLM output against a strict grounded schema.
5. Operations and evidence
   - `scripts/`, `bundle/`, `service/windows/`, `docs/ops/`, `earCrawler/audit/`, `earCrawler/telemetry/`, and `earCrawler/observability/` provide packaging, audit logging, monitoring, canaries, backup/restore drill scripts, and release evidence generation.

### Design patterns and architecture traits

- Layered architecture: clients -> corpus -> KG -> service -> RAG/eval.
- Adapter pattern: API clients, Fuseki client/gateway, LLM provider abstraction, keyring/secret adapters.
- Registry/template pattern: SPARQL templates are allow-listed in `service/templates/registry.json` and rendered through `service/api_server/templates.py`.
- Factory pattern: FastAPI app assembly happens in `service/api_server/__init__.py`.
- Policy/guardrail pattern: CLI RBAC, data egress policy, strict output schema validation, refusal rules, groundedness gates.
- Contract-first design: manifests, checksums, schema validation, OpenAPI artifacts, eval manifests, and strict JSON output contracts appear throughout the repo.

### Data flow

Supported baseline flow:

1. `earctl corpus build` creates normalized JSONL under `data/` or another output directory.
2. `earctl corpus validate` checks canonical IDs, hashes, URLs, dates, and required metadata.
3. `earctl kg-emit` emits deterministic Turtle.
4. `kg-validate` and KG integrity checks validate the emitted artifacts.
5. Optional: `kg-load` and `kg-serve` load/query Fuseki for local or quarantined workflows.
6. `service/api_server` exposes read-only HTTP routes using curated SPARQL templates and an optional retrieval stack.
7. `eval/` datasets and `scripts/eval/*` score retrieval and answer quality.

Optional answer-generation flow:

1. query enters `/v1/rag/query` or `/v1/rag/answer`
2. retriever loads corpus metadata + embeddings/index
3. temporal rules filter or refuse
4. optional KG expansion augments context
5. prompt is redacted and sent to a remote or local-adapter LLM
6. output is validated for schema, citations, and grounding
7. audit/telemetry events are emitted

### Dependency relationships

Primary runtime dependencies:

- CLI and service shell: `click`, `fastapi`, `uvicorn`, `httpx`
- graph and validation: `rdflib`, `pyshacl`, `SPARQLWrapper`
- networking and retries: `requests`, `tenacity`
- parsing: `beautifulsoup4`, `lxml`, `PyYAML`
- secrets: `keyring`
- optional retrieval/model stack: `sentence-transformers`, `torch`, `transformers`, `peft`, `faiss-cpu`

External services and systems:

- Trade.gov Consolidated Screening List API
- Federal Register API
- optional Groq and NVIDIA NIM OpenAI-compatible APIs
- Apache Jena TDB2 / Fuseki
- Windows Credential Manager / keyring
- Windows Event Log
- GitHub Actions for CI/release

### State management approach

State is mostly file-based and deterministic:

- JSONL corpora and manifests in `data/`
- FAISS index and metadata in `data/faiss/`
- RDF/Turtle and reports in `kg/`
- eval artifacts in `dist/eval/`
- benchmark/training outputs in `dist/training/` and `dist/benchmarks/`
- append-only audit logs under `%PROGRAMDATA%` or `%APPDATA%`
- telemetry spool on disk

In-memory runtime state is intentionally small:

- API rate limiter is in-memory and process-local
- RAG query cache is in-memory and process-local
- retriever/model caches are process-local

This is acceptable for the documented single-host contract, but it is not multi-instance safe.

### Concurrency and async patterns

- FastAPI routes are async.
- Blocking retrieval and generation work is moved off the event loop with `asyncio.to_thread`.
- Fuseki queries use a pooled `httpx.AsyncClient`.
- rate limiting uses a thread-safe token bucket with a lock.
- retriever warm-up uses a `ThreadPoolExecutor`.
- most CLI and build logic remains synchronous and deterministic.

## 3. Repository Structure Analysis

### High-level repository map

```text
earCrawler/
|- earCrawler/                 Core package code
|  |- cli/                     Supported CLI command groups and registrars
|  |- core/                    Source crawling/parsing/load helpers
|  |- corpus/                  Deterministic corpus build/validate/snapshot logic
|  |- kg/                      RDF/KG emit, validation, provenance, Fuseki/Jena support
|  |- rag/                     Retrieval, temporal logic, prompting, output validation
|  |- eval/                    Groundedness/citation/evidence scoring helpers
|  |- security/                RBAC, credential store, egress policy
|  |- telemetry/               Config, sinks, redaction, hooks
|  |- audit/                   Audit ledger and required event emission
|  |- observability/           Canary/watchdog config and helpers
|  |- monitor/                 Run logger and monitoring state helpers
|  |- transforms/              CSL/EAR normalization and RDF transforms
|  |- loaders/                 KG/data load helpers
|  |- pipelines/               Legacy/synthetic or helper pipeline entrypoints
|  `- analytics/               Corpus reporting utilities
|- service/
|  |- api_server/              Supported FastAPI app, routers, schemas, middleware
|  |- templates/               Curated SPARQL templates and registry
|  |- openapi/                 OpenAPI contract source
|  `- windows/                 Windows service installation docs
|- api_clients/                HTTP clients for upstreams and the local API
|- scripts/                    Packaging, CI, ops, eval, health, release, training automation
|- tests/                      Broad automated validation across runtime, KG, RAG, ops, release
|- docs/                       Runbooks, ADRs, boundary docs, ops guides, audit notes
|- kg/                         Ontology, assembler configs, queries, baseline artifacts, scripts
|- eval/                       Versioned datasets, schema, manifest, benchmark inputs
|- bundle/                     Offline bundle configs and helper scripts
|- config/                     Example env/config contracts for secrets and training
|- data/                       Corpus and retrieval index artifacts
|- Research/                   Research notes, prompts, decision log, proposal material
`- .github/workflows/          CI, KG CI, monitoring, release workflows
```

### Major components and purpose

| Component | Purpose |
| --- | --- |
| `README.md` | Canonical capability matrix and product boundary definition. |
| `RUNBOOK.md` | Operator lifecycle guide for the supported runtime path. |
| `pyproject.toml` | Package metadata, dependencies, console scripts, package data, coverage threshold. |
| `earCrawler/cli/__main__.py` | Top-level CLI composition and command registration. |
| `service/api_server/__init__.py` | FastAPI app factory, middleware wiring, retriever/cache initialization, docs/openapi routes. |
| `service/api_server/routers/*` | Read-only API boundaries for health, entities, lineage, SPARQL, RAG, and quarantined search. |
| `earCrawler/corpus/builder.py` | Deterministic source normalization, hashing, metadata resolution, manifest/checksum generation. |
| `earCrawler/kg/*` | RDF emitters, integrity checks, provenance helpers, Jena/Fuseki integration. |
| `earCrawler/rag/*` | Retrieval corpus/indexing, retrieval runtime, temporal logic, prompt construction, output schema enforcement. |
| `earCrawler/eval/*` | Groundedness and evidence scoring logic used by benchmark/eval scripts. |
| `api_clients/*` | Upstream/downstream API access with retries, budgets, and secrets handling. |
| `scripts/*` | Release, packaging, eval, benchmark, operator, telemetry, and health automation. |
| `tests/*` | Behavioral safety net for supported runtime path and much of the optional/quarantined tooling. |

### Key subpackages inside `earCrawler/`

| Package | Purpose |
| --- | --- |
| `cli` | Command groups for API, corpus, KG, eval, telemetry, policy, bundle, audit, jobs, and performance tooling. |
| `core` | EAR/NSF crawlers and parsers used by corpus generation. |
| `corpus` | Canonical record identity, entity extraction, build/validate/snapshot workflow. |
| `kg` | Graph namespaces, IRIs, emitters, loader, integrity, provenance store, SPARQL helpers. |
| `rag` | Retrieval backend, hybrid ranking, temporal selection, KG expansion, LLM runtime, strict schema validation. |
| `eval` | Groundedness gates, evidence resolver, citation metrics, label inference. |
| `security` | CLI policy enforcement, data egress rules, credential handling, identity helpers. |
| `telemetry` | Local telemetry config, sinks, hooks, and redaction. |
| `audit` | Append-only audit ledger and required event emission. |
| `observability` / `monitor` | Canaries, watchdog flow, health state, step/run logs. |

### Workflows and build systems

- `.github/workflows/ci.yml`
  - primary Windows CI for lint, tests, API smoke, supported evidence path, eval validation, perf smoke
- `.github/workflows/kg-ci.yml`
  - extensive KG/provenance/offline-bundle/incremental/perf contract workflow
- `.github/workflows/release.yml`
  - wheel/EXE/installer/signing/SBOM/release artifact generation
- `.github/workflows/monitor.yml`, `phase1-coverage-dev.yml`
  - additional monitoring and dataset-related workflow support

### Tests and verification

The repository has a broad test surface spanning:

- API contracts and headers
- RAG retrieval, output, temporal logic, and KG expansion
- KG emission, SHACL/OWL/integrity and Fuseki tooling
- audit ledger, privacy redaction, telemetry, retention, monitoring
- CLI command behavior
- release scripts and offline bundle logic

The local validation run in this workspace succeeded:

- `py -m pytest -q`
- Result: `404 passed, 8 skipped`

## 4. Research and Concept Evaluation

### Intended research and product concept

The conceptual model behind the repository is an evidence-first regulatory QA system:

- authoritative regulatory text is normalized into a deterministic corpus
- that corpus can be represented both as retrieval documents and as RDF/KG artifacts
- answer generation must remain grounded in retrieved evidence, not free-form model recall
- temporal ambiguity should cause refusal rather than heuristic guessing
- KG augmentation is useful, but it should not silently widen the supported runtime contract

This is consistent across:

- `docs/runtime_research_boundary.md`
- `docs/temporal_reasoning_design.md`
- `docs/hybrid_retrieval_design.md`
- `docs/model_training_surface_adr.md`
- the evaluation manifest and groundedness gate documents in `eval/` and `docs/`

### AI model usage

There are three AI-related surfaces:

1. Dense retrieval embeddings
   - `sentence-transformers` with FAISS or brute-force cosine search
2. Optional remote LLM answering
   - Groq or NVIDIA NIM through an OpenAI-compatible API
3. Optional local-adapter answering
   - a narrowly gated LoRA adapter path tied to a future Phase 5 training artifact

The current supported baseline does not require remote or local LLMs. That is an important product decision and is consistently documented.

### Algorithmic and theoretical ideas in use

- deterministic corpus identity and manifest hashing
- canonical IDs and provenance capture
- dense retrieval with deterministic tie-breaking
- optional hybrid retrieval using BM25 + reciprocal rank fusion
- temporal applicability filtering using explicit metadata only
- strict output schema validation for LLM responses
- groundedness scoring that distinguishes citation validity, support, and overclaim
- quarantine gates that separate implemented capability from supported capability

### Alignment between code and concept

Alignment is strong for the supported baseline:

- deterministic corpus build/validate behavior exists in code and is CI-gated
- KG emit/integrity/provenance logic is implemented and heavily tested
- the API surface is narrow, curated, and documented
- LLM output is guarded by schema validation, refusal logic, and citation checks
- temporal design is implemented conservatively and matches the design note

Alignment is weaker for optional/quarantined surfaces:

- `/v1/search` is documented as quarantined but still mounted and client-visible
- "KG-backed hybrid retrieval" is not one single product feature; it is split across hybrid ranking and separate KG expansion logic
- local-adapter runtime support is implemented, but the benchmark/release evidence still depends on artifacts not present in this checkout

Conclusion: the implementation matches the intended research concept for the supported path. The largest mismatch is not conceptual. It is operational: some research/quarantined features exist in code more concretely than the support boundary currently allows.

## 5. Strengths

### 5.1 Clear supported-vs-research boundary

The repository explicitly distinguishes supported runtime code from research, proposal, experimental, and quarantined surfaces. This is unusually strong for a mixed product/research codebase and reduces takeover risk for a new developer.

Why it helps:

- lowers onboarding ambiguity
- prevents overclaiming unsupported features
- makes production-readiness discussions concrete

### 5.2 Strong deterministic artifact discipline

Corpus manifests, checksums, KG baselines, canonical freezes, and release verification scripts are built into the workflow rather than treated as afterthoughts.

Why it helps:

- makes debugging and regression analysis reproducible
- supports auditability and release confidence
- aligns well with compliance-oriented product goals

### 5.3 Broad automated test coverage

The repo has a large, behavior-oriented test surface, and the current workspace test run passed cleanly.

Why it helps:

- reduces regression risk during handoff
- validates not only code units but also packaging, scripts, release checks, and policy boundaries
- gives new maintainers confidence to refactor

### 5.4 Good separation of concerns in core layers

The package organization is sensible: `api_clients`, `corpus`, `kg`, `rag`, `service`, `security`, `telemetry`, and `audit` are conceptually distinct and mostly follow that separation.

Why it helps:

- makes ownership boundaries understandable
- supports incremental hardening without large rewrites
- keeps the core supported runtime readable despite the repo size

### 5.5 Security-conscious defaults for sensitive operations

Examples include:

- Windows keyring integration for secrets
- explicit remote LLM egress policy gating
- structured audit ledger with chain hashes and optional HMAC
- CLI RBAC policy enforcement
- redaction support for telemetry and egress payloads

Why it helps:

- reduces accidental leakage
- creates evidence for operator and audit workflows
- fits the compliance-heavy domain

### 5.6 Conservative answer-generation contract

The RAG stack does not trust model output blindly. It validates labels, citations, assumptions, and groundedness, and it refuses on thin or temporally ambiguous evidence.

Why it helps:

- keeps model behavior aligned with regulatory use
- reduces hallucination risk
- makes evaluation more meaningful than generic answer scoring

### 5.7 Release and ops maturity for the supported single-host path

Release scripts, SBOM generation, signature verification, backup/restore drill scripts, and Windows operator docs are already in place.

Why it helps:

- shortens the path from source checkout to operator deployment
- makes the supported deployment story concrete
- gives a new maintainer a stable foundation for production hardening

## 6. Weaknesses and Remediation Steps

| Category | Problem | Why it matters | Technical impact | Risk | Concrete remediation |
| --- | --- | --- | --- | --- | --- |
| Architecture / Support boundary | Quarantined `/v1/search` is still mounted by default in `service/api_server/routers/__init__.py`, implemented in `service/api_server/routers/search.py`, and exposed in `api_clients/ear_api_client.py`. | The docs say it is quarantined, but the runtime and client surface still ship it. | Support boundary drift, accidental operator use, documentation inconsistency, harder incident handling. | High | Add an explicit feature flag or router mount gate; remove it from default client/OpenAPI artifacts until graduation; only re-enable once operator docs and release gates exist. |
| Packaging / Release | KG expansion depends on `earCrawler/sparql/kg_expand_by_section_id.rq`, but `pyproject.toml` only packages `earCrawler.sparql` as `*.sparql`, and `scripts/package-wheel-smoke.ps1` does not validate the `.rq` resource. | Installed-wheel behavior can differ from source-checkout behavior. | Optional KG expansion can fail in clean-room installs even when source tests pass. | High | Include `earCrawler.sparql` `*.rq` files in package data, extend wheel smoke to assert presence, and add a dedicated installed-artifact KG expansion smoke test. |
| Architecture / Maintainability | RAG orchestration is split between `earCrawler/rag/pipeline.py` and `service/api_server/rag_service.py`. | Duplicate logic drifts over time and makes fixes harder to apply consistently. | API and CLI/eval behavior can diverge for refusal logic, output handling, or future KG features. | High | Consolidate shared retrieval/generation flow into one reusable service layer with thin API/CLI adapters; add parity tests for API vs pipeline behavior. |
| Code quality | Several large modules remain hotspots: `scripts/eval/eval_rag_llm.py` (~1926 lines), `earCrawler/rag/retriever.py` (~869), `earCrawler/cli/rag_commands.py` (~634), `earCrawler/cli/eval_commands.py` (~523). | Large modules are harder to reason about and refactor safely. | Slower maintenance, more fragile reviews, higher change risk. | Medium | Continue the Pass 7 extraction strategy: separate metrics, workflow orchestration, backend adapters, and CLI rendering. |
| Scalability | Rate limiting and RAG query caching are process-local; the support contract is explicitly single-host/single-instance. | The system cannot scale out safely without behavioral changes. | Multi-instance deployments would have inconsistent limits, caches, and response behavior. | Medium | Either enforce single-instance deployment in service/runtime config or externalize cache/rate-limit state before claiming scale-out support. |
| Production readiness | `/v1/search` and KG-related runtime behavior lack installed-artifact proof, rollback docs, and end-to-end release-gated smokes in the supported runtime shape. | Code exists, but operator readiness is incomplete. | Promotion would add support burden faster than evidence supports. | Medium | Add release-shaped smoke tests, operator setup/rollback docs, and explicit failure contracts before graduating those features. |
| Documentation / Repo hygiene | Empty placeholder directories remain under `earCrawler/agent`, `earCrawler/models/legalbert`, and `earCrawler/quant`, while ADR text says these surfaces are absent or removed. | Even empty directories can confuse new contributors about supported capability. | Onboarding friction and misleading repo archaeology. | Low | Remove empty package directories or document them explicitly as placeholders scheduled for deletion. |
| Release hardening | Placeholder release artifacts remain in-tree, including `bundle/static/offline_bundle.zip.PLACEHOLDER.txt`, `bundle/static/manifest.sig.PLACEHOLDER.txt`, and `security/PLACEHOLDER_AUDIT_SIGNING_CERT.txt`. | Release workflows look mature, but placeholders signal incomplete distribution evidence. | Risk of incomplete release packaging or operator confusion. | Medium | Replace placeholders with generated artifacts in release builds, or move placeholders into docs/examples so distributable trees contain only real release assets. |
| Optional feature verification | Local-adapter benchmark/runtime paths are implemented and documented, but current checkout lacks a real `dist/training/<run_id>/` artifact, so the path cannot be proven end-to-end here. | Optional production-candidate claims rely on artifacts that are not part of the current validation run. | Benchmark and local-model serving readiness remain partially theoretical in this workspace. | Medium | Add a retained benchmark artifact in CI or a reproducible synthetic validation package for local-adapter runtime proof. |
| CI strategy | Optional GPU/benchmark jobs in `.github/workflows/ci.yml` are non-blocking (`continue-on-error: true`). | Optional features can regress without blocking mainline changes. | Lower confidence for retrieval/indexing/model-adjacent paths. | Low | Keep them non-blocking if scope requires it, but add explicit dashboarding and a promotion checklist for any feature that depends on those jobs. |

## 7. Missing Components

These are the main gaps between the current repository state and a stronger production-ready posture.

### 7.1 Hard runtime gating for quarantined features

What is missing:

- a real runtime kill-switch for `/v1/search`
- a clearer capability gate for KG expansion and hybrid retrieval on the API path

What it should do:

- ensure unsupported features are either disabled by default or clearly partitioned from the supported runtime

### 7.2 Installed-artifact validation for all optional runtime resources

What is missing:

- clean-room validation for every runtime resource needed by optional KG expansion/text search paths

What it should do:

- prove that wheels and release artifacts behave the same as source checkouts for packaged templates and support files

### 7.3 Unified RAG service abstraction

What is missing:

- one canonical orchestration layer used by API, CLI, and eval flows

What it should do:

- eliminate duplicated retrieval/generation/refusal logic and reduce drift

### 7.4 Explicit multi-instance strategy

What is missing:

- shared state for rate limits, cache, and rollout semantics

What it should do:

- either formally keep deployment single-instance and enforce it, or provide shared state for horizontal scale

### 7.5 Fully closed release evidence loop

What is missing:

- replacement of placeholder signing/bundle artifacts with actual release outputs in the full release chain

What it should do:

- ensure all release artifacts are complete, signed, verified, and operator-ready without manual placeholder replacement

### 7.6 Stronger optional-feature operator playbooks

What is missing:

- authoritative enable/disable/rollback docs for text search, hybrid retrieval, KG expansion, and local-adapter serving

What it should do:

- let operators manage optional features as intentional runtime states rather than ad hoc environment settings

## 8. Development Roadmap

### Phase A - Stabilization

| Task | Affected files | Implementation suggestion | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Add hard runtime gating for `/v1/search` | `service/api_server/routers/__init__.py`, `service/api_server/routers/search.py`, `api_clients/ear_api_client.py`, `service/openapi/openapi.yaml`, `docs/api/*` | Gate router registration behind an explicit setting, default it off, and align OpenAPI/client generation to the same gate. | Medium | P0 | None |
| Fix KG expansion packaging gap | `pyproject.toml`, `scripts/package-wheel-smoke.ps1`, `tests/tooling/test_runtime_service_surface.py`, `tests/bundle/*` or new tooling test | Include `*.rq` in package data and add a clean-room assertion for `kg_expand_by_section_id.rq`. | Low | P0 | None |
| Remove or document placeholder package dirs | `earCrawler/agent`, `earCrawler/models/legalbert`, `earCrawler/quant`, `docs/model_training_surface_adr.md` | Delete empty dirs or add explicit repo-hygiene note if they must remain. | Low | P1 | None |
| Add release check for placeholder artifacts | `scripts/verify-release.ps1`, `.github/workflows/release.yml`, `bundle/static/*`, `security/*` | Fail release validation if placeholder files survive into distributable outputs. | Medium | P1 | None |

### Phase B - Architecture Improvements

| Task | Affected files | Implementation suggestion | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Consolidate RAG orchestration | `earCrawler/rag/pipeline.py`, `service/api_server/rag_service.py`, `service/api_server/routers/rag.py`, `tests/rag/*`, `tests/service/*` | Create one shared orchestration service for retrieval, prompt prep, policy, generation, and response shaping. | High | P1 | Phase A packaging fix recommended |
| Continue hotspot refactors | `scripts/eval/eval_rag_llm.py`, `earCrawler/rag/retriever.py`, `earCrawler/cli/rag_commands.py`, `earCrawler/cli/eval_commands.py` | Extract adapter, reporting, and command-rendering modules; keep command entrypoints thin. | Medium | P2 | None |
| Align supported-path capability gating in code and docs | `README.md`, `RUNBOOK.md`, `docs/runtime_research_boundary.md`, `service/api_server/*`, `tests/tooling/*` | Replace documentary-only quarantine with machine-enforced capability boundaries. | Medium | P1 | Phase A search gate |

### Phase C - Feature Completion

| Task | Affected files | Implementation suggestion | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Decide the graduation scope for retrieval enhancements | `docs/kg_quarantine_exit_gate.md`, `docs/kg_unquarantine_plan.md`, `docs/hybrid_retrieval_design.md`, `service/api_server/schemas/rag.py` | Split the question into separate tracks: text search, hybrid ranking, and KG expansion. | Medium | P1 | Phase A/B boundary work |
| Add installed-wheel/runtime proof for KG expansion and optional search | `scripts/package-wheel-smoke.ps1`, `scripts/api-smoke.ps1`, new smoke scripts/tests, release workflows | Validate optional runtime features in the same deployment shape the operator would use. | High | P1 | Search/KG feature definitions |
| Prove local-adapter benchmark path with a real artifact contract | `scripts/eval/run_local_adapter_benchmark.py`, `scripts/local_adapter_smoke.ps1`, `docs/production_candidate_benchmark_plan.md`, CI workflow | Add a repeatable artifact-backed benchmark smoke and archive its evidence. | High | P2 | Real training artifact or packaged benchmark fixture |

### Phase D - Production Hardening

| Task | Affected files | Implementation suggestion | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Enforce single-instance assumptions or externalize shared state | `service/api_server/limits.py`, `service/api_server/rag_support.py`, `docs/ops/windows_single_host_operator.md`, future infra config | Either make single-instance non-negotiable in deployment tooling or add shared state for scale-out. | High | P2 | Architecture decision |
| Expand operator runbooks for optional features and incident response | `docs/ops/*`, `RUNBOOK.md`, `service/windows/*` | Add enablement, rollback, failure-mode, and troubleshooting procedures for optional runtime modes. | Medium | P2 | Feature definitions |
| Tighten release promotion criteria | `.github/workflows/release.yml`, `scripts/verify-release.ps1`, `docs/ops/release_process.md` | Require full evidence bundle, no placeholders, signature validation, and supported-path smoke parity before release publication. | Medium | P1 | Phase A release checks |

## 9. Quick Wins

These improvements should fit comfortably within one day each.

- Add `*.rq` package data for `earCrawler.sparql` and extend wheel smoke to assert that the KG expansion template is present.
- Add a service setting that disables `/v1/search` router registration by default.
- Remove empty placeholder directories or add a short repo-hygiene note explaining them.
- Add a release validation rule that fails if placeholder files are present in `dist/` or offline-bundle outputs.
- Add a focused tooling test that asserts API client/OpenAPI exposure matches the supported capability matrix.
- Split one more section out of `scripts/eval/eval_rag_llm.py`, which is still the largest maintainability hotspot.

## 10. Long-Term Improvements

### 10.1 Converge on a single supported evidence engine

Long term, the best architecture is a single reusable evidence service used by CLI, API, eval, and benchmark code. The current split is manageable, but it will get expensive as more retrieval and policy rules accumulate.

### 10.2 Separate productized runtime modules from research modules more aggressively

The boundary is documented well, but the codebase would be easier to inherit if optional and research-oriented logic were grouped more explicitly, possibly as separate packages or clearly versioned feature modules.

### 10.3 Externalize runtime state if scale-out becomes a goal

If this project ever moves beyond the documented single-host contract, rate limits, query cache state, and possibly audit/telemetry control state should move into shared infrastructure.

### 10.4 Add release-grade fixture packs for optional paths

Optional paths such as local-adapter serving and KG expansion would benefit from compact, versioned validation artifacts that can be exercised in CI and by new developers without reconstructing large external dependencies.

### 10.5 Formalize feature graduation criteria as code

The repo already has good decision memos and gates. The next step is to make more of those gates executable so that "quarantined", "optional", and "supported" are enforced by runtime and CI behavior, not just by documentation.

## 11. Final Assessment

### Current maturity level

Supported single-host deterministic path: `beta`

Optional local-adapter path: `alpha`

Quarantined search/KG-dependent runtime behavior: `alpha`

### Major risks

- documentary quarantine without full runtime isolation for `/v1/search`
- installed-artifact gap for KG expansion resources
- duplicated RAG orchestration across pipeline and API layers
- incomplete release evidence loop due placeholder artifacts
- optional runtime paths that are implemented but not fully proven from the current checkout

### Estimated effort remaining

To make the supported baseline more production-ready without widening scope:

- roughly `2 to 4 weeks` of focused engineering to close the gating, packaging, and release-evidence gaps

To graduate text search and KG-dependent retrieval into the supported contract:

- likely `4 to 8 additional weeks`, depending on operator docs, release-shaped smoke coverage, and packaging/runtime decisions

### Recommended next three development priorities

1. Add hard runtime gating for `/v1/search` and align API/client/docs with the same capability state.
2. Fix the KG expansion packaging/install validation gap and extend clean-room runtime proof.
3. Consolidate RAG orchestration into one shared service layer to prevent API/pipeline drift.

### Takeover guidance for a new developer

Start with:

- `README.md`
- `RUNBOOK.md`
- `docs/start_here_supported_paths.md`
- `docs/runtime_research_boundary.md`
- `earCrawler/cli/__main__.py`
- `service/api_server/__init__.py`
- `earCrawler/corpus/builder.py`
- `earCrawler/kg/*`
- `earCrawler/rag/*`

Then validate locally with:

- `py -m pytest -q`
- `py -m earCrawler.cli --help`
- the supported corpus -> KG -> API smoke path described in the README and runbook

That path is the most credible, best-tested, and best-documented part of the repository today.
