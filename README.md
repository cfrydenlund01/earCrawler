# earCrawler
[![CI](https://github.com/cfrydenlund01/earCrawler/actions/workflows/ci.yml/badge.svg)](https://github.com/cfrydenlund01/earCrawler/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/cfrydenlund01/earCrawler/branch/main/graph/badge.svg)](https://codecov.io/gh/cfrydenlund01/earCrawler)

## Project Overview
EarCrawler is a retrieval-augmented crawler used by the EAR-QA system to gather
regulatory data from Trade.gov and the Federal Register. It provides light‑weight
API clients and utilities for building question answering workflows backed by
a RAG (Retrieval Augmented Generation) approach.

## Prerequisites
- **Python 3.11**
- **Windows 11**
- **PowerShell 7** (`pwsh`) on the PATH
- **Git**
- **Trade.gov API key**
- **Docker Desktop**

## Installation (Windows)
Download the signed installer or standalone executable from the releases page, or install the wheel from PyPI:

```bash
pip install earCrawler
```

## CLI usage
The CLI is available as `earctl`:

```cmd
earctl --help
earctl diagnose
```

### B.18 Reconciliation
The reconciliation engine merges duplicate entities across sources using
deterministic rules.  Example usage:

```cmd
earctl reconcile run
earctl reconcile report
earctl reconcile explain s1 s2
```

## Setup
Use the commands below from a Windows terminal. The repository is assumed to be
cloned to `C:\Users\cfrydenlund\Projects\earCrawler`.

```cmd
cd C:\Users\cfrydenlund\Projects\earCrawler
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
cmdkey /generic:TRADEGOV_API_KEY /user:ignored /pass:<YOUR_API_KEY>
REM Optional modules used by tests and examples
python -m pip install rdflib pyshacl fastapi "uvicorn[standard]" SPARQLWrapper sentence-transformers faiss-cpu
```

## Secret Management
- Store API keys and SPARQL URLs in the Windows Credential Manager or as
  environment variables. Never commit secrets to source control.
- Rotate credentials with `cmdkey /delete:<NAME>` followed by a new `cmdkey`
  command. See `RUNBOOK.md` for detailed procedures.

## Telemetry (opt-in)
Telemetry and crash reporting are disabled by default. Enable only if you wish to share anonymous usage statistics.

```cmd
earctl telemetry status
earctl telemetry enable
earctl telemetry disable
earctl telemetry test
earctl crash-test  # writes a crash report to the spool
```

See `docs/privacy/telemetry_policy.md` for details and how to purge data.

## Testing
Run the CPU test suite:

```bash
pytest -m "not gpu"
```

Run the GPU tests:

```bash
pytest -m gpu
```

## Validation
Run sanity checks on emitted Turtle before using them.

```powershell
python -m cli.kg_emit --sources ear --sources nsf --in data --out data\kg
python -m cli.kg_validate --glob "data\kg\*.ttl"
```

## Repository Structure
- `api_clients/` – clients for Trade.gov and Federal Register APIs.
- `tests/` – unit tests covering success and failure scenarios.
- `.github/workflows/ci.yml` – GitHub Actions workflow.
- `requirements.txt` – Python dependencies.
- `README.md`, `CHANGELOG.md` – project documentation.

## Usage
```python
from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient

tradegov = TradeGovClient()
countries = tradegov.list_countries()

federal = FederalRegisterClient()
for doc in federal.search_documents("export controls", per_page=5):
    print(doc)
```

## API Clients
Example use of the `TradeGovClient`:

```python
from api_clients.tradegov_client import TradeGovClient

client = TradeGovClient()
for entity in client.search_entities("export controls", page_size=50):
    print(entity)
```

Example use of the `FederalRegisterClient`:

```python
from api_clients.federalregister_client import FederalRegisterClient

client = FederalRegisterClient()
for doc in client.search_documents("export controls", per_page=50):
    print(doc["document_number"])
```

The Federal Register API is public and requires no API key.

## NSF Case Parser
Parse NSF/ORI misconduct cases from offline HTML. The parser extracts
paragraphs, entities, and a deterministic hash for each case. Use the CLI:

```cmd
python -m earCrawler.cli nsf-parse --fixtures tests/fixtures --out data --live false
```

Each case is written as a JSON file under `data`. Store the Trade.gov API key in
the Windows Credential Manager:

```cmd
cmdkey /generic:TRADEGOV_API_KEY /user:ignored /pass:<YOUR_API_KEY>
```

An ORI client scaffold is included for future live crawling.

## Unified Corpus Loader
Use the ``CorpusLoader`` abstraction to consume paragraphs from different
sources. The CLI can load multiple corpora at once:

```cmd
python -m earCrawler.cli crawl --sources ear nsf
```

## Reporting
Generate analytics across saved corpora:

```bash
python -m earCrawler.cli report --sources ear nsf --type top-entities --entity ORG --n 5
```

Write the results to a JSON file instead of stdout:

```bash
python -m earCrawler.cli report --sources ear --type term-frequency --n 10 --out report.json
```

## Ontology & TTL Emitters
Generate deterministic RDF/Turtle for the EAR and NSF corpora:

```cmd
python -m earCrawler.cli kg-emit -s ear -s nsf -i data -o data\\kg
```

Outputs `data\\kg\\ear.ttl` and `data\\kg\\nsf.ttl`. Re-running the command without input changes produces byte-identical files.

## Knowledge Graph
- `kg/ear_ontology.ttl`: RDF schema for paragraphs & entities.
- `python -m earCrawler.cli kg-export`: Export TTL triples.
- Start Fuseki: `fuseki-server --config config/fuseki-config.ttl`

### Setup for SHACL/OWL validation
1. Install Java 17+ and verify the installation:
   ```powershell
   java -version
   ```
2. Bootstrap the Jena tools:
   ```powershell
   python -m earCrawler.utils.jena_tools
   pwsh scripts/check_jena_env.ps1
   ```
3. Download Apache Jena Fuseki or use an existing installation and verify:
   ```powershell
   fuseki-server --version
   ```
   
- The PowerShell scripts under `kg/scripts` require `pwsh` (PowerShell 7) and
  will auto-download Apache Jena and Fuseki into `tools/jena` and `tools/fuseki`
  when missing.

### Load triples without installing Jena
```
# Export TTL
python -m earCrawler.cli kg-export

# Load into a local TDB2 store; earCrawler will auto-download Jena to .\tools\jena
python -m earCrawler.cli kg-load --ttl kg\ear_triples.ttl --db db
```
To disable auto-download, add `--no-auto-install`. By default, Jena is fetched once and cached in `tools\jena`.
Local bootstrap uses the Apache archive for pinned Jena 5.3.0; set `JENA_VERSION` to override.

### Jena bootstrap

The repository pins Apache Jena to version **5.3.0** via `tools/versions.json`.
Running any command that needs Jena will download the Windows binary
distribution to `tools\jena`, preferring the Apache archive and falling back to
the live mirror if required. The extracted layout must contain `bat\` scripts
like `riot.bat`, `arq.bat`, and either `tdb2_tdbloader.bat` or
`tdb2.tdbloader.bat`. Override the version by setting the `JENA_VERSION`
environment variable.

### Phase B.3 — Serve & Query

```powershell
# Serve (foreground)
python -m earCrawler.cli kg-serve -d db -p 3030 --dataset /ear

# Dry run (print command)
python -m earCrawler.cli kg-serve --dry-run

# Query (SELECT)
python -m earCrawler.cli kg-query --sparql "SELECT * WHERE { ?s ?p ?o } LIMIT 5" -o data\rows.json

# Query (CONSTRUCT)
python -m earCrawler.cli kg-query --form construct -q "CONSTRUCT WHERE { ?s ?p ?o } LIMIT 10" -o data\graph.nt
```

**Troubleshooting:**
- If port 3030 is in use, specify a free one with `-p 3031`.
- On first run, Jena auto-downloads to `.\tools\jena`; no PATH changes required.


## Core
Combine both clients using the ``Crawler`` orchestration layer:

```python
from earCrawler.core.crawler import Crawler
from earCrawler.api_clients.tradegov_client import TradeGovClient
from earCrawler.api_clients.federalregister_client import FederalRegisterClient

crawler = Crawler(TradeGovClient(), FederalRegisterClient())
entities, documents = crawler.run("renewable energy")
```

## Ingestion
```python
from pathlib import Path
from earCrawler.ingestion.ingest import Ingestor
from earCrawler.api_clients.tradegov_client import TradeGovClient
from earCrawler.api_clients.federalregister_client import FederalRegisterClient

ingestor = Ingestor(
  TradeGovClient(),
  FederalRegisterClient(),
  Path(r"C:\\Projects\\earCrawler\\data\\tdb2")
)
ingestor.run("emerging technology")
```
## RAG
To use the Retriever you must install the optional packages
`sentence-transformers` and `faiss-cpu`:

```bash
pip install sentence-transformers faiss-cpu
```
```python
from pathlib import Path
from earCrawler.rag.retriever import Retriever
from earCrawler.api_clients.tradegov_client import TradeGovClient
from earCrawler.api_clients.federalregister_client import FederalRegisterClient

retriever = Retriever(
    TradeGovClient(),
    FederalRegisterClient(),
    model_name="all-MiniLM-L12-v2",
    index_path=Path(r"C:\\Projects\\earCrawler\\data\\faiss\\index.faiss")
)
retriever.add_documents(docs)
results = retriever.query("export control regulations", k=5)
```
## Service
```python
from fastapi import FastAPI
from earCrawler.service.sparql_service import app

# run with: uvicorn earCrawler.service.sparql_service:app --reload
```

## Knowledge Graph Service
Start the service after setting environment variables for the SPARQL endpoint
and SHACL shapes file:

```cmd
set SPARQL_ENDPOINT_URL=http://localhost:3030/ds
set SHAPES_FILE_PATH=C:\path\to\shapes.ttl
uvicorn earCrawler.service.kg_service:app --reload
```

Query the knowledge graph via ``curl``:

```bash
curl -X POST http://localhost:8000/kg/query \
  -H "Content-Type: application/json" \
  -d "{\"sparql\": \"SELECT * WHERE { ?s ?p ?o } LIMIT 1\"}"
```

Insert triples from Python:

```python
from fastapi.testclient import TestClient
from earCrawler.service.kg_service import app

client = TestClient(app)
client.post("/kg/insert", json={"ttl": "<a> <b> <c> ."})
```

## Analytics
```python
from earCrawler.analytics.reports import ReportsGenerator

reports = ReportsGenerator()
print(reports.count_entities_by_country())
print(reports.count_documents_by_year())
print(reports.get_document_count_for_entity("ENTITY123"))
```

## CLI
```bash
cd C:\Projects\earCrawler
pip install .
earCrawler --help
export ANALYTICS_SERVICE_URL=http://localhost:8000
earCrawler reports entities-by-country
earCrawler reports documents-by-year
earCrawler reports document-count ENTITY123
```

## Models
Install the optional dependencies and run the Legal-BERT training script:

```cmd
pip install transformers peft accelerate
python earCrawler\models\legalbert\train.py --do_train --do_eval
```


## Agent
Fine-tune a quantized Mistral-7B model with QLoRA and run the agent:

```cmd
pip install bitsandbytes peft transformers datasets
python -m earCrawler.agent.mistral_agent  # runs small adapter training
```

Use the trained adapter at `models/mistral7b/qlora_adapter` with the `Agent` class:

```python
from earCrawler.agent.mistral_agent import Agent
from earCrawler.rag.retriever import Retriever

retriever = Retriever(...)
agent = Agent(retriever)
print(agent.answer("What does EAR regulate?"))
```

## Benchmarking
Run the end-to-end benchmark to measure retrieval, classification, and
generation latency. The script spins up the internal FastAPI services using
``TestClient`` and writes metrics to ``reports/benchmark_results.csv``.

```cmd
python scripts/benchmark.py --queries scripts/benchmark_queries.json
```

## Testing
Run the test suite with:
```cmd
pytest
```
The ingestion, service, and RAG tests rely on optional dependencies installed in the setup instructions. Ensure that `rdflib`, `pyshacl`, `fastapi`, `uvicorn[standard]`, `SPARQLWrapper`, `sentence-transformers`, and `faiss-cpu` are available.

## CI/CD
Continuous integration runs on GitHub Actions using the `windows-latest` image.
See `.github/workflows/ci.yml` for details.

## Containerized Builds
An Apptainer definition file is available at `container/earcrawler.def` for GPU-aware runs.
Build a writable sandbox and execute commands inside the container:

```bash
apptainer build --sandbox earcrawler_sandbox container/earcrawler.def
apptainer exec --nv earcrawler_sandbox python train.py --config <config_path>
```

See [`container/README.md`](container/README.md) for installation and usage details.

## Contributing
Pull requests are welcome. For major changes, please open an issue first to
discuss what you would like to change.

## License
This project is licensed under the MIT License.

## B.6 (Windows)
The `kg/scripts/ci-roundtrip.ps1` script validates Turtle files with RIOT,
round-trips them through a fresh TDB2 store, snapshots deterministic SPARQL
queries to `kg/snapshots/*.srj`, and performs a Fuseki smoke query.

Run locally:

```powershell
pwsh kg/scripts/ci-roundtrip.ps1
```

## B.7 SHACL/OWL smoke (Windows)
The `kg/scripts/ci-shacl-owl.ps1` script validates ontology TTL files against SHACL shapes and runs lightweight OWL reasoner ASK checks.

Run locally:

```powershell
pwsh kg/scripts/ci-shacl-owl.ps1
```

Artifacts are written to `kg/reports/`:
- `shacl-report.ttl` and `shacl-report.json`
- `shacl-conforms.txt` with `true` or `false`
- `owl-smoke.json` summarizing three ASK checks

Failures indicate SHACL non-conformance or missing OWL entailments. Review the report files to diagnose issues.

## B.8 Inference service (Windows)
Use the assembler configs under `kg/assembler/` to expose an inference-enabled dataset at `/ds-inf`.

```powershell
fuseki-server.bat --config kg/assembler/tdb2-inference-rdfs.ttl
# or
fuseki-server.bat --config kg/assembler/tdb2-inference-owlmini.ttl
```

Run the smoke script to validate remote ASK queries and capture a SELECT report:

```powershell
pwsh kg/scripts/ci-inference-smoke.ps1 -Mode rdfs
pwsh kg/scripts/ci-inference-smoke.ps1 -Mode owlmini
```

Artifacts are written to `kg/reports/`:
- `inference-<mode>.json` summary of ASK checks
- `inference-<mode>.txt` one-line status
- `inference-<mode>-select.srj` SELECT snapshot

All ASK checks must pass for the script to exit 0. Use the `.srj` file for manual inspection of inferred bindings.

## B.9 API integrations

The Trade.gov and Federal Register clients use `keyring` to load API keys and
user agents from the Windows Credential Manager. Environment variables with the
same names override stored secrets. Responses are cached on disk under
`.cache/api/` with ETag support so subsequent runs are deterministic.

Contract tests ship with [VCR](https://github.com/kevin1024/vcrpy) cassettes so
CI runs completely offline. To refresh recordings locally set
`VCR_RECORD_MODE=once` and run the tests; commit the updated files afterwards.

## B.10 Provenance (PROV-O)

API-sourced triples now carry W3C PROV-O lineage. Domain data remains in the
default graph while provenance quads are written to the named graph
`urn:graph:prov` under `kg/prov/`. Deterministic IRIs connect
`prov:Entity` resources to their generating `prov:Activity` and responsible
`prov:Agent`. Run the lineage checks:

```powershell
pwsh kg/scripts/ci-provenance.ps1
```

Reports appear in `kg/reports/` and include counts of missing provenance,
activity integrity, and a sample SELECT for manual review.

## B.11 Incremental builds

`kg/scripts/ci-incremental.ps1` hashes all KG inputs and stores a manifest
under `kg/.kgstate/manifest.json`. A subsequent run compares hashes to detect
changes. When nothing changed the script writes
`kg/reports/incremental-noop.txt` and exits quickly. When inputs differ it
re-runs the round-trip, SHACL/OWL, inference, and provenance steps, then writes
diffs for canonical N-Quads and SPARQL snapshots to `kg/reports/`.

## B.14 Retention & GC

Centralised retention policies govern telemetry spools, API caches, and KG
artifacts. Preview actions with:

```powershell
earctl gc --dry-run --target all
```

Run with `--apply --yes` to delete and record an audit log under
`kg/reports/`.

## B.15 Hermetic toolchain

Build and install dependencies from the pre-verified wheelhouse:

```powershell
pwsh -File .\scripts\build-wheelhouse.ps1
pwsh -File .\scripts\install-from-wheelhouse.ps1
```

## B.17 Monitoring & Delta Ingest

A scheduled job runs on weekdays at 08:15 America/Chicago to check watchlisted
Trade.gov and Federal Register sources. Results are normalized and hashed to
detect changes. When upstream content changes, the job writes dated delta files
under `monitor/`, converts them to Turtle and regenerates only the impacted
SPARQL snapshots. An automated pull request is then opened with the updated
artifacts.
