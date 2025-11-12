from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..fuseki import FusekiGateway
from ..schemas import ProblemDetails, SparqlProxyRequest, SparqlProxyResponse
from ..templates import TemplateRegistry
from .dependencies import get_gateway, rate_limit

router = APIRouter(prefix="/v1", tags=["sparql"])


@router.post(
    "/sparql",
    response_model=SparqlProxyResponse,
    responses={400: {"model": ProblemDetails}},
)
async def sparql_proxy(
    payload: SparqlProxyRequest,
    request: Request,
    gateway: FusekiGateway = Depends(get_gateway),
    _: None = Depends(rate_limit("sparql")),
) -> SparqlProxyResponse:
    registry: TemplateRegistry = request.app.state.registry
    allowed = registry.filter_by_allow_in("sparql")
    if payload.template not in allowed:
        raise HTTPException(status_code=400, detail="Template not permitted")
    try:
        raw = await gateway.select_as_raw(payload.template, payload.parameters)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if "head" not in raw or "results" not in raw:
        raise HTTPException(
            status_code=502, detail="Unexpected response from SPARQL endpoint"
        )
    return SparqlProxyResponse(head=raw.get("head", {}), results=raw.get("results", {}))
