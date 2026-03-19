from __future__ import annotations

from typing import Mapping, Sequence

from earCrawler.corpus.entities import merge_entity_maps
from earCrawler.corpus.identity import (
    build_record_id,
    compute_content_sha256,
    content_sha256_for_record,
    normalize_corpus_record,
)
from earCrawler.corpus.metadata import DocMeta
from earCrawler.policy import load_hints
from earCrawler.privacy import scrub_text
from earCrawler.transforms.canonical import CanonicalRegistry
from earCrawler.transforms.mentions import MentionExtractor


class RecordNormalizer:
    def __init__(self) -> None:
        self.canonical = CanonicalRegistry()
        self.extractor = MentionExtractor()
        self.hint_entities = self._load_hint_entities()

    def make_record(
        self,
        source: str,
        identifier: str,
        text: str,
        meta: DocMeta,
        *,
        extra_entities: Mapping[str, Sequence[str]] | None,
    ) -> dict | None:
        normalized = " ".join((text or "").split())
        paragraph = scrub_text(normalized)
        if not paragraph:
            return None
        sha = compute_content_sha256(paragraph)
        record_id = build_record_id(source, identifier)
        if not record_id:
            raise ValueError(
                f"Unable to build canonical record id for source={source!r} identifier={identifier!r}"
            )
        record = {
            "id": record_id,
            "record_id": record_id,
            "identifier": identifier,
            "source": source,
            "sha256": sha,
            "content_sha256": sha,
            "paragraph": paragraph,
            "text": paragraph,
            "source_url": meta.source_url,
            "date": meta.date,
            "provider": meta.provider,
            "section": meta.section,
            "identifiers": [identifier],
        }
        record["entities"] = merge_entity_maps(
            self.hint_entities_for_paragraph(paragraph),
            extra_entities,
        )
        return record

    def hint_entities_for_paragraph(self, paragraph: str) -> dict[str, list[str]]:
        if not self.hint_entities:
            return {}
        matches = self.extractor.extract(paragraph, self.hint_entities)
        if not matches:
            return {}
        names = sorted({self.hint_entities[key] for key in matches})
        return {"PROGRAM": names}

    def _load_hint_entities(self) -> dict[str, str]:
        entities: dict[str, str] = {}
        hints = load_hints()
        for idx, hint in enumerate(hints):
            programs = self.canonical.canonical_programs([hint.program])
            for program in programs:
                entities[f"hint:{idx}:{program.lower()}"] = program
        return entities


def merge_records(primary: dict, secondary: dict) -> dict:
    primary_norm = normalize_corpus_record(primary)
    secondary_norm = normalize_corpus_record(secondary)
    primary_id = str(primary_norm.get("record_id") or primary_norm.get("id") or "").strip()
    secondary_id = str(secondary_norm.get("record_id") or secondary_norm.get("id") or "").strip()
    if primary_id and secondary_id and primary_id != secondary_id:
        raise ValueError(
            f"Conflicting corpus identities cannot be merged: {primary_id!r} != {secondary_id!r}"
        )
    primary_fp = content_sha256_for_record(primary_norm)
    secondary_fp = content_sha256_for_record(secondary_norm)
    if primary_fp and secondary_fp and primary_fp != secondary_fp:
        raise ValueError(
            f"Conflicting content fingerprints for record {primary_id or secondary_id}: "
            f"{primary_fp} != {secondary_fp}"
        )

    merged = dict(primary_norm)
    merged_ids = list(
        {*(primary_norm.get("identifiers") or []), *(secondary_norm.get("identifiers") or [])}
    )
    merged["identifiers"] = sorted(merged_ids)
    for field in (
        "id",
        "record_id",
        "identifier",
        "content_sha256",
        "sha256",
        "source_url",
        "date",
        "provider",
        "section",
        "paragraph",
        "text",
    ):
        if not merged.get(field) and secondary_norm.get(field):
            merged[field] = secondary_norm[field]
    merged["entities"] = merge_entity_maps(
        primary_norm.get("entities"),
        secondary_norm.get("entities"),
    )
    return merged


__all__ = ["RecordNormalizer", "merge_records"]
