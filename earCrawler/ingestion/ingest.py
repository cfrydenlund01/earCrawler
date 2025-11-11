from __future__ import annotations

"""ETL ingestion module for loading Trade.gov and Federal Register data."""

import os
from pathlib import WindowsPath, Path
import logging
import subprocess
from typing import Any

from rdflib import Graph, URIRef, Literal
from pyshacl import validate
try:
    from pyshacl.errors import SHACLValidationError
except Exception:  # pragma: no cover - fallback for pyshacl versions
    class SHACLValidationError(Exception):
        """Fallback SHACL validation error."""

from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient
from earCrawler.utils.jena_tools import find_tdbloader


class Ingestor:
    """Run the ETL pipeline to ingest EAR data.

    Parameters
    ----------
    tradegov_client:
        Client used to fetch entities from Trade.gov.
    fedreg_client:
        Client used to fetch documents from the Federal Register.
    tdb_location:
        Location of the Jena TDB2 dataset.

    Notes
    -----
    Load SHACL shapes and Jena TDB2 path via secure config; do not hard-code
    paths in source.
    """

    def __init__(self, tradegov_client: TradeGovClient, fedreg_client: FederalRegisterClient, tdb_location: WindowsPath) -> None:
        self.tradegov_client = tradegov_client
        self.fedreg_client = fedreg_client
        self.tdb_location = tdb_location
        self.logger = logging.getLogger(__name__)
        # Load SHACL shapes path from secure config; do not hard-code in source.
        self.shapes_path = Path(__file__).resolve().parents[1] / "ontology" / "shapes.ttl"

    def map_entity_to_triples(self, entity: dict[str, Any]) -> Graph:
        """Map an entity JSON dictionary to RDF triples.

        Parameters
        ----------
        entity:
            Parsed JSON from Trade.gov.

        Returns
        -------
        rdflib.Graph
            Graph containing triples for the entity.

        Notes
        -----
        This is a placeholder mapping. Extend with proper EAR ontology terms.
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
        """Execute the ETL pipeline for ``query``.

        Steps:
            1. Fetch entities and documents from the APIs.
            2. Map JSON records to RDF triples.
            3. Validate the generated graph using SHACL.
            4. Load the validated TTL file into Jena TDB2.
        """
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
