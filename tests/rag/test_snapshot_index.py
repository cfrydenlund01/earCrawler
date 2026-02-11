from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from earCrawler.rag.build_corpus import compute_corpus_digest
from earCrawler.rag.corpus_contract import SCHEMA_VERSION
from earCrawler.rag.index_builder import INDEX_META_VERSION
from earCrawler.rag.snapshot_index import build_snapshot_index_bundle


def _write_corpus(path: Path) -> list[dict]:
    docs = [
        {
            "schema_version": SCHEMA_VERSION,
            "doc_id": "EAR-736.2",
            "section_id": "EAR-736.2",
            "text": "General prohibitions intro text.",
            "chunk_kind": "section",
            "source": "ecfr_snapshot",
            "source_ref": "snap-1",
            "snapshot_id": "snap-test-1",
            "snapshot_sha256": "a" * 64,
            "title": "General prohibitions",
            "part": "736",
        },
        {
            "schema_version": SCHEMA_VERSION,
            "doc_id": "EAR-740.1",
            "section_id": "EAR-740.1",
            "text": "License exceptions overview text.",
            "chunk_kind": "section",
            "source": "ecfr_snapshot",
            "source_ref": "snap-1",
            "snapshot_id": "snap-test-1",
            "snapshot_sha256": "a" * 64,
            "title": "License exceptions",
            "part": "740",
        },
    ]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for doc in docs:
            handle.write(json.dumps(doc, sort_keys=True) + "\n")
    return docs


def test_build_snapshot_index_bundle_success(monkeypatch, tmp_path: Path) -> None:
    corpus_path = tmp_path / "retrieval_corpus.jsonl"
    docs = _write_corpus(corpus_path)

    def _stub_build(corpus_docs, *, index_path: Path, meta_path: Path, embedding_model: str) -> None:
        ordered = sorted(corpus_docs, key=lambda d: str(d.get("doc_id") or ""))
        index_path.write_bytes(b"stub-faiss-index")
        meta = {
            "schema_version": INDEX_META_VERSION,
            "build_timestamp_utc": "2026-02-10T00:00:00Z",
            "corpus_schema_version": SCHEMA_VERSION,
            "corpus_digest": compute_corpus_digest(ordered),
            "doc_count": len(ordered),
            "embedding_model": embedding_model,
            "snapshot": {"snapshot_id": "snap-test-1", "snapshot_sha256": "a" * 64},
            "rows": [
                {
                    "row_id": idx,
                    "doc_id": doc["doc_id"],
                    "section_id": doc["section_id"],
                    "chunk_kind": doc["chunk_kind"],
                    "source_ref": doc["source_ref"],
                    "text": doc["text"],
                }
                for idx, doc in enumerate(ordered)
            ],
        }
        meta_path.write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    fake_retriever = SimpleNamespace(
        index_path=tmp_path / "dist" / "snap-test-1" / "index.faiss",
        model_name="stub-model",
        enabled=True,
        ready=True,
        failure_type=None,
    )

    def _stub_ensure(_retriever, *, strict: bool = True, warnings=None):
        return fake_retriever

    def _stub_retrieve(query: str, top_k: int = 5, **_kwargs):
        return [
            {
                "section_id": "EAR-736.2",
                "text": f"{query} result text",
                "score": 0.99,
                "raw": {"doc_id": "EAR-736.2"},
            }
        ]

    import earCrawler.rag.snapshot_index as snapshot_index

    monkeypatch.setattr(snapshot_index, "build_faiss_index_from_corpus", _stub_build)
    monkeypatch.setattr(snapshot_index.rag_pipeline, "_ensure_retriever", _stub_ensure)
    monkeypatch.setattr(snapshot_index.rag_pipeline, "retrieve_regulation_context", _stub_retrieve)

    bundle = build_snapshot_index_bundle(
        corpus_path=corpus_path,
        out_base=tmp_path / "dist",
        model_name="stub-model",
        verify_pipeline_env=True,
        smoke_query="General prohibitions",
        smoke_top_k=3,
        expected_sections=["EAR-736.2"],
    )

    assert bundle.snapshot_id == "snap-test-1"
    assert bundle.doc_count == len(docs)
    assert bundle.embedding_model == "stub-model"
    assert bundle.build_timestamp_utc == "2026-02-10T00:00:00Z"
    assert bundle.index_path.exists()
    assert bundle.meta_path.exists()
    assert bundle.build_log_path.exists()
    assert bundle.env_file_path.exists()
    assert bundle.env_ps1_path.exists()
    assert bundle.smoke_result_count == 1
    assert bundle.smoke_expected_hits == 1

    build_log = json.loads(bundle.build_log_path.read_text(encoding="utf-8"))
    assert build_log["env_check"]["ok"] is True
    assert build_log["metadata"]["embedding_model"] == "stub-model"
    assert build_log["metadata"]["doc_count"] == len(docs)
    assert build_log["smoke"]["result_count"] == 1


def test_build_snapshot_index_bundle_raises_on_missing_expected_section(monkeypatch, tmp_path: Path) -> None:
    corpus_path = tmp_path / "retrieval_corpus.jsonl"
    _write_corpus(corpus_path)

    def _stub_build(corpus_docs, *, index_path: Path, meta_path: Path, embedding_model: str) -> None:
        ordered = sorted(corpus_docs, key=lambda d: str(d.get("doc_id") or ""))
        index_path.write_bytes(b"stub-faiss-index")
        meta = {
            "schema_version": INDEX_META_VERSION,
            "build_timestamp_utc": "2026-02-10T00:00:00Z",
            "corpus_schema_version": SCHEMA_VERSION,
            "corpus_digest": compute_corpus_digest(ordered),
            "doc_count": len(ordered),
            "embedding_model": embedding_model,
            "rows": [
                {
                    "row_id": idx,
                    "doc_id": doc["doc_id"],
                    "section_id": doc["section_id"],
                    "chunk_kind": doc["chunk_kind"],
                    "source_ref": doc["source_ref"],
                    "text": doc["text"],
                }
                for idx, doc in enumerate(ordered)
            ],
        }
        meta_path.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")

    fake_retriever = SimpleNamespace(
        index_path=tmp_path / "dist" / "snap-test-1" / "index.faiss",
        model_name="stub-model",
        enabled=True,
        ready=True,
        failure_type=None,
    )

    def _stub_ensure(_retriever, *, strict: bool = True, warnings=None):
        return fake_retriever

    def _stub_retrieve(*_args, **_kwargs):
        return [
            {
                "section_id": "EAR-736.2",
                "text": "smoke result",
                "score": 0.99,
                "raw": {"doc_id": "EAR-736.2"},
            }
        ]

    import earCrawler.rag.snapshot_index as snapshot_index

    monkeypatch.setattr(snapshot_index, "build_faiss_index_from_corpus", _stub_build)
    monkeypatch.setattr(snapshot_index.rag_pipeline, "_ensure_retriever", _stub_ensure)
    monkeypatch.setattr(snapshot_index.rag_pipeline, "retrieve_regulation_context", _stub_retrieve)

    with pytest.raises(ValueError, match="no expected section IDs"):
        build_snapshot_index_bundle(
            corpus_path=corpus_path,
            out_base=tmp_path / "dist",
            model_name="stub-model",
            verify_pipeline_env=True,
            smoke_query="General prohibitions",
            expected_sections=["EAR-999.1"],
        )
