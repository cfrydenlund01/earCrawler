from __future__ import annotations

from earCrawler.observability.canary import CanaryBudget, evaluate_canary_response


def test_canary_passes_within_budget():
    budget = CanaryBudget(max_latency_ms=500, min_rows=1, expect_status=200)
    result = evaluate_canary_response(
        name="api-search",
        latency_ms=320,
        observed_rows=5,
        status_code=200,
        budget=budget,
    )
    assert result.ok
    assert result.status == "pass"


def test_canary_fails_on_latency_and_rows():
    budget = CanaryBudget(max_latency_ms=200, min_rows=2, expect_status=200)
    result = evaluate_canary_response(
        name="api-search",
        latency_ms=250,
        observed_rows=1,
        status_code=500,
        budget=budget,
    )
    assert not result.ok
    assert "latency" in result.message
    assert "rows" in result.message
    assert "status" in result.message
