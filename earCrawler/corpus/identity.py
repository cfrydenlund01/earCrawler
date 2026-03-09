from __future__ import annotations

"""Helpers for source-aware corpus identity and content fingerprints."""

import hashlib
from typing import Mapping


def compute_content_sha256(text: str) -> str:
    """Return a deterministic SHA-256 fingerprint for normalized content."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_record_id(source: object | None, identifier: object | None) -> str | None:
    """Return the canonical source-aware record id for a corpus record."""

    source_value = str(source or "").strip().lower()
    identifier_value = str(identifier or "").strip()
    if not source_value or not identifier_value:
        return None
    prefix = f"{source_value}:"
    if identifier_value.startswith(prefix):
        return identifier_value
    return f"{source_value}:{identifier_value}"


def source_identifier_for_record(record: Mapping[str, object]) -> str | None:
    """Infer the source-local stable identifier for ``record``."""

    for key in ("identifier", "source_identifier"):
        value = str(record.get(key) or "").strip()
        if value:
            return value

    source_value = str(record.get("source") or "").strip().lower()
    prefix = f"{source_value}:"
    for key in ("record_id", "id"):
        value = str(record.get(key) or "").strip()
        if not value:
            continue
        if source_value and value.startswith(prefix):
            return value[len(prefix) :]

    fallback = str(record.get("id") or "").strip()
    return fallback or None


def content_sha256_for_record(record: Mapping[str, object]) -> str | None:
    """Return the content fingerprint stored in or derivable from ``record``."""

    for key in ("content_sha256", "sha256"):
        value = str(record.get(key) or "").strip().lower()
        if value:
            return value

    for key in ("paragraph", "text"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return compute_content_sha256(value.strip())
    return None


def canonical_record_id_for_record(record: Mapping[str, object]) -> str | None:
    """Return the preferred source-aware identity for ``record`` when possible."""

    canonical = build_record_id(record.get("source"), source_identifier_for_record(record))
    if canonical:
        return canonical
    for key in ("record_id", "id"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return None


def paragraph_identity_token(record: Mapping[str, object]) -> str | None:
    """Return the token used to mint paragraph IRIs.

    Prefer the source-aware record id. Fall back to the content fingerprint so
    legacy corpus fixtures continue to emit deterministic paragraph IRIs.
    """

    canonical = build_record_id(record.get("source"), source_identifier_for_record(record))
    if canonical:
        return canonical
    fingerprint = content_sha256_for_record(record)
    if fingerprint:
        return fingerprint
    for key in ("record_id", "id", "identifier"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return None


def normalize_corpus_record(record: Mapping[str, object]) -> dict[str, object]:
    """Backfill the source-aware identity fields for old or partial records."""

    normalized = dict(record)

    source_value = str(normalized.get("source") or "").strip().lower()
    if source_value:
        normalized["source"] = source_value

    identifier = source_identifier_for_record(normalized)
    if identifier:
        normalized["identifier"] = identifier

    record_id = build_record_id(source_value, identifier)
    if record_id:
        normalized["id"] = record_id
        normalized["record_id"] = record_id
    else:
        raw_record_id = str(normalized.get("record_id") or normalized.get("id") or "").strip()
        if raw_record_id:
            normalized["id"] = raw_record_id
            normalized["record_id"] = raw_record_id

    fingerprint = content_sha256_for_record(normalized)
    if fingerprint:
        normalized["sha256"] = fingerprint
        normalized["content_sha256"] = fingerprint

    if identifier:
        values: list[str] = []
        seen: set[str] = set()
        for item in normalized.get("identifiers") or []:
            value = str(item or "").strip()
            if value and value not in seen:
                values.append(value)
                seen.add(value)
        if identifier not in seen:
            values.append(identifier)
        normalized["identifiers"] = values

    return normalized


__all__ = [
    "build_record_id",
    "canonical_record_id_for_record",
    "compute_content_sha256",
    "content_sha256_for_record",
    "normalize_corpus_record",
    "paragraph_identity_token",
    "source_identifier_for_record",
]
