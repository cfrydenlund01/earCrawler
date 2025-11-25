from pathlib import Path
import json

from eval.validate_datasets import validate_datasets


def test_eval_datasets_conform_to_schema() -> None:
    issues = validate_datasets(
        manifest_path=Path("eval") / "manifest.json",
        schema_path=Path("eval") / "schema.json",
        dataset_ids=None,
    )
    assert issues == []


def test_validate_datasets_flags_missing_references(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    dataset_path = tmp_path / "test_dataset.jsonl"
    schema_path = Path("eval") / "schema.json"
    manifest = {
        "kg_state": {"manifest_path": "kg/.kgstate/manifest.json", "digest": "abc"},
        "datasets": [
            {
                "id": "test.v1",
                "task": "test_task",
                "file": str(dataset_path),
                "version": 1,
                "description": "",
                "num_items": 1,
            }
        ],
        "references": {
            "sections": {"DOC1": ["A"]},
            "kg_nodes": ["node://valid"],
            "kg_paths": ["path:valid"],
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    dataset_item = {
        "id": "item1",
        "task": "test_task",
        "question": "Q?",
        "ground_truth": {"answer_text": "A", "label": "label"},
        "ear_sections": [],
        "kg_entities": [],
        "evidence": {
            "doc_spans": [{"doc_id": "UNKNOWN", "span_id": "Z"}],
            "kg_nodes": ["node://invalid"],
            "kg_paths": ["path:invalid"],
        },
    }
    dataset_path.write_text(json.dumps(dataset_item) + "\n", encoding="utf-8")
    issues = validate_datasets(
        manifest_path=manifest_path,
        schema_path=schema_path,
        dataset_ids=None,
    )
    assert len(issues) == 3
