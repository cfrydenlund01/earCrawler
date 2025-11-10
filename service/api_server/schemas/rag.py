from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from .lineage import LineageEdge


class RagQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512, description="Natural language question")
    top_k: int = Field(3, ge=1, le=10, description="Maximum candidate passages")
    include_lineage: bool = Field(False, description="Return KG lineage data when available")

    def cache_key(self) -> str:
        lineage_flag = "1" if self.include_lineage else "0"
        return f"{self.query.strip()}::{self.top_k}::{lineage_flag}"


class RagSource(BaseModel):
    id: Optional[str] = Field(default=None, description="Source identifier (section/entity)")
    url: Optional[str] = Field(default=None, description="Canonical URL")
    label: Optional[str] = Field(default=None, description="Display title or citation")
    section: Optional[str] = Field(default=None, description="Regulatory section or part")
    provider: Optional[str] = Field(default=None, description="Upstream provider (e.g., federalregister.gov)")


class RagLineageReference(BaseModel):
    entity_id: str = Field(..., description="KG entity used to collect lineage edges")
    edges: List[LineageEdge]


class RagAnswer(BaseModel):
    content: str = Field(..., description="Extracted passage or paragraph text")
    score: float = Field(..., description="Retriever score normalized to 0-1 range")
    source: RagSource
    lineage: Optional[RagLineageReference] = None


class CacheState(BaseModel):
    hit: bool
    expires_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the cached response will be invalidated",
    )


class RagResponse(BaseModel):
    trace_id: str = Field(..., description="Trace identifier for correlating logs")
    latency_ms: float = Field(..., description="Measured latency for the request")
    query: str
    cache: CacheState
    results: List[RagAnswer]
