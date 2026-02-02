from __future__ import annotations

from pathlib import Path
import json
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))

import importlib  # noqa: E402
from types import SimpleNamespace  # noqa: E402
import pytest  # noqa: E402

np = pytest.importorskip("numpy")  # noqa: E402
from earCrawler.rag.corpus_contract import SCHEMA_VERSION  # noqa: E402


class DummyModel:
    def __init__(self, _name: str) -> None:
        self.calls: list[list[str]] = []
        self.fail_once = False

    def encode(self, texts, show_progress_bar=False):
        self.calls.append(list(texts))
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("boom")
        return np.ones((len(texts), 3), dtype="float32")


class StubIndex:
    def __init__(self) -> None:
        self.added = []
        self.ids = []
        self.ntotal = 0
        self.returns = (
            np.zeros((1, 5), dtype="float32"),
            np.array([[0, 1, -1, -1, -1]], dtype="int64"),
        )

    def add_with_ids(self, vecs, ids):
        self.added.append(np.array(vecs))
        self.ids.append(np.array(ids))
        self.ntotal = len(ids)

    def search(self, vec, k):
        return self.returns


class IndexIDMapStub(StubIndex):
    """Simple stand-in for faiss.IndexIDMap."""

    def __new__(cls, base):
        base.__class__ = cls
        return base

    def __init__(self, *_a, **_kw):  # noqa: D401
        """No-op constructor."""


class StubFaiss(SimpleNamespace):
    IndexIDMap = IndexIDMapStub

    def __init__(self, index: StubIndex) -> None:
        super().__init__()
        self.index = index
        self.write_args = None

    def IndexFlatL2(self, dim):  # noqa: N802 - mimics faiss API
        self.dim = dim
        return object()

    # IndexIDMap class is callable; index returned via __new__

    def read_index(self, path):  # noqa: N802
        return self.index

    def write_index(self, index, path):  # noqa: N802
        self.write_args = (index, path)
        Path(path).touch()


def _doc(doc_id: str, text: str, *, chunk_kind: str = "section") -> dict:
    section_id = doc_id.split("#", 1)[0]
    return {
        "schema_version": SCHEMA_VERSION,
        "doc_id": doc_id,
        "section_id": section_id,
        "text": text,
        "chunk_kind": chunk_kind,
        "source": "ecfr_snapshot",
        "source_ref": "test-snapshot",
    }


def _load_retriever(monkeypatch, tmp_path, fail_encode=False):
    index = StubIndex()
    faiss_mod = StubFaiss(index)
    monkeypatch.setitem(sys.modules, "faiss", faiss_mod)
    st_mod = SimpleNamespace(SentenceTransformer=lambda name: DummyModel(name))
    monkeypatch.setitem(sys.modules, "sentence_transformers", st_mod)
    tg_mod = SimpleNamespace(TradeGovClient=object)
    fr_mod = SimpleNamespace(FederalRegisterClient=object)
    pkg_mod = SimpleNamespace(
        TradeGovClient=object,
        TradeGovError=Exception,
        FederalRegisterClient=object,
        FederalRegisterError=Exception,
    )
    monkeypatch.setitem(sys.modules, "api_clients.tradegov_client", tg_mod)
    monkeypatch.setitem(
        sys.modules,
        "api_clients.federalregister_client",
        fr_mod,
    )
    monkeypatch.setitem(sys.modules, "api_clients", pkg_mod)
    import earCrawler.rag.retriever as retriever

    importlib.reload(retriever)
    monkeypatch.setattr(
        retriever.Retriever,
        "_load_index",
        lambda self, dim, allow_create=False: index,
    )
    monkeypatch.setattr(
        retriever.Retriever,
        "_create_index",
        lambda self, dim: index,
    )
    model = DummyModel("x")
    model.fail_once = fail_encode
    monkeypatch.setattr(retriever, "SentenceTransformer", lambda name: model)
    monkeypatch.setattr(retriever, "faiss", faiss_mod)
    r = retriever.Retriever(
        SimpleNamespace(),
        SimpleNamespace(),
        index_path=Path(tmp_path / "idx.faiss"),
    )
    return r, model, index, faiss_mod, retriever


def test_add_documents_creates_index(monkeypatch, tmp_path):
    r, model, index, faiss_mod, _retriever = _load_retriever(monkeypatch, tmp_path)
    docs = [_doc("EAR-736.2", "a"), _doc("EAR-736.3", "b")]
    r.add_documents(docs)
    assert len(index.added[0]) == 2
    assert faiss_mod.write_args[1] == str(r.index_path)
    meta = json.loads(r.meta_path.read_text(encoding="utf-8"))
    assert meta["doc_count"] == 2
    assert [row["doc_id"] for row in meta["rows"]] == ["EAR-736.2", "EAR-736.3"]


def test_add_documents_empty(monkeypatch, tmp_path):
    r, _m, index, faiss_mod, _retriever = _load_retriever(monkeypatch, tmp_path)
    r.add_documents([])
    assert index.added == []
    assert not r.index_path.exists()


def test_query_returns_docs(monkeypatch, tmp_path):
    r, model, index, faiss_mod, _retriever = _load_retriever(monkeypatch, tmp_path)
    docs = [_doc("EAR-736.2", "a"), _doc("EAR-736.3", "b")]
    r.add_documents(docs)
    result = r.query("hi", k=2)
    assert result == [
        {**docs[0], "score": 1.0},
        {**docs[1], "score": 1.0},
    ]


def test_query_no_index(monkeypatch, tmp_path):
    r, _m, _index, _f, retriever_mod = _load_retriever(monkeypatch, tmp_path)
    with pytest.raises(retriever_mod.IndexMissingError):
        r.query("hi")


def test_retry_on_encode_failure(monkeypatch, tmp_path):
    r, model, index, _f, _retriever = _load_retriever(
        monkeypatch,
        tmp_path,
        fail_encode=True,
    )
    docs = [_doc("EAR-700.1", "a")]
    r.add_documents(docs)
    # encode should be called twice due to retry
    assert len(model.calls) == 2


def test_query_missing_metadata(monkeypatch, tmp_path):
    r, _m, _index, _f, retriever_mod = _load_retriever(monkeypatch, tmp_path)
    r.index_path.parent.mkdir(parents=True, exist_ok=True)
    r.index_path.touch()
    with pytest.raises(retriever_mod.IndexBuildRequiredError):
        r.query("hi")


def test_query_returns_empty_when_no_hits(monkeypatch, tmp_path):
    r, _m, index, _f, _retriever = _load_retriever(monkeypatch, tmp_path)
    docs = [_doc("EAR-736.2", "a"), _doc("EAR-736.3", "b")]
    r.add_documents(docs)
    index.returns = (
        np.zeros((1, 3), dtype="float32"),
        np.array([[-1, -1, -1]], dtype="int64"),
    )
    result = r.query("hi", k=3)
    assert result == []


def test_missing_optional_dependency_raises(monkeypatch, tmp_path):
    import importlib
    import earCrawler.rag.retriever as retriever_mod

    importlib.reload(retriever_mod)
    monkeypatch.setattr(retriever_mod, "SentenceTransformer", None)
    monkeypatch.setattr(retriever_mod, "faiss", None)
    monkeypatch.setattr(
        retriever_mod,
        "import_optional",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("missing dep")),
    )
    with pytest.raises(retriever_mod.RetrieverUnavailableError):
        retriever_mod.Retriever(
            SimpleNamespace(),
            SimpleNamespace(),
            index_path=tmp_path / "x.faiss",
        )
