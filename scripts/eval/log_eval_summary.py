from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


def format_summary(metrics: dict, metrics_path: Path) -> str:
    dataset_id = metrics.get("dataset_id") or "n/a"
    task = metrics.get("task") or "n/a"
    accuracy = metrics.get("accuracy", 0.0)
    label_accuracy = metrics.get("label_accuracy", 0.0)
    unanswerable_accuracy = metrics.get("unanswerable_accuracy", 0.0)
    model = metrics.get("model_path") or "n/a"
    kg_digest = metrics.get("kg_state_digest") or "n/a"
    timestamp = metrics.get("timestamp") or "n/a"
    return (
        f"[{timestamp}] dataset={dataset_id} task={task} "
        f"model={model} accuracy={accuracy:.4f} "
        f"label_accuracy={label_accuracy:.4f} "
        f"unanswerable_accuracy={unanswerable_accuracy:.4f} "
        f"kg_digest={kg_digest} file={metrics_path}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit a one-line summary for eval metrics JSON files."
    )
    parser.add_argument(
        "metrics",
        type=Path,
        help="Path to metrics JSON emitted by eval-benchmark.",
    )
    args = parser.parse_args(argv)
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    print(format_summary(metrics, args.metrics))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
