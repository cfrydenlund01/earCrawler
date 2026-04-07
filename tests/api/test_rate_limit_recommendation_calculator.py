from __future__ import annotations

from service.api_server.runtime_state import (
    RateLimitRecommendationContext,
    build_rate_limit_recommendation,
)


def _recommendation_inputs(
    *,
    query_count: int,
    query_p95_ms: float,
    query_rate_429: float = 0.0,
    query_rate_503: float = 0.0,
    query_saturation_rate: float = 0.0,
    answer_count: int = 0,
    answer_p95_ms: float = 0.0,
    answer_rate_429: float = 0.0,
    answer_rate_503: float = 0.0,
    answer_saturation_rate: float = 0.0,
) -> dict[str, object]:
    return {
        "started_at": "2026-04-06T20:00:00Z",
        "duration_seconds": 900.0,
        "total_request_count": query_count + answer_count,
        "route_classes": {
            "health": {
                "request_count": 0,
                "p95_latency_ms": 0.0,
                "rate_429": 0.0,
                "rate_503": 0.0,
                "concurrency_saturation_rate": 0.0,
            },
            "query": {
                "request_count": query_count,
                "p95_latency_ms": query_p95_ms,
                "rate_429": query_rate_429,
                "rate_503": query_rate_503,
                "concurrency_saturation_rate": query_saturation_rate,
            },
            "answer": {
                "request_count": answer_count,
                "p95_latency_ms": answer_p95_ms,
                "rate_429": answer_rate_429,
                "rate_503": answer_rate_503,
                "concurrency_saturation_rate": answer_saturation_rate,
            },
            "other": {
                "request_count": 0,
                "p95_latency_ms": 0.0,
                "rate_429": 0.0,
                "rate_503": 0.0,
                "concurrency_saturation_rate": 0.0,
            },
        },
    }


def _context() -> RateLimitRecommendationContext:
    return RateLimitRecommendationContext(
        topology="single_host",
        declared_instance_count=1,
        request_timeout_seconds=5.0,
        concurrency_limit=16,
    )


def test_recommendation_low_capacity_window_clamps_to_minimum() -> None:
    payload = build_rate_limit_recommendation(
        recommendation_inputs=_recommendation_inputs(
            query_count=220,
            query_p95_ms=4500.0,
            query_rate_503=0.01,
            query_saturation_rate=0.10,
        ),
        runtime_state_backend="process_local",
        context=_context(),
    )

    assert payload["status"] == "ready"
    assert payload["capacity_inputs"]["slowest_eligible_route_class"] == "query"
    assert payload["capacity_inputs"]["host_budget_rpm"] == 27
    assert payload["recommendations"]["authenticated_per_minute"] == 40
    assert payload["recommendations"]["anonymous_per_minute"] == 10
    assert "error_pressure" in payload["clamp_reasons"]
    assert "concurrency_pressure" in payload["clamp_reasons"]
    assert "latency_pressure" in payload["clamp_reasons"]
    assert "min_clamp" in payload["clamp_reasons"]


def test_recommendation_nominal_capacity_window_remains_within_bounds() -> None:
    payload = build_rate_limit_recommendation(
        recommendation_inputs=_recommendation_inputs(
            query_count=120,
            query_p95_ms=320.0,
            answer_count=100,
            answer_p95_ms=1100.0,
        ),
        runtime_state_backend="process_local",
        context=_context(),
    )

    assert payload["status"] == "ready"
    assert payload["capacity_inputs"]["slowest_eligible_route_class"] == "answer"
    assert payload["capacity_inputs"]["host_budget_rpm"] == 610
    assert payload["recommendations"]["authenticated_per_minute"] == 152
    assert payload["recommendations"]["anonymous_per_minute"] == 38
    assert payload["clamp_reasons"] == []
    assert payload["operator_override"]["env_vars_authoritative"] is True


def test_recommendation_high_capacity_window_clamps_to_maximum() -> None:
    payload = build_rate_limit_recommendation(
        recommendation_inputs=_recommendation_inputs(
            query_count=240,
            query_p95_ms=250.0,
        ),
        runtime_state_backend="process_local",
        context=_context(),
    )

    assert payload["status"] == "ready"
    assert payload["capacity_inputs"]["host_budget_rpm"] == 2688
    assert payload["recommendations"]["authenticated_per_minute"] == 240
    assert payload["recommendations"]["anonymous_per_minute"] == 60
    assert "max_clamp" in payload["clamp_reasons"]
