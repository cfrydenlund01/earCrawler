from earCrawler.utils import perf_report


def test_percentile_and_diff():
    runs = [
        {
            "results": [
                {
                    "group": "lookup",
                    "latencies_ms": [10, 20, 30, 40, 50],
                    "errors": 0,
                    "timeouts": 0,
                }
            ]
        }
    ]
    groups = perf_report.merge_segments(runs)
    summary = perf_report.summarize(groups)
    lookup = summary["lookup"]
    assert lookup["p50_ms"] == 30
    assert round(lookup["p95_ms"], 1) == 48.0
    baseline = {"groups": {"lookup": {"p95_ms": 50, "p99_ms": 60}}}
    budgets = {"query_groups": {"lookup": {"p95_ms": 100, "p99_ms": 120}}}
    passed, diff = perf_report.compare(summary, baseline, budgets)
    assert passed
    assert diff["lookup"]["p95_ms"] == -2
