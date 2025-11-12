from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..fuseki import FusekiGateway
from ..schemas import ProblemDetails, SearchHit, SearchResponse
from .dependencies import get_gateway, rate_limit

router = APIRouter(prefix="/v1", tags=["search"])


@router.get(
    "/search", response_model=SearchResponse, responses={429: {"model": ProblemDetails}}
)
async def search(
    q: str = Query(..., min_length=1, max_length=128, description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0, le=1000),
    gateway: FusekiGateway = Depends(get_gateway),
    _: None = Depends(rate_limit("search")),
) -> SearchResponse:
    rows = await gateway.select(
        "search_entities", {"q": q, "limit": limit, "offset": offset}
    )
    hits: list[SearchHit] = []
    for row in rows:
        score_raw = row.get("score")
        score = float(score_raw) if isinstance(score_raw, (int, float, str)) else 0.0
        hits.append(
            SearchHit(
                id=str(row.get("entity")),
                label=row.get("label") if isinstance(row.get("label"), str) else None,
                score=round(score, 4),
                snippet=(
                    row.get("snippet") if isinstance(row.get("snippet"), str) else None
                ),
            )
        )
    return SearchResponse(total=len(hits), results=hits)
