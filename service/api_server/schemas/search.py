from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional


class SearchHit(BaseModel):
    id: str = Field(..., description="Matched entity IRI")
    label: Optional[str] = Field(default=None, description="Best effort label")
    score: float = Field(..., description="Normalized score between 0 and 1")
    snippet: Optional[str] = Field(default=None)


class SearchResponse(BaseModel):
    total: int = Field(..., description="Total matches truncated to limit")
    results: List[SearchHit]
