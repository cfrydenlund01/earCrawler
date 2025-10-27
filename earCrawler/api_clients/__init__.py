"""Compatibility re-exports for API clients."""
from importlib import import_module

_tradegov = import_module("api_clients.tradegov_client")
_federal = import_module("api_clients.federalregister_client")
_ori = import_module("api_clients.ori_client")

TradeGovClient = _tradegov.TradeGovClient
TradeGovEntityClient = _tradegov.TradeGovEntityClient
TradeGovError = _tradegov.TradeGovError
search_entities = _tradegov.search_entities

FederalRegisterClient = _federal.FederalRegisterClient
FederalRegisterError = _federal.FederalRegisterError
search_documents = _federal.search_documents

ORIClient = _ori.ORIClient
ORIClientError = _ori.ORIClientError

__all__ = [
    "FederalRegisterClient",
    "FederalRegisterError",
    "ORIClient",
    "ORIClientError",
    "TradeGovClient",
    "TradeGovEntityClient",
    "TradeGovError",
    "search_documents",
    "search_entities",
]
