import json
import yaml
from pathlib import Path
from earCrawler.utils import perf_report


def test_timeout_causes_failure(tmp_path):
    report = {
        "runs": [
            {
                "results": [
                    {
                        "group": "lookup",
                        "latencies_ms": [10],
                        "errors": 0,
                        "timeouts": 1,
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
    rp.write_text(json.dumps(report))
    bp.write_text(json.dumps(baseline))
    bud.write_text(yaml.safe_dump(budgets))
    passed, result = perf_report.gate(rp, bp, bud, "S")
    assert not passed
    assert result["summary"]["lookup"]["timeouts"] == 1
