"""Trade.gov Data API client with caching and keyring integration."""
from __future__ import annotations

from pathlib import Path
import os
from typing import Dict, Iterable, List, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from earCrawler.utils.secure_store import get_secret
from earCrawler.utils.http_cache import HTTPCache
from earCrawler.utils import budget


class TradeGovError(Exception):
    """Raised for Trade.gov client errors or invalid responses."""


class TradeGovClient:
    """Client for the Trade.gov Consolidated Screening List gateway."""

    BASE_URL = "https://data.trade.gov/consolidated_screening_list/v1"
    SUBSCRIPTION_HEADER = "subscription-key"

    def __init__(self, *, session: requests.Session | None = None, cache_dir: Path | None = None) -> None:
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.api_key = get_secret("TRADEGOV_API_KEY", fallback="")
        self.user_agent = get_secret("TRADEGOV_USER_AGENT", fallback="ear-ai/0.2.5")
        self.cache = HTTPCache(cache_dir or Path(".cache/api/tradegov"))
        env_limit = os.getenv("TRADEGOV_MAX_CALLS")
        self.request_limit = int(env_limit) if env_limit else None

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def _get(self, endpoint: str, params: dict[str, str]) -> dict:
        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        }
        if not self.api_key:
            return {"results": []}
        else:
            headers[self.SUBSCRIPTION_HEADER] = self.api_key
        try:
            with budget.consume("tradegov", self.request_limit):
                resp = self.cache.get(self.session, url, params, headers=headers)
        except budget.BudgetExceededError:
            raise
        except requests.RequestException:
            return {"results": []}
        if resp.status_code in (301, 302) or any(h.status_code in (301, 302) for h in getattr(resp, "history", [])):
            raise TradeGovError(
                "Trade.gov redirected to developer portal. Confirm your CSL subscription and subscription-key header."
            )
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" not in content_type.lower():
            snippet = (resp.text or "")[:200]
            raise TradeGovError(
                f"Unexpected content type '{content_type}' from Trade.gov: {snippet}"
            )
        try:
            return resp.json()
        except ValueError as exc:  # pragma: no cover - invalid JSON
            raise TradeGovError("Invalid JSON response from Trade.gov") from exc

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        sources: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, str]]:
        """Search for entities matching ``query`` and return normalized records."""
        params: dict[str, str] = {"name": query, "size": str(max(1, min(limit, 50)))}
        if sources:
            params["sources"] = ",".join(sources)
        data = self._get("/search", params)
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

    def lookup_entity(self, query: str) -> Dict[str, str]:
        """Return the first entity result for ``query`` or an empty dict."""
        results = self.search(query, limit=1)
        return results[0] if results else {}

    # Backwards compatibility aliases
    def search_entities(self, query: str, page_size: int = 100):
        return iter(self.search(query, limit=page_size))


# Alias for legacy imports
TradeGovEntityClient = TradeGovClient


def search_entities(
    query: str,
    *,
    size: int = 10,
    sources: Optional[Iterable[str]] = None,
) -> List[Dict[str, str]]:
    """Convenience function mirroring :meth:`TradeGovClient.search`."""

    client = TradeGovClient()
    return client.search(query, limit=size, sources=sources)
