from __future__ import annotations

"""Deterministic Fuseki-backed KG expansion adapter for RAG."""

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import unquote

from earCrawler.kg.iri import canonical_section_id, section_iri
from earCrawler.kg.namespaces import RESOURCE_NS
from earCrawler.kg.paths import KGExpansionSnippet, KGPath, KGPathEdge, stable_path_id
from earCrawler.kg.sparql import SPARQLClient

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "sparql" / "kg_expand_by_section_id.rq"
_SECTION_IRI_PREFIX = f"{RESOURCE_NS}ear/section/"


class FusekiGatewayLike(Protocol):
    def select(self, query_id: str, params: Mapping[str, object]) -> list[dict[str, object]]: ...


@dataclass(slots=True)
class _EdgeRow:
    edge: KGPathEdge
    graph_iri: str | None
    confidence: float | None
    text_hints: list[str]
    related_section: str | None


class SPARQLTemplateGateway:
    """Small sync gateway used by the RAG pipeline.

    The interface matches test stubs that implement ``.select(query_id, params)``.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        template_path: Path | None = None,
        timeout: int = 5,
        query_retries: int = 0,
        retry_backoff_ms: int = 0,
        client: SPARQLClient | None = None,
    ) -> None:
        self._template_path = template_path or _TEMPLATE_PATH
        self._template = self._template_path.read_text(encoding="utf-8")
        self._client = client or SPARQLClient(endpoint=endpoint, timeout=timeout)
        self._query_retries = max(0, int(query_retries))
        self._retry_backoff_ms = max(0, int(retry_backoff_ms))

    def select(self, query_id: str, params: Mapping[str, object]) -> list[dict[str, object]]:
        if query_id != "kg_expand_by_section_id":
            raise KeyError(f"Unknown query template: {query_id}")
        section = _as_str(params.get("section_iri"))
        if not section:
            raise ValueError("section_iri is required")
        query = self._template.replace("{{section_iri}}", f"<{section}>")

        attempts = self._query_retries + 1
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                payload = self._client.select(query)
                return _coerce_bindings(payload)
            except Exception as exc:
                last_exc = exc
                if attempt >= attempts:
                    raise
                if self._retry_backoff_ms > 0:
                    time.sleep(self._retry_backoff_ms / 1000.0)

        if last_exc is not None:
            raise last_exc
        return []


def expand_sections_via_fuseki(
    section_ids: list[str],
    gateway: FusekiGatewayLike,
    *,
    max_paths_per_section: int,
    max_hops: int,
) -> list[KGExpansionSnippet]:
    if max_paths_per_section <= 0 or max_hops <= 0:
        return []

    normalized_sections = sorted(
        {
            norm
            for norm in (canonical_section_id(section) for section in section_ids)
            if norm
        }
    )

    expansions: list[KGExpansionSnippet] = []
    for section_id in normalized_sections:
        snippet = _expand_one_section(
            section_id,
            gateway,
            max_paths_per_section=max_paths_per_section,
            max_hops=max_hops,
        )
        if snippet is not None:
            expansions.append(snippet)
    return expansions


def _expand_one_section(
    section_id: str,
    gateway: FusekiGatewayLike,
    *,
    max_paths_per_section: int,
    max_hops: int,
) -> KGExpansionSnippet | None:
    start_iri = section_iri(section_id)
    frontier: list[tuple[list[KGPathEdge], str, str | None, list[float]]] = [
        ([], start_iri, None, [])
    ]
    all_paths: list[tuple[list[KGPathEdge], str | None, list[float]]] = []
    text_hints: set[str] = set()
    related_sections: set[str] = set()

    for _hop in range(1, max_hops + 1):
        next_frontier: list[tuple[list[KGPathEdge], str, str | None, list[float]]] = []
        for edges, current_node, graph_iri, conf_values in frontier:
            rows = gateway.select(
                "kg_expand_by_section_id",
                {
                    "section_iri": current_node,
                    "start_section_id": section_id,
                    "max_hops": max_hops,
                },
            )
            parsed_rows = _parse_rows_for_source(rows, current_node)
            seen_nodes = {start_iri}
            seen_nodes.update(edge.target for edge in edges)
            for parsed in parsed_rows:
                if parsed.edge.target in seen_nodes:
                    continue
                new_edges = [*edges, parsed.edge]
                new_graph = parsed.graph_iri or graph_iri
                new_conf_values = list(conf_values)
                if parsed.confidence is not None:
                    new_conf_values.append(parsed.confidence)
                all_paths.append((new_edges, new_graph, new_conf_values))
                next_frontier.append(
                    (new_edges, parsed.edge.target, new_graph, new_conf_values)
                )

                if parsed.related_section:
                    related_sections.add(parsed.related_section)
                target_section = _section_id_from_iri(parsed.edge.target)
                if target_section:
                    related_sections.add(target_section)
                for hint in parsed.text_hints:
                    if hint:
                        text_hints.add(hint)

        frontier = _sort_frontier(next_frontier)
        if not frontier:
            break
        # Keep traversal deterministic and bounded.
        frontier = frontier[: max_paths_per_section * 4]

    if not all_paths:
        return None

    path_objs: list[KGPath] = []
    for edges, graph_iri, conf_values in _sort_path_rows(all_paths)[:max_paths_per_section]:
        confidence = min(conf_values) if conf_values else None
        path_id = stable_path_id(
            start_section_id=section_id,
            edges=edges,
            graph_iri=graph_iri,
        )
        path_objs.append(
            KGPath(
                path_id=path_id,
                start_section_id=section_id,
                edges=list(edges),
                graph_iri=graph_iri,
                confidence=confidence,
            )
        )

    snippet_text = _build_snippet_text(text_hints, path_objs)
    related_sections.discard(section_id)

    return KGExpansionSnippet(
        section_id=section_id,
        text=snippet_text,
        source="fuseki",
        paths=path_objs,
        related_sections=sorted(related_sections),
    )


def _parse_rows_for_source(
    rows: Sequence[Mapping[str, object]],
    source_iri: str,
) -> list[_EdgeRow]:
    parsed: list[_EdgeRow] = []
    for row in rows:
        source = _as_str(_first(row, "source", "s"))
        predicate = _as_str(_first(row, "predicate", "p", "relation"))
        target = _as_str(_first(row, "target", "o", "value"))
        if source != source_iri:
            continue
        if not source or not predicate or not target:
            continue
        graph_iri = _as_optional_str(_first(row, "graph_iri", "graph"))
        confidence = _as_optional_float(_first(row, "confidence", "score"))

        related_section = _canonical_section_id(
            _first(row, "related_section", "relatedSection")
        )
        if not related_section:
            related_section = _section_id_from_iri(target)

        hints = []
        for key in (
            "section_label",
            "section_comment",
            "source_label",
            "source_comment",
            "target_label",
            "target_comment",
            "label",
            "comment",
        ):
            value = _as_optional_str(row.get(key))
            if value:
                hints.append(value)

        parsed.append(
            _EdgeRow(
                edge=KGPathEdge(source=source, predicate=predicate, target=target),
                graph_iri=graph_iri,
                confidence=confidence,
                text_hints=hints,
                related_section=related_section,
            )
        )

    return sorted(
        parsed,
        key=lambda item: (
            item.edge.source,
            item.edge.predicate,
            item.edge.target,
            item.graph_iri or "",
            item.confidence if item.confidence is not None else -1.0,
            item.related_section or "",
        ),
    )


def _sort_frontier(
    rows: Sequence[tuple[list[KGPathEdge], str, str | None, list[float]]],
) -> list[tuple[list[KGPathEdge], str, str | None, list[float]]]:
    return sorted(
        rows,
        key=lambda row: (
            _path_sort_key(row[0]),
            row[1],
            row[2] or "",
            min(row[3]) if row[3] else -1.0,
        ),
    )


def _sort_path_rows(
    rows: Sequence[tuple[list[KGPathEdge], str | None, list[float]]],
) -> list[tuple[list[KGPathEdge], str | None, list[float]]]:
    return sorted(
        rows,
        key=lambda row: (
            _path_sort_key(row[0]),
            row[1] or "",
            min(row[2]) if row[2] else -1.0,
        ),
    )


def _path_sort_key(edges: Sequence[KGPathEdge]) -> tuple[tuple[str, str, str], ...]:
    return tuple((edge.source, edge.predicate, edge.target) for edge in edges)


def _build_snippet_text(text_hints: set[str], paths: Sequence[KGPath]) -> str:
    cleaned_hints = sorted({_normalize_text(value) for value in text_hints if value})
    cleaned_hints = [value for value in cleaned_hints if value]
    if cleaned_hints:
        return " | ".join(cleaned_hints[:2])[:320]

    edge_fragments: list[str] = []
    for path in paths[:1]:
        for edge in path.edges[:2]:
            edge_fragments.append(
                f"{_short_iri(edge.source)} {_short_iri(edge.predicate)} {_short_iri(edge.target)}"
            )
    if edge_fragments:
        return "; ".join(edge_fragments)[:320]
    return ""


def _short_iri(value: str) -> str:
    raw = _as_str(value)
    if not raw:
        return ""
    token = raw.rsplit("#", 1)[-1]
    token = token.rsplit("/", 1)[-1]
    return unquote(token)


def _normalize_text(value: str) -> str:
    return " ".join(_as_str(value).split())


def _section_id_from_iri(value: object | None) -> str | None:
    iri = _as_str(value)
    if not iri.startswith(_SECTION_IRI_PREFIX):
        return None
    encoded = iri[len(_SECTION_IRI_PREFIX) :]
    decoded = unquote(encoded)
    return _canonical_section_id(decoded)


def _canonical_section_id(value: object | None) -> str | None:
    raw = _as_str(value)
    if not raw:
        return None
    return canonical_section_id(raw)


def _first(row: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in row:
            return row.get(key)
    return None


def _as_str(value: object | None) -> str:
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    return str(value or "").strip()


def _as_optional_str(value: object | None) -> str | None:
    text = _as_str(value)
    return text or None


def _as_optional_float(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    if isinstance(value, (int, float)):
        return float(value)
    raw = _as_str(value)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _coerce_bindings(data: Mapping[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    raw_results = data.get("results")
    if not isinstance(raw_results, Mapping):
        return rows
    raw_bindings = raw_results.get("bindings")
    if not isinstance(raw_bindings, list):
        return rows

    for binding in raw_bindings:
        if not isinstance(binding, Mapping):
            continue
        row: dict[str, object] = {}
        for key, raw_value in binding.items():
            if not isinstance(key, str):
                continue
            if isinstance(raw_value, Mapping):
                row[key] = raw_value.get("value")
            else:
                row[key] = raw_value
        rows.append(row)
    return rows


__all__ = [
    "FusekiGatewayLike",
    "SPARQLTemplateGateway",
    "expand_sections_via_fuseki",
]
