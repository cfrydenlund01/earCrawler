from __future__ import annotations

from earCrawler.trace.trace_pack import provenance_hash, validate_trace_pack


def _base_pack() -> dict[str, object]:
    return {
        "trace_id": "trace-1",
        "question_hash": "qhash",
        "answer_text": "Answer",
        "label": "true",
        "section_quotes": [
            {
                "section_id": "EAR-740.1",
                "quote": "License exceptions are conditional.",
                "source_url": "https://example/740",
                "score": 0.8,
            }
        ],
        "kg_paths": [
            {
                "path_id": "path-2",
                "edges": [
                    {"source": "b", "predicate": "p2", "target": "c"},
                    {"source": "a", "predicate": "p1", "target": "b"},
                ],
            }
        ],
        "citations": [
            {"section_id": "740.1", "quote": "License exceptions are conditional.", "span_id": "", "source": "model"}
        ],
        "retrieval_metadata": [
            {"id": "EAR-740.1", "section": "EAR-740.1", "score": 0.8, "source": "retrieval", "url": "https://example/740", "title": "s"},
        ],
        "run_provenance": {
            "snapshot_id": "snap-1",
            "snapshot_sha256": "a" * 64,
            "corpus_digest": "b" * 64,
            "index_path": "dist/index/snap-1/index.faiss",
            "embedding_model": "all-MiniLM-L12-v2",
            "llm_provider": "groq",
            "llm_model": "llama-3.1-8b",
        },
    }


def test_provenance_hash_is_deterministic_for_equivalent_payloads() -> None:
    pack_a = _base_pack()
    pack_b = _base_pack()
    pack_b["kg_paths"] = [
        {
            "path_id": "path-2",
            "edges": [
                {"source": "a", "predicate": "p1", "target": "b"},
                {"source": "b", "predicate": "p2", "target": "c"},
            ],
        }
    ]

    assert provenance_hash(pack_a) == provenance_hash(pack_b)


def test_validate_trace_pack_enforces_required_fields_and_hash() -> None:
    pack = _base_pack()
    pack["provenance_hash"] = provenance_hash(pack)
    assert validate_trace_pack(pack) == []

    broken = dict(pack)
    broken["provenance_hash"] = "0" * 64
    issues = validate_trace_pack(broken)
    assert any(issue.field == "provenance_hash" for issue in issues)


def test_validate_trace_pack_requires_kg_paths_when_requested() -> None:
    pack = _base_pack()
    pack["kg_paths"] = []
    pack["provenance_hash"] = provenance_hash(pack)
    issues = validate_trace_pack(pack, require_kg_paths=True)
    assert any(issue.field == "kg_paths" for issue in issues)


def test_validate_trace_pack_requires_run_provenance_when_requested() -> None:
    pack = _base_pack()
    pack["run_provenance"] = {}
    pack["provenance_hash"] = provenance_hash(pack)
    issues = validate_trace_pack(pack, require_run_provenance=True)
    assert any(issue.field.startswith("run_provenance.") for issue in issues)
