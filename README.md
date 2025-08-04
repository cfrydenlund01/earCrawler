# earCrawler

## Project Overview
EarCrawler is a retrieval-augmented crawler used by the EAR-QA system to gather
regulatory data from Trade.gov and the Federal Register. It provides light‑weight
API clients and utilities for building question answering workflows backed by
a RAG (Retrieval Augmented Generation) approach.

## Prerequisites
- **Python 3.11**
- **Windows 11**
- **Git**
- **Trade.gov API key**
- **Docker Desktop**

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
Use the KG service to run safe SPARQL queries and insert validated triples.

```bash
curl -X POST http://localhost:8000/kg/query -H "Content-Type: application/json" \
  -d "{\"sparql\": \"SELECT * WHERE {?s ?p ?o} LIMIT 1\"}"

curl -X POST http://localhost:8000/kg/insert -H "Content-Type: application/json" \
  -d "{\"ttl\": \"<a> <b> <c>.\"}"
```

```python
from fastapi.testclient import TestClient
from earCrawler.service.kg_service import app

client = TestClient(app)
resp = client.post("/kg/query", json={"sparql": "SELECT * WHERE {}"})
print(resp.json())
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



## Testing
Run the test suite with:
```cmd
pytest
```
The ingestion, service, and RAG tests rely on optional dependencies installed in the setup instructions. Ensure that `rdflib`, `pyshacl`, `fastapi`, `uvicorn[standard]`, `SPARQLWrapper`, `sentence-transformers`, and `faiss-cpu` are available.

## CI/CD
Continuous integration runs on GitHub Actions using the `windows-latest` image.
See `.github/workflows/ci.yml` for details.

## Contributing
Pull requests are welcome. For major changes, please open an issue first to
discuss what you would like to change.

## License
This project is licensed under the MIT License.
