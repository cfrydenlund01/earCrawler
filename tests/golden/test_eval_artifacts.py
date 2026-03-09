from __future__ import annotations

import hashlib
import json
from datetime import datetime as real_datetime, timezone as real_timezone
from pathlib import Path

import pytest

from scripts.eval import eval_rag_llm


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def _build_manifest(tmp_path: Path, dataset_id: str, dataset_path: Path) -> Path:
    manifest = {
        "datasets": [
            {
                "id": dataset_id,
                "task": "ear_compliance",
                "file": str(dataset_path),
                "version": 1,
                "description": "golden fixture",
                "num_items": 4,
            }
        ],
        "references": {
            "sections": {
                "EAR-736": ["736.2(b)"],
                "EAR-740": ["740.1"],
            }
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _write_dummy_index_bundle(tmp_path: Path, *, corpus_digest: str) -> tuple[Path, Path]:
    index_dir = tmp_path / "faiss"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / "index.faiss"
    index_path.write_bytes(b"stub-faiss-index")
    meta_path = index_dir / "index.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "schema_version": "faiss-index-meta.v1",
                "build_timestamp_utc": "2025-01-01T00:00:00Z",
                "corpus_digest": corpus_digest,
                "embedding_model": "all-MiniLM-L12-v2",
                "snapshot": {
                    "snapshot_id": "snapshot-test",
                    "snapshot_sha256": "abc123",
                },
            }
        ),
        encoding="utf-8",
    )
    return index_path, meta_path


def _stub_llm(monkeypatch) -> None:
    class DummyProvider:
        def __init__(self) -> None:
            self.provider = "stub"
            self.model = "stub-model"
            self.api_key = "x"
            self.base_url = "http://local"
            self.request_limit = None

    class DummyCfg:
        def __init__(self) -> None:
            self.provider = DummyProvider()
            self.enable_remote = True

    monkeypatch.setattr(eval_rag_llm, "get_llm_config", lambda *args, **kwargs: DummyCfg())


def _stub_datetime(monkeypatch) -> None:
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            tzinfo = tz or real_timezone.utc
            return real_datetime(2025, 1, 1, tzinfo=tzinfo)

    monkeypatch.setattr(eval_rag_llm, "datetime", FixedDateTime)


def test_eval_writes_answer_artifacts_and_citation_metrics(monkeypatch, tmp_path: Path) -> None:
    dataset_id = "ds.golden"
    dataset_path = tmp_path / "dataset.jsonl"
    items = [
        {
            "id": "item-1",
            "task": "ear_compliance",
            "question": "Q1 grounded citation",
            "ground_truth": {"answer_text": "Yes", "label": "true"},
            "ear_sections": ["EAR-736.2(b)"],
            "kg_entities": [],
            "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
        },
        {
            "id": "item-2",
            "task": "ear_compliance",
            "question": "Q2 missing citation",
            "ground_truth": {"answer_text": "No", "label": "false"},
            "ear_sections": [],
            "kg_entities": [],
            "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
        },
        {
            "id": "item-3",
            "task": "ear_compliance",
            "question": "Q3 invalid citation",
            "ground_truth": {"answer_text": "No", "label": "false"},
            "ear_sections": ["EAR-740.1"],
            "kg_entities": [],
            "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
        },
        {
            "id": "item-4",
            "task": "ear_compliance",
            "question": "Q4 overclaim citation",
            "ground_truth": {"answer_text": "No", "label": "false"},
            "ear_sections": ["EAR-740.1"],
            "kg_entities": [],
            "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
        },
    ]
    _write_jsonl(dataset_path, items)
    manifest_path = _build_manifest(tmp_path, dataset_id, dataset_path)

    responses = {
        "Q1 grounded citation": {
            "question": "Q1 grounded citation",
            "answer": "Yes, grounded by 736.2(b).",
            "label": "true",
            "justification": "Supported by EAR-736.2(b).",
            "citations": [{"section_id": "EAR-736.2(b)", "quote": "export is restricted under 736.2(b)"}],
            "retrieved_docs": [
                {
                    "id": "doc-736",
                    "section": "EAR-736.2(b)",
                    "url": "http://example/736",
                    "title": "736 section",
                    "score": 0.9,
                    "source": "retrieval",
                }
            ],
            "trace_id": "trace-1",
            "used_sections": ["EAR-736.2(b)"],
            "raw_context": "[EAR-736.2(b)] export is restricted under 736.2(b)",
            "raw_answer": "{}",
            "retrieval_warnings": [],
            "retrieval_empty": False,
            "retrieval_empty_reason": None,
            "output_ok": True,
            "output_error": None,
            "evidence_okay": {"ok": True, "reasons": ["ok"]},
            "assumptions": [],
            "citation_span_ids": [],
        },
        "Q2 missing citation": {
            "question": "Q2 missing citation",
            "answer": "No citation provided.",
            "label": "false",
            "justification": "",
            "citations": [],
            "retrieved_docs": [],
            "trace_id": "trace-2",
            "used_sections": [],
            "raw_context": "",
            "raw_answer": "{}",
            "retrieval_warnings": [],
            "retrieval_empty": True,
            "retrieval_empty_reason": "no_hits",
            "output_ok": True,
            "output_error": None,
            "evidence_okay": {"ok": True, "reasons": ["ok"]},
            "assumptions": [],
            "citation_span_ids": [],
        },
        "Q3 invalid citation": {
            "question": "Q3 invalid citation",
            "answer": "Unsupported reference.",
            "label": "false",
            "justification": "Bad citation.",
            "citations": [{"section_id": "invalid-ref", "quote": "invalid ref"}],
            "retrieved_docs": [
                {
                    "id": "doc-740",
                    "section": "EAR-740.1",
                    "url": "http://example/740",
                    "title": "740 section",
                    "score": 0.8,
                    "source": "retrieval",
                }
            ],
            "trace_id": "trace-3",
            "used_sections": ["EAR-740.1"],
            "raw_context": "[EAR-740.1] License Exceptions intro",
            "raw_answer": "{}",
            "retrieval_warnings": [],
            "retrieval_empty": False,
            "retrieval_empty_reason": None,
            "output_ok": True,
            "output_error": None,
            "evidence_okay": {"ok": True, "reasons": ["ok"]},
            "assumptions": [],
            "citation_span_ids": [],
        },
        "Q4 overclaim citation": {
            "question": "Q4 overclaim citation",
            "answer": "Claims 742.",
            "label": "false",
            "justification": "Cites 742 but not retrieved.",
            "citations": [{"section_id": "EAR-742.4(a)(1)", "quote": "license required"}],
            "retrieved_docs": [
                {
                    "id": "doc-740",
                    "section": "EAR-740.1",
                    "url": "http://example/740",
                    "title": "740 section",
                    "score": 0.8,
                    "source": "retrieval",
                }
            ],
            "trace_id": "trace-4",
            "used_sections": ["EAR-740.1"],
            "raw_context": "[EAR-740.1] License Exceptions intro",
            "raw_answer": "{}",
            "retrieval_warnings": [],
            "retrieval_empty": False,
            "retrieval_empty_reason": None,
            "output_ok": True,
            "output_error": None,
            "evidence_okay": {"ok": True, "reasons": ["ok"]},
            "assumptions": [],
            "citation_span_ids": [],
        },
    }

    def fake_answer_with_rag(question: str, **kwargs):
        return responses[question]

    _stub_llm(monkeypatch)
    _stub_datetime(monkeypatch)
    monkeypatch.setattr(eval_rag_llm, "answer_with_rag", fake_answer_with_rag)

    out_json = tmp_path / "metrics.json"
    out_md = tmp_path / "metrics.md"

    eval_rag_llm.evaluate_dataset(
        dataset_id,
        manifest_path=manifest_path,
        llm_provider="stub",
        llm_model="stub-model",
        top_k=2,
        max_items=None,
        out_json=out_json,
        out_md=out_md,
        answer_score_mode="semantic",
        semantic_threshold=0.6,
        semantic=False,
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["citation_metrics"]["presence_rate"] == pytest.approx(0.75)
    assert payload["citation_metrics"]["valid_citation_rate"] == pytest.approx(1 / 3)
    assert payload["citation_metrics"]["valid_id_rate"] == pytest.approx(1 / 3)
    assert payload["citation_metrics"]["supported_rate"] == pytest.approx(0.25)
    assert payload["citation_metrics"]["overclaim_rate"] == pytest.approx(0.75)
    assert payload["citation_pr"]["items_scored"] == 4
    assert "status_counts" in payload

    results = payload["results"]
    assert all("citations" in r and "justification" in r for r in results)
    assert "citation_precision" in results[0]
    assert all("citation_validity" in r and "citation_support" in r and "overclaim" in r for r in results)
    assert any(r["citations_errors"] for r in results if r["id"] == "item-2")
    assert any(r["citations_ok"] is True for r in results)
    assert any(r["overclaim"]["overclaim_count"] > 0 for r in results if r["id"] != "item-1")
    assert all(r.get("trace_pack_path") for r in results)

    artifact_dir = tmp_path / "metrics" / "answers" / dataset_id
    artifacts = sorted(artifact_dir.glob("*.answer.json"))
    assert len(artifacts) == 4
    sample = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert set(sample.keys()) == {
        "dataset_id",
        "item_id",
        "question",
        "label",
        "answer",
        "justification",
        "citations",
        "retrieved_docs",
        "kg_paths_used",
        "kg_related_sections",
        "kg_expansion_snippets",
        "trace_id",
        "provider",
        "model",
        "run_id",
        "run_meta",
    }
    assert sample["citations"]
    assert sample["citations"][0]["section_id"] == "EAR-736.2(b)"
    assert sample["retrieved_docs"]

    trace_sample_path = Path(str(results[0]["trace_pack_path"]))
    trace_sample = json.loads(trace_sample_path.read_text(encoding="utf-8"))
    run_provenance = trace_sample.get("run_provenance") or {}
    assert run_provenance.get("snapshot_id")
    assert run_provenance.get("snapshot_sha256")
    assert run_provenance.get("corpus_digest")
    assert run_provenance.get("index_path")
    assert run_provenance.get("embedding_model")
    assert "api_key" not in run_provenance
    assert len(str(trace_sample.get("provenance_hash") or "")) == 64


def test_eval_writes_provenance_snapshot_and_redacts_secrets(
    monkeypatch, tmp_path: Path
) -> None:
    dataset_id = "ds.provenance"
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "task": "ear_compliance",
                "question": "Q provenance",
                "ground_truth": {"answer_text": "Yes", "label": "true"},
                "ear_sections": ["EAR-736.2(b)"],
                "kg_entities": [],
                "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
            }
        ],
    )
    manifest_path = _build_manifest(tmp_path, dataset_id, dataset_path)
    corpus_digest = "deadbeef" * 8
    index_path, meta_path = _write_dummy_index_bundle(tmp_path, corpus_digest=corpus_digest)

    def fake_answer_with_rag(question: str, **kwargs):
        return {
            "question": question,
            "answer": "Yes.",
            "label": "true",
            "justification": "Supported by EAR-736.2(b).",
            "citations": [{"section_id": "EAR-736.2(b)", "quote": "Quoted support"}],
            "retrieved_docs": [
                {
                    "id": "EAR-736.2(b)",
                    "section": "EAR-736.2(b)",
                    "url": "https://example.test/736",
                    "title": "736",
                    "score": 0.9,
                    "source": "retrieval",
                }
            ],
            "trace_id": "trace-provenance",
            "used_sections": ["EAR-736.2(b)"],
            "raw_context": "[EAR-736.2(b)] Quoted support",
            "raw_answer": "{}",
            "retrieval_warnings": [],
            "retrieval_empty": False,
            "retrieval_empty_reason": None,
            "output_ok": True,
            "output_error": None,
            "evidence_okay": {"ok": True, "reasons": ["ok"]},
            "assumptions": [],
            "citation_span_ids": [],
            "kg_paths_used": [],
            "kg_expansions": [],
        }

    _stub_llm(monkeypatch)
    _stub_datetime(monkeypatch)
    monkeypatch.setattr(eval_rag_llm, "answer_with_rag", fake_answer_with_rag)
    monkeypatch.setenv("EARCRAWLER_FAISS_INDEX", str(index_path))
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret-value")
    monkeypatch.setenv("EARCRAWLER_REFUSE_ON_THIN_RETRIEVAL", "1")
    monkeypatch.setenv("EARCRAWLER_THIN_RETRIEVAL_MIN_TOP_SCORE", "0.55")
    monkeypatch.setenv("EARCRAWLER_KG_EXPANSION_PROVIDER", "json_stub")

    out_json = tmp_path / "metrics.json"
    out_md = tmp_path / "metrics.md"
    eval_rag_llm.evaluate_dataset(
        dataset_id,
        manifest_path=manifest_path,
        llm_provider="stub",
        llm_model="stub-model",
        top_k=2,
        retrieval_mode="hybrid",
        max_items=1,
        out_json=out_json,
        out_md=out_md,
        answer_score_mode="semantic",
        semantic_threshold=0.6,
        semantic=False,
    )

    provenance_path = tmp_path / "metrics" / "provenance.json"
    assert provenance_path.exists()
    payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert {
        "git",
        "timestamp_utc",
        "dataset_id",
        "dataset_path",
        "eval_suite",
        "thresholds",
        "corpus_digest",
        "index_digest",
        "index_meta_digest",
        "index_meta_path",
        "retrieval",
        "llm",
        "python",
        "installed_packages_digest",
        "os",
        "env",
    }.issubset(payload.keys())
    assert payload["dataset_id"] == dataset_id
    assert payload["corpus_digest"] == corpus_digest
    assert payload["index_digest"] == hashlib.sha256(index_path.read_bytes()).hexdigest()
    assert payload["index_meta_digest"] == hashlib.sha256(
        meta_path.read_bytes()
    ).hexdigest()
    assert payload["retrieval"]["mode"] == "hybrid"
    assert payload["retrieval"]["backend"] in {"faiss", "bruteforce"}
    assert payload["retrieval"]["fusion"] == {"algorithm": "rrf", "rrf_k": 60}
    assert payload["retrieval"]["k"] == 2
    assert payload["retrieval"]["thin_retrieval_refusal"]["enabled"] is True
    assert payload["retrieval"]["thin_retrieval_refusal"]["min_top_score"] == pytest.approx(
        0.55
    )
    assert payload["llm"]["mode"] == "remote"
    assert payload["llm"]["provider"] == "stub"
    assert payload["llm"]["model"] == "stub-model"
    assert payload["env"]["OPENAI_API_KEY"] == "[REDACTED]"
