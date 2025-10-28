"""Re-export Federal Register client from the legacy location."""
from importlib import import_module

_mod = import_module("api_clients.federalregister_client")

FederalRegisterClient = _mod.FederalRegisterClient
FederalRegisterError = _mod.FederalRegisterError
search_documents = _mod.search_documents

__all__ = [
    "FederalRegisterClient",
    "FederalRegisterError",
    "search_documents",
]
