from __future__ import annotations

"""Route and exception-handler wiring helpers for API startup."""

import html
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from .schemas import ProblemDetails

_DOCS_PATH = Path(__file__).resolve().parent.parent / "docs" / "index.md"
_OPENAPI_PATH = Path(__file__).resolve().parent.parent / "openapi" / "openapi.yaml"


def register_docs_routes(app: FastAPI) -> None:
    """Register static docs and OpenAPI YAML routes."""

    @app.get("/docs", include_in_schema=False)
    async def docs() -> Response:
        body = _DOCS_PATH.read_text(encoding="utf-8")
        return Response(
            content=f"<html><body><pre>{html.escape(body)}</pre></body></html>",
            media_type="text/html",
        )

    @app.get("/openapi.yaml", include_in_schema=False)
    async def openapi_spec() -> Response:
        return Response(
            content=_OPENAPI_PATH.read_text(encoding="utf-8"),
            media_type="application/yaml",
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Register API error responses as ProblemDetails payloads."""

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", "")
        detail = exc.errors()
        problem = ProblemDetails(
            type="https://earcrawler.gov/problems/validation",
            title="Validation Failed",
            status=422,
            detail=str(detail),
            instance=str(request.url),
            trace_id=trace_id,
        )
        return JSONResponse(
            status_code=422, content=problem.model_dump(exclude_none=True)
        )

    @app.exception_handler(HTTPException)
    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", "")
        problem = ProblemDetails(
            type="https://earcrawler.gov/problems/http",
            title=exc.detail if isinstance(exc.detail, str) else "HTTP Error",
            status=exc.status_code,
            detail=exc.detail if isinstance(exc.detail, str) else None,
            instance=str(request.url),
            trace_id=trace_id,
        )
        headers = {}
        if exc.headers:
            headers.update(exc.headers)
        return JSONResponse(
            status_code=exc.status_code,
            content=problem.model_dump(exclude_none=True),
            headers=headers,
        )
