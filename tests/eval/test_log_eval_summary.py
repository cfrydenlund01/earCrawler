from pathlib import Path
import json

from scripts.eval.log_eval_summary import summarize_metrics


def test_log_eval_summary_multiple(tmp_path: Path) -> None:
    path1 = tmp_path / "a.json"
    path2 = tmp_path / "b.json"
    template = {
        "accuracy": 0.5,
        "label_accuracy": 0.4,
        "unanswerable_accuracy": 0.3,
        "model_path": "model",
        "kg_state_digest": "digest",
        "timestamp": "2025-01-01T00:00:00Z",
        "dataset_id": "ds1",
        "task": "task1",
    }
    path1.write_text(
        json.dumps(template | {"dataset_id": "ds1"}), encoding="utf-8"
    )
    path2.write_text(
        json.dumps(template | {"dataset_id": "ds2"}), encoding="utf-8"
    )
    output = summarize_metrics([path1, path2])
    assert "ds1" in output and "ds2" in output
    assert output.startswith("Eval summaries:")
