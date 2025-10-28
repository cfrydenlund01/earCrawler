"""Re-export ORI client from the legacy location."""
from importlib import import_module

_mod = import_module("api_clients.ori_client")

ORIClient = _mod.ORIClient
ORIClientError = _mod.ORIClientError

__all__ = ["ORIClient", "ORIClientError"]
