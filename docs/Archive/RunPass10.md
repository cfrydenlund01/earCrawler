# RunPass10 Technical Review

> Archive note (2026-04-07): Active local-adapter baseline switched to `google/gemma-4-E4B-it`. This archived document is retained for historical context only and no longer governs active execution.


Prepared: March 19, 2026  
Repository: `earCrawler`  
Package version observed: `0.2.5`

Audit basis:

- Full workspace review across source, docs, tests, scripts, config, generated evidence, and release assets.
- Validation executed locally on this workspace:
  - `py -3 -m pytest -q` -> `442 passed, 8 skipped`
  - `py -3 -m pytest -q --cov --cov-report=term` -> `81.10%` total coverage

## 1. Executive Summary

`earCrawler` is a Windows-first Python system that combines deterministic regulatory corpus building, RDF knowledge graph emission and validation, a guarded RAG stack, and a small FastAPI service layered in front of a local read-only Fuseki instance.

The project is not a loose prototype. The supported baseline is clearly defined, heavily documented, and backed by meaningful automated verification. The strongest architectural decision in the repository is the explicit separation between:

- supported runtime surfaces
- optional but maintained capabilities
- quarantined research or locally testable features
- generated artifacts
- archival planning material

That separation is enforced both in documentation and in machine-readable form through `service/docs/capability_registry.json` and `docs/repository_status_index.md`. This sharply reduces accidental production claims.

Current maturity assessment:

- Supported baseline: `near production` for the documented Windows single-host deployment shape.
- Optional local-model and advanced search surfaces: `alpha` to `research-grade`, intentionally not promoted.

What is already strong:

- deterministic corpus and KG artifact generation
- provenance and manifest discipline
- explicit operator docs for Windows deployment and rollback
- guarded RAG design with refusal behavior, strict output validation, and citation grounding
- CI and release automation that go beyond basic lint-and-test checks
- broad automated test coverage across the supported baseline

What still limits broader production claims:

- runtime state is process-local, so multi-instance correctness is not supported
- optional local-adapter serving has no passing promotion-ready candidate in the current workspace evidence
- `/v1/search` and KG-backed runtime expansion remain correctly quarantined
- live upstream client behavior sometimes collapses failure into empty results, which weakens operator visibility
- several startup, live-integration, and optional-code paths remain under-tested relative to the rest of the codebase
- release and operator flows are strong, but fully hermetic deployment and broader enterprise auth remain partly manual or documentation-only

Estimated effort remaining:

- `2 to 4 engineer-weeks` to further harden the supported single-host baseline
- `6 to 10+ engineer-weeks` to graduate optional local-model and search/KG runtime capabilities with evidence strong enough for production claims

## 2. Project Architecture Overview

### 2.1 Application Type

This repository is a modular Python monolith with several coordinated surfaces:

- CLI application: `earctl` / `py -m earCrawler.cli ...`
- FastAPI service: `service.api_server`
- deterministic corpus and KG pipeline
- optional RAG answer generation runtime
- packaging, release, and Windows operator automation
- phase-gated training and benchmark workflows for optional local model work

It is not a microservice system. The repository organizes concerns cleanly, but they are delivered from one codebase and one operator story.

### 2.2 Plain-Language Architecture Explanation

In plain terms, the system works like this:

1. It gathers or rebuilds authoritative text and entity data from sources such as the Federal Register and ORI/NSF-related materials.
2. It normalizes that material into deterministic JSONL corpus artifacts with manifests and digests.
3. It converts corpus artifacts into RDF/Turtle knowledge graph outputs and validates them offline with SHACL and SPARQL sanity checks.
4. It can load a local read-only Fuseki instance and expose curated read-only API routes for entities, lineage, SPARQL templates, and retrieval.
5. For RAG flows, it retrieves grounded context from an authoritative retrieval corpus, optionally calls an LLM, then validates the answer format and grounding before returning a response.
6. Optional experimental capabilities such as `/v1/search`, KG expansion during retrieval, and local-adapter serving are left disabled by default and require explicit evidence-backed enablement.

A new developer should think of the system as:

- an evidence-first regulatory data pipeline
- with a read-only query API
- and a conservative RAG layer added on top
- where production claims are intentionally narrower than the full set of code present in the repo

### 2.3 Architectural Layers

| Layer | Primary Paths | Purpose |
| --- | --- | --- |
| Operator entrypoints | `earCrawler/cli/`, `README.md`, `RUNBOOK.md` | Supported command surface for corpus, KG, API, policy, eval, and operations. |
| API runtime | `service/api_server/` | Read-only FastAPI facade with middleware, auth, limits, telemetry, curated routes, and capability reporting. |
| Data acquisition | `api_clients/`, `earCrawler/core/`, `earCrawler/loaders/` | External-source access, parsing, and normalization. |
| Corpus pipeline | `earCrawler/corpus/` | Deterministic JSONL corpus generation, normalization, manifests, provenance, and content hashing. |
| KG pipeline | `earCrawler/kg/`, `kg/` | RDF emission, provenance, SHACL and SPARQL validation, canonical artifacts, and KG reports. |
| Retrieval and RAG | `earCrawler/rag/` | Retrieval orchestration, temporal filtering, refusal policy, prompt construction, output validation, and optional LLM execution. |
| Security and audit | `earCrawler/security/`, `security/`, `earCrawler/audit/`, `earCrawler/privacy/` | RBAC, egress controls, redaction, audit ledgers, and policy configuration. |
| Operations and release | `scripts/`, `.github/workflows/`, `packaging/`, `installer/` | CI, release creation, smoke validation, signing, SBOM generation, Windows service automation, and operator tooling. |
| Evaluation and training evidence | `eval/`, `scripts/eval/`, `scripts/training/`, `docs/model_training_*` | Holdout datasets, benchmark plans, training contracts, local-adapter evidence, and promotion gates. |
### 2.4 Data Flow Through the System

#### Corpus and KG Flow

1. External clients fetch or replay source data.
2. `earCrawler/corpus/builder.py` normalizes records into source-specific corpus JSONL files.
3. The builder writes manifests, digests, and summary metadata.
4. `earCrawler/kg/emit_ear.py` and related emitters convert corpus records into deterministic Turtle.
5. `earCrawler/kg/validate.py` applies SHACL and SPARQL checks.
6. Validated artifacts can be loaded into local Fuseki for read-only query serving.

#### API Flow

1. `service.api_server.create_app()` loads settings from environment variables.
2. Middleware adds request context, authentication identity, request ID, rate-limit state, timeout enforcement, body-size control, and concurrency control.
3. Curated routes call allowlisted SPARQL templates or RAG services.
4. `/health` exposes capability state and the runtime contract, including the fact that state is process-local.

#### RAG Flow

1. A route receives a question.
2. The retriever loads the authoritative retrieval corpus/index configuration if explicitly enabled.
3. Retrieval returns candidate documents plus temporal metadata and warning state.
4. Policy logic decides whether generation should proceed or refuse due to weak evidence.
5. If generation is enabled, prompt construction applies label taxonomy, temporal instructions, and optional redaction.
6. The selected provider is either a remote OpenAI-compatible service or the optional local adapter.
7. Output is parsed and validated against a strict JSON schema with grounding checks.
8. The API returns retrieval metadata, citations, and refusal information rather than silently hallucinating.

### 2.5 Design Patterns and Architectural Conventions

Observed patterns:

- application factory pattern for FastAPI creation
- dataclass-heavy configuration and runtime state objects
- capability-registry pattern for supported versus optional versus quarantined surfaces
- contract-first docs and generated API artifacts
- deterministic build artifact pattern with manifests, checksums, and provenance sidecars
- defensive wrapper pattern around live external APIs
- adapter-style provider abstraction for LLM backends
- explicit refusal and validation pipeline for generated answers

### 2.6 Dependency Relationships

High-level dependency map:

- `earCrawler.cli` orchestrates corpus, KG, API, eval, policy, and operational workflows.
- `service.api_server` depends on `earCrawler.rag`, `service/templates`, `service/openapi`, `api_clients`, and security/telemetry modules.
- `earCrawler.corpus` depends on loaders, parsers, source clients, canonical transforms, and privacy helpers.
- `earCrawler.kg` depends on corpus record conventions plus `rdflib` and `pyshacl`.
- `earCrawler.rag` depends on retrieval corpora, model/config helpers, egress policy, and optional provider runtimes.
- `scripts/` wrap or validate the same supported surfaces rather than defining a separate runtime architecture.

### 2.7 API and Service Boundaries

Supported API surface:

- `/health`
- `/v1/entities/{entity_id}`
- `/v1/lineage/{entity_id}`
- `/v1/sparql`
- `/v1/rag/query`

Optional API surface:

- `/v1/rag/answer`

Quarantined API surface:

- `/v1/search`

The service boundary is intentionally narrow. The app is read-only, template-driven, and designed around a local Fuseki dependency. It does not expose arbitrary graph mutation or arbitrary query execution by default.

### 2.8 State Management Approach

State is primarily handled in three ways:

- environment-driven config objects such as `ApiSettings`
- in-memory runtime state stored on `FastAPI.app.state`
- deterministic file-based artifacts, manifests, and reports for cross-run persistence

Important current limitation:

- rate limiting is process-local
- the RAG cache is process-local
- retriever warm/cache state is process-local

This is correctly documented and surfaced in `/health`, but it means the supported deployment topology is intentionally single-instance.

### 2.9 Concurrency and Async Patterns

The API runtime uses asynchronous request handling but offloads blocking work carefully:

- FastAPI async routes serve requests
- blocking retrieval and provider calls are sent to threads via `asyncio.to_thread`
- concurrency is capped with an async semaphore middleware
- request timeout is enforced centrally in middleware
- request-log draining uses an async queue and background task
- retriever warmup uses a bounded startup thread pool

This is a pragmatic design for a single-host service with a mostly I/O-bound workload.

### 2.10 External Services and Integrations

| Service | Usage |
| --- | --- |
| Federal Register API | EAR text and metadata retrieval. |
| Trade.gov CSL API | Entity lookup and enrichment. |
| ORI / HHS HTML endpoints | Case listing and detail retrieval for NSF/ORI flows. |
| Apache Jena Fuseki | Local read-only graph query backend. |
| Groq | Optional remote OpenAI-compatible answer generation. |
| NVIDIA NIM | Optional remote OpenAI-compatible answer generation. |
| Hugging Face / PEFT / Transformers / Torch | Optional local-adapter training and serving path. |
| Windows Credential Manager / `keyring` | Secrets resolution. |
| Windows Event Log | Optional observability sink. |
| NSSM | Supported Windows service wrapper. |
| GitHub Actions | CI and release automation. |

## 3. Repository Structure Analysis

### 3.1 Hierarchical Summary

```text
.
|- README.md
|- RUNBOOK.md
|- pyproject.toml
|- requirements*.txt / requirements.in
|- docs/
|  |- api/
|  |- ops/
|  |- Archive/
|  |- repository_status_index.md
|  |- data_artifact_inventory.md
|  |- runtime_research_boundary.md
|- earCrawler/
|  |- cli/
|  |- core/
|  |- corpus/
|  |- kg/
|  |- rag/
|  |- security/
|  |- privacy/
|  |- telemetry/
|  |- observability/
|  |- audit/
|  |- transforms/
|  |- policy/
|  |- utils/
|- service/
|  |- api_server/
|  |- openapi/
|  |- templates/
|  |- docs/
|  |- windows/
|- api_clients/
|- scripts/
|  |- api/
|  |- eval/
|  |- ops/
|  |- training/
|  |- kg/
|  |- reporting/
|- tests/
|  |- api/
|  |- cli/
|  |- corpus/
|  |- kg/
|  |- rag/
|  |- security/
|  |- release/
|  |- perf/
|  |- integration/
|- kg/
|  |- baseline/
|  |- canonical/
|  |- reports/
|  |- scripts/
|  |- queries/
|- eval/
|- config/
|- security/
|- packaging/
|- installer/
|- Research/
|- dist/ / build/ / run/ / runs/
```

### 3.2 Major Directories and Purpose

| Path | Status | Purpose |
| --- | --- | --- |
| `earCrawler/` | Supported | Core Python package. Contains CLI registration, corpus logic, KG logic, RAG logic, security, telemetry, and utilities. |
| `service/` | Supported | Supported FastAPI API surface, OpenAPI sources, route templates, and service documentation. |
| `api_clients/` | Supported | Wrappers for live upstream services and the application API client. |
| `scripts/` | Supported | Build, smoke, release, operator, evaluation, and training automation. |
| `tests/` | Supported | Large automated test suite spanning API, CLI, corpus, KG, RAG, privacy, release, and perf behaviors. |
| `docs/` | Supported | Active handoff, architecture, capability, API, and operational documentation. |
| `kg/` | Supported | KG support assets, reports, queries, baseline/canonical evidence, and reconciliation helpers. |
| `eval/` | Supported | Holdout dataset manifests, schema, and evaluation inputs. |
| `config/` | Supported | Example runtime and model-training contract inputs. |
| `security/` | Supported | RBAC and policy configuration for CLI and runtime security controls. |
| `packaging/`, `installer/` | Supported | Release packaging and Windows installer definitions. |
| `Research/` | Quarantined | Notes and research logs that inform work but are not runtime commitments. |
| `docs/Archive/` | Archival | Historical execution plans and review passes. |
| `dist/`, `build/`, `run/`, `runs/` | Generated | Build outputs, evidence bundles, reports, and run artifacts. |

### 3.3 Key Modules and Files

| File or Module | Purpose |
| --- | --- |
| `pyproject.toml` | Package metadata, dependencies, console entrypoints, and coverage gate. |
| `earCrawler/cli/__main__.py` | Main CLI entrypoint. |
| `earCrawler/corpus/builder.py` | Deterministic corpus building, metadata resolution, manifests, and normalization. |
| `earCrawler/kg/emit_ear.py` | EAR corpus to Turtle emitter with deterministic ordering and provenance. |
| `earCrawler/kg/validate.py` | Offline SHACL and SPARQL KG validation. |
| `service/api_server/__init__.py` | API app factory, middleware registration, capability state, retriever setup, telemetry, and error handlers. |
| `service/api_server/config.py` | Runtime config and single-host contract validation. |
| `service/api_server/auth.py` | Shared-secret and keyring-based identity resolution. |
| `service/api_server/limits.py` | In-memory token-bucket rate limiting. |
| `service/api_server/rag_support.py` | Retrievers, warmup behavior, and in-memory RAG cache. |
| `service/api_server/routers/rag.py` | RAG query and optional answer routes. |
| `earCrawler/rag/llm_runtime.py` | Prompt planning, redaction, egress decision records, and strict output validation. |
| `earCrawler/rag/retrieval_runtime.py` | Retrieval orchestration and warning propagation. |
| `earCrawler/rag/retriever.py` | Core retrieval implementation and index-backed retrieval logic. |
| `api_clients/federalregister_client.py` | Federal Register API access with caching and retries. |
| `api_clients/tradegov_client.py` | Trade.gov CSL access with caching and retries. |
| `security/policy.yml` | CLI RBAC map. |
| `service/docs/capability_registry.json` | Machine-readable source of truth for supported, optional, quarantined, and legacy capabilities. |
| `docs/repository_status_index.md` | Top-level repository support map. |
| `docs/data_artifact_inventory.md` | Source-of-truth map for data and evidence artifacts. |
| `docs/ops/windows_single_host_operator.md` | Authoritative Windows operator lifecycle guide. |
### 3.4 Key Libraries Used

| Category | Libraries |
| --- | --- |
| CLI / API | `click`, `fastapi`, `uvicorn`, `httpx` |
| HTTP / resilience | `requests`, `tenacity` |
| RDF / graph validation | `rdflib`, `pyshacl`, `SPARQLWrapper` |
| Secrets / OS integration | `keyring`, `pywin32` |
| Data validation / testing | `jsonschema`, `pytest`, `pytest-cov`, `pytest-socket`, `vcrpy` |
| Parsing / scraping | `beautifulsoup4`, `lxml` |
| Optional retrieval / model stack | `faiss-cpu`, `sentence-transformers`, `torch`, `transformers`, `peft` |
| Tooling / release support | `black`, `flake8` |

### 3.5 Build, Test, and Release Systems

Observed build and release system components:

- `pyproject.toml` package metadata and console scripts
- GitHub Actions workflows: `ci.yml`, `kg-ci.yml`, `monitor.yml`, `release.yml`
- PowerShell-first packaging and smoke scripts under `scripts/`
- clean-room wheel smoke and installed-runtime smoke
- PyInstaller executable build and Windows installer generation
- checksum, signing, SBOM, manifest, and provenance steps in release flow

This is more mature than a typical prototype repository.

### 3.6 Test Structure

The `tests/` tree includes coverage across:

- API routes and middleware
- CLI commands
- corpus building
- KG emission and validation
- RAG retrieval and answer generation
- privacy and redaction behavior
- policy and auth behavior
- release and packaging flows
- perf and smoke constraints
- integration and golden-path checks

The suite passed locally with `442` passing tests and `8` skips.

### 3.7 Suggested Onboarding Path for a New Developer

Read in this order:

1. `docs/start_here_supported_paths.md`
2. `README.md`
3. `RUNBOOK.md`
4. `docs/repository_status_index.md`
5. `docs/data_artifact_inventory.md`
6. `docs/api/readme.md`
7. `docs/ops/windows_single_host_operator.md`
8. `service/api_server/__init__.py`
9. `earCrawler/corpus/builder.py`
10. `earCrawler/rag/llm_runtime.py`

## 4. Research and Concept Evaluation

### 4.1 Core Research and Product Concepts

The repository is built around four conceptual ideas.

#### A. Deterministic Regulatory Evidence Pipeline

The project assumes regulatory reasoning should start from reproducible text artifacts, not ad hoc live calls at answer time. That assumption appears throughout the code and docs:

- corpus outputs are normalized and hashed
- retrieval corpora have authoritative sidecars
- eval datasets are contract-based and held out from training
- generated artifacts under `dist/` are treated as evidence, not source truth

This is a sound conceptual foundation for auditability.

#### B. Knowledge Graph as Offline Evidence and Query Substrate

The KG is used to preserve lineage, entity relationships, and offline semantic checks. The implementation emphasizes deterministic Turtle emission and validation before runtime use.

This is conceptually coherent. The repository does not overclaim that the KG is already a production-safe dynamic runtime dependency for every feature.

#### C. Conservative RAG for Compliance-Oriented Question Answering

The RAG stack is intentionally cautious:

- retrieval is grounded in an authoritative corpus
- prompts include explicit label taxonomies
- temporal instructions are injected when dates matter
- answer generation can refuse when evidence is weak
- citation quotes must be exact substrings of provided context
- strict JSON output validation is enforced
- egress decisions are logged with hashed or redacted material

This is the right conceptual pattern for a compliance-sensitive assistant.

#### D. Evidence-Gated Local Model Promotion

The optional local-adapter path is treated as a research-to-production promotion pipeline, not as an automatic capability claim. Promotion requires:

- named artifacts
- smoke results
- benchmark outputs
- thresholds
- rollback instructions
- an evidence manifest

This is disciplined and appropriate.

### 4.2 AI Model Usage

Observed model usage patterns:

- Retrieval embeddings and optional dense retrieval rely on a sentence-transformer style stack and FAISS.
- Default retriever wiring in the API references `all-MiniLM-L12-v2` as the baseline embedding model.
- Remote answer generation supports OpenAI-compatible providers such as Groq and NVIDIA NIM.
- Future local adapter training targets `google/gemma-4-E4B-it` as the selected 4B-class base model.
- Local adapter serving is deliberately gated behind explicit environment variables and artifact checks.

### 4.3 Theoretical and Algorithmic Ideas

Key ideas present in the implementation:

- deterministic text normalization and hashing
- provenance-preserving record identity
- knowledge graph emission with sorted Turtle output
- SHACL plus SPARQL semantic validation
- dense or hybrid retrieval options
- temporal answer conditioning and refusal logic
- strict grounded-citation enforcement
- policy-aware remote egress control

### 4.4 Does the Implementation Match the Intended Concept?

Assessment: `mostly yes for the supported baseline`, `partially for the optional research surfaces`.

Where implementation strongly matches concept:

- deterministic corpus and KG pipeline
- explicit artifact truth chain
- narrow read-only API boundary
- guarded RAG answer generation
- evidence-based capability promotion rules

Where implementation intentionally does not yet satisfy the concept end to end:

- local adapter capability exists in code and docs, but current evidence does not justify promotion beyond optional status
- search and runtime KG expansion exist, but production-like operator proof is still missing, so they remain quarantined
- multi-instance production architecture is explicitly deferred rather than partially supported

This is a positive sign overall. The codebase is honest about what is implemented versus what is production-proven.

## 5. Strengths

### 5.1 Explicit Capability Boundary and Support Model

The combination of `service/docs/capability_registry.json`, `docs/repository_status_index.md`, and `docs/start_here_supported_paths.md` is one of the strongest parts of the project.

Why this is beneficial:

- new contributors can quickly understand what is safe to modify
- optional and research surfaces do not silently become production commitments
- API and operator claims stay aligned with actual evidence

### 5.2 Strong Determinism and Provenance Discipline

Corpus, KG, eval, and training-adjacent workflows consistently use manifests, digests, and named artifacts.

Why this is beneficial:

- improves reproducibility
- supports audit and rollback
- makes regression analysis materially easier
- reduces ambiguity about what data or model was used in a result

### 5.3 Conservative Read-Only API Design

The FastAPI service is intentionally narrow, template-driven, and read-only.

Why this is beneficial:

- smaller attack surface
- easier operator reasoning
- clearer contract boundaries
- lower risk of accidental graph mutation or arbitrary query execution

### 5.4 Guarded RAG Implementation

The RAG path has several unusually strong safety properties for a repo at this stage:

- refusal on insufficient evidence
- temporal-scoping behavior
- strict schema validation
- exact-substring citation checks
- egress decision logging with redaction support

Why this is beneficial:

- reduces unsupported claims
- improves traceability of generated answers
- fits the compliance/regulatory domain better than generic answer generation
### 5.5 Broad Automated Validation

The suite passed with `442` tests and `81.10%` coverage. CI also enforces:

- coverage minimums
- packaging smoke
- API latency budgets
- corpus determinism gates
- supported corpus/KG/API smoke flows
- optional runtime smoke
- eval dataset validation

Why this is beneficial:

- validates the actual operator shape, not just unit behavior
- catches drift in packaging and release workflows
- provides stronger confidence than a narrow test suite would

### 5.6 Mature Release Engineering for a Small Team Codebase

The release flow includes:

- wheel build
- clean-room install smoke
- installed-runtime smoke
- API parity smoke
- optional runtime smoke
- signing and checksum steps
- SBOM generation
- provenance attestation

Why this is beneficial:

- reduces release regressions
- supports compliance and audit needs
- gives future maintainers a repeatable delivery path

### 5.7 Honest Windows-First Operator Story

The repository does not pretend to support every platform or topology. It clearly documents the supported target as one Windows host with one API service instance.

Why this is beneficial:

- fewer hidden assumptions
- better operator handoff quality
- reduced risk of accidental unsupported deployment shapes

### 5.8 Security and Privacy Controls Appropriate to the Baseline

Notable controls include:

- CLI RBAC policy in `security/policy.yml`
- constant-time secret comparison in API auth
- optional keyring-based secret lookup
- payload redaction support
- egress decision records for LLM usage
- documented reverse-proxy pattern for broader exposure

Why this is beneficial:

- good baseline posture for a single-host internal service
- clearer escalation path when deployment broadens
- less temptation to overstate security posture

## 6. Weaknesses and Remediation Steps

No currently observed issue is a clear `critical` blocker for the documented supported single-host baseline. The main issues are medium-to-high risks that block broader claims, increase maintenance cost, or weaken operational clarity.

| Problem | Why It Matters | Technical Impact | Risk | Concrete Remediation | Affected Files |
| --- | --- | --- | --- | --- | --- |
| Process-local runtime state prevents scale-out correctness | Rate limits, concurrency controls, and the RAG cache behave differently as soon as multiple processes or hosts are introduced. | Incorrect aggregate throttling, inconsistent cache behavior, unclear failure semantics under load balancing. | Medium | Either formalize single-host as a permanent product boundary or introduce shared backends for rate limits and cache plus multi-instance tests and operator docs. | `service/api_server/config.py`, `service/api_server/limits.py`, `service/api_server/rag_support.py`, `docs/ops/multi_instance_deferred.md` |
| Large modules concentrate too many responsibilities | Onboarding, testing, and safe refactoring become harder when startup, telemetry, routing, and runtime state are coupled. | Higher maintenance cost, harder defect isolation, weaker targeted testability. | Medium | Split `service/api_server/__init__.py` into app-factory submodules; split `earCrawler/rag/retriever.py` and `earCrawler/corpus/builder.py` into smaller units with explicit interfaces. | `service/api_server/__init__.py`, `earCrawler/rag/retriever.py`, `earCrawler/corpus/builder.py`, `earCrawler/rag/retrieval_runtime.py` |
| Upstream client failures are sometimes normalized into empty results or log-only behavior | Operators and calling code cannot always distinguish `no data` from `upstream unavailable`, `missing key`, or `partial failure`. | Silent data-quality degradation, confusing downstream behavior, weaker diagnostics. | Medium | Introduce typed domain errors or explicit status objects; propagate degraded-state metadata into corpus manifests, smokes, and API health/reporting. | `api_clients/federalregister_client.py`, `api_clients/tradegov_client.py`, `api_clients/ori_client.py`, callers in `earCrawler/corpus/` and `earCrawler/rag/` |
| Coverage is uneven in startup, live-integration, and optional-runtime paths | Overall coverage is good, but the weaker areas cluster around the places that fail most often in real operations. | Increased regression risk in bootstrap and optional feature paths. | Medium | Add focused tests for startup wiring, retriever warmup, local-adapter runtime, eCFR fetch logic, and upstream error paths. | `service/api_server/__init__.py`, `service/api_server/rag_support.py`, `earCrawler/rag/local_adapter_runtime.py`, `earCrawler/rag/ecfr_api_fetch.py`, `api_clients/ori_client.py`, `api_clients/federalregister_client.py` |
| Optional local-adapter serving has no passing release candidate in current evidence | The code path exists, but the current evidence bundle explicitly does not justify promotion. | Optional local-model claims remain non-production; runtime smoke and benchmark posture are not sufficient. | High | Either produce a passing candidate against the current thresholds or formally keep the capability optional/research-only and avoid roadmap ambiguity. | `docs/local_adapter_release_evidence.md`, `docs/model_training_first_pass.md`, `dist/training/step52-real-candidate-gpt2b-20260319/`, `dist/benchmarks/step52-real-candidate-gpt2b-20260319/`, `kg/reports/local-adapter-smoke.json` |
| Search and KG-backed runtime behavior remain unproven for production | These capabilities require a real text-index-backed Fuseki operator story and production-like smoke proof, which are not yet present. | Search and KG expansion cannot be safely promoted despite existing code. | Medium to High | Keep them quarantined until operator provisioning, rollback, and production-like validation artifacts exist; otherwise remove them from near-term production scope. | `service/api_server/routers/search.py`, `earCrawler/rag/kg_expansion_fuseki.py`, `docs/kg_quarantine_exit_gate.md`, `docs/search_kg_quarantine_review_2026-03-19.md` |
| Operator install path is not fully hermetic by default | The operator guide still centers a wheel install into a fresh venv; hermetic wheelhouse tooling exists but is not clearly the default deployment path. | Reproducibility drift between release evidence and field installs. | Medium | Make offline wheelhouse installation the default hardened path or clearly separate `quick install` from `release-grade install` in operator docs and release artifacts. | `docs/ops/windows_single_host_operator.md`, `docs/ops/hermetic_toolchain.md`, `scripts/install-from-wheelhouse.ps1`, `release.yml` |
| App auth model is coarse-grained outside the trusted single-host boundary | Static shared-secret auth is acceptable for loopback/local use but not sufficient for enterprise internet-facing access. | Weak external authorization model, limited per-user attribution in-app, deployment risk if misapplied. | Medium | Keep loopback-only baseline, add reference reverse-proxy configs and deployment automation, and do not broaden direct-exposure claims until edge auth is operationalized. | `service/api_server/auth.py`, `docs/ops/external_auth_front_door.md`, `docs/ops/windows_single_host_operator.md` |
| CI does not currently show dedicated security scanning gates | The repo has strong build/test/release checks, but no obvious CodeQL, dependency audit, or secret-scan workflow is present. | Supply-chain or code-pattern issues may go undetected until manual review. | Medium | Add dependency audit, SAST, and secret scanning to GitHub Actions and treat them as release-quality evidence. | `.github/workflows/ci.yml`, `.github/workflows/release.yml`, dependency manifests |

Coverage hotspots observed during the audit that deserve attention:

- `api_clients/ori_client.py` at about `28%`
- `earCrawler/rag/ecfr_api_fetch.py` at about `25%`
- `earCrawler/rag/local_adapter_runtime.py` at about `27%`
- `service/api_server/__init__.py` at about `61%`
- `service/api_server/rag_support.py` at about `68%`
- `earCrawler/cli/corpus_commands.py` at about `60%`
- `earCrawler/cli/rag_commands.py` at about `62%`

## 7. Missing Components

The project is close to production for the narrow supported baseline, but several components are still missing if the goal is a broader production-grade platform.

| Missing Component | What It Should Do | Why It Is Needed |
| --- | --- | --- |
| Evidence-backed promotable local compliance model | Produce a passing adapter artifact with smoke, benchmark, rollback, and threshold evidence. | Without this, the local-model story is implementation-only, not production-ready. |
| Production-like search/KG promotion package | Provision text-index-backed Fuseki, validate `/v1/search`, prove KG expansion success and rollback in the actual operator shape. | Required before quarantined runtime capabilities can be promoted. |
| Shared-state or explicitly simplified scale strategy | Either support distributed rate-limit/cache semantics or deliberately remove any implied future scale-out expectation. | Current runtime contract stops at one process on one host. |
| Hermetic release install bundle as the default field path | Ensure deployment can be reproduced from signed artifacts and pinned dependencies without network drift. | Needed for strong reproducibility and operator confidence. |
| Enterprise front-door implementation assets | Provide concrete IIS/nginx/gateway examples, deployment scripts, and correlation-id guidance. | Current broader-exposure guidance is good conceptually, but still documentation-driven. |
| Upstream dependency health and degradation signaling | Distinguish `no records` from `source unavailable`, `auth missing`, and `retry exhaustion` across logs, manifests, and health surfaces. | Needed for operational clarity and trustworthy data freshness. |
| Security scanning in CI | Add dependency audit, secret scanning, and SAST as first-class validation artifacts. | Build quality is strong, but security evidence is comparatively thinner. |
| Environment promotion automation | Add release-to-host deployment automation or at least validation scripts that match the supported field install shape exactly. | Current release flow is strong, but actual deployment remains operator-driven. |

## 8. Development Roadmap

### Phase A - Stabilization

Goal: improve reliability and reduce ambiguity in the supported baseline.

| Task | Affected Files | Implementation Suggestions | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Make upstream failure semantics explicit | `api_clients/federalregister_client.py`, `api_clients/tradegov_client.py`, `api_clients/ori_client.py`, relevant callers | Replace empty-result collapse with typed errors or structured degraded-status returns; surface this in logs and manifests. | Medium | P0 | None |
| Add tests for weak startup and optional-runtime paths | `service/api_server/__init__.py`, `service/api_server/rag_support.py`, `earCrawler/rag/local_adapter_runtime.py`, `earCrawler/rag/ecfr_api_fetch.py` | Add targeted tests for app startup branches, warmup skip logic, local-adapter validation failures, and upstream error handling. | Medium | P0 | None |
| Harden operator install reproducibility | `docs/ops/windows_single_host_operator.md`, `scripts/install-from-wheelhouse.ps1`, `release.yml` | Promote hermetic wheelhouse flow or add an explicit hardened install track with matching smoke verification. | Medium | P1 | None |
| Add CI security scanning | `.github/workflows/ci.yml`, dependency manifests | Add `pip-audit` or equivalent, secret scanning, and SAST to CI. Publish outputs as evidence artifacts. | Small to Medium | P1 | None |
### Phase B - Architecture Improvements

Goal: reduce maintenance cost and prepare the codebase for controlled growth.

| Task | Affected Files | Implementation Suggestions | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Refactor API app factory into composable modules | `service/api_server/__init__.py` and new helper modules | Separate capability-state construction, middleware setup, telemetry startup, docs/openapi handlers, and shutdown hooks. | Medium | P1 | Phase A tests |
| Decompose retriever implementation | `earCrawler/rag/retriever.py`, `earCrawler/rag/retrieval_runtime.py` | Split index loading, backend selection, ranking/fusion, and post-filtering into isolated components. | Large | P1 | Phase A tests |
| Decompose corpus builder | `earCrawler/corpus/builder.py` and supporting modules | Separate source adapters, metadata resolvers, record normalization, and manifest writing. | Large | P2 | Phase A failure-semantics work |
| Introduce runtime state abstraction | `service/api_server/limits.py`, `service/api_server/rag_support.py`, `service/api_server/config.py` | Define interfaces for rate-limit and cache backends so single-host and future shared-state modes are explicit. | Medium | P2 | None |

### Phase C - Feature Completion

Goal: finish or explicitly retire the capabilities that are currently in an in-between state.

| Task | Affected Files | Implementation Suggestions | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Decide the local-adapter path | `scripts/training/`, `scripts/eval/`, `docs/local_adapter_release_evidence.md`, `earCrawler/rag/local_adapter_runtime.py` | Either produce a passing candidate with real thresholds or freeze the feature as optional research and document that decision explicitly. | Large | P1 | Phase A tests |
| Resolve search/KG roadmap | `service/api_server/routers/search.py`, `earCrawler/rag/kg_expansion_fuseki.py`, `docs/kg_quarantine_exit_gate.md` | Either build the missing operator/evidence path or explicitly narrow long-term product scope by keeping these quarantined. | Large | P1 | Phase A install and test hardening |
| Improve health and freshness reporting for live sources | source clients, health/reporting scripts, docs | Expose source availability, cache age, missing-key status, and last successful sync information. | Medium | P2 | Phase A failure semantics |
| Provide concrete external-auth deployment assets | `docs/ops/external_auth_front_door.md`, new config/examples under `scripts/ops/` or `service/windows/` | Ship one supported front-door reference implementation with logging and correlation guidance. | Medium | P2 | None |

### Phase D - Production Hardening

Goal: align delivery, operations, and evidence with long-term support expectations.

| Task | Affected Files | Implementation Suggestions | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Validate release on a clean host using the actual field install shape | release scripts, operator docs, smoke scripts | Run a full clean-host install from signed release artifacts and archive the evidence bundle. | Medium | P1 | Phase A hermetic install work |
| Automate backup and restore drills as recurring operational evidence | `scripts/ops/windows-single-host-backup.ps1`, `scripts/ops/windows-single-host-restore-drill.ps1`, monitoring workflows | Schedule and retain periodic drill outputs rather than treating DR verification as ad hoc. | Medium | P2 | None |
| Add security evidence to release validation | release workflow and verification scripts | Fail release if security scans, dependency audits, or secret checks are missing or non-passing. | Medium | P1 | Phase A CI security scanning |
| Expand observability and alert thresholds | telemetry and monitor scripts, docs | Define operator-facing alerts for upstream outages, repeated 503s, retriever failures, and latency budget breaches. | Medium | P2 | Phase A health/failure semantics |

## 9. Quick Wins

These improvements are realistic in less than one day each and would materially improve the project.

1. Add explicit `upstream_unavailable` style error objects instead of returning empty collections from source clients.
2. Add targeted tests for `service/api_server/__init__.py`, `service/api_server/rag_support.py`, and `earCrawler/rag/local_adapter_runtime.py`.
3. Update `docs/ops/windows_single_host_operator.md` to distinguish `quick install` from `release-grade hermetic install`.
4. Add a lightweight CI dependency audit and secret-scan step to the existing GitHub Actions workflow.
5. Add a small `first files to read` section to `README.md` or `docs/start_here_supported_paths.md` for faster onboarding.
6. Exclude clearly generated tooling paths from coverage measurement to reduce coverage noise and focus on authored runtime code.

## 10. Long-Term Improvements

### 10.1 Choose a Permanent Runtime Topology Strategy

The project should eventually make an explicit architectural choice:

- remain intentionally single-host and simplify around that constraint
- or implement shared-state rate limits, caching, and multi-instance validation

Remaining in the current middle state is workable but not ideal long term.

### 10.2 Evolve Toward Smaller Core Components

The largest modules should be split into stable internal interfaces so that retrieval, corpus generation, and app wiring can evolve independently.

### 10.3 Strengthen the Model-Promotion Pipeline

If local models remain strategic, the project should extend the existing evidence contract into a full model-promotion pipeline with:

- benchmark dashboards
- regression comparisons against retrieval-only baselines
- artifact retention rules
- explicit promotion and rollback records

### 10.4 Deepen Operational Evidence

The repo already does more release validation than average. The next step is to make field-install evidence as strong as build-time evidence through:

- clean-host validation
- scheduled DR proof
- external-auth reference deployments
- formal environment promotion records

### 10.5 Clarify Product Scope for Quarantined Features

If search and runtime KG expansion are strategically important, they need dedicated investment and an operator-owned deployment path. If not, they should remain permanently quarantined and stop consuming roadmap attention.

## 11. Final Assessment

### Current Maturity Level

`Near production` for the documented Windows single-host baseline.

More precise breakdown:

- corpus, KG, CLI, and read-only API baseline: near production
- optional remote-answer generation: controlled optional capability
- optional local-adapter serving: not promotion-ready in the current workspace
- `/v1/search` and runtime KG expansion: quarantined and not production-ready

### Major Risks

1. Silent degradation from upstream client failures being represented as empty data.
2. Under-tested startup and optional-runtime paths relative to the maturity of the mainline code.
3. Architectural pressure from large modules and process-local runtime state.
4. Misuse of optional or quarantined capabilities as if they were part of the supported baseline.
5. Security evidence lagging behind build and release evidence.

### Estimated Effort Remaining

- Supported baseline hardening: `2 to 4 engineer-weeks`
- Optional capability graduation and broader production posture: `6 to 10+ engineer-weeks`

### Recommended Next Three Development Priorities

1. Harden live-source failure semantics and raise coverage on startup and optional-runtime hotspots.
2. Make hermetic deployment and security scanning part of the standard release-quality path.
3. Decide optional capability scope with evidence: either promote local-adapter and search/KG using real operator proof, or keep them explicitly optional/quarantined.

### Final Verdict

A new developer can take over this project effectively because the repository has unusually strong support-boundary documentation, release evidence, and operator guidance for its size. The codebase is not finished in every direction, but it is honest about that fact.

The supported product is narrower than the total code present in the repository. That is the right posture. The next phase should preserve that rigor: improve reliability and deployment evidence for the supported baseline first, then graduate optional capabilities only when the evidence actually supports promotion.

