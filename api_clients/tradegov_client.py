"""Client for the Trade.gov Data API.

This module provides :class:`TradeGovEntityClient` for querying the Trade.gov
entities endpoint. The API key should be stored in the Windows Credential
Manager under the target name ``TRADEGOV_API_KEY`` or supplied via the
``TRADEGOV_API_KEY`` environment variable—never hard-coded in source code.
"""

from __future__ import annotations

import os
import time
from typing import Iterator

import requests

try:  # pragma: no cover - optional on non-Windows
    import win32cred  # type: ignore
except Exception:  # pragma: no cover - non-Windows fallback
    win32cred = None


class TradeGovError(Exception):
    """Raised for Trade.gov client errors or invalid responses."""


class TradeGovEntityClient:
    """Simple Trade.gov API client."""

    BASE_URL = "https://api.trade.gov/v1"

    def __init__(self) -> None:
        self.api_key = self._load_api_key()
        self.session = requests.Session()

    @staticmethod
    def _load_api_key() -> str:
        """Load the API key from env var or Windows Credential Manager."""
        env_key = os.getenv("TRADEGOV_API_KEY")
        if env_key:
            return env_key
        if win32cred is not None:  # pragma: no cover - platform specific
            try:
                cred = win32cred.CredRead(
                    "TRADEGOV_API_KEY",
                    win32cred.CRED_TYPE_GENERIC,
                    0,
                )
                return cred["CredentialBlob"].decode("utf-16")
            except Exception:  # pragma: no cover - platform specific
                pass
        raise RuntimeError(
            "TRADEGOV_API_KEY not found in environment or Windows Credential Manager",
        )

    def list_countries(self) -> dict:
        """Return a list of countries from Trade.gov."""
        url = f"{self.BASE_URL}/countries"
        response = self.session.get(url, params={"api_key": self.api_key}, timeout=10)
        response.raise_for_status()
        return response.json()

    def search_entities(self, query: str, page_size: int = 100) -> Iterator[dict]:
        """Search the Trade.gov entities endpoint and yield each result.

        Parameters
        ----------
        query:
            Free text search query.
        page_size:
            Number of results per page.
        """
        url = f"{self.BASE_URL}/entities/search"
        page = 1
        while True:
            params = {
                "api_key": self.api_key,
                "q": query,
                "size": page_size,
                "page": page,
            }
            attempts = 3
            for attempt in range(attempts):
                try:
                    response = self.session.get(url, params=params, timeout=10)
                    response.raise_for_status()
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise TradeGovError("Invalid JSON from Trade.gov") from exc
                    break
                except requests.HTTPError as exc:
                    status = getattr(exc.response, "status_code", 0)
                    if 500 <= status < 600 and attempt < attempts - 1:
                        time.sleep(2 ** attempt)
                        continue
                    if 400 <= status < 500:
                        message = getattr(exc.response, "text", str(status))
                        raise TradeGovError(
                            f"Trade.gov client error: {message}"
                        ) from exc
                    raise TradeGovError(
                        f"Trade.gov request failed: {status}"
                    ) from exc
                except requests.RequestException as exc:
                    if attempt < attempts - 1:
                        time.sleep(2 ** attempt)
                        continue
                    raise TradeGovError(
                        f"Trade.gov request error: {exc}"
                    ) from exc
            results = data.get("results", [])
            for item in results:
                yield item
            next_page = data.get("next_page")
            if not next_page:
                break
            page = next_page


    def lookup_entity(self, query: str) -> dict:
        """Return the first entity matching ``query`` or an empty dict if none."""
        return next(self.search_entities(query, page_size=1), {})

# Backwards compatibility alias
TradeGovClient = TradeGovEntityClient
