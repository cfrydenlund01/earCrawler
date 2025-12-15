from __future__ import annotations

"""Thin RAG pipeline wrapper that reuses the existing FAISS retriever and LLM client."""

import re
from typing import Iterable, List, Mapping

from api_clients.llm_client import LLMProviderError, generate_chat
from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient
from earCrawler.agent.retrieval_adapter import TextContextRetriever
from pathlib import Path
import os
from earCrawler.utils.log_json import JsonLogger

_logger = JsonLogger("rag-pipeline")


def _ensure_retriever(retriever: object | None = None):
    if retriever is not None:
        return retriever
    try:
        from earCrawler.rag.retriever import Retriever  # lazy import
    except Exception as exc:  # pragma: no cover - optional deps
        _logger.warning("rag.retriever.import_failed", error=str(exc))
        return None
    try:
        index_override = os.getenv("EARCRAWLER_FAISS_INDEX")
        model_override = os.getenv("EARCRAWLER_FAISS_MODEL")
        index_path = Path(index_override) if index_override else Path("data") / "faiss" / "index.faiss"
        model_name = model_override or "all-MiniLM-L12-v2"
        return Retriever(
            TradeGovClient(),
            FederalRegisterClient(),
            model_name=model_name,
            index_path=index_path,
        )
    except Exception as exc:  # pragma: no cover - runtime failures
        _logger.warning("rag.retriever.init_failed", error=str(exc))
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
        return raw
    match = _EAR_SECTION_RE.match(raw)
    if match:
        return f"EAR-{match.group('section')}"
    return raw


def retrieve_regulation_context(
    query: str, top_k: int = 5, *, retriever: object | None = None
) -> list[dict]:
    """Return top-k regulation snippets using the existing FAISS-backed retriever."""

    r = _ensure_retriever(retriever)
    if r is None:
        return []
    docs = r.query(query, k=top_k)
    results: list[dict] = []
    for doc in docs:
        text = _extract_text(doc)
        if not text:
            continue
        section_id = _normalize_section_id(
            doc.get("section") or doc.get("id") or doc.get("entity_id") or ""
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


def _build_prompt(question: str, contexts: List[str]) -> list[dict]:
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
        '  \"answer_text\": \"Yes, if a License Exception applies the export can proceed without a license.\",\n'
        '  \"label\": \"exception_applies\",\n'
        '  \"justification\": \"A License Exception under EAR-740.1 permits export without a license when its conditions are met.\"\n'
        "}\n"
        "Example B (permitted with license):\n"
        "Context: [EAR-742.4(a)(1)] A license is required to export certain high-performance computers to China.\n"
        "Question: Can ACME export a high-performance computer to China without a license?\n"
        "Answer JSON:\n"
        "{\n"
        '  \"answer_text\": \"No, a license is required before exporting that item to China.\",\n'
        '  \"label\": \"permitted_with_license\",\n'
        '  \"justification\": \"EAR-742.4(a)(1) indicates a license is required for this export; therefore it is only permitted with a license.\"\n'
        "}\n\n"
        "Respond in STRICT JSON with this exact shape and no extra text:\n"
        "{\n"
        '  \"answer_text\": \"<short answer>\",\n'
        '  \"label\": \"<one of: '
        + allowed_labels
        + '>\",\n'
        '  \"justification\": \"<1-3 sentence rationale citing EAR sections>\"\n'
        "}\n"
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
    provider: str | None = None,
    model: str | None = None,
    top_k: int = 5,
    retriever: object | None = None,
) -> dict:
    """Run retrieval + optional KG expansion + LLM generation."""

    import json

    docs = retrieve_regulation_context(question, top_k=top_k, retriever=retriever)
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
    prompt = _build_prompt(prompt_question, contexts)

    try:
        raw_answer = generate_chat(prompt, provider=provider, model=model)
    except LLMProviderError as exc:
        _logger.error("rag.answer.failed", error=str(exc))
        raise

    answer_text = raw_answer
    label: str | None = None
    justification: str | None = None

    try:
        parsed = json.loads(raw_answer)
        if isinstance(parsed, dict):
            answer_text = str(parsed.get("answer_text") or "").strip() or answer_text
            label_value = (parsed.get("label") or "").strip().lower()
            label = label_value or None
            just_value = (parsed.get("justification") or "").strip()
            justification = just_value or None
    except Exception:
        # Fall back to treating the entire response as plain text.
        pass

    return {
        "question": question,
        "answer": answer_text,
        "label": label,
        "justification": justification,
        "used_sections": section_ids,
        "raw_context": "\n\n".join(contexts),
        "raw_answer": raw_answer,
    }


__all__ = [
    "answer_with_rag",
    "retrieve_regulation_context",
    "expand_with_kg",
]
