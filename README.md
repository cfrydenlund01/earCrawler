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

2. **Install Python dependencies**
   ```powershell
   py -m pip install --upgrade pip
   py -m pip install --requirement requirements.txt
   ```
   This installs all runtime and developer dependencies defined in `requirements.txt`. To add the `earCrawler` console helpers to your user site-packages, install the project wheel as well:
   ```powershell
   py -m pip install --user --upgrade .
   ```
   Windows places the console scripts under:
   ```
   %LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\Scripts
   ```
   Either add that directory to `PATH` or invoke the CLI via the module form shown below.

3. **Optional: create an isolated environment**
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   py -m pip install --upgrade pip
   py -m pip install -r requirements.txt
   py -m pip install -e .
   ```

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

## B.26 — Schema and SHACL
- Defines `ear:` schema for Entities and Parts.
- Enforces shapes with `pyshacl` in CI on `windows-latest`.
- Local run:
  ```powershell
  python -m earCrawler.validation.validate_shapes
  ```

Upstream callers:

Keep using Trade.gov Data API for entity lookup and Federal Register API for EAR text via our clients.

Ensure transforms (`csl_to_rdf.py`, `ear_fr_to_rdf.py`) emit IRIs under ent: and part: to satisfy shapes.

Secrets: store in Windows Credential Store or vault. Do not hardcode.

## B.27 — TTL build and gated load
- Transforms now emit `dist/bundle.ttl`.
- Validation gate must pass before any load.
- Local load (Windows PowerShell):
  ```powershell
  $env:EAR_FUSEKI_DATASET="http://localhost:3030/ear"
  $env:EAR_ENABLE_LOAD="1"
  python -m earCrawler.pipelines.build_ttl
  python -m earCrawler.pipelines.load_after_validate
  ```

Data sources remain:

Trade.gov Data API for entity lookup.

Federal Register API for EAR text.
Embed accesses in client modules only.

Secrets: store in Windows Credential Store or a vault. Do not hardcode.
