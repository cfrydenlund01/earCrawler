# RunPass11

> Archive note (2026-04-07): Active local-adapter baseline switched to `google/gemma-4-E4B-it`. This archived document is retained for historical context only and no longer governs active execution.


Prepared: March 19, 2026

Scope: full repository and workspace audit for the currently open `earCrawler` project, including source, docs, config, dependencies, tests, generated artifacts, release evidence, and research material.

Audit basis:

- Repository source, docs, config, and scripts under the current workspace root
- Workspace-generated state in `build/`, `dist/`, `.pytest_tmp*`, `.venv*`, `run/`, and `runs/`
- Validation run on March 19, 2026:
  - `.venv\Scripts\python.exe eval\validate_datasets.py` -> passed
  - `.venv\Scripts\python.exe -m pytest -q` -> `481 passed, 7 skipped, 1 failed`
- Existing evidence artifacts reviewed:
  - `dist/security/security_scan_summary.json`
  - `dist/installed_runtime_smoke.json`
  - `dist/release_validation_evidence.json`
  - `dist/training/step52-real-candidate-gpt2b-20260319/release_evidence_manifest.json`
  - `docs/production_beta_readiness_review_2026-03-19.md`

---

## 1. Executive Summary

`earCrawler` is a modular Python monorepo that implements a deterministic regulatory-data pipeline, RDF knowledge-graph emission and validation flow, a supported read-only FastAPI service, and an evidence-heavy evaluation and Windows release process. Architecturally, it is strongest as a single-host, Windows-first regulatory retrieval and provenance system. It is not a microservice platform and it is not a production-ready multi-instance application.

The current source tree is disciplined about support boundaries. The supported baseline is narrow: `earctl`, `service.api_server`, deterministic corpus/KG artifacts, and a loopback-first Windows operator path. Optional features such as `/v1/rag/answer`, hybrid retrieval, and local-adapter serving are explicitly gated. `/v1/search` and KG-backed runtime expansion remain quarantined.

The current workspace is more mixed than the authored source. The git worktree is clean, but the workspace contains a large amount of generated state in `dist/`, `build/`, `.venv*`, `.pytest_tmp*`, and cache-only ghost directories such as `earCrawler/agent`, `earCrawler/models/legalbert`, and `earCrawler/quant`. Those are not active source features, but they materially increase takeover confusion.

Current maturity assessment: `beta / pre-production hardening`, not production-ready as a whole workspace. The supported baseline is close to a production-beta shape, but the workspace still exhibits evidence drift and capability gaps. The clearest example is that the full test suite currently fails one release-validation test because an existing `dist/earcrawler-kg-dev-20260319-snapshot.zip` artifact no longer matches `dist/checksums.sha256`. That is not a core logic failure; it is a release-workspace integrity failure, which still matters for handoff and operational trust.

The project is in a strong position for continued development by a new engineer, but the next stage should focus on workspace hygiene, release-evidence reproducibility, and reducing confusion between supported runtime code, quarantined capability code, and generated leftovers.

---

## 2. Project Architecture Overview

### Application type

The system is best described as a modular monolith with four tightly related surfaces:

- a supported CLI application (`earctl`)
- a supported FastAPI read-only service (`service.api_server`)
- a deterministic corpus -> KG artifact pipeline
- an evaluation, packaging, and release-evidence toolchain

It also contains optional and quarantined AI/RAG features, but those are intentionally not the baseline product.

### Plain-language architecture

In plain terms, the system does this:

1. Pull or replay EAR and NSF/ORI source material from fixtures or upstream services.
2. Normalize that material into deterministic corpus records with stable IDs, hashes, provenance metadata, and manifests.
3. Emit RDF/Turtle knowledge-graph files and validate them with SHACL plus SPARQL integrity checks.
4. Optionally load/query those graph artifacts through a local Apache Jena Fuseki service.
5. Build and use a retrieval corpus and vector index for RAG-style question answering.
6. Expose a controlled read-only HTTP API over curated KG templates and retrieval.
7. Optionally call remote LLM providers or a local adapter runtime for generated answers.
8. Measure everything with evaluation datasets, release smoke tests, security scans, signed manifests, and Windows operator workflows.

### Major architecture patterns

- Modular monolith: most logic lives in the `earCrawler/` package with clear functional subpackages.
- Contract-first runtime: OpenAPI, capability registry, Pydantic schemas, and runtime contract output from `/health`.
- Deterministic artifact pipeline: manifests, checksums, canonical ordering, baseline freezes, reproducibility tooling.
- Adapter/wrapper pattern: upstream clients in `api_clients/` abstract Trade.gov, Federal Register, ORI, and downstream API access.
- Feature-gating pattern: optional and quarantined features are controlled by explicit env gates and documented capability states.
- Retrieval orchestration pattern: retrieval, temporal filtering, KG expansion, generation policy, and output validation are separated into dedicated RAG modules.
- Process-local runtime state abstraction: rate limiting and RAG cache are explicit, not hidden globals.
- Evidence-driven release pattern: release quality depends on smoke tests, security scans, signed checksums, canonical manifests, and installed-runtime validation.

### Dependency relationships

Core dependency flow:

- `earCrawler.cli` depends on most application packages and registers supported command groups.
- `service.api_server` depends on `earCrawler.rag`, `earCrawler.observability`, template registries, and Fuseki gateway abstractions.
- `earCrawler.corpus` depends on `earCrawler.core`, `api_clients`, and corpus identity/metadata helpers.
- `earCrawler.kg` depends on corpus artifacts plus RDF/SPARQL/SHACL libraries.
- `earCrawler.rag` depends on retrieval artifacts, optional ML packages, upstream clients, and LLM configuration.
- `scripts/` orchestrates build, release, security, canary, benchmark, and operator tasks around those package surfaces.

### Data flow

Primary data flow:

- Upstream or fixture input
- `earCrawler.core` parsers/loaders
- `earCrawler.corpus` normalization and manifests
- `data/*_corpus.jsonl` plus `data/manifest.json`
- `earCrawler.kg.emit_*` -> `kg/*.ttl` or `data/kg/*.ttl`
- `earCrawler.kg.validate` / Fuseki
- retrieval corpus and FAISS sidecars in `data/faiss/`
- API routes in `service/api_server`
- optional eval, benchmark, and release evidence in `dist/`

RAG data flow:

- Request -> API route -> retriever loader / cache
- dense or hybrid retrieval over `data/faiss/`
- optional temporal filtering
- optional KG expansion
- prompt assembly and generation policy checks
- optional remote/local LLM call
- strict output validation and groundedness checks
- response plus structured telemetry/audit events

### Model interactions

Supported baseline model behavior:

- Retrieval embeddings use SentenceTransformers, defaulting to `all-MiniLM-L12-v2`.
- Dense retrieval can run via FAISS or brute-force cosine search.
- Hybrid retrieval adds BM25 fusion and remains optional.
- Remote generation uses OpenAI-compatible providers through Groq or NVIDIA NIM.
- Local generation exists only as a gated optional adapter runtime.

Training and local-model posture:

- The codebase contains a planning and evidence workflow for local adapter candidates.
- The selected future base-model target is `google/gemma-4-E4B-it`.
- The currently reviewed local training candidate under `dist/training/step52-real-candidate-gpt2b-20260319/` is not reviewable for promotion and remains optional.

### State management

State is split into:

- file-based deterministic artifacts: corpus JSONL, KG TTL, manifests, baseline snapshots, eval outputs
- OS or host state: Windows Credential Store, environment variables, NSSM/Fuseki services
- process-local runtime state: in-memory rate limiter, RAG query cache, retriever warm/cache state

This is a deliberate design choice, but it means scale-out is not supported.

### Concurrency and async patterns

- FastAPI routes are async.
- Blocking retriever and LLM calls are pushed through `asyncio.to_thread`.
- Request concurrency is limited via middleware.
- Rate limiting is token-bucket style and in-memory.
- Warmup uses thread-based timeout control.
- No distributed job queue, no shared cache, and no multi-process coordination layer exists.

### External services and integrations

- Trade.gov Consolidated Screening List API
- Federal Register API
- ORI / HHS case pages
- Apache Jena Fuseki
- Windows Credential Manager
- Groq
- NVIDIA NIM
- GitHub Actions
- NSSM for Windows service hosting
- optional Inno Setup for installer creation

### Architecture verdict

The architecture is coherent for a single-host, evidence-oriented regulatory retrieval product. It is not architected for distributed serving, generalized agent workflows, or autonomous legal reasoning. The code matches the narrower, safer deployment story better than the broader research ambition.

---

## 3. Repository Structure Analysis

### High-level structure

```text
.
├─ README.md / RUNBOOK.md / pyproject.toml / requirements*
├─ earCrawler/                  # main Python package
│  ├─ cli/                      # supported CLI entrypoints and grouped commands
│  ├─ core/                     # source crawlers, parsers, loaders
│  ├─ corpus/                   # deterministic corpus build/validate/snapshot
│  ├─ kg/                       # RDF emit, validation, Fuseki helpers, integrity
│  ├─ rag/                      # retriever, temporal logic, generation, local adapter
│  ├─ eval/                     # groundedness, citation, evidence metrics
│  ├─ security/                 # RBAC, secrets, egress policy
│  ├─ observability/            # health budgets, canary/watchdog config
│  ├─ telemetry/                # telemetry config, redaction, sinks
│  ├─ audit/                    # audit ledger and required event contracts
│  ├─ trace/                    # trace packaging
│  ├─ analytics/                # reporting helpers
│  ├─ monitor/                  # run logging and state merge helpers
│  ├─ privacy/                  # privacy/redaction helpers
│  ├─ service/legacy            # quarantined legacy service code
│  ├─ ingestion/                # quarantined legacy ingestion placeholder
│  └─ agent/, models/, quant/   # workspace ghost dirs / unsupported signals
├─ service/api_server/          # supported FastAPI runtime
├─ api_clients/                 # upstream and downstream HTTP clients
├─ docs/                        # active docs, ops, API, ADRs, reviews
├─ eval/                        # evaluation datasets, schema, manifests
├─ kg/                          # ontology, baseline, queries, scripts, canonical data
├─ data/                        # retrieval corpus, FAISS index, FR sections, manifests
├─ scripts/                     # build, release, security, eval, training, ops automation
├─ tests/                       # broad validation suite
├─ security/                    # top-level RBAC policy and security config
├─ config/                      # example env/config inputs for runtime and training
├─ bundle/ packaging/ installer/# release and offline packaging assets
├─ Research/                    # research notes, prompts, manuscript planning
├─ build/ dist/ run/ runs/      # generated workspace state
└─ .venv* / .pytest_tmp*        # local environment and test state
```

### Purpose of each major component

| Path | Purpose |
| --- | --- |
| `earCrawler/cli` | Supported CLI surface and command registration. |
| `service/api_server` | Supported HTTP runtime exposing curated read-only routes. |
| `api_clients` | Integrations for Trade.gov, Federal Register, ORI, remote LLMs, and the EarCrawler API itself. |
| `earCrawler/core` | Low-level crawling and parsing for EAR and NSF/ORI content. |
| `earCrawler/corpus` | Canonical corpus builder, manifesting, hashing, and validation logic. |
| `earCrawler/kg` | RDF/Turtle emission, SHACL/SPARQL validation, Fuseki/Jena glue, and integrity checks. |
| `earCrawler/rag` | Retrieval, temporal selection, KG expansion, prompt building, generation orchestration, output contracts. |
| `earCrawler/eval` | Groundedness scoring, evidence resolution, label inference, provenance for evaluation. |
| `earCrawler/security` | CLI policy enforcement, credential lookup, data-egress controls. |
| `earCrawler/observability` | Request logging, health budgets, canary/watchdog configuration. |
| `earCrawler/telemetry` | Telemetry config, spool handling, redaction, sink plumbing. |
| `earCrawler/audit` | Append-only audit ledger and required event emission. |
| `service/templates` | Allowlisted SPARQL templates used by `/v1/sparql`, entities, lineage, and search. |
| `docs/ops` | Windows single-host operator procedures, backup/restore, release handling, auth front door. |
| `eval/` | Held-out datasets plus schema and manifest. |
| `kg/` | Canonical KG assets, baseline snapshots, queries, and release/canonical freeze tooling. |
| `scripts/` | Most operational and release automation. |
| `Research/` | Research planning, decision logs, prompt packs, manuscript outlines. |
| `dist/` | Generated evidence, build outputs, eval outputs, training runs, bundles. |
| `build/` | Build intermediates and packaged copies; not authored source. |

### Key files

| File | Role |
| --- | --- |
| `pyproject.toml` | Package metadata, dependencies, entrypoints, coverage rules. |
| `README.md` | Canonical support boundary and developer/operator orientation. |
| `RUNBOOK.md` | Release workflow, runtime notes, and operational command references. |
| `security/policy.yml` | CLI RBAC policy and test identities. |
| `service/openapi/openapi.yaml` | API contract source of truth. |
| `service/docs/capability_registry.json` | Machine-readable capability-state source of truth. |
| `docs/repository_status_index.md` | Repository map by support status. |
| `docs/runtime_research_boundary.md` | Boundary between supported runtime and research/proposal content. |
| `docs/ops/windows_single_host_operator.md` | Main operator handoff document for the supported deployment shape. |
| `eval/manifest.json` | Eval dataset catalog plus pinned KG/references. |
| `data/faiss/index.meta.json` | Retrieval index sidecar and corpus provenance. |
| `dist/release_validation_evidence.json` | Current workspace release evidence summary. |

### Libraries used

Core runtime and tooling libraries:

- `click`
- `fastapi`
- `uvicorn`
- `requests`
- `httpx`
- `tenacity`
- `keyring`
- `rdflib`
- `pyshacl`
- `SPARQLWrapper`
- `beautifulsoup4`
- `PyYAML`
- `jsonschema`
- `pytest`, `pytest-cov`, `pytest-socket`, `requests-mock`, `vcrpy`
- optional ML stack: `sentence-transformers`, `faiss-cpu`, `torch`, `transformers`, `peft`

### Repository status and workspace observations

Important observations for takeover:

- The authored repository is intentionally partitioned by support state and does this well.
- The workspace is not minimal. It contains:
  - `dist/` with hundreds of generated files
  - `build/` intermediates and stale packaged copies
  - multiple virtual environments
  - test temp directories
  - cache-only ghost directories that contradict some ADR wording if inspected naively
- New developers should treat `docs/repository_status_index.md` and `docs/data_artifact_inventory.md` as mandatory before trusting what they see in the raw workspace.

---

## 4. Research and Concept Evaluation

### Research assumptions and theoretical framing

The research thread behind this project is clear:

- explainable regulatory QA is more valuable than opaque generation
- citation-grounded answers are necessary for trust
- a knowledge graph can improve structure, lineage, and possibly reasoning
- temporal accuracy matters because regulations change over time
- local model candidates should be evaluated with explicit evidence rather than promoted because code exists

This is visible in:

- `Research/` planning and manuscript materials
- `docs/hybrid_retrieval_design.md`
- `docs/temporal_reasoning_design.md`
- `docs/model_training_surface_adr.md`
- `docs/local_adapter_release_evidence.md`
- `earCrawler/eval/groundedness_gates.py`
- `earCrawler/rag/temporal.py`

### AI model usage

The project currently uses AI in three different layers:

1. Retrieval embeddings
   - SentenceTransformer-based retrieval, defaulting to `all-MiniLM-L12-v2`
2. Optional generation
   - OpenAI-compatible remote APIs via Groq or NVIDIA NIM
3. Optional future local serving
   - local adapter runtime with explicit artifact validation

The training story is intentionally partial:

- the intended base model is `google/gemma-4-E4B-it`
- the current local candidate reviewed in the workspace is based on `hf-internal-testing/tiny-random-gpt2`
- the current candidate fails its evidence contract and remains optional

### Experimental and quarantined components

Experimental or gated concepts include:

- hybrid dense + BM25 retrieval
- KG expansion during RAG
- text-backed search via Fuseki
- local-adapter serving
- training and benchmark bundle generation

These are implemented enough to test, but not promoted enough to treat as default product behavior.

### Does implementation match the intended concept?

Partially yes, and the differences are important:

- The code strongly matches the explainable, citation-grounded, deterministic, provenance-heavy concept.
- The code only partially matches the broader research vision of advanced KG-backed reasoning and local regulatory-model serving.
- The project is disciplined about this mismatch; it does not silently pretend that experimental capability is production capability.

Where the implementation matches well:

- deterministic corpus and KG artifact production
- groundedness and citation metrics
- temporal retrieval logic
- provenance and audit thinking
- explicit optional/quarantined boundaries

Where the implementation falls short of the research ambition:

- no production-validated local legal/regulatory interpretation model
- no promoted KG-expansion runtime path
- no search capability promotion
- no evidence that multi-instance or larger-scale service architecture is ready

### Concept evaluation verdict

The implemented system is a strong regulatory evidence platform with optional AI layers, not yet a full explainable regulatory AI product in the broader research sense. The conservative boundary management is a strength, not a weakness.

---

## 5. Strengths

1. Support-boundary discipline is unusually strong.
   - The repo clearly separates `supported`, `optional`, `quarantined`, `generated`, and `archival` surfaces through docs and machine-readable capability state.
   - This reduces accidental over-claiming and makes operator expectations defensible.

2. Artifact determinism is a major architectural asset.
   - Corpus outputs, KG outputs, manifests, checksums, baseline freezes, and release verification are first-class concerns.
   - This makes debugging, auditing, regression detection, and release review substantially easier.

3. The FastAPI runtime is narrow and intentionally curated.
   - The API exposes allowlisted templates and read-only projections rather than a broad arbitrary graph surface.
   - That reduces attack surface and makes contract management realistic.

4. Retrieval and answer-generation guardrails are thoughtful.
   - Temporal filtering, retrieval-empty handling, refusal policy, strict JSON validation, citation validation, and groundedness metrics show mature risk awareness.
   - This is exactly the right design bias for a regulatory QA product.

5. Tests cover the repo broadly.
   - The suite spans API, RAG, KG, release workflows, security, observability, CLI, bundle flows, telemetry, and privacy.
   - Even with one current failure, the test surface demonstrates real engineering rigor.

6. Release and operator evidence is much stronger than in most prototypes.
   - Installed-runtime smoke, optional-runtime smoke, security baseline, signed checksums, canonical manifests, and Windows operator docs are all present.
   - This materially lowers handoff and deployment risk.

7. Security posture is pragmatic and aligned to the deployment model.
   - RBAC for CLI operations, keyring/env secret handling, shared-secret API auth for single-host use, and the IIS front-door guidance for broader exposure are coherent.
   - The project avoids pretending that a simple built-in auth model is internet-grade by itself.

8. Research-to-runtime separation is explicit.
   - `Research/`, proposal docs, optional training artifacts, and quarantined runtime features are documented as such.
   - This makes the repo usable by both product engineers and research contributors without fully conflating the two.

9. The codebase has very little obvious marker-style debt.
   - No obvious `TODO`, `FIXME`, `XXX`, or `HACK` markers were found in the current workspace scan.
   - Debt here is structural and operational, not hidden in casual placeholders.

---

## 6. Weaknesses and Remediation Steps

| Category | Problem | Why it matters | Technical impact | Risk | Remediation |
| --- | --- | --- | --- | --- | --- |
| Reliability / Release | The current workspace fails `tests/release/test_verify_script.py::test_verify_detects_tamper` because `dist/earcrawler-kg-dev-20260319-snapshot.zip` does not match `dist/checksums.sha256`. | Release verification is only credible if generated artifacts and checksums stay synchronized. | Full-suite confidence is reduced; release-oriented tests are not hermetic against mutable workspace state. | High | Make release-verification tests isolate their own artifact directories, or refresh/segregate mutable `dist/` artifacts before test execution. Add a workspace hygiene step that rejects stale release artifacts before running release tests. |
| Workspace hygiene | The workspace contains ghost or cache-only directories such as `earCrawler/agent`, `earCrawler/models/legalbert`, `earCrawler/quant`, `tests/agent`, and `tests/models`, while docs say those surfaces are absent or unsupported. | A new developer can mistake cache leftovers for supported code or half-removed features. | Increases onboarding confusion and weakens trust in documentation. | Medium | Purge cache-only unsupported directories from the workspace, or add explicit ignore/cleanup scripts. Tighten docs to say these may appear as local leftovers and must not be treated as source. |
| Architecture / Packaging | Dependency truth is duplicated between `requirements.in`/lockfiles and `pyproject.toml`. | Divergent dependency declarations can create `works in venv, fails in wheel` drift. | Install behavior can differ between editable installs, lockfile installs, and package metadata installs. | Medium | Establish one authoritative dependency policy: either generate `pyproject` runtime deps from the lock source or narrow `pyproject` to the minimal publish-time contract and document the difference explicitly. |
| Architecture | Runtime state is explicitly process-local only. | This is fine for the current baseline, but it blocks any safe move to multi-instance deployments. | Rate limits, RAG cache, and warm state cannot be shared or coordinated. | Medium | Keep the current single-host contract, but define an interface layer for future shared state and add design notes for cache invalidation, distributed rate limiting, and rollout semantics. |
| Reliability / API client design | Upstream clients still return empty collections on many failures and require callers to inspect status trackers separately. | The failure taxonomy exists, but the public call contract remains partly lossy. | Callers can still confuse `no results` with `dependency degraded` unless they inspect side channels. | Medium | Introduce typed result envelopes or optional strict modes so higher-level code can distinguish absence from degraded upstream state without extra out-of-band calls. |
| Documentation / Onboarding | There is a large amount of active and archival documentation. | The repo is well documented, but not always easy to enter quickly. | New developers may spend significant time reconciling README, runbook, operator guides, ADRs, reviews, and archived passes. | Medium | Add one maintained architecture handoff doc that maps supported flows, generated artifact classes, and quarantine boundaries in one place. This report can seed that, but it should become a maintained doc, not a one-off artifact. |
| Production hardening | Clean-host proof is strong for the API wheel path but incomplete for the full surrounding deployment story, especially Fuseki provisioning and IIS front-door deployment. | The product relies on more than the wheel alone in real operation. | Production rollout still depends on partially manual or separately trusted operational steps. | High | Add reproducible clean-host validation for the full Windows baseline: Fuseki service provisioning, API install, health smoke, and one approved front-door deployment drill. |
| AI capability readiness | The local-adapter path is implemented but the current candidate evidence bundle is incomplete and failing. | This capability is visible in source and docs, but not ready for operational claims. | Any new developer could overestimate local-model maturity. | High | Keep it optional. Require passing release-evidence bundles before broader investment, and clearly separate `runtime exists` from `candidate is deployable`. |
| Quarantine complexity | `/v1/search` and KG expansion remain in-tree, partially wired, and partially documented for local validation. | Quarantined code increases cognitive load and maintenance burden. | More tests, docs, and gates must stay synchronized around non-baseline features. | Medium | Either continue strict quarantine with minimal maintenance surface, or remove unused paths until promotion work is resourced. |
| Workspace isolation | The current workspace relies on local environment specifics; `python` and `pytest` were not on `PATH` in this shell, while `.venv\Scripts\python.exe` worked. | Developer reproducibility depends on local environment assumptions. | Small but real friction for takeover, especially on Windows. | Low | Standardize command examples around `py -m ...` or provide a single bootstrap script that validates the shell environment and active interpreter. |

---

## 7. Missing Components

The following pieces are still missing if the goal is a production-ready system rather than a strong beta/pre-production baseline.

1. Hermetic release-workspace isolation.
   - The project needs a testable rule for which artifacts in `dist/` are authoritative for verification and which are disposable leftovers.
   - This should prevent mutable workspace drift from breaking release verification.

2. Full clean-host deployment proof for the complete supported stack.
   - The API wheel path is well covered.
   - Fresh-host Fuseki provisioning, rollback, and broader IIS front-door validation need equally repeatable evidence.

3. A validated production legal/regulatory answer model.
   - There is no benchmark-passing, promotion-ready local model artifact in the workspace.
   - If product direction includes local legal interpretation, that capability is still missing.

4. Enterprise-grade shared-state architecture for any scale-out ambitions.
   - The project is honest about this, but the component is still missing.
   - This would need shared rate limiting, distributed cache semantics, and deployment-aware rollout rules.

5. Stronger typed upstream failure propagation.
   - Status tracking exists, but callers still largely consume empty lists or dicts.
   - A production-grade integration layer should expose a clearer result model.

6. A single maintained architectural handoff document.
   - The repo has good partial docs, but no single always-current `system map` for new maintainers.
   - This report should evolve into that maintained document if the team wants faster onboarding.

7. Production deployment automation beyond release artifact generation.
   - CI builds, tests, scans, and releases artifacts.
   - There is not yet an end-to-end CD story for promoting and applying those artifacts to real environments.

8. Definitive cleanup automation for unsupported workspace leftovers.
   - The repo needs a simple cleanup script or policy for build caches, ghost dirs, and stale generated outputs so developers do not infer false capabilities.

9. If `legal interpretation AI` is a product requirement, a formal human-review layer is still missing.
   - The current system emphasizes evidence and refusal, which is appropriate.
   - It does not yet provide a promoted, validated human-in-the-loop adjudication workflow for high-stakes answer release.

---

## 8. Development Roadmap

### Phase A — Stabilization

| Task | Affected files / areas | Suggestion | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Isolate release verification from mutable `dist/` state | `scripts/verify-release.ps1`, `tests/release/test_verify_script.py`, `dist/` conventions | Make tests create and verify private artifact roots instead of using shared repo `dist/`. | Medium | P0 | None |
| Add workspace hygiene cleanup for ghost dirs and stale build outputs | `.gitignore`, cleanup scripts, docs, possibly `scripts/` | Create a `scripts/workspace-clean.ps1` or equivalent and document what is source vs generated. | Low | P0 | None |
| Resolve the current checksum drift in the workspace | `dist/checksums.sha256`, generated release artifacts | Either refresh checksums or remove stale release artifacts from the active workspace. | Low | P0 | None |
| Tighten developer bootstrap guidance | `README.md`, `RUNBOOK.md`, maybe `scripts/check_versions.py` | Make the supported local command path unambiguous: `py -m ...` or `.venv\Scripts\python.exe -m ...`. | Low | P1 | None |

### Phase B — Architecture Improvements

| Task | Affected files / areas | Suggestion | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Consolidate dependency truth model | `pyproject.toml`, `requirements.in`, lockfiles, docs | Remove ambiguity between editable install/runtime metadata and lock-based installs. | Medium | P1 | Phase A complete |
| Introduce typed upstream result envelopes | `api_clients/*`, direct callers, health/report surfaces | Preserve status tracking but add explicit typed results for degraded/empty/success states. | Medium | P1 | Phase A complete |
| Reduce quarantine maintenance burden | `service/api_server/routers/search.py`, KG expansion docs/tests, capability docs | Decide whether search/KG expansion stay in-tree with strict maintenance or move further out of the default contributor path. | Medium | P2 | None |
| Produce a maintained system map for new developers | `docs/` | Convert the best parts of this report into a stable architecture handoff doc. | Low | P1 | None |

### Phase C — Feature Completion

| Task | Affected files / areas | Suggestion | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Produce a benchmark-passing local-adapter candidate or formally deprioritize it | `scripts/training/*`, `scripts/eval/*`, `dist/training/*`, `docs/local_adapter_release_evidence.md` | Either achieve a reviewable candidate or narrow the roadmap so maintainers stop treating it as near-term. | High | P2 | Stable release/eval workflow |
| Decide the future of `/v1/search` and KG expansion | capability docs, optional-runtime smoke, operator docs | Keep quarantined with minimal maintenance, or invest in full promotion evidence. | High | P2 | Clean-host validation, operator proof |
| Improve typed temporal/legal reasoning evaluation | `eval/`, `earCrawler/eval/*`, `earCrawler/rag/temporal.py` | Add more targeted datasets for temporal correctness and answer abstention under ambiguous regulation states. | Medium | P2 | Existing eval manifest |

### Phase D — Production Hardening

| Task | Affected files / areas | Suggestion | Difficulty | Priority | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Add clean-host validation for the full Windows baseline including Fuseki | `scripts/ops/*`, `docs/ops/windows_*`, release workflows | Validate fresh-host provisioning, service install, restore, and rollback in the actual field shape. | High | P0 | Phase A complete |
| Add one reproducible IIS front-door deployment drill | `docs/ops/external_auth_front_door.md`, `scripts/ops/iis-earcrawler-front-door.web.config.example`, release evidence | Prove the approved broader-exposure pattern, not just document it. | Medium | P1 | Full clean-host baseline |
| Add deployment promotion automation and evidence retention rules | `.github/workflows/*`, release scripts, operator docs | Move from artifact creation to explicit environment promotion stages and retained evidence. | High | P1 | Clean-host validation |
| Define explicit shared-state roadmap before any scaling claims | `service/api_server/runtime_state.py`, design docs | Keep single-host support, but document the technical prerequisites for any future scale-out. | Medium | P2 | Architecture alignment |

---

## 9. Quick Wins

These are high-value improvements that should fit in less than one day each.

1. Clean `dist/` and refresh or regenerate release checksums so the full test suite returns to green.
2. Add a workspace cleanup script that removes cache-only unsupported directories and stale build intermediates.
3. Add a short `docs/maintainer_start_here.md` that points new developers to the exact supported source, generated, and quarantined surfaces.
4. Add a CI or pre-test check that refuses to run release-verification tests against drifted shared `dist/` artifacts.
5. Add a short dependency policy note explaining the relationship between `pyproject.toml`, `requirements.in`, and lockfiles.
6. Add a one-command local bootstrap verifier that confirms `py`, `.venv`, Java, and PowerShell prerequisites.
7. Add a note in `docs/model_training_surface_adr.md` explicitly warning that cache-only workspace directories may still exist locally even when tracked source is absent.

---

## 10. Long-Term Improvements

1. Move from a modular monolith with process-local state to a deployable shared-state design only if product scope truly requires multi-instance serving.
2. Promote or remove quarantined features deliberately; avoid indefinite `implemented but not really supported` middle states.
3. Replace partial local-model scaffolding with a real decision: either invest in benchmarked local serving or keep remote/provider-backed generation as the only answer path.
4. Add stronger provenance joins between corpus, KG, retrieval corpus, eval datasets, and release bundles so every answer path can be traced across artifacts more directly.
5. Introduce environment-level deployment automation and evidence archiving so release readiness is tied to real deploy steps, not only local artifact generation.
6. Simplify documentation by converging ADRs, review passes, and operator docs into a smaller number of authoritative maintained documents.

---

## 11. Final Assessment

### Current maturity level

Recommended label: `beta / pre-production hardening`.

Reasoning:

- The supported single-host baseline is thoughtfully engineered and heavily documented.
- The repo has strong tests, clear capability boundaries, and credible release evidence.
- The full workspace is still not stable enough to call production-ready because generated artifact drift and unsupported workspace leftovers remain active sources of confusion and one current test failure.
- Optional AI capability is still not validated enough to widen product claims.

### Major risks

1. Release-evidence drift in the live workspace undermines trust in packaging and verification.
2. Workspace leftovers can mislead maintainers about unsupported or removed capability.
3. Production deployment proof is stronger for the API wheel than for the complete surrounding Windows stack.
4. Optional AI/runtime features remain source-visible but operationally immature.
5. The architecture cannot safely claim multi-instance correctness.

### Estimated effort remaining

To reach a defensible production-ready baseline for the supported single-host shape:

- 2 to 4 weeks of focused hardening if scope stays narrow and excludes search/KG promotion and excludes local-model promotion.

To reach a broader `AI product` production posture including validated local models or promoted KG-backed runtime features:

- materially longer, likely 6 to 12+ weeks, because that work is not just cleanup; it requires new evidence, operator proof, and product decisions.

### Recommended next three development priorities

1. Restore workspace integrity by fixing release-artifact drift and making release verification hermetic against mutable `dist/` state.
2. Clean up unsupported ghost directories and generated leftovers so the workspace matches the documented support boundary.
3. Close the clean-host deployment proof gap for the entire supported Windows baseline, not only the API wheel path.

### Closing judgment

This is a strong engineering codebase with unusually good caution around claims, evidence, and regulatory answer quality. The current repository is good enough for a new developer to take over. The current workspace is not yet in a true production phase because it still mixes authoritative source with stale generated evidence and partially removed capability traces. Fixing that mismatch should be the immediate focus.

