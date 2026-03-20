from __future__ import annotations

"""Crawler orchestrates Trade.gov and Federal Register API clients."""

import logging
from typing import Dict, List, Tuple, TYPE_CHECKING

try:
    from api_clients.tradegov_client import TradeGovError
except Exception:  # pragma: no cover - fallback for non-Windows env

    class TradeGovError(Exception):
        """Fallback TradeGov error when client module is unavailable."""


try:
    from api_clients.federalregister_client import FederalRegisterError
except Exception:  # pragma: no cover - fallback for non-Windows env

    class FederalRegisterError(Exception):
        """Fallback Federal Register error when client module is
        unavailable."""


if TYPE_CHECKING:  # pragma: no cover - type hints only
    from api_clients.tradegov_client import TradeGovClient
    from api_clients.federalregister_client import FederalRegisterClient


class Crawler:
    """Orchestrate entity and document retrieval for ingestion.

    Parameters
    ----------
    tradegov_client:
        Instance of :class:`TradeGovClient` used to search for entities.
    federalregister_client:
        Instance of :class:`FederalRegisterClient` used to search for
        documents.

    Notes
    -----
    Do not log or expose API keys; rely on secure storage (Windows Credential
    Store).
    """

    def __init__(
        self,
        tradegov_client: "TradeGovClient",
        federalregister_client: "FederalRegisterClient",
    ) -> None:
        self.tradegov_client = tradegov_client
        self.federalregister_client = federalregister_client
        self.logger = logging.getLogger(__name__)

    def run(self, query: str) -> Tuple[List[Dict], List[Dict]]:
        """Fetch entities from Trade.gov and their associated documents.

        Parameters
        ----------
        query:
            Search string used to locate Trade.gov entities.

        Returns
        -------
        tuple[list[dict], list[dict]]
            All entity dictionaries and all related document dictionaries.
        """

        entities: List[Dict] = []
        documents: List[Dict] = []
        self.last_upstream_status: dict[str, dict[str, object]] = {}
        healthy_states = {"ok", "no_results"}

        typed_tradegov = self._tradegov_search_result(query)
        if typed_tradegov is not None:
            entities = list(typed_tradegov["data"])
            self._capture_status_payload(
                "tradegov.search",
                typed_tradegov["status"],
                context={"query": query},
            )
            tradegov_state = str(typed_tradegov["status"].get("state") or "")
            if tradegov_state not in healthy_states:
                return entities, documents
        else:
            try:
                entity_iter = self.tradegov_client.search_entities(query)
            except TradeGovError as exc:
                self.logger.warning("Trade.gov search failed: %s", exc)
                return entities, documents

            try:
                for entity in entity_iter:
                    entities.append(entity)
            except TradeGovError as exc:
                self.logger.warning(
                    "Trade.gov search failed during iteration: %s",
                    exc,
                )
            self._capture_status(
                "tradegov.search",
                self.tradegov_client,
                "search",
                context={"query": query},
            )

        for entity in entities:
            entity_id = entity.get("id")
            typed_fr = self._federalregister_search_result(str(entity_id))
            if typed_fr is not None:
                self._capture_status_payload(
                    "federalregister.search_documents",
                    typed_fr["status"],
                    context={"entity_id": entity_id},
                )
                documents.extend(list(typed_fr["data"]))
                continue
            try:
                docs = self.federalregister_client.search_documents(str(entity_id))
                self._capture_status(
                    "federalregister.search_documents",
                    self.federalregister_client,
                    "search_documents",
                    context={"entity_id": entity_id},
                )
                for doc in docs:
                    documents.append(doc)
            except FederalRegisterError as exc:
                self.logger.warning(
                    "Federal Register search failed for entity %s: %s",
                    entity_id,
                    exc,
                )
        return entities, documents

    def _tradegov_search_result(self, query: str) -> dict[str, object] | None:
        getter = getattr(self.tradegov_client, "search_entities_result", None)
        if not callable(getter):
            return None
        result = getter(query)
        status = getattr(result, "status", None)
        if status is None or not hasattr(status, "as_dict"):
            return None
        return {
            "data": list(getattr(result, "data", []) or []),
            "status": status.as_dict(),
        }

    def _federalregister_search_result(self, entity_id: str) -> dict[str, object] | None:
        getter = getattr(self.federalregister_client, "search_documents_result", None)
        if not callable(getter):
            return None
        result = getter(entity_id)
        status = getattr(result, "status", None)
        if status is None or not hasattr(status, "as_dict"):
            return None
        return {
            "data": list(getattr(result, "data", []) or []),
            "status": status.as_dict(),
        }

    def _capture_status_payload(
        self,
        key: str,
        payload: dict[str, object],
        *,
        context: dict[str, object] | None = None,
    ) -> None:
        if not payload:
            return
        entry = dict(payload)
        if context:
            entry = {**entry, **context}
        self.last_upstream_status[key] = entry
        state = entry.get("state")
        if state not in {"ok", "no_results"}:
            self.logger.warning(
                "Upstream degraded for %s (state=%s): %s",
                key,
                state,
                entry,
            )

    def _capture_status(
        self,
        key: str,
        client: object,
        operation: str,
        *,
        context: dict[str, object] | None = None,
    ) -> None:
        getter = getattr(client, "get_last_status", None)
        if not callable(getter):
            return
        status = getter(operation)
        if status is None:
            return
        payload = status.as_dict() if hasattr(status, "as_dict") else {"state": str(status)}
        self._capture_status_payload(key, payload, context=context)
