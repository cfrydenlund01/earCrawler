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
cmdkey /generic:earCrawler:tradegov_api /user:ignored /pass:<YOUR_API_KEY>
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
from api_clients.federal_register_client import FederalRegisterClient

tradegov = TradeGovClient()
countries = tradegov.list_countries()

federal = FederalRegisterClient()
docs = federal.list_documents({"per_page": 5})
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
