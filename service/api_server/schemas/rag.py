from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from .lineage import LineageEdge


class RagQueryRequest(BaseModel):
    query: str = Field(
        ..., min_length=1, max_length=512, description="Natural language question"
    )
    top_k: int = Field(3, ge=1, le=10, description="Maximum candidate passages")
    include_lineage: bool = Field(
        False, description="Return KG lineage data when available"
    )

    def cache_key(self) -> str:
        lineage_flag = "1" if self.include_lineage else "0"
        return f"{self.query.strip()}::{self.top_k}::{lineage_flag}"


class RagSource(BaseModel):
    id: Optional[str] = Field(
        default=None, description="Source identifier (section/entity)"
    )
    url: Optional[str] = Field(default=None, description="Canonical URL")
    label: Optional[str] = Field(default=None, description="Display title or citation")
    section: Optional[str] = Field(
        default=None, description="Regulatory section or part"
    )
    provider: Optional[str] = Field(
        default=None, description="Upstream provider (e.g., federalregister.gov)"
    )


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


class OutputError(BaseModel):
    code: str = Field(..., description="Stable error code for client handling")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(
        default=None, description="Optional key-level metadata (e.g., offending key)"
    )
    raw_preview: Optional[str] = Field(
        default=None, description="Truncated raw LLM output for debugging"
    )
    raw_len: Optional[int] = Field(
        default=None, description="Length of the raw LLM output"
    )


class RagCitation(BaseModel):
    section_id: str = Field(..., description="Section/citation identifier (e.g., EAR-740.1)")
    quote: str = Field(..., description="Verbatim quote that must be a substring of the retrieved contexts")
    span_id: Optional[str] = Field(
        default=None, description="Optional doc/span identifier for auditability"
    )


class EvidenceOkay(BaseModel):
    ok: bool = Field(..., description="True when the response is grounded and follows the contract")
    reasons: List[str] = Field(default_factory=list, description="Machine-readable reasons for ok/failed checks")


class RagResponse(BaseModel):
    trace_id: str = Field(..., description="Trace identifier for correlating logs")
    latency_ms: float = Field(..., description="Measured latency for the request")
    query: str
    cache: CacheState
    results: List[RagAnswer]
    retrieval_empty: bool = Field(
        default=False, description="True when retrieval returned zero hits"
    )
    retrieval_empty_reason: Optional[str] = Field(
        default=None,
        description="Reason for an empty retrieval result (no_hits, retriever_error, retriever_disabled)",
    )


class RetrievedDocument(BaseModel):
    id: Optional[str] = Field(default=None, description="Source identifier")
    score: Optional[float] = Field(default=None, description="Retriever score")
    title: Optional[str] = Field(default=None, description="Document title")
    url: Optional[str] = Field(default=None, description="Canonical URL")
    section: Optional[str] = Field(default=None, description="Section/citation")
    provider: Optional[str] = Field(default=None, description="Upstream provider")


class RagGeneratedResponse(BaseModel):
    trace_id: str = Field(..., description="Trace identifier for correlating logs")
    latency_ms: float = Field(..., description="Measured latency for the request")
    question: str = Field(..., description="Original user query")
    answer: Optional[str] = Field(
        default=None, description="Generated answer from the configured remote LLM provider"
    )
    contexts: List[str] = Field(
        default_factory=list,
        description="Plain-text contexts passed to the LLM",
    )
    retrieved: List[RetrievedDocument] = Field(
        default_factory=list,
        description="Raw retrieval metadata for transparency",
    )
    model: Optional[str] = Field(
        default=None, description="Model identifier used for generation"
    )
    provider: Optional[str] = Field(
        default=None, description="Remote LLM provider used for generation"
    )
    rag_enabled: bool = Field(
        ...,
        description="True when FAISS/SentenceTransformers RAG is enabled",
    )
    llm_enabled: bool = Field(
        ...,
        description="True when remote LLM generation is enabled and configured",
    )
    disabled_reason: Optional[str] = Field(
        default=None,
        description="Reason when rag_enabled or llm_enabled are false",
    )
    cache: CacheState
    retrieval_empty: bool = Field(
        default=False, description="True when retrieval returned zero hits"
    )
    retrieval_empty_reason: Optional[str] = Field(
        default=None,
        description="Reason for an empty retrieval result (no_hits, retriever_error, retriever_disabled)",
    )
    output_ok: bool = Field(
        default=True, description="True when LLM output matched the strict JSON schema"
    )
    output_error: Optional[OutputError] = Field(
        default=None,
        description="Structured schema or provider error when output_ok is false",
    )
    raw_answer: Optional[str] = Field(
        default=None, description="Raw LLM response prior to parsing/validation"
    )
    label: Optional[str] = Field(
        default=None, description="Structured label parsed from the LLM output"
    )
    justification: Optional[str] = Field(
        default=None, description="Structured justification parsed from the LLM output"
    )
    citations: List[RagCitation] = Field(
        default_factory=list, description="Machine-checkable citations with verbatim quotes"
    )
    evidence_okay: Optional[EvidenceOkay] = Field(
        default=None, description="Model-provided evidence self-check for auditability"
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="Explicit assumptions; non-empty assumptions generally require label=unanswerable unless supported",
    )
