from __future__ import annotations

"""Retrieval orchestration helpers for the RAG pipeline."""

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

import requests

from api_clients.federalregister_client import FederalRegisterClient
from api_clients.tradegov_client import TradeGovClient
from earCrawler.kg.paths import KGExpansionSnippet, KGPath, KGPathEdge
from earCrawler.rag.kg_expansion_fuseki import (
    FusekiGatewayLike,
    SPARQLTemplateGateway,
    expand_sections_via_fuseki,
)
from earCrawler.rag.temporal import (
    resolve_temporal_request,
    select_temporal_documents,
    temporal_candidate_count,
)
from earCrawler.utils.log_json import JsonLogger

_logger = JsonLogger("rag-retrieval")

_EAR_SECTION_RE = re.compile(
    r"^(?:15\s*CFR\s*)?(?:§+\s*)?(?P<section>\d{3}(?:\.\S+)?)$",
    re.IGNORECASE,
)


@dataclass
class RetrievalContextBundle:
    section_ids: list[str]
    contexts: list[str]
    retrieved_docs: list[dict]
    kg_expansions_payload: list[dict]
    kg_paths_payload: list[dict]


def _resolved_logger(logger: object | None):
    return logger if logger is not None else _logger


def warn_from_exc(exc: BaseException) -> dict[str, object]:
    """Normalize retriever errors into a stable warning payload."""

    code = getattr(exc, "code", "retriever_error")
    metadata = getattr(exc, "metadata", {}) or {}
    return {
        "code": code,
        "message": str(exc),
        "metadata": dict(metadata),
    }


def ensure_retriever(
    retriever: object | None = None,
    *,
    strict: bool = True,
    warnings: list[dict[str, object]] | None = None,
    logger: object | None = None,
):
    log = _resolved_logger(logger)
    if retriever is not None:
        return retriever
    try:
        from earCrawler.rag.retriever import (  # lazy import
            Retriever,
            RetrieverError,
            describe_retriever_config,
        )
    except Exception as exc:  # pragma: no cover - optional deps
        log.error("rag.retriever.import_failed", error=str(exc))
        if strict:
            raise
        if warnings is not None:
            warnings.append(warn_from_exc(exc))
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
        log.info(
            "rag.retriever.ready",
            details={"retriever": describe_retriever_config(retriever_obj)},
        )
        return retriever_obj
    except RetrieverError as exc:
        log.error(
            "rag.retriever.init_failed",
            details={"retriever_error": warn_from_exc(exc)},
        )
        if strict:
            raise
        if warnings is not None:
            warnings.append(warn_from_exc(exc))
        return None
    except Exception as exc:  # pragma: no cover - runtime failures
        log.error("rag.retriever.init_failed", error=str(exc))
        if strict:
            raise
        if warnings is not None:
            warnings.append(warn_from_exc(exc))
        return None


def extract_text(doc: Mapping[str, object]) -> str:
    for key in ("text", "body", "content", "paragraph", "summary", "snippet", "title"):
        val = doc.get(key)
        if val:
            return str(val).strip()
    return ""


def normalize_section_id(value: object | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.upper().startswith("EAR-"):
        if "#" in raw:
            raw = raw.split("#", 1)[0].strip()
        return raw
    cleaned = raw.strip().rstrip(".,;:")
    cleaned = re.sub(r"^§+\s*", "", cleaned).strip()
    match = _EAR_SECTION_RE.match(cleaned)
    if match:
        return f"EAR-{match.group('section')}"
    return raw


def summarize_retrieved_doc(doc: Mapping[str, object], *, source: str = "retrieval") -> dict:
    """Return a compact, stable view of a retrieved document for artifacts."""

    raw = doc.get("raw") if isinstance(doc.get("raw"), Mapping) else {}
    raw = raw or {}

    def _first(keys: Iterable[str]) -> str | None:
        for key in keys:
            val = raw.get(key) if isinstance(raw, Mapping) else None
            if val:
                return str(val)
        return None

    section = normalize_section_id(
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
        "snapshot_date": doc.get("snapshot_date") or _first(["snapshot_date"]),
        "effective_from": doc.get("effective_from")
        or _first(["effective_from", "effective_date"]),
        "effective_to": doc.get("effective_to")
        or _first(["effective_to", "expires_on", "superseded_on"]),
        "temporal_status": doc.get("temporal_status"),
        "temporal_reason": doc.get("temporal_reason"),
    }


def retrieve_regulation_context(
    query: str,
    top_k: int = 5,
    *,
    retriever: object | None = None,
    strict: bool = True,
    warnings: list[dict[str, object]] | None = None,
    effective_date: str | None = None,
    temporal_state: dict[str, object] | None = None,
    ensure_retriever_fn=None,
    logger: object | None = None,
) -> list[dict]:
    """Return top-k regulation snippets using the configured dense/hybrid retriever."""

    log = _resolved_logger(logger)
    warning_list = warnings if warnings is not None else []
    temporal_request = resolve_temporal_request(query, effective_date=effective_date)
    if temporal_request.refusal_reason:
        if temporal_state is not None:
            temporal_state.clear()
            temporal_state.update(
                select_temporal_documents([], request=temporal_request, top_k=top_k).to_dict()
            )
        return []

    try:
        from earCrawler.rag.retriever import RetrieverError
    except Exception:
        RetrieverError = Exception  # type: ignore[assignment]

    try:
        if ensure_retriever_fn is None:
            r = ensure_retriever(
                retriever,
                strict=strict,
                warnings=warning_list,
                logger=log,
            )
        else:
            r = ensure_retriever_fn(retriever, strict=strict, warnings=warning_list)
    except RetrieverError as exc:
        log.error(
            "rag.retriever.unavailable",
            details={"retriever_error": warn_from_exc(exc)},
        )
        if strict:
            raise
        warning_list.append(warn_from_exc(exc))
        return []
    except Exception as exc:  # pragma: no cover - defensive
        log.error("rag.retriever.unavailable", error=str(exc))
        if strict:
            raise
        warning_list.append(warn_from_exc(exc))
        return []

    if r is None:
        return []
    try:
        query_k = temporal_candidate_count(top_k) if temporal_request.requested else top_k
        docs = r.query(query, k=query_k)
    except RetrieverError as exc:
        log.error(
            "rag.retrieval.failed",
            details={"retriever_error": warn_from_exc(exc)},
        )
        if strict:
            raise
        warning_list.append(warn_from_exc(exc))
        return []
    except Exception as exc:  # pragma: no cover - defensive
        log.error("rag.retrieval.failed", error=str(exc))
        if strict:
            raise
        warning_list.append(warn_from_exc(exc))
        return []
    selection = select_temporal_documents(docs, request=temporal_request, top_k=top_k)
    if temporal_state is not None:
        temporal_state.clear()
        temporal_state.update(selection.to_dict())
    docs = list(selection.selected_docs)
    results: list[dict] = []
    for doc in docs:
        text = extract_text(doc)
        if not text:
            continue
        section_id = normalize_section_id(
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
                "snapshot_date": doc.get("snapshot_date"),
                "effective_from": doc.get("effective_from"),
                "effective_to": doc.get("effective_to"),
                "temporal_status": doc.get("temporal_status"),
                "temporal_reason": doc.get("temporal_reason"),
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


def kg_failure_policy() -> Literal["error", "disable"]:
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


def kg_expansion_mode() -> Literal["always_on", "multihop_only", "off"]:
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


def task_is_multihop(task: str | None) -> bool:
    value = str(task or "").strip().lower()
    return "multihop" in value or "multi-hop" in value


def should_run_kg_expansion(*, task: str | None, explicit: bool | None) -> bool:
    if explicit is not None:
        return bool(explicit)

    mode = kg_expansion_mode()
    if mode == "off":
        return False
    if mode == "multihop_only":
        return task_is_multihop(task)
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


def create_fuseki_gateway() -> FusekiGatewayLike:
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


def _expand_with_json_stub(
    section_ids: list[str],
    mapping_path: str,
    *,
    logger: object | None = None,
) -> list[KGExpansionSnippet]:
    log = _resolved_logger(logger)
    try:
        data = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive, optional path
        log.warning("rag.kg.expansion_failed", error=str(exc))
        return []

    normalized: dict[str, str] = {}
    for raw_key in data.keys():
        norm = normalize_section_id(raw_key)
        if norm:
            normalized.setdefault(norm, str(raw_key))

    max_paths = _env_int(
        "EARCRAWLER_KG_EXPANSION_MAX_PATHS_PER_SECTION",
        default=4,
        min_value=1,
    )
    expansions: list[KGExpansionSnippet] = []
    for sec in sorted(set(section_ids)):
        key = normalize_section_id(sec)
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
            norm_related = normalize_section_id(related)
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
    gateway_factory=None,
    logger: object | None = None,
) -> list[KGExpansionSnippet]:
    """Expand retrieved sections with KG snippets and structured path provenance."""

    log = _resolved_logger(logger)
    sections = [norm for norm in (normalize_section_id(value) for value in section_ids) if norm]
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

    log.info("rag.kg_expansion.provider", provider=selected_provider)

    if selected_provider == "json_stub":
        if not mapping_path:
            log.warning(
                "rag.kg.expansion_failed",
                error="json_stub provider selected but EARCRAWLER_KG_EXPANSION_PATH is not configured",
            )
            return []
        return _expand_with_json_stub(sections, mapping_path, logger=log)

    max_paths = _env_int(
        "EARCRAWLER_KG_EXPANSION_MAX_PATHS_PER_SECTION",
        default=4,
        min_value=1,
    )
    max_hops = _env_int("EARCRAWLER_KG_EXPANSION_MAX_HOPS", default=2, min_value=1)
    failure_policy = kg_failure_policy()
    gateway_builder = gateway_factory or create_fuseki_gateway
    try:
        provider_gateway = gateway or gateway_builder()
        return expand_sections_via_fuseki(
            sections,
            provider_gateway,
            max_paths_per_section=max_paths,
            max_hops=max_hops,
        )
    except Exception as exc:
        if failure_policy == "disable":
            log.warning(
                "rag.kg.expansion_failed",
                error=str(exc),
                failure_policy=failure_policy,
            )
            return []
        raise


def build_context_lines(
    documents: Sequence[Mapping[str, object]],
    *,
    normalize_section_headers: bool = True,
) -> list[str]:
    contexts: list[str] = []
    for doc in documents:
        text = extract_text(doc)
        if not text:
            continue
        raw_section = (
            doc.get("section_id")
            or doc.get("section")
            or doc.get("span_id")
            or doc.get("doc_id")
            or doc.get("id")
            or doc.get("entity_id")
            or ""
        )
        if normalize_section_headers:
            section_value = normalize_section_id(raw_section)
        else:
            section_value = str(raw_section or "").strip() or None
        temporal_parts: list[str] = []
        if doc.get("snapshot_date"):
            temporal_parts.append(f"snapshot={doc['snapshot_date']}")
        if doc.get("effective_from"):
            temporal_parts.append(f"from={doc['effective_from']}")
        if doc.get("effective_to"):
            temporal_parts.append(f"to={doc['effective_to']}")
        if section_value:
            header = section_value
            if temporal_parts:
                header = f"{header} | {'; '.join(temporal_parts)}"
            contexts.append(f"[{header}] {text}")
        else:
            contexts.append(text)
    return contexts


def build_retrieval_context_bundle(
    docs: Sequence[Mapping[str, object]],
    *,
    kg_expansion: Sequence[KGExpansionSnippet] | None = None,
) -> RetrievalContextBundle:
    section_ids = [str(value) for value in (doc.get("section_id") for doc in docs) if value]
    contexts = build_context_lines(docs, normalize_section_headers=True)
    retrieved_docs = [summarize_retrieved_doc(doc, source="retrieval") for doc in docs]

    kg_paths_by_id: dict[str, KGPath] = {}
    kg_expansions_payload: list[dict] = []
    if kg_expansion:
        for snippet in kg_expansion:
            kg_expansions_payload.append(snippet.to_dict())
            for path in snippet.paths:
                kg_paths_by_id.setdefault(path.path_id, path)
            retrieved_docs.append(
                summarize_retrieved_doc(
                    {
                        "section_id": snippet.section_id,
                        "text": snippet.text,
                        "source": snippet.source,
                    },
                    source="kg",
                )
            )
            text = str(snippet.text or "").strip()
            if not text:
                continue
            section_id = normalize_section_id(snippet.section_id)
            if section_id:
                contexts.append(f"[{section_id}] {text}")
            else:
                contexts.append(text)

    kg_paths_payload = [path.to_dict() for path in (kg_paths_by_id[key] for key in sorted(kg_paths_by_id))]
    return RetrievalContextBundle(
        section_ids=section_ids,
        contexts=contexts,
        retrieved_docs=retrieved_docs,
        kg_expansions_payload=kg_expansions_payload,
        kg_paths_payload=kg_paths_payload,
    )


__all__ = [
    "RetrievalContextBundle",
    "build_context_lines",
    "build_retrieval_context_bundle",
    "create_fuseki_gateway",
    "ensure_retriever",
    "expand_with_kg",
    "extract_text",
    "kg_expansion_mode",
    "normalize_section_id",
    "retrieve_regulation_context",
    "should_run_kg_expansion",
    "summarize_retrieved_doc",
    "warn_from_exc",
]
