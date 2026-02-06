from __future__ import annotations

import json
from pathlib import Path

import pytest

from api_clients.llm_client import LLMProviderError
from scripts.eval import eval_rag_llm


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


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


def _manifest(tmp_path: Path, dataset_id: str, dataset_path: Path, references: dict) -> Path:
    manifest = {
        "datasets": [
            {
                "id": dataset_id,
                "task": "ear_compliance",
                "file": str(dataset_path),
                "version": 1,
                "description": "regression fixture",
                "num_items": 1,
            }
        ],
        "references": references,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _response_template(
    *,
    label: str,
    answer: str,
    citations: list[dict],
    used_sections: list[str] | None = None,
    retrieved_docs: list[dict] | None = None,
    output_ok: bool = True,
):
    return {
        "question": "",
        "answer": answer,
        "label": label,
        "justification": answer,
        "citations": citations,
        "retrieved_docs": retrieved_docs or [],
        "trace_id": "trace",
        "used_sections": used_sections or [],
        "raw_context": "",
        "raw_answer": "{}",
        "retrieval_warnings": [],
        "retrieval_empty": False,
        "retrieval_empty_reason": None,
        "output_ok": output_ok,
        "output_error": None if output_ok else {"code": "invalid_json", "message": "bad"},
        "evidence_okay": {"ok": True, "reasons": ["ok"]},
        "assumptions": [],
        "citation_span_ids": [],
    }


def test_retrieval_miss_is_flagged(monkeypatch, tmp_path: Path) -> None:
    dataset_id = "ds.miss"
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "task": "ear_compliance",
                "question": "Where is 736.2(b)?",
                "ground_truth": {"answer_text": "Yes", "label": "true"},
                "ear_sections": ["EAR-736.2(b)"],
                "kg_entities": [],
                "evidence": {"doc_spans": [{"doc_id": "EAR-736", "span_id": "736.2(b)"}], "kg_nodes": [], "kg_paths": []},
            }
        ],
    )
    manifest_path = _manifest(
        tmp_path,
        dataset_id,
        dataset_path,
        {"sections": {"EAR-736": ["736.2(b)"], "EAR-740": ["740.1"]}},
    )

    responses = {
        "Where is 736.2(b)?": _response_template(
            label="true",
            answer="Cites 740.1 instead.",
            citations=[{"section_id": "EAR-740.1", "quote": "incorrect cite"}],
            used_sections=["EAR-740.1"],
            retrieved_docs=[{"id": "doc-740", "section": "EAR-740.1", "url": "u", "title": "t", "score": 0.9, "source": "retrieval"}],
        )
    }

    def fake_answer_with_rag(question: str, **_kwargs):
        return responses[question]

    _stub_llm(monkeypatch)
    monkeypatch.setattr(eval_rag_llm, "answer_with_rag", fake_answer_with_rag)

    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"
    eval_rag_llm.evaluate_dataset(
        dataset_id,
        manifest_path=manifest_path,
        llm_provider="stub",
        llm_model="stub-model",
        top_k=1,
        max_items=None,
        out_json=out_json,
        out_md=out_md,
        answer_score_mode="semantic",
        semantic_threshold=0.6,
        semantic=False,
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    res = payload["results"][0]
    assert res["missing_ground_truth_in_retrieval"] is True
    assert res["citation_recall"] < 1.0
    assert res["citation_fn"] > 0
    assert res["status_category"] == "retrieval_miss_gt_section"


def test_reserved_section_is_error(monkeypatch, tmp_path: Path) -> None:
    dataset_id = "ds.reserved"
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "task": "ear_compliance",
                "question": "Reserved?",
                "ground_truth": {"answer_text": "Supported", "label": "true"},
                "ear_sections": ["EAR-740.1"],
                "kg_entities": [],
                "evidence": {"doc_spans": [{"doc_id": "EAR-740", "span_id": "740.1"}], "kg_nodes": [], "kg_paths": []},
            }
        ],
    )
    manifest_path = _manifest(
        tmp_path,
        dataset_id,
        dataset_path,
        {"sections": {"EAR-740": [{"id": "740.1", "reserved": True}]}},
    )

    responses = {
        "Reserved?": _response_template(
            label="true",
            answer="Reserved cite.",
            citations=[{"section_id": "EAR-740.1", "quote": "reserved cite"}],
            used_sections=["EAR-740.1"],
            retrieved_docs=[{"id": "doc-740", "section": "EAR-740.1", "url": "u", "title": "t", "score": 0.9, "source": "retrieval"}],
        )
    }

    def fake_answer_with_rag(question: str, **_kwargs):
        return responses[question]

    _stub_llm(monkeypatch)
    monkeypatch.setattr(eval_rag_llm, "answer_with_rag", fake_answer_with_rag)

    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"
    eval_rag_llm.evaluate_dataset(
        dataset_id,
        manifest_path=manifest_path,
        llm_provider="stub",
        llm_model="stub-model",
        top_k=1,
        max_items=None,
        out_json=out_json,
        out_md=out_md,
        answer_score_mode="semantic",
        semantic_threshold=0.6,
        semantic=False,
    )

    res = json.loads(out_json.read_text(encoding="utf-8"))["results"][0]
    assert any(err.get("code") == "reserved_cited" for err in res["citation_errors"])
    assert res["status_category"] == "citation_wrong"
    assert res["citation_precision"] == pytest.approx(1.0)
    assert res["citation_recall"] == pytest.approx(1.0)


def test_out_of_scope_requires_refusal(monkeypatch, tmp_path: Path) -> None:
    dataset_id = "ds.refusal"
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "task": "unanswerable",
                "question": "Out of scope?",
                "ground_truth": {"answer_text": "Decline", "label": "unanswerable"},
                "ear_sections": [],
                "kg_entities": [],
                "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
            }
        ],
    )
    manifest_path = _manifest(
        tmp_path,
        dataset_id,
        dataset_path,
        {"sections": {"EAR-736": ["736.2(b)"]}},
    )

    responses = {
        "Out of scope?": _response_template(
            label="permitted",
            answer="Improper answer.",
            citations=[{"section_id": "EAR-736.2(b)", "quote": "wrong cite"}],
            used_sections=["EAR-736.2(b)"],
            retrieved_docs=[{"id": "doc-736", "section": "EAR-736.2(b)", "url": "u", "title": "t", "score": 0.9, "source": "retrieval"}],
        )
    }

    def fake_answer_with_rag(question: str, **_kwargs):
        return responses[question]

    _stub_llm(monkeypatch)
    monkeypatch.setattr(eval_rag_llm, "answer_with_rag", fake_answer_with_rag)

    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"
    eval_rag_llm.evaluate_dataset(
        dataset_id,
        manifest_path=manifest_path,
        llm_provider="stub",
        llm_model="stub-model",
        top_k=1,
        max_items=None,
        out_json=out_json,
        out_md=out_md,
        answer_score_mode="semantic",
        semantic_threshold=0.6,
        semantic=False,
    )

    res = json.loads(out_json.read_text(encoding="utf-8"))["results"][0]
    assert res["status_category"] == "refusal_expected_missing"
    assert res["citation_precision"] == pytest.approx(0.0)
    assert res["citation_recall"] == pytest.approx(1.0)


def test_infra_error_is_separated(monkeypatch, tmp_path: Path) -> None:
    dataset_id = "ds.infra"
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "task": "ear_compliance",
                "question": "Infra?",
                "ground_truth": {"answer_text": "Yes", "label": "true"},
                "ear_sections": ["EAR-736.2(b)"],
                "kg_entities": [],
                "evidence": {"doc_spans": [{"doc_id": "EAR-736", "span_id": "736.2(b)"}], "kg_nodes": [], "kg_paths": []},
            }
        ],
    )
    manifest_path = _manifest(
        tmp_path,
        dataset_id,
        dataset_path,
        {"sections": {"EAR-736": ["736.2(b)"]}},
    )

    def failing_answer_with_rag(*_args, **_kwargs):
        raise LLMProviderError("llm_down")

    _stub_llm(monkeypatch)
    monkeypatch.setattr(eval_rag_llm, "answer_with_rag", failing_answer_with_rag)

    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"
    eval_rag_llm.evaluate_dataset(
        dataset_id,
        manifest_path=manifest_path,
        llm_provider="stub",
        llm_model="stub-model",
        top_k=1,
        max_items=None,
        out_json=out_json,
        out_md=out_md,
        answer_score_mode="semantic",
        semantic_threshold=0.6,
        semantic=False,
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    res = payload["results"][0]
    assert res["status_category"] == "infra_error"
    assert res["citation_not_scored_due_to_infra"] is True
    assert payload["citation_pr"]["items_scored"] == 0
    assert payload["citation_pr"]["infra_skipped"] == 1
    assert payload["status_counts"]["infra_error"] == 1
