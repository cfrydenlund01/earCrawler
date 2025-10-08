from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request

from ..fuseki import FusekiGateway
from ..schemas import EntityAttribute, EntityView, ProblemDetails
from .dependencies import get_gateway, rate_limit

router = APIRouter(prefix="/v1", tags=["entities"])


@router.get("/entities/{entity_id}", response_model=EntityView, responses={404: {"model": ProblemDetails}})
async def get_entity(
    entity_id: str,
    request: Request,
    gateway: FusekiGateway = Depends(get_gateway),
    _: None = Depends(rate_limit("entities")),
) -> EntityView:
    rows = await gateway.select("entity_by_id", {"id": entity_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Entity not found")
    labels: list[str] = []
    types: set[str] = set()
    same_as: set[str] = set()
    attributes_map: dict[str, set[str]] = defaultdict(set)
    description: str | None = None
    for row in rows:
        label = row.get("label")
        if isinstance(label, str) and label not in labels:
            labels.append(label)
        if isinstance(row.get("type"), str):
            types.add(row["type"])
        if isinstance(row.get("sameAs"), str):
            same_as.add(row["sameAs"])
        desc = row.get("description")
        if isinstance(desc, str):
            description = desc
        predicate = row.get("attribute")
        obj = row.get("value")
        if isinstance(predicate, str) and isinstance(obj, str):
            attributes_map[predicate].add(obj)
    attributes = [EntityAttribute(predicate=pred, value=val) for pred, values in attributes_map.items() for val in sorted(values)]
    return EntityView(
        id=entity_id,
        labels=labels,
        description=description,
        types=sorted(types),
        same_as=sorted(same_as),
        attributes=sorted(attributes, key=lambda attr: (attr.predicate, attr.value)),
    )
