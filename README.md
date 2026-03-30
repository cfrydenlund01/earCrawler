# earCrawler
[![CI](https://github.com/cfrydenlund01/earCrawler/actions/workflows/ci.yml/badge.svg)](https://github.com/cfrydenlund01/earCrawler/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/cfrydenlund01/earCrawler/branch/main/graph/badge.svg)](https://codecov.io/gh/cfrydenlund01/earCrawler)

earCrawler is the crawling and knowledge-graph component that powers the EAR-QA system. It provides light-weight clients for Trade.gov and the Federal Register, a deterministic ingestion pipeline, and a small FastAPI facade that fronts a local Apache Jena Fuseki deployment.

---

## Prerequisites

- Windows 11 with PowerShell 7 (`pwsh`) on `PATH`
- Python 3.11 or newer (`py --version`)
- Java 11+ JDK absolute minimum for local bootstrap checks; Java 17+ is required for the supported Fuseki auto-provision release/install path (`ensure_jena` auto-detects and sets `JAVA_HOME`)
- Git
- Trade.gov CSL API subscription key (required for live data pulls)
- Apache Jena Fuseki 4/5 (the CLI can auto-download it on Windows)
- GitHub CLI (`gh`) 2.x (needed for automated pull-request helpers)

Container runtimes are not part of the supported runtime or release flow at this point. The repo does not build or publish Docker or Apptainer artifacts; use the Windows CLI/service paths documented in this repo instead.

---

## Install the Tooling

For Windows operator deployment from signed release artifacts, use `docs/ops/windows_fuseki_operator.md` for the pinned read-only Fuseki dependency and `docs/ops/windows_single_host_operator.md` for the API wheel/service lifecycle. The clone/editable-install flow below is for source-checkout development and local validation.

> These instructions assume you are running commands from the repository root (the directory that contains `pyproject.toml`).

1. **Clone the repository**
   ```powershell
   git clone https://github.com/cfrydenlund01/earCrawler.git
   cd earCrawler
   ```

2. **(Recommended) create and activate a virtual environment**
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   When the prompt shows `(.venv)` you will be installing into the isolated environment. If you later see `Defaulting to user installation because normal site-packages is not writeable`, the environment is not active-re-run the `Activate.ps1` step.

   > Tip: Once the virtual environment is active, you can swap `py -m ...` for `python -m ...` to force the venv interpreter. The examples below continue to show the `py` launcher for brevity—use whichever matches your setup.

3. **Install Python dependencies**
   ```powershell
   python -m pip install --upgrade pip
   python -m pip install --requirement requirements.txt
   python -m pip install -e .
   ```
   This path keeps the dependencies and console scripts inside `.venv\Scripts\`. `requirements.in` is the single dependency source of truth; `requirements.txt` is a compatibility wrapper that points at it. If you prefer a global install, omit step 2 and use `py -m pip install --user --upgrade .`, then ensure the scripts directory shown in the warning messages is on `PATH`.
   Verify bootstrap prerequisites and dependency-policy consistency:
   ```powershell
   pwsh .\scripts\bootstrap-verify.ps1
   py .\scripts\verify-dependency-policy.py
   ```
   > Tip: Pip may leave a temporary folder (for example `~aml`) behind or warn that script shims such as `uvicorn.exe` are not on `PATH`. The folder can be deleted safely, and you can either add the scripts directory to `PATH` or continue using `python -m earCrawler.cli ...` to invoke commands.

   > **RAG extras (optional):** Base install intentionally excludes `sentence-transformers`, `torch`, `transformers`, and `peft`. Install these extras only when you need local embedding/indexing or the optional Task 5.4 local-adapter RAG path. They do not provide a supported model-training, fine-tuning, agent, or quantization stack.
   > ```powershell
   > python -m pip install --requirement requirements-gpu.txt
   > # or, equivalently:
   > python -m pip install -e .[gpu]
   > ```

4. **Hermetic/offline install (Windows)**
   Use this only when installing from a prebuilt wheelhouse bundle:
   ```powershell
   pwsh .\scripts\install-from-wheelhouse.ps1 -LockFile requirements-win-lock.txt
   python -m pip install -e . --no-deps
   ```

5. **Install GitHub CLI (required for PR automation)**
   ```powershell
   # winget (Windows 11 default)
   winget install --id GitHub.cli -e

   # or manually download the MSI/ZIP from https://cli.github.com/manual/installation
   ```
   After installation, verify the binary is on `PATH` and sign in once so the `pushCommitsAndLFS.ps1` helper can create pull requests:
   ```powershell
   gh --version
   gh auth login
   ```

---

## CLI Basics

The console script is installed as `earctl`, and the published wheel bundles the `perf` helpers plus the `service.api_server` package and its runtime assets. That means the documented `uvicorn service.api_server.server:app` entrypoint works from an installed wheel, not just from a checkout. When developing from a checkout you can also drive the commands with `python -m` to avoid PATH issues:

For deployed Windows hosts, the authoritative lifecycle guides are `docs/ops/windows_fuseki_operator.md` for the local read-only Fuseki service and `docs/ops/windows_single_host_operator.md` for the API wheel/service lifecycle. Use the signed wheel as the API deployment artifact. Do not treat the PyInstaller `earctl.exe`, the installer, or the repo-local `scripts/api-*.ps1` helpers as the authoritative API hosting path.
If a deployment must accept traffic beyond the trusted local host boundary, keep EarCrawler on loopback and add the reverse-proxy pattern in `docs/ops/external_auth_front_door.md`; the built-in static shared-secret model is not the approved internet-facing front door by itself.

```powershell
py -m earCrawler.cli --help
py -m earCrawler.cli diagnose
```

Supported entrypoints in this repo are:

- `earctl` / `py -m earCrawler.cli ...` for supported CLI workflows.
- KG workflows should use the grouped commands under `earctl kg ...` or `py -m earCrawler.cli kg ...`.
- `py -m uvicorn service.api_server.server:app --host 127.0.0.1 --port 9001` for direct FastAPI hosting and the wheel-based Windows service path.
- `py -m earCrawler.cli eval run-rag ...` for evaluation runs against datasets in `eval/`.

Quarantined or unsupported runtime surfaces in this repo are:

- `earCrawler.service.sparql_service`
- `earCrawler.service.legacy.kg_service`
- `earCrawler.ingestion.ingest` (legacy placeholder pipeline; explicitly gated)
- container runtimes and image-based deployments
- legacy training or research scaffolding; see `docs/model_training_surface_adr.md`
- top-level `cli/` wrappers such as `python -m cli.kg_validate`; these are deprecated compatibility shims that now point back to `earctl kg ...`

Use `service/api_server` and the CLI/operator paths above as the only supported runtime surface.

## Capability Matrix

Machine-readable capability state now lives in
`service/docs/capability_registry.json` and is published with the API contract
artifacts at `docs/api/capability_registry.json`. The table below is the
human-readable summary for the runtime and repo surfaces contributors ask about
most often.

| Surface | Status | Notes |
| --- | --- | --- |
| `earctl` / `py -m earCrawler.cli ...` and the documented Windows single-host service path | Supported | These are the supported operator entrypoints. Capability-level status still matters; use the rows below for feature-specific claims. |
| `service.api_server`, `/health`, `/v1/entities/{entity_id}`, `/v1/lineage/{entity_id}`, `/v1/sparql`, `/v1/rag/query` | Supported | These are the supported service/API surfaces for the Windows-first single-host runtime. Rate limits, concurrency limits, the RAG cache, retriever caches, and retriever warm state are process-local; multi-instance correctness is not claimed. |
| `/v1/rag/answer`, remote OpenAI-compatible providers, and retrieval extras installed from `requirements-gpu.txt` | Optional | Available only when explicitly enabled and configured. Generated output is advisory-only for production beta and must not be treated as an autonomous legal/regulatory determination. See `docs/answer_generation_posture.md`. |
| `EARCRAWLER_RETRIEVAL_MODE=hybrid` across `/v1/rag/query`, `/v1/rag/answer`, and eval flows | Optional | Off by default. Dense remains the baseline retrieval mode. Promotion/default-on criteria are tracked in `docs/capability_graduation_boundaries.md`. |
| The optional local adapter runtime (`LLM_PROVIDER=local_adapter`) | Optional | Implemented, but formally deprioritized for the current production-beta target. Requires explicit local-model env plus a recorded Task 5.3 adapter artifact. Validation path: `scripts/local_adapter_smoke.ps1`. See `docs/local_adapter_deprioritization_2026-03-25.md` and `docs/capability_graduation_boundaries.md`. |
| `/v1/search`, text-index-backed Fuseki search, `kg-load`, `kg-serve`, `kg-query`, and KG expansion | Quarantined | Implemented for local validation and research, but not part of the supported production contract until `docs/kg_quarantine_exit_gate.md` is passed and recorded. Current decision record: `docs/search_kg_capability_decision_2026-03-27.md` (Step 5.3: keep quarantined). Supporting history: `docs/kg_search_status_decision_2026-03-10.md` and `docs/search_kg_quarantine_decision_package_2026-03-19.md`. Capability-specific promotion boundaries live in `docs/capability_graduation_boundaries.md`. |
| `Research/`, `docs/proposal/`, benchmark planning, model-training/fine-tuning notes, and other future-work design docs | Proposal-only | Useful for planning and evaluation, not an operator/runtime commitment. Phase 5 records include base-model selection (`docs/model_training_surface_adr.md`, `config/training_model_selection.example.env`), training-input contract (`docs/model_training_contract.md`, `config/training_input_contract.example.json`), first-pass run tooling (`docs/model_training_first_pass.md`, `config/training_first_pass.example.json`, `scripts/training/*`), and the Phase 6 benchmark plan (`docs/production_candidate_benchmark_plan.md`). |

## Runtime vs Research Boundary

If you are new to the repo, use this rule first:

- `README.md`, `RUNBOOK.md`, `service/api_server`, `earctl`, and the code and scripts they directly rely on are the supported product/runtime surface.
- `Research/`, `docs/proposal/`, and design notes for gated or future work are not production commitments by themselves.
- If a feature is not described through a supported `earctl` or `service.api_server` path with tests and operator docs, treat it as research, experimental, or quarantined.
- Phase 5 training records keep `Qwen/Qwen2.5-7B-Instruct` as a planning-only future target and include Task 5.3 first-pass tooling in `docs/model_training_first_pass.md` and `scripts/training/`.
- The training-input contract for this model work is recorded in `docs/model_training_contract.md`; it uses approved eCFR snapshot text and the derived retrieval corpus, not eval fixtures or benchmark artifacts.
- Training scripts and artifacts are still a phase-gated workflow, not a supported operator runtime path by themselves.
- Task 5.4 adds a separate optional runtime path that can load a Task 5.3 adapter through `/v1/rag/answer` only when `LLM_PROVIDER=local_adapter`, `EARCRAWLER_ENABLE_LOCAL_LLM=1`, and the recorded adapter artifacts are present.
- The minimum release evidence bundle for a local-adapter candidate is defined in `docs/local_adapter_release_evidence.md` and `config/local_adapter_release_evidence.example.json`, but that track is formally deprioritized for the current production-beta target by `docs/local_adapter_deprioritization_2026-03-25.md`.
- Phase 6 benchmark planning is retained in `docs/production_candidate_benchmark_plan.md` as a future resumption plan, not active near-term release work.
- Capability-specific promotion and rollback boundaries for text search, hybrid ranking, KG expansion, and local-adapter serving are tracked in `docs/capability_graduation_boundaries.md`.

The repo-level boundary is documented in `docs/runtime_research_boundary.md`.
New maintainers should begin with `docs/maintainer_start_here.md`.
New contributors should begin with `docs/start_here_supported_paths.md`.
Use `docs/repository_status_index.md` for the top-level map of supported,
optional, quarantined, generated, and archival surfaces.
Use `docs/data_artifact_inventory.md` for the runtime/eval/training artifact
truth model.

## Single-Host Support Statement

The supported deployment contract is one Windows host running one EarCrawler API
service instance. Current rate limiting, concurrency controls, the RAG query
cache, retriever caches, and startup warmup state are process-local constructs.
Running multiple API instances behind a load balancer would therefore change
behavior immediately, and this repo does not claim that such a deployment is
correct today.

Future multi-instance design is deferred until the project has shared limit
state, cache semantics, rollout/rollback behavior, and tests that explicitly
cover scale-out behavior. See `docs/ops/multi_instance_deferred.md` and
`docs/single_host_runtime_state_boundary.md`.

The CLI enforces role-based access control defined in `security/policy.yml` for operational commands. Protected surfaces include `crawl`, `fetch-*`, `warm-cache`, `telemetry`, `kg-load`, `kg-serve`, `kg-query`, `eval`, API/admin helpers, and release/bundle workflows. Local helper commands such as `nsf-parse`, `kg-emit`, `kg-export`, `fr-fetch`, and `rag-index *` remain outside RBAC. For local testing you can opt into one of the built-in test identities:

```powershell
$env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES = '1'  # local test/dev only
$env:EARCTL_USER = 'test_operator'   # grants operator role
py -m earCrawler.cli policy whoami   # shows the identity and roles
```

By default, the CLI ignores `EARCTL_USER`/`EARCTL_POLICY_PATH` unless `EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES=1` is set. This keeps production runs bound to the logged-in OS identity.

Built-in identities and their permissions:

| Identity        | Role(s)      | Highlights                                                                          |
|-----------------|--------------|-------------------------------------------------------------------------------------|
| `test_reader`   | `reader`     | Read-only commands such as `diagnose`, `report`, and `kg-query`.                    |
| `test_operator` | `operator`   | Data movement and serving commands including `crawl`, `fetch-*`, `telemetry`, `jobs`, `kg-load`, `kg-serve`, and `eval`. |
| `test_maintainer` | `maintainer` | Release and operational workflows such as `reconcile`, `bundle`, `api`, `kg-load`, `kg-serve`, and `eval`. |
| `test_admin`    | `admin`      | Full access across the CLI, including `auth` and audit tooling.                    |

Run `py -m earCrawler.cli policy --help` to see these identities and the explicit local override instructions.

---

## Starting The API Facade

The FastAPI facade in `service/api_server` is the only supported service runtime in this repository. It wraps Fuseki with curated SPARQL templates and health checks. The steps below are for local source-checkout smoke and development. For deployed Windows hosts, provision Fuseki with `docs/ops/windows_fuseki_operator.md` and manage the API with `docs/ops/windows_single_host_operator.md`.

```powershell
# 1. ensure you have operator rights
$env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES = '1'  # local test/dev only
$env:EARCTL_USER = 'test_operator'

# 2. start the facade (spawns uvicorn in the background)
py -m earCrawler.cli api start

# 3. check health
Invoke-WebRequest http://127.0.0.1:9001/health -UseBasicParsing

# 4. run the smoke test bundle (writes reports to kg/reports/api-smoke.json and kg/reports/api-smoke.txt)
py -m earCrawler.cli api smoke

# 5. stop the facade
py -m earCrawler.cli api stop
```

If you do not need the PowerShell wrapper, you can launch the same ASGI app
directly:

```powershell
py -m uvicorn service.api_server.server:app --host 127.0.0.1 --port 9001
```

PID files are written to `kg/reports/api.pid`. If the stop command warns that it cannot find the process, the server has already exited; remove the stale PID file before the next start.

Legacy / Future work: `earCrawler.service.sparql_service` and `earCrawler.service.legacy.kg_service` are quarantined and are not supported entrypoints in this repo. Use `service/api_server/` and the `earctl api ...` commands as the only runtime service surface.

Environment variables:

- `EARCRAWLER_API_HOST` and `EARCRAWLER_API_PORT` control bind address and port.
- `EARCRAWLER_FUSEKI_URL` points the facade at the Fuseki SPARQL query endpoint, for example `http://localhost:3030/ear/query`.
- `EARCRAWLER_API_ENABLE_SEARCH=1` enables quarantined `/v1/search` for local validation; default is `0` (disabled).
- `EARCTL_PYTHON` overrides the interpreter used by the PowerShell wrappers.

---

## RAG / Optional LLM Answering

Status: `Optional`. This path requires explicit environment enablement and,
depending on the mode, either provider credentials or a recorded local adapter
artifact; it is not part of the default baseline runtime.

Production-beta posture: generated output from `/v1/rag/answer` is a
citation-grounded advisory draft, not a supported autonomous legal or
regulatory decision. Use `docs/answer_generation_posture.md` for the current
abstention rules, human-review boundary, and evidence threshold for any future
promotion claim.

The API can generate answers using:

- remote OpenAI-compatible providers (Groq or NVIDIA NIM)
- a local Task 5.3 adapter runtime loaded from `dist/training/<run_id>/adapter`

Remote calls are gated by `EARCRAWLER_ENABLE_REMOTE_LLM=1` and provider API keys loaded from your environment, Windows Credential Store, or an optional local-only `config/llm_secrets.env` (copy from `config/llm_secrets.example.env` and do not commit it).

```powershell
$env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES = '1'  # local test/dev only
$env:EARCTL_USER = 'test_operator'
$env:EARCRAWLER_API_ENABLE_RAG = '1'
$env:EARCRAWLER_ENABLE_REMOTE_LLM = '1'
# Provide keys via env or Windows Credential Store (recommended), or via config/llm_secrets.env
py -m earCrawler.cli api start
```

For the local adapter path, point the runtime at a completed Task 5.3 artifact
and keep the same evidence/schema guardrails:

Current scope note: this path is implemented but formally deprioritized for the
current production-beta target. Do not treat it as part of the normal release
or deployed-host baseline. See `docs/local_adapter_deprioritization_2026-03-25.md`.

```powershell
$env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES = '1'  # local test/dev only
$env:EARCTL_USER = 'test_operator'
$env:EARCRAWLER_API_ENABLE_RAG = '1'
$env:LLM_PROVIDER = 'local_adapter'
$env:EARCRAWLER_ENABLE_LOCAL_LLM = '1'
$env:EARCRAWLER_LOCAL_LLM_BASE_MODEL = 'Qwen/Qwen2.5-7B-Instruct'
$env:EARCRAWLER_LOCAL_LLM_ADAPTER_DIR = 'dist/training/<run_id>/adapter'
$env:EARCRAWLER_LOCAL_LLM_MODEL_ID = '<run_id>'
py -m earCrawler.cli api start
```

Then run the operator smoke helper against the same run artifact:

```powershell
pwsh .\scripts\local_adapter_smoke.ps1 -RunDir dist/training/<run_id>
```

Validate the minimum release evidence bundle for that same candidate:

```powershell
py -m scripts.eval.validate_local_adapter_release_bundle `
  --run-dir dist/training/<run_id> `
  --benchmark-summary dist/benchmarks/<benchmark_run_id>/benchmark_summary.json `
  --smoke-report kg/reports/local-adapter-smoke.json
```

Call the generated-answer endpoint:

```powershell
Invoke-WebRequest `
  -Uri http://127.0.0.1:9001/v1/rag/answer `
  -Method Post `
  -Headers @{'Content-Type'='application/json'} `
  -Body (@{ query = 'Do laptops to France need a license?'; top_k = 3 } | ConvertTo-Json) |
  Select-Object -ExpandProperty Content
```

The response includes `question`, `answer`, `contexts` (the passages passed to
the LLM), `retrieved` (document metadata), `provider`, `model`, and flags
`rag_enabled` / `llm_enabled` indicating whether the stack is active. Local
adapter runs continue to use the same refusal policy, strict JSON schema
validation, and citation grounding checks as remote runs.

Higher-risk interpretations still require human review before operational use,
including concrete license determinations, License Exception conclusions, and
time-sensitive applicability questions. If retrieval is thin, ambiguous, or
temporally inconsistent, the safe behavior is to return `unanswerable` rather
than guess.

Retrieval mode selection is controlled by `EARCRAWLER_RETRIEVAL_MODE`:

- `dense`: existing dense retrieval only; this remains the default.
- `hybrid`: optional BM25+dense fusion using reciprocal rank fusion over the existing retrieval metadata. Dense remains the baseline. Promotion/default-on criteria are tracked in `docs/capability_graduation_boundaries.md`.

Dense backend selection is still controlled by `EARCRAWLER_RETRIEVAL_BACKEND`:

- `bruteforce`: deterministic cosine search over the metadata corpus embeddings; this is the default on Windows because the project does not package `faiss-cpu` on `win32`.
- `faiss`: uses the existing FAISS index; on Windows the retriever forces FAISS to one thread and applies a stable tie-break on equal-score hits.

Windows retrieval smoke:

```powershell
.\scripts\retrieval_smoke.ps1
```

---

## RAG + Remote LLM Evaluation

You can score the existing eval datasets (`eval/*.jsonl`) through the RAG pipeline using remote providers (Groq or NVIDIA NIM). Remote calls are gated by `EARCRAWLER_ENABLE_REMOTE_LLM=1` and provider API keys in `config/llm_secrets.env` or your environment. The defaults come from `earCrawler/config/llm_secrets.py` and remain provider-agnostic/configurable via environment overrides if a default remote model changes.

Examples:

```powershell
$env:EARCRAWLER_ENABLE_REMOTE_LLM = '1'
# Override model if needed (Groq example)
# $env:GROQ_MODEL = 'llama-3.1-8b-instant'

py -m eval.validate_datasets
python scripts/eval/eval_rag_llm.py --dataset-id ear_compliance.v1 --llm-provider groq --llm-model llama-3.1-8b-instant
python scripts/eval/eval_rag_llm.py --dataset-id entity_obligations.v1 --llm-provider nvidia_nim
python scripts/eval/eval_rag_llm.py --dataset-id unanswerable.v1 --llm-provider groq --max-items 2
python scripts/eval/eval_rag_llm.py --dataset-id ear_compliance.v1 --retrieval-mode hybrid
python scripts/eval/eval_rag_llm.py --dataset-id multihop_slice.v1 --retrieval-compare
```

Outputs land under `dist/eval/` with filenames like `<dataset>.rag.<provider>.<model>.json`/`.md`. Metrics include accuracy, label accuracy, unanswerable accuracy, grounded_rate (section overlap), by-task breakdowns, provider/model metadata, and per-item records (with any LLM errors captured without stopping the run).
Artifacts also include an `eval_strictness` section with fallback counters and threshold status (`fallbacks_used`, `fallback_counts`, `fallback_items`, `fallback_max_uses`, `fallback_threshold_breached`).

---

## Preparing Fuseki & The Knowledge Graph

Status: `Quarantined`. The commands below exist for local validation and
quarantine work, but they are not part of the supported production contract
until `docs/kg_quarantine_exit_gate.md` is passed and recorded.

1. **Ensure Jena is available**  
   The first CLI call that needs Jena will download it into `tools/jena` and populate the `JENA_HOME`/`JAVA_HOME` environment variables if they are not already set. If Java cannot be located automatically, install JDK 11+ and set `JAVA_HOME` before retrying (use JDK 17+ for the supported Fuseki auto-provision release/install path). You can pre-flight the download:
   ```powershell
   py -m earCrawler.cli kg-serve --dry-run
   ```
   `kg-load` and `kg-serve` require the `operator` or `maintainer` role; `kg-query` is available to `reader` and above.

2. **Serve a local dataset**  
   The command below hosts the embedded TDB2 database from `.\db` at `http://localhost:3030/ear`:
   ```powershell
   py -m earCrawler.cli kg-serve --db db --dataset /ear
   ```
   This command runs until you stop it (CTRL+C). Open a second PowerShell window for follow-on steps, or add `--no-wait` to detach the Fuseki process and regain the prompt:
   ```powershell
   py -m earCrawler.cli kg-serve --db db --dataset /ear --no-wait
   ```
   (PowerShell does not support the POSIX `&` background operator—either use `--no-wait`, `Start-Job`, or keep Fuseki in its own terminal.)
   Use `Ctrl+C` to stop the server.

3. **Load triples into TDB2**  
   Export or craft a Turtle file (`kg/ear_triples.ttl`) and load it:
   ```powershell
   py -m earCrawler.cli kg-load --ttl kg\ear_triples.ttl --db db
   ```
   The loader bootstraps Jena when necessary and records artifacts under `kg/reports/`.

4. **Querying**  
   ```powershell
   py -m earCrawler.cli kg-query --sparql "SELECT * WHERE { ?s ?p ?o } LIMIT 5"
   ```

> **Note:** The SPARQL templates in `earCrawler/sparql/` include the required prefixes, so they can be sent to Fuseki without additional preprocessing.

---

## Loading Demo Data

1. **Store your Trade.gov credentials**  
   ```powershell
   py -c "import keyring; keyring.set_password('EAR_AI', 'TRADEGOV_API_KEY', '<YOUR KEY HERE>')"
   py -c "import keyring; keyring.set_password('EAR_AI', 'TRADEGOV_USER_AGENT', 'ear-ai/0.2.5')"
   ```
   You can also set `TRADEGOV_API_KEY` / `TRADEGOV_USER_AGENT` as environment variables.

2. **Fetch CSL entities and load into Fuseki**
   ```powershell
   py -c "from earCrawler.loaders.csl_loader import load_csl_by_query; from earCrawler.kg.jena_client import JenaClient; client = JenaClient(); count = load_csl_by_query('Huawei', limit=5, jena=client); print('Loaded', count, 'entities')"
   ```
   If you see `SPARQL UPDATE failed: 400`, double-check that the prefix block at the top of `earCrawler/sparql/upsert_entity.sparql` is intact.

3. **Seed EAR parts from the Federal Register**
   ```powershell
   py -c "from earCrawler.loaders.ear_parts_loader import load_parts_from_fr; from earCrawler.kg.jena_client import JenaClient; client = JenaClient(); count = load_parts_from_fr('Export Administration Regulations', jena=client, pages=1, per_page=10); print('Loaded', count, 'parts')"
   ```

4. **Link demo entities to parts**
   ```powershell
   py -c "from earCrawler.loaders.ear_parts_loader import link_entities_to_parts_by_name_contains; from earCrawler.kg.jena_client import JenaClient; client = JenaClient(); links = link_entities_to_parts_by_name_contains(client, 'Huawei', ['744']); print('Created', links, 'links')"
   ```

5. **Verify the Trade.gov gateway**
   ```powershell
   py -c "import requests, keyring; key = keyring.get_password('EAR_AI','TRADEGOV_API_KEY'); headers={'subscription-key': key, 'Accept': 'application/json', 'User-Agent': 'ear-ai/0.2.5'}; resp=requests.get('https://data.trade.gov/consolidated_screening_list/v1/search', params={'name':'Huawei','size':'1'}, headers=headers, timeout=30, allow_redirects=False); print(resp.status_code, resp.headers.get('Content-Type','')); print(resp.text[:120])"
   ```
   A `401` indicates the subscription key is invalid. A `301` redirect usually means the header was missing.

---

## Observability & Health

- API smoke, health, and watchdog artefacts land in `kg/reports/`.
- Health probes live under `scripts/health/` and produce `kg/reports/health-*.txt`.
- Canary automation uses `canary/config.yml` plus `scripts/canary/run-canaries.ps1`; default API checks stay on supported routes, and quarantined `/v1/search` checks are local-validation only.
- Telemetry policy and redaction rules are stored in `docs/privacy/`.
- Scheduler jobs and admin helpers persist structured run logs in `run/logs/`. Each JSON file contains a `run_id`, status, timestamps, and per-step metadata so operators can audit Windows Task Scheduler executions.
- The Trade.gov and Federal Register clients honour `TRADEGOV_MAX_CALLS` and `FR_MAX_CALLS` environment budgets. Requests use exponential backoff with structured retry logs, and the on-disk cache key now incorporates Accept/User-Agent headers to avoid stale mixes across CLI environments.

## Proposal Assets

Status: `Proposal-only`. These materials can inform future work but do not
change the supported runtime contract by themselves.
- `scripts/demo-end-to-end.ps1` produces a deterministic crawl -> KG -> bundle run with fixtures and emits a summary artefact. The script uses the active `python` interpreter by default; override with `-Python` to call a specific executable.
- `scripts/build-release.ps1` orchestrates wheel/EXE/installer builds and writes SHA-256 checksums for signing.
- `docs/proposal/architecture.md`, `docs/proposal/security.md`, and `docs/proposal/observability.md` capture the architecture story, security posture, and SLO model pitched in the proposal.
- `api_clients.EarCrawlerApiClient` is a typed helper for downstream consumers of the FastAPI facade.

The `docs/proposal/` set is proposal material, not an operator contract. Treat `README.md`, `RUNBOOK.md`, and `docs/runtime_research_boundary.md` as the source of truth for supported runtime commitments.

---

## Evaluation & Benchmarks

earCrawler ships a lightweight evaluation harness for Phase E experiments and regression checks.

### Evaluation Contract

The eval pipeline is contract-first: datasets are versioned, schema-validated, tied to a specific KG snapshot, and expected to produce reproducible artifacts.

- Dataset schema: [`eval/schema.json`](eval/schema.json)
- Dataset manifest and curated references: [`eval/manifest.json`](eval/manifest.json)
- Dataset validator entrypoints:
  ```powershell
  py -m eval.validate_datasets
  python eval/validate_datasets.py
  ```

Primary eval outputs are written under `dist/eval/` and typically include:

- `<dataset>.<run-type>.json` with aggregate metrics, metadata, and per-item records
- `<dataset>.<run-type>.md` with a short human-readable summary

Validation checks more than JSON shape. The manifest pins:

- dataset ids, files, versions, and item counts
- the expected KG snapshot via `kg_state.manifest_path` and `kg_state.digest`
- curated `references.sections`, `references.kg_nodes`, and `references.kg_paths` that dataset items are allowed to cite

For groundedness, evals go beyond citation presence. The split metrics in [`earCrawler/eval/groundedness_gates.py`](earCrawler/eval/groundedness_gates.py) separately track:

- `valid_citation_rate`: are cited section ids and quoted spans structurally valid and present in the allowed references/context?
- `supported_rate`: do the answer's decisive claims actually map to supported cited evidence?
- `overclaim_rate`: does the answer make unsupported claims even when some citations are present?

This means a response can cite something and still fail groundedness if the quote is invalid, the claim is not actually supported, or the answer overreaches beyond the cited evidence.

### Datasets

- Evaluation items live under `eval/` as JSONL files (one JSON object per line) and are indexed by `eval/manifest.json`.
- The manifest ties datasets to a specific KG snapshot **and** the curated references they rely on:
  - `kg_state.manifest_path` and `kg_state.digest` point at `kg/.kgstate/manifest.json` and its hash.
  - `datasets[]` records entries such as `ear_compliance.v1`, `entity_obligations.v1`, and `unanswerable.v1` with `task`, `file`, `version`, `description`, and `num_items`.
  - `references.sections`, `references.kg_nodes`, and `references.kg_paths` enumerate the EAR sections and KG nodes/paths used in the eval slices. `python eval/validate_datasets.py` verifies that every dataset item references only these curated entries in addition to passing the JSON schema.
- Per-item schema (shared across all datasets):
  - `id` – stable item identifier.
  - `task` – logical task (`ear_compliance`, `entity_obligation`, `unanswerable`, etc.).
  - `question` – user-facing question text.
  - `ground_truth` – object with:
    - `answer_text` – canonical short answer.
    - `label` – normalized label for scoring (for example `license_required`, `permitted_with_license`, `prohibited`, `unanswerable`).
  - `ear_sections` – EAR section IDs relevant to the answer (for example `["EAR-744.6(b)(3)"]`).
  - `kg_entities` – IRIs of the main KG entities involved, or empty for statute-only questions.
  - `evidence` – object with:
    - `doc_spans` – list of `{ "doc_id": "<EAR document ID>", "span_id": "<section/paragraph ID>" }` entries.
    - `kg_nodes` – IRIs of policy-graph nodes (obligations/exceptions) that encode the decision logic.
    - `kg_paths` (optional) – identifiers for precomputed reasoning paths used in explainability and KG-walk evaluations.

To add a new dataset:

1. Create `eval/<name>.vX.jsonl` following the schema above, using one JSON object per line.
2. Append a new entry to `eval/manifest.json` with:
   - `id` (for example `my_task.v1`),
   - `task` (for example `my_task`),
   - `file` (`eval/<name>.vX.jsonl`),
   - `version` (integer),
   - `description` and `num_items`.
3. Update `references.sections`, `references.kg_nodes`, and `references.kg_paths` if your dataset introduces new EAR sections or policy nodes so that referential validation succeeds.
4. If the dataset assumes a different KG snapshot, run `py -m earCrawler.utils.kg_state` (or the appropriate helper) to refresh `kg/.kgstate/manifest.json`, then update `kg_state.digest` in `eval/manifest.json` intentionally.

### Running evals via CLI

The CLI exposes a convenience command that runs the RAG pipeline against datasets using a remote LLM provider:

```powershell
$env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES = '1'  # local test/dev only
$env:EARCTL_USER = 'test_operator'  # requires operator or maintainer role
$env:EARCRAWLER_ENABLE_REMOTE_LLM = '1'
py -m eval.validate_datasets
py -m earCrawler.cli eval run-rag --dataset-id ear_compliance.v1 --max-items 5 --fallback-max-uses 0
```

By default this:

- Resolves `ear_compliance.v1` from `eval/manifest.json`,
- Loads the dataset JSONL and runs retrieval + generation,
- Writes metrics + metadata to `dist\eval\ear_compliance.v1.rag.<provider>.<model>.json`,
- Writes a short Markdown summary to `dist\eval\ear_compliance.v1.rag.<provider>.<model>.md`.

Other useful options:

- `--top-k` – number of contexts to retrieve before generation.
- `--max-items` – cap the number of items for a quick smoke run.
- `--answer-score-mode` – `semantic` (default), `normalized`, or `exact`.

To log the results in `Research/decision_log.md`, run `python scripts/eval/log_eval_summary.py dist/eval/*.json` to emit a markdown-ready set of bullet points for all benchmark outputs in one go. This helper accepts one or many metrics files, making it easy to paste consolidated summaries into the research log. The `Research/` folder is for notes and proposal artifacts, not for a supported model-training runtime.

These outputs are suitable for CI artefacts and for logging Phase E endpoints in `Research/decision_log.md`.

---

## Useful CLI Commands

| Command | What it does |
| --- | --- |
| `py -m earCrawler.cli diagnose` | Prints Python/platform/build info and telemetry status. |
| `py -m earCrawler.cli crawl --sources ear nsf` | Loads multiple corpora to `data/`. |
| `py -m earCrawler.cli report --sources ear --type term-frequency --n 10` | Generates analytics summaries. |
| `py -m earCrawler.cli warm-cache` | Primes the Trade.gov cache. |
| `py -m earCrawler.cli telemetry enable` | Enables local telemetry spooling. |
| `py -m earCrawler.cli perf ...` | Synthetic dataset generation and latency gates (requires the `perf/` fixtures on disk). |
| `py -m earCrawler.cli llm ask --llm-provider groq "What does EAR regulate?"` | Run a RAG-backed LLM query (requires `EARCRAWLER_ENABLE_REMOTE_LLM=1` and provider keys). |

## Optional LLM Providers (NVIDIA NIM, Groq)

- Create `config/llm_secrets.env` from `config/llm_secrets.example.env` and fill in provider keys/models. The file is git-ignored and only supplements the usual env/Windows Credential Store secrets.
- Enable remote calls explicitly: `set EARCRAWLER_ENABLE_REMOTE_LLM=1` (default is disabled for CI/offline safety).
- Choose provider/model per call via CLI (defaults come from `earCrawler/config/llm_secrets.py` and can be overridden via environment or `config/llm_secrets.env`):
  - `py -m earCrawler.cli llm ask --llm-provider groq --llm-model <provider-model-id> "Can ACME export laptops to France?"`
  - `py -m earCrawler.cli llm ask --llm-provider nvidia_nim --llm-model <nim-model-id> "Are Huawei exports restricted under EAR?"`
- Requests use OpenAI-style `/chat/completions` endpoints with soft call budgets (configure with `LLM_MAX_CALLS` or `LLM_<PROVIDER>_MAX_CALLS`).

Run `py -m earCrawler.cli COMMAND --help` for detailed options.

---

## Baseline run (Phase 0)

Run the replayable baseline helper from the repo root:

```powershell
pwsh .\scripts\baseline.ps1
```

It creates a new timestamped artifact directory at `runs\<YYYYMMDD_HHMMSS>\` and writes `pytest.txt`, `python_version.txt`, and `env_freeze.txt` there. The script also creates a matching baseline branch (`baseline/<timestamp>`) and tag (`baseline-<timestamp>`) for the exact `HEAD` commit used by the run, adding a suffix such as `_01` if the branch/tag name already exists. To find the recorded commit later, run `git rev-list -n 1 baseline-<timestamp>` or inspect the tag with `git show baseline-<timestamp>`.

- Run `pwsh .\scripts\env_snapshot.ps1` to capture a replay-friendly environment snapshot in the latest `runs\<timestamp>\env_snapshot.json`; it reuses existing `python_version.txt` / `env_freeze.txt` when present and redacts secret-like environment variables.

## Troubleshooting

- **`earctl` is not recognized**  
  Add the user `Scripts` directory to `PATH` or run the CLI with `py -m earCrawler.cli`.

- **`command 'api' requires role(s): operator, maintainer`**  
  For local test identity use, set `EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES=1` and then `EARCTL_USER=test_operator` (or configure your OS identity/roles in `security/policy.yml`).

- **`ModuleNotFoundError: No module named 'perf'` when starting the CLI**  
  Upgrade to the latest wheel (which bundles `perf`) or run `py -m earCrawler.cli ...` from the repository root when working from source.

- **`SPARQL UPDATE failed: 400`**  
  Ensure the SPARQL file you are submitting still contains the prefix block at the top; Fuseki returns 400 when the prefixes are missing.

- **Trade.gov returns `401` or a redirect**  
  Confirm the CSL subscription key is active and stored via `keyring` (or environment variables). The header name must be `subscription-key`.

- **PowerShell cannot find `pwsh` inside scripts**  
  Set `EARCTL_POWERSHELL` to the path of `pwsh.exe` or fall back to Windows PowerShell.

---

## Project Layout

- `earCrawler/` - Python package (loaders, KG helpers, API facade).
- `api_clients/` - HTTP clients for Trade.gov and Federal Register.
- `cli/` - Legacy CLI helpers kept for backwards compatibility.
- `kg/` - Ontology, assembler configs, scripts, and reports.
- `scripts/` - PowerShell orchestration for API, health checks, and CI automation.
- `perf/` - Synthetic dataset generators and regression gates (requires local checkout).
- `service/` - FastAPI application surface (`service/api_server/server.py`) plus OpenAPI spec.

---

## Contributing & License

Pull requests are welcome - open an issue first for substantial changes so we can align on scope. The project is licensed under the MIT License (`LICENSE` in the repository root).

## Schema and SHACL

- Defines the `ear:` schema for Entities and Parts.
- Enforces shapes with `pyshacl` in CI on `windows-latest`.
- Local run:
  ```powershell
  python -m earCrawler.validation.validate_shapes
  ```

Keep using the Trade.gov Data API for entity lookup and the Federal Register API for EAR text via the packaged clients. Ensure transforms (`csl_to_rdf.py`, `ear_fr_to_rdf.py`) emit IRIs under `ent:` and `part:` to satisfy shapes. Store secrets in the Windows Credential Store or a vault—never hardcode them.

## Synthetic Sample TTL Build and Gated Load (Quarantined)

- This flow builds a synthetic demo fixture at `dist/bundle.ttl`.
- A validation gate must pass before any load.
- It is not the supported production corpus -> KG validation path.
- Local load (Windows PowerShell):
  ```powershell
  $env:EAR_FUSEKI_DATASET="http://localhost:3030/ear"
  $env:EAR_ENABLE_LOAD="1"
  python -m earCrawler.pipelines.build_sample_fixture_ttl
  python -m earCrawler.pipelines.load_after_validate
  ```

## Supported CI Evidence Path

- `ci.yml` validates the supported offline evidence path in this order:
  corpus build -> corpus validate -> kg-emit -> SHACL gate -> supported API smoke -> no-network RAG smoke.
- The API smoke gate covers only supported routes: `/health`, `/v1/entities/{entity_id}`, `/v1/lineage/{entity_id}`, and `/v1/sparql`.
- The no-network RAG smoke gate runs `tests/golden/test_phase2_golden_gate.py` with stubbed retrieval and stubbed LLM outputs; it does not depend on provider keys, FAISS, or live network access.
