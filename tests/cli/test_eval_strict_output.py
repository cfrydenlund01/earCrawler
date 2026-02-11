from __future__ import annotations

import json
from pathlib import Path

import pytest

from earCrawler.config.llm_secrets import LLMConfig, ProviderConfig
from scripts.eval import eval_rag_llm


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_eval_counts_schema_failures(monkeypatch, tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "question": "Q1",
                "ground_truth": {"answer_text": "Yes", "label": "permitted"},
                "ear_sections": [],
            },
            {
                "id": "item-2",
                "question": "Q2",
                "ground_truth": {"answer_text": "No", "label": "license_required"},
                "ear_sections": [],
            },
        ],
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"datasets": [{"id": "ds1", "file": str(dataset_path)}]}),
        encoding="utf-8",
    )

    fake_cfg = LLMConfig(
        provider=ProviderConfig(
            provider="groq", api_key="x", model="m", base_url="", request_limit=None
        ),
        enable_remote=True,
    )
    monkeypatch.setattr(eval_rag_llm, "get_llm_config", lambda *a, **k: fake_cfg)

    responses = iter(
        [
            {
                "answer": "Yes",
                "label": "permitted",
                "justification": "Because",
                "used_sections": [],
                "raw_context": "",
                "raw_answer": '{"answer_text":"Yes","label":"permitted","justification":"Because"}',
                "output_ok": True,
                "output_error": None,
                "retrieval_warnings": [],
                "retrieval_empty": False,
                "retrieval_empty_reason": None,
            },
            {
                "answer": None,
                "label": None,
                "justification": None,
                "used_sections": [],
                "raw_context": "",
                "raw_answer": "oops",
                "output_ok": False,
                "output_error": {"code": "invalid_json", "message": "bad", "details": {}},
                "retrieval_warnings": [],
                "retrieval_empty": False,
                "retrieval_empty_reason": None,
            },
        ]
    )

    def fake_answer_with_rag(*_args, **_kwargs):
        return next(responses)

    monkeypatch.setattr(eval_rag_llm, "answer_with_rag", fake_answer_with_rag)

    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"

    eval_rag_llm.evaluate_dataset(
        "ds1",
        manifest_path=manifest_path,
        llm_provider=None,
        llm_model=None,
        top_k=3,
        max_items=None,
        out_json=out_json,
        out_md=out_md,
        answer_score_mode="semantic",
        semantic_threshold=0.6,
        semantic=False,
    )

    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["output_failures"] == 1
    assert report["results"][1]["status"] == "failed_output_schema"
    assert report["results"][1]["output_error"]["code"] == "invalid_json"
    assert report["results"][1]["pred_answer"] == ""
    assert report["accuracy"] < 1.0


def test_eval_reports_fallback_counters(monkeypatch, tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "question": "Q1",
                "ground_truth": {"answer_text": "Yes", "label": "permitted"},
                "ear_sections": [],
            },
        ],
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"datasets": [{"id": "ds1", "file": str(dataset_path)}]}),
        encoding="utf-8",
    )

    fake_cfg = LLMConfig(
        provider=ProviderConfig(
            provider="groq", api_key="x", model="m", base_url="", request_limit=None
        ),
        enable_remote=True,
    )
    monkeypatch.setattr(eval_rag_llm, "get_llm_config", lambda *a, **k: fake_cfg)

    def fake_answer_with_rag(*_args, **_kwargs):
        return {
            "answer": "The export can proceed under the cited conditions.",
            "label": "not_a_known_label",
            "justification": "Because",
            "used_sections": [],
            "raw_context": "",
            "raw_answer": '{"answer_text":"Yes","label":"not_a_known_label","justification":"Because"}',
            "output_ok": True,
            "output_error": None,
            "retrieval_warnings": [],
            "retrieval_empty": False,
            "retrieval_empty_reason": None,
        }

    monkeypatch.setattr(eval_rag_llm, "answer_with_rag", fake_answer_with_rag)

    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"

    eval_rag_llm.evaluate_dataset(
        "ds1",
        manifest_path=manifest_path,
        llm_provider=None,
        llm_model=None,
        top_k=3,
        max_items=None,
        out_json=out_json,
        out_md=out_md,
        answer_score_mode="semantic",
        semantic_threshold=0.6,
        semantic=False,
        fallback_max_uses=2,
    )

    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["fallbacks_used"] == 1
    assert report["fallback_counts"]["infer_label_from_answer"] == 1
    assert report["eval_strictness"]["fallback_threshold_breached"] is False
    assert report["results"][0]["fallbacks_used"] == 1


def test_eval_fails_when_fallback_threshold_exceeded(monkeypatch, tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "question": "Q1",
                "ground_truth": {"answer_text": "Yes", "label": "permitted"},
                "ear_sections": [],
            },
        ],
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"datasets": [{"id": "ds1", "file": str(dataset_path)}]}),
        encoding="utf-8",
    )

    fake_cfg = LLMConfig(
        provider=ProviderConfig(
            provider="groq", api_key="x", model="m", base_url="", request_limit=None
        ),
        enable_remote=True,
    )
    monkeypatch.setattr(eval_rag_llm, "get_llm_config", lambda *a, **k: fake_cfg)

    def fake_answer_with_rag(*_args, **_kwargs):
        return {
            "answer": "The export can proceed under the cited conditions.",
            "label": "not_a_known_label",
            "justification": "Because",
            "used_sections": [],
            "raw_context": "",
            "raw_answer": '{"answer_text":"Yes","label":"not_a_known_label","justification":"Because"}',
            "output_ok": True,
            "output_error": None,
            "retrieval_warnings": [],
            "retrieval_empty": False,
            "retrieval_empty_reason": None,
        }

    monkeypatch.setattr(eval_rag_llm, "answer_with_rag", fake_answer_with_rag)

    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"

    with pytest.raises(RuntimeError, match="Eval strictness failed"):
        eval_rag_llm.evaluate_dataset(
            "ds1",
            manifest_path=manifest_path,
            llm_provider=None,
            llm_model=None,
            top_k=3,
            max_items=None,
            out_json=out_json,
            out_md=out_md,
            answer_score_mode="semantic",
            semantic_threshold=0.6,
            semantic=False,
            fallback_max_uses=0,
        )

    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["fallbacks_used"] == 1
    assert report["eval_strictness"]["fallback_threshold_breached"] is True
