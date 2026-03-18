# Run Pass 8

Audit date: 2026-03-18

## 1. Executive Summary

This repository is a Windows-first Python monorepo for the EAR AI / `earCrawler` program. In its supported form, it is a single-host compliance retrieval and question-answering system built around deterministic corpus generation, RDF knowledge graph emission, a FastAPI read API, and a guarded retrieval-augmented generation (RAG) pipeline. The codebase also contains research, optional capabilities, and quarantined legacy surfaces that are intentionally not part of the default production path.

The project is stronger than a prototype. It has a clear runtime boundary, disciplined release packaging, extensive documentation, and substantial automated test coverage. The supported path is coherent: build corpus and KG artifacts, load them into infrastructure the operator provides, expose a small read-only API, and optionally run grounded answer generation with local or remote large-language-model adapters under explicit policy gates.

The main concern is not lack of raw functionality. The main concern is alignment across supported, optional, and historical surfaces. Two mismatches are currently material:

1. The live test suite currently has one deterministic failure: `tests/perf/test_api_budget_gate.py::test_api_budget_gate_passes`. The budget gate expects `/v1/search` to be enabled, but the supported API app does not mount that route unless search is explicitly enabled. This creates noise in release confidence and obscures the intended support boundary.
2. The model-training surface has conflicting input defaults. The contract and index metadata identify `data/faiss/retrieval_corpus.jsonl` as the authoritative retrieval corpus, but Phase 5 training defaults still point at `data/retrieval_corpus.jsonl`, which currently contains only six records and appears to be an experimental derivative. That creates a real risk of training on the wrong corpus.

Current maturity is best described as `beta` for the supported single-host retrieval/API baseline and `alpha or research-only` for optional search, KG expansion, and local model-training paths. A new developer can take over effectively, but only if they are taught to treat the supported boundary documents as authoritative and to avoid assuming every folder in the repository is an active production surface.

Validation performed during this audit:

- `py -m pytest -q`: 422 passed, 8 skipped, 1 failed.
- `py eval/validate_datasets.py`: passed.
- `py -m earCrawler.cli diagnose`: passed and confirmed remote LLM access is disabled by policy in the current environment.

## 2. Project Architecture Overview

### System type

The repository is primarily a monorepo containing:

- a Python package (`earCrawler`) with the main supported runtime and data-processing logic
- a FastAPI service (`service/api_server`) that exposes the supported read API
- command-line tools (`earCrawler.cli`, plus some legacy/top-level `cli` utilities)
- build, release, evaluation, and packaging infrastructure
- research and experimental artifacts kept alongside production code

In practical terms, the deployed system is a single-host data and inference application, not a microservice mesh.

### Supported architecture boundary

The clearest architectural fact in this repository is that the team has intentionally narrowed the supported runtime:

- Supported by default: `earctl`, deterministic corpus and KG generation, a read-only API, health checks, entity lookup, SPARQL templates, lineage, and RAG query flow.
- Optional but gated: remote LLM providers, local adapter inference, hybrid retrieval, and `/v1/rag/answer`.
- Quarantined or legacy: `/v1/search`, runtime KG expansion dependency, legacy service modules, and legacy ingestion.

That distinction appears consistently in `README.md`, `RUNBOOK.md`, API artifacts, and several documents under `docs/`.

### Plain-language explanation

The project works in six layers:

1. Source data is transformed into a normalized retrieval corpus and RDF-style entity graph.
2. Deterministic manifests, hashes, and digests are written so outputs can be verified later.
3. The graph is validated and loaded into a SPARQL endpoint such as Fuseki.
4. A FastAPI server exposes a narrow, read-only interface for entity lookup, lineage, SPARQL templates, and RAG.
5. The RAG orchestrator retrieves evidence, enforces guardrails, optionally calls an LLM, and validates the response structure.
6. Audit, telemetry, policy, and packaging layers make the system operable on a single Windows host.

### Data flow

Primary supported flow:

1. `earCrawler.corpus.builder` creates a deterministic corpus with stable identities and manifests.
2. `earCrawler.kg.emit_ear`, `earCrawler.kg.triples`, and related validators generate RDF triples and integrity checks.
3. Operators provision or point the system at a Fuseki/SPARQL endpoint.
4. `service.api_server` loads configuration, retriever state, rate-limiting, observability, and template registry.
5. `/v1/entities`, `/v1/lineage`, and `/v1/sparql` answer directly from the graph or template layer.
6. `/v1/rag/query` and optionally `/v1/rag/answer` use the retriever and orchestrator to build evidence-grounded answers.

### Design patterns in use

- Contract-first boundaries: OpenAPI, manifest files, JSON contracts, evaluation manifests, and capability gates.
- Deterministic artifact generation: digests, manifests, reproducible corpus/KG outputs, and canonical freeze tooling.
- Adapter pattern for model providers: remote LLM providers and local adapter inference share common runtime contracts.
- Policy gating: features are turned on only when explicit environment variables or runtime settings allow them.
- Quarantine pattern: unstable or not-yet-supported features remain in-tree but outside the default runtime path.

### Dependency and service relationships

- `earCrawler` is the core domain package.
- `service/api_server` depends on `earCrawler` runtime modules, not the reverse.
- The API client package mirrors the supported API surface and intentionally excludes quarantined search by default.
- External services are limited and explicit: Fuseki/SPARQL, optional OpenAI-compatible remote LLM endpoints, and optional local adapter serving.

### State management and concurrency

State is mostly file- and artifact-based rather than database-centric. Persistent state lives in generated corpora, KG artifacts, manifests, index files, policy/config YAML, and external Fuseki data stores. Runtime state inside the API process is light and mostly read-only after startup.

The service uses standard async FastAPI patterns, request-scoped middleware, and bounded concurrency controls. Concurrency assumptions are intentionally conservative; the config enforces a single-instance model unless the operator overrides it explicitly.

## 3. Repository Structure Analysis

### High-level repository map

The workspace contains both maintained source and many generated or environment-specific directories. A new developer should focus first on the maintained sources below and treat `.venv*`, `dist/`, `run/`, `runs/`, `.pytest_tmp*`, and local Fuseki data directories as environment or output artifacts rather than primary code.

Core maintained structure:

```text
earCrawler/
├─ earCrawler/                 Main Python package
├─ service/api_server/         Supported FastAPI service
├─ api_clients/                Client wrappers for supported API and LLM calls
├─ config/                     Example contracts and runtime configuration inputs
├─ data/                       Corpus, FAISS, and runtime data artifacts
├─ db/                         Database and graph support assets
├─ docs/                       Architecture, operations, research boundary, and plans
├─ eval/                       Evaluation datasets, manifests, and validators
├─ kg/                         Top-level KG helpers/assets
├─ packaging/                  Packaging specs for executable distribution
├─ scripts/                    CI, release, data, training, and validation scripts
├─ security/                   Policy configuration
├─ tests/                      Unit, integration, performance, and policy tests
├─ README.md                   Primary orientation document
├─ RUNBOOK.md                  Supported operations runbook
├─ pyproject.toml              Package metadata and dependency declarations
└─ requirements*.txt/in        Python dependency pins and lock workflow
```

### Major directories and purpose

| Path | Purpose | Notes |
| --- | --- | --- |
| `earCrawler/` | Core implementation package for corpus building, KG logic, RAG, security, telemetry, audit, and CLI entrypoints. | This is the main code ownership center. |
| `service/api_server/` | FastAPI application, routers, middleware, auth, OpenAPI generation, and service config. | This is the supported API runtime. |
| `api_clients/` | Programmatic clients for the API and remote LLM providers. | Mirrors the supported service boundary and exposes quarantined search only by opt-in. |
| `docs/` | Operational guidance, design records, research-boundary documentation, and execution plans. | Essential for understanding which surfaces are intended to be used. |
| `eval/` | Evaluation datasets, manifests, and validation scripts. | Important evidence package for regression tracking. |
| `scripts/` | Build, packaging, release, training, benchmark, and verification scripts. | Large and important, but mixed between supported and experimental workflows. |
| `security/` | Policy YAML and related security controls. | Used by CLI role-based access and runtime policy. |
| `tests/` | Unit, integration, performance, CLI, packaging, security, and release verification tests. | Coverage is broad and operationally useful. |
| `config/` | Example contracts and config templates. | Some of these are authoritative; others have drifted from runtime truth. |
| `data/` | Runtime data artifacts, corpora, FAISS index metadata, and derived datasets. | Contains both authoritative and experimental files; this needs clearer labeling. |

### Key modules a new developer should understand first

| Module or file | Purpose |
| --- | --- |
| `earCrawler/corpus/builder.py` | Builds deterministic retrieval corpora and manifests from source material. |
| `earCrawler/corpus/identity.py` | Provides stable identity and content-hash logic. |
| `earCrawler/kg/emit_ear.py` | Emits knowledge-graph entities and triples for the EAR domain. |
| `earCrawler/kg/validate.py` | Runs KG validation and integrity checks. |
| `earCrawler/kg/loader.py` | Handles KG load workflows for downstream graph infrastructure. |
| `earCrawler/rag/orchestrator.py` | Central RAG workflow and orchestration logic. |
| `earCrawler/rag/retriever.py` | Dense and hybrid retrieval implementation. |
| `earCrawler/rag/retrieval_runtime.py` | Loads retrieval assets and runtime configuration. |
| `earCrawler/rag/output_schema.py` | Enforces strict answer schema and guardrails. |
| `earCrawler/security/data_egress.py` | Governs whether remote model calls are permitted. |
| `service/api_server/__init__.py` | Application factory and service composition entrypoint. |
| `service/api_server/routers/` | Supported API route definitions. |
| `service/api_server/templates.py` | Template registry and SPARQL parameter sanitization. |
| `api_clients/ear_api_client.py` | Client mirror of the supported service interface. |

### Libraries and platform dependencies

Important runtime libraries include:

- `fastapi`, `uvicorn`, `httpx`: service runtime and HTTP integration
- `click`: CLI framework
- `rdflib`, `pyshacl`, `SPARQLWrapper`: RDF, SHACL, and SPARQL operations
- `requests`, `tenacity`, `keyring`: HTTP integration, retries, and secret retrieval
- `PyYAML`, `tabulate`, `beautifulsoup4`: configuration and utility parsing
- optional retrieval/model extras: `sentence-transformers`, `torch`, `transformers`, `peft`, `faiss-cpu`

Platform dependencies and external services:

- Apache Jena / Fuseki 5.3.0 for SPARQL serving and graph storage
- Optional OpenAI-compatible remote LLM providers such as Groq and NVIDIA NIM
- Optional local adapter runtime for a fine-tuned local model
- Windows packaging stack via PyInstaller and Inno Setup

### Important documentation and control files

| File | Why it matters |
| --- | --- |
| `README.md` | Best starting point for supported vs optional vs quarantined surfaces. |
| `RUNBOOK.md` | Operational truth for the supported single-host deployment path. |
| `docs/start_here_supported_paths.md` | Fast orientation for new contributors. |
| `docs/runtime_research_boundary.md` | Critical explanation of what is research-only versus runtime-supported. |
| `service/openapi/openapi.yaml` | Contract artifact for the supported API surface. |
| `pyproject.toml` | Dependency declarations, package metadata, and test configuration. |
| `.github/workflows/ci.yml` | Main CI definition for supported paths. |
| `.github/workflows/kg-ci.yml` | Additional graph-focused validation pipeline. |
| `.github/workflows/release.yml` | Release packaging and verification workflow. |

### Current runtime data and model artifacts in the workspace

The current workspace contains evidence that the project is already generating real artifacts:

- `data/faiss/index.meta.json` records a FAISS-backed retrieval index built on 2026-02-10 with `3040` documents and embedding model `all-MiniLM-L12-v2`.
- `data/faiss/retrieval_corpus.jsonl` appears to be the authoritative corpus matched to that index.
- `eval/manifest.json` contains multiple evaluation datasets and a KG state digest, which is a strong sign of measurement discipline.

However, the workspace also contains `data/retrieval_corpus.jsonl`, a much smaller derived file that does not match the authoritative corpus scale. This is one of the clearest examples of repository ambiguity that needs cleanup.

## 4. Research and Concept Evaluation

### Intended conceptual model

The project is not trying to be a general chatbot. The underlying concept is an evidence-first regulatory analysis system:

- build a controlled corpus from legal or compliance-relevant source material
- represent important entities and relationships in a graph
- retrieve evidence deterministically
- use language models only as a bounded reasoning and synthesis layer
- preserve provenance, citations, and operator control over outbound data

That conceptual approach is consistent with the documentation set, especially the runtime-boundary documents, temporal reasoning notes, hybrid retrieval design, and model-training artifacts.

### Research assumptions and theoretical ideas present in the repository

Observed assumptions include:

- Grounded answers are safer than unconstrained generation for compliance use cases.
- Deterministic retrieval artifacts and graph lineage are necessary for auditability.
- Temporal reasoning matters; answers should respect dates and effective periods rather than only lexical match.
- Hybrid retrieval and KG expansion may improve answer quality, but should remain optional until performance and reliability evidence are strong enough.
- Local fine-tuning may eventually reduce dependence on external providers, but should be treated as an evidence-gated capability rather than assumed production truth.

### AI and model usage

Current model stack present in code and docs:

- Retrieval embeddings: `all-MiniLM-L12-v2` is the active embedding model recorded in current FAISS metadata.
- Remote generation providers: Groq and NVIDIA NIM are supported through an OpenAI-compatible client layer.
- Local generation path: the codebase references a local adapter workflow and documentation for a Qwen/Qwen2.5 7B-style instruction model path, but the repository does not currently contain a fully evidenced trained adapter artifact for a supported deployment.

The implementation uses models conservatively. Remote generation is disabled unless explicit policy and enablement flags are set, and the orchestrator validates structure and evidence before accepting output.

### Experimental components

Experimental or research-heavy components include:

- hybrid dense + BM25 retrieval
- runtime KG expansion
- local adapter model serving and training
- some training and benchmark scripts under `scripts/training/`
- legacy ingestion code preserved under experimental or quarantined paths

These are valuable research assets, but they are not uniformly promoted to the same reliability level as the supported runtime.

### Does implementation match the intended concept?

Mostly yes, with two notable exceptions.

What matches well:

- The supported runtime strongly reflects the evidence-first design.
- Output guardrails, provenance, and policy-gated remote inference are implemented rather than merely described.
- The API surface is narrow and read-only, which fits the audit-oriented product intent.

Where implementation does not fully match the intended concept:

1. The performance gate still assumes `/v1/search` is part of the default service shape, even though the architecture documents quarantine it. The most likely explanation is not that search has quietly re-entered the supported contract, but that an older benchmark fixture was kept to preserve latency coverage for the quarantined route while search stayed implemented for local validation and possible future graduation work. In other words, this looks more like boundary drift between research or staging coverage and the default runtime harness than a current product decision to treat `/v1/search` as supported-by-default. The codebase concept is clearer than the test gate.
2. The training workflow does not consistently point at the authoritative retrieval corpus. That undermines the stated model-training contract and weakens reproducibility for the local-model research path.

Overall assessment: the repository demonstrates unusually good conceptual discipline for an AI project, but a few execution details still blur the boundary between supported runtime and active experimentation.

## 5. Strengths

### 1. Explicit supported-vs-research boundary

The strongest decision in this repository is the repeated, explicit distinction between supported, optional, quarantined, and proposal-only surfaces. This reduces accidental scope creep, helps release management, and gives new developers a reliable frame for understanding what they can safely change.

### 2. Deterministic artifacts and contract orientation

Corpus builders, KG emitters, manifests, digests, OpenAPI artifacts, and evaluation manifests all push the system toward reproducibility. That is especially beneficial in compliance and AI settings, where vague data lineage quickly becomes unacceptable.

### 3. Coherent, narrow API surface

The supported API is intentionally read-only and limited to health, entity, lineage, SPARQL-template, and RAG operations. That reduces attack surface, keeps operational behavior understandable, and makes client compatibility easier to preserve.

### 4. Strong RAG guardrails

The RAG stack is not a thin wrapper around an LLM. It includes retrieval runtime controls, temporal logic, structured output validation, and egress policy checks. These protections materially improve trustworthiness relative to a generic prompt-and-respond design.

### 5. Good separation between core package and service layer

`earCrawler` contains domain logic while `service/api_server` composes runtime concerns around it. That separation supports testing, reuse, and future service evolution without forcing all logic into route handlers.

### 6. Security posture is cautious by default

Remote model calls are disabled by default, API keys are compared with constant-time checks, keyring integration exists, and SPARQL templates are parameter-sanitized and registry-driven. The project is not security-complete, but the default posture is careful.

### 7. Observability and audit support are built in

Audit ledger modules, telemetry configuration, observability middleware, watchdog support, and release verification scripts are already present. That gives operators and future maintainers a useful base for incident analysis and deployment confidence.

### 8. Broad automated validation

The test suite covers unit, integration, policy, packaging, evaluation, and performance concerns. Even though one performance test currently fails, the breadth of verification is a real strength and indicates engineering maturity.

### 9. Strong Windows operational focus

Packaging specs, installer definitions, release workflows, and Windows operator documentation are unusually complete for a Python AI project. This improves handoff quality for the actual deployment environment the repository targets.

### 10. Honest single-host constraint

The service configuration explicitly rejects multi-instance deployment unless overridden. That honesty is beneficial: it prevents accidental overstatement of scalability and forces architectural decisions to be made deliberately instead of by implication.

## 6. Weaknesses and Remediation Steps

| Category | Problem | Why it matters | Technical impact | Risk | Concrete remediation |
| --- | --- | --- | --- | --- | --- |
| Testing / Architecture | The current suite has a deterministic failure in `tests/perf/test_api_budget_gate.py::test_api_budget_gate_passes`. The budget gate expects `/v1/search` to return success, but `service/api_server` only mounts search when explicitly enabled. | It creates false confidence signals and confuses the supported boundary. A new developer cannot tell whether search is meant to be default-on, optional, or retired. | CI and local release confidence are degraded; performance baselines no longer match runtime truth. | High | Update `earCrawler/perf/api_budget_gate.py` and the related test to measure only the supported default routes, or explicitly enable search in the benchmark harness and classify it as quarantined coverage. Document the choice in the perf gate and runbook. |
| Data / AI workflow | Training defaults are inconsistent. `config/training_input_contract.example.json` and docs point to `data/faiss/retrieval_corpus.jsonl`, but `scripts/training/run_phase5_finetune.py`, `config/training_first_pass.example.json`, and related docs still default to `data/retrieval_corpus.jsonl`. | This risks training or benchmarking against the wrong corpus, which directly undermines reproducibility and model-evaluation validity. | Local model work can silently use a six-record derivative instead of the 3040-record indexed corpus. | High | Make one retrieval corpus path authoritative across code, docs, and config. Prefer the indexed `data/faiss/retrieval_corpus.jsonl` unless there is a documented experimental reason not to. Add a preflight that refuses to train if corpus path and index metadata disagree. |
| Performance / Scalability | `earCrawler/kg/reconcile.py` performs pairwise reconciliation across all entity combinations even though blocking-key helpers exist. | This will not scale as entity counts grow and will make reconciliation cost rise quadratically. | Larger corpora will see avoidable latency and compute growth; future batch jobs may become impractical. | Medium-High | Replace the all-pairs loop with real block partitioning using the existing blocking-key concepts, then add benchmark tests to measure candidate reduction and recall. |
| Maintainability | The repository contains multiple overlapping entry surfaces: `earCrawler/cli`, top-level `cli`, `service/api_server`, legacy `earCrawler/service` modules, archived docs, and experimental scripts. | Onboarding is slower because active ownership boundaries are not visible from the directory tree alone. | Developers can modify the wrong surface or assume historical modules remain production-critical. | Medium | Publish a single architecture index that maps each top-level directory to one of: supported, optional, quarantined, generated, or archival. For code, consider consolidating or clearly deprecating the top-level `cli/` package. |
| Reliability / Evidence | The optional local-model path is implemented in code and docs, but the workspace does not contain a clearly supported `dist/training/<run_id>` adapter artifact or benchmark evidence package tied to release criteria. | The feature can appear more mature than it is, leading to premature adoption or unclear ownership. | Operators cannot reliably tell whether local inference is deployment-ready or still research-only. | Medium | Define a minimum evidence bundle for local models: adapter artifact, evaluation report, benchmark thresholds, provenance manifest, and rollback guidance. Require that bundle before promoting the local path beyond optional/research status. |
| Deployment | The supported operator docs assume a Fuseki/SPARQL endpoint exists, but the repository does not provide a full deployed-host provisioning or lifecycle story for that dependency. | Production handoff is incomplete without a repeatable graph-service provisioning path. | Environment setup remains partly manual and may differ across hosts, reducing reproducibility. | Medium | Add provisioning and recovery guidance for Fuseki, including version pin, directory layout, backup/restore, startup order, health checks, and upgrade procedure. If the operator must supply Fuseki externally, state that as a hard dependency in release artifacts. |
| Security / Product scope | API authentication is adequate for loopback or tightly controlled single-host exposure, but it is still a static shared-secret model rather than a robust enterprise front door. | If the service scope broadens later, the current auth model will become a weak point. | Limited identity, rotation, and authorization granularity for non-local deployments. | Medium | Keep current auth for the supported single-host mode, but define an external auth front-door pattern for any wider deployment: reverse proxy auth, service identity, rotation policy, and request attribution. |
| Documentation / Data hygiene | `data/` mixes authoritative runtime assets and experimental derivatives. Some generated or archived paths are also present at the repository root. | Mixed data truth creates avoidable mistakes during training, evaluation, and debugging. | Developers may use stale or partial artifacts without realizing it. | Medium | Label authoritative versus experimental data directories clearly, move derivatives into an `experimental/` or `scratch/` path, and document artifact lineage in a single data inventory page. |
| Technical debt | Quarantined and legacy modules remain in-tree, including legacy ingestion and service code. | Keeping them is reasonable, but they still impose cognitive load and can silently drift. | Test and maintenance burden stays higher than necessary. | Low-Medium | Either keep them under a clearly isolated legacy namespace with explicit non-support notices, or remove/archive the modules that no longer serve an active migration purpose. |

## 7. Missing Components

The repository is close to a disciplined single-host baseline, but several pieces are still missing for a production-ready claim.

| Missing component | What it should do | Why it is needed |
| --- | --- | --- |
| Search/KG graduation evidence package | Define the exact reliability, performance, and operator evidence required before `/v1/search` or runtime KG expansion become supported defaults. | The code contains these capabilities, but the support boundary is still inconsistent in tests and scripts. |
| Single authoritative training input contract | Establish one canonical corpus path and one canonical training manifest for local-model workflows. | Without this, training reproducibility remains fragile. |
| Local-model release artifact bundle | Provide a real, versioned adapter artifact plus evaluation and provenance metadata for the supported local inference path. | The code supports the path, but deployment evidence is incomplete. |
| Fuseki provisioning and disaster-recovery package | Define installation, backup, restore, and lifecycle management for the graph dependency. | The current runbook assumes the service exists but does not fully operationalize it. |
| Multi-instance coordination design | If scaling beyond one instance is ever required, define cache, rate-limit, and shared-state behavior explicitly. | Current behavior is intentionally single-host; broader deployment would require real design work. |
| Stronger external authentication pattern | Add a supported integration pattern for enterprise auth if the service is exposed beyond loopback or trusted internal use. | Current auth is suitable only for the constrained deployment model. |
| Domain-specific legal/compliance model evidence | Show whether a local model actually improves legal/regulatory reasoning enough to justify deployment. | The project mentions local model training, but evidence for a production-grade legal interpretation model is not yet present in the workspace. |

## 8. Development Roadmap

### Phase A - Stabilization

| Task | Affected files | Implementation suggestions | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Fix the failing search performance gate | `tests/perf/test_api_budget_gate.py`, `earCrawler/perf/api_budget_gate.py`, `service/api_server/__init__.py`, related perf docs | Decide whether search remains quarantined or is intentionally benchmarked. Then align the harness, expected route set, and docs to one truth. | Small | Critical | None |
| Align all training defaults with the authoritative retrieval corpus | `scripts/training/run_phase5_finetune.py`, `config/training_first_pass.example.json`, `config/training_input_contract.example.json`, `docs/model_training_contract.md`, `docs/model_training_first_pass.md` | Pick one canonical corpus path, update every default to it, and add a runtime preflight that verifies corpus size and digest against index metadata. | Medium | Critical | None |
| Mark or relocate the six-record derived corpus | `data/retrieval_corpus.jsonl`, docs that reference it | If still useful, move it under an experimental location and document its purpose. Otherwise remove it from the supported training path entirely. | Small | High | Training contract alignment |
| Publish a root-level repository status index | New `docs/` inventory page, updates to `README.md` or `docs/start_here_supported_paths.md` | Create a one-page map labeling each top-level directory as supported, optional, quarantined, generated, or archival. | Small | High | None |

### Phase B - Architecture Improvements

| Task | Affected files | Implementation suggestions | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Implement true blocked reconciliation | `earCrawler/kg/reconcile.py`, reconciliation tests, performance benchmarks | Use blocking keys to generate candidate partitions before pair comparison. Add precision/recall and runtime benchmarks. | Medium | High | Stabilization complete |
| Centralize capability-state policy | `README.md`, `RUNBOOK.md`, `docs/runtime_research_boundary.md`, service config or a new machine-readable policy file | Introduce one machine-readable manifest that marks each feature as supported, optional, quarantined, or legacy, then consume it in tests/docs where practical. | Medium | High | Repository status index |
| Simplify or clearly deprecate overlapping CLI surfaces | `earCrawler/cli/`, top-level `cli/`, docs referencing both | Either merge the remaining useful top-level CLI commands into the main package or label the top-level package as legacy-only. | Medium | Medium | Repository status index |
| Create a formal data artifact inventory | `docs/`, `data/`, maybe a generated manifest script | Document each artifact, its source, whether it is authoritative, and which workflows depend on it. | Small-Medium | Medium | Training contract alignment |

### Phase C - Feature Completion

| Task | Affected files | Implementation suggestions | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Produce a real local-adapter release candidate | `scripts/training/`, `config/`, `docs/model_training_*`, `dist/training/` outputs | Run the full training workflow against the authoritative corpus, package the adapter, and archive provenance plus benchmark results. | Large | High | Stabilization, authoritative training contract |
| Decide the future of `/v1/search` | Search router/tests/docs/client code | Either graduate it with evidence and default-on support, or keep it quarantined and remove it from default gates and client expectations. | Medium | High | Perf gate fix, capability-state policy |
| Decide the future of runtime KG expansion | `earCrawler/rag/kg_expansion_fuseki.py`, docs, benchmarks | Benchmark quality and latency, then either graduate with thresholds or keep it as research-only. | Medium-Large | Medium | Capability-state policy |
| Complete end-to-end deployed-host graph workflow | Operator docs, packaging docs, automation scripts | Provide a supported method to provision, validate, back up, and restore Fuseki for the target deployment model. | Medium | High | Architecture improvements |

### Phase D - Production Hardening

| Task | Affected files | Implementation suggestions | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Add release-shaped smoke tests for deployed hosts | CI workflows, packaging scripts, operator verification scripts | Validate the packaged executable/installer against the supported runtime contract on a clean host image or equivalent CI environment. | Medium | High | Feature completion baseline |
| Strengthen auth and secret lifecycle guidance | `service/api_server/auth.py`, secret-handling docs, operator docs | Keep current single-host auth, but document an approved reverse-proxy or enterprise-auth integration for wider exposure. | Medium | Medium | Deployment workflow definition |
| Continuously validate backup and restore | Fuseki operations docs, scripts, CI or scheduled validation jobs | Add repeatable tests or runbooks that prove recovery works from released artifacts and graph data backups. | Medium | Medium | Deployed-host graph workflow |
| Remove or archive obsolete legacy surfaces | Legacy service and ingestion modules, docs | After migration decisions are made, reduce dead weight so the supported path is easier to maintain. | Small-Medium | Medium | Capability decisions complete |

## 9. Quick Wins

The following improvements should each be feasible in less than one day and would materially improve the project:

- Fix the `/v1/search` performance gate mismatch so the test suite reflects the intended support boundary.
- Change all training defaults to the authoritative retrieval corpus and add a simple corpus digest preflight.
- Add a one-page repository inventory that labels supported, optional, quarantined, generated, and archival directories.
- Move or clearly relabel `data/retrieval_corpus.jsonl` so it cannot be mistaken for the main training corpus.
- Add a short supported-vs-legacy CLI table to onboarding docs.
- Add a note in the runbook that Fuseki is an operator-supplied dependency until provisioning automation is added.

## 10. Long-Term Improvements

- Introduce a machine-readable capability registry that can drive docs, tests, packaging gates, and client surface generation from one source of truth.
- Redesign reconciliation for scalable candidate generation and benchmark it against larger entity sets.
- Formalize a model registry for local adapters, including corpus digest, eval version, benchmark scores, and release eligibility.
- If broader deployment becomes a goal, design a true multi-instance architecture instead of incrementally weakening the current single-host assumption.
- Split research and production assets more aggressively, potentially into clearly separated workspace areas or packages, to reduce onboarding ambiguity.

## 11. Final Assessment

### Current maturity level

`Beta` for the supported single-host corpus/KG/API/RAG baseline. `Alpha or research-only` for optional search, KG expansion, and local-model training/deployment paths.

### Major risks

- Support-boundary drift between tests, docs, and runtime behavior
- Training on the wrong corpus because of conflicting defaults
- Operational incompleteness around Fuseki lifecycle management
- Performance limits in reconciliation as data volume grows
- Ambiguity caused by mixed supported, legacy, and experimental assets in one workspace

### Estimated effort remaining

For a clean, supportable single-host baseline: roughly 3 to 6 engineer-weeks, assuming one developer focuses on stabilization, doc alignment, and deployment workflow closure.

For optional capability graduation such as local models or default-on search: an additional 6 to 10 engineer-weeks is realistic, mostly because those paths need evidence, benchmarking, packaging discipline, and support policy decisions rather than just more code.

### Recommended next three development priorities

1. Fix the failing performance gate and align all support-boundary tests with the actual default runtime.
2. Unify the training corpus contract across code, docs, configs, and generated artifacts.
3. Decide, with evidence, whether search and runtime KG expansion are being promoted or intentionally kept quarantined.

Overall conclusion: this is a serious codebase with better architectural discipline than most AI projects at the same maturity stage. The path to a stable handoff is not to add more major features first. The path is to tighten the boundary between supported runtime and active research, then operationalize the missing deployment and model-evidence pieces behind that boundary.
