from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Dict, Any


class SparqlProxyRequest(BaseModel):
    template: str = Field(..., description="Template identifier from registry")
    parameters: Dict[str, Any] = Field(default_factory=dict)


class SparqlProxyResponse(BaseModel):
    head: Dict[str, Any]
    results: Dict[str, Any]
