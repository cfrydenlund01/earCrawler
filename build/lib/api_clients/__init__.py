"""API client exports.

Imports that require Windows credentials are wrapped so Linux tests do not fail
when the optional dependencies are missing.
"""

try:  # pragma: no cover - platform specific
    from .tradegov_client import (
        TradeGovEntityClient,
        TradeGovClient,
        TradeGovError,
    )
except Exception:  # pragma: no cover - optional on non-Windows
    TradeGovEntityClient = None  # type: ignore
    TradeGovClient = None  # type: ignore
    TradeGovError = Exception  # type: ignore

try:  # pragma: no cover - platform specific
    from .federalregister_client import FederalRegisterClient, FederalRegisterError
except Exception:  # pragma: no cover - optional on non-Windows
    FederalRegisterClient = None  # type: ignore
    FederalRegisterError = Exception  # type: ignore

from .ori_client import ORIClient, ORIClientError
