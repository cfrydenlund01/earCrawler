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
cloned to `C:\Projects\earCrawler`.

```cmd
cd C:\Projects\earCrawler
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
pip install .
earCrawler --help
cmdkey /generic:TRADEGOV_API_KEY /user:ignored /pass:<YOUR_API_KEY>
REM Optional modules used by tests and examples
python -m pip install rdflib pyshacl fastapi "uvicorn[standard]" SPARQLWrapper
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
## Service
```python
from fastapi import FastAPI
from earCrawler.service.sparql_service import app

# run with: uvicorn earCrawler.service.sparql_service:app --reload
```

## Analytics
```python
from earCrawler.analytics.reports import ReportsGenerator

reports = ReportsGenerator()
print(reports.count_entities_by_country())
print(reports.count_documents_by_year())
print(reports.get_document_count_for_entity("ENTITY123"))
```

## CLI Usage
Run the same reports from the command line:
```powershell
earCrawler countries
earCrawler years
earCrawler entity-docs ENTITY123
```


## Testing
Run the test suite with:
```cmd
pytest
```

## CI/CD
Continuous integration runs on GitHub Actions using the `windows-latest` image.
See `.github/workflows/ci.yml` for details.

## Contributing
Pull requests are welcome. For major changes, please open an issue first to
discuss what you would like to change.

## License
This project is licensed under the MIT License.
