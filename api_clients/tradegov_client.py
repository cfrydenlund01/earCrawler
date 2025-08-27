"""Trade.gov Data API client with caching and keyring integration."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from earCrawler.utils.secure_store import get_secret
from earCrawler.utils.http_cache import HTTPCache


class TradeGovError(Exception):
    """Raised for Trade.gov client errors or invalid responses."""


class TradeGovClient:
    """Client for the Trade.gov entity lookup API."""

    BASE_URL = "https://api.trade.gov/v1"

    def __init__(self, *, session: requests.Session | None = None, cache_dir: Path | None = None) -> None:
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.api_key = get_secret("TRADEGOV_API_KEY")
        self.user_agent = get_secret("TRADEGOV_USER_AGENT", fallback="earCrawler/0.9")
        self.cache = HTTPCache(cache_dir or Path(".cache/api/tradegov"))

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def _get(self, endpoint: str, params: dict[str, str]) -> dict:
        url = f"{self.BASE_URL}{endpoint}"
        params = {"api_key": self.api_key, **params}
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        resp = self.cache.get(self.session, url, params, headers=headers)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError as exc:  # pragma: no cover - invalid JSON
            raise TradeGovError("Invalid JSON response from Trade.gov") from exc

    def search(self, query: str, *, limit: int = 10) -> List[Dict[str, str]]:
        """Search for entities matching ``query`` and return normalized records."""
        data = self._get("/entities/search", {"q": query, "size": str(limit)})
        results: List[Dict[str, str]] = []
        for item in data.get("results", []):
            results.append(
                {
                    "id": str(item.get("id") or item.get("entity_id") or ""),
                    "name": (item.get("name") or "").title(),
                    "country": item.get("country") or item.get("country_code") or "",
                    "source_url": item.get("url") or item.get("source_url") or "",
                }
            )
        return results

    def lookup_entity(self, name: str) -> Dict[str, str]:
        """Return the first entity result for ``name`` or an empty dict."""
        results = self.search(name, limit=1)
        return results[0] if results else {}

    # Backwards compatibility aliases
    def search_entities(self, query: str, page_size: int = 100):
        return iter(self.search(query, limit=page_size))


# Alias for legacy imports
TradeGovEntityClient = TradeGovClient
