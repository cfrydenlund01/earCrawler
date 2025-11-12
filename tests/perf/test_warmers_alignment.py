from __future__ import annotations

import json
from pathlib import Path

import yaml


def test_warm_queries_align_with_budgets() -> None:
    warmers = json.loads(
        Path("perf/warmers/warm_queries.json").read_text(encoding="utf-8")
    )
    budgets = yaml.safe_load(
        Path("perf/config/perf_budgets.yml").read_text(encoding="utf-8")
    )["scales"]["S"]["query_groups"]
    warmer_groups = {entry["group"] for entry in warmers}

    # Every budgeted group must have a warmer and the underlying query file must be annotated.
    assert set(budgets.keys()).issubset(warmer_groups)

    for entry in warmers:
        file_path = Path(entry["file"])
        assert file_path.is_file(), f"missing warm query: {file_path}"
        group = entry["group"]
        assert group in budgets, f"group '{group}' not budgeted"
        text = file_path.read_text(encoding="utf-8")
        assert f"# @group: {group}" in text
        assert entry["repeat"] >= 1
