"""Compat exports for API clients.

Imports that rely on Windows credential helpers are wrapped so Linux tests do
not fail when optional dependencies are missing. Convenience functions are
re-exported for legacy call sites (``search_entities`` / ``search_documents``).
"""

try:  # pragma: no cover - platform specific
    from .tradegov_client import (
        TradeGovClient,
        TradeGovEntityClient,
        TradeGovError,
        search_entities,
    )
except Exception:  # pragma: no cover - optional on non-Windows
    TradeGovClient = None  # type: ignore
    TradeGovEntityClient = None  # type: ignore
    TradeGovError = Exception  # type: ignore

    def search_entities(*args, **kwargs):  # type: ignore
        raise RuntimeError(
            "Trade.gov client unavailable: install dependencies or configure secrets"
        )


try:  # pragma: no cover - platform specific
    from .federalregister_client import (
        FederalRegisterClient,
        FederalRegisterError,
        search_documents,
    )
except Exception:  # pragma: no cover - optional on non-Windows
    FederalRegisterClient = None  # type: ignore
    FederalRegisterError = Exception  # type: ignore

    def search_documents(*args, **kwargs):  # type: ignore
        raise RuntimeError(
            "Federal Register client unavailable: install dependencies or configure secrets"
        )


from .ear_api_client import EarCrawlerApiClient, EarApiError
from .ori_client import ORIClient, ORIClientError

__all__ = [
    "TradeGovClient",
    "TradeGovEntityClient",
    "TradeGovError",
    "search_entities",
    "FederalRegisterClient",
    "FederalRegisterError",
    "search_documents",
    "ORIClient",
    "ORIClientError",
    "EarCrawlerApiClient",
    "EarApiError",
]
