"""Client for Trade.gov Data API."""

from __future__ import annotations

import requests
import win32cred


class TradeGovClient:
    """Simple Trade.gov API client."""

    BASE_URL = "https://api.trade.gov/v1"

    def __init__(self) -> None:
        self.api_key = self._load_api_key()

    @staticmethod
    def _load_api_key() -> str:
        try:
            cred = win32cred.CredRead(
                "earCrawler:tradegov_api",
                win32cred.CRED_TYPE_GENERIC,
                0,
            )
            return cred["CredentialBlob"].decode("utf-16")
        except Exception as exc:  # pylint: disable=broad-except
            raise RuntimeError(
                "Trade.gov API key not found in Windows Credential Manager"
            ) from exc

    def list_countries(self) -> dict:
        """Return a list of countries from Trade.gov."""
        url = f"{self.BASE_URL}/countries"
        try:
            response = requests.get(url, params={"api_key": self.api_key}, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:  # pragma: no cover - network failure
            raise RuntimeError(f"Failed to fetch countries: {exc}") from exc
