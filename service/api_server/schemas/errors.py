from __future__ import annotations

"""Shared error schema definitions."""

from pydantic import BaseModel


class ProblemDetails(BaseModel):
    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    trace_id: str | None = None
