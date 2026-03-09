from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import eval_rag_llm


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_compare_retrieval_modes_writes_summary(monkeypatch, tmp_path: Path) -> None:
    dataset_id = "ds.hybrid"
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "task": "ear_compliance",
                "question": "Q?",
                "ground_truth": {"answer_text": "A", "label": "permitted"},
                "ear_sections": ["EAR-740.1"],
                "kg_entities": [],
                "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
            }
        ],
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "id": dataset_id,
                        "task": "ear_compliance",
                        "file": str(dataset_path),
                        "version": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_evaluate(
        dataset_id,
        *,
        manifest_path,
        llm_provider,
        llm_model,
        top_k,
        retrieval_mode,
        max_items,
        out_json,
        out_md,
        answer_score_mode,
        semantic_threshold,
        semantic,
        ablation,
        kg_expansion,
        multihop_only,
        emit_hitl_template,
        trace_pack_require_kg_paths,
        trace_pack_required_threshold,
        fallback_max_uses,
    ):
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "dataset_id": dataset_id,
            "num_items": 3,
            "provider": llm_provider,
            "model": llm_model,
            "slice_definition": {"kind": "all"},
            "accuracy": 0.8 if retrieval_mode == "dense" else 0.9,
            "label_accuracy": 0.8 if retrieval_mode == "dense" else 0.9,
            "grounded_rate": 0.7 if retrieval_mode == "dense" else 0.85,
            "citation_metrics": {"supported_rate": 0.6 if retrieval_mode == "dense" else 0.8},
            "citation_pr": {
                "micro": {"precision": 0.6, "recall": 0.6, "f1": 0.6},
                "macro": {"precision": 0.6, "recall": 0.6, "f1": 0.6},
            },
            "evidence_coverage_recall": 0.5 if retrieval_mode == "dense" else 0.75,
            "multihop_metrics": {
                "evidence_coverage_recall": 0.0,
                "kg_path_usage_rate": 0.0,
                "trace_pack_pass_rate": 1.0,
            },
            "fallbacks_used": 0,
            "run_provenance": {
                "corpus_digest": "deadbeef",
                "index_path": str(tmp_path / "index.faiss"),
                "index_sha256": "a" * 64,
                "index_meta_path": str(tmp_path / "index.meta.json"),
                "index_meta_sha256": "b" * 64,
            },
        }
        out_json.write_text(json.dumps(payload), encoding="utf-8")
        out_md.write_text("ok", encoding="utf-8")
        return out_json, out_md

    monkeypatch.setattr(eval_rag_llm, "evaluate_dataset", fake_evaluate)

    summary_path = eval_rag_llm.compare_retrieval_modes(
        dataset_id,
        manifest_path=manifest_path,
        llm_provider="stub",
        llm_model="stub-model",
        top_k=5,
        max_items=3,
        answer_score_mode="semantic",
        semantic_threshold=0.6,
        semantic=False,
        ablation=None,
        kg_expansion=None,
        multihop_only=False,
        emit_hitl_template=None,
        trace_pack_required_threshold=None,
        fallback_max_uses=0,
        out_root=tmp_path / "bench",
        run_id="ds-hybrid-retrieval",
    )

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_path.exists()
    assert payload["comparison_dimension"] == "retrieval_mode"
    assert set(payload["conditions"].keys()) == {"dense", "hybrid"}
    assert payload["deltas"]["accuracy"] == pytest.approx(0.1)
    assert payload["artifacts"]["hybrid"]["eval_json"].endswith(".hybrid.json")
