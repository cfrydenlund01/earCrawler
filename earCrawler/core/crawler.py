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

        try:
            entity_iter = self.tradegov_client.search_entities(query)
        except TradeGovError as exc:
            self.logger.warning("Trade.gov search failed: %s", exc)
            return entities, documents

        try:
            for entity in entity_iter:
                entities.append(entity)
                entity_id = entity.get("id")
                try:
                    for doc in self.federalregister_client.search_documents(
                        str(entity_id)
                    ):
                        documents.append(doc)
                except FederalRegisterError as exc:
                    self.logger.warning(
                        "Federal Register search failed for entity %s: %s",
                        entity_id,
                        exc,
                    )
        except TradeGovError as exc:
            self.logger.warning(
                "Trade.gov search failed during iteration: %s",
                exc,
            )

        return entities, documents
