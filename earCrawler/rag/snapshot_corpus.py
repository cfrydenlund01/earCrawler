from __future__ import annotations

"""Deterministic snapshot -> retrieval corpus rebuild helpers."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from earCrawler.rag.build_corpus import (
    build_retrieval_corpus,
    compute_corpus_digest,
    write_corpus_jsonl,
)
from earCrawler.rag.corpus_contract import (
    load_corpus_jsonl,
    normalize_ear_section_id,
    require_valid_corpus,
)
from earCrawler.rag.offline_snapshot_manifest import discover_manifest_path, compute_sha256_hex


BUILD_LOG_VERSION = "retrieval-corpus-build.v1"


@dataclass(frozen=True)
class SnapshotCorpusBundle:
    snapshot_id: str
    output_dir: Path
    corpus_path: Path
    build_log_path: Path
    corpus_digest: str
    corpus_sha256: str
    doc_count: int
    unique_section_count: int
    expected_section_count: int
    missing_expected_sections: tuple[str, ...]


def _resolve_dataset_file(manifest_path: Path, entry_file: str) -> Path:
    candidate = Path(entry_file)
    if candidate.is_absolute():
        return candidate
    if candidate.exists():
        return candidate
    return (manifest_path.parent / candidate).resolve()


def _iter_jsonl_objects(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except Exception as exc:
                raise ValueError(f"{path}:{lineno} invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{lineno} expected object, got {type(payload).__name__}")
            yield payload


def _normalize_sections_from_item(item: Mapping[str, Any]) -> set[str]:
    found: set[str] = set()
    for value in item.get("ear_sections") or []:
        canonical = normalize_ear_section_id(value)
        if canonical:
            found.add(canonical)

    evidence = item.get("evidence") or {}
    doc_spans = evidence.get("doc_spans") or []
    for span in doc_spans:
        if not isinstance(span, Mapping):
            continue
        span_id = normalize_ear_section_id(span.get("span_id"))
        if span_id:
            found.add(span_id)
            continue
        doc_id = normalize_ear_section_id(span.get("doc_id"))
        if doc_id:
            found.add(doc_id)
    return found


def collect_expected_sections_from_eval_manifest(
    manifest_path: Path,
    *,
    dataset_ids: Sequence[str] | None = None,
    include_v2_only: bool = True,
) -> tuple[set[str], list[str]]:
    """Collect expected canonical section IDs from eval datasets."""

    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise ValueError(f"Dataset manifest not found: {manifest_path}")

    try:
        manifest_obj = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid dataset manifest JSON: {manifest_path}: {exc}") from exc
    if not isinstance(manifest_obj, dict):
        raise ValueError(f"Dataset manifest must be an object: {manifest_path}")

    all_entries = manifest_obj.get("datasets") or []
    if not isinstance(all_entries, list):
        raise ValueError(f"{manifest_path}: 'datasets' must be an array")

    selected = set(dataset_ids or [])
    selected_ids: list[str] = []
    section_ids: set[str] = set()
    for entry in all_entries:
        if not isinstance(entry, Mapping):
            continue
        dataset_id = str(entry.get("id") or "").strip()
        if not dataset_id:
            continue
        if selected and dataset_id not in selected:
            continue
        if not selected and include_v2_only and not dataset_id.endswith(".v2"):
            continue

        raw_file = str(entry.get("file") or "").strip()
        if not raw_file:
            raise ValueError(f"{manifest_path}: dataset '{dataset_id}' missing 'file'")
        dataset_file = _resolve_dataset_file(manifest_path, raw_file)
        if not dataset_file.exists():
            raise ValueError(f"Dataset file not found for '{dataset_id}': {dataset_file}")
        selected_ids.append(dataset_id)
        for item in _iter_jsonl_objects(dataset_file):
            section_ids.update(_normalize_sections_from_item(item))

    if selected:
        missing_datasets = sorted(selected - set(selected_ids))
        if missing_datasets:
            raise ValueError(
                f"Dataset id(s) not found in {manifest_path}: {', '.join(missing_datasets)}"
            )

    return section_ids, sorted(selected_ids)


def _count_non_empty_str(docs: Sequence[Mapping[str, Any]], key: str) -> int:
    return sum(1 for doc in docs if isinstance(doc.get(key), str) and bool(str(doc.get(key)).strip()))


def build_snapshot_corpus_bundle(
    *,
    snapshot: Path,
    snapshot_manifest: Path | None = None,
    out_base: Path = Path("dist") / "corpus",
    source_ref: str | None = None,
    chunk_max_chars: int = 6000,
    preflight: bool = True,
    check_expected_sections: bool = True,
    dataset_manifest: Path = Path("eval") / "manifest.json",
    dataset_ids: Sequence[str] | None = None,
    include_v2_only: bool = True,
) -> SnapshotCorpusBundle:
    """Rebuild a snapshot corpus deterministically under ``out_base/snapshot_id``."""

    docs = build_retrieval_corpus(
        snapshot,
        source_ref=source_ref,
        manifest_path=snapshot_manifest,
        preflight_validate_snapshot=preflight,
        chunk_max_chars=chunk_max_chars,
    )
    if not docs:
        raise ValueError("Corpus build produced no documents")

    snapshot_id = str(docs[0].get("snapshot_id") or "").strip()
    if not snapshot_id:
        raise ValueError("snapshot_id missing from corpus documents")
    snapshot_sha256 = str(docs[0].get("snapshot_sha256") or "").strip()
    manifest_path = snapshot_manifest or discover_manifest_path(snapshot)

    out_dir = Path(out_base) / snapshot_id
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = out_dir / "retrieval_corpus.jsonl"
    write_corpus_jsonl(corpus_path, docs)

    loaded_docs = load_corpus_jsonl(corpus_path)
    require_valid_corpus(loaded_docs)
    corpus_digest = compute_corpus_digest(loaded_docs)
    corpus_sha256 = compute_sha256_hex(corpus_path)
    section_ids = sorted({str(doc.get("section_id") or "").strip() for doc in loaded_docs if doc.get("section_id")})

    expected_sections: set[str] = set()
    selected_dataset_ids: list[str] = []
    if check_expected_sections:
        expected_sections, selected_dataset_ids = collect_expected_sections_from_eval_manifest(
            dataset_manifest,
            dataset_ids=dataset_ids,
            include_v2_only=include_v2_only,
        )
    missing_expected = sorted(expected_sections - set(section_ids))
    if check_expected_sections and missing_expected:
        raise ValueError(
            "Corpus missing expected section IDs: " + ", ".join(missing_expected[:20])
        )

    total_docs = len(loaded_docs)
    build_log = {
        "schema_version": BUILD_LOG_VERSION,
        "snapshot": {
            "snapshot_id": snapshot_id,
            "snapshot_sha256": snapshot_sha256,
            "manifest_path": str(manifest_path) if manifest_path else None,
        },
        "corpus": {
            "path": corpus_path.name,
            "sha256": corpus_sha256,
            "digest": corpus_digest,
            "doc_count": total_docs,
            "unique_section_count": len(section_ids),
        },
        "metadata_coverage": {
            "section_id": {"present": _count_non_empty_str(loaded_docs, "section_id"), "total": total_docs},
            "title": {"present": _count_non_empty_str(loaded_docs, "title"), "total": total_docs},
            "part": {"present": _count_non_empty_str(loaded_docs, "part"), "total": total_docs},
            "source_ref": {"present": _count_non_empty_str(loaded_docs, "source_ref"), "total": total_docs},
        },
        "smoke": {
            "contract_errors": 0,
            "dataset_manifest": str(dataset_manifest) if check_expected_sections else None,
            "datasets_checked": selected_dataset_ids,
            "expected_section_count": len(expected_sections),
            "missing_expected_sections": missing_expected,
        },
    }
    build_log_path = out_dir / "build_log.json"
    build_log_path.write_text(
        json.dumps(build_log, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return SnapshotCorpusBundle(
        snapshot_id=snapshot_id,
        output_dir=out_dir,
        corpus_path=corpus_path,
        build_log_path=build_log_path,
        corpus_digest=corpus_digest,
        corpus_sha256=corpus_sha256,
        doc_count=total_docs,
        unique_section_count=len(section_ids),
        expected_section_count=len(expected_sections),
        missing_expected_sections=tuple(missing_expected),
    )


__all__ = [
    "BUILD_LOG_VERSION",
    "SnapshotCorpusBundle",
    "build_snapshot_corpus_bundle",
    "collect_expected_sections_from_eval_manifest",
]
