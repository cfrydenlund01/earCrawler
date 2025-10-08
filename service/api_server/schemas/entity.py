from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional


class EntityAttribute(BaseModel):
    predicate: str = Field(..., description="Predicate IRI")
    value: str = Field(..., description="Object value as a compact string")


class EntityView(BaseModel):
    id: str = Field(..., description="Entity IRI")
    labels: List[str] = Field(default_factory=list)
    description: Optional[str] = Field(default=None)
    types: List[str] = Field(default_factory=list, description="rdf:type IRIs")
    same_as: List[str] = Field(default_factory=list, description="Equivalent IRIs")
    attributes: List[EntityAttribute] = Field(default_factory=list)
