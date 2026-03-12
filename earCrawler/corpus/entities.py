from __future__ import annotations

"""Shared helpers for normalized corpus entity payloads."""

from collections.abc import Mapping, Sequence

DEFAULT_ENTITY_BUCKET = "ORG"


def _normalize_bucket(value: object | None) -> str | None:
    bucket = str(value or "").strip()
    if not bucket:
        return None
    return bucket.upper()


def _normalize_values(value: object | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        raw_values = list(value)
    else:
        raw_values = [value]
    values = {str(item or "").strip() for item in raw_values}
    return sorted(item for item in values if item)


def normalize_entity_map(
    payload: object | None, *, default_bucket: str = DEFAULT_ENTITY_BUCKET
) -> dict[str, list[str]]:
    """Return the canonical entity payload shape ``{TYPE: [names...]}``.

    Supported inputs:
    - dict-like payloads from the current corpus builder
    - legacy flat lists of names (bucketed into ``default_bucket``)
    """

    merged: dict[str, set[str]] = {}
    if isinstance(payload, Mapping):
        for raw_bucket, raw_values in payload.items():
            bucket = _normalize_bucket(raw_bucket)
            if not bucket:
                continue
            values = _normalize_values(raw_values)
            if values:
                merged.setdefault(bucket, set()).update(values)
    elif isinstance(payload, Sequence) and not isinstance(
        payload, (str, bytes, bytearray)
    ):
        bucket = _normalize_bucket(default_bucket)
        values = _normalize_values(payload)
        if bucket and values:
            merged[bucket] = set(values)
    return {bucket: sorted(values) for bucket, values in merged.items() if values}


def merge_entity_maps(*payloads: object | None) -> dict[str, list[str]]:
    """Merge multiple entity payloads into one canonical map."""

    merged: dict[str, set[str]] = {}
    for payload in payloads:
        for bucket, values in normalize_entity_map(payload).items():
            merged.setdefault(bucket, set()).update(values)
    return {bucket: sorted(values) for bucket, values in merged.items() if values}


def entity_names(payload: object | None) -> list[str]:
    """Return sorted, unique entity names regardless of incoming payload shape."""

    names: set[str] = set()
    for values in normalize_entity_map(payload).values():
        names.update(values)
    return sorted(names)


__all__ = [
    "DEFAULT_ENTITY_BUCKET",
    "entity_names",
    "merge_entity_maps",
    "normalize_entity_map",
]
