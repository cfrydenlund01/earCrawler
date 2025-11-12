import json
import yaml
from pathlib import Path
from earCrawler.utils import perf_report


def test_gate_pass_fail(tmp_path):
    report_good = {
        "runs": [
            {
                "results": [
                    {
                        "group": "lookup",
                        "latencies_ms": [10, 20, 30],
                        "errors": 0,
                        "timeouts": 0,
                    }
                ]
            }
        ]
    }
    report_bad = {
        "runs": [
            {
                "results": [
                    {
                        "group": "lookup",
                        "latencies_ms": [2000, 3000],
                        "errors": 0,
                        "timeouts": 0,
                    }
                ]
            }
        ]
    }
    baseline = {"groups": {"lookup": {"p95_ms": 15, "p99_ms": 20}}}
    budgets = {
        "scales": {"S": {"query_groups": {"lookup": {"p95_ms": 100, "p99_ms": 120}}}}
    }
    rp = tmp_path / "r.json"
    bp = tmp_path / "b.json"
    bud = tmp_path / "bud.yml"
    bp.write_text(json.dumps(baseline))
    bud.write_text(yaml.safe_dump(budgets))
    # good run
    rp.write_text(json.dumps(report_good))
    passed, _ = perf_report.gate(rp, bp, bud, "S")
    assert passed
    # bad run
    rp.write_text(json.dumps(report_bad))
    passed, _ = perf_report.gate(rp, bp, bud, "S")
    assert not passed
