from __future__ import annotations

"""Deterministic FAISS index builder for the retrieval corpus."""

import json
from pathlib import Path
from typing import Iterable, List, Dict, Any

from earCrawler.rag.build_corpus import compute_corpus_digest
from earCrawler.rag.corpus_contract import SCHEMA_VERSION, require_valid_corpus
from earCrawler.utils.import_guard import import_optional

INDEX_META_VERSION = "faiss-index-meta.v1"


def _load_sentence_transformer(model_name: str):
    sentence_transformers = import_optional(
        "sentence_transformers", ["sentence-transformers"]
    )
    return sentence_transformers.SentenceTransformer(model_name)


def _load_faiss():
    return import_optional("faiss", ["faiss-cpu"])


def build_faiss_index_from_corpus(
    corpus_docs: Iterable[Dict[str, Any]],
    *,
    index_path: Path,
    meta_path: Path,
    embedding_model: str,
) -> None:
    """Build a FAISS index + metadata sidecar from validated corpus docs."""

    docs = sorted(corpus_docs, key=lambda d: str(d.get("doc_id") or ""))
    require_valid_corpus(docs)

    model = _load_sentence_transformer(embedding_model)
    vectors = model.encode([str(doc.get("text") or "") for doc in docs], show_progress_bar=False)

    np_mod = import_optional("numpy", ["numpy"])
    vectors_np = np_mod.asarray(vectors).astype("float32")
    if vectors_np.ndim != 2 or vectors_np.shape[0] != len(docs):
        raise ValueError("Embedding model returned unexpected shape.")
    dim = int(vectors_np.shape[1])

    faiss_mod = _load_faiss()
    index = faiss_mod.IndexIDMap(faiss_mod.IndexFlatL2(dim))
    ids = np_mod.arange(len(docs), dtype="int64")
    index.add_with_ids(vectors_np, ids)

    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss_mod.write_index(index, str(index_path))

    rows: List[Dict[str, Any]] = []
    for idx, doc in enumerate(docs):
        row: Dict[str, Any] = {
            "row_id": idx,
            "doc_id": doc.get("doc_id"),
            "section_id": doc.get("section_id") or str(doc.get("doc_id") or "").split("#", 1)[0],
            "chunk_kind": doc.get("chunk_kind"),
            "source_ref": doc.get("source_ref"),
        }
        if doc.get("title"):
            row["title"] = doc.get("title")
        if doc.get("text"):
            row["text"] = doc.get("text")
        rows.append(row)

    snapshot_ids = {str(v) for v in (doc.get("snapshot_id") for doc in docs) if isinstance(v, str) and v.strip()}
    snapshot_sha256s = {str(v) for v in (doc.get("snapshot_sha256") for doc in docs) if isinstance(v, str) and v.strip()}
    snapshot_obj = None
    if len(snapshot_ids) == 1 and len(snapshot_sha256s) == 1:
        snapshot_obj = {"snapshot_id": sorted(snapshot_ids)[0], "snapshot_sha256": sorted(snapshot_sha256s)[0]}

    meta = {
        "schema_version": INDEX_META_VERSION,
        "corpus_schema_version": SCHEMA_VERSION,
        "corpus_digest": compute_corpus_digest(docs),
        "doc_count": len(docs),
        "embedding_model": embedding_model,
        "snapshot": snapshot_obj,
        "rows": rows,
    }
    meta_path = Path(meta_path)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = ["build_faiss_index_from_corpus", "INDEX_META_VERSION"]
