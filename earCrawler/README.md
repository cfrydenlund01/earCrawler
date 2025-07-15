# earCrawler

## Installation
`PowerShell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
`

## Usage
`Python
from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient

tg = TradeGovClient()
countries = tg.list_countries()

fr = FederalRegisterClient()
docs = fr.list_documents({'per_page': 5})
`

Store API keys in Windows Credential Manager or your OS vault. Never hardcode them.
