from __future__ import annotations

from pathlib import Path
import json
import pickle
import sys
from datetime import datetime

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


class KeywordModel:
    def __init__(self, _name: str) -> None:
        self.calls: list[list[str]] = []

    def _encode_one(self, text: str):
        lowered = str(text or "").lower()
        if "license" in lowered:
            return np.array([1.0, 0.0, 0.0], dtype="float32")
        if "prohibition" in lowered:
            return np.array([0.0, 1.0, 0.0], dtype="float32")
        return np.array([0.0, 0.0, 1.0], dtype="float32")

    def encode(self, texts, show_progress_bar=False):
        self.calls.append(list(texts))
        return np.asarray([self._encode_one(text) for text in texts], dtype="float32")


class FlatModel:
    def __init__(self, _name: str) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts, show_progress_bar=False):
        self.calls.append(list(texts))
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
        self.threads = None

    def IndexFlatL2(self, dim):  # noqa: N802 - mimics faiss API
        self.dim = dim
        return object()

    # IndexIDMap class is callable; index returned via __new__

    def read_index(self, path):  # noqa: N802
        return self.index

    def write_index(self, index, path):  # noqa: N802
        self.write_args = (index, path)
        Path(path).touch()

    def omp_set_num_threads(self, value):  # noqa: N802
        self.threads = value


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


def _load_retriever(monkeypatch, tmp_path, fail_encode=False, *, backend="faiss", retrieval_mode=None):
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
        backend=backend,
        retrieval_mode=retrieval_mode,
    )
    return r, model, index, faiss_mod, retriever


def test_add_documents_creates_index(monkeypatch, tmp_path):
    r, model, index, faiss_mod, _retriever = _load_retriever(monkeypatch, tmp_path)
    docs = [_doc("EAR-736.2", "a"), _doc("EAR-736.3", "b")]
    r.add_documents(docs)
    assert len(index.added[0]) == 2
    assert faiss_mod.write_args[1] == str(r.index_path)
    meta = json.loads(r.meta_path.read_text(encoding="utf-8"))
    assert isinstance(meta["build_timestamp_utc"], str)
    datetime.fromisoformat(meta["build_timestamp_utc"].replace("Z", "+00:00"))
    assert meta["doc_count"] == 2
    assert [row["doc_id"] for row in meta["rows"]] == ["EAR-736.2", "EAR-736.3"]
    assert not r.legacy_meta_path.exists()


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


def test_query_ignores_legacy_pickle_metadata_by_default(monkeypatch, tmp_path):
    r, _m, _index, _f, retriever_mod = _load_retriever(monkeypatch, tmp_path)
    r.index_path.parent.mkdir(parents=True, exist_ok=True)
    r.index_path.touch()
    with r.legacy_meta_path.open("wb") as fh:
        pickle.dump([_doc("EAR-736.2", "a")], fh)

    with pytest.raises(retriever_mod.IndexBuildRequiredError, match="metadata file missing"):
        r.query("hi")


def test_query_can_load_legacy_pickle_metadata_with_opt_in(monkeypatch, tmp_path):
    monkeypatch.setenv("EARCRAWLER_ENABLE_LEGACY_PICKLE_METADATA", "1")
    r, _m, index, _f, _retriever = _load_retriever(monkeypatch, tmp_path)
    r.index_path.parent.mkdir(parents=True, exist_ok=True)
    r.index_path.touch()
    docs = [_doc("EAR-736.2", "a"), _doc("EAR-736.3", "b")]
    with r.legacy_meta_path.open("wb") as fh:
        pickle.dump(docs, fh)

    result = r.query("hi", k=2)

    assert [row["doc_id"] for row in result] == ["EAR-736.2", "EAR-736.3"]


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


def test_model_instance_cached_across_retrievers(monkeypatch, tmp_path):
    index = StubIndex()
    faiss_mod = StubFaiss(index)
    monkeypatch.setitem(sys.modules, "faiss", faiss_mod)
    calls = {"count": 0}

    def _model_ctor(name: str):
        calls["count"] += 1
        return DummyModel(name)

    st_mod = SimpleNamespace(SentenceTransformer=_model_ctor)
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
    monkeypatch.setitem(sys.modules, "api_clients.federalregister_client", fr_mod)
    monkeypatch.setitem(sys.modules, "api_clients", pkg_mod)
    import earCrawler.rag.retriever as retriever_mod

    importlib.reload(retriever_mod)
    with retriever_mod._CACHE_LOCK:
        retriever_mod._MODEL_CACHE.clear()
    monkeypatch.setattr(retriever_mod, "SentenceTransformer", _model_ctor)
    monkeypatch.setattr(retriever_mod, "faiss", faiss_mod)
    retriever_mod.Retriever(
        SimpleNamespace(),
        SimpleNamespace(),
        model_name="all-MiniLM-L12-v2",
        index_path=Path(tmp_path / "idx1.faiss"),
    )
    retriever_mod.Retriever(
        SimpleNamespace(),
        SimpleNamespace(),
        model_name="all-MiniLM-L12-v2",
        index_path=Path(tmp_path / "idx2.faiss"),
    )
    assert calls["count"] == 1


def test_windows_default_backend_uses_bruteforce_without_faiss(monkeypatch, tmp_path):
    tg_mod = SimpleNamespace(TradeGovClient=object)
    fr_mod = SimpleNamespace(FederalRegisterClient=object)
    pkg_mod = SimpleNamespace(
        TradeGovClient=object,
        TradeGovError=Exception,
        FederalRegisterClient=object,
        FederalRegisterError=Exception,
    )
    monkeypatch.setitem(sys.modules, "api_clients.tradegov_client", tg_mod)
    monkeypatch.setitem(sys.modules, "api_clients.federalregister_client", fr_mod)
    monkeypatch.setitem(sys.modules, "api_clients", pkg_mod)
    monkeypatch.delenv("EARCRAWLER_RETRIEVAL_BACKEND", raising=False)

    import earCrawler.rag.retriever as retriever_mod

    importlib.reload(retriever_mod)
    monkeypatch.setattr(retriever_mod, "SentenceTransformer", lambda name: KeywordModel(name))
    monkeypatch.setattr(retriever_mod, "faiss", None)
    monkeypatch.setattr(retriever_mod.sys, "platform", "win32", raising=False)

    rows = [
        _doc("EAR-740.9", "License exception STA eligibility."),
        _doc("EAR-740.1", "License exception overview."),
        _doc("EAR-736.2", "General prohibition one."),
    ]
    meta_path = tmp_path / "windows.meta.json"
    meta_path.write_text(
        json.dumps({"rows": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    retriever = retriever_mod.Retriever(
        SimpleNamespace(),
        SimpleNamespace(),
        model_name="stub-model",
        index_path=tmp_path / "windows.faiss",
    )

    first = retriever.query("license exception", k=2)
    second = retriever.query("license exception", k=2)

    assert retriever.backend == "bruteforce"
    assert [row["doc_id"] for row in first] == ["EAR-740.1", "EAR-740.9"]
    assert [row["doc_id"] for row in second] == ["EAR-740.1", "EAR-740.9"]
    assert any(row["section_id"] == "EAR-740.1" for row in first)


def test_faiss_backend_breaks_ties_deterministically_on_windows(monkeypatch, tmp_path):
    r, _model, index, faiss_mod, retriever_mod = _load_retriever(
        monkeypatch,
        tmp_path,
        backend="faiss",
    )
    monkeypatch.setattr(retriever_mod.sys, "platform", "win32", raising=False)
    docs = [_doc("EAR-736.3", "b"), _doc("EAR-736.2", "a")]
    r.add_documents(docs)
    index.returns = (
        np.zeros((1, 2), dtype="float32"),
        np.array([[1, 0]], dtype="int64"),
    )

    first = r.query("hi", k=2)
    second = r.query("hi", k=2)

    assert faiss_mod.threads == 1
    assert [row["doc_id"] for row in first] == ["EAR-736.2", "EAR-736.3"]
    assert [row["doc_id"] for row in second] == ["EAR-736.2", "EAR-736.3"]


def test_hybrid_mode_fuses_bm25_with_dense_rank(monkeypatch, tmp_path):
    tg_mod = SimpleNamespace(TradeGovClient=object)
    fr_mod = SimpleNamespace(FederalRegisterClient=object)
    pkg_mod = SimpleNamespace(
        TradeGovClient=object,
        TradeGovError=Exception,
        FederalRegisterClient=object,
        FederalRegisterError=Exception,
    )
    monkeypatch.setitem(sys.modules, "api_clients.tradegov_client", tg_mod)
    monkeypatch.setitem(sys.modules, "api_clients.federalregister_client", fr_mod)
    monkeypatch.setitem(sys.modules, "api_clients", pkg_mod)

    import earCrawler.rag.retriever as retriever_mod

    importlib.reload(retriever_mod)
    monkeypatch.setattr(retriever_mod, "SentenceTransformer", lambda name: FlatModel(name))
    monkeypatch.setattr(retriever_mod, "faiss", None)

    rows = [
        _doc("EAR-736.2", "General prohibitions apply to exports."),
        _doc("EAR-740.1", "License exceptions can authorize some exports."),
    ]
    meta_path = tmp_path / "hybrid.meta.json"
    meta_path.write_text(
        json.dumps({"rows": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    dense = retriever_mod.Retriever(
        SimpleNamespace(),
        SimpleNamespace(),
        model_name="stub-model",
        index_path=tmp_path / "hybrid.faiss",
        backend="bruteforce",
        retrieval_mode="dense",
    )
    hybrid = retriever_mod.Retriever(
        SimpleNamespace(),
        SimpleNamespace(),
        model_name="stub-model",
        index_path=tmp_path / "hybrid.faiss",
        backend="bruteforce",
        retrieval_mode="hybrid",
    )

    dense_results = dense.query("license exception", k=2)
    hybrid_results = hybrid.query("license exception", k=2)
    hybrid_cfg = retriever_mod.describe_retriever_config(hybrid)

    assert [row["doc_id"] for row in dense_results] == ["EAR-736.2", "EAR-740.1"]
    assert [row["doc_id"] for row in hybrid_results] == ["EAR-740.1", "EAR-736.2"]
    assert hybrid_results[0]["retrieval_mode"] == "hybrid"
    assert hybrid_results[0]["bm25_rank"] == 1
    assert hybrid_results[0]["dense_rank"] == 2
    assert hybrid_cfg["mode"] == "hybrid"


def test_invalid_retrieval_mode_raises(monkeypatch, tmp_path):
    tg_mod = SimpleNamespace(TradeGovClient=object)
    fr_mod = SimpleNamespace(FederalRegisterClient=object)
    pkg_mod = SimpleNamespace(
        TradeGovClient=object,
        TradeGovError=Exception,
        FederalRegisterClient=object,
        FederalRegisterError=Exception,
    )
    monkeypatch.setitem(sys.modules, "api_clients.tradegov_client", tg_mod)
    monkeypatch.setitem(sys.modules, "api_clients.federalregister_client", fr_mod)
    monkeypatch.setitem(sys.modules, "api_clients", pkg_mod)

    import earCrawler.rag.retriever as retriever_mod

    importlib.reload(retriever_mod)
    monkeypatch.setattr(retriever_mod, "SentenceTransformer", lambda name: FlatModel(name))
    monkeypatch.setattr(retriever_mod, "faiss", None)

    with pytest.raises(retriever_mod.RetrieverMisconfiguredError, match="Unsupported retrieval mode"):
        retriever_mod.Retriever(
            SimpleNamespace(),
            SimpleNamespace(),
            index_path=tmp_path / "hybrid.faiss",
            backend="bruteforce",
            retrieval_mode="invalid",
        )
