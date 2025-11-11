from __future__ import annotations

"""FastAPI Knowledge Graph service for querying and inserting triples.

This module exposes a minimal API in front of a SPARQL endpoint. It supports
safe read-only ``SELECT`` queries and SHACL-validated inserts of Turtle
triples.
"""

import logging
import os
from pathlib import Path
from typing import Any, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from rdflib import Graph
from pydantic import BaseModel
from SPARQLWrapper import JSON, SPARQLWrapper
from SPARQLWrapper.SPARQLExceptions import QueryBadFormed
from pyshacl import validate
from urllib.error import HTTPError, URLError

from .utils import get_secret

# Load SPARQL_ENDPOINT_URL & SHAPES_FILE_PATH from env or
# Windows Credential Store.
# Enforce operation whitelisting to prevent injection.
ENDPOINT_URL = get_secret("SPARQL_ENDPOINT_URL")
SHAPES_FILE_PATH = os.getenv("SHAPES_FILE_PATH")
if not ENDPOINT_URL or not SHAPES_FILE_PATH:
    raise RuntimeError("SPARQL_ENDPOINT_URL and SHAPES_FILE_PATH must be set")

SHAPES_PATH = Path(SHAPES_FILE_PATH)
if not SHAPES_PATH.exists():
    raise RuntimeError(f"SHAPES_FILE_PATH does not exist: {SHAPES_FILE_PATH}")

SHAPES_TTL = SHAPES_PATH.read_text(encoding="utf-8")

logger = logging.getLogger(__name__)

app = FastAPI(title="Knowledge Graph Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    """Request body for the ``/kg/query`` endpoint."""

    sparql: str


class QueryResponse(BaseModel):
    """Response model for query results."""

    results: List[Any]


class InsertRequest(BaseModel):
    """Request body for the ``/kg/insert`` endpoint."""

    ttl: str


class InsertResponse(BaseModel):
    """Response model for triple insertion."""

    inserted: bool


@app.post("/kg/query", response_model=QueryResponse)
def kg_query(body: QueryRequest) -> QueryResponse:
    """Execute a read-only SPARQL ``SELECT`` query.

    Parameters
    ----------
    body:
        The request body containing a SPARQL ``SELECT`` statement.

    Returns
    -------
    QueryResponse
        JSON bindings under the ``results`` key.

    Raises
    ------
    HTTPException
        If the query is not a ``SELECT`` or the endpoint returns an error.
    """

    sparql = body.sparql
    logger.info("Received KG query: %s", sparql.replace("\n", " ")[:200])

    if not sparql.strip().upper().startswith("SELECT"):
        logger.error("Rejected non-SELECT query")
        raise HTTPException(
            status_code=400,
            detail="Only SELECT queries allowed",
        )

    wrapper = SPARQLWrapper(ENDPOINT_URL)
    wrapper.setQuery(sparql)
    wrapper.setReturnFormat(JSON)

    try:
        data = wrapper.query().convert()
    except QueryBadFormed as exc:
        logger.error("Bad SPARQL query: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Invalid SPARQL query",
        ) from exc
    except (HTTPError, URLError) as exc:
        logger.error("SPARQL endpoint error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="SPARQL endpoint error",
        ) from exc
    except Exception as exc:  # pragma: no cover - unexpected
        logger.error("SPARQL request failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="SPARQL endpoint error",
        ) from exc

    bindings = data.get("results", {}).get("bindings", [])
    return QueryResponse(results=bindings)


@app.post("/kg/insert", response_model=InsertResponse)
def kg_insert(body: InsertRequest) -> InsertResponse:
    """Validate and insert Turtle triples into the knowledge graph.

    Parameters
    ----------
    body:
        Request body containing Turtle triples to insert.

    Returns
    -------
    InsertResponse
        ``{"inserted": True}`` on success.

    Raises
    ------
    HTTPException
        If SHACL validation fails or the SPARQL endpoint returns an error.
    """

    ttl = body.ttl
    logger.info("Received KG insert request")

    parsed_graph: Graph | None = None
    try:
        valid, data_graph, text = validate(
            data_graph=ttl,
            shacl_graph=SHAPES_TTL,
            data_graph_format="turtle",
            shacl_graph_format="turtle",
        )
        if isinstance(data_graph, Graph):
            parsed_graph = data_graph
    except Exception as exc:  # pragma: no cover - pyshacl internal error
        logger.error("SHACL validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not valid:
        logger.error("SHACL validation failed: %s", text)
        raise HTTPException(status_code=400, detail=text)

    if parsed_graph is None:
        try:
            parsed_graph = Graph().parse(data=ttl, format="turtle")
        except Exception as exc:
            logger.error("Invalid Turtle payload: %s", exc)
            raise HTTPException(
                status_code=400,
                detail="Invalid Turtle payload",
            ) from exc

    serialized = parsed_graph.serialize(format="nt")
    if isinstance(serialized, bytes):
        serialized = serialized.decode("utf-8")

    wrapper = SPARQLWrapper(ENDPOINT_URL)
    wrapper.setMethod("POST")
    wrapper.setQuery(f"INSERT DATA {{\n{serialized}\n}}")

    try:
        wrapper.query()
    except (HTTPError, URLError) as exc:
        logger.error("SPARQL update error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="SPARQL endpoint error",
        ) from exc
    except Exception as exc:  # pragma: no cover - unexpected
        logger.error("SPARQL update failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="SPARQL endpoint error",
        ) from exc

    return InsertResponse(inserted=True)


@app.get("/health")
def health() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok"}
