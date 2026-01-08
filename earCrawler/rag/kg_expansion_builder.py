from __future__ import annotations

"""Deterministic builder for file-backed KG expansion snippets.

Schema (JSON object):
- key: normalized EAR section id (for example EAR-740.1)
- value: {
    "text": "<short preview>",
    "source": "<source url>",
    "title": "<optional title>",
    "related_sections": ["EAR-..."],
    "label_hints": ["kg_node_or_path", ...]
  }
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping

from earCrawler.rag.pipeline import _normalize_section_id


def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)


def _load_corpus_index(corpus_path: Path) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for record in _iter_jsonl(corpus_path):
        section_id = (
            record.get("section")
            or record.get("span_id")
            or record.get("id")
            or record.get("entity_id")
        )
        norm = _normalize_section_id(section_id)
        if not norm:
            continue
        index.setdefault(norm, []).append(record)
    for key in list(index.keys()):
        index[key] = sorted(
            index[key],
            key=lambda rec: str(rec.get("id") or rec.get("title") or rec.get("section") or ""),
        )
    return index


def _resolve_dataset_paths(manifest: Mapping[str, object], manifest_path: Path) -> list[Path]:
    paths: list[Path] = []
    for entry in manifest.get("datasets", []) or []:
        raw = entry.get("file")
        if not raw:
            continue
        candidate = Path(str(raw))
        if not candidate.is_absolute() and not candidate.exists():
            candidate = manifest_path.parent / candidate
        paths.append(candidate)
    return paths


def _collect_targets(manifest_path: Path) -> tuple[set[str], dict[str, set[str]], dict[str, set[str]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    targets: set[str] = set()
    related: dict[str, set[str]] = defaultdict(set)
    label_hints: dict[str, set[str]] = defaultdict(set)

    ref = manifest.get("references") or {}
    ref_sections = ref.get("sections") or {}
    for parent, children in ref_sections.items():
        norm_parent = _normalize_section_id(parent)
        group = []
        for child in children or []:
            norm_child = _normalize_section_id(child)
            if norm_child:
                targets.add(norm_child)
                group.append(norm_child)
        if norm_parent:
            targets.add(norm_parent)
        for child in group:
            group_related = set(group)
            if norm_parent:
                group_related.add(norm_parent)
            group_related.discard(child)
            related[child].update(group_related)
            label_hints[child].update(ref.get("kg_nodes") or [])
            label_hints[child].update(ref.get("kg_paths") or [])

    for dataset_path in _resolve_dataset_paths(manifest, manifest_path):
        if not dataset_path.exists():
            continue
        for item in _iter_jsonl(dataset_path):
            for sec in item.get("ear_sections") or []:
                norm = _normalize_section_id(sec)
                if norm:
                    targets.add(norm)
                    evidence = item.get("evidence") or {}
                    label_hints[norm].update(evidence.get("kg_nodes") or [])
                    label_hints[norm].update(evidence.get("kg_paths") or [])
            evidence = item.get("evidence") or {}
            for span in evidence.get("doc_spans") or []:
                norm_span = _normalize_section_id(span.get("span_id"))
                if norm_span:
                    targets.add(norm_span)
    return targets, related, label_hints


def build_expansion_mapping(corpus_path: Path, manifest_path: Path) -> dict[str, dict]:
    """Construct a deterministic KG expansion map using the local corpus."""

    corpus_index = _load_corpus_index(corpus_path)
    targets, related, label_hints = _collect_targets(manifest_path)

    expansions: dict[str, dict] = {}
    for section_id in sorted(targets):
        records = corpus_index.get(section_id, [])
        if not records:
            continue
        record = records[0]
        text = str(
            record.get("text")
            or record.get("body")
            or record.get("content")
            or record.get("summary")
            or ""
        ).strip()
        if not text:
            continue
        expansions[section_id] = {
            "text": text[:320],
            "source": record.get("source_url") or record.get("source"),
            "title": record.get("title"),
            "related_sections": sorted(related.get(section_id, set())),
            "label_hints": sorted(label_hints.get(section_id, set())),
        }
    return expansions


def write_expansion_mapping(out_path: Path, mapping: Mapping[str, object]) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


__all__ = ["build_expansion_mapping", "write_expansion_mapping"]
