from __future__ import annotations

"""Offline snapshot manifest + validation (offline-snapshot.v1).

This is a *pre-corpus* contract: validate the snapshot payload and bind it to a
manifest with a cryptographic hash before building corpus/index artifacts.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Mapping

from earCrawler.rag.corpus_contract import normalize_ear_section_id


MANIFEST_VERSION = "offline-snapshot.v1"

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class OfflineSnapshotManifest:
    path: Path
    data: Dict[str, Any]


@dataclass(frozen=True)
class SnapshotValidationSummary:
    snapshot_path: Path
    manifest: OfflineSnapshotManifest
    section_count: int
    title_count: int
    part_count: int
    payload_bytes: int


def _iter_bytes(path: Path, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                return
            yield chunk


def compute_sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    for chunk in _iter_bytes(path):
        digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path) -> Dict[str, Any]:
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid JSON manifest: {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError(f"Manifest must be a JSON object: {path}")
    return obj


def discover_manifest_path(snapshot_path: Path) -> Path | None:
    """Discover a manifest path for a given snapshot payload.

    Supported conventions (first match wins):
    - <snapshot>.manifest.json  (example: title15.manifest.json)
    - <snapshot_dir>/manifest.json
    """

    snapshot_path = Path(snapshot_path)
    candidates = [
        snapshot_path.with_suffix(".manifest.json"),
        snapshot_path.parent / "manifest.json",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return None


def _require_str(obj: Mapping[str, Any], key: str, *, where: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: '{key}' must be a non-empty string")
    return value


def _require_obj(obj: Mapping[str, Any], key: str, *, where: str) -> Mapping[str, Any]:
    value = obj.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{where}: '{key}' must be an object")
    return value


def _require_str_list(obj: Mapping[str, Any], key: str, *, where: str) -> list[str]:
    value = obj.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
        raise ValueError(f"{where}: '{key}' must be a non-empty array of strings")
    return [str(v) for v in value]


def _validate_manifest_shape(manifest: Mapping[str, Any], *, manifest_path: Path) -> None:
    where = str(manifest_path)

    version = _require_str(manifest, "manifest_version", where=where)
    if version != MANIFEST_VERSION:
        raise ValueError(f"{where}: 'manifest_version' must equal '{MANIFEST_VERSION}'")

    _require_str(manifest, "snapshot_id", where=where)
    _require_str(manifest, "created_at", where=where)

    source = _require_obj(manifest, "source", where=where)
    _require_str(source, "owner", where=f"{where}.source")
    _require_str(source, "upstream", where=f"{where}.source")
    _require_str(source, "approved_by", where=f"{where}.source")
    _require_str(source, "approved_at", where=f"{where}.source")

    scope = _require_obj(manifest, "scope", where=where)
    _require_str_list(scope, "titles", where=f"{where}.scope")
    parts = scope.get("parts")
    if not isinstance(parts, list) or not all(isinstance(v, str) and v.strip() for v in parts):
        raise ValueError(f"{where}.scope: 'parts' must be an array of strings (can be empty)")

    payload = _require_obj(manifest, "payload", where=where)
    _require_str(payload, "path", where=f"{where}.payload")
    sha256_hex = _require_str(payload, "sha256", where=f"{where}.payload").lower()
    if not _SHA256_HEX_RE.match(sha256_hex):
        raise ValueError(f"{where}.payload: 'sha256' must be 64 lowercase hex characters")
    size = payload.get("size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError(f"{where}.payload: 'size_bytes' must be a non-negative integer")


def _validate_payload_encoding(snapshot_path: Path) -> None:
    # Stable encoding requirement:
    # - UTF-8 (no BOM)
    # - LF-only newlines (no CRLF)
    first = True
    for chunk in _iter_bytes(snapshot_path):
        if first:
            first = False
            if chunk.startswith(b"\xef\xbb\xbf"):
                raise ValueError(f"{snapshot_path}: UTF-8 BOM is not allowed (unstable encoding)")
        if b"\r" in chunk:
            raise ValueError(f"{snapshot_path}: CRLF newlines are not allowed; use LF-only")

    # Ensure it actually decodes as UTF-8.
    try:
        for _ in Path(snapshot_path).open("r", encoding="utf-8", newline="\n"):
            break
    except UnicodeDecodeError as exc:
        raise ValueError(f"{snapshot_path}: must be valid UTF-8: {exc}") from exc


def _iter_snapshot_records(snapshot_path: Path) -> Iterable[tuple[int, Dict[str, Any]]]:
    with Path(snapshot_path).open("r", encoding="utf-8", newline="\n") as handle:
        for lineno, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except Exception as exc:
                raise ValueError(f"{snapshot_path}:{lineno} invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(
                    f"{snapshot_path}:{lineno} expected object, got {type(payload).__name__}"
                )
            yield lineno, payload


def _extract_part(canonical_section_id: str) -> str:
    body = canonical_section_id[len("EAR-") :]
    return body.split(".", 1)[0]


def validate_snapshot_payload(snapshot_path: Path) -> None:
    """Validate snapshot payload content (ids, empties) independent of manifest."""

    snapshot_path = Path(snapshot_path)
    if not snapshot_path.exists():
        raise ValueError(f"Snapshot not found: {snapshot_path}")

    _validate_payload_encoding(snapshot_path)

    count = 0
    seen_sections: dict[str, int] = {}
    for lineno, rec in _iter_snapshot_records(snapshot_path):
        count += 1
        if "section_id" not in rec:
            raise ValueError(f"{snapshot_path}:{lineno} missing required field 'section_id'")
        section_id = rec.get("section_id")
        if not isinstance(section_id, str) or not section_id.strip():
            raise ValueError(f"{snapshot_path}:{lineno} invalid 'section_id': expected non-empty string")
        canonical = normalize_ear_section_id(section_id)
        if canonical is None:
            raise ValueError(
                f"{snapshot_path}:{lineno} section_id '{section_id}' is not a normalizable EAR id"
            )
        first_seen = seen_sections.get(canonical)
        if first_seen is not None:
            raise ValueError(
                f"{snapshot_path}:{lineno} duplicate section_id '{canonical}' "
                f"(first seen at line {first_seen})"
            )
        seen_sections[canonical] = lineno
        if "text" not in rec:
            raise ValueError(f"{snapshot_path}:{lineno} missing required field 'text'")
        text = rec.get("text")
        if text is None:
            raise ValueError(f"{snapshot_path}:{lineno} unexpected null text block in 'text'")
        if not isinstance(text, str):
            raise ValueError(f"{snapshot_path}:{lineno} invalid 'text': expected string")
        if not text.strip():
            raise ValueError(f"{snapshot_path}:{lineno} empty 'text'")

    if count == 0:
        raise ValueError(f"No records found in snapshot: {snapshot_path}")


def _resolve_manifest_path(snapshot_path: Path, *, manifest_path: Path | None = None) -> Path:
    snapshot_path = Path(snapshot_path)
    if manifest_path is None:
        manifest_path = discover_manifest_path(snapshot_path)
    if manifest_path is None:
        raise ValueError(
            f"Snapshot manifest missing for {snapshot_path}. Expected either "
            f"'{snapshot_path.with_suffix('.manifest.json')}' or '{snapshot_path.parent / 'manifest.json'}'."
        )
    return Path(manifest_path)


def _load_manifest(snapshot_path: Path, *, manifest_path: Path | None = None) -> OfflineSnapshotManifest:
    manifest_path = _resolve_manifest_path(snapshot_path, manifest_path=manifest_path)
    manifest = _load_json_object(manifest_path)
    _validate_manifest_shape(manifest, manifest_path=manifest_path)
    return OfflineSnapshotManifest(path=manifest_path, data=manifest)


def _validate_payload_binding(snapshot_path: Path, manifest: OfflineSnapshotManifest) -> None:
    payload_obj = manifest.data["payload"]
    payload_rel = Path(str(payload_obj["path"]))
    payload_path = (manifest.path.parent / payload_rel).resolve()
    if payload_path != snapshot_path.resolve():
        raise ValueError(
            f"{manifest.path}: payload.path points to '{payload_rel}', which resolves to '{payload_path}', "
            f"but the provided snapshot path is '{snapshot_path}'."
        )

    expected_sha256 = str(payload_obj["sha256"]).lower()
    expected_size = int(payload_obj["size_bytes"])
    actual_size = snapshot_path.stat().st_size
    if actual_size != expected_size:
        raise ValueError(
            f"{manifest.path}: payload.size_bytes mismatch (expected {expected_size}, got {actual_size})"
        )
    actual_sha256 = compute_sha256_hex(snapshot_path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"{manifest.path}: payload.sha256 mismatch (expected {expected_sha256}, got {actual_sha256})"
        )


def validate_offline_snapshot(
    snapshot_path: Path, *, manifest_path: Path | None = None
) -> SnapshotValidationSummary:
    """Validate snapshot + manifest and return a compact summary for logs/CLI."""

    snapshot_path = Path(snapshot_path)
    if not snapshot_path.exists():
        raise ValueError(f"Snapshot not found: {snapshot_path}")

    manifest = _load_manifest(snapshot_path, manifest_path=manifest_path)
    scope = manifest.data["scope"]
    allowed_parts = {str(part) for part in scope["parts"]}
    declared_titles = [str(title) for title in scope["titles"]]

    validate_snapshot_payload(snapshot_path)

    parts_seen: set[str] = set()
    for lineno, rec in _iter_snapshot_records(snapshot_path):
        canonical = normalize_ear_section_id(rec.get("section_id"))
        if canonical is None:
            # validate_snapshot_payload already guards this; keep defensive fallback.
            raise ValueError(f"{snapshot_path}:{lineno} invalid section_id")
        part = _extract_part(canonical)
        parts_seen.add(part)
        if allowed_parts and part not in allowed_parts:
            raise ValueError(
                f"{snapshot_path}:{lineno} part '{part}' not declared in manifest scope.parts"
            )

    if allowed_parts:
        missing_parts = sorted(allowed_parts - parts_seen)
        if missing_parts:
            raise ValueError(
                f"{manifest.path}: scope.parts contains part(s) not present in payload: {', '.join(missing_parts)}"
            )

    _validate_payload_binding(snapshot_path, manifest)

    return SnapshotValidationSummary(
        snapshot_path=snapshot_path,
        manifest=manifest,
        section_count=sum(1 for _ in _iter_snapshot_records(snapshot_path)),
        title_count=len(declared_titles),
        part_count=len(parts_seen),
        payload_bytes=snapshot_path.stat().st_size,
    )


def require_offline_snapshot_manifest(snapshot_path: Path, *, manifest_path: Path | None = None) -> OfflineSnapshotManifest:
    """Fail-fast helper used by builders to require a valid bound manifest."""

    summary = validate_offline_snapshot(snapshot_path, manifest_path=manifest_path)
    return summary.manifest


__all__ = [
    "MANIFEST_VERSION",
    "OfflineSnapshotManifest",
    "SnapshotValidationSummary",
    "compute_sha256_hex",
    "discover_manifest_path",
    "validate_snapshot_payload",
    "validate_offline_snapshot",
    "require_offline_snapshot_manifest",
]
