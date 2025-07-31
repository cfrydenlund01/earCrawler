from __future__ import annotations

"""FastAPI Knowledge Graph service for SPARQL queries and inserts."""

import logging
import os
from pathlib import Path
from typing import Any, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from SPARQLWrapper import SPARQLWrapper, JSON, POST
from SPARQLWrapper.SPARQLExceptions import QueryBadFormed
from urllib.error import HTTPError, URLError
from rdflib import Graph
from pyshacl import validate

logger = logging.getLogger(__name__)

# Load SPARQL_ENDPOINT_URL & SHAPES_FILE_PATH from env or credential store.
ENDPOINT_URL = os.getenv("SPARQL_ENDPOINT_URL")
SHAPES_PATH = os.getenv("SHAPES_FILE_PATH")
if not ENDPOINT_URL:
    raise RuntimeError("SPARQL_ENDPOINT_URL environment variable not set")
if not SHAPES_PATH:
    raise RuntimeError("SHAPES_FILE_PATH environment variable not set")

app = FastAPI(title="Knowledge Graph Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    """Input model for SPARQL SELECT queries."""

    sparql: str


class QueryResults(BaseModel):
    """Output model for SPARQL query results."""

    results: List[Any]


class InsertRequest(BaseModel):
    """Input model for inserting Turtle triples."""

    ttl: str


class InsertResponse(BaseModel):
    """Output model after successful insert."""

    inserted: bool


@app.post("/kg/query", response_model=QueryResults)
def run_query(payload: QueryRequest) -> QueryResults:
    """Execute a safe SPARQL SELECT query against the endpoint."""
    sparql = payload.sparql
    logger.info("/kg/query: %s", sparql.replace("\n", " ")[:200])

    if not sparql.strip().upper().startswith("SELECT"):
        logger.error("Rejected non-SELECT query")
        raise HTTPException(
            status_code=400,
            detail="Only SELECT queries are allowed",
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
    except Exception as exc:  # pragma: no cover
        logger.error("SPARQL request failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="SPARQL endpoint error",
        ) from exc

    bindings = data.get("results", {}).get("bindings", [])
    return QueryResults(results=bindings)


@app.post("/kg/insert", response_model=InsertResponse)
def insert_triples(payload: InsertRequest) -> InsertResponse:
    """Validate and insert TTL triples into the knowledge graph."""
    ttl = payload.ttl
    logger.info("/kg/insert received %d chars", len(ttl))

    try:
        data_graph = Graph().parse(data=ttl, format="turtle")
    except Exception as exc:
        logger.error("Turtle parse error: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Invalid Turtle data",
        ) from exc

    shapes_path = Path(SHAPES_PATH).resolve()
    try:
        shapes_graph = Graph().parse(shapes_path)
        conforms, _r, report = validate(
            data_graph=data_graph,
            shacl_graph=shapes_graph,
            inference="rdfs",
            serialize_report_graph=True,
        )
    except Exception as exc:
        logger.error("SHACL validation error: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if not conforms:
        logger.error("SHACL validation failed: %s", report)
        raise HTTPException(
            status_code=400,
            detail=str(report),
        )

    update_query = f"INSERT DATA {{\n{ttl}\n}}"
    wrapper = SPARQLWrapper(ENDPOINT_URL)
    wrapper.setMethod(POST)
    wrapper.setQuery(update_query)

    try:
        wrapper.query()  # SPARQLWrapper returns a Response like object
    except (HTTPError, URLError) as exc:
        logger.error("SPARQL endpoint error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="SPARQL endpoint error",
        ) from exc
    except Exception as exc:  # pragma: no cover
        logger.error("SPARQL update failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="SPARQL endpoint error",
        ) from exc

    return InsertResponse(inserted=True)

# Enforce operation whitelisting to prevent injection.
