from __future__ import annotations

import json
from pathlib import Path

from earCrawler.config.llm_secrets import LLMConfig, ProviderConfig
from scripts.eval import eval_rag_llm


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_evaluate_dataset_passes_effective_date_to_rag(monkeypatch, tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "id": "item-1",
                "task": "ear_compliance",
                "question": "Q?",
                "ground_truth": {"answer_text": "A", "label": "permitted"},
                "ear_sections": [],
                "kg_entities": [],
                "evidence": {"doc_spans": [], "kg_nodes": []},
                "temporal": {"effective_date": "2024-01-01"},
            }
        ],
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"datasets": [{"id": "temporal.v1", "file": str(dataset_path)}]}),
        encoding="utf-8",
    )

    fake_cfg = LLMConfig(
        provider=ProviderConfig(
            provider="groq",
            api_key="x",
            model="stub-model",
            base_url="",
            request_limit=None,
        ),
        enable_remote=True,
    )
    monkeypatch.setattr(eval_rag_llm, "get_llm_config", lambda *a, **k: fake_cfg)

    captured: list[dict[str, object]] = []

    def fake_answer_with_rag(*_args, **kwargs):
        captured.append(dict(kwargs))
        return {
            "answer": "A",
            "label": "permitted",
            "justification": "Because.",
            "used_sections": [],
            "retrieved_docs": [],
            "kg_paths_used": [],
            "kg_expansions": [],
            "trace_id": "trace-1",
            "raw_context": "",
            "raw_answer": '{"label":"permitted","answer_text":"A"}',
            "output_ok": True,
            "output_error": None,
            "retrieval_warnings": [],
            "retrieval_empty": False,
            "retrieval_empty_reason": None,
            "citations": [],
            "evidence_okay": {"ok": True, "reasons": []},
            "assumptions": [],
            "citation_span_ids": [],
        }

    monkeypatch.setattr(eval_rag_llm, "answer_with_rag", fake_answer_with_rag)

    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"
    eval_rag_llm.evaluate_dataset(
        "temporal.v1",
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

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert captured[0]["effective_date"] == "2024-01-01"
    assert payload["results"][0]["effective_date"] == "2024-01-01"
