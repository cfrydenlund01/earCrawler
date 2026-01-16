from __future__ import annotations

"""Helpers for wiring the Mistral QLoRA agent into the API facade."""

import logging
import os
from dataclasses import dataclass
from typing import Optional

from earCrawler.agent.retrieval_adapter import TextContextRetriever
from .rag_support import RetrieverProtocol, NullRetriever

logger = logging.getLogger(__name__)


@dataclass
class MistralAgentResult:
    answer: Optional[str]
    contexts: list[str]
    documents: list[dict]
    error: Optional[str] = None


class MistralService:
    """Thin wrapper around the QLoRA Mistral agent with defensive loading."""

    def __init__(
        self,
        retriever: RetrieverProtocol,
        *,
        agent: object | None = None,
        adapter: TextContextRetriever | None = None,
    ) -> None:
        self.enabled = os.getenv("EARCRAWLER_API_ENABLE_MISTRAL", "0") == "1"
        self.disabled_reason: Optional[str] = None
        self.model_label: Optional[str] = None
        self.adapter: Optional[TextContextRetriever] = None
        self.agent: Optional[object] = None
        self._retriever = retriever

        if not self.enabled:
            self.disabled_reason = (
                "Mistral agent disabled; set EARCRAWLER_API_ENABLE_MISTRAL=1 to enable"
            )
            return

        if isinstance(retriever, NullRetriever):
            self.enabled = False
            self.disabled_reason = (
                "RAG retriever disabled; set EARCRAWLER_API_ENABLE_RAG=1 to enable"
            )
            return

        if agent is not None and adapter is not None:
            self.agent = agent
            self.adapter = adapter
            self.model_label = getattr(agent, "model_name", None) or "custom"
            return

        try:
            from earCrawler.agent.mistral_agent import (
                Agent,
                DEFAULT_MODEL,
                load_mistral_with_lora,
            )
        except Exception as exc:  # pragma: no cover - import errors handled gracefully
            logger.warning("Failed to import Mistral agent components: %s", exc)
            self.enabled = False
            self.disabled_reason = f"import failed: {exc}"
            return

        model_name = os.getenv("EARCRAWLER_MISTRAL_MODEL", DEFAULT_MODEL)
        use_4bit = os.getenv("EARCRAWLER_MISTRAL_USE_4BIT", "1") != "0"
        try:
            tokenizer, model = load_mistral_with_lora(
                model_name=model_name, use_4bit=use_4bit
            )
            adapter = TextContextRetriever(retriever)
            self.agent = Agent(retriever=adapter, model=model, tokenizer=tokenizer)
            self.adapter = adapter
            adapter_label = "QLoRA"
            quant_label = "4-bit" if use_4bit else "full precision"
            self.model_label = f"{model_name} ({adapter_label}, {quant_label})"
        except Exception as exc:  # pragma: no cover - heavy deps may fail
            logger.warning("Failed to initialize Mistral agent: %s", exc)
            self.enabled = False
            self.disabled_reason = f"initialization failed: {exc}"

    def generate(
        self, query: str, *, k: int, documents: list[dict] | None = None
    ) -> MistralAgentResult:
        if not self.enabled or self.agent is None:
            return MistralAgentResult(
                answer=None,
                contexts=[],
                documents=list(documents or []),
                error=self.disabled_reason,
            )

        if self.adapter is None:
            return MistralAgentResult(
                answer=None,
                contexts=[],
                documents=list(documents or []),
                error="adapter unavailable",
            )

        contexts = (
            self.adapter.select_contexts(documents or [])
            if documents is not None
            else None
        )

        try:
            answer, used_contexts = self.agent.answer_with_contexts(
                query, k=k, contexts=contexts
            )
        except Exception as exc:  # pragma: no cover - runtime failures
            logger.warning("Mistral generation failed: %s", exc)
            return MistralAgentResult(
                answer=None,
                contexts=list(contexts or []),
                documents=list(documents or []),
                error=str(exc),
            )

        final_contexts = list(used_contexts or [])
        final_documents = (
            list(documents or [])
            if documents is not None
            else self.adapter.last_documents
        )
        return MistralAgentResult(
            answer=answer,
            contexts=final_contexts,
            documents=final_documents,
            error=None,
        )


def load_mistral_service(retriever: RetrieverProtocol) -> MistralService:
    """Factory that defers heavy model loading behind an env guard."""

    return MistralService(retriever)


__all__ = ["MistralService", "MistralAgentResult", "load_mistral_service"]
