from __future__ import annotations

from earCrawler.rag import retriever_backend, retriever_ranking


def test_backend_resolver_defaults_to_platform_backend(monkeypatch) -> None:
    monkeypatch.delenv(retriever_backend.RETRIEVAL_BACKEND_ENV, raising=False)
    monkeypatch.setattr(retriever_backend.sys, "platform", "win32", raising=False)
    backend, source = retriever_backend.resolve_backend_name()
    assert backend == "bruteforce"
    assert source == "default"


def test_backend_resolver_marks_invalid_values_without_promoting() -> None:
    invalid_backend, source = retriever_backend.resolve_backend_name("invalid")
    assert invalid_backend is None
    assert source == "argument"


def test_fusion_prefers_metadata_tie_break_on_equal_scores() -> None:
    metadata = [
        {"doc_id": "EAR-736.3", "section_id": "EAR-736.3"},
        {"doc_id": "EAR-736.2", "section_id": "EAR-736.2"},
    ]
    dense_results = [
        {"doc_id": "EAR-736.3", "score": 0.8},
        {"doc_id": "EAR-736.2", "score": 0.8},
    ]
    bm25_results = [
        {"doc_id": "EAR-736.2", "score": 0.6},
        {"doc_id": "EAR-736.3", "score": 0.6},
    ]

    fused = retriever_ranking.fuse_rankings(
        metadata=metadata,
        dense_results=dense_results,
        bm25_results=bm25_results,
        k=2,
    )
    assert [row["doc_id"] for row in fused] == ["EAR-736.2", "EAR-736.3"]
