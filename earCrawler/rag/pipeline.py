from __future__ import annotations

"""Thin RAG pipeline wrapper that reuses the existing FAISS retriever and LLM client."""

import re
from typing import Iterable, List, Mapping

from api_clients.llm_client import LLMProviderError, generate_chat
from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient
from pathlib import Path
import os
from earCrawler.rag.output_schema import (
    DEFAULT_ALLOWED_LABELS,
    TRUTHINESS_LABELS,
    OutputSchemaError,
    parse_strict_answer_json,
)
from earCrawler.utils.log_json import JsonLogger

_logger = JsonLogger("rag-pipeline")


def _warn_from_exc(exc: BaseException) -> dict[str, object]:
    """Normalize retriever errors into a stable warning payload."""

    code = getattr(exc, "code", "retriever_error")
    metadata = getattr(exc, "metadata", {}) or {}
    return {
        "code": code,
        "message": str(exc),
        "metadata": dict(metadata),
    }


def _ensure_retriever(
    retriever: object | None = None,
    *,
    strict: bool = True,
    warnings: list[dict[str, object]] | None = None,
):
    if retriever is not None:
        return retriever
    try:
        from earCrawler.rag.retriever import (  # lazy import
            Retriever,
            RetrieverError,
            describe_retriever_config,
        )
    except Exception as exc:  # pragma: no cover - optional deps
        _logger.error("rag.retriever.import_failed", error=str(exc))
        if strict:
            raise
        if warnings is not None:
            warnings.append(_warn_from_exc(exc))
        return None
    try:
        index_override = os.getenv("EARCRAWLER_FAISS_INDEX")
        model_override = os.getenv("EARCRAWLER_FAISS_MODEL")
        index_path = (
            Path(index_override)
            if index_override
            else Path("data") / "faiss" / "index.faiss"
        )
        model_name = model_override or "all-MiniLM-L12-v2"
        retriever_obj = Retriever(
            TradeGovClient(),
            FederalRegisterClient(),
            model_name=model_name,
            index_path=index_path,
        )
        _logger.info(
            "rag.retriever.ready",
            details={"retriever": describe_retriever_config(retriever_obj)},
        )
        return retriever_obj
    except RetrieverError as exc:
        _logger.error(
            "rag.retriever.init_failed",
            details={"retriever_error": _warn_from_exc(exc)},
        )
        if strict:
            raise
        if warnings is not None:
            warnings.append(_warn_from_exc(exc))
        return None
    except Exception as exc:  # pragma: no cover - runtime failures
        _logger.error("rag.retriever.init_failed", error=str(exc))
        if strict:
            raise
        if warnings is not None:
            warnings.append(_warn_from_exc(exc))
        return None


def _extract_text(doc: Mapping[str, object]) -> str:
    for key in ("text", "body", "content", "paragraph", "summary", "snippet", "title"):
        val = doc.get(key)
        if val:
            return str(val).strip()
    return ""


_EAR_SECTION_RE = re.compile(
    r"^(?:15\s*CFR\s*)?(?P<section>\d{3}(?:\.\S+)?)$",
    re.IGNORECASE,
)


def _normalize_section_id(value: object | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.upper().startswith("EAR-"):
        # Allow doc_id-style values that carry a stable suffix (for example
        # "EAR-736.2(b)#...") while keeping citation ids canonical.
        if "#" in raw:
            raw = raw.split("#", 1)[0].strip()
        return raw
    match = _EAR_SECTION_RE.match(raw)
    if match:
        return f"EAR-{match.group('section')}"
    return raw


def retrieve_regulation_context(
    query: str,
    top_k: int = 5,
    *,
    retriever: object | None = None,
    strict: bool = True,
    warnings: list[dict[str, object]] | None = None,
) -> list[dict]:
    """Return top-k regulation snippets using the existing FAISS-backed retriever."""

    warning_list = warnings if warnings is not None else []
    try:
        from earCrawler.rag.retriever import RetrieverError
    except Exception:
        RetrieverError = Exception  # type: ignore[assignment]

    try:
        r = _ensure_retriever(retriever, strict=strict, warnings=warning_list)
    except RetrieverError as exc:
        _logger.error(
            "rag.retriever.unavailable", details={"retriever_error": _warn_from_exc(exc)}
        )
        if strict:
            raise
        warning_list.append(_warn_from_exc(exc))
        return []
    except Exception as exc:  # pragma: no cover - defensive
        _logger.error("rag.retriever.unavailable", error=str(exc))
        if strict:
            raise
        warning_list.append(_warn_from_exc(exc))
        return []

    if r is None:
        return []
    try:
        docs = r.query(query, k=top_k)
    except RetrieverError as exc:
        _logger.error(
            "rag.retrieval.failed", details={"retriever_error": _warn_from_exc(exc)}
        )
        if strict:
            raise
        warning_list.append(_warn_from_exc(exc))
        return []
    except Exception as exc:  # pragma: no cover - defensive
        _logger.error("rag.retrieval.failed", error=str(exc))
        if strict:
            raise
        warning_list.append(_warn_from_exc(exc))
        return []
    results: list[dict] = []
    for doc in docs:
        text = _extract_text(doc)
        if not text:
            continue
        section_id = _normalize_section_id(
            doc.get("section_id")
            or doc.get("section")
            or doc.get("doc_id")
            or doc.get("id")
            or doc.get("entity_id")
            or ""
        )
        results.append(
            {
                "section_id": section_id,
                "text": text,
                "score": doc.get("score"),
                "raw": doc,
            }
        )
    return results


def expand_with_kg(section_ids: Iterable[str]) -> list[dict]:
    """Optionally expand results with KG snippets.

    This remains a lightweight hook: it reads from a JSON mapping when provided
    via EARCRAWLER_KG_EXPANSION_PATH. If the mapping is absent or cannot be
    parsed, the function returns an empty list (safe fallback).

    TODO: Replace JSON KG expansion with Fuseki queries. Swap the file read
    below with calls to the Fuseki gateway (see service/api_server/fuseki.py,
    service/api_server/templates.py, and earCrawler/sparql/*.sparql) that return
    the same {section_id, text, source, related_sections} structure so callers
    do not need to change.
    """

    mapping_path = os.getenv("EARCRAWLER_KG_EXPANSION_PATH")
    if not mapping_path:
        return []
    try:
        import json

        data = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive, optional path
        _logger.warning("rag.kg.expansion_failed", error=str(exc))
        return []

    normalized = {}
    for raw_key in data.keys():
        norm = _normalize_section_id(raw_key)
        if norm:
            normalized.setdefault(norm, raw_key)
    expansions: list[dict] = []
    for sec in section_ids:
        key = _normalize_section_id(sec)
        if key in normalized:
            raw_key = normalized[key]
            entry = data.get(raw_key) or {}
            text = str(entry.get("text") or entry.get("comment") or "").strip()
            if not text:
                continue
            related_sections = []
            for related in entry.get("related_sections") or []:
                norm_related = _normalize_section_id(related)
                if norm_related:
                    related_sections.append(norm_related)
            expansions.append(
                {
                    "section_id": key or raw_key,
                    "text": text,
                    "source": entry.get("source"),
                    "title": entry.get("title"),
                    "related_sections": sorted(set(related_sections)),
                    "label_hints": sorted(entry.get("label_hints") or []),
                }
            )
    return expansions


def _build_prompt(
    question: str,
    contexts: List[str],
    *,
    label_schema: str | None = None,
) -> list[dict]:
    if label_schema == "truthiness":
        allowed_labels = "true, false, unanswerable"
        system = (
            "You are an expert on Export Administration Regulations (EAR). "
            "Answer ONLY using the provided regulation excerpts and knowledge-graph context. "
            "Cite EAR section IDs when possible. If the answer is not determinable from the "
            "provided text, say so explicitly.\n\n"
            "Truthiness labeling (MUST match exactly):\n"
            f"- Allowed labels: {allowed_labels}\n"
            "- Definitions:\n"
            "  - true: the statement in the question is supported by the provided context.\n"
            "  - false: the statement is not supported or is contradicted by the provided context.\n"
            "  - unanswerable: the provided context is insufficient to decide true vs false.\n\n"
            "Respond in STRICT JSON with this exact shape and no extra text:\n"
            "{\n"
            '  \"label\": \"<one of: '
            + allowed_labels
            + '>\",\n'
            '  \"answer_text\": \"<short answer>\",\n'
            "  \"citations\": [\n"
            "    {\"section_id\": \"EAR-<id>\", \"quote\": \"<verbatim substring from Context>\", \"span_id\": \"<optional>\"}\n"
            "  ],\n"
            "  \"evidence_okay\": {\"ok\": true, \"reasons\": [\"<brief machine-checkable reasons>\"]},\n"
            "  \"assumptions\": []\n"
            "}\n\n"
            "Grounding rules (MUST follow):\n"
            "- Every citation.quote MUST be an exact substring of the provided Context (verbatim).\n"
            "- If you cannot provide at least one grounded quote for the key claim, set label=unanswerable.\n"
            "- If label=unanswerable, answer_text MUST include a short refusal and a retrieval-guidance hint (e.g., missing ECCN/destination/end-use).\n"
            "- evidence_okay.ok MUST be true when you followed these rules.\n"
        )
        context_block = (
            "\n\n".join(contexts) if contexts else "No supporting context provided."
        )
        user = f"Context:\n{context_block}\n\nQuestion: {question}\nAnswer JSON:"
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    allowed_labels = (
        "license_required, no_license_required, exception_applies, "
        "permitted_with_license, permitted, prohibited, unanswerable"
    )
    system = (
        "You are an expert on Export Administration Regulations (EAR). "
        "Answer ONLY using the provided regulation excerpts and knowledge-graph context. "
        "Cite EAR section IDs when possible. If the answer is not determinable from the "
        "provided text, say so explicitly.\n\n"
        "Label taxonomy (MUST match exactly):\n"
        f"- Allowed labels: {allowed_labels}\n"
        "- Definitions:\n"
        "  - license_required: the question asks whether a license is required and the context supports that it is.\n"
        "  - no_license_required: the question asks whether a license is required and the context supports that it is not.\n"
        "  - exception_applies: a License Exception applies so export can proceed without a license.\n"
        "  - permitted_with_license: export/activity is allowed, but ONLY if a license is obtained.\n"
        "  - permitted: export/activity is allowed as described (no additional requirement stated in provided context).\n"
        "  - prohibited: export/activity is not allowed as described.\n"
        "  - unanswerable: the provided context does not support any of the above.\n\n"
        "Task-aware label rules:\n"
        "- If the question is phrased as “need a license / license required?”, choose among: "
        "license_required | no_license_required | exception_applies | unanswerable.\n"
        "- If the question is phrased as “can X export … without a license?”, then:\n"
        "  - If context implies a license must be obtained: permitted_with_license.\n"
        "  - If a License Exception applies: exception_applies.\n"
        "  - If context implies it is allowed without a license: no_license_required.\n"
        "- Dataset convention: when task=entity_obligation and a License Exception applies, "
        "use label=permitted (NOT exception_applies).\n"
        "- Avoid using prohibited unless the provided excerpts explicitly prohibit the export/activity.\n\n"
        "Decision table (use verbatim logic):\n"
        "- If answer is “No” to “without a license?” because a license is required => permitted_with_license.\n"
        "- If a License Exception applies => exception_applies.\n"
        "- If you cannot cite a relevant EAR section from the provided context => unanswerable.\n\n"
        "Examples:\n"
        "Example A (exception applies):\n"
        "Context: [EAR-740.1] License Exceptions describe conditions where exports may be made without a license.\n"
        "Question: Can a controlled item be exported without a license if a License Exception applies under the EAR?\n"
        "Answer JSON:\n"
        "{\n"
        '  \"label\": \"exception_applies\",\n'
        '  \"answer_text\": \"Yes. Insufficient evidence to apply conditions unless the cited exception applies; if it does, the export can proceed without a license.\",\n'
        "  \"citations\": [\n"
        "    {\"section_id\": \"EAR-740.1\", \"quote\": \"License Exceptions describe conditions where exports may be made without a license.\", \"span_id\": \"\"}\n"
        "  ],\n"
        "  \"evidence_okay\": {\"ok\": true, \"reasons\": [\"citation_quote_is_substring_of_context\"]},\n"
        "  \"assumptions\": []\n"
        "}\n"
        "Example B (permitted with license):\n"
        "Context: [EAR-742.4(a)(1)] A license is required to export certain high-performance computers to China.\n"
        "Question: Can ACME export a high-performance computer to China without a license?\n"
        "Answer JSON:\n"
        "{\n"
        '  \"label\": \"permitted_with_license\",\n'
        '  \"answer_text\": \"No. The activity is only permitted with a license based on the provided excerpt.\",\n'
        "  \"citations\": [\n"
        "    {\"section_id\": \"EAR-742.4(a)(1)\", \"quote\": \"A license is required to export certain high-performance computers to China.\", \"span_id\": \"\"}\n"
        "  ],\n"
        "  \"evidence_okay\": {\"ok\": true, \"reasons\": [\"citation_quote_is_substring_of_context\"]},\n"
        "  \"assumptions\": []\n"
        "}\n\n"
        "Respond in STRICT JSON with this exact shape and no extra text:\n"
        "{\n"
        '  \"label\": \"<one of: '
        + allowed_labels
        + '>\",\n'
        '  \"answer_text\": \"<short answer>\",\n'
        "  \"citations\": [\n"
        "    {\"section_id\": \"EAR-<id>\", \"quote\": \"<verbatim substring from Context>\", \"span_id\": \"<optional>\"}\n"
        "  ],\n"
        "  \"evidence_okay\": {\"ok\": true, \"reasons\": [\"<brief machine-checkable reasons>\"]},\n"
        "  \"assumptions\": []\n"
        "}\n\n"
        "Grounding rules (MUST follow):\n"
        "- Every citation.quote MUST be an exact substring of the provided Context (verbatim).\n"
        "- If you cannot provide at least one grounded quote for the key claim, set label=unanswerable.\n"
        "- If label=unanswerable, answer_text MUST include a short refusal and a retrieval-guidance hint (e.g., missing ECCN/destination/end-use).\n"
        "- If assumptions is non-empty, label MUST be unanswerable unless each assumption is directly supported by the Context.\n"
        "- evidence_okay.ok MUST be true when you followed these rules.\n"
    )
    context_block = (
        "\n\n".join(contexts) if contexts else "No supporting context provided."
    )
    user = f"Context:\n{context_block}\n\nQuestion: {question}\nAnswer JSON:"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def answer_with_rag(
    question: str,
    *,
    task: str | None = None,
    label_schema: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    top_k: int = 5,
    retriever: object | None = None,
    strict_retrieval: bool = True,
    strict_output: bool = True,
) -> dict:
    """Run retrieval + optional KG expansion + LLM generation."""

    retrieval_warnings: list[dict[str, object]] = []
    docs = retrieve_regulation_context(
        question,
        top_k=top_k,
        retriever=retriever,
        strict=strict_retrieval,
        warnings=retrieval_warnings,
    )
    retrieval_empty = len(docs) == 0
    retrieval_empty_reason = (
        (retrieval_warnings[-1]["code"] if retrieval_warnings else "no_hits")
        if retrieval_empty
        else None
    )
    section_ids = [d["section_id"] for d in docs if d.get("section_id")]
    kg_expansion = expand_with_kg(section_ids)
    contexts: list[str] = []
    for d in docs:
        text = (d.get("text") or "").strip()
        if not text:
            continue
        section_id = d.get("section_id")
        if section_id:
            contexts.append(f"[{section_id}] {text}")
        else:
            contexts.append(text)
    for d in kg_expansion:
        text = str(d.get("text") or "").strip()
        if not text:
            continue
        section_id = _normalize_section_id(d.get("section_id"))
        if section_id:
            contexts.append(f"[{section_id}] {text}")
        else:
            contexts.append(text)

    prompt_question = question
    if task:
        prompt_question = f"(task={task}) {question}"
    prompt = _build_prompt(prompt_question, contexts, label_schema=label_schema)

    try:
        raw_answer = generate_chat(prompt, provider=provider, model=model)
    except LLMProviderError as exc:
        _logger.error("rag.answer.failed", error=str(exc))
        raise

    raw_answer = str(raw_answer)
    answer_text: str | None = None
    label: str | None = None
    justification: str | None = None  # backward-compat derived from citations
    citations: list[dict] | None = None
    assumptions: list[str] | None = None
    evidence_okay: dict | None = None
    citation_span_ids: list[str] | None = None
    output_ok = True
    output_error: dict | None = None

    try:
        allowed_labels = (
            TRUTHINESS_LABELS if label_schema == "truthiness" else DEFAULT_ALLOWED_LABELS
        )
        parsed = parse_strict_answer_json(
            raw_answer,
            allowed_labels=allowed_labels,
            context="\n\n".join(contexts),
        )
        answer_text = str(parsed["answer_text"])
        label = str(parsed["label"])
        citations = list(parsed.get("citations") or [])
        assumptions = list(parsed.get("assumptions") or [])
        evidence_okay = dict(parsed.get("evidence_okay") or {})
        # Derived: compact human-readable trace for older callers.
        justification = " ".join(
            f"[{c.get('section_id')}] {c.get('quote')}"
            for c in (citations or [])
            if c.get("section_id") and c.get("quote")
        ).strip() or None
        citation_span_ids = sorted(
            {
                str(c.get("span_id")).strip()
                for c in (citations or [])
                if isinstance(c.get("span_id"), str) and str(c.get("span_id")).strip()
            }
        )
    except OutputSchemaError as exc:
        output_ok = False
        output_error = exc.as_dict()
        if not strict_output:
            answer_text = raw_answer
        else:
            answer_text = None
            label = None
            justification = None
            citations = None
            assumptions = None
            evidence_okay = None
            citation_span_ids = None

    return {
        "question": question,
        "answer": answer_text,
        "label": label,
        "justification": justification,
        "citations": citations,
        "evidence_okay": evidence_okay,
        "assumptions": assumptions,
        "citation_span_ids": citation_span_ids,
        "used_sections": section_ids,
        "raw_context": "\n\n".join(contexts),
        "raw_answer": raw_answer,
        "retrieval_warnings": retrieval_warnings,
        "retrieval_empty": retrieval_empty,
        "retrieval_empty_reason": retrieval_empty_reason,
        "output_ok": output_ok,
        "output_error": output_error,
    }


__all__ = [
    "answer_with_rag",
    "retrieve_regulation_context",
    "expand_with_kg",
]
