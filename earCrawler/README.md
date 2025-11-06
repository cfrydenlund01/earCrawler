# earCrawler Package

This directory contains the installable Python package that backs the
`earctl` CLI, FastAPI facade, and automation scripts described in the root
[`README.md`](../README.md). Use the top-level guide for environment setup,
tooling, and release instructions.

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
countries = tg.list_countries()

fr = FederalRegisterClient()
docs = fr.list_documents({'per_page': 5})
```

The clients read credentials from the OS credential store (Windows Credential
Manager on Windows). Do not hard-code API keys. Consult `security/policy.yml`
for role-based command gating and `RUNBOOK.md` for service operations.
