from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from earCrawler.cli.__main__ import cli


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_verify_evidence_cli_success(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.jsonl"
    _write_jsonl(
        corpus_path,
        [
            {
                "id": "EAR-740.1",
                "section": "740.1",
                "text": "License Exceptions intro",
                "source_url": "http://example/740",
            },
        ],
    )
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "ear_sections": ["EAR-740.1"],
                "evidence": {"doc_spans": [{"doc_id": "EAR-740", "span_id": "740.1"}]},
            }
        ],
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"datasets": [{"id": "ds1", "file": str(dataset_path)}]}),
        encoding="utf-8",
    )

    runner = CliRunner()
    out_path = tmp_path / "report.json"
    result = runner.invoke(
        cli,
        [
            "eval",
            "verify-evidence",
            "--manifest",
            str(manifest_path),
            "--corpus",
            str(corpus_path),
            "--out",
            str(out_path),
        ],
    )
    assert result.exit_code == 0
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["summary"]["missing_sections"] == []
    assert report["summary"]["missing_spans"] == []


def test_run_rag_cli_invokes_evaluator(monkeypatch, tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "q1",
                "question": "?",
                "ground_truth": {},
                "ear_sections": [],
                "evidence": {},
            }
        ],
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"datasets": [{"id": "ds1", "file": str(dataset_path)}]}),
        encoding="utf-8",
    )

    calls: list[dict] = []
    from scripts.eval import eval_rag_llm

    def fake_eval(
        dataset_id,
        *,
        manifest_path,
        llm_provider,
        llm_model,
        top_k,
        max_items,
        out_json,
        out_md,
        answer_score_mode,
        semantic_threshold,
        semantic,
        **kwargs,
    ):
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text("{}", encoding="utf-8")
        out_md.write_text("ok", encoding="utf-8")
        calls.append(
            {
                "dataset_id": dataset_id,
                "provider": llm_provider,
                "model": llm_model,
                "top_k": top_k,
                "semantic": semantic,
                "max_items": max_items,
                "answer_score_mode": answer_score_mode,
                "semantic_threshold": semantic_threshold,
                "manifest": Path(manifest_path),
                "kwargs": kwargs,
            }
        )
        return out_json, out_md

    monkeypatch.setattr(eval_rag_llm, "evaluate_dataset", fake_eval)

    runner = CliRunner()
    out_dir = tmp_path / "out"
    result = runner.invoke(
        cli,
        [
            "eval",
            "run-rag",
            "--manifest",
            str(manifest_path),
            "--top-k",
            "2",
            "--provider",
            "groq",
            "--model",
            "llama-3.3-70b-versatile",
            "--out-dir",
            str(out_dir),
            "--semantic",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls
    assert calls[0]["dataset_id"] == "ds1"
    assert calls[0]["top_k"] == 2
    assert calls[0]["semantic"] is True
    assert calls[0]["answer_score_mode"] == "semantic"
    assert calls[0]["semantic_threshold"] == 0.6
    assert calls[0]["manifest"] == manifest_path
    assert (out_dir / "ds1.rag.groq.llama-3.3-70b-versatile.json").exists()


def test_fr_coverage_cli_records_ranks(monkeypatch, tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.jsonl"
    _write_jsonl(
        corpus_path,
        [
            {
                "id": "EAR-740.1",
                "section": "740.1",
                "text": "License Exceptions intro",
                "source_url": "http://example/740",
            }
        ],
    )
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "question": "Can I export without a license if a license exception applies?",
                "ear_sections": ["EAR-740.1"],
                "evidence": {"doc_spans": [{"doc_id": "EAR-740", "span_id": "740.1"}]},
            }
        ],
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"datasets": [{"id": "ds1", "file": str(dataset_path)}]}),
        encoding="utf-8",
    )

    from earCrawler.rag import pipeline as rag_pipeline

    monkeypatch.setattr(
        rag_pipeline, "_ensure_retriever", lambda *args, **kwargs: object()
    )

    def fake_retrieve(question: str, top_k: int = 5, *, retriever=None):
        return [
            {
                "section_id": "EAR-736.2(b)",
                "text": "irrelevant",
                "score": 0.9,
                "raw": {},
            },
            {"section_id": "EAR-740.1", "text": "hit", "score": 0.8, "raw": {}},
        ][:top_k]

    monkeypatch.setattr(rag_pipeline, "retrieve_regulation_context", fake_retrieve)

    runner = CliRunner()
    out_path = tmp_path / "report.json"
    result = runner.invoke(
        cli,
        [
            "eval",
            "fr-coverage",
            "--manifest",
            str(manifest_path),
            "--corpus",
            str(corpus_path),
            "--dataset-id",
            "ds1",
            "--retrieval-k",
            "5",
            "--out",
            str(out_path),
            "--no-fail",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(out_path.read_text(encoding="utf-8"))
    items = report["datasets"][0]["items"]
    ranks = items[0]["retrieval"]["ranks"]
    assert ranks["EAR-740.1"] == 2


def test_check_grounding_cli_enforces_thresholds(tmp_path: Path) -> None:
    eval_payload = {
        "results": [
            {
                "id": "item-1",
                "question": "Q1",
                "ground_truth_label": "true",
                "pred_label": "true",
                "expected_sections": ["EAR-740.1"],
                "used_sections": ["EAR-740.1"],
            }
        ]
    }
    eval_json_path = tmp_path / "eval.json"
    eval_json_path.write_text(json.dumps(eval_payload), encoding="utf-8")

    runner = CliRunner()
    out_path = tmp_path / "grounding.json"
    result = runner.invoke(
        cli,
        [
            "eval",
            "check-grounding",
            "--eval-json",
            str(eval_json_path),
            "--out",
            str(out_path),
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["thresholds_ok"] is True
