from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..fuseki import FusekiGateway
from ..schemas import LineageEdge, LineageResponse, ProblemDetails
from .dependencies import get_gateway, rate_limit

router = APIRouter(prefix="/v1", tags=["lineage"])


@router.get(
    "/lineage/{entity_id}",
    response_model=LineageResponse,
    responses={404: {"model": ProblemDetails}},
)
async def lineage(
    entity_id: str,
    gateway: FusekiGateway = Depends(get_gateway),
    _: None = Depends(rate_limit("lineage")),
) -> LineageResponse:
    rows = await gateway.select("lineage_by_id", {"id": entity_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Lineage unavailable")
    edges: list[LineageEdge] = []
    for row in rows:
        src = row.get("source") or entity_id
        tgt = row.get("target")
        relation = row.get("relation")
        if not (isinstance(tgt, str) and isinstance(relation, str)):
            continue
        timestamp = None
        ts_value = row.get("timestamp")
        if isinstance(ts_value, dict) and "value" in ts_value:
            timestamp = ts_value["value"]
        elif isinstance(ts_value, str):
            timestamp = ts_value
        edges.append(
            LineageEdge(
                source=str(src), target=tgt, relation=relation, timestamp=timestamp
            )
        )
    return LineageResponse(id=entity_id, edges=edges)
