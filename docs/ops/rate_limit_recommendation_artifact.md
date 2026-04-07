# API Rate-Limit Recommendation Artifact

Date: April 6, 2026

Artifact id: `api-rate-limit-recommendation.v1`

This document defines the minimum machine-readable recommendation payload for
single-host API rate-limit advice. It is informational only and does not mutate
runtime configuration.

## Contract

Required top-level fields:

- `schema_version`
- `generated_at`
- `status`
- `observation_window`
- `runtime_context`
- `route_class_metrics`
- `capacity_inputs`
- `recommendations`
- `clamp_reasons`
- `operator_override`

`status` values:

- `ready`
- `insufficient_evidence`
- `unsupported_topology`

`route_class_metrics` keys:

- `health`
- `query`
- `answer`
- `other`

Each route class payload keeps only the minimum fields needed by recommendation
logic:

- `request_count`
- `p95_latency_ms`
- `rate_429`
- `rate_503`
- `concurrency_saturation_rate`
- `eligible_for_capacity_math`

## Example (`api-rate-limit-recommendation.v1`)

```json
{
  "schema_version": "api-rate-limit-recommendation.v1",
  "generated_at": "2026-04-06T20:36:19Z",
  "status": "ready",
  "observation_window": {
    "started_at": "2026-04-06T20:20:00Z",
    "ended_at": "2026-04-06T20:35:00Z",
    "duration_seconds": 900,
    "non_health_request_count": 284,
    "minimum_duration_seconds": 900,
    "minimum_non_health_request_count": 200,
    "window_eligible": true
  },
  "runtime_context": {
    "topology": "single_host",
    "declared_instance_count": 1,
    "runtime_state_backend": "process_local",
    "request_timeout_seconds": 5.0,
    "concurrency_limit": 16
  },
  "route_class_metrics": {
    "health": {
      "request_count": 28,
      "p95_latency_ms": 24.7,
      "rate_429": 0.0,
      "rate_503": 0.0,
      "concurrency_saturation_rate": 0.0,
      "eligible_for_capacity_math": false
    },
    "query": {
      "request_count": 220,
      "p95_latency_ms": 310.4,
      "rate_429": 0.01,
      "rate_503": 0.0,
      "concurrency_saturation_rate": 0.02,
      "eligible_for_capacity_math": true
    },
    "answer": {
      "request_count": 64,
      "p95_latency_ms": 1160.8,
      "rate_429": 0.0,
      "rate_503": 0.0,
      "concurrency_saturation_rate": 0.04,
      "eligible_for_capacity_math": true
    },
    "other": {
      "request_count": 0,
      "p95_latency_ms": 0.0,
      "rate_429": 0.0,
      "rate_503": 0.0,
      "concurrency_saturation_rate": 0.0,
      "eligible_for_capacity_math": false
    }
  },
  "capacity_inputs": {
    "slowest_eligible_route_class": "answer",
    "safety_factor": 0.7,
    "base_capacity_rpm": 579,
    "penalty_multipliers": {
      "error_pressure": 1.0,
      "concurrency_pressure": 1.0,
      "latency_pressure": 1.0
    },
    "host_budget_rpm": 579
  },
  "recommendations": {
    "authenticated_per_minute": 145,
    "anonymous_per_minute": 36,
    "min_clamp": {
      "authenticated_per_minute": 40,
      "anonymous_per_minute": 10
    },
    "max_clamp": {
      "authenticated_per_minute": 240,
      "anonymous_per_minute": 60
    }
  },
  "clamp_reasons": [],
  "operator_override": {
    "env_vars_authoritative": true,
    "authoritative_env_vars": [
      "EARCRAWLER_API_AUTH_PER_MIN",
      "EARCRAWLER_API_ANON_PER_MIN"
    ],
    "note": "Informational recommendation only. Config changes require explicit operator action."
  }
}
```
