from __future__ import annotations

from pathlib import Path
from typing import Callable

from earCrawler.rag.build_corpus import build_retrieval_corpus, write_corpus_jsonl
from earCrawler.rag.index_builder import build_faiss_index_from_corpus
from earCrawler.rag.offline_snapshot_manifest import validate_offline_snapshot
from earCrawler.rag.snapshot_corpus import build_snapshot_corpus_bundle


def build_index_from_corpus(
    *,
    input_path: Path,
    index_path: Path,
    model_name: str,
    reset: bool,
    meta_path: Path | None,
) -> tuple[int, Path, Path]:
    resolved_meta = meta_path or index_path.with_suffix(".meta.json")
    if reset:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        for path in (index_path, index_path.with_suffix(".pkl"), resolved_meta):
            if path.exists():
                path.unlink()

    from earCrawler.rag.corpus_contract import load_corpus_jsonl, require_valid_corpus

    docs = load_corpus_jsonl(input_path)
    require_valid_corpus(docs)
    build_faiss_index_from_corpus(
        docs,
        index_path=index_path,
        meta_path=resolved_meta,
        embedding_model=model_name,
    )
    return len(docs), index_path, resolved_meta


def build_corpus_from_snapshot(
    *,
    snapshot: Path,
    snapshot_manifest: Path | None,
    out: Path,
    source_ref: str | None,
    chunk_max_chars: int,
    preflight: bool,
) -> tuple[int, Path]:
    docs = build_retrieval_corpus(
        snapshot,
        source_ref=source_ref,
        manifest_path=snapshot_manifest,
        preflight_validate_snapshot=preflight,
        chunk_max_chars=chunk_max_chars,
    )
    write_corpus_jsonl(out, docs)
    return len(docs), out


def rebuild_snapshot_corpus(
    *,
    snapshot: Path,
    snapshot_manifest: Path | None,
    out_base: Path,
    source_ref: str | None,
    chunk_max_chars: int,
    preflight: bool,
    check_expected_sections: bool,
    dataset_manifest: Path,
    dataset_ids: list[str] | tuple[str, ...] | None,
    v2_only: bool,
):
    resolved_dataset_ids = list(dataset_ids) if dataset_ids else None
    return build_snapshot_corpus_bundle(
        snapshot=snapshot,
        snapshot_manifest=snapshot_manifest,
        out_base=out_base,
        source_ref=source_ref,
        chunk_max_chars=chunk_max_chars,
        preflight=preflight,
        check_expected_sections=check_expected_sections,
        dataset_manifest=dataset_manifest,
        dataset_ids=resolved_dataset_ids,
        include_v2_only=v2_only,
    )


def rebuild_snapshot_index(
    *,
    index_builder: Callable[..., object],
    corpus_path: Path,
    out_base: Path,
    model_name: str,
    verify_env: bool,
    smoke_query: str | None,
    smoke_top_k: int,
    expected_sections: tuple[str, ...],
):
    return index_builder(
        corpus_path=corpus_path,
        out_base=out_base,
        model_name=model_name,
        verify_pipeline_env=verify_env,
        smoke_query=smoke_query,
        smoke_top_k=smoke_top_k,
        expected_sections=list(expected_sections) or None,
    )


def validate_snapshot(
    *,
    snapshot: Path,
    snapshot_manifest: Path | None,
):
    return validate_offline_snapshot(snapshot, manifest_path=snapshot_manifest)
