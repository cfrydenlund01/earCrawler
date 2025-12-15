from __future__ import annotations

from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))

import importlib  # noqa: E402
import pickle  # noqa: E402
from types import SimpleNamespace  # noqa: E402
import pytest  # noqa: E402

np = pytest.importorskip("numpy")  # noqa: E402


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
        self.returns = (
            np.zeros((1, 5), dtype="float32"),
            np.array([[0, 1, -1, -1, -1]], dtype="int64"),
        )

    def add_with_ids(self, vecs, ids):
        self.added.append(np.array(vecs))
        self.ids.append(np.array(ids))

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
    return r, model, index, faiss_mod


def test_add_documents_creates_index(monkeypatch, tmp_path):
    r, model, index, faiss_mod = _load_retriever(monkeypatch, tmp_path)
    docs = [{"text": "a"}, {"text": "b"}]
    r.add_documents(docs)
    assert len(index.added[0]) == 2
    assert faiss_mod.write_args[1] == str(r.index_path)
    meta = pickle.load(open(r.meta_path, "rb"))
    assert meta == docs


def test_add_documents_empty(monkeypatch, tmp_path):
    r, _m, index, faiss_mod = _load_retriever(monkeypatch, tmp_path)
    r.add_documents([])
    assert index.added == []
    assert not r.index_path.exists()


def test_query_returns_docs(monkeypatch, tmp_path):
    r, model, index, faiss_mod = _load_retriever(monkeypatch, tmp_path)
    docs = [{"text": "a"}, {"text": "b"}]
    r.add_documents(docs)
    result = r.query("hi", k=2)
    assert result == [
        {**docs[0], "score": 1.0},
        {**docs[1], "score": 1.0},
    ]


def test_query_no_index(monkeypatch, tmp_path):
    r, _m, index, _f = _load_retriever(monkeypatch, tmp_path)
    result = r.query("hi")
    assert result == []


def test_retry_on_encode_failure(monkeypatch, tmp_path):
    r, model, index, _f = _load_retriever(
        monkeypatch,
        tmp_path,
        fail_encode=True,
    )
    docs = [{"text": "a"}]
    r.add_documents(docs)
    # encode should be called twice due to retry
    assert len(model.calls) == 2
