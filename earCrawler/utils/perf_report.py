from __future__ import annotations

"""Utilities to aggregate performance reports and enforce budgets."""

import json
import math
from pathlib import Path
from typing import Iterable, List, Dict, Tuple

try:
    import yaml
except Exception:  # pragma: no cover - yaml optional at runtime
    yaml = None  # type: ignore


def _percentile(data: List[float], pct: float) -> float:
    if not data:
        return 0.0
    data_sorted = sorted(data)
    k = (len(data_sorted) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return data_sorted[int(k)]
    d0 = data_sorted[f] * (c - k)
    d1 = data_sorted[c] * (k - f)
    return d0 + d1


def merge_segments(runs: Iterable[Dict]) -> Dict[str, Dict]:
    groups: Dict[str, Dict] = {}
    for run in runs:
        for res in run.get("results", []):
            g = res["group"]
            entry = groups.setdefault(g, {"latencies": [], "errors": 0, "timeouts": 0})
            entry["latencies"].extend(res.get("latencies_ms", []))
            entry["errors"] += res.get("errors", 0)
            entry["timeouts"] += res.get("timeouts", 0)
    return groups


def summarize(groups: Dict[str, Dict]) -> Dict[str, Dict[str, float]]:
    summary: Dict[str, Dict[str, float]] = {}
    for g, data in groups.items():
        lats = data["latencies"]
        summary[g] = {
            "count": float(len(lats)),
            "p50_ms": _percentile(lats, 0.5),
            "p90_ms": _percentile(lats, 0.9),
            "p95_ms": _percentile(lats, 0.95),
            "p99_ms": _percentile(lats, 0.99),
            "errors": float(data["errors"]),
            "timeouts": float(data["timeouts"]),
        }
    return summary


def load_json(path: Path) -> Dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_budgets(path: Path, scale: str) -> Dict:
    data = (
        yaml.safe_load(Path(path).read_text())
        if path.suffix in {".yml", ".yaml"}
        else json.loads(Path(path).read_text())
    )
    return data["scales"][scale]


def compare(
    summary: Dict[str, Dict[str, float]], baseline: Dict, budgets: Dict
) -> Tuple[bool, Dict]:
    passed = True
    diff: Dict[str, Dict[str, float]] = {}
    for group, stats in summary.items():
        base = baseline["groups"].get(group, {})
        budget = budgets["query_groups"].get(group, {})
        diff[group] = {}
        for key in ("p95_ms", "p99_ms"):
            val = stats.get(key, 0.0)
            limit = budget.get(key, float("inf"))
            if val > limit:
                passed = False
            diff[group][key] = val - base.get(key, val)
        if stats.get("errors", 0) > 0 or stats.get("timeouts", 0) > 0:
            passed = False
    return passed, diff


def gate(
    report_path: Path, baseline_path: Path, budgets_path: Path, scale: str
) -> Tuple[bool, Dict]:
    report = load_json(report_path)
    baseline = load_json(baseline_path)
    budgets = load_budgets(budgets_path, scale)
    groups = merge_segments(report.get("runs", []))
    summary = summarize(groups)
    passed, diff = compare(summary, baseline, budgets)
    result = {"summary": summary, "diff": diff, "passed": passed}
    return passed, result


def main() -> None:  # pragma: no cover - CLI wrapper
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    g = sub.add_parser("gate")
    g.add_argument("--report", required=True)
    g.add_argument("--baseline", required=True)
    g.add_argument("--budgets", required=True)
    g.add_argument("--scale", default="S")
    g.add_argument("--out", default="kg/reports/perf-gate.txt")
    args = parser.parse_args()
    passed, result = gate(
        Path(args.report), Path(args.baseline), Path(args.budgets), args.scale
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
