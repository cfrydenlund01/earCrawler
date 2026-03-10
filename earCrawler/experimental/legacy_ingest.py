from __future__ import annotations

"""Quarantined legacy ETL ingestion pipeline.

This module is intentionally outside the supported runtime surface. Supported
operator flows use ``earctl`` and ``service/api_server`` as documented in
``README.md`` and ``RUNBOOK.md``.
"""

import logging
import os
from pathlib import Path, WindowsPath
import subprocess
from typing import Any

from rdflib import Graph, Literal, URIRef
from pyshacl import validate

try:
    from pyshacl.errors import SHACLValidationError
except Exception:  # pragma: no cover - fallback for pyshacl versions

    class SHACLValidationError(Exception):
        """Fallback SHACL validation error."""


from api_clients.federalregister_client import FederalRegisterClient
from api_clients.tradegov_client import TradeGovClient
from earCrawler.utils.jena_tools import find_tdbloader


class Ingestor:
    """Run the legacy ETL pipeline to ingest EAR data."""

    def __init__(
        self,
        tradegov_client: TradeGovClient,
        fedreg_client: FederalRegisterClient,
        tdb_location: WindowsPath,
    ) -> None:
        self.tradegov_client = tradegov_client
        self.fedreg_client = fedreg_client
        self.tdb_location = tdb_location
        self.logger = logging.getLogger(__name__)
        self.shapes_path = (
            Path(__file__).resolve().parents[1] / "ontology" / "shapes.ttl"
        )

    def map_entity_to_triples(self, entity: dict[str, Any]) -> Graph:
        """Map an entity JSON dictionary to RDF triples.

        Notes
        -----
        This is a placeholder mapping kept only for quarantined legacy tests.
        """
        g = Graph()
        subject = URIRef(f"urn:entity:{entity.get('id')}")
        g.add((subject, URIRef("urn:prop:id"), Literal(str(entity.get("id")))))
        return g

    def map_document_to_triples(self, document: dict[str, Any]) -> Graph:
        """Map a document JSON dictionary to RDF triples."""
        g = Graph()
        subject = URIRef(f"urn:doc:{document.get('id')}")
        g.add((subject, URIRef("urn:prop:id"), Literal(str(document.get("id")))))
        return g

    def run(self, query: str) -> None:
        """Execute the legacy ETL pipeline for ``query``."""
        graph = Graph()

        try:
            for entity in self.tradegov_client.search_entities(query):
                graph += self.map_entity_to_triples(entity)
                entity_id = str(entity.get("id"))
                for doc in self.fedreg_client.search_documents(entity_id):
                    graph += self.map_document_to_triples(doc)
        except Exception as exc:
            self.logger.warning("Data fetch failed: %s", exc)
            return

        ttl_path = Path("generated-triples.ttl")
        graph.serialize(destination=ttl_path, format="turtle")

        try:
            shapes_graph = Graph().parse(self.shapes_path)
            conforms, _, report = validate(
                data_graph=graph,
                shacl_graph=shapes_graph,
                inference="rdfs",
                serialize_report_graph=True,
            )
            if not conforms:
                self.logger.warning("SHACL validation failed: %s", report)
                return
        except SHACLValidationError as exc:
            self.logger.warning("SHACL validation error: %s", exc)
            return

        try:
            env_loader = os.getenv("EAR_TDBLOADER_PATH")
            if env_loader:
                loader = Path(env_loader)
            elif os.getenv("EAR_DISABLE_JENA_BOOTSTRAP") == "1":
                loader = Path("tdb2.tdbloader")
            else:
                loader = find_tdbloader()
            subprocess.run(
                [
                    str(loader),
                    "--loc",
                    str(self.tdb_location),
                    str(ttl_path),
                ],
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            self.logger.warning("Jena load failed: %s", exc)
            return

        self.logger.info("Ingestion completed")

