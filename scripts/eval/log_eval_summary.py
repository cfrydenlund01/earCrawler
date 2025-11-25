from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence, List


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


def summarize_metrics(paths: Sequence[Path]) -> str:
    summaries: List[str] = []
    for metrics_path in paths:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        summaries.append(format_summary(metrics, metrics_path))
    if len(summaries) == 1:
        return summaries[0]
    output_lines = ["Eval summaries:"]
    for summary in summaries:
        output_lines.append(f"- {summary}")
    return "\n".join(output_lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit a one-line summary for eval metrics JSON files."
    )
    parser.add_argument(
        "metrics",
        type=Path,
        nargs="+",
        help="One or more metrics JSON files emitted by eval-benchmark.",
    )
    args = parser.parse_args(argv)
    print(summarize_metrics(args.metrics))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
