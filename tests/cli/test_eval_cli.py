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
            {"id": "EAR-740.1", "section": "740.1", "text": "License Exceptions intro", "source_url": "http://example/740"},
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
        json.dumps({"datasets": [{"id": "ds1", "file": str(dataset_path)}]}), encoding="utf-8"
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
    _write_jsonl(dataset_path, [{"id": "q1", "question": "?", "ground_truth": {}, "ear_sections": [], "evidence": {}}])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"datasets": [{"id": "ds1", "file": str(dataset_path)}]}), encoding="utf-8"
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
        semantic,
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
                "manifest": Path(manifest_path),
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
    assert calls[0]["manifest"] == manifest_path
    assert (out_dir / "ds1.rag.groq.llama-3.3-70b-versatile.json").exists()
