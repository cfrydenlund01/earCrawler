# earCrawler
[![CI](https://github.com/cfrydenlund01/earCrawler/actions/workflows/ci.yml/badge.svg)](https://github.com/cfrydenlund01/earCrawler/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/cfrydenlund01/earCrawler/branch/main/graph/badge.svg)](https://codecov.io/gh/cfrydenlund01/earCrawler)

earCrawler is the crawling and knowledge-graph component that powers the EAR-QA system. It provides light-weight clients for Trade.gov and the Federal Register, a deterministic ingestion pipeline, and a small FastAPI facade that fronts a local Apache Jena Fuseki deployment.

---

## Prerequisites

- Windows 11 with PowerShell 7 (`pwsh`) on `PATH`
- Python 3.11 or newer (`py --version`)
- Java 11+ JDK (required for Apache Jena; `ensure_jena` auto-detects and sets `JAVA_HOME`)
- Git
- Docker Desktop (needed for optional container packaging)
- Trade.gov CSL API subscription key (required for live data pulls)
- Apache Jena Fuseki 4/5 (the CLI can auto-download it on Windows)
- GitHub CLI (`gh`) 2.x (needed for automated pull-request helpers)

---

## Install the Tooling

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
   This path keeps the dependencies and console scripts inside `.venv\Scripts\`. If you prefer a global install, omit step 2 and use `py -m pip install --user --upgrade .`, then ensure the scripts directory shown in the warning messages is on `PATH`.
   > Tip: Pip may leave a temporary folder (for example `~aml`) behind or warn that script shims such as `uvicorn.exe` are not on `PATH`. The folder can be deleted safely, and you can either add the scripts directory to `PATH` or continue using `python -m earCrawler.cli ...` to invoke commands.

   > **RAG extras:** The retrieval stack (SentenceTransformers/FAISS) is optional; install it only when you need RAG indexing/querying. This project no longer relies on a local Mistral model for generation.
   > ```powershell
   > python -m pip install -e .[gpu]
   > # or use pip install -r requirements-gpu.txt on Linux runners
   > ```

4. **Install GitHub CLI (required for PR automation)**
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

The console script is installed as `earctl`, and the published wheel bundles the `perf` helpers that the CLI imports. When developing from a checkout you can also drive the commands with `python -m` to avoid PATH issues:

```powershell
py -m earCrawler.cli --help
py -m earCrawler.cli diagnose
```

The CLI enforces role-based access control defined in `security/policy.yml`. Most high-value commands require the `operator` or `maintainer` role. For local testing you can opt into one of the built-in test identities:

```powershell
$env:EARCTL_USER = 'test_operator'   # grants operator role
py -m earCrawler.cli policy whoami   # shows the identity and roles
```

Unset `EARCTL_USER` to fall back to the logged-in Windows account (default role: `reader`).

Built-in identities and their permissions:

| Identity        | Role(s)      | Highlights                                                                          |
|-----------------|--------------|-------------------------------------------------------------------------------------|
| `test_reader`   | `reader`     | Read-only commands such as `diagnose`, `report`, and knowledge-graph queries.      |
| `test_operator` | `operator`   | Data movement commands including `crawl`, `fetch-*`, `bundle`, `jobs`, and `gc`.   |
| `test_maintainer` | `maintainer` | Release workflows such as `reconcile`, `bundle`, and API management.             |
| `test_admin`    | `admin`      | Full access across the CLI, including `auth` and audit tooling.                    |

Run `py -m earCrawler.cli policy --help` to see these identities inside the CLI along with tips for setting `EARCTL_USER`.

---

## Starting The API Facade

The FastAPI facade wraps Fuseki with curated SPARQL templates and health checks. The PowerShell helper scripts under `scripts/` handle process management and PID files.

```powershell
# 1. ensure you have operator rights
$env:EARCTL_USER = 'test_operator'

# 2. start the facade (spawns uvicorn in the background)
py -m earCrawler.cli api start

# 3. check health
Invoke-WebRequest http://127.0.0.1:9001/health -UseBasicParsing

# 4. run the smoke test bundle (writes reports to kg/reports/api-smoke.txt)
py -m earCrawler.cli api smoke

# 5. stop the facade
py -m earCrawler.cli api stop
```

PID files are written to `kg/reports/api.pid`. If the stop command warns that it cannot find the process, the server has already exited; remove the stale PID file before the next start.

Environment variables:

- `EARCRAWLER_API_HOST` and `EARCRAWLER_API_PORT` control bind address and port.
- `EARCRAWLER_FUSEKI_URL` points the facade at a remote Fuseki instance (defaults to `http://localhost:3030/ear`).
- `EARCTL_PYTHON` overrides the interpreter used by the PowerShell wrappers.

---

## RAG / Remote LLM Answering

The API can generate answers using remote OpenAI-compatible providers (Groq or NVIDIA NIM). Remote calls are gated by `EARCRAWLER_ENABLE_REMOTE_LLM=1` and provider API keys loaded from your environment, Windows Credential Store, or an optional local-only `config/llm_secrets.env` (copy from `config/llm_secrets.example.env` and do not commit it).

```powershell
$env:EARCTL_USER = 'test_operator'
$env:EARCRAWLER_API_ENABLE_RAG = '1'
$env:EARCRAWLER_ENABLE_REMOTE_LLM = '1'
# Provide keys via env or Windows Credential Store (recommended), or via config/llm_secrets.env
py -m earCrawler.cli api start
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

The response includes `question`, `answer`, `contexts` (the passages passed to the LLM), `retrieved` (document metadata), `provider`, `model`, and flags `rag_enabled` / `llm_enabled` indicating whether the stack is active.

---

## RAG + Remote LLM Evaluation

You can score the existing eval datasets (`eval/*.jsonl`) through the RAG pipeline using remote providers (Groq or NVIDIA NIM). Remote calls are gated by `EARCRAWLER_ENABLE_REMOTE_LLM=1` and provider API keys in `config/llm_secrets.env` or your environment. The defaults come from `earCrawler/config/llm_secrets.py`, but you can override them if a model is decommissioned (e.g., Groq `mixtral-8x7b-32768`).

Examples:

```powershell
$env:EARCRAWLER_ENABLE_REMOTE_LLM = '1'
# Override model if needed (Groq example)
# $env:GROQ_MODEL = 'llama-3.1-8b-instant'

python scripts/eval/eval_rag_llm.py --dataset-id ear_compliance.v1 --llm-provider groq --llm-model llama-3.1-8b-instant
python scripts/eval/eval_rag_llm.py --dataset-id entity_obligations.v1 --llm-provider nvidia_nim
python scripts/eval/eval_rag_llm.py --dataset-id unanswerable.v1 --llm-provider groq --max-items 2
```

Outputs land under `dist/eval/` with filenames like `<dataset>.rag.<provider>.<model>.json`/`.md`. Metrics include accuracy, label accuracy, unanswerable accuracy, grounded_rate (section overlap), by-task breakdowns, provider/model metadata, and per-item records (with any LLM errors captured without stopping the run).

---

## Preparing Fuseki & The Knowledge Graph

1. **Ensure Jena is available**  
   The first CLI call that needs Jena will download it into `tools/jena` and populate the `JENA_HOME`/`JAVA_HOME` environment variables if they are not already set. If Java cannot be located automatically, install JDK 11+ and set `JAVA_HOME` before retrying. You can pre-flight the download:
   ```powershell
   py -m earCrawler.cli kg-serve --dry-run
   ```

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
- Canary automation uses `canary/config.yml` plus `scripts/canary/run-canaries.ps1`.
- Telemetry policy and redaction rules are stored in `docs/privacy/`.
- Scheduler jobs and admin helpers persist structured run logs in `run/logs/`. Each JSON file contains a `run_id`, status, timestamps, and per-step metadata so operators can audit Windows Task Scheduler executions.
- The Trade.gov and Federal Register clients honour `TRADEGOV_MAX_CALLS` and `FR_MAX_CALLS` environment budgets. Requests use exponential backoff with structured retry logs, and the on-disk cache key now incorporates Accept/User-Agent headers to avoid stale mixes across CLI environments.

## Proposal Assets
- `scripts/demo-end-to-end.ps1` produces a deterministic crawl -> KG -> bundle run with fixtures and emits a summary artefact. The script uses the active `python` interpreter by default; override with `-Python` to call a specific executable.
- `scripts/build-release.ps1` orchestrates wheel/EXE/installer builds and writes SHA-256 checksums for signing.
- `docs/proposal/architecture.md`, `docs/proposal/security.md`, and `docs/proposal/observability.md` capture the architecture story, security posture, and SLO model pitched in the proposal.
- `api_clients.EarCrawlerApiClient` is a typed helper for downstream consumers of the FastAPI facade.

---

## Evaluation & Benchmarks

earCrawler ships a lightweight evaluation harness for Phase E experiments and regression checks.

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
$env:EARCTL_USER = 'test_operator'  # if RBAC is enabled
$env:EARCRAWLER_ENABLE_REMOTE_LLM = '1'
py -m earCrawler.cli eval run-rag --dataset-id ear_compliance.v1 --max-items 5
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

To log the results in `Research/decision_log.md`, run `python scripts/eval/log_eval_summary.py dist/eval/*.json` to emit a markdown-ready set of bullet points for all benchmark outputs in one go. This helper accepts one or many metrics files, making it easy to paste consolidated summaries into the research log.

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
  - `py -m earCrawler.cli llm ask --llm-provider groq --llm-model mixtral-8x7b-32768 "Can ACME export laptops to France?"`
  - `py -m earCrawler.cli llm ask --llm-provider nvidia_nim --llm-model <nim-model-id> "Are Huawei exports restricted under EAR?"`
- Requests use OpenAI-style `/chat/completions` endpoints with soft call budgets (configure with `LLM_MAX_CALLS` or `LLM_<PROVIDER>_MAX_CALLS`).

Run `py -m earCrawler.cli COMMAND --help` for detailed options.

---

## Troubleshooting

- **`earctl` is not recognized**  
  Add the user `Scripts` directory to `PATH` or run the CLI with `py -m earCrawler.cli`.

- **`command 'api' requires role(s): operator, maintainer`**  
  Set `EARCTL_USER=test_operator` (or configure your identity in `security/policy.yml`).

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

## TTL Build and Gated Load

- Transforms now emit `dist/bundle.ttl`.
- A validation gate must pass before any load.
- Local load (Windows PowerShell):
  ```powershell
  $env:EAR_FUSEKI_DATASET="http://localhost:3030/ear"
  $env:EAR_ENABLE_LOAD="1"
  python -m earCrawler.pipelines.build_ttl
  python -m earCrawler.pipelines.load_after_validate
  ```
