# earCrawler Package

This directory contains the installable Python package that backs the
`earctl` CLI, FastAPI facade, and automation scripts described in the root
[`README.md`](../README.md). Use the top-level guide for environment setup,
tooling, and release instructions.

This package directory is part of the supported runtime surface. Proposal and
research materials live elsewhere in the repo; use
[`docs/runtime_research_boundary.md`](../docs/runtime_research_boundary.md) if
you need the repo-level support boundary.

## Local Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ..
```

## Library Usage

The package exposes the HTTP clients and utilities used throughout the CLI.
They can be imported directly when composing bespoke automation:

```python
from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient

tg = TradeGovClient()
entity = tg.lookup_entity("ACME Corp")
print(entity.get("id"), entity.get("name"))

fr = FederalRegisterClient()
articles = fr.get_ear_articles("export", per_page=1)
print(articles[0]["id"] if articles else "no articles")
```

`TradeGovClient.lookup_entity()` and `FederalRegisterClient.get_ear_articles()`
are the client entrypoints covered by the repository tests. Trade.gov requests
require a configured API key for live results; without one, the client returns
an empty record instead of raising.

Smoke checks:

```powershell
py -c "from api_clients.tradegov_client import TradeGovClient; from api_clients.federalregister_client import FederalRegisterClient; print(hasattr(TradeGovClient, 'lookup_entity'), hasattr(FederalRegisterClient, 'get_ear_articles'))"
py -m pytest tests/clients/test_tradegov_client.py tests/clients/test_federalregister_client.py tests/test_api_clients_stubs.py -q
```

The clients read credentials from the OS credential store (Windows Credential
Manager on Windows). Do not hard-code API keys. Consult `security/policy.yml`
for role-based command gating and `RUNBOOK.md` for service operations.
