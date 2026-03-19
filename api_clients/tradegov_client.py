"""Trade.gov Data API client with caching and keyring integration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from earCrawler.utils.secure_store import get_secret
from earCrawler.utils.http_cache import HTTPCache
from earCrawler.utils import budget
from earCrawler.utils.log_json import JsonLogger
from api_clients.upstream_status import (
    UpstreamState,
    UpstreamStatus,
    UpstreamStatusTracker,
)


_VARY_HEADERS = ("Accept", "User-Agent")
_logger = JsonLogger("tradegov-client")


def _log_retry(retry_state: RetryCallState) -> None:
    """Emit structured telemetry for retry attempts."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    wait_time = (
        getattr(retry_state.next_action, "sleep", None)
        if retry_state.next_action
        else None
    )
    endpoint = ""
    if len(retry_state.args) >= 2:
        endpoint = str(retry_state.args[1])
    _logger.warning(
        "api.retry",
        endpoint=endpoint,
        attempt=retry_state.attempt_number,
        wait_seconds=wait_time,
        error=str(exc) if exc else None,
    )


class TradeGovError(Exception):
    """Raised for Trade.gov client errors or invalid responses."""

    def __init__(
        self,
        message: str,
        *,
        state: UpstreamState = "upstream_unavailable",
    ) -> None:
        super().__init__(message)
        self.state = state


class TradeGovClient:
    """Client for the Trade.gov Consolidated Screening List gateway."""

    BASE_URL = "https://data.trade.gov/consolidated_screening_list/v1"
    SUBSCRIPTION_HEADER = "subscription-key"

    def __init__(
        self, *, session: requests.Session | None = None, cache_dir: Path | None = None
    ) -> None:
        self.session = session or requests.Session()
        self._owns_session = session is None
        self.session.trust_env = False
        self.api_key = get_secret("TRADEGOV_API_KEY", fallback="")
        self.user_agent = get_secret("TRADEGOV_USER_AGENT", fallback="ear-ai/0.2.5")
        ttl_env = os.getenv("TRADEGOV_CACHE_TTL_SECONDS")
        ttl_seconds = int(ttl_env) if ttl_env else None
        max_env = os.getenv("TRADEGOV_CACHE_MAX_ENTRIES")
        max_entries = int(max_env) if max_env else 4096
        self.cache = HTTPCache(
            cache_dir or Path(".cache/api/tradegov"),
            max_entries=max_entries,
            ttl_seconds=ttl_seconds,
        )
        env_limit = os.getenv("TRADEGOV_MAX_CALLS")
        self.request_limit = int(env_limit) if env_limit else None
        self._status = UpstreamStatusTracker("tradegov")
        _logger.info(
            "api.client.init",
            user_agent=self.user_agent,
            has_api_key=bool(self.api_key),
            request_limit=self.request_limit,
        )

    def _record_status(
        self,
        operation: str,
        state: UpstreamState,
        *,
        message: str | None = None,
        status_code: int | None = None,
        retry_attempts: int | None = None,
        result_count: int | None = None,
        cache_hit: bool | None = None,
        cache_age_seconds: float | None = None,
    ) -> UpstreamStatus:
        status = self._status.set(
            operation,
            state,
            message=message,
            status_code=status_code,
            retry_attempts=retry_attempts,
            result_count=result_count,
            cache_hit=cache_hit,
            cache_age_seconds=cache_age_seconds,
        )
        log_fn = _logger.warning if status.degraded else _logger.info
        log_fn(
            "api.upstream_state",
            operation=operation,
            state=state,
            status_code=status_code,
            retry_attempts=retry_attempts,
            result_count=result_count,
            cache_hit=cache_hit,
            cache_age_seconds=cache_age_seconds,
            message=message,
        )
        return status

    def get_last_status(self, operation: str | None = None) -> UpstreamStatus | None:
        """Return the latest known upstream status for ``operation``."""
        return self._status.get(operation)

    def get_status_snapshot(self) -> dict[str, dict[str, object]]:
        """Return the latest status payload for each tracked operation."""
        return self._status.snapshot()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1),
        retry=retry_if_exception_type(requests.RequestException),
        before_sleep=_log_retry,
    )
    def _get(self, endpoint: str, params: dict[str, str]) -> tuple[dict, bool, float | None]:
        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        }
        if not self.api_key:
            raise TradeGovError(
                "Trade.gov API key is not configured",
                state="missing_credentials",
            )
        headers[self.SUBSCRIPTION_HEADER] = self.api_key
        _logger.info(
            "api.request", endpoint=endpoint, params=params, limit=self.request_limit
        )
        try:
            with budget.consume("tradegov", self.request_limit):
                resp = self.cache.get(
                    self.session,
                    url,
                    params,
                    headers=headers,
                    vary_headers=_VARY_HEADERS,
                )
        except budget.BudgetExceededError:
            _logger.error(
                "api.budget_exceeded", endpoint=endpoint, limit=self.request_limit
            )
            raise
        if resp.status_code in (301, 302) or any(
            h.status_code in (301, 302) for h in getattr(resp, "history", [])
        ):
            _logger.error(
                "api.redirect", endpoint=endpoint, status=resp.status_code, url=resp.url
            )
            raise TradeGovError(
                "Trade.gov redirected to developer portal. Confirm your CSL subscription and subscription-key header.",
                state="invalid_response",
            )
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" not in content_type.lower():
            snippet = (resp.text or "")[:200]
            _logger.error(
                "api.invalid_content_type",
                endpoint=endpoint,
                content_type=content_type,
                preview=snippet,
            )
            raise TradeGovError(
                f"Unexpected content type '{content_type}' from Trade.gov: {snippet}",
                state="invalid_response",
            )
        try:
            payload = resp.json()
        except ValueError as exc:  # pragma: no cover - invalid JSON
            _logger.error("api.invalid_json", endpoint=endpoint, error=str(exc))
            raise TradeGovError(
                "Invalid JSON response from Trade.gov",
                state="invalid_response",
            ) from exc
        _logger.info(
            "api.response",
            endpoint=endpoint,
            status=resp.status_code,
            cache="hit" if getattr(resp, "from_cache", False) else "miss",
            cache_age_seconds=getattr(resp, "cache_age_seconds", None),
            result_count=(
                len(payload.get("results", [])) if isinstance(payload, dict) else None
            ),
        )
        return (
            payload,
            bool(getattr(resp, "from_cache", False)),
            (
                float(getattr(resp, "cache_age_seconds"))
                if getattr(resp, "cache_age_seconds", None) is not None
                else None
            ),
        )

    @staticmethod
    def _classify_request_error(
        exc: requests.RequestException,
    ) -> tuple[UpstreamState, int | None]:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code is not None and 400 <= int(status_code) < 500:
            return "upstream_unavailable", int(status_code)
        return "retry_exhausted", int(status_code) if status_code is not None else None

    @staticmethod
    def _normalize_get_result(
        payload: dict | tuple[dict, bool, float | None],
    ) -> tuple[dict, bool, float | None]:
        if isinstance(payload, tuple) and len(payload) == 3:
            data, cache_hit, cache_age_seconds = payload
            return dict(data), bool(cache_hit), (
                float(cache_age_seconds) if cache_age_seconds is not None else None
            )
        return dict(payload), False, None

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        sources: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, str]]:
        """Search for entities matching ``query`` and return normalized records."""
        operation = "search"
        params: dict[str, str] = {"name": query, "size": str(max(1, min(limit, 50)))}
        if sources:
            params["sources"] = ",".join(sources)
        if not self.api_key:
            self._record_status(
                operation,
                "missing_credentials",
                message="TRADEGOV_API_KEY is empty; request skipped",
            )
            _logger.warning(
                "api.request.skipped",
                reason="missing_api_key",
                endpoint="/search",
            )
            return []
        try:
            data, cache_hit, cache_age_seconds = self._normalize_get_result(
                self._get("/search", params)
            )
        except TradeGovError as exc:
            self._record_status(operation, exc.state, message=str(exc))
            _logger.error(
                "api.request_failed",
                endpoint="/search",
                query=query,
                state=exc.state,
                error=str(exc),
            )
            return []
        except requests.RequestException as exc:
            state, status_code = self._classify_request_error(exc)
            self._record_status(
                operation,
                state,
                message=str(exc),
                status_code=status_code,
                retry_attempts=3 if state == "retry_exhausted" else None,
            )
            _logger.error(
                "api.request_failed",
                endpoint="/search",
                query=query,
                state=state,
                status_code=status_code,
                error=str(exc),
            )
            return []
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
        if results:
            self._record_status(
                operation,
                "ok",
                result_count=len(results),
                cache_hit=cache_hit,
                cache_age_seconds=cache_age_seconds,
            )
        else:
            self._record_status(
                operation,
                "no_results",
                message=f"No entities matched query={query!r}",
                result_count=0,
                cache_hit=cache_hit,
                cache_age_seconds=cache_age_seconds,
            )
        return results

    def lookup_entity(self, query: str) -> Dict[str, str]:
        """Return the first entity result for ``query`` or an empty dict."""
        operation = "lookup_entity"
        results = self.search(query, limit=1)
        if results:
            self._record_status(operation, "ok", result_count=1)
            return results[0]
        search_status = self.get_last_status("search")
        if search_status is not None:
            self._record_status(
                operation,
                search_status.state,
                message=search_status.message,
                status_code=search_status.status_code,
                retry_attempts=search_status.retry_attempts,
                result_count=0,
            )
        else:
            self._record_status(
                operation,
                "no_results",
                message=f"No entity found for query={query!r}",
                result_count=0,
            )
        return {}

    # Backwards compatibility aliases
    def search_entities(self, query: str, page_size: int = 100):
        return iter(self.search(query, limit=page_size))

    # Resource lifecycle -------------------------------------------------
    def close(self) -> None:
        try:
            if self._owns_session:
                self.session.close()
        except Exception:
            pass


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
