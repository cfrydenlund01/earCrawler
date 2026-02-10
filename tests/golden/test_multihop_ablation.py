from __future__ import annotations

import json
from pathlib import Path

from scripts.eval import eval_rag_llm


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_ablation_compare_writes_both_conditions_and_deltas(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    dataset_path = tmp_path / "multihop.jsonl"
    rows = [
        {
            "id": "mh-1",
            "task": "entity_obligation",
            "question": "Q1",
            "ground_truth": {"answer_text": "Supported", "label": "true"},
            "ear_sections": ["EAR-736.2(b)", "EAR-740.1"],
            "kg_entities": ["https://ear.example.org/entity/acme"],
            "evidence": {
                "doc_spans": [
                    {"doc_id": "EAR-736", "span_id": "736.2(b)"},
                    {"doc_id": "EAR-740", "span_id": "740.1"},
                ],
                "kg_nodes": ["https://ear.example.org/resource/ear/exception/740_1"],
                "kg_paths": ["path:entity/acme_736_2b_T_v2"],
            },
        },
        {
            "id": "mh-2",
            "task": "entity_obligation",
            "question": "Q2",
            "ground_truth": {"answer_text": "Supported", "label": "true"},
            "ear_sections": ["EAR-742.4(a)(1)", "EAR-744.6(b)(3)"],
            "kg_entities": ["https://ear.example.org/entity/acme"],
            "evidence": {
                "doc_spans": [
                    {"doc_id": "EAR-742", "span_id": "742.4(a)(1)"},
                    {"doc_id": "EAR-744", "span_id": "744.6(b)(3)"},
                ],
                "kg_nodes": [
                    "https://ear.example.org/resource/ear/policy/ns_column_1_742_4_a_1"
                ],
                "kg_paths": ["path:entity/acme_742_4a1_T_v2"],
            },
        },
    ]
    _write_jsonl(dataset_path, rows)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "id": "multihop_slice.v1",
                        "file": str(dataset_path),
                        "version": 1,
                        "task": "multihop",
                        "description": "fixture",
                        "num_items": 2,
                    }
                ],
                "references": {
                    "sections": {
                        "EAR-736": ["736.2(b)"],
                        "EAR-740": ["740.1"],
                        "EAR-742": ["742.4(a)(1)"],
                        "EAR-744": ["744.6(b)(3)"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    class DummyProvider:
        def __init__(self) -> None:
            self.provider = "groq"
            self.model = "stub-model"
            self.api_key = "x"
            self.base_url = "http://local"
            self.request_limit = None

    class DummyCfg:
        def __init__(self) -> None:
            self.provider = DummyProvider()
            self.enable_remote = True

    monkeypatch.setattr(eval_rag_llm, "get_llm_config", lambda *a, **k: DummyCfg())

    def fake_answer_with_rag(question: str, **kwargs):
        use_kg = bool(kwargs.get("kg_expansion"))
        trace_id = kwargs.get("trace_id")
        if question == "Q1":
            gt_sections = ["EAR-736.2(b)", "EAR-740.1"]
        else:
            gt_sections = ["EAR-742.4(a)(1)", "EAR-744.6(b)(3)"]
        citations = [{"section_id": gt_sections[0], "quote": "Quoted support"}]
        if use_kg:
            citations.append({"section_id": gt_sections[1], "quote": "Second quoted support"})
        return {
            "answer": "Supported",
            "label": "true",
            "justification": "Supported by excerpts.",
            "citations": citations,
            "retrieved_docs": [
                {
                    "id": gt_sections[0],
                    "section": gt_sections[0],
                    "score": 0.9,
                    "source": "retrieval",
                    "url": "https://example/doc",
                    "title": "doc",
                },
                {
                    "id": gt_sections[1],
                    "section": gt_sections[1],
                    "score": 0.8,
                    "source": "retrieval",
                    "url": "https://example/doc2",
                    "title": "doc2",
                },
            ],
            "kg_paths_used": (
                [
                    {
                        "path_id": f"path-{question}",
                        "start_section_id": gt_sections[0],
                        "edges": [
                            {
                                "source": "a",
                                "predicate": "rel",
                                "target": "b",
                            }
                        ],
                        "graph_iri": "https://ear.example.org/graph/kg/test",
                        "confidence": 0.9,
                    }
                ]
                if use_kg
                else []
            ),
            "kg_expansions": [],
            "trace_id": trace_id,
            "used_sections": gt_sections[:1] if not use_kg else gt_sections,
            "raw_context": "ctx",
            "raw_answer": "{}",
            "retrieval_warnings": [],
            "retrieval_empty": False,
            "retrieval_empty_reason": None,
            "output_ok": True,
            "output_error": None,
            "evidence_okay": {"ok": True, "reasons": ["ok"]},
            "assumptions": [],
            "citation_span_ids": [],
        }

    monkeypatch.setattr(eval_rag_llm, "answer_with_rag", fake_answer_with_rag)

    rc = eval_rag_llm.main(
        [
            "--dataset-id",
            "multihop_slice.v1",
            "--manifest",
            str(manifest_path),
            "--ablation-compare",
            "--ablation-run-id",
            "test-run",
            "--multihop-only",
            "--trace-pack-threshold",
            "0.9",
        ]
    )
    assert rc == 0

    summary_path = tmp_path / "dist" / "ablations" / "test-run" / "ablation_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert "faiss_only" in summary["conditions"]
    assert "faiss_plus_kg" in summary["conditions"]
    assert "deltas" in summary
    assert summary["deltas"]["kg_path_usage_rate"] > 0.0
    assert summary["deltas"]["multihop_evidence_coverage_recall"] > 0.0

