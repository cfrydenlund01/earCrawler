from __future__ import annotations

"""Thin RAG pipeline wrapper that reuses the existing FAISS retriever and LLM client."""

import json
import re
from typing import Iterable, List, Literal, Mapping
from urllib.parse import urlsplit, urlunsplit

from api_clients.llm_client import LLMProviderError, generate_chat
from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient
from pathlib import Path
import os
import requests
import time
from earCrawler.config.llm_secrets import get_llm_config
from earCrawler.kg.paths import KGExpansionSnippet, KGPath, KGPathEdge
from earCrawler.audit import required_events as audit_required_events
from earCrawler.rag.kg_expansion_fuseki import (
    FusekiGatewayLike,
    SPARQLTemplateGateway,
    expand_sections_via_fuseki,
)
from earCrawler.rag.output_schema import (
    DEFAULT_ALLOWED_LABELS,
    TRUTHINESS_LABELS,
    OutputSchemaError,
    make_unanswerable_payload,
    validate_and_extract_strict_answer,
)
from earCrawler.security.data_egress import (
    build_data_egress_decision,
    redact_contexts,
    redact_text_for_mode,
    resolve_redaction_mode,
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
    r"^(?:15\s*CFR\s*)?(?:§+\s*)?(?P<section>\d{3}(?:\.\S+)?)$",
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
    # Normalize common CFR section prefixes like "§ 736.1" to the canonical
    # "EAR-736.1" form used across datasets, citations, and KG identifiers.
    cleaned = raw.strip().rstrip(".,;:")
    cleaned = re.sub(r"^§+\\s*", "", cleaned).strip()
    match = _EAR_SECTION_RE.match(cleaned)
    if match:
        return f"EAR-{match.group('section')}"
    return raw


def _summarize_retrieved_doc(doc: Mapping[str, object], *, source: str = "retrieval") -> dict:
    """Return a compact, stable view of a retrieved document for artifacts."""

    raw = doc.get("raw") if isinstance(doc.get("raw"), Mapping) else {}
    raw = raw or {}

    def _first(keys: Iterable[str]) -> str | None:
        for key in keys:
            val = raw.get(key) if isinstance(raw, Mapping) else None
            if val:
                return str(val)
        return None

    section = _normalize_section_id(
        doc.get("section_id")
        or doc.get("section")
        or _first(["section", "id", "doc_id", "entity_id"])
    )
    url = _first(["source_url", "url"])
    title = _first(["title", "heading"])

    return {
        "id": _first(["id", "doc_id"]) or section,
        "section": section,
        "url": url,
        "title": title,
        "score": doc.get("score"),
        "source": source,
    }


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


def _env_truthy(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, *, default: int, min_value: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return max(min_value, value)


def _env_float(name: str, *, default: float, min_value: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(str(raw).strip())
    except ValueError:
        return default
    return max(min_value, value)


def _max_retrieval_score(docs: list[dict]) -> float:
    best = 0.0
    for doc in docs or []:
        score = doc.get("score")
        if isinstance(score, (int, float)):
            best = max(best, float(score))
        elif isinstance(score, str):
            try:
                best = max(best, float(score))
            except ValueError:
                continue
    return best


def _total_context_chars(contexts: list[str]) -> int:
    return sum(len(str(c or "")) for c in (contexts or []))


def _kg_failure_policy() -> Literal["error", "disable"]:
    raw = str(os.getenv("EARCRAWLER_KG_EXPANSION_FAILURE_POLICY") or "error").strip().lower()
    aliases = {
        "error": "error",
        "fail": "error",
        "disable": "disable",
    }
    resolved = aliases.get(raw)
    if resolved is None:
        raise ValueError(
            "EARCRAWLER_KG_EXPANSION_FAILURE_POLICY must be one of: error, disable"
        )
    return resolved


def _kg_expansion_mode() -> Literal["always_on", "multihop_only", "off"]:
    raw = str(os.getenv("EARCRAWLER_KG_EXPANSION_MODE") or "always_on").strip().lower()
    aliases = {
        "always_on": "always_on",
        "always": "always_on",
        "multihop_only": "multihop_only",
        "multihop": "multihop_only",
        "off": "off",
    }
    resolved = aliases.get(raw)
    if resolved is None:
        raise ValueError(
            "EARCRAWLER_KG_EXPANSION_MODE must be one of: always_on, multihop_only, off"
        )
    return resolved


def _task_is_multihop(task: str | None) -> bool:
    value = str(task or "").strip().lower()
    return "multihop" in value or "multi-hop" in value


def _should_run_kg_expansion(*, task: str | None, explicit: bool | None) -> bool:
    # Explicit caller choice (for example eval ablation modes) takes precedence.
    if explicit is not None:
        return bool(explicit)

    mode = _kg_expansion_mode()
    if mode == "off":
        return False
    if mode == "multihop_only":
        return _task_is_multihop(task)
    return True


def _fuseki_ping_url(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError(f"Invalid EARCRAWLER_FUSEKI_URL: {endpoint!r}")
    return urlunsplit((parsed.scheme, parsed.netloc, "/$/ping", "", ""))


def _probe_fuseki_endpoint(
    endpoint: str,
    *,
    timeout: int,
    retries: int,
    retry_backoff_ms: int,
) -> None:
    ping_url = _fuseki_ping_url(endpoint)
    ask_query = "ASK { ?s ?p ?o }"

    attempts = max(1, retries + 1)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            ping_response = requests.get(ping_url, timeout=timeout)
            if ping_response.status_code != 200:
                raise RuntimeError(f"ping status={ping_response.status_code}")

            ask_response = requests.get(
                endpoint,
                params={"query": ask_query},
                headers={"Accept": "application/sparql-results+json"},
                timeout=timeout,
            )
            if ask_response.status_code != 200:
                raise RuntimeError(f"ask status={ask_response.status_code}")
            payload = ask_response.json()
            if not isinstance(payload, Mapping) or "boolean" not in payload:
                raise RuntimeError("ask probe returned invalid JSON payload")
            return
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            if retry_backoff_ms > 0:
                time.sleep(retry_backoff_ms / 1000.0)

    raise RuntimeError(f"Fuseki health check failed for {endpoint}: {last_exc}")


def _create_fuseki_gateway() -> FusekiGatewayLike:
    endpoint = str(os.getenv("EARCRAWLER_FUSEKI_URL") or "").strip()
    if not endpoint:
        raise RuntimeError(
            "KG expansion provider=fuseki selected but EARCRAWLER_FUSEKI_URL is not configured."
        )
    timeout = _env_int("EARCRAWLER_KG_EXPANSION_FUSEKI_TIMEOUT", default=5, min_value=1)
    retries = _env_int("EARCRAWLER_KG_EXPANSION_FUSEKI_RETRIES", default=1, min_value=0)
    retry_backoff_ms = _env_int(
        "EARCRAWLER_KG_EXPANSION_FUSEKI_RETRY_BACKOFF_MS",
        default=200,
        min_value=0,
    )
    healthcheck_enabled = _env_truthy(
        "EARCRAWLER_KG_EXPANSION_FUSEKI_HEALTHCHECK",
        default=True,
    )

    if healthcheck_enabled:
        _probe_fuseki_endpoint(
            endpoint,
            timeout=timeout,
            retries=retries,
            retry_backoff_ms=retry_backoff_ms,
        )

    return SPARQLTemplateGateway(
        endpoint=endpoint,
        timeout=timeout,
        query_retries=retries,
        retry_backoff_ms=retry_backoff_ms,
    )


def _expand_with_json_stub(section_ids: list[str], mapping_path: str) -> list[KGExpansionSnippet]:
    try:
        import json

        data = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive, optional path
        _logger.warning("rag.kg.expansion_failed", error=str(exc))
        return []

    normalized: dict[str, str] = {}
    for raw_key in data.keys():
        norm = _normalize_section_id(raw_key)
        if norm:
            normalized.setdefault(norm, str(raw_key))

    max_paths = _env_int(
        "EARCRAWLER_KG_EXPANSION_MAX_PATHS_PER_SECTION",
        default=4,
        min_value=1,
    )
    expansions: list[KGExpansionSnippet] = []
    for sec in sorted(set(section_ids)):
        key = _normalize_section_id(sec)
        if not key or key not in normalized:
            continue
        raw_key = normalized[key]
        entry = data.get(raw_key) or {}
        text = str(entry.get("text") or entry.get("comment") or "").strip()
        if not text:
            continue

        paths: list[KGPath] = []
        raw_hints = entry.get("label_hints") or []
        if isinstance(raw_hints, list):
            for hint in raw_hints:
                value = str(hint or "").strip()
                if not value.startswith("path:"):
                    continue
                paths.append(
                    KGPath(
                        path_id=value,
                        start_section_id=key,
                        edges=[
                            KGPathEdge(
                                source=f"stub:section/{key}",
                                predicate="stub:hint_path",
                                target=value,
                            )
                        ],
                        graph_iri="stub://kg_expansion.json",
                        confidence=None,
                    )
                )
                if len(paths) >= max_paths:
                    break

        related_sections: list[str] = []
        for related in entry.get("related_sections") or []:
            norm_related = _normalize_section_id(related)
            if norm_related:
                related_sections.append(norm_related)
        expansions.append(
            KGExpansionSnippet(
                section_id=key,
                text=text,
                source=str(entry.get("source") or "json_stub"),
                paths=paths,
                related_sections=sorted(set(related_sections) - {key}),
            )
        )
    return expansions


def expand_with_kg(
    section_ids: Iterable[str],
    *,
    provider: Literal["fuseki", "json_stub"] = "fuseki",
    gateway: FusekiGatewayLike | None = None,
) -> list[KGExpansionSnippet]:
    """Expand retrieved sections with KG snippets and structured path provenance.

    Provider selection:
    - explicit: ``EARCRAWLER_KG_EXPANSION_PROVIDER`` (``fuseki`` or ``json_stub``)
    - explicit stub fallback: ``EARCRAWLER_KG_EXPANSION_PATH``
    - default when enabled: ``fuseki`` via ``EARCRAWLER_ENABLE_KG_EXPANSION=1``

    When ``fuseki`` is selected, missing gateway configuration is a hard error.
    """

    sections = [norm for norm in (_normalize_section_id(value) for value in section_ids) if norm]
    if not sections:
        return []

    configured_provider = str(os.getenv("EARCRAWLER_KG_EXPANSION_PROVIDER") or "").strip().lower()
    mapping_path = str(os.getenv("EARCRAWLER_KG_EXPANSION_PATH") or "").strip()
    enabled = _env_truthy("EARCRAWLER_ENABLE_KG_EXPANSION", default=False)

    selected_provider: Literal["fuseki", "json_stub"] | None = None
    if configured_provider:
        if configured_provider not in {"fuseki", "json_stub"}:
            raise ValueError(
                "EARCRAWLER_KG_EXPANSION_PROVIDER must be one of: fuseki, json_stub"
            )
        selected_provider = configured_provider  # type: ignore[assignment]
    elif mapping_path:
        selected_provider = "json_stub"
    elif enabled or gateway is not None:
        selected_provider = provider
    else:
        return []

    _logger.info("rag.kg_expansion.provider", provider=selected_provider)

    if selected_provider == "json_stub":
        if not mapping_path:
            _logger.warning(
                "rag.kg.expansion_failed",
                error="json_stub provider selected but EARCRAWLER_KG_EXPANSION_PATH is not configured",
            )
            return []
        return _expand_with_json_stub(sections, mapping_path)

    max_paths = _env_int(
        "EARCRAWLER_KG_EXPANSION_MAX_PATHS_PER_SECTION",
        default=4,
        min_value=1,
    )
    max_hops = _env_int("EARCRAWLER_KG_EXPANSION_MAX_HOPS", default=2, min_value=1)
    failure_policy = _kg_failure_policy()
    try:
        provider_gateway = gateway or _create_fuseki_gateway()
        return expand_sections_via_fuseki(
            sections,
            provider_gateway,
            max_paths_per_section=max_paths,
            max_hops=max_hops,
        )
    except Exception as exc:
        if failure_policy == "disable":
            _logger.warning(
                "rag.kg.expansion_failed",
                error=str(exc),
                failure_policy=failure_policy,
            )
            return []
        raise


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
        '  \"justification\": \"<1-2 sentences summarizing evidence>\",\n'
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
    kg_expansion: bool | None = None,
    strict_retrieval: bool = True,
    strict_output: bool = True,
    generate: bool = True,
    trace_id: str | None = None,
    run_id: str | None = None,
) -> dict:
    """Run retrieval + optional KG expansion + LLM generation."""

    t_total_start = time.perf_counter()
    audit_run_id = str(run_id or os.getenv("EARCTL_AUDIT_RUN_ID") or "").strip() or None
    t_retrieve_ms = 0.0
    t_cache_ms = 0.0
    t_prompt_ms = 0.0
    t_llm_ms = 0.0
    t_parse_ms = 0.0
    rag_enabled = bool(getattr(retriever, "enabled", True)) if retriever is not None else True
    retriever_ready = bool(getattr(retriever, "ready", True)) if retriever is not None else True

    retrieval_warnings: list[dict[str, object]] = []
    retrieve_start = time.perf_counter()
    docs = retrieve_regulation_context(
        question,
        top_k=top_k,
        retriever=retriever,
        strict=strict_retrieval,
        warnings=retrieval_warnings,
    )
    t_retrieve_ms = round((time.perf_counter() - retrieve_start) * 1000.0, 3)
    if retrieval_warnings:
        rag_enabled = rag_enabled and retrieval_warnings[-1].get("code") != "retriever_disabled"
        retriever_ready = retriever_ready and retrieval_warnings[-1].get("code") not in {
            "retriever_error",
            "retriever_unavailable",
            "index_missing",
            "index_build_required",
        }
    retrieval_empty = len(docs) == 0
    retrieval_empty_reason = (
        (retrieval_warnings[-1]["code"] if retrieval_warnings else "no_hits")
        if retrieval_empty
        else None
    )
    section_ids = [d["section_id"] for d in docs if d.get("section_id")]
    kg_mode = _kg_expansion_mode()
    kg_expansion_enabled = _should_run_kg_expansion(task=task, explicit=kg_expansion)
    _logger.info(
        "rag.kg_expansion.mode",
        mode=kg_mode,
        enabled=kg_expansion_enabled,
        task=str(task or ""),
        explicit=kg_expansion,
    )
    kg_expansion = expand_with_kg(section_ids) if kg_expansion_enabled else []
    kg_paths_by_id: dict[str, KGPath] = {}
    for snippet in kg_expansion:
        for path in snippet.paths:
            kg_paths_by_id.setdefault(path.path_id, path)
    kg_paths_used = [kg_paths_by_id[key] for key in sorted(kg_paths_by_id)]
    kg_expansions_payload = [snippet.to_dict() for snippet in kg_expansion]
    kg_paths_payload = [path.to_dict() for path in kg_paths_used]
    retrieved_docs: list[dict] = [_summarize_retrieved_doc(d, source="retrieval") for d in docs]
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
    for snippet in kg_expansion:
        kg_doc = {
            "section_id": snippet.section_id,
            "text": snippet.text,
            "source": snippet.source,
        }
        retrieved_docs.append(_summarize_retrieved_doc(kg_doc, source="kg"))
    for snippet in kg_expansion:
        text = str(snippet.text or "").strip()
        if not text:
            continue
        section_id = _normalize_section_id(snippet.section_id)
        if section_id:
            contexts.append(f"[{section_id}] {text}")
        else:
            contexts.append(text)

    prompt_question = question if not task else f"(task={task}) {question}"
    redaction_mode = resolve_redaction_mode()
    redacted_question = redact_text_for_mode(prompt_question, mode=redaction_mode)
    provider_label: str | None = None
    model_label: str | None = None
    llm_enabled = False
    llm_attempted = False
    raw_answer: str | None = None
    disabled_reason: str | None = None
    prompt: list[dict] | None = None
    redacted_contexts: list[str] = []
    egress_decision = build_data_egress_decision(
        remote_enabled=False,
        disabled_reason="generation not attempted",
        provider=None,
        model=None,
        redaction_mode=redaction_mode,
        question=redacted_question,
        contexts=[],
        messages=None,
        trace_id=trace_id,
    )

    answer_text: str | None = None
    label: str | None = None
    justification: str | None = None  # backward-compat derived from citations
    citations: list[dict] | None = None
    assumptions: list[str] | None = None
    evidence_okay: dict | None = None
    citation_span_ids: list[str] | None = None
    output_ok = True
    output_error: dict | None = None

    if generate:
        prompt_start = time.perf_counter()
        redacted_contexts = redact_contexts(contexts, mode=redaction_mode)
        prompt = _build_prompt(redacted_question, redacted_contexts, label_schema=label_schema)
        t_prompt_ms = round((time.perf_counter() - prompt_start) * 1000.0, 3)

        allowed_labels = (
            TRUTHINESS_LABELS if label_schema == "truthiness" else DEFAULT_ALLOWED_LABELS
        )
        refuse_on_thin = _env_truthy("EARCRAWLER_REFUSE_ON_THIN_RETRIEVAL", default=False)
        min_docs = _env_int("EARCRAWLER_THIN_RETRIEVAL_MIN_DOCS", default=1, min_value=1)
        min_top_score = _env_float("EARCRAWLER_THIN_RETRIEVAL_MIN_TOP_SCORE", default=0.0, min_value=0.0)
        min_total_chars = _env_int("EARCRAWLER_THIN_RETRIEVAL_MIN_TOTAL_CHARS", default=0, min_value=0)

        thin_retrieval = False
        if refuse_on_thin:
            thin_retrieval = retrieval_empty
            if not thin_retrieval:
                if len(docs) < min_docs:
                    thin_retrieval = True
                elif _max_retrieval_score(docs) < min_top_score:
                    thin_retrieval = True
                elif _total_context_chars(redacted_contexts) < min_total_chars:
                    thin_retrieval = True

        if thin_retrieval:
            disabled_reason = "insufficient_evidence"
            llm_enabled = False
            egress_decision = build_data_egress_decision(
                remote_enabled=False,
                disabled_reason=disabled_reason,
                provider=None,
                model=None,
                redaction_mode=redaction_mode,
                question=redacted_question,
                contexts=redacted_contexts,
                messages=prompt,
                trace_id=trace_id,
            )
            _logger.info("llm.egress_decision", **egress_decision.to_dict())

            refusal = make_unanswerable_payload(
                hint="the relevant EAR section excerpt(s) for this scenario (for example: ECCN, destination, end user/end use)",
                justification="Retrieval evidence was empty or too thin to ground a compliant answer.",
                evidence_reasons=["thin_or_empty_retrieval"],
            )
            rendered = json.dumps(refusal, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            validated = validate_and_extract_strict_answer(
                rendered,
                allowed_labels=allowed_labels,
                context="\n\n".join(redacted_contexts),
            )
            answer_text = str(validated["answer_text"])
            label = str(validated["label"])
            citations = list(validated.get("citations") or [])
            assumptions = list(validated.get("assumptions") or [])
            evidence_okay = dict(validated.get("evidence_okay") or {})
            justification = validated.get("justification")
            citation_span_ids = list(validated.get("citation_span_ids") or [])
        else:
            try:
                config = get_llm_config(provider_override=provider, model_override=model)
            except ValueError as exc:
                raise LLMProviderError(str(exc)) from exc
            provider_label = config.provider.provider
            model_label = config.provider.model

            if not config.enable_remote:
                disabled_reason = config.remote_disabled_reason or "remote LLM policy denied egress"
                egress_decision = build_data_egress_decision(
                    remote_enabled=False,
                    disabled_reason=disabled_reason,
                    provider=provider_label,
                    model=model_label,
                    redaction_mode=redaction_mode,
                    question=redacted_question,
                    contexts=redacted_contexts,
                    messages=prompt,
                    trace_id=trace_id,
                )
                _logger.info("llm.egress_decision", **egress_decision.to_dict())
                raise LLMProviderError(
                    f"Remote LLM calls are disabled ({disabled_reason}). "
                    "Remote use requires EARCRAWLER_REMOTE_LLM_POLICY=allow and "
                    "EARCRAWLER_ENABLE_REMOTE_LLM=1."
                )

            llm_attempted = True
            llm_start = time.perf_counter()
            try:
                raw_answer = generate_chat(
                    prompt, provider=provider_label, model=model_label
                )
                t_llm_ms = round((time.perf_counter() - llm_start) * 1000.0, 3)
            except LLMProviderError as exc:
                t_llm_ms = round((time.perf_counter() - llm_start) * 1000.0, 3)
                egress_decision = build_data_egress_decision(
                    remote_enabled=True,
                    disabled_reason=str(exc),
                    provider=provider_label,
                    model=model_label,
                    redaction_mode=redaction_mode,
                    question=redacted_question,
                    contexts=redacted_contexts,
                    messages=prompt,
                    trace_id=trace_id,
                )
                _logger.info("llm.egress_decision", **egress_decision.to_dict())
                _logger.error("rag.answer.failed", error=str(exc))
                raise

            llm_enabled = True
            egress_decision = build_data_egress_decision(
                remote_enabled=True,
                disabled_reason=None,
                provider=provider_label,
                model=model_label,
                redaction_mode=redaction_mode,
                question=redacted_question,
                contexts=redacted_contexts,
                messages=prompt,
                trace_id=trace_id,
            )
            _logger.info("llm.egress_decision", **egress_decision.to_dict())

            raw_answer = str(raw_answer)
            parse_start = time.perf_counter()
            try:
                validated = validate_and_extract_strict_answer(
                    raw_answer,
                    allowed_labels=allowed_labels,
                    context="\n\n".join(redacted_contexts),
                )
                t_parse_ms = round((time.perf_counter() - parse_start) * 1000.0, 3)
                answer_text = str(validated["answer_text"])
                label = str(validated["label"])
                citations = list(validated.get("citations") or [])
                assumptions = list(validated.get("assumptions") or [])
                evidence_okay = dict(validated.get("evidence_okay") or {})
                justification = validated.get("justification")
                citation_span_ids = list(validated.get("citation_span_ids") or [])
            except OutputSchemaError as exc:
                t_parse_ms = round((time.perf_counter() - parse_start) * 1000.0, 3)
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
    else:
        disabled_reason = "generation_disabled_by_request"
        egress_decision = build_data_egress_decision(
            remote_enabled=False,
            disabled_reason=disabled_reason,
            provider=None,
            model=None,
            redaction_mode=redaction_mode,
            question=redacted_question,
            contexts=[],
            messages=None,
            trace_id=trace_id,
        )

    t_total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 3)
    latency_fields: dict[str, object] = {
        "trace_id": trace_id,
        "t_total_ms": t_total_ms,
        "t_retrieve_ms": t_retrieve_ms,
        "t_cache_ms": t_cache_ms,
        "t_prompt_ms": t_prompt_ms,
        "t_llm_ms": t_llm_ms,
        "t_parse_ms": t_parse_ms,
        "rag_enabled": rag_enabled,
        "retriever_ready": retriever_ready,
        "retrieved_count": len(docs),
    }
    if llm_attempted:
        latency_fields["provider"] = provider_label
        latency_fields["model"] = model_label
    _logger.info("rag.pipeline.latency", **latency_fields)

    try:
        audit_required_events.emit_remote_llm_policy_decision(
            trace_id=trace_id,
            run_id=audit_run_id,
            egress_decision=egress_decision.to_dict() if egress_decision else {},
        )
        output_error_code: str | None = None
        if isinstance(output_error, Mapping):
            raw_code = output_error.get("code")
            if raw_code is not None:
                output_error_code = str(raw_code)
        audit_required_events.emit_query_outcome(
            trace_id=trace_id,
            run_id=audit_run_id,
            label=label,
            answer_text=answer_text,
            output_ok=bool(output_ok),
            retrieval_empty=bool(retrieval_empty),
            retrieval_empty_reason=str(retrieval_empty_reason or "") or None,
            disabled_reason=str(disabled_reason or "") or None,
            output_error_code=output_error_code,
        )
    except Exception as exc:  # pragma: no cover - audit logging must never break answers
        _logger.warning("audit.event.emit_failed", error=str(exc), trace_id=trace_id)

    return {
        "question": question,
        "answer": answer_text,
        "label": label,
        "justification": justification,
        "citations": citations,
        "retrieved_docs": retrieved_docs,
        "kg_expansions": kg_expansions_payload,
        "kg_paths_used": kg_paths_payload,
        "trace_id": trace_id,
        "evidence_okay": evidence_okay,
        "assumptions": assumptions,
        "citation_span_ids": citation_span_ids,
        "used_sections": section_ids,
        "contexts": contexts,
        "prompt_contexts": contexts,
        "rag_enabled": rag_enabled,
        "retriever_ready": retriever_ready,
        "llm_enabled": llm_enabled,
        "disabled_reason": disabled_reason,
        "raw_context": "\n\n".join(contexts),
        "raw_answer": raw_answer,
        "retrieval_warnings": retrieval_warnings,
        "retrieval_empty": retrieval_empty,
        "retrieval_empty_reason": retrieval_empty_reason,
        "output_ok": output_ok,
        "output_error": output_error,
        "timings": {
            "t_total_ms": t_total_ms,
            "t_retrieve_ms": t_retrieve_ms,
            "t_cache_ms": t_cache_ms,
            "t_prompt_ms": t_prompt_ms,
            "t_llm_ms": t_llm_ms,
            "t_parse_ms": t_parse_ms,
        },
        "egress_decision": egress_decision.to_dict() if egress_decision else None,
    }


__all__ = [
    "answer_with_rag",
    "retrieve_regulation_context",
    "expand_with_kg",
]
