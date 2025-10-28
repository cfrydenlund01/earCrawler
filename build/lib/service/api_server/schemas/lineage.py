from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional


class LineageEdge(BaseModel):
    source: str = Field(..., description="Subject entity IRI")
    target: str = Field(..., description="Object entity IRI")
    relation: str = Field(..., description="Predicate IRI")
    timestamp: Optional[str] = Field(default=None, description="prov:atTime literal if present")


class LineageResponse(BaseModel):
    id: str = Field(..., description="Root entity IRI")
    edges: List[LineageEdge] = Field(default_factory=list)
