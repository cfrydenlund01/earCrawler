"""Re-export Trade.gov client from the legacy location."""
from importlib import import_module

_mod = import_module("api_clients.tradegov_client")

TradeGovClient = _mod.TradeGovClient
TradeGovEntityClient = _mod.TradeGovEntityClient
TradeGovError = _mod.TradeGovError
search_entities = _mod.search_entities

__all__ = [
    "TradeGovClient",
    "TradeGovEntityClient",
    "TradeGovError",
    "search_entities",
]
