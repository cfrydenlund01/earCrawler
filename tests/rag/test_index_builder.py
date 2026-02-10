from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from earCrawler.rag.build_corpus import compute_corpus_digest
from earCrawler.rag.corpus_contract import SCHEMA_VERSION
from earCrawler.rag.index_builder import INDEX_META_VERSION, build_faiss_index_from_corpus

np = pytest.importorskip("numpy")


class DummyModel:
    def __init__(self, _name: str) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts, show_progress_bar=False):
        self.calls.append(list(texts))
        return np.ones((len(texts), 4), dtype="float32")


class StubIndex:
    def __init__(self) -> None:
        self.added = []
        self.ids = []
        self.ntotal = 0
        self.returns = (
            np.zeros((1, 2), dtype="float32"),
            np.array([[0, 1]], dtype="int64"),
        )

    def add_with_ids(self, vecs, ids):
        self.added.append(np.array(vecs))
        self.ids.append(np.array(ids))
        self.ntotal = len(ids)

    def search(self, vec, k):
        return self.returns


class StubFaiss(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__()
        self.index = StubIndex()
        self.write_args = None
        self.dim = None

    def IndexFlatL2(self, dim):  # noqa: N802
        self.dim = dim
        return object()

    def IndexIDMap(self, base):  # noqa: N802
        return self.index

    def read_index(self, path):  # noqa: N802
        return self.index

    def write_index(self, index, path):  # noqa: N802
        self.write_args = (index, path)
        Path(path).touch()
        self.index = index


def _install_stubs(monkeypatch):
    faiss_mod = StubFaiss()
    st_mod = SimpleNamespace(SentenceTransformer=lambda name: DummyModel(name))
    monkeypatch.setitem(sys.modules, "faiss", faiss_mod)
    monkeypatch.setitem(sys.modules, "sentence_transformers", st_mod)
    return faiss_mod, st_mod


def _corpus() -> list[dict]:
    return [
        {
            "schema_version": SCHEMA_VERSION,
            "doc_id": "EAR-736.2",
            "section_id": "EAR-736.2",
            "text": "General prohibitions intro.",
            "chunk_kind": "section",
            "source": "ecfr_snapshot",
            "source_ref": "snap-1",
            "snapshot_id": "ecfr-title15-2025-12-31",
            "snapshot_sha256": "a" * 64,
        },
        {
            "schema_version": SCHEMA_VERSION,
            "doc_id": "EAR-736.2(a)",
            "section_id": "EAR-736.2(a)",
            "text": "Paragraph a.",
            "chunk_kind": "subsection",
            "source": "ecfr_snapshot",
            "source_ref": "snap-1",
            "snapshot_id": "ecfr-title15-2025-12-31",
            "snapshot_sha256": "a" * 64,
        },
        {
            "schema_version": SCHEMA_VERSION,
            "doc_id": "EAR-740.1",
            "section_id": "EAR-740.1",
            "text": "License exceptions overview.",
            "chunk_kind": "section",
            "source": "ecfr_snapshot",
            "source_ref": "snap-1",
            "snapshot_id": "ecfr-title15-2025-12-31",
            "snapshot_sha256": "a" * 64,
        },
    ]


def test_index_builder_writes_meta(monkeypatch, tmp_path: Path) -> None:
    faiss_mod, _ = _install_stubs(monkeypatch)
    index_path = tmp_path / "index.faiss"
    meta_path = tmp_path / "index.meta.json"
    corpus_docs = _corpus()

    build_faiss_index_from_corpus(
        corpus_docs,
        index_path=index_path,
        meta_path=meta_path,
        embedding_model="stub-model",
    )
    faiss_mod.index.ntotal = len(corpus_docs)

    assert index_path.exists()
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["schema_version"] == INDEX_META_VERSION
    assert meta["doc_count"] == len(corpus_docs)
    assert meta["snapshot"] == {"snapshot_id": "ecfr-title15-2025-12-31", "snapshot_sha256": "a" * 64}
    rows = meta["rows"]
    doc_ids = [row["doc_id"] for row in rows]
    assert doc_ids == sorted(doc_ids)
    assert meta["corpus_digest"] == compute_corpus_digest(corpus_docs)
    assert faiss_mod.write_args[1] == str(index_path)


def test_retriever_reads_index_and_meta(monkeypatch, tmp_path: Path) -> None:
    faiss_mod, st_mod = _install_stubs(monkeypatch)
    index_path = tmp_path / "index.faiss"
    meta_path = tmp_path / "index.meta.json"
    corpus_docs = _corpus()
    build_faiss_index_from_corpus(
        corpus_docs,
        index_path=index_path,
        meta_path=meta_path,
        embedding_model="stub-model",
    )
    # Return rows in reversed order to check doc/section propagation.
    faiss_mod.index.returns = (
        np.zeros((1, 2), dtype="float32"),
        np.array([[1, 0]], dtype="int64"),
    )

    import importlib
    import earCrawler.rag.retriever as retriever_mod

    importlib.reload(retriever_mod)
    monkeypatch.setattr(retriever_mod, "faiss", faiss_mod)
    monkeypatch.setattr(retriever_mod, "SentenceTransformer", st_mod.SentenceTransformer)
    r = retriever_mod.Retriever(
        SimpleNamespace(),
        SimpleNamespace(),
        model_name="stub-model",
        index_path=index_path,
    )
    results = r.query("hi", k=2)
    assert [res["doc_id"] for res in results] == ["EAR-736.2(a)", "EAR-736.2"]
    assert all("section_id" in res for res in results)
    assert all(res["score"] >= 0 for res in results)
