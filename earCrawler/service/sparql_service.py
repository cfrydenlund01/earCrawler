from __future__ import annotations

"""FastAPI service for executing SPARQL SELECT queries."""

import logging
from typing import Any, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from SPARQLWrapper import JSON, SPARQLWrapper
from SPARQLWrapper.SPARQLExceptions import QueryBadFormed
from urllib.error import HTTPError, URLError

from .utils import get_secret

logger = logging.getLogger(__name__)

ENDPOINT_URL = get_secret("SPARQL_ENDPOINT_URL")
if not ENDPOINT_URL:
    raise RuntimeError("SPARQL_ENDPOINT_URL not configured")

app = FastAPI(title="SPARQL Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryResponse(BaseModel):
    """Response model for SPARQL results."""

    results: List[Any]


@app.get("/query", response_model=QueryResponse)
def run_query(
    sparql: str = Query(..., description="SPARQL SELECT query"),
) -> QueryResponse:
    """Execute ``sparql`` against the configured endpoint.

    Validate SPARQL input to prevent injection; restrict to SELECT only.
    """
    logger.info("Received SPARQL query: %s", sparql.replace("\n", " ")[:200])

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
    except Exception as exc:  # pragma: no cover - unexpected
        logger.error("SPARQL request failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="SPARQL endpoint error",
        ) from exc

    bindings = data.get("results", {}).get("bindings", [])
    return QueryResponse(results=bindings)


@app.get("/health")
def health() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok"}
